"""
rti_lib/devices/u2/encoders.py — TLV builders for U2 buttons and shortcuts.

The U2 has:
  • A 2×4 shortcut grid (up to 8 icon tiles on the main screen).
  • Up to 35 physical hardware buttons (MENU, Vol+, numbers, etc.).

Shortcut cells live inside the TAG=02 global button group alongside the
hardware buttons.  Each cell is a TAG=01 CONTAINER.

Shortcut cell TLV structure:
  I32  tag=01 = 0          (type sentinel — 0 for shortcut, 254 for hw button)
  I32  tag=02 = position   ((row+1)<<16 | col)  zero-based, row 0 = top
  I32  tag=03 = 0x00010001 (dimensions flag)
  BYTE tag=02 = 0xFF       (unconfigured sentinel — shortcuts use 0xFF)
  BYTE tag=03–06 = 0
  I32  tag=0E = -1
  BYTE tag=0E = 1
  VARSTR tag=04 = icon_name
  I32  tag=04 = 12 if icon else 0   (bitmap index)
  BYTE tag=07 = 2
  BYTE tag=08/09 = 0
  I32  tag=0C = 10
  I32  tag=0D = 0
  [optional bitmap container — TAG=02 CONTAINER with 1-bpp pixel data]
  [optional comment container — TAG=01 CONTAINER with compressed label + macro ref]
  FF FF

Hardware-button TLV structure:
  [same base fields as U1 except configured=False and has extra fields]
  I32 tag=04 = 0    (bitmap index)
  BYTE tag=07 = 2
  BYTE tag=08/09 = 0
  I32 tag=0C = 10
  I32 tag=0D = 0
  [optional comment container]
  FF FF

Comment container (TAG=01 CONTAINER):
  U16  tag=01 = 1 or 2        (2 if macro ref is present)
  BLOB tag=13 = 6 zero bytes  (fixed padding)
  raw bytes: 02 E0 <orig_len LE32> <comp_len LE32> <zlib-compressed UTF-16LE>
  [optional BLOB tag=17 = seq_num(2) + MACRO_REF_SUFFIX(6)]
  FF FF

Bitmap container (TAG=02 CONTAINER):
  inside a TAG=01 CONTAINER:
    I32   tag=01 = pixel_data_length
    BYTE  tag=01 = 2
    raw TAG=01 CONTAINER with pixel_data_length bytes of raw 1-bpp data
  FF FF
"""

import math
import struct
import zlib
from ...core import tlv
from ..common import _encode_button_base, encode_macro_ref_container

# Suffix appended to the 2-byte macro seq_num inside comment containers.
# Observed in Test3.rti; purpose is unknown.
MACRO_REF_SUFFIX = bytes([0xFF, 0x00, 0x00, 0x00, 0x08, 0x07])


def _encode_u2_extra_fields(bitmap_index: int = 0) -> bytes:
    """
    Encode the 27-byte extra fields present in U2 button records but absent
    from U1 button records.

      I32  tag=04 = bitmap_index  (0 = no icon, >0 = icon index)
      BYTE tag=07 = 2
      BYTE tag=08 = 0
      BYTE tag=09 = 0
      I32  tag=0C = 10
      I32  tag=0D = 0
    """
    return (
        tlv.encode_i32(0x04, bitmap_index) +
        tlv.encode_byte(0x07, 2) +
        tlv.encode_byte(0x08, 0) +
        tlv.encode_byte(0x09, 0) +
        tlv.encode_i32(0x0C, 10) +
        tlv.encode_i32(0x0D, 0)
    )


def encode_u2_comment_container(text: str,
                                macro_seq_num: int = None) -> bytes:
    """
    Encode the U2 compressed comment/label container (TAG=01 CONTAINER).

    The label text is stored zlib-compressed (level 1) as UTF-16LE.
    A macro reference BLOB is appended when macro_seq_num is given.

    This container is used for:
      • Hardware button factory labels (e.g. 'MENU', 'Vol+')
      • Shortcut cell action labels shown on press (e.g. 'Source1')

    Parameters
    ----------
    text          : label text (encoded as UTF-16LE, then zlib-compressed)
    macro_seq_num : XP macro sequence number to link, or None for label-only
    """
    raw  = text.encode('utf-16-le')
    comp = zlib.compress(raw, level=1)
    # RTI uses a custom 10-byte prefix before the compressed payload:
    #   02 E0 <original_len LE32> <compressed_len LE32>
    custom_var = (
        bytes([0x02, 0xE0]) +
        struct.pack('<I', len(raw)) +
        struct.pack('<I', len(comp)) +
        comp
    )
    macro_ref = b''
    if macro_seq_num is not None:
        macro_ref = tlv.encode_blob(
            0x17,
            struct.pack('<H', macro_seq_num) + MACRO_REF_SUFFIX,
        )
    content = (
        tlv.encode_u16(0x01, 2 if macro_ref else 1) +
        tlv.encode_blob(0x13, b'\x00' * 6) +
        custom_var +
        macro_ref +
        tlv.TERMINATOR
    )
    return tlv.encode_container(0x01, content)


def encode_u2_bitmap_container(icon) -> bytes:
    """
    Encode an inline 1-bpp bitmap container from a BMLIcon.

    The bitmap is embedded directly inside the shortcut cell container
    rather than stored as a separate stream.  Integration Designer expects
    this structure for icons displayed on the U2 touchscreen.

    icon : BMLIcon loaded via BMLFile.load()  (from devices/u2/bml.py)

    Pixel encoding: 1-bpp big-endian rows, 1=background(white), 0=foreground.
    Row stride = ceil(width / 8) bytes.
    """
    if icon is None:
        return b''
    pixel_data = icon.pixel_data
    expected   = math.ceil(icon.width / 8) * icon.height
    if len(pixel_data) != expected:
        raise ValueError(
            f"icon pixel_data length {len(pixel_data)} != "
            f"expected {icon.width}×{icon.height} 1-bpp size {expected}"
        )
    # Inner raw bitmap node — the pixel bytes are wrapped in a container header
    # but without the usual TLV length because the pixel size is known externally.
    raw_bitmap_node = (
        bytes([0x01, tlv.T_CONTAINER]) +
        struct.pack('<I', len(pixel_data)) +
        pixel_data
    )
    content = (
        tlv.encode_i32(0x01, len(pixel_data)) +
        tlv.encode_byte(0x01, 2) +
        raw_bitmap_node +
        tlv.TERMINATOR
    )
    return tlv.encode_container(0x02, content)


def encode_u2_hardware_button(btn_idx: int, comment: str = '',
                              macro_seq_num: int = None) -> bytes:
    """
    Encode one U2 physical hardware button record (TAG=01 CONTAINER).

    These records represent the factory-labelled physical buttons
    (MENU, Vol+, 0–9, PLAY, etc.).  Their indices run from 128–162.
    They always carry the extra U2 fields (bitmap index, display flags)
    in addition to the U1 base fields.

    Parameters
    ----------
    btn_idx       : hardware button index (128–162)
    comment       : factory label string (e.g. 'MENU', 'Vol+')
    macro_seq_num : macro to invoke on press (usually None for hw buttons)
    """
    content = (
        _encode_button_base(btn_idx, configured=False, label='') +
        _encode_u2_extra_fields(0)
    )
    if comment:
        content += encode_u2_comment_container(comment)
    if macro_seq_num is not None:
        content += encode_macro_ref_container(macro_seq_num)
    return tlv.encode_container(0x01, content + tlv.TERMINATOR)


def encode_u2_shortcut_cell(row: int, col: int, label: str = '',
                            icon=None, macro_seq_num: int = None,
                            comment: str = '') -> bytes:
    """
    Encode a U2 2×4 display shortcut cell (TAG=01 CONTAINER).

    The U2 main screen shows a 2-column × 4-row grid of icon tiles.
    Rows and columns are zero-based; row 0 is the top-left.

    Integration Designer encodes the cell position as:
      position = (row + 1) << 16 | col

    Parameters
    ----------
    row           : grid row (0–3, top to bottom)
    col           : grid column (0–1, left to right)
    label         : icon name label (e.g. icon.name from BMLFile)
    icon          : BMLIcon for the tile image (optional)
    macro_seq_num : XP macro to invoke when this tile is tapped (optional)
    comment       : action label shown when pressed (e.g. 'Source1')
    """
    position = ((row + 1) << 16) | (col & 0xFFFF)
    content = (
        tlv.encode_i32(0x01, 0) +
        tlv.encode_i32(0x02, position) +
        tlv.encode_i32(0x03, 0x00010001) +
        tlv.encode_byte(0x02, 0xFF) +
        tlv.encode_byte(0x03, 0) +
        tlv.encode_byte(0x04, 0) +
        tlv.encode_byte(0x05, 0) +
        tlv.encode_byte(0x06, 0) +
        tlv.encode_i32(0x0E, -1) +
        tlv.encode_byte(0x0E, 1) +
        tlv.encode_varstr(0x04, label) +
        tlv.encode_i32(0x04, 12 if icon is not None else 0) +
        tlv.encode_byte(0x07, 2) +
        tlv.encode_byte(0x08, 0) +
        tlv.encode_byte(0x09, 0) +
        tlv.encode_i32(0x0C, 10) +
        tlv.encode_i32(0x0D, 0)
    )
    if icon is not None:
        content += encode_u2_bitmap_container(icon)
    if comment or label:
        content += encode_u2_comment_container(comment or label, macro_seq_num)
    return tlv.encode_container(0x01, content + tlv.TERMINATOR)
