"""
rti_lib/assets/icon_library.py

Reads RTI icon-library .rtitemplate files (Channel Icons style).

These templates are OLE2/CFB containers holding:
  - RTIBitmapIndex  — UTF-8 XML listing every image by name, with up/down
                      states pointing to PNG stream names
  - IMAGE######.png — individual PNG streams (one per state per image)

Usage
-----
    from rti_lib.assets import IconLibrary

    lib = IconLibrary.load(r'C:\\...\\Channel Icons - TV.rtitemplate')
    print(lib.name)           # "Channel Icons - TV"
    for entry in lib.entries: # ImageEntry objects
        print(entry.name, entry.up_stream, entry.down_stream,
              entry.width, entry.height)

    png_bytes = lib.get_png('ABC')          # up state by default
    png_bytes = lib.get_png('ABC', 'down')
"""

from __future__ import annotations
import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional
from rti_lib.core import cfb as cfb_mod


@dataclass
class ImageEntry:
    name: str
    up_stream: str
    down_stream: str
    width: int
    height: int


class IconLibrary:
    """
    An RTI icon-library template (Channel Icons style).

    Attributes
    ----------
    name     : Library name from the XML, e.g. "Channel Icons - TV".
    entries  : List of ImageEntry objects in XML order.
    path     : Source file path (may be None if constructed from bytes).
    """

    def __init__(self, name: str, entries: list[ImageEntry],
                 _cfb: object, path: Optional[str] = None):
        self.name = name
        self.entries = entries
        self._cfb = _cfb
        self.path = path
        # Build fast-lookup dict: lower-cased name → entry
        self._by_name = {e.name.lower(): e for e in entries}

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: str) -> 'IconLibrary':
        """Load an icon-library .rtitemplate file from *path*."""
        container = cfb_mod.load(path)
        return cls._from_cfb(container, path=path)

    @classmethod
    def from_bytes(cls, data: bytes) -> 'IconLibrary':
        """Load from raw bytes (e.g. if the template is already in memory)."""
        container = cfb_mod.load_bytes(data)
        return cls._from_cfb(container)

    @classmethod
    def _from_cfb(cls, container, path=None) -> 'IconLibrary':
        idx_raw = container.read_stream('RTIBitmapIndex')
        root = ET.fromstring(idx_raw.decode('utf-8'))

        lib_el = root.find('bitmaplibrary')
        if lib_el is None:
            raise ValueError('RTIBitmapIndex has no <bitmaplibrary> element')
        lib_name = lib_el.get('name', '')

        entries = []
        for img in lib_el.findall('image'):
            entries.append(ImageEntry(
                name=img.get('name', ''),
                up_stream=img.get('up', ''),
                down_stream=img.get('down', ''),
                width=int(img.get('width', 0)),
                height=int(img.get('height', 0)),
            ))

        return cls(lib_name, entries, container, path=path)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def find(self, name: str) -> Optional[ImageEntry]:
        """Return an ImageEntry by name (case-insensitive), or None."""
        return self._by_name.get(name.lower())

    def __len__(self):
        return len(self.entries)

    def __iter__(self):
        return iter(self.entries)

    # ------------------------------------------------------------------
    # Image data
    # ------------------------------------------------------------------

    def get_png(self, name: str, state: str = 'up') -> bytes:
        """
        Return raw PNG bytes for *name*.

        Parameters
        ----------
        name  : Image name as listed in the template (case-insensitive).
        state : 'up' (default, normal/released) or 'down' (pressed).

        Raises
        ------
        KeyError if the image name is not found.
        """
        entry = self._by_name.get(name.lower())
        if entry is None:
            raise KeyError(f'Image not found in {self.name!r}: {name!r}')
        stream_name = entry.up_stream if state == 'up' else entry.down_stream
        return self._cfb.read_stream(stream_name)

    def get_all_png(self, name: str) -> tuple[bytes, bytes]:
        """Return (up_png, down_png) for *name*."""
        return self.get_png(name, 'up'), self.get_png(name, 'down')

    # ------------------------------------------------------------------
    # Listing helpers
    # ------------------------------------------------------------------

    def names(self) -> list[str]:
        """Return all image names in index order."""
        return [e.name for e in self.entries]

    def summary(self) -> str:
        """One-line summary string."""
        return (f'IconLibrary({self.name!r}, {len(self.entries)} images, '
                f'{self.entries[0].width}x{self.entries[0].height}px)')
