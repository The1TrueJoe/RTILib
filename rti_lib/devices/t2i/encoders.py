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
  BYTE tag=02 = 0x00|0xFF    0x00=configured (has label/macro), 0xFF=unconfigured
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

import io
import struct
import zlib
from PIL import Image, ImageEnhance
from rti_lib.core import tlv
from rti_lib.devices.t2i.stream_profile import _encode_t2i_image_inner

# ---------------------------------------------------------------------------
# Button-image encoder
# ---------------------------------------------------------------------------

def encode_t2i_button_image(tag: int, rgb_bytes: bytes, w: int, h: int) -> bytes:
    """
    Encode a button state image as CONT(tag).

    Used to embed normal-state (tag=0x04) and pressed-state (tag=0x05) images
    inside a screen button CONT.  The image data uses the same encoding as
    page background images but with BMP 4-byte row-stride alignment.

    Parameters
    ----------
    tag      : 0x04 for normal state, 0x05 for pressed state.
    rgb_bytes: Raw RGB pixel data (width × height × 3 bytes), top-to-bottom.
    w, h     : Image dimensions (must match the button's touch-region size).
    """
    return tlv.encode_container(tag, _encode_t2i_image_inner(rgb_bytes, w, h))


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


def _encode_t2i_button_base(index: int, label: str = '',
                           configured: bool = False) -> bytes:
    """Encode the 17-field common base shared with U2 hardware buttons."""
    return (
        tlv.encode_i32(0x01, 254) +
        tlv.encode_i32(0x02, index) +
        tlv.encode_i32(0x03, 0) +
        tlv.encode_byte(0x02, 0x00 if configured else 0xFF) +  # 0x00=configured, 0xFF=unconfigured
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
    Encode a hardware-slot T2i button (sentinel=254, slot 128-179) with a macro.

    Used for physical hardware buttons that have a global macro assigned
    (e.g. Vol+, Guide).  Screen-visible touch buttons use
    ``encode_t2i_screen_button`` instead.

    Parameters
    ----------
    index         : hardware slot index (128-179)
    label         : label used in Integration Designer
    macro_seq_num : XP macro sequence number to invoke, or None
    x, y          : touch region top-left (0 = unset)
    w, h          : touch region dimensions (0 = unset)
    """
    is_configured = bool(label or macro_seq_num is not None)
    content = (
        _encode_t2i_button_base(index, label=label, configured=is_configured) +
        _encode_t2i_touch_fields(index, x, y, w, h)
    )
    if is_configured:
        content += encode_t2i_label_container(label or '', macro_seq_num)
    content += tlv.TERMINATOR
    return tlv.encode_container(0x01, content)


def encode_t2i_screen_button(x: int, y: int, w: int, h: int,
                              label: str = '',
                              macro_seq_num: int = None,
                              image_rgb: bytes = None,
                              pressed_rgb: bytes = None) -> bytes:
    """
    Encode a T2i on-screen touch button (type sentinel = 0).

    Screen buttons are the visible, tappable tiles rendered on the T2i
    display.  They differ from hardware button stubs (sentinel=254, slots
    128-179) in two key ways:

    * The type sentinel in I32(01) is ``0`` (not ``254``).
    * Position and size are packed into I32(02)/(I32(03)) as::

          I32(02) = (x << 16) | y    — top-left pixel coordinate
          I32(03) = (h << 16) | w    — pixel dimensions

    Integration Designer renders the embedded chip images (CONT tag=04 normal
    state, CONT tag=05 pressed state) as the button visual.  Without those
    images the button face is transparent.

    Parameters
    ----------
    x, y          : Top-left pixel coordinate of the touch region.
    w, h          : Pixel dimensions of the touch region.
    label         : Display label shown in Integration Designer (may be empty).
    macro_seq_num : XP macro sequence number to invoke on tap, or None.
    image_rgb     : Optional raw RGB bytes (w×h×3) for the normal state chip image.
    pressed_rgb   : Optional raw RGB bytes (w×h×3) for the pressed state chip image.
                    Defaults to a darkened version of image_rgb when omitted.
    """
    packed_pos  = ((x & 0xFFFF) << 16) | (y & 0xFFFF)
    packed_size = ((h & 0xFFFF) << 16) | (w & 0xFFFF)

    # Colour values observed in Test4.rti.  High byte is alpha (0x00=transparent,
    # 0xFF=opaque).  Face is transparent so the embedded chip image shows through.
    _FACE    =  16711680   # 0x00FF0000 — transparent face (chip image drawn instead)
    _BORDER  = -16777216   # 0xFF000000 — opaque black border
    _TEXT    =  16777215   # 0x00FFFFFF — white text

    content = (
        tlv.encode_i32(0x01, 0) +            # type sentinel (0 = screen button)
        tlv.encode_i32(0x02, packed_pos) +   # packed (x<<16)|y position
        tlv.encode_i32(0x03, packed_size) +  # packed (h<<16)|w size
        tlv.encode_byte(0x02, 0xFF) +        # configured flag (always 0xFF for screen buttons)
        tlv.encode_byte(0x03, 0) +
        tlv.encode_byte(0x04, 0) +
        tlv.encode_byte(0x05, 0) +
        tlv.encode_byte(0x06, 0) +
        tlv.encode_i32(0x0E, -1) +
        tlv.encode_byte(0x0E, 1) +
        tlv.encode_varstr(0x04, '') +        # label field (text goes in label CONT below)
        tlv.encode_i32(0x04, 0) +            # bitmap index (0 = no embedded BML icon)
        tlv.encode_byte(0x07, 2) +
        tlv.encode_byte(0x08, 0) +
        tlv.encode_byte(0x09, 0) +
        tlv.encode_i32(0x0C, 10) +
        tlv.encode_i32(0x0D, 0) +
        tlv.encode_i32(0x10, packed_pos) +   # touch slot ID (mirrors I32(02))
        tlv.encode_i32(0x11, packed_size) +  # touch size (mirrors I32(03))
        tlv.encode_byte(0x0F, 3) +
        tlv.encode_i32(0x05, _FACE) +
        tlv.encode_i32(0x06, _BORDER) +
        tlv.encode_i32(0x07, _FACE) +
        tlv.encode_i32(0x08, _FACE) +
        tlv.encode_i32(0x09, _BORDER) +
        tlv.encode_i32(0x0A, _TEXT) +
        tlv.encode_byte(0x0D, 0) +           # 0 for screen buttons (1 for hw stubs)
        tlv.encode_byte(0x0A, 0) +
        tlv.encode_byte(0x0B, 0) +
        tlv.encode_byte(0x0C, 0) +
        tlv.encode_i32(0x0B, 0)
        # CONT(04) normal image, CONT(05) pressed image, I32(0F)=-1, label CONT
        # are appended below in the order observed in Test4.rti.
    )

    # Embed chip images (normal and pressed states).
    if image_rgb is not None:
        if pressed_rgb is None:
            # Auto-generate a 75%-brightness pressed state from the normal image.
            img = Image.frombytes('RGB', (w, h), image_rgb)
            pressed_rgb = ImageEnhance.Brightness(img).enhance(0.75).tobytes()
        content += encode_t2i_button_image(0x04, image_rgb, w, h)
        content += encode_t2i_button_image(0x05, pressed_rgb, w, h)

    content += tlv.encode_i32(0x0F, -1)
    if label or macro_seq_num is not None:
        content += encode_t2i_label_container(label or '', macro_seq_num)
    content += tlv.TERMINATOR
    return tlv.encode_container(0x01, content)
