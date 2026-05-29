"""
rti_lib/core/fields.py

Named field constants and field registry for RTI device data streams.

All RTI remote device streams (U1, U2, T2i, T2+) share the same 350-node
TLV header structure.  The registry maps each position to a human-readable
name, expected TLV tag/type, and known value labels.

IMPORTANT: TLV tag bytes are REUSED throughout every stream.  The same tag
byte can appear dozens of times with completely different meanings depending
on its position in the stream.  Constants here are therefore prefixed by the
stream section where they are used (CFG_, NET_, ID_, SLT_).

Usage in stream profiles::

    from rti_lib.core.fields import CFG, NET, ID, SLT

    e.append(tlv.encode_byte(CFG_DEVICE_TYPE, _DEVICE_TYPE_U2))  # pos 0
    e.append(tlv.encode_byte(CFG_POLLING_RATE, 10))               # pos 1

Usage in the diff / inspect tool::

    from rti_lib.core.fields import STREAM_FIELDS, field_label

    label = field_label(position)
"""

from dataclasses import dataclass, field as dc_field
from typing import Any, Dict
from rti_lib.core.tlv import T_BYTE, T_U16, T_I32, T_BLOB, T_VARSTR, T_GUID, T_CONTAINER  # noqa: F401

# ---------------------------------------------------------------------------
# TLV tag byte constants — grouped by stream section
# ---------------------------------------------------------------------------
# Each constant is the raw byte value written as the first byte of a TLV
# record.  The same numeric value re-appears across sections with different
# meaning; hence the section prefixes.

# -- Device config (positions 0–36) -----------------------------------------
CFG_DEVICE_TYPE        = 0x01   # pos  0  BYTE  hardware device type
CFG_POLLING_RATE       = 0x03   # pos  1  BYTE  RF polling rate (default 10)
CFG_NTP_SYNC_INTERVAL  = 0x34   # pos  2  I32   NTP re-sync interval (seconds)
CFG_UNKNOWN_04         = 0x04   # pos  3  BYTE  unknown (always 0)
CFG_PROTOCOL_VERSION   = 0x01   # pos  4  U16   protocol format version (always 2)
CFG_IS_PROCESSOR       = 0x07   # pos  5  BYTE  0 = remote, 1 = XP processor
CFG_UNKNOWN_08         = 0x08   # pos  6  BYTE  unknown (always 0)
CFG_DEVICE_CATEGORY    = 0x26   # pos  7  BYTE  2 = handheld remote, 0 = processor
CFG_UNKNOWN_27         = 0x27   # pos  8  BYTE  0 = remote, 1 = XP
CFG_HAS_PHYS_BUTTONS   = 0x0B   # pos  9  BYTE  1 = physical IR buttons, 0 = touchscreen only
CFG_UNKNOWN_0C         = 0x0C   # pos 10  BYTE  unknown (always 0)
CFG_UI_VERSION         = 0x2D   # pos 11  BYTE  1 = mono B&W (U1/U2), 2 = colour (T2i)
CFG_UNKNOWN_2C         = 0x2C   # pos 12  BYTE  unknown (always 1)
CFG_UNKNOWN_0E         = 0x0E   # pos 13  BYTE  unknown (always 1)
CFG_UNKNOWN_0F_B       = 0x0F   # pos 14  BYTE  unknown (always 0)
CFG_UNKNOWN_11         = 0x11   # pos 15  BYTE  unknown (always 0)
CFG_IDLE_TIMEOUT       = 0x01   # pos 16  I32   idle timeout (milliseconds)
CFG_UNKNOWN_13_B       = 0x13   # pos 17  BYTE  unknown (always 0)
CFG_BACKLIGHT_MAX      = 0x24   # pos 18  I32   backlight maximum level (0–255)
CFG_BACKLIGHT_ON       = 0x04   # pos 19  I32   backlight on percentage
CFG_BACKLIGHT_DIM      = 0x05   # pos 20  I32   backlight dimmed percentage
CFG_BACKLIGHT_OFF      = 0x06   # pos 21  I32   backlight off value (−1 = never)
CFG_MOTION_ON          = 0x07   # pos 22  I32   motion-on threshold
CFG_MOTION_DIM         = 0x08   # pos 23  I32   motion-dim threshold
CFG_MOTION_OFF         = 0x09   # pos 24  I32   motion-off threshold
CFG_KEYCLICK_VOL       = 0x13   # pos 25  I32   key-click volume
CFG_KEYCLICK_ON        = 0x14   # pos 26  I32   key-click on flag
CFG_VIBRATION_MS       = 0x15   # pos 27  I32   vibration duration (ms)
CFG_HAS_TOUCHSCREEN    = 0x16   # pos 28  BYTE  1 = has touchscreen, 0 = button-only
CFG_UNKNOWN_2B         = 0x2B   # pos 29  BYTE  unknown (always 1)
CFG_RF_CHANNEL         = 0x0A   # pos 30  I32   RF channel number
CFG_RF_CHANNEL_COUNT   = 0x0B   # pos 31  I32   RF channel count
CFG_RF_RETRY_COUNT     = 0x0D   # pos 32  I32   RF retry count (−1 = unlimited)
CFG_UNKNOWN_17         = 0x17   # pos 33  BYTE  unknown (always 0)
CFG_UNKNOWN_19         = 0x19   # pos 34  BYTE  unknown (always 1)
CFG_UNKNOWN_1A         = 0x1A   # pos 35  BYTE  unknown (always 1)
CFG_UNKNOWN_1B         = 0x1B   # pos 36  BYTE  unknown (always 1)

# -- Network / location (positions 37–53) ------------------------------------
NET_NTP_SERVER         = 0x0A   # pos 37  VARSTR NTP server hostname
NET_UNKNOWN_1C         = 0x1C   # pos 38  BYTE   unknown (always 1)
NET_RF_FREQ_CODE       = 0x16   # pos 39  I32    RF frequency code (8)
NET_UNKNOWN_05         = 0x05   # pos 40  U16    unknown (always 0)
NET_PROTOCOL_GUID      = 0x02   # pos 41  GUID   RTI protocol GUID (shared)
NET_LATITUDE           = 0x08   # pos 42  BLOB   latitude bytes (8, zeroed)
NET_LONGITUDE          = 0x09   # pos 43  BLOB   longitude bytes (8, zeroed)
NET_LOCATION           = 0x0D   # pos 44  VARSTR location / room name
NET_UNKNOWN_24         = 0x24   # pos 45  BYTE   unknown (always 0)
NET_HAS_COLOR          = 0x25   # pos 46  BYTE   1 = colour display (T2i), 0 = mono
NET_UNKNOWN_28         = 0x28   # pos 47  BYTE   unknown (always 0)
NET_UNKNOWN_29         = 0x29   # pos 48  BYTE   unknown (always 3)
NET_DEVICE_GUID        = 0x0D   # pos 49  BLOB   device identity GUID (16 bytes)
NET_UNKNOWN_2A         = 0x2A   # pos 50  BYTE   unknown (always 0)
NET_DISPLAY_DPI        = 0x30   # pos 51  I32    display DPI (U2 = 96, U1/T2i = 0)
NET_UNKNOWN_0F_BLK     = 0x0F   # pos 52  BLOB   unknown (8 zero bytes)
NET_UNKNOWN_10_BLK     = 0x10   # pos 53  BLOB   unknown (8 zero bytes)

# -- Device identity (positions 54–55) ---------------------------------------
ID_MAC_ADDRESS         = 0x1F   # pos 54  VARSTR device MAC address (12 hex chars)
ID_SERIAL              = 0x03   # pos 55  BLOB   device serial number (b'0000')

# -- Slot layout (positions 56–349) ------------------------------------------
SLT_INPUT_SLOT_IDX     = 0x04   # pos  56–64   U16    input slot index (256–264)
SLT_PAGE_GROUP_ID      = 0x1D   # pos  65–68   I32    page group ID
SLT_GROUP_NAME         = 0x08   # pos  69–84   VARSTR group slot name (indexed)
SLT_GROUP_STATE        = 0x0C   # pos  85–92   BLOB   group slot state
SLT_VARIABLE_NAME      = 0x09   # pos  93–348  VARSTR variable slot name (indexed)
SLT_PAGE_CAP_U2        = 0x06   # pos 349      BLOB   page-cap sentinel (U2/U1)
SLT_PAGE_CAP_T2I       = 0x0A   # pos 349      BLOB   page-cap sentinel (T2i)

# ---------------------------------------------------------------------------
# Field registry
# ---------------------------------------------------------------------------

@dataclass
class FieldDef:
    """Metadata for a single stream position (used by the diff / inspect tool)."""
    name: str                                          # snake_case field name
    tag:  int                                          # expected TLV tag byte
    type_code: int                                     # expected TLV type byte
    description: str = ''                             # human-readable explanation
    known_values: Dict[Any, str] = dc_field(default_factory=dict)

    def fmt_value(self, value: Any) -> str:
        """Format a decoded value, appending a label for known values."""
        if isinstance(value, bytes):
            s = value.hex()
        elif isinstance(value, tuple):
            idx, text = value
            s = f'[{idx}] {text!r}'
        else:
            s = repr(value)
        label = self.known_values.get(value)
        return f'{s}  ({label})' if label else s


def _v(*pairs) -> dict:
    """Shorthand for building known_values dicts from (value, label) pairs."""
    return dict(pairs)


# Ordered list of the 350 common header fields shared by all RTI remote streams.
# Positions 0–348 are always present; position 349 is the page-cap sentinel.
STREAM_FIELDS: list = [
    # ---- device config (pos 0-36) ----
    FieldDef('device_type',          CFG_DEVICE_TYPE,       T_BYTE,
             'Hardware device type byte',
             _v((7, 'T2+'), (17, 'U1'), (29, 'U2'), (75, 'T2i'), (49, 'XP'))),
    FieldDef('polling_rate',         CFG_POLLING_RATE,      T_BYTE,
             'RF polling rate (always 10)'),
    FieldDef('ntp_sync_interval_s',  CFG_NTP_SYNC_INTERVAL, T_I32,
             'NTP re-sync interval in seconds (always 3600)'),
    FieldDef('unknown_04_b',         CFG_UNKNOWN_04,        T_BYTE,
             'Unknown — always 0'),
    FieldDef('protocol_version',     CFG_PROTOCOL_VERSION,  T_U16,
             'Protocol format version (always 2)'),
    FieldDef('is_processor',         CFG_IS_PROCESSOR,      T_BYTE,
             'Device role', _v((0, 'remote'), (1, 'XP processor'))),
    FieldDef('unknown_08_b',         CFG_UNKNOWN_08,        T_BYTE,
             'Unknown — always 0'),
    FieldDef('device_category',      CFG_DEVICE_CATEGORY,   T_BYTE,
             'Device category', _v((0, 'processor'), (2, 'handheld remote'))),
    FieldDef('unknown_27_b',         CFG_UNKNOWN_27,        T_BYTE,
             'Unknown — 0=remote, 1=XP'),
    FieldDef('has_physical_buttons', CFG_HAS_PHYS_BUTTONS,  T_BYTE,
             'Has physical IR buttons', _v((0, 'no'), (1, 'yes'))),
    FieldDef('unknown_0c_b',         CFG_UNKNOWN_0C,        T_BYTE,
             'Unknown — always 0'),
    FieldDef('ui_version',           CFG_UI_VERSION,        T_BYTE,
             'UI / display version',
             _v((1, 'mono B&W (U1/U2)'), (2, 'colour (T2i)'))),
    FieldDef('unknown_2c_b',         CFG_UNKNOWN_2C,        T_BYTE,
             'Unknown — always 1'),
    FieldDef('unknown_0e_b',         CFG_UNKNOWN_0E,        T_BYTE,
             'Unknown — always 1'),
    FieldDef('unknown_0f_b',         CFG_UNKNOWN_0F_B,      T_BYTE,
             'Unknown — always 0'),
    FieldDef('unknown_11_b',         CFG_UNKNOWN_11,        T_BYTE,
             'Unknown — always 0'),
    FieldDef('idle_timeout_ms',      CFG_IDLE_TIMEOUT,      T_I32,
             'Idle timeout in milliseconds (always 25000)'),
    FieldDef('unknown_13_b',         CFG_UNKNOWN_13_B,      T_BYTE,
             'Unknown — always 0'),
    FieldDef('backlight_max',        CFG_BACKLIGHT_MAX,     T_I32,
             'Backlight maximum level 0–255'),
    FieldDef('backlight_on_pct',     CFG_BACKLIGHT_ON,      T_I32,
             'Backlight on percentage'),
    FieldDef('backlight_dim_pct',    CFG_BACKLIGHT_DIM,     T_I32,
             'Backlight dimmed percentage'),
    FieldDef('backlight_off_val',    CFG_BACKLIGHT_OFF,     T_I32,
             'Backlight off value (-1 = never off)'),
    FieldDef('motion_on_threshold',  CFG_MOTION_ON,         T_I32,
             'Motion sensor on threshold'),
    FieldDef('motion_dim_threshold', CFG_MOTION_DIM,        T_I32,
             'Motion sensor dim threshold'),
    FieldDef('motion_off_threshold', CFG_MOTION_OFF,        T_I32,
             'Motion sensor off threshold'),
    FieldDef('keyclick_volume',      CFG_KEYCLICK_VOL,      T_I32,
             'Key click volume'),
    FieldDef('keyclick_on',          CFG_KEYCLICK_ON,       T_I32,
             'Key click on flag'),
    FieldDef('vibration_ms',         CFG_VIBRATION_MS,      T_I32,
             'Vibration motor duration (ms)'),
    FieldDef('has_touchscreen',      CFG_HAS_TOUCHSCREEN,   T_BYTE,
             'Has touchscreen display', _v((0, 'no'), (1, 'yes'))),
    FieldDef('unknown_2b_b',         CFG_UNKNOWN_2B,        T_BYTE,
             'Unknown — always 1'),
    FieldDef('rf_channel',           CFG_RF_CHANNEL,        T_I32,
             'RF channel number'),
    FieldDef('rf_channel_count',     CFG_RF_CHANNEL_COUNT,  T_I32,
             'RF channel count'),
    FieldDef('rf_retry_count',       CFG_RF_RETRY_COUNT,    T_I32,
             'RF retry count (-1 = unlimited)'),
    FieldDef('unknown_17_b',         CFG_UNKNOWN_17,        T_BYTE,
             'Unknown — always 0'),
    FieldDef('unknown_19_b',         CFG_UNKNOWN_19,        T_BYTE,
             'Unknown — always 1'),
    FieldDef('unknown_1a_b',         CFG_UNKNOWN_1A,        T_BYTE,
             'Unknown — always 1'),
    FieldDef('unknown_1b_b',         CFG_UNKNOWN_1B,        T_BYTE,
             'Unknown — always 1'),
    # ---- network / location (pos 37-53) ----
    FieldDef('ntp_server',           NET_NTP_SERVER,        T_VARSTR,
             'NTP server hostname'),
    FieldDef('unknown_1c_b',         NET_UNKNOWN_1C,        T_BYTE,
             'Unknown — always 1'),
    FieldDef('rf_frequency_code',    NET_RF_FREQ_CODE,      T_I32,
             'RF frequency code (always 8)'),
    FieldDef('unknown_05_u16',       NET_UNKNOWN_05,        T_U16,
             'Unknown — always 0'),
    FieldDef('protocol_guid',        NET_PROTOCOL_GUID,     T_GUID,
             'RTI protocol GUID (same for all devices)'),
    FieldDef('latitude_bytes',       NET_LATITUDE,          T_BLOB,
             'Device latitude (8 bytes, zeroed when unknown)'),
    FieldDef('longitude_bytes',      NET_LONGITUDE,         T_BLOB,
             'Device longitude (8 bytes, zeroed when unknown)'),
    FieldDef('location_name',        NET_LOCATION,          T_VARSTR,
             'Location / room name'),
    FieldDef('unknown_24_b2',        NET_UNKNOWN_24,        T_BYTE,
             'Unknown — always 0'),
    FieldDef('has_color_display',    NET_HAS_COLOR,         T_BYTE,
             'Has colour display', _v((0, 'no — mono B&W'), (1, 'yes — T2i RGB'))),
    FieldDef('unknown_28_b',         NET_UNKNOWN_28,        T_BYTE,
             'Unknown — always 0'),
    FieldDef('unknown_29_b',         NET_UNKNOWN_29,        T_BYTE,
             'Unknown — always 3'),
    FieldDef('device_guid',          NET_DEVICE_GUID,       T_BLOB,
             'Device identity GUID (16 bytes)'),
    FieldDef('unknown_2a_b',         NET_UNKNOWN_2A,        T_BYTE,
             'Unknown — always 0'),
    FieldDef('display_dpi',          NET_DISPLAY_DPI,       T_I32,
             'Display DPI', _v((0, 'no display / U1'), (96, 'U2 64x128 B&W / T2i 240x320 colour'))),
    FieldDef('unknown_0f_blk',       NET_UNKNOWN_0F_BLK,    T_BLOB,
             'Unknown — 8 zero bytes'),
    FieldDef('unknown_10_blk',       NET_UNKNOWN_10_BLK,    T_BLOB,
             'Unknown — 8 zero bytes'),
    # ---- device identity (pos 54-55) ----
    FieldDef('mac_address',          ID_MAC_ADDRESS,        T_VARSTR,
             'Device MAC address (12 hex chars, no separators)'),
    FieldDef('device_serial',        ID_SERIAL,             T_BLOB,
             'Device serial number (b"0000")'),
    # ---- slot layout (pos 56-64: 9 input slot indices) ----
    *[FieldDef(f'input_slot_idx_{256+i}', SLT_INPUT_SLOT_IDX, T_U16,
               f'Input slot index {256+i}')
      for i in range(9)],
    # ---- pos 65-68: 4 page group IDs ----
    *[FieldDef(f'page_group_id_{i}', SLT_PAGE_GROUP_ID, T_I32,
               f'Page group {i} ID')
      for i in range(4)],
    # ---- pos 69-84: 16 group slot names ----
    *[FieldDef(f'group_slot_name_{i}', SLT_GROUP_NAME, T_VARSTR,
               f'Group slot {i} name')
      for i in range(16)],
    # ---- pos 85-92: 8 group slot state blobs ----
    *[FieldDef(f'group_slot_state_{i}', SLT_GROUP_STATE, T_BLOB,
               f'Group slot {i} state')
      for i in range(8)],
    # ---- pos 93-348: 256 variable slot names ----
    *[FieldDef(f'variable_slot_{i}', SLT_VARIABLE_NAME, T_VARSTR,
               f'Variable slot {i} name')
      for i in range(256)],
    # ---- pos 349: page-capabilities sentinel ----
    FieldDef('page_cap_sentinel', SLT_PAGE_CAP_U2, T_BLOB,
             'Page capabilities sentinel (tag=0x06 U2/U1, tag=0x0A T2i)'),
]

assert len(STREAM_FIELDS) == 350, f'Expected 350 fields, got {len(STREAM_FIELDS)}'


def field_label(pos: int) -> str:
    """Return a short label string for stream position *pos*."""
    if 0 <= pos < len(STREAM_FIELDS):
        f = STREAM_FIELDS[pos]
        return f'{f.name}  [tag=0x{f.tag:02X}]'
    return f'pos_{pos}'
