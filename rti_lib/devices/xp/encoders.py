"""
rti_lib/devices/xp/encoders.py — TLV builders for XP processor streams.

XP macros consist of:
  1.  One or more *command* TLV blocks (serial, driver, etc.)
  2.  Each command is wrapped in a *commands container* (TAG=01 CONTAINER)
      that identifies the device protocol (serial/driver hash).
  3.  The commands container sits inside an *inner macro* container (TAG=01)
      which carries the macro name and sequence number.
  4.  All macros go in a *macro group* container (TAG=01), followed by an
      empty secondary group (TAG=02) that Integration Designer always writes.

Wire-format reference: rti_lib/core/tlv.py
"""

from ...core import tlv

# ---- 7-byte device-protocol hashes (observed in Test2/Test3.rti) --------
# These identify the communication protocol used for a command.
# The hash is stored in a BLOB inside the commands container header.
DEVICE_HASH_SERIAL = bytes([0xA0, 0xC4, 0x7C, 0x06, 0x00, 0x00, 0x00])
DEVICE_HASH_IR     = bytes([0x50, 0xC4, 0x7C, 0x06, 0x00, 0x00, 0x00])
DEVICE_HASH_DRIVER = bytes([0x48, 0xC7, 0xE7, 0x00, 0x00, 0x00, 0x00])

# ---- Baud-rate → baud_byte encoding (TAG=06 BYTE in serial command) ------
# RTI encodes baud rates as a byte: baud / 50 (e.g. 9600 → 192, 19200 → 384→128)
BAUD_TABLE = {
    300:   6,
    600:   12,
    1200:  24,
    2400:  48,
    4800:  96,
    9600:  192,
    19200: 128,
    38400: 200,
}

# 8 data bits, No parity, 1 stop bit — the most common serial setting.
SERIAL_SETTINGS_8N1 = 0x88


# ---------------------------------------------------------------------------
# Serial / driver command builders
# ---------------------------------------------------------------------------

def encode_serial_command_tlv(
        serial_string: bytes,
        baud_rate: int = 9600,
        port_num: int = 0,
        settings_byte: int = SERIAL_SETTINGS_8N1,
        manufacturer: str = '',
        model_str: str = '',
        device_name: str = '',
        command_name: str = 'Serial Command',
) -> bytes:
    """
    Encode a serial command into the nested VARSTR TLV format used inside
    a commands container.

    serial_string : raw bytes to send (e.g. b'src tv\\r')
    baud_rate     : one of the keys in BAUD_TABLE (default 9600)
    port_num      : serial port index on the processor (0-based)
    settings_byte : 0x88 = 8-N-1 (see SERIAL_SETTINGS_8N1)
    manufacturer  : optional label for Integration Designer UI
    model_str     : optional label for Integration Designer UI
    device_name   : optional label for Integration Designer UI
    command_name  : display name shown in the macro list
    """
    baud_byte = BAUD_TABLE.get(baud_rate, 192)
    return (
        tlv.encode_varstr(0x02, manufacturer) +
        tlv.encode_varstr(0x03, model_str) +
        tlv.encode_varstr(0x04, device_name) +
        tlv.encode_varstr(0x05, command_name) +
        tlv.encode_i32(0x01, port_num) +
        tlv.encode_byte(0x01, 0) +
        tlv.encode_u16(0x01, 0) +
        tlv.encode_u16(0x02, 4) +
        tlv.encode_byte(0x02, 0) +
        tlv.encode_byte(0x03, 0) +
        tlv.encode_byte(0x04, 0) +
        tlv.encode_byte(0x0A, 1) +
        tlv.encode_byte(0x06, baud_byte) +
        tlv.encode_byte(0x07, settings_byte) +
        tlv.encode_byte(0x08, 0) +
        tlv.encode_byte(0x09, 1) +
        tlv.encode_varstr_raw(0x01, serial_string) +
        tlv.encode_i32(0x02, -1) +
        tlv.TERMINATOR
    )


def encode_driver_command_tlv(
        driver_guid: bytes,
        export_name: str,
        string_param: str = '',
        slot_index: int = 0,
        timeout_ms: int = 200,
) -> bytes:
    """
    Encode an RTI driver command TLV block.

    driver_guid  : 16-byte driver GUID (identifies the installed RTI driver)
    export_name  : driver export function name (e.g. 'SendHTTP')
    string_param : string argument to the function
    slot_index   : driver slot index (0-based)
    timeout_ms   : command timeout in milliseconds
    """
    if len(driver_guid) != 16:
        raise ValueError("driver_guid must be 16 bytes")
    driver_block = (
        tlv.encode_blob(0x01, driver_guid) +
        tlv.encode_i32(0x01, slot_index) +
        tlv.encode_varstr(0x01, export_name) +
        tlv.encode_byte(0x01, 0) +
        tlv.encode_i32(0x02, timeout_ms) +
        tlv.encode_i32(0x03, -1) +
        tlv.encode_varstr(0x02, string_param) +
        tlv.TERMINATOR
    )
    return (
        tlv.encode_varstr(0x02, '') +
        tlv.encode_varstr(0x03, '') +
        tlv.encode_varstr(0x04, '') +
        tlv.encode_varstr(0x05, '') +
        tlv.encode_varstr_raw(0x06, driver_block) +
        tlv.TERMINATOR
    )


def encode_commands_container(device_hash: bytes,
                              command_tlv_bytes: bytes) -> bytes:
    """
    Wrap a command TLV block in a TAG=01 CONTAINER commands container.

    The commands container is the mid-level wrapper that identifies which
    device protocol the command uses (via the 7-byte device_hash).

    device_hash        : one of DEVICE_HASH_SERIAL / DEVICE_HASH_DRIVER / …
    command_tlv_bytes  : output of encode_serial_command_tlv() etc.
    """
    if len(device_hash) != 7:
        raise ValueError("device_hash must be 7 bytes")
    content = (
        tlv.encode_u16(0x01, 1) +
        tlv.encode_blob(0x01, device_hash) +
        tlv.encode_varstr_raw(0x01, command_tlv_bytes) +
        tlv.TERMINATOR
    )
    return tlv.encode_container(0x01, content)


# ---------------------------------------------------------------------------
# Macro container builders
# ---------------------------------------------------------------------------

def encode_inner_macro(seq_num: int, name: str,
                       commands_bytes: bytes) -> bytes:
    """
    Encode a single macro as a TAG=01 CONTAINER.

    This is the innermost macro wrapper.  The outer macro group container
    (encode_macro_group) holds a list of these.

    seq_num        : 1-based macro sequence number (must be unique per project)
    name           : macro display name
    commands_bytes : output of encode_commands_container()
    """
    content = (
        tlv.encode_i32(0x01, 254) +        # macro type sentinel
        tlv.encode_i32(0x02, seq_num) +    # sequence number
        tlv.encode_i32(0x03, 0) +
        tlv.encode_byte(0x02, 0xFF) +
        tlv.encode_byte(0x03, 0) +
        tlv.encode_byte(0x04, 0) +
        tlv.encode_byte(0x05, 0) +
        tlv.encode_byte(0x06, 0) +
        tlv.encode_i32(0x0E, -1) +
        tlv.encode_byte(0x0E, 1) +
        tlv.encode_varstr(0x04, name) +    # macro display name
        commands_bytes +
        tlv.TERMINATOR
    )
    return tlv.encode_container(0x01, content)


def encode_macro_group(inner_macros: list, group_name: str = '') -> bytes:
    """
    Encode the primary macro group as a TAG=01 CONTAINER.

    This is the outermost level for macro definitions in an XP stream.
    It uses the same group-header format as button groups.

    inner_macros : list of bytes from encode_inner_macro()
    group_name   : optional group label (usually empty string)
    """
    from ..common import _encode_group_header
    content = (
        _encode_group_header(group_name) +
        b''.join(inner_macros) +
        tlv.TERMINATOR
    )
    return tlv.encode_container(0x01, content)


def encode_empty_macro_group() -> bytes:
    """
    Encode the secondary empty macro group (TAG=02 CONTAINER).

    Integration Designer always appends an empty TAG=02 group after the
    primary macro group in XP streams.  The contents are just the group
    header + terminator (no macros).
    """
    from ..common import _encode_group_header
    return tlv.encode_container(0x02, _encode_group_header() + tlv.TERMINATOR)
