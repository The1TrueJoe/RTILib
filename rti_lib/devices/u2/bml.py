"""
rti_lib/bml.py — RTI Bitmap Library (.bml) reader and writer.

.bml files store a collection of 1-bpp icons used on RTI U2 remotes.
Format reverse-engineered; implementation based on
https://github.com/The1TrueJoe/rti-bml-scripts

File layout
-----------
  Header (12 bytes):
    [0:4]  magic    = 27 75 37 09
    [4:6]  count    LE uint16 — number of records
    [6:8]  version  = 01 00
    [8:12] flags    = 00 00 00 00

  Record (41 + pixel_bytes bytes):
    [0:2]   marker   12 21
    [2:4]   width    LE uint16
    [4:6]   height   LE uint16
    [6:14]  fixed    01 00 01 00 01 00 00 09
    [14:18] unknown  (zeroed when writing)
    [18:41] name+meta (23 bytes):
              [18..]  null-terminated name (max 20 chars)
              [..]    meta fills remainder:
                        meta[0:3] = fg R, G, B
                        meta[-2:] = pixel_data_size LE uint16
    [41..]  pixels   big-endian packed 1-bpp rows
              bit 1 = background (white)
              bit 0 = foreground (icon colour)
              row stride = ceil(width / 8) bytes
"""

import math
import struct
from dataclasses import dataclass
from typing import List, Optional

_MAGIC      = b'\x27\x75\x37\x09'
_MARKER     = b'\x12\x21'
_FIXED_HDR  = 18   # bytes before the name+meta field
_NAME_FIELD = 23   # bytes for the name+meta field combined
_RECORD_HDR = _FIXED_HDR + _NAME_FIELD  # = 41 bytes


def _row_stride(width: int) -> int:
    return math.ceil(width / 8)


@dataclass
class BMLIcon:
    """A single icon from a .bml file."""
    name: str
    width: int
    height: int
    fg_color: tuple          # (R, G, B) — foreground (logo) colour
    pixel_data: bytes        # 1-bpp big-endian rows; 1=bg(white), 0=fg

    # ---- pixel helpers ----

    @property
    def row_stride(self) -> int:
        return _row_stride(self.width)

    def get_pixel(self, x: int, y: int) -> bool:
        """Return True if the pixel at (x, y) is foreground (icon colour)."""
        stride = self.row_stride
        byte_idx = y * stride + x // 8
        bit_idx  = 7 - (x % 8)
        return not bool((self.pixel_data[byte_idx] >> bit_idx) & 1)

    def to_ascii(self, fg: str = '#', bg: str = '.') -> str:
        """Render as an ASCII art string (useful for debugging)."""
        rows = []
        for y in range(self.height):
            rows.append(''.join(fg if self.get_pixel(x, y) else bg
                                for x in range(self.width)))
        return '\n'.join(rows)

    # ---- serialisation ----

    def to_record_bytes(self) -> bytes:
        """Serialise this icon back to BML record format."""
        name_enc = self.name.encode('latin-1')[:20]
        meta_len = _NAME_FIELD - len(name_enc) - 1   # bytes after name\0
        if meta_len < 2:
            raise ValueError(f"Icon name {self.name!r} is too long (max 20 chars)")

        meta = bytearray(meta_len)
        struct.pack_into('<H', meta, meta_len - 2, len(self.pixel_data))
        if meta_len >= 3:
            meta[0], meta[1], meta[2] = self.fg_color

        hdr = (_MARKER
               + struct.pack('<HH', self.width, self.height)
               + b'\x01\x00\x01\x00\x01\x00\x00\x09'
               + b'\x00\x00\x00\x00')
        return hdr + name_enc + b'\x00' + bytes(meta) + self.pixel_data

    def __repr__(self) -> str:
        return (f"BMLIcon({self.name!r}, {self.width}×{self.height}, "
                f"fg={self.fg_color})")


class BMLFile:
    """
    A collection of icons loaded from (or to be written to) a .bml file.

    Usage::

        bml = BMLFile.load('Channels.bml')
        print(bml.names())          # ['ABC', 'CBS', ...]
        icon = bml['ABC']           # BMLIcon
        bml.save('output.bml')

        # Build a new BML from scratch
        bml2 = BMLFile()
        bml2.add_icon(my_icon)
        bml2.save('custom.bml')
    """

    def __init__(self):
        self.icons: List[BMLIcon] = []

    # ---- loading ----

    @classmethod
    def load(cls, path: str) -> 'BMLFile':
        """Load all icons from a .bml file."""
        with open(path, 'rb') as f:
            data = f.read()

        if data[:4] != _MAGIC:
            raise ValueError(f"Not a .bml file (bad magic): {path}")

        declared_count = struct.unpack_from('<H', data, 4)[0]
        obj = cls()
        pos = 12  # skip 12-byte file header

        for _ in range(declared_count):
            # Find next marker
            pos = data.find(_MARKER, pos)
            if pos == -1:
                break
            if pos + 6 > len(data):
                break

            w = struct.unpack_from('<H', data, pos + 2)[0]
            h = struct.unpack_from('<H', data, pos + 4)[0]
            if not (1 <= w <= 255 and 1 <= h <= 255):
                pos += 1
                continue

            pix_len = h * _row_stride(w)
            rec_end = pos + _RECORD_HDR + pix_len
            if rec_end > len(data):
                break

            # Decode name
            try:
                null_pos = data.index(b'\x00', pos + _FIXED_HDR,
                                      pos + _FIXED_HDR + _NAME_FIELD)
            except ValueError:
                pos = rec_end
                continue
            name = data[pos + _FIXED_HDR : null_pos].decode('latin-1')

            # Decode fg colour from meta (first 3 bytes after name\0)
            meta_start = null_pos + 1
            meta_end   = pos + _RECORD_HDR
            meta       = data[meta_start:meta_end]
            fg = (0, 0, 0)
            if len(meta) >= 3:
                fg = (meta[0], meta[1], meta[2])

            pix = data[pos + _RECORD_HDR : rec_end]
            obj.icons.append(BMLIcon(name=name, width=w, height=h,
                                     fg_color=fg, pixel_data=pix))
            pos = rec_end

        return obj

    # ---- saving ----

    def save(self, path: str) -> None:
        """Write all icons to a .bml file."""
        records = [icon.to_record_bytes() for icon in self.icons]
        header  = (_MAGIC
                   + struct.pack('<H', len(records))
                   + b'\x01\x00'
                   + b'\x00\x00\x00\x00')
        with open(path, 'wb') as f:
            f.write(header + b''.join(records))

    # ---- icon management ----

    def add_icon(self, icon: BMLIcon) -> None:
        """Append an icon to this library."""
        self.icons.append(icon)

    def names(self) -> List[str]:
        """Return a list of all icon names."""
        return [icon.name for icon in self.icons]

    def get(self, name: str) -> Optional[BMLIcon]:
        """Return the icon with the given name, or None if not found."""
        for icon in self.icons:
            if icon.name == name:
                return icon
        return None

    # ---- dict-like access ----

    def __getitem__(self, name: str) -> BMLIcon:
        icon = self.get(name)
        if icon is None:
            raise KeyError(f"Icon {name!r} not in BML file. "
                           f"Available: {self.names()}")
        return icon

    def __contains__(self, name: str) -> bool:
        return self.get(name) is not None

    def __len__(self) -> int:
        return len(self.icons)

    def __iter__(self):
        return iter(self.icons)

    def __repr__(self) -> str:
        return f"BMLFile({len(self.icons)} icons: {self.names()})"
