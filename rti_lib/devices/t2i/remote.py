"""
rti_lib/devices/t2i/remote.py — T2i colour touchscreen remote device class.

The T2i is a 240×320 pixel full-colour touchscreen handheld remote.
Its home page holds an optional background image and a set of touch buttons.
A secondary page holds additional buttons (typically navigation / media controls).

Each page supports up to 52 button slots (indices 128-179) covering the full
T2i hardware button set.  Slots that are not explicitly configured are written
as unconfigured stubs so Integration Designer can recognise the full slot map.

Typical usage::

    from rti_lib.devices.t2i import T2iRemote

    t2i = T2iRemote(display_name='Living Room')

    # Assign source buttons to the home page (auto-index starting at 128)
    t2i.add_source_button('Watch TV',    macro=m_tv)
    t2i.add_source_button('Watch Movie', macro=m_movie)

    # Or assign to a specific slot
    t2i.assign_button(130, 'Apple TV', macro=m_atv)

    # Secondary page: media controls
    t2i.assign_secondary_button(128, 'Play',  macro=m_play)
    t2i.assign_secondary_button(129, 'Pause', macro=m_pause)

    # Optional background image
    from rti_lib import load_image_rgb
    t2i.set_background(load_image_rgb('my_bg.png'))

    stream = t2i.build_stream()
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from rti_lib.devices.t2i.stream_profile import build_t2i_base_stream, T2I_WIDTH, T2I_HEIGHT
from rti_lib.devices.t2i.encoders import (
    encode_t2i_button_stub, encode_t2i_button, encode_t2i_screen_button,
    T2I_BUTTON_COUNT, T2I_BUTTON_BASE,
)


@dataclass
class _T2iButton:
    """Internal representation of one configured T2i button."""
    index:     int
    label:     str    = ''
    macro:     object = None   # Macro | None
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0
    image_rgb: bytes  = None   # Pre-rendered chip RGB bytes (w×h×3), or None for auto


class T2iRemote:
    """
    RTI T2i colour touchscreen handheld remote (240×320 px, 24-bit RGB).

    Pages
    -----
    Home page   (tag=0x01) — background image + source/shortcut buttons.
    Secondary page (tag=0x02) — additional buttons (media controls etc.).

    Each page has 52 button slots (indices 128-179).  Unassigned slots are
    written as empty stubs covering the full T2i slot map.

    Attributes
    ----------
    display_name : Name shown in the RTI project browser.
    """

    DISPLAY_WIDTH  = T2I_WIDTH
    DISPLAY_HEIGHT = T2I_HEIGHT

    # ---- hardware button table (T2i virtual hardware buttons) ---------------
    # Indices and factory labels observed in Test4.rti baseline file.
    # These map to standard T2i button functions in Integration Designer.
    _HARDWARE_BUTTONS: List[Tuple[int, str]] = [
        (128, 'Source'),   (129, 'Source 2'), (130, 'Source 3'),
        (131, 'Source 4'), (132, 'Source 5'), (133, 'Source 6'),
        (134, 'Source 7'), (135, 'Source 8'), (136, 'Source 9'),
        (137, 'Source 10'),
        (138, 'Vol+'),     (139, 'Vol-'),     (140, 'Mute'),
        (141, 'Ch+'),      (142, 'Ch-'),
        (143, 'Up'),       (144, 'Down'),     (145, 'Left'),
        (146, 'Right'),    (147, 'Select'),   (148, 'Back'),
        (149, 'Home'),     (150, 'Menu'),     (151, 'Info'),
        (152, 'Exit'),     (153, 'Guide'),
        (154, 'Play'),     (155, 'Pause'),    (156, 'Stop'),
        (157, 'Rewind'),   (158, 'FFwd'),     (159, 'Prev'),
        (160, 'Next'),     (161, 'Rec'),
        (162, '1'),  (163, '2'),  (164, '3'),
        (165, '4'),  (166, '5'),  (167, '6'),
        (168, '7'),  (169, '8'),  (170, '9'),
        (171, '0'),  (172, 'Enter'), (173, 'Clear'),
        (174, 'Fav'),  (175, 'On'),   (176, 'Off'),
        (177, 'Btn A'), (178, 'Btn B'), (179, 'Btn C'),
    ]

    def __init__(self, display_name: str = 'T2i', style=None):
        """
        Parameters
        ----------
        display_name : Name shown in the RTI project browser.
        style        : Optional ``StyleDef`` from ``rti_lib.assets.button_designer``.
                       When set, chip images are automatically generated for
                       each screen button that has w and h > 0.  Users can
                       also supply pre-rendered ``image_rgb`` bytes per button
                       to override auto-generation (e.g. for icon chips).
        """
        self.display_name             = display_name
        self._style                   = style
        self._image_rgb: Optional[bytes] = None
        self._home_btns: Dict[int, _T2iButton] = {}
        self._sec_btns:  Dict[int, _T2iButton] = {}
        self._next_home  = T2I_BUTTON_BASE
        self._next_sec   = T2I_BUTTON_BASE
        self._hw_button_macros: Dict[int, object] = {}  # index -> Macro
        # Fast label lookup from _HARDWARE_BUTTONS table
        self._hw_button_labels: Dict[int, str] = {
            idx: lbl for idx, lbl in self._HARDWARE_BUTTONS
        }

    # ---- background image ---------------------------------------------------

    def set_background(self, rgb_bytes: bytes,
                       width: int = None, height: int = None) -> None:
        """
        Set the home page background image.

        Parameters
        ----------
        rgb_bytes : Raw RGB pixel data (one byte per channel, top-to-bottom).
                    Must be exactly width * height * 3 bytes.
        width, height : Dimensions in pixels.  Defaults to 240 × 320.
        """
        w = width  or self.DISPLAY_WIDTH
        h = height or self.DISPLAY_HEIGHT
        expected = w * h * 3
        if len(rgb_bytes) != expected:
            raise ValueError(
                f'Background must be {w}x{h} RGB ({expected} bytes); '
                f'got {len(rgb_bytes)} bytes.'
            )
        self._image_rgb = rgb_bytes

    def clear_background(self) -> None:
        """Remove the home page background (reverts to solid white)."""
        self._image_rgb = None

    # ---- home page buttons --------------------------------------------------

    def assign_button(self, index: int, label: str = '',
                      macro=None,
                      x: int = 0, y: int = 0,
                      w: int = 0, h: int = 0,
                      image_rgb: bytes = None) -> None:
        """
        Assign a label and/or macro to a home-page button slot by index.

        Parameters
        ----------
        index  : Button slot (128-179).
        label  : Action label shown when the button is pressed.
        macro  : Macro from XPProcessor.add_macro().
        x, y   : Touch region top-left pixel position (0 = unset).
        w, h   : Touch region pixel dimensions (0 = unset).
        """
        self._home_btns[index] = _T2iButton(
            index=index, label=label, macro=macro, x=x, y=y, w=w, h=h,
            image_rgb=image_rgb)

    def add_source_button(self, label: str, macro=None,
                          x: int = 0, y: int = 0,
                          w: int = 0, h: int = 0,
                          image_rgb: bytes = None) -> int:
        """
        Add a source button to the next available home-page slot.

        Slots are filled from index 128 upward, skipping any that are already
        assigned.

        Parameters
        ----------
        label        : Action label (e.g. 'Watch TV').
        macro        : XP macro to invoke on tap.
        x, y, w, h   : Optional touch region in pixels.

        Returns
        -------
        int — The slot index assigned.
        """
        while self._next_home in self._home_btns:
            self._next_home += 1
        idx = self._next_home
        self._next_home += 1
        self.assign_button(idx, label=label, macro=macro, x=x, y=y, w=w, h=h,
                           image_rgb=image_rgb)
        return idx

    # ---- secondary page buttons ---------------------------------------------

    def assign_secondary_button(self, index: int, label: str = '',
                                macro=None,
                                x: int = 0, y: int = 0,
                                w: int = 0, h: int = 0,
                                image_rgb: bytes = None) -> None:
        """
        Assign a label and/or macro to a secondary-page button slot by index.

        Parameters
        ----------
        index  : Button slot (128-179).
        label  : Button label.
        macro  : XP macro to invoke on tap.
        x, y, w, h : Touch region in pixels (0 = unset).
        """
        self._sec_btns[index] = _T2iButton(
            index=index, label=label, macro=macro, x=x, y=y, w=w, h=h,
            image_rgb=image_rgb)

    def add_secondary_button(self, label: str, macro=None,
                             x: int = 0, y: int = 0,
                             w: int = 0, h: int = 0,
                             image_rgb: bytes = None) -> int:
        """
        Add a button to the next available secondary-page slot.

        Returns the assigned slot index.
        """
        while self._next_sec in self._sec_btns:
            self._next_sec += 1
        idx = self._next_sec
        self._next_sec += 1
        self.assign_secondary_button(idx, label=label, macro=macro,
                                     x=x, y=y, w=w, h=h,
                                     image_rgb=image_rgb)
        return idx

    @classmethod
    def hardware_buttons(cls) -> List[Tuple[int, str]]:
        """Return the list of (index, factory_label) for all 52 T2i slots."""
        return cls._HARDWARE_BUTTONS

    def assign_hw_button_macro(self, index: int, macro) -> None:
        """
        Link an XP macro to a physical hardware button by index (128-179).

        Hardware button macros are written into *every* page so the button
        works regardless of which page is currently displayed.  Page-specific
        buttons (assigned via assign_button / add_source_button) take
        priority for the same slot index on their respective page.

        Parameters
        ----------
        index : Hardware button index as listed in _HARDWARE_BUTTONS.
        macro : Macro from XPProcessor.add_macro().
        """
        self._hw_button_macros[index] = macro

    # ---- stream build -------------------------------------------------------

    def _build_page_buttons(self, assigned: Dict[int, _T2iButton]) -> bytes:
        """
        Build all button CONT records for one page.

        Two distinct button types are written to the same page CONTAINER:

        1. **Hardware button stubs** (sentinel=254, indices 128-179) — always
           written for all 52 T2i hardware slots.  Slots that have a global
           hardware macro assigned (via ``assign_hw_button_macro``) are written
           with that macro; all others are empty stubs.

        2. **Screen buttons** (sentinel=0) — one per entry in ``assigned``,
           appended after the hardware stubs.  These are the visible, tappable
           tiles on the T2i display.

           If the remote was created with a ``style`` and the button has
           non-zero w/h, chip images are auto-generated unless the button
           already carries pre-rendered ``image_rgb`` bytes.
        """
        import io
        parts = []

        # --- 52 hardware button stubs (slots 128-179) ---
        for idx in range(T2I_BUTTON_BASE, T2I_BUTTON_BASE + T2I_BUTTON_COUNT):
            if idx in self._hw_button_macros:
                m = self._hw_button_macros[idx]
                lbl = self._hw_button_labels.get(idx, '')
                parts.append(encode_t2i_button(
                    idx,
                    label=lbl,
                    macro_seq_num=m.seq_num if m else None,
                ))
            else:
                parts.append(encode_t2i_button_stub(idx))

        # --- Screen buttons (visible tiles on the touchscreen display) ---
        for b in assigned.values():
            image_rgb = b.image_rgb
            if image_rgb is None and self._style is not None and b.w > 0 and b.h > 0:
                # Auto-generate a chip using ButtonDesigner.
                from rti_lib.assets.button_designer import ButtonDesigner
                from PIL import Image
                font_size = max(8, min(14, b.h // 6))
                chip_png  = ButtonDesigner.button_chip(
                    b.w, b.h, label=b.label,
                    style=self._style, font_size=font_size,
                )
                img = Image.open(io.BytesIO(chip_png)).convert('RGB')
                image_rgb = img.tobytes()
            parts.append(encode_t2i_screen_button(
                x=b.x, y=b.y, w=b.w, h=b.h,
                label=b.label,
                macro_seq_num=b.macro.seq_num if b.macro else None,
                image_rgb=image_rgb,
            ))

        return b''.join(parts)

    def _build_global_buttons(self) -> list:
        """
        Build one button CONT record per slot for the global TAG=02 group.

        Integration Designer reads this group to discover all configured
        buttons (same role as the global group on U1/U2 remotes).

        Priority per slot: home page > secondary page > hw global macro > stub.
        Returns a list of encoded byte strings (one per slot).
        """
        records = []
        for idx in range(T2I_BUTTON_BASE, T2I_BUTTON_BASE + T2I_BUTTON_COUNT):
            if idx in self._home_btns:
                b = self._home_btns[idx]
                records.append(encode_t2i_button(
                    idx,
                    label=b.label,
                    macro_seq_num=b.macro.seq_num if b.macro else None,
                    x=b.x, y=b.y, w=b.w, h=b.h,
                ))
            elif idx in self._sec_btns:
                b = self._sec_btns[idx]
                records.append(encode_t2i_button(
                    idx,
                    label=b.label,
                    macro_seq_num=b.macro.seq_num if b.macro else None,
                    x=b.x, y=b.y, w=b.w, h=b.h,
                ))
            elif idx in self._hw_button_macros:
                m = self._hw_button_macros[idx]
                lbl = self._hw_button_labels.get(idx, '')
                records.append(encode_t2i_button(
                    idx,
                    label=lbl,
                    macro_seq_num=m.seq_num if m else None,
                ))
            else:
                records.append(encode_t2i_button_stub(idx))
        return records

    def build_stream(self) -> bytes:
        """
        Build the complete T2i device data stream bytes.

        Layout::

            [350 shared header TLV records]
            [Page-capabilities sentinel BLOB (tag=0x0A)]
            [Home page CONTAINER  (tag=0x01) — background image + 52 buttons]
            [Secondary page CONTAINER (tag=0x02) — 52 buttons]

        The T2i is a touchscreen device.  Integration Designer discovers
        configured buttons by reading the page CONTs (TAG=01 for home page,
        TAG=02 for secondary page).  Unlike U1/U2 button-only remotes, T2i
        does not use a separate global button group — the page containers
        serve that role.

        Returns
        -------
        bytes — Raw TLV stream ready to write into an RTI Data Stream slot.
        """
        return build_t2i_base_stream(
            display_name=self.display_name,
            image_rgb=self._image_rgb,
            home_buttons=self._build_page_buttons(self._home_btns),
            sec_buttons=self._build_page_buttons(self._sec_btns),
        )

