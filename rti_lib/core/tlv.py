"""
RTI TLV (Tag-Length-Value) decoder and encoder for Device Data Streams.

RTI uses a custom TLV format inside Device Data Streams within .rti OLE2 files.

TLV Wire Format:
  [TAG: 1 byte][TYPE: 1 byte][VALUE: variable]
  Terminator: 0xFF 0xFF (or single 0xFF at end)

TYPE codes and value sizes:
  0x20 = BYTE    : 1 byte unsigned
  0x40 = U16     : 2 bytes little-endian unsigned
  0x60 = I32     : 4 bytes little-endian signed
  0x80 = BLOB    : 1 byte length prefix + N data bytes
  0xA0 = VARSTR  : 2 bytes LE length prefix + N UTF-16LE chars
  0xC0 = CONTAINER: 4 bytes LE length prefix + nested TLV bytes
  0xE0 = GUID    : 16 bytes fixed

Some VARSTR tags have an extra 2-byte uint16 index as the first 2 bytes of value:
  Indexed VARSTR tags: 0x04, 0x08, 0x09, 0x0C, 0x0F, 0x1D

Stream Header (first ~20 bytes):
  [0x00] TAG=0x01 TYPE=0x20 VAL=device_type_byte
  [0x03] TAG=0x03 TYPE=0x20 VAL=model_number
  [0x06] TAG=0x34 TYPE=0x60 VAL=timeout_seconds (I32)
  [0x0F] TAG=0x01 TYPE=0x40 VAL=format_version (U16)
"""

import struct

# TYPE code constants
T_BYTE = 0x20
T_U16 = 0x40
T_I32 = 0x60
T_BLOB = 0x80
T_VARSTR = 0xA0
T_CONTAINER = 0xC0
T_GUID = 0xE0

TYPE_NAMES = {
    T_BYTE: 'BYTE',
    T_U16: 'U16',
    T_I32: 'I32',
    T_BLOB: 'BLOB',
    T_VARSTR: 'VARSTR',
    T_CONTAINER: 'CONTAINER',
    T_GUID: 'GUID',
}

# Tags whose VARSTR value starts with a 2-byte uint16 index
INDEXED_VARSTR_TAGS = {0x04, 0x08, 0x09, 0x0C, 0x0F, 0x1D}


class TLVNode:
    """A single decoded TLV record."""
    def __init__(self, tag, type_code, value, raw_value=None, offset=0):
        self.tag = tag
        self.type_code = type_code
        self.value = value        # Python-native decoded value
        self.raw_value = raw_value  # raw bytes of just the value field
        self.offset = offset      # byte offset in stream where this node started
        self.children = []        # populated for CONTAINER nodes

    def type_name(self):
        return TYPE_NAMES.get(self.type_code, f'0x{self.type_code:02X}')

    def __repr__(self):
        v = self.value
        if isinstance(v, bytes) and len(v) > 16:
            v = v[:16].hex() + '...'
        elif isinstance(v, bytes):
            v = v.hex()
        return f"TLVNode(tag=0x{self.tag:02X}, type={self.type_name()}, value={v!r})"


def decode(data: bytes, offset: int = 0, length: int = None) -> list:
    """
    Decode TLV records from data starting at offset.
    Returns list of TLVNode objects.
    If length is specified, only decode up to offset+length bytes.
    """
    if length is None:
        end = len(data)
    else:
        end = offset + length

    nodes = []
    pos = offset

    while pos < end - 1:
        tag = data[pos]
        type_code = data[pos + 1]

        # Terminator
        if tag == 0xFF and type_code == 0xFF:
            break
        if tag == 0xFF:
            break

        node_offset = pos
        pos += 2

        if type_code == T_BYTE:
            if pos >= end:
                break
            raw = data[pos:pos+1]
            value = data[pos]
            pos += 1

        elif type_code == T_U16:
            if pos + 2 > end:
                break
            raw = data[pos:pos+2]
            value = struct.unpack_from('<H', data, pos)[0]
            pos += 2

        elif type_code == T_I32:
            if pos + 4 > end:
                break
            raw = data[pos:pos+4]
            value = struct.unpack_from('<i', data, pos)[0]
            pos += 4

        elif type_code == T_BLOB:
            if pos >= end:
                break
            blen = data[pos]
            pos += 1
            raw = data[pos:pos+blen]
            value = raw
            pos += blen

        elif type_code == T_VARSTR:
            if pos + 2 > end:
                break
            slen = struct.unpack_from('<H', data, pos)[0]
            pos += 2
            raw = data[pos:pos+slen]
            if tag in INDEXED_VARSTR_TAGS and slen >= 2:
                index = struct.unpack_from('<H', raw, 0)[0]
                # TAG=0x0F has an extra FF FF separator after the index
                if tag == 0x0F and slen >= 4 and raw[2:4] == b'\xFF\xFF':
                    text = raw[4:].decode('utf-16-le', errors='replace')
                else:
                    text = raw[2:].decode('utf-16-le', errors='replace')
                value = (index, text)
            else:
                value = raw.decode('utf-16-le', errors='replace')
            pos += slen

        elif type_code == T_CONTAINER:
            if pos + 4 > end:
                break
            clen = struct.unpack_from('<I', data, pos)[0]
            pos += 4
            raw = data[pos:pos+clen]
            value = raw
            node = TLVNode(tag, type_code, value, raw, node_offset)
            node.children = decode(raw)
            nodes.append(node)
            pos += clen
            continue

        elif type_code == T_GUID:
            raw = data[pos:pos+16]
            value = raw
            pos += 16

        else:
            # Unknown type — stop parsing to avoid garbage
            break

        node = TLVNode(tag, type_code, value, raw if 'raw' in dir() else None, node_offset)
        nodes.append(node)

    return nodes


def encode_byte(tag: int, value: int) -> bytes:
    return bytes([tag, T_BYTE, value & 0xFF])


def encode_u16(tag: int, value: int) -> bytes:
    return bytes([tag, T_U16]) + struct.pack('<H', value & 0xFFFF)


def encode_i32(tag: int, value: int) -> bytes:
    return bytes([tag, T_I32]) + struct.pack('<i', value)


def encode_blob(tag: int, data: bytes) -> bytes:
    assert len(data) <= 255, "BLOB max 255 bytes"
    return bytes([tag, T_BLOB, len(data)]) + data


def encode_varstr(tag: int, text: str, index: int = None) -> bytes:
    """Encode a VARSTR. If index is given, prepend the 2-byte index."""
    utf16 = text.encode('utf-16-le')
    if index is not None:
        payload = struct.pack('<H', index) + utf16
    else:
        payload = utf16
    return bytes([tag, T_VARSTR]) + struct.pack('<H', len(payload)) + payload


def encode_varstr_raw(tag: int, raw_bytes: bytes) -> bytes:
    """Encode a VARSTR with raw byte content (not UTF-16LE). Used for
    nested TLV blocks stored inside a VARSTR field (e.g. command blocks)
    and for serial command strings stored as raw ASCII bytes."""
    return bytes([tag, T_VARSTR]) + struct.pack('<H', len(raw_bytes)) + raw_bytes


def encode_macro_name(index: int, name: str) -> bytes:
    """Encode a macro name as TAG=0x0F VARSTR with [2B index][FF FF][UTF-16LE name].
    This is the indexed VARSTR format used for macro names in controller streams."""
    utf16 = name.encode('utf-16-le')
    payload = struct.pack('<H', index) + b'\xFF\xFF' + utf16
    return bytes([0x0F, T_VARSTR]) + struct.pack('<H', len(payload)) + payload


def encode_container(tag: int, children_bytes: bytes) -> bytes:
    return bytes([tag, T_CONTAINER]) + struct.pack('<I', len(children_bytes)) + children_bytes


def encode_guid(tag: int, guid_bytes: bytes) -> bytes:
    assert len(guid_bytes) == 16
    return bytes([tag, T_GUID]) + guid_bytes


TERMINATOR = b'\xFF\xFF'


def nodes_to_bytes(nodes: list) -> bytes:
    """Serialize a list of TLVNode objects back to wire format."""
    parts = []
    for node in nodes:
        t = node.tag
        tc = node.type_code
        v = node.raw_value if node.raw_value is not None else b''

        if tc == T_BYTE:
            parts.append(bytes([t, tc, node.value & 0xFF]))
        elif tc == T_U16:
            parts.append(bytes([t, tc]) + struct.pack('<H', node.value))
        elif tc == T_I32:
            parts.append(bytes([t, tc]) + struct.pack('<i', node.value))
        elif tc == T_BLOB:
            parts.append(bytes([t, tc, len(v)]) + v)
        elif tc == T_VARSTR:
            parts.append(bytes([t, tc]) + struct.pack('<H', len(v)) + v)
        elif tc == T_CONTAINER:
            if node.children:
                inner = nodes_to_bytes(node.children)
            else:
                inner = v
            parts.append(bytes([t, tc]) + struct.pack('<I', len(inner)) + inner)
        elif tc == T_GUID:
            parts.append(bytes([t, tc]) + v)

    return b''.join(parts)


def print_nodes(nodes: list, indent: int = 0):
    """Pretty-print a list of TLVNode objects."""
    prefix = '  ' * indent
    for node in nodes:
        type_name = node.type_name()
        v = node.value
        if isinstance(v, bytes):
            if len(v) > 32:
                vstr = v[:32].hex(' ') + ' ...'
            else:
                vstr = v.hex(' ')
        elif isinstance(v, tuple):
            vstr = f"[{v[0]}] {v[1]!r}"
        else:
            vstr = repr(v)
        print(f"{prefix}[0x{node.offset:04X}] TAG=0x{node.tag:02X} {type_name}: {vstr}")
        if node.children:
            print_nodes(node.children, indent + 1)
