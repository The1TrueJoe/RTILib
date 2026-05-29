"""
rti_lib/devices/u2/remote.py — U2 touchscreen remote device class.

The U2 is a 2.1-inch 64×128 pixel B&W LCD handheld remote.
It shows a 2×4 icon grid (shortcut tiles) on its main screen and has
35 physical hardware buttons below the display.

Typical usage::

    from rti_lib.devices.u2 import U2Remote
    from rti_lib.devices.u2.bml import BMLFile

    bml = BMLFile.load('icons.bml')
    u2  = U2Remote(display_name='Living Room')
    u2.add_shortcut('Watch TV',    icon=bml['TV'],    macro=m1)
    u2.add_shortcut('Watch Movie', icon=bml['Movie'], macro=m2)
    u2.add_shortcut('All Off',                         macro=m3)
"""

from dataclasses import dataclass
from typing import List, Optional
from rti_lib.core import tlv
from rti_lib.devices.common import encode_global_button_group
from rti_lib.devices.u2.encoders import encode_u2_hardware_button, encode_u2_shortcut_cell
from rti_lib.devices.u2.stream_profile import build_u2_base_stream


@dataclass
class _U2Shortcut:
    """Internal representation of one shortcut tile."""
    hw_index:     int
    label:        str
    macro:        object = None   # Macro | None
    bitmap_index: int    = 0
    icon:         object = None   # BMLIcon | None


class U2Remote:
    """
    RTI U2 display-based handheld remote (64×128 B&W LCD, 2×4 icon grid).

    Up to 8 shortcut tiles are shown on the main screen.
    Tiles and physical buttons are both stored in the same TAG=02 global
    button group container in the device stream.

    Attributes
    ----------
    display_name : name shown in the RTI Data Directory (project browser)
    """

    def __init__(self, display_name: str = 'U2'):
        self.display_name        = display_name
        self._shortcuts: List[_U2Shortcut] = []
        self._bitmaps:   list              = []  # BMLIcon list (insertion order)
        self._next_idx   = 128
        self._hw_button_macros: dict       = {}  # {hw_index: Macro}

    # ---- Factory-assigned hardware button layout (from Test3.rti) ---------
    # Each tuple is (hw_index, factory_label).
    # Indices 128–162 map directly to the physical buttons on the U2 chassis.
    # Labels are the factory-default names visible in Integration Designer.
    _HARDWARE_BUTTONS = [
        (128, 'MENU'),
        (129, ''),
        (130, 'Home'),
        (131, ''),
        (132, 'Left'),
        (133, 'Right'),
        (134, 'DOWN'),
        (135, 'SELECT'),
        (136, 'GUIDE'),
        (137, 'Exit'),
        (138, 'Vol+'),
        (139, 'VOL-'),
        (140, ''),
        (141, 'Channel-'),
        (142, '9'),
        (143, '8'),
        (144, '7'),
        (145, '6'),
        (146, '5'),
        (147, '4'),
        (148, '3'),
        (149, '2'),
        (150, '1'),
        (151, '0'),
        (152, 'Enter'),
        (153, 'Star'),
        (154, 'PLAY'),
        (155, 'PAUSE'),
        (156, 'STOP'),
        (157, 'NEXT'),
        (158, 'BACK'),
        (159, 'FORWARD'),
        (160, 'On'),
        (161, 'Off'),
        (162, 'Favorites'),
    ]

    # ---- public API -------------------------------------------------------

    def add_shortcut(
            self,
            label: str,
            macro=None,
            icon=None,
            hw_index: int = None,
    ) -> _U2Shortcut:
        """
        Add a shortcut tile to the 2×4 icon grid.

        The grid fills left-to-right, top-to-bottom.  Up to 8 tiles are
        displayed; any beyond 8 are silently ignored.

        Parameters
        ----------
        label    : action label shown when the tile is pressed (e.g. 'Source1')
        macro    : Macro from XPProcessor.add_macro() to invoke on tap
        icon     : BMLIcon loaded via BMLFile.load() for the tile image
        hw_index : hardware index (auto-assigned starting at 128 if omitted)
        """
        if hw_index is None:
            hw_index = self._next_idx
            self._next_idx += 1

        bitmap_index = 0
        if icon is not None:
            bitmap_index = len(self._bitmaps)
            self._bitmaps.append(icon)

        sc = _U2Shortcut(hw_index=hw_index, label=label, macro=macro,
                         bitmap_index=bitmap_index, icon=icon)
        self._shortcuts.append(sc)
        return sc

    def assign_hw_button_macro(self, hw_index: int, macro) -> None:
        """
        Link an XP macro to a physical hardware button by its index (128-162).

        Parameters
        ----------
        hw_index : hardware button index as listed in _HARDWARE_BUTTONS
        macro    : Macro from XPProcessor.add_macro()
        """
        self._hw_button_macros[hw_index] = macro

    @classmethod
    def hardware_buttons(cls):
        """Return the list of (hw_index, label) tuples for all 35 physical buttons."""
        return cls._HARDWARE_BUTTONS

    # ---- internal ---------------------------------------------------------

    def build_stream(self) -> bytes:
        """
        Build the complete device data stream bytes for this U2 remote.

        Layout:
          [U2 base stream — 351 TLV records, 8679 bytes]
          [TAG=02 global button group container]:
            [shortcut tile records (TAG=01 each) — up to 8]
            [hardware button records (TAG=01 each) — 35 factory buttons]
          [FF FF terminator]

        Both shortcut tiles and hardware buttons live inside the same TAG=02
        container.  Placing shortcut records outside the container would cause
        Integration Designer to interpret them as separate pages.
        """
        prefix = build_u2_base_stream(self.display_name)

        # ---- shortcut grid (up to 8 tiles, 2 columns × 4 rows) -----------
        shortcut_records = []
        for pos, sc in enumerate(self._shortcuts[:8]):
            row = pos // 2
            col = pos % 2
            # Use the BML icon name as the tile label, comment as the action label
            cell_label = getattr(sc.icon, 'name', '') if sc.icon is not None else ''
            shortcut_records.append(encode_u2_shortcut_cell(
                row=row,
                col=col,
                label=cell_label,
                icon=sc.icon,
                macro_seq_num=sc.macro.seq_num if sc.macro else None,
                comment=sc.label,
            ))

        # ---- factory hardware buttons (35 physical buttons) ---------------
        hardware_buttons = [
            encode_u2_hardware_button(
                index,
                comment,
                macro_seq_num=(
                    self._hw_button_macros[index].seq_num
                    if index in self._hw_button_macros else None
                ),
            )
            for index, comment in self._HARDWARE_BUTTONS
        ]

        # Both shortcut tiles and hardware buttons go inside the TAG=02 group.
        suffix = (
            encode_global_button_group(shortcut_records + hardware_buttons) +
            tlv.TERMINATOR
        )
        return prefix + suffix
