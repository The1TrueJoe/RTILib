"""
rti_lib/devices/u1/stream_profile.py

U1 base device-stream builder.  Generates the opening TLV records for an
RTI U1 button-only handheld remote.

Structure (350 TLV records):
  Device config (44)   NTP / location   Identity
  9 input-slot indices   4 page-group IDs
  16 group slots (first 4 named)   8 state blobs   256 variable slots
  End sentinel (8-byte blob)
"""

import struct
from rti_lib.core import tlv
from rti_lib.core.fields import (
    CFG_DEVICE_TYPE, CFG_POLLING_RATE, CFG_NTP_SYNC_INTERVAL,
    CFG_UNKNOWN_04, CFG_PROTOCOL_VERSION, CFG_IS_PROCESSOR,
    CFG_UNKNOWN_08, CFG_DEVICE_CATEGORY, CFG_UNKNOWN_27,
    CFG_HAS_PHYS_BUTTONS, CFG_UNKNOWN_0C, CFG_UI_VERSION,
    CFG_UNKNOWN_2C, CFG_UNKNOWN_0E, CFG_UNKNOWN_0F_B, CFG_UNKNOWN_11,
    CFG_IDLE_TIMEOUT, CFG_UNKNOWN_13_B, CFG_BACKLIGHT_MAX,
    CFG_BACKLIGHT_ON, CFG_BACKLIGHT_DIM, CFG_BACKLIGHT_OFF,
    CFG_MOTION_ON, CFG_MOTION_DIM, CFG_MOTION_OFF,
    CFG_KEYCLICK_VOL, CFG_KEYCLICK_ON, CFG_VIBRATION_MS,
    CFG_HAS_TOUCHSCREEN, CFG_UNKNOWN_2B, CFG_RF_CHANNEL,
    CFG_RF_CHANNEL_COUNT, CFG_RF_RETRY_COUNT, CFG_UNKNOWN_17,
    CFG_UNKNOWN_19, CFG_UNKNOWN_1A, CFG_UNKNOWN_1B,
    NET_NTP_SERVER, NET_UNKNOWN_1C, NET_RF_FREQ_CODE, NET_UNKNOWN_05,
    NET_PROTOCOL_GUID, NET_LATITUDE, NET_LONGITUDE, NET_LOCATION,
    NET_UNKNOWN_24, NET_HAS_COLOR, NET_UNKNOWN_28, NET_UNKNOWN_29,
    NET_DEVICE_GUID, NET_UNKNOWN_2A, NET_DISPLAY_DPI,
    NET_UNKNOWN_0F_BLK, NET_UNKNOWN_10_BLK,
    ID_MAC_ADDRESS, ID_SERIAL,
    SLT_INPUT_SLOT_IDX, SLT_PAGE_GROUP_ID, SLT_GROUP_NAME,
    SLT_GROUP_STATE, SLT_VARIABLE_NAME, SLT_PAGE_CAP_U2,
)

_DEVICE_TYPE_U1 = 17    # 0x11
_DEVICE_GUID_U1 = bytes.fromhex('79fa74f97bac5f47b55e41140badec4f')
_PROTOCOL_GUID  = bytes.fromhex('00000000080000007801030000000001')

# First 4 input group slots carry factory names on the U1
_U1_SLOT_NAMES = ['CD', 'Tuner', 'Satellite', 'Aux']


def build_u1_base_stream(
    display_name: str = 'U1',
    ntp_server:   str = 'time.windows.com',
    location:     str = '',
    device_mac:   str = '001526000000',
) -> bytes:
    """Build the U1 base device-stream prefix (350 TLV records)."""
    e = []

    # -- Device config (positions 0-36) --
    e.append(tlv.encode_byte(CFG_DEVICE_TYPE,       _DEVICE_TYPE_U1))  # pos  0
    e.append(tlv.encode_byte(CFG_POLLING_RATE,       10))               # pos  1
    e.append(tlv.encode_i32 (CFG_NTP_SYNC_INTERVAL,  3600))             # pos  2
    e.append(tlv.encode_byte(CFG_UNKNOWN_04,          0))               # pos  3
    e.append(tlv.encode_u16 (CFG_PROTOCOL_VERSION,    2))               # pos  4
    e.append(tlv.encode_byte(CFG_IS_PROCESSOR,        0))               # pos  5  0=remote
    e.append(tlv.encode_byte(CFG_UNKNOWN_08,          0))               # pos  6
    e.append(tlv.encode_byte(CFG_DEVICE_CATEGORY,     2))               # pos  7  2=handheld
    e.append(tlv.encode_byte(CFG_UNKNOWN_27,          0))               # pos  8  0=remote
    e.append(tlv.encode_byte(CFG_HAS_PHYS_BUTTONS,    0))               # pos  9  U1=0 (no display buttons)
    e.append(tlv.encode_byte(CFG_UNKNOWN_0C,          0))               # pos 10
    e.append(tlv.encode_byte(CFG_UI_VERSION,          1))               # pos 11  1=mono B&W
    e.append(tlv.encode_byte(CFG_UNKNOWN_2C,          1))               # pos 12
    e.append(tlv.encode_byte(CFG_UNKNOWN_0E,          1))               # pos 13
    e.append(tlv.encode_byte(CFG_UNKNOWN_0F_B,        0))               # pos 14
    e.append(tlv.encode_byte(CFG_UNKNOWN_11,          0))               # pos 15
    e.append(tlv.encode_i32 (CFG_IDLE_TIMEOUT,        25000))           # pos 16
    e.append(tlv.encode_byte(CFG_UNKNOWN_13_B,        0))               # pos 17
    e.append(tlv.encode_i32 (CFG_BACKLIGHT_MAX,       255))             # pos 18
    e.append(tlv.encode_i32 (CFG_BACKLIGHT_ON,        100))             # pos 19
    e.append(tlv.encode_i32 (CFG_BACKLIGHT_DIM,       10))              # pos 20
    e.append(tlv.encode_i32 (CFG_BACKLIGHT_OFF,       -1))              # pos 21
    e.append(tlv.encode_i32 (CFG_MOTION_ON,           100))             # pos 22
    e.append(tlv.encode_i32 (CFG_MOTION_DIM,          60))              # pos 23
    e.append(tlv.encode_i32 (CFG_MOTION_OFF,          30))              # pos 24
    e.append(tlv.encode_i32 (CFG_KEYCLICK_VOL,        10))              # pos 25
    e.append(tlv.encode_i32 (CFG_KEYCLICK_ON,         10))              # pos 26
    e.append(tlv.encode_i32 (CFG_VIBRATION_MS,        10))              # pos 27
    e.append(tlv.encode_byte(CFG_HAS_TOUCHSCREEN,     0))               # pos 28  U1=0
    e.append(tlv.encode_byte(CFG_UNKNOWN_2B,          1))               # pos 29
    e.append(tlv.encode_i32 (CFG_RF_CHANNEL,          80))              # pos 30
    e.append(tlv.encode_i32 (CFG_RF_CHANNEL_COUNT,    1))               # pos 31
    e.append(tlv.encode_i32 (CFG_RF_RETRY_COUNT,      -1))              # pos 32
    e.append(tlv.encode_byte(CFG_UNKNOWN_17,          0))               # pos 33
    e.append(tlv.encode_byte(CFG_UNKNOWN_19,          1))               # pos 34
    e.append(tlv.encode_byte(CFG_UNKNOWN_1A,          1))               # pos 35
    e.append(tlv.encode_byte(CFG_UNKNOWN_1B,          1))               # pos 36

    # -- Network / location (positions 37-53) --
    e.append(tlv.encode_varstr_raw(NET_NTP_SERVER,    ntp_server.encode('utf-16-le')))  # pos 37
    e.append(tlv.encode_byte(NET_UNKNOWN_1C,          1))               # pos 38
    e.append(tlv.encode_i32 (NET_RF_FREQ_CODE,        8))               # pos 39
    e.append(tlv.encode_u16 (NET_UNKNOWN_05,          0))               # pos 40
    e.append(tlv.encode_guid(NET_PROTOCOL_GUID,       _PROTOCOL_GUID))  # pos 41
    e.append(tlv.encode_blob(NET_LATITUDE,            b'\x00' * 8))     # pos 42
    e.append(tlv.encode_blob(NET_LONGITUDE,           b'\x00' * 8))     # pos 43
    e.append(tlv.encode_varstr_raw(NET_LOCATION,      location.encode('utf-16-le')))  # pos 44
    e.append(tlv.encode_byte(NET_UNKNOWN_24,          0))               # pos 45
    e.append(tlv.encode_byte(NET_HAS_COLOR,           0))               # pos 46  U1=0
    e.append(tlv.encode_byte(NET_UNKNOWN_28,          0))               # pos 47
    e.append(tlv.encode_byte(NET_UNKNOWN_29,          3))               # pos 48
    e.append(tlv.encode_blob(NET_DEVICE_GUID,         _DEVICE_GUID_U1)) # pos 49
    e.append(tlv.encode_byte(NET_UNKNOWN_2A,          0))               # pos 50
    e.append(tlv.encode_i32 (NET_DISPLAY_DPI,         0))               # pos 51  U1=0 (no display — button-only)
    e.append(tlv.encode_blob(NET_UNKNOWN_0F_BLK,      b'\x00' * 8))     # pos 52
    e.append(tlv.encode_blob(NET_UNKNOWN_10_BLK,      b'\x00' * 8))     # pos 53

    # -- Device identity (positions 54-55) --
    e.append(tlv.encode_varstr_raw(ID_MAC_ADDRESS,    device_mac.encode('utf-16-le')))  # pos 54
    e.append(tlv.encode_blob(ID_SERIAL,               b'0000'))         # pos 55

    # -- Input slot indices (positions 56-64, 9 slots: 256-264) --
    for idx in range(256, 265):
        e.append(tlv.encode_u16(SLT_INPUT_SLOT_IDX, idx))

    # -- Page group IDs (positions 65-68, 4 groups) --
    for grp in range(4):
        e.append(tlv.encode_i32(SLT_PAGE_GROUP_ID, grp << 24))

    # -- Input group slot names (positions 69-84): first 4 named, rest empty --
    for idx in range(16):
        if idx < len(_U1_SLOT_NAMES):
            payload = struct.pack('<H', idx) + _U1_SLOT_NAMES[idx].encode('utf-16-le')
        else:
            payload = struct.pack('<H', idx)
        e.append(tlv.encode_varstr_raw(SLT_GROUP_NAME, payload))

    # -- Input group state blobs (positions 85-92, 8 blobs) --
    for idx in range(8):
        e.append(tlv.encode_blob(SLT_GROUP_STATE, struct.pack('<I', idx) + b'\xff\xff\xff\xff'))

    # -- Variable slots (positions 93-348, 256 × 'Unnamed') --
    unnamed = 'Unnamed'.encode('utf-16-le')
    for idx in range(256):
        e.append(tlv.encode_varstr_raw(SLT_VARIABLE_NAME, struct.pack('<H', idx) + unnamed))

    # -- End sentinel (position 349) --
    e.append(tlv.encode_blob(SLT_PAGE_CAP_U2, bytes.fromhex('2e00ff0f00000000')))

    return b''.join(e)
