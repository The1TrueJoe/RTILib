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
from ...core import tlv

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

    # -- Device type and core config --
    e.append(tlv.encode_byte(1,  _DEVICE_TYPE_U1))  # device type U1 = 0x11
    e.append(tlv.encode_byte(3,  10))
    e.append(tlv.encode_i32(52,  3600))
    e.append(tlv.encode_byte(4,  0))
    e.append(tlv.encode_u16(1,   2))
    e.append(tlv.encode_byte(7,  0))   # 0 for remote
    e.append(tlv.encode_byte(8,  0))
    e.append(tlv.encode_byte(38, 2))
    e.append(tlv.encode_byte(39, 0))
    e.append(tlv.encode_byte(11, 0))   # U1 = 0, U2 = 1
    e.append(tlv.encode_byte(12, 0))
    e.append(tlv.encode_byte(45, 1))
    e.append(tlv.encode_byte(44, 1))
    e.append(tlv.encode_byte(14, 1))
    e.append(tlv.encode_byte(15, 0))
    e.append(tlv.encode_byte(17, 0))
    e.append(tlv.encode_i32(1,   25000))
    e.append(tlv.encode_byte(19, 0))
    e.append(tlv.encode_i32(36,  255))
    e.append(tlv.encode_i32(4,   100))
    e.append(tlv.encode_i32(5,   10))
    e.append(tlv.encode_i32(6,   -1))
    e.append(tlv.encode_i32(7,   100))
    e.append(tlv.encode_i32(8,   60))
    e.append(tlv.encode_i32(9,   30))
    e.append(tlv.encode_i32(19,  10))
    e.append(tlv.encode_i32(20,  10))
    e.append(tlv.encode_i32(21,  10))
    e.append(tlv.encode_byte(22, 0))
    e.append(tlv.encode_byte(43, 1))
    e.append(tlv.encode_i32(10,  80))
    e.append(tlv.encode_i32(11,  1))
    e.append(tlv.encode_i32(13,  -1))
    e.append(tlv.encode_byte(23, 0))
    e.append(tlv.encode_byte(25, 1))
    e.append(tlv.encode_byte(26, 1))
    e.append(tlv.encode_byte(27, 1))

    # -- Network / location --
    e.append(tlv.encode_varstr_raw(10, ntp_server.encode('utf-16-le')))
    e.append(tlv.encode_byte(28, 1))
    e.append(tlv.encode_i32(22,  8))
    e.append(tlv.encode_u16(5,   0))
    e.append(tlv.encode_guid(2,  _PROTOCOL_GUID))
    e.append(tlv.encode_blob(8,  b'\x00' * 8))
    e.append(tlv.encode_blob(9,  b'\x00' * 8))
    e.append(tlv.encode_varstr_raw(13, location.encode('utf-16-le')))
    e.append(tlv.encode_byte(36, 0))
    e.append(tlv.encode_byte(37, 0))   # 0 for U2/U1 (1 = XP)
    e.append(tlv.encode_byte(40, 0))
    e.append(tlv.encode_byte(41, 3))
    e.append(tlv.encode_blob(13, _DEVICE_GUID_U1))
    e.append(tlv.encode_byte(42, 0))
    e.append(tlv.encode_i32(48,  0))   # 0 for U1 (96 = U2)
    e.append(tlv.encode_blob(15, b'\x00' * 8))
    e.append(tlv.encode_blob(16, b'\x00' * 8))

    # -- Identity --
    e.append(tlv.encode_varstr_raw(31, device_mac.encode('utf-16-le')))
    e.append(tlv.encode_blob(3, b'0000'))

    # -- Input slot indices (9 slots: 256-264) --
    for idx in range(256, 265):
        e.append(tlv.encode_u16(4, idx))

    # -- Page group IDs (4 groups) --
    for grp in range(4):
        e.append(tlv.encode_i32(29, grp << 24))

    # -- Input group slot names (16): first 4 named, rest empty --
    for idx in range(16):
        if idx < len(_U1_SLOT_NAMES):
            payload = struct.pack('<H', idx) + _U1_SLOT_NAMES[idx].encode('utf-16-le')
        else:
            payload = struct.pack('<H', idx)
        e.append(tlv.encode_varstr_raw(8, payload))

    # -- Input group state blobs (8) --
    for idx in range(8):
        e.append(tlv.encode_blob(12, struct.pack('<I', idx) + b'\xff\xff\xff\xff'))

    # -- Variable slots: 256 "Unnamed" entries --
    unnamed = 'Unnamed'.encode('utf-16-le')
    for idx in range(256):
        e.append(tlv.encode_varstr_raw(9, struct.pack('<H', idx) + unnamed))

    # -- End sentinel (U1 uses a different sentinel than XP) --
    e.append(tlv.encode_blob(6, bytes.fromhex('2e00ff0f00000000')))

    return b''.join(e)
