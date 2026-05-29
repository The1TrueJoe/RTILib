"""
rti_lib/devices/t2i/stream_profile.py

T2i base device-stream builder.  Generates the opening TLV records for an
RTI T2i colour touchscreen handheld remote (240×320 px, 24bpp RGB display).

The T2i stream is structurally identical to the U2 stream with exactly seven
field-value differences in the first 350 nodes, followed by two CONTAINER
nodes that describe the page/button layout instead of the U2 home-page block.

Confirmed differences vs U2 (from Test4.rti probe):
  node[ 0] BYTE tag=01  U2=29(0x1D)  T2i=75(0x4B)  — device type
  node[ 9] BYTE tag=0b  U2=1         T2i=0          — physical-button flag
  node[11] BYTE tag=2d  U2=1         T2i=2          — page count?
  node[28] BYTE tag=16  U2=0         T2i=1          — touchscreen flag
  node[46] BYTE tag=25  U2=0         T2i=1          — colour-display flag
  node[49] BLOB tag=0d  U2 GUID      T2i GUID       — device identity
  node[349] BLOB tag differs: U2=tag-06/8B, T2i=tag-0A/9B  — page-cap sentinel

Display specs:  240 × 320 pixels, 24-bit RGB (3 bytes/pixel).
Image encoding: zlib-compressed raw RGB scanlines, stored inside a nested CONT
                node preceded by a BITMAPINFOHEADER in a VARSTR field.
"""

import struct, zlib, binascii
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
    SLT_GROUP_STATE, SLT_VARIABLE_NAME, SLT_PAGE_CAP_T2I,
)

_DEVICE_TYPE_T2I = 0x4B   # 75

# Placeholder GUID — matches the T2i in Test4.rti.  Each physical device has
# a unique identifier; this default is used when no GUID is supplied.
_DEVICE_GUID_T2I_DEFAULT = bytes.fromhex('5813e5b97aa79844b5917a06199388f0')

# Shared protocol GUID (same across all RTI device types).
_PROTOCOL_GUID = bytes.fromhex('00000000080000007801030000000001')

# T2i display dimensions.
T2I_WIDTH  = 240
T2I_HEIGHT = 320


# ---------------------------------------------------------------------------
# Image encoding
# ---------------------------------------------------------------------------

def encode_t2i_image(rgb_bytes: bytes, width: int = T2I_WIDTH,
                     height: int = T2I_HEIGHT) -> bytes:
    """
    Encode a raw 24-bit RGB image (width × height × 3 bytes) into a T2i
    image CONTAINER node (type=GUID sentinel + zlib stream).

    Parameters
    ----------
    rgb_bytes : Raw pixel data, top-to-bottom, RGB order.  Must be exactly
                width * height * 3 bytes.
    width, height : Image dimensions in pixels.

    Returns
    -------
    bytes — The encoded CONTAINER (tag=0x02) ready to embed in a page CONT.
    """
    expected = width * height * 3
    if len(rgb_bytes) != expected:
        raise ValueError(
            f'rgb_bytes must be {expected} bytes ({width}x{height}x3); '
            f'got {len(rgb_bytes)}'
        )

    total_pixels = width * height

    # BITMAPINFOHEADER (40 bytes, BI_RGB uncompressed; height is positive =
    # bottom-up, but RTI stores top-down so we set it as positive regardless).
    bih = struct.pack('<IIiHHIIiiII',
        40,           # biSize
        width,        # biWidth
        height,       # biHeight (positive = bottom-up convention)
        1,            # biPlanes
        24,           # biBitCount
        0,            # biCompression (BI_RGB)
        0,            # biSizeImage (can be 0 for BI_RGB)
        0, 0,         # biXPelsPerMeter, biYPelsPerMeter
        0, 0,         # biClrUsed, biClrImportant
    )

    # Convert top-to-bottom RGB to bottom-to-top BGR (Windows BMP convention).
    # biHeight is positive (bottom-up), so row 0 of the image is stored last.
    w3 = width * 3
    bgr_rows = []
    for row_i in range(height - 1, -1, -1):  # reversed: bottom row first
        src = rgb_bytes[row_i * w3:(row_i + 1) * w3]
        row_bgr = bytearray(w3)
        for px in range(width):
            row_bgr[px * 3]     = src[px * 3 + 2]  # B
            row_bgr[px * 3 + 1] = src[px * 3 + 1]  # G
            row_bgr[px * 3 + 2] = src[px * 3]      # R
        bgr_rows.append(bytes(row_bgr))
    pixel_data = b''.join(bgr_rows)

    # Compress the pixel data.
    compressed = zlib.compress(pixel_data, level=1)
    comp_size  = len(compressed)          # zlib stream size (incl. header+checksum)
    uncomp_size = total_pixels * 3        # raw byte count

    # Build the 8-byte image hash.
    # hash[0:4] = CRC32(BGR bottom-up pixels) stored little-endian.
    # hash[4:8] = unknown second half; set to zero (RTI may not validate it).
    crc_px = binascii.crc32(pixel_data) & 0xFFFFFFFF
    image_hash = struct.pack('<I', crc_px) + b'\x00' * 4

    # Assemble image CONT inner content:
    #   I32(tag=1)  = total uncompressed bytes
    #   I32(tag=2)  = -1 (observed constant)
    #   BLOB(tag=1) = 8-byte image hash
    #   VARSTR(tag=1) = BITMAPINFOHEADER (44 bytes; actual BIH is 40 bytes but
    #                   RTI pads with 4 zeros matching imageSize field placement)
    #   [marker bytes tag=01 type=E0]: 4B uncompressed_size, 4B compressed_size,
    #                                  then 8B of zlib stream start  (16B "GUID")
    #   [remainder of zlib stream appended after the GUID]
    #
    # The "GUID" node is a deliberate misuse: the RTI format stores:
    #   01 E0 [4B unc_sz] [4B comp_sz] [8B zlib_head] [rest of zlib]
    # where the zlib stream begins at the 8th byte of the 16-byte GUID value
    # and continues beyond the node boundary until the end of the CONT raw.

    varstr_raw = bih + b'\x00' * 4   # BITMAPINFOHEADER padded to 44 bytes
    inner  = tlv.encode_i32(0x01, uncomp_size)
    inner += tlv.encode_i32(0x02, -1)
    inner += tlv.encode_blob(0x01, image_hash)
    inner += tlv.encode_varstr_raw(0x01, varstr_raw)

    # Write the fake GUID sentinel: tag=01, type=E0, then 16 bytes where
    # the first 8 encode sizes and the last 8 start the zlib stream.
    guid_data = (struct.pack('<I', uncomp_size) +
                 struct.pack('<I', comp_size) +      # full zlib stream length
                 compressed[:8])
    inner += bytes([0x01, 0xE0]) + guid_data

    # Append the rest of the zlib stream (bytes 8 onward).
    inner += compressed[8:]

    # Terminate the image CONT inner content (required by RTI's TLV decoder).
    inner += b'\xFF\xFF'

    return tlv.encode_container(0x02, inner)


# ---------------------------------------------------------------------------
# Page / button CONTs
# ---------------------------------------------------------------------------

def build_t2i_home_page(name: str = 'Home Page',
                        image_rgb: bytes = None,
                        buttons: bytes = b'') -> bytes:
    """
    Build the T2i home page CONTAINER (tag=0x01).

    Observed node ordering in RTI Integration Designer files:
      BYTE(01)=2, BYTE(02)=0, VARSTR(01)=name, I32(01)=0xFFFFFF
      [image CONT tag=02 — inserted here when present]
      BYTE(03)=2, BYTE(04)=0
      [button CONT tag=01 records]
      FF FF terminator

    Parameters
    ----------
    name      : Page display name.
    image_rgb : Optional raw RGB bytes (240x320x3) for the background image.
    buttons   : Pre-encoded button CONT bytes (concatenated TAG=01 CONTs).

    Returns
    -------
    bytes — The outer tag=01 CONTAINER.
    """
    content = (
        tlv.encode_byte(0x01, 2) +
        tlv.encode_byte(0x02, 0) +
        tlv.encode_varstr(0x01, name) +
        tlv.encode_i32(0x01, 0x00FFFFFF)
    )
    if image_rgb is not None:
        content += encode_t2i_image(image_rgb)
    content += (
        tlv.encode_byte(0x03, 2 if image_rgb is not None else 1) +
        tlv.encode_byte(0x04, 0) +
        buttons +
        tlv.TERMINATOR
    )
    return tlv.encode_container(0x01, content)


def build_t2i_secondary_page(buttons: bytes = b'') -> bytes:
    """
    Build the T2i secondary page CONTAINER (tag=0x02).

    Parameters
    ----------
    buttons : Pre-encoded button CONT bytes (concatenated TAG=01 CONTs).
    """
    content = (
        tlv.encode_byte(0x01, 2) +
        tlv.encode_byte(0x02, 0) +
        tlv.encode_varstr(0x01, '') +
        tlv.encode_i32(0x01, 0x00FFFFFF) +
        tlv.encode_byte(0x03, 1) +
        tlv.encode_byte(0x04, 0) +
        buttons +
        tlv.TERMINATOR
    )
    return tlv.encode_container(0x02, content)


# ---------------------------------------------------------------------------
# Base stream builder
# ---------------------------------------------------------------------------

def build_t2i_base_stream(
    display_name:  str   = 'T2i',
    ntp_server:    str   = 'time.windows.com',
    location:      str   = '',
    device_mac:    str   = '001526000000',
    device_guid:   bytes = None,
    image_rgb:     bytes = None,
    home_buttons:  bytes = b'',
    sec_buttons:   bytes = b'',
) -> bytes:
    """
    Build the complete T2i device-stream bytes.

    The stream is structurally equivalent to the U2 base stream (same 350
    shared TLV records) with seven field differences and T2i-specific page
    containers at the end.

    Parameters
    ----------
    display_name  : Label shown in the RTI project browser.
    ntp_server    : NTP hostname (default 'time.windows.com').
    location      : Geographic location string (may be empty).
    device_mac    : 12-hex-digit MAC address string (no separators).
    device_guid   : 16-byte device identity GUID.  Defaults to the T2i GUID
                    captured from Test4.rti; supply a unique value per device.
    image_rgb     : Optional 240x320x3 raw RGB bytes for the home page
                    background image.
    home_buttons  : Pre-encoded button CONT bytes for the home page.
    sec_buttons   : Pre-encoded button CONT bytes for the secondary page.
    """
    if device_guid is None:
        device_guid = _DEVICE_GUID_T2I_DEFAULT

    e = []

    # -- Device config (positions 0-36) --
    e.append(tlv.encode_byte(CFG_DEVICE_TYPE,       _DEVICE_TYPE_T2I))  # pos  0  T2i=0x4B
    e.append(tlv.encode_byte(CFG_POLLING_RATE,       10))                # pos  1
    e.append(tlv.encode_i32 (CFG_NTP_SYNC_INTERVAL,  3600))              # pos  2
    e.append(tlv.encode_byte(CFG_UNKNOWN_04,          0))                # pos  3
    e.append(tlv.encode_u16 (CFG_PROTOCOL_VERSION,    2))                # pos  4
    e.append(tlv.encode_byte(CFG_IS_PROCESSOR,        0))                # pos  5  0=remote
    e.append(tlv.encode_byte(CFG_UNKNOWN_08,          0))                # pos  6
    e.append(tlv.encode_byte(CFG_DEVICE_CATEGORY,     2))                # pos  7  2=handheld
    e.append(tlv.encode_byte(CFG_UNKNOWN_27,          0))                # pos  8
    e.append(tlv.encode_byte(CFG_HAS_PHYS_BUTTONS,    0))                # pos  9  T2i=0 (touchscreen only)
    e.append(tlv.encode_byte(CFG_UNKNOWN_0C,          0))                # pos 10
    e.append(tlv.encode_byte(CFG_UI_VERSION,          2))                # pos 11  T2i=2 (colour)
    e.append(tlv.encode_byte(CFG_UNKNOWN_2C,          1))                # pos 12
    e.append(tlv.encode_byte(CFG_UNKNOWN_0E,          1))                # pos 13
    e.append(tlv.encode_byte(CFG_UNKNOWN_0F_B,        0))                # pos 14
    e.append(tlv.encode_byte(CFG_UNKNOWN_11,          0))                # pos 15
    e.append(tlv.encode_i32 (CFG_IDLE_TIMEOUT,        25000))            # pos 16
    e.append(tlv.encode_byte(CFG_UNKNOWN_13_B,        0))                # pos 17
    e.append(tlv.encode_i32 (CFG_BACKLIGHT_MAX,       255))              # pos 18
    e.append(tlv.encode_i32 (CFG_BACKLIGHT_ON,        100))              # pos 19
    e.append(tlv.encode_i32 (CFG_BACKLIGHT_DIM,       10))               # pos 20
    e.append(tlv.encode_i32 (CFG_BACKLIGHT_OFF,       -1))               # pos 21
    e.append(tlv.encode_i32 (CFG_MOTION_ON,           100))              # pos 22
    e.append(tlv.encode_i32 (CFG_MOTION_DIM,          60))               # pos 23
    e.append(tlv.encode_i32 (CFG_MOTION_OFF,          30))               # pos 24
    e.append(tlv.encode_i32 (CFG_KEYCLICK_VOL,        10))               # pos 25
    e.append(tlv.encode_i32 (CFG_KEYCLICK_ON,         10))               # pos 26
    e.append(tlv.encode_i32 (CFG_VIBRATION_MS,        10))               # pos 27
    e.append(tlv.encode_byte(CFG_HAS_TOUCHSCREEN,     1))                # pos 28  T2i=1 (touchscreen)
    e.append(tlv.encode_byte(CFG_UNKNOWN_2B,          1))                # pos 29
    e.append(tlv.encode_i32 (CFG_RF_CHANNEL,          80))               # pos 30
    e.append(tlv.encode_i32 (CFG_RF_CHANNEL_COUNT,    1))                # pos 31
    e.append(tlv.encode_i32 (CFG_RF_RETRY_COUNT,      -1))               # pos 32
    e.append(tlv.encode_byte(CFG_UNKNOWN_17,          0))                # pos 33
    e.append(tlv.encode_byte(CFG_UNKNOWN_19,          1))                # pos 34
    e.append(tlv.encode_byte(CFG_UNKNOWN_1A,          1))                # pos 35
    e.append(tlv.encode_byte(CFG_UNKNOWN_1B,          1))                # pos 36

    # -- Network / location (positions 37-53) --
    e.append(tlv.encode_varstr_raw(NET_NTP_SERVER,    ntp_server.encode('utf-16-le')))   # pos 37
    e.append(tlv.encode_byte(NET_UNKNOWN_1C,          1))                # pos 38
    e.append(tlv.encode_i32 (NET_RF_FREQ_CODE,        8))                # pos 39
    e.append(tlv.encode_u16 (NET_UNKNOWN_05,          0))                # pos 40
    e.append(tlv.encode_guid(NET_PROTOCOL_GUID,       _PROTOCOL_GUID))   # pos 41
    e.append(tlv.encode_blob(NET_LATITUDE,            b'\x00' * 8))      # pos 42
    e.append(tlv.encode_blob(NET_LONGITUDE,           b'\x00' * 8))      # pos 43
    e.append(tlv.encode_varstr_raw(NET_LOCATION,      location.encode('utf-16-le')))     # pos 44
    e.append(tlv.encode_byte(NET_UNKNOWN_24,          0))                # pos 45
    e.append(tlv.encode_byte(NET_HAS_COLOR,           1))                # pos 46  T2i=1 (colour)
    e.append(tlv.encode_byte(NET_UNKNOWN_28,          0))                # pos 47
    e.append(tlv.encode_byte(NET_UNKNOWN_29,          3))                # pos 48
    e.append(tlv.encode_blob(NET_DEVICE_GUID,         device_guid))      # pos 49
    e.append(tlv.encode_byte(NET_UNKNOWN_2A,          0))                # pos 50
    e.append(tlv.encode_i32 (NET_DISPLAY_DPI,         96))               # pos 51  T2i=96 (same as U2)
    e.append(tlv.encode_blob(NET_UNKNOWN_0F_BLK,      b'\x00' * 8))      # pos 52
    e.append(tlv.encode_blob(NET_UNKNOWN_10_BLK,      b'\x00' * 8))      # pos 53

    # -- Device identity (positions 54-55) --
    e.append(tlv.encode_varstr_raw(ID_MAC_ADDRESS,    device_mac.encode('utf-16-le')))   # pos 54
    e.append(tlv.encode_blob(ID_SERIAL,               b'0000'))          # pos 55

    # -- Input slot indices (positions 56-64, 9 slots: 256-264) --
    for idx in range(256, 265):
        e.append(tlv.encode_u16(SLT_INPUT_SLOT_IDX, idx))

    # -- Page group IDs (positions 65-68, 4 groups) --
    for grp in range(4):
        e.append(tlv.encode_i32(SLT_PAGE_GROUP_ID, grp << 24))

    # -- Input group slot names (positions 69-84, 16 slots; all empty for T2i) --
    for idx in range(16):
        e.append(tlv.encode_varstr_raw(SLT_GROUP_NAME, struct.pack('<H', idx)))

    # -- Input group state blobs (positions 85-92, 8 blobs) --
    for idx in range(8):
        e.append(tlv.encode_blob(SLT_GROUP_STATE, struct.pack('<I', idx) + b'\xff\xff\xff\xff'))

    # -- Variable slots (positions 93-348, 256 × 'Unnamed') --
    unnamed = 'Unnamed'.encode('utf-16-le')
    for idx in range(256):
        e.append(tlv.encode_varstr_raw(SLT_VARIABLE_NAME, struct.pack('<H', idx) + unnamed))

    # -- Page capabilities sentinel (position 349) — T2i uses tag=0x0A / 9 bytes --
    e.append(tlv.encode_blob(SLT_PAGE_CAP_T2I, bytes.fromhex('3400020c0000000000')))

    # -- T2i page containers --
    e.append(build_t2i_home_page(image_rgb=image_rgb, buttons=home_buttons))
    e.append(build_t2i_secondary_page(buttons=sec_buttons))

    # -- Trailing stream flags (present in both T2i streams of Test4.rti) --
    e.append(tlv.encode_byte(0x2f, 0))
    e.append(tlv.encode_byte(0x30, 0))
    e.append(tlv.encode_byte(0x31, 0))
    e.append(tlv.encode_byte(0x32, 0))
    e.append(tlv.encode_byte(0x33, 3))
    e.append(tlv.encode_byte(0x34, 2))
    e.append(tlv.encode_byte(0x35, 0))
    e.append(tlv.TERMINATOR)

    return b''.join(e)
