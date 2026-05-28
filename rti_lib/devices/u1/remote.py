"""
rti_lib/devices/u1/remote.py — U1 handheld remote device class.

The U1 is a button-only remote.  All buttons are 'global' — they are active
regardless of which page is displayed (there is no display on the U1).

Typical usage::

    u1 = U1Remote(display_name='Bedroom Remote')
    u1.add_global_button('Watch TV',    macro=m1)
    u1.add_global_button('Watch Movie', macro=m2)
    u1.add_global_button('All Off',     macro=m3)
"""

from dataclasses import dataclass
from typing import List, Optional
from ...core import tlv
from ..common import encode_global_button_group
from .encoders import encode_u1_button_empty, encode_u1_button_with_ref
from .stream_profile import build_u1_base_stream


@dataclass
class _U1Button:
    """Internal representation of a single U1 button."""
    hw_index: int
    label:    str
    macro:    object = None   # Macro | None


class U1Remote:
    """
    RTI U1 button-only handheld remote.

    Hardware button indices start at 128 and are auto-assigned unless you
    supply an explicit hw_index.

    Attributes
    ----------
    display_name : name shown in the RTI Data Directory (project browser)
    """

    def __init__(self, display_name: str = 'U1'):
        self.display_name    = display_name
        self._global: List[_U1Button] = []
        self._next_idx = 128

    # ---- public API -------------------------------------------------------

    def add_global_button(
            self,
            label: str,
            macro=None,
            hw_index: int = None,
    ) -> _U1Button:
        """
        Add a global button that is always active.

        Parameters
        ----------
        label    : button display label (e.g. 'Watch TV')
        macro    : Macro returned by XPProcessor.add_macro() to invoke on press
        hw_index : hardware index (auto-assigned starting at 128 if omitted)
        """
        if hw_index is None:
            hw_index = self._next_idx
            self._next_idx += 1
        btn = _U1Button(hw_index=hw_index, label=label, macro=macro)
        self._global.append(btn)
        return btn

    # ---- internal ---------------------------------------------------------

    def build_stream(self) -> bytes:
        """
        Build the complete device data stream bytes for this U1 remote.

        Layout:
          [U1 base stream — 350 TLV records, 5834 bytes]
          [global button group container — TAG=02, contains all buttons]
          [FF FF terminator]
        """
        prefix = build_u1_base_stream(self.display_name)
        btns = []
        for btn in self._global:
            if btn.macro:
                btns.append(encode_u1_button_with_ref(
                    btn.hw_index, btn.macro.seq_num, label=btn.label))
            else:
                btns.append(encode_u1_button_empty(btn.hw_index, label=btn.label))
        return prefix + encode_global_button_group(btns) + tlv.TERMINATOR
