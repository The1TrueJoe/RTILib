"""
rti_lib/devices/t2i/encoders.py — TLV builders for T2i touch buttons.

The T2i is a colour touchscreen device.  Its page CONT nodes hold a list of
TAG=01 CONTAINER records — one per touch button.  Each button record is
structurally a superset of the U2 hardware button: the same 17-field base
section (254 sentinel, index, configured flag, label, bitmap index, etc.)
followed by 15 T2i-specific touch-region fields.

Button layout:
  Slots 128-179 (52 slots) cover the full T2i hardware button set.

  Slot → Integration Designer name (verified from idesign.exe device profile):
    128=Exit    129=Mute       130=Softkey 2  131=Up       132=Left
    133=Right   134=Down       135=OK         136=Softkey 1  137=Softkey 4
    138=Vol+    139=Vol-       140=Ch+        141=Ch-      142=Guide
    143=Menu    144=Info       145=Power Off  146=Play     147=Pause
    148=Stop    149=Record     150=Scan<<     151=Scan>>   152=Skip<<
    153=Skip>>  154=1          155=2          156=3        157=4
    158=5       159=6          160=7          161=8        162=9
    163=0       164=-/.        165=Enter      166=Joy Up   167=Joy Click
    168=Joy Dn  169=Joy Left   170=Joy Right  171=Power On 172=List
    173=Red     174=Green      175=Yellow     176=Blue     177=Softkey 3
    178=Prev    179=Back

Verified against Test4.rti (RTI Integration Designer baseline file).

Button CONT inner content (150 bytes):
  === U2-compatible base fields ===
  I32  tag=01 = 254          type sentinel (hardware-button style)
  I32  tag=02 = index        button index (128-179)
  I32  tag=03 = 0
  BYTE tag=02 = 0xFF         unconfigured flag (always 0xFF on T2i)
  BYTE tag=03 = 0
  BYTE tag=04 = 0
  BYTE tag=05 = 0
  BYTE tag=06 = 0
  I32  tag=0E = -1
  BYTE tag=0E = 1
  VARSTR tag=04 = label      display label (empty for stubs)
  I32  tag=04 = 0            bitmap index (unused on T2i — no BML icons)
  BYTE tag=07 = 2
  BYTE tag=08 = 0
  BYTE tag=09 = 0
  I32  tag=0C = 10
  I32  tag=0D = 0
  === T2i-specific touch fields ===
  I32  tag=10 = index        touch-slot ID (mirrors tag=02)
  I32  tag=11 = 0
  BYTE tag=0F = 3
  I32  tag=05 = x            touch region x (pixels, 0 = unset)
  I32  tag=06 = y            touch region y (pixels, 0 = unset)
  I32  tag=07 = w            touch region width (pixels, 0 = unset)
  I32  tag=08 = h            touch region height (pixels, 0 = unset)
  I32  tag=09 = 0
  I32  tag=0A = 0
  BYTE tag=0D = 1
  BYTE tag=0A = 0
  BYTE tag=0B = 0
  BYTE tag=0C = 0
  I32  tag=0B = 0
  I32  tag=0F = -1
  FF FF                      TERMINATOR

Label/macro container (TAG=01 CONTAINER, appended when a button is configured):
  U16  tag=01 = 1 or 2       (2 if macro reference present)
  BLOB tag=13 = 6 zero bytes
  raw: 02 E0 <orig_len LE32> <comp_len LE32> <zlib-compressed UTF-16LE label>
  [BLOB tag=17 = seq_num(2) + MACRO_REF_SUFFIX(6)]   (only if macro assigned)
  FF FF
"""

import struct
import zlib
from rti_lib.core import tlv

# ---- constants ------------------------------------------------------------

#: Suffix appended to the 2-byte macro sequence number inside label containers.
#: Same value as U1/U2 (observed in Test2/Test3.rti).
MACRO_REF_SUFFIX = bytes([0xFF, 0x00, 0x00, 0x00, 0x08, 0x07])

#: Number of button slots per page (52 slots, indices 128-179).
T2I_BUTTON_COUNT = 52

#: First hardware-button index for T2i slots.
T2I_BUTTON_BASE = 128


# ---- helpers --------------------------------------------------------------

def encode_t2i_label_container(label: str,
                               macro_seq_num: int = None) -> bytes:
    """
    Build the label/macro container (TAG=01 CONTAINER) for a T2i button.

    The label is stored as zlib-compressed UTF-16LE.  An optional macro
    reference BLOB is appended when ``macro_seq_num`` is given.

    Parameters
    ----------
    label         : button action label (e.g. 'Watch TV')
    macro_seq_num : XP macro sequence number, or None
    """
    raw  = label.encode('utf-16-le')
    comp = zlib.compress(raw, level=1)
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


def _encode_t2i_button_base(index: int, label: str = '') -> bytes:
    """Encode the 17-field common base shared with U2 hardware buttons."""
    return (
        tlv.encode_i32(0x01, 254) +
        tlv.encode_i32(0x02, index) +
        tlv.encode_i32(0x03, 0) +
        tlv.encode_byte(0x02, 0xFF) +   # always 0xFF on T2i
        tlv.encode_byte(0x03, 0) +
        tlv.encode_byte(0x04, 0) +
        tlv.encode_byte(0x05, 0) +
        tlv.encode_byte(0x06, 0) +
        tlv.encode_i32(0x0E, -1) +
        tlv.encode_byte(0x0E, 1) +
        tlv.encode_varstr(0x04, label) +
        tlv.encode_i32(0x04, 0) +       # bitmap index (unused)
        tlv.encode_byte(0x07, 2) +
        tlv.encode_byte(0x08, 0) +
        tlv.encode_byte(0x09, 0) +
        tlv.encode_i32(0x0C, 10) +
        tlv.encode_i32(0x0D, 0)
    )


def _encode_t2i_touch_fields(index: int,
                              x: int = 0, y: int = 0,
                              w: int = 0, h: int = 0) -> bytes:
    """
    Encode the 15 T2i-specific touch-region fields appended after the base.

    Parameters
    ----------
    index  : button slot index (repeated in tag=0x10 as the touch slot ID)
    x, y   : top-left pixel coordinate of the touch region (0 = unset)
    w, h   : pixel width and height of the touch region (0 = unset)
    """
    return (
        tlv.encode_i32(0x10, index) +
        tlv.encode_i32(0x11, 0) +
        tlv.encode_byte(0x0F, 3) +
        tlv.encode_i32(0x05, x) +
        tlv.encode_i32(0x06, y) +
        tlv.encode_i32(0x07, w) +
        tlv.encode_i32(0x08, h) +
        tlv.encode_i32(0x09, 0) +
        tlv.encode_i32(0x0A, 0) +
        tlv.encode_byte(0x0D, 1) +
        tlv.encode_byte(0x0A, 0) +
        tlv.encode_byte(0x0B, 0) +
        tlv.encode_byte(0x0C, 0) +
        tlv.encode_i32(0x0B, 0) +
        tlv.encode_i32(0x0F, -1)
    )


# ---- public button encoders -----------------------------------------------

def encode_t2i_button_stub(index: int) -> bytes:
    """
    Encode an unconfigured T2i button stub (150-byte inner content).

    Stub buttons are touch targets with no label, no macro, and no
    screen position set.  Both pages default to 52 stubs (indices 128-179)
    to match the T2i slot map.

    Parameters
    ----------
    index : button slot index (128-179)
    """
    content = (
        _encode_t2i_button_base(index) +
        _encode_t2i_touch_fields(index) +
        tlv.TERMINATOR
    )
    return tlv.encode_container(0x01, content)


def encode_t2i_button(index: int,
                      label: str = '',
                      macro_seq_num: int = None,
                      x: int = 0, y: int = 0,
                      w: int = 0, h: int = 0) -> bytes:
    """
    Encode a configured T2i button with an optional label, macro, and touch region.

    When ``label`` or ``macro_seq_num`` is provided the label/macro container
    is appended after the base fields, making the CONT larger than a plain stub.

    Parameters
    ----------
    index         : button slot index (128-179)
    label         : action label displayed on press (e.g. 'Watch TV')
    macro_seq_num : XP macro sequence number to invoke on tap, or None
    x, y          : top-left pixel position of the touch region (0 = unset)
    w, h          : pixel dimensions of the touch region (0 = unset)
    """
    content = (
        _encode_t2i_button_base(index, label=label) +
        _encode_t2i_touch_fields(index, x, y, w, h)
    )
    if label or macro_seq_num is not None:
        content += encode_t2i_label_container(label or '', macro_seq_num)
    content += tlv.TERMINATOR
    return tlv.encode_container(0x01, content)
