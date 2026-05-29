"""
rti_lib/devices/xp/stream_profile.py

XP-6 base device-stream builder.  Generates the opening TLV records for an
RTI XP-3/XP-6/XP-8 processor stream entirely in code.

Structure (397 TLV records, ~6633 bytes):
  Device config (50)   NTP / location   Identity
  9 input-slot indices   4 page-group IDs   32 port names
  3 schedule placeholders   16 group slots   8 state blobs
  256 variable slots   End sentinel
"""

import struct
from rti_lib.core import tlv

_DEVICE_TYPE_XP = 49   # 0x31
_DEVICE_GUID_XP = bytes.fromhex('7ede5b2bcffa6646b73e7ccdd79850e4')
_PROTOCOL_GUID  = bytes.fromhex('00000000080000007801030000000001')

# 8 serial ports x 4 label subtypes = 32 entries.
# Payload: [port_byte][subtype_byte] 0xFF 0xFF [name as UTF-16LE]
_XP6_PORT_NAMES = [
    # subtype 0 — primary port alias
    (0, 0, 'Port 1'), (1, 0, 'Port 2'), (2, 0, 'Port 3'), (3, 0, 'Port 4'),
    (4, 0, 'Port 5'), (5, 0, 'Port 6'), (6, 0, 'Port 7'), (7, 0, 'Port 8'),
    # subtype 1 — secondary port alias
    (0, 1, 'Port 1'), (1, 1, 'Port 2'), (2, 1, 'Port 3'), (3, 1, 'Port 4'),
    (4, 1, 'Port 5'), (5, 1, 'Port 6'), (6, 1, 'Port 7'), (7, 1, 'Port 8'),
    # subtype 2 — Power Sense for ports 0-2, Port N for 3-7
    (0, 2, 'Power Sense 1'), (1, 2, 'Power Sense 2'), (2, 2, 'Power Sense 3'),
    (3, 2, 'Port 4'), (4, 2, 'Port 5'), (5, 2, 'Port 6'),
    (6, 2, 'Port 7'), (7, 2, 'Port 8'),
    # subtype 3 — Relay / Trigger Out labels
    (0, 3, 'Relay 1'), (1, 3, 'Relay 2'), (2, 3, 'Relay 3'),
    (3, 3, 'Trigger Out 1'), (4, 3, 'Trigger Out 2'), (5, 3, 'Trigger Out 3'),
    (6, 3, 'Relay 7'), (7, 3, 'Relay 8'),
]


def build_xp6_base_stream(
    display_name: str = 'XP-6',
    ntp_server:   str = 'time.windows.com',
    location:     str = '',
    device_mac:   str = '001526000000',
) -> bytes:
    """Build the XP-6 base device-stream prefix (397 TLV records)."""
    e = []

    # -- Device type and core config --
    e.append(tlv.encode_byte(1,  _DEVICE_TYPE_XP))  # device type XP = 0x31
    e.append(tlv.encode_byte(3,  10))               # protocol version
    e.append(tlv.encode_i32(52,  3600))             # auto-disconnect timeout (s)
    e.append(tlv.encode_byte(4,  0))
    e.append(tlv.encode_u16(1,   2))
    e.append(tlv.encode_byte(7,  1))   # processor flag: 1=XP, 0=remote
    e.append(tlv.encode_byte(8,  0))
    e.append(tlv.encode_byte(38, 0))
    e.append(tlv.encode_byte(39, 1))
    e.append(tlv.encode_byte(11, 0))
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
    # XP-specific block (not present on U1/U2 remotes):
    e.append(tlv.encode_byte(24, 1))
    for tag in (14, 15, 16, 17, 18):
        e.append(tlv.encode_i32(tag, 0))
    e.append(tlv.encode_byte(33, 1))
    for tag in (24, 25, 26, 27, 28):
        e.append(tlv.encode_i32(tag, 0))
    e.append(tlv.encode_byte(26, 1))
    e.append(tlv.encode_byte(27, 1))

    # -- Network / location --
    e.append(tlv.encode_varstr_raw(10, ntp_server.encode('utf-16-le')))
    e.append(tlv.encode_byte(28, 1))
    e.append(tlv.encode_i32(22,  8))
    e.append(tlv.encode_u16(5,   0))
    e.append(tlv.encode_guid(2,  _PROTOCOL_GUID))
    e.append(tlv.encode_blob(8,  b'\x00' * 8))   # latitude  (cleared)
    e.append(tlv.encode_blob(9,  b'\x00' * 8))   # longitude (cleared)
    e.append(tlv.encode_varstr_raw(13, location.encode('utf-16-le')))
    e.append(tlv.encode_byte(36, 0))
    e.append(tlv.encode_byte(37, 1))   # XP-specific
    e.append(tlv.encode_byte(40, 0))
    e.append(tlv.encode_byte(41, 3))
    e.append(tlv.encode_blob(13, _DEVICE_GUID_XP))
    e.append(tlv.encode_byte(42, 0))
    e.append(tlv.encode_i32(48,  0))
    e.append(tlv.encode_blob(15, b'\x00' * 8))
    e.append(tlv.encode_blob(16, b'\x00' * 8))

    # -- Identity --
    e.append(tlv.encode_varstr_raw(31, device_mac.encode('utf-16-le')))
    e.append(tlv.encode_blob(3, b'0000'))   # model code

    # -- Input slot indices (9 slots: 256-264) --
    for idx in range(256, 265):
        e.append(tlv.encode_u16(4, idx))

    # -- Page group IDs (4 groups) --
    for grp in range(4):
        e.append(tlv.encode_i32(29, grp << 24))

    # -- Serial port names (32 entries: 8 ports x 4 subtypes) --
    for port, subtype, name in _XP6_PORT_NAMES:
        payload = struct.pack('<BB', port, subtype) + b'\xff\xff' + name.encode('utf-16-le')
        e.append(tlv.encode_varstr_raw(15, payload))

    # -- Schedule placeholders (3) --
    sched = bytes.fromhex('ffffffff00000000')
    e.append(tlv.encode_varstr_raw(28, sched))
    e.append(tlv.encode_varstr_raw(29, sched))
    e.append(tlv.encode_varstr_raw(30, sched))

    # -- Input group slot names (16) --
    for idx in range(16):
        e.append(tlv.encode_varstr_raw(8, struct.pack('<H', idx)))

    # -- Input group state blobs (8) --
    for idx in range(8):
        e.append(tlv.encode_blob(12, struct.pack('<I', idx) + b'\xff\xff\xff\xff'))

    # -- Variable slots: 256 "Unnamed" entries --
    unnamed = 'Unnamed'.encode('utf-16-le')
    for idx in range(256):
        e.append(tlv.encode_varstr_raw(9, struct.pack('<H', idx) + unnamed))

    # -- End sentinel --
    e.append(tlv.encode_blob(10, bytes.fromhex('340000000000000000')))

    return b''.join(e)
