"""
rti_lib/devices/u1/encoders.py — TLV builders for U1 button records.

The U1 remote has only physical buttons (no display).  Each button maps to
a hardware index (≥128) and optionally references an XP macro.

Button TLV structure (inside TAG=01 CONTAINER):
  base fields (46 bytes):
    I32  tag=01 = 254        (type sentinel)
    I32  tag=02 = hw_index   (hardware button index)
    I32  tag=03 = 0
    BYTE tag=02 = 0x00|0xFF  (0x00=configured, 0xFF=unconfigured)
    BYTE tag=03–06 = 0
    I32  tag=0E = -1
    BYTE tag=0E = 1
    VARSTR tag=04 = label
  [optional macro-ref container — only when button has an action]
  FF FF  (terminator)
"""

from rti_lib.core import tlv
from rti_lib.devices.common import _encode_button_base, encode_macro_ref_container


def encode_u1_button_empty(btn_idx: int, label: str = '') -> bytes:
    """
    Encode an unconfigured U1 button (no macro assigned).

    btn_idx : hardware button index (128-based)
    label   : display label (VARSTR tag=04)
    """
    return tlv.encode_container(
        0x01,
        _encode_button_base(btn_idx, configured=False, label=label)
        + tlv.TERMINATOR,
    )


def encode_u1_button_with_ref(btn_idx: int, macro_seq_num: int,
                               label: str = '') -> bytes:
    """
    Encode a U1 button that triggers an XP macro when pressed.

    btn_idx       : hardware button index (128-based)
    macro_seq_num : sequence number of the target macro (from XPProcessor)
    label         : display label
    """
    return tlv.encode_container(
        0x01,
        _encode_button_base(btn_idx, configured=True, label=label)
        + encode_macro_ref_container(macro_seq_num)
        + tlv.TERMINATOR,
    )
