"""
OLE2 Compound File Binary (CFB) parser for RTI .rti project files.
Pure Python, no external dependencies.

RTI .rti files are standard OLE2/CFB containers. This parser reads the
directory tree and extracts named streams as raw bytes.

Reference: [MS-CFB] v20211006
"""

import struct

MAGIC = b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1'
FAT_FREESECT = 0xFFFFFFFF
FAT_ENDOFCHAIN = 0xFFFFFFFE
FAT_FATSECT = 0xFFFFFFFD
FAT_DIFSECT = 0xFFFFFFFC

SECT_FREE = FAT_FREESECT
SECT_EOC = FAT_ENDOFCHAIN


class CFBStream:
    """Represents a stream entry in the CFB directory."""
    def __init__(self, name, start_sect, size, is_mini=False):
        self.name = name
        self.start_sect = start_sect
        self.size = size
        self.is_mini = is_mini

    def __repr__(self):
        return f"CFBStream({self.name!r}, size={self.size}, mini={self.is_mini})"


class CFBParser:
    """Parse an OLE2 Compound File Binary (.rti, .doc, etc.)."""

    def __init__(self, data: bytes):
        self.data = data
        self._parse_header()
        self._build_fat()
        self._build_directory()
        self._build_mini_fat()

    def _parse_header(self):
        d = self.data
        if d[:8] != MAGIC:
            raise ValueError("Not a valid OLE2 CFB file (bad magic)")

        # Header is 512 bytes
        # Minor version at 0x18, major at 0x1A
        self.minor_ver = struct.unpack_from('<H', d, 0x18)[0]
        self.major_ver = struct.unpack_from('<H', d, 0x1A)[0]
        byte_order = struct.unpack_from('<H', d, 0x1C)[0]
        if byte_order != 0xFFFE:
            raise ValueError(f"Unexpected byte order mark: {byte_order:#06x}")

        sector_size_exp = struct.unpack_from('<H', d, 0x1E)[0]
        mini_sector_size_exp = struct.unpack_from('<H', d, 0x20)[0]
        self.sector_size = 1 << sector_size_exp       # typically 512
        self.mini_sector_size = 1 << mini_sector_size_exp  # typically 64

        self.num_fat_sectors = struct.unpack_from('<I', d, 0x2C)[0]
        self.root_dir_sect = struct.unpack_from('<I', d, 0x30)[0]
        self.mini_stream_cutoff = struct.unpack_from('<I', d, 0x38)[0]  # typically 4096
        self.first_mini_fat_sect = struct.unpack_from('<I', d, 0x3C)[0]
        self.num_mini_fat_sectors = struct.unpack_from('<I', d, 0x40)[0]
        self.first_difat_sect = struct.unpack_from('<I', d, 0x44)[0]
        self.num_difat_sectors = struct.unpack_from('<I', d, 0x48)[0]

        # First 109 DIFAT entries in header (at 0x4C)
        self.difat = []
        for i in range(109):
            val = struct.unpack_from('<I', d, 0x4C + i * 4)[0]
            if val == FAT_FREESECT:
                break
            self.difat.append(val)

        # Append additional DIFAT sectors if any
        next_difat = self.first_difat_sect
        while next_difat not in (FAT_FREESECT, FAT_ENDOFCHAIN, FAT_FATSECT, FAT_DIFSECT):
            sect_data = self._read_sector(next_difat)
            entries_per_difat = (self.sector_size // 4) - 1
            for i in range(entries_per_difat):
                val = struct.unpack_from('<I', sect_data, i * 4)[0]
                if val == FAT_FREESECT:
                    break
                self.difat.append(val)
            next_difat = struct.unpack_from('<I', sect_data, self.sector_size - 4)[0]

    def _sector_offset(self, sect_num: int) -> int:
        """Byte offset of sector N in the file (sector 0 starts at byte 512)."""
        return 512 + sect_num * self.sector_size

    def _read_sector(self, sect_num: int) -> bytes:
        off = self._sector_offset(sect_num)
        return self.data[off: off + self.sector_size]

    def _build_fat(self):
        """Build the full FAT (file allocation table) as a list of uint32."""
        fat_entries = []
        for fat_sect in self.difat:
            sect_data = self._read_sector(fat_sect)
            count = self.sector_size // 4
            for i in range(count):
                fat_entries.append(struct.unpack_from('<I', sect_data, i * 4)[0])
        self.fat = fat_entries

    def _follow_chain(self, start_sect: int) -> list:
        """Follow FAT chain from start_sect, return list of sector numbers."""
        chain = []
        current = start_sect
        seen = set()
        while current not in (FAT_FREESECT, FAT_ENDOFCHAIN, FAT_FATSECT, FAT_DIFSECT):
            if current in seen or current >= len(self.fat):
                break
            seen.add(current)
            chain.append(current)
            current = self.fat[current]
        return chain

    def _build_directory(self):
        """Read all directory entries from the root directory chain."""
        chain = self._follow_chain(self.root_dir_sect)
        dir_data = b''.join(self._read_sector(s) for s in chain)

        self.dir_entries = []
        entry_size = 128
        for i in range(len(dir_data) // entry_size):
            off = i * entry_size
            entry = dir_data[off: off + entry_size]
            name_len = struct.unpack_from('<H', entry, 0x40)[0]
            if name_len < 2:
                continue
            name = entry[:name_len - 2].decode('utf-16-le', errors='replace')
            obj_type = entry[0x42]   # 0=unknown/free, 1=storage, 2=stream, 5=root
            start_sect = struct.unpack_from('<I', entry, 0x74)[0]
            size = struct.unpack_from('<I', entry, 0x78)[0]
            self.dir_entries.append({
                'name': name,
                'type': obj_type,
                'start_sect': start_sect,
                'size': size,
                'index': i,
            })

        # The root entry (index 0) holds the mini stream
        if self.dir_entries:
            root = self.dir_entries[0]
            self.mini_stream_start = root['start_sect']
            self.mini_stream_size = root['size']

    def _build_mini_fat(self):
        """Build the mini FAT."""
        if self.first_mini_fat_sect in (FAT_FREESECT, FAT_ENDOFCHAIN):
            self.mini_fat = []
            self.mini_stream_data = b''
            return

        chain = self._follow_chain(self.first_mini_fat_sect)
        mini_fat_data = b''.join(self._read_sector(s) for s in chain)
        count = len(mini_fat_data) // 4
        self.mini_fat = [struct.unpack_from('<I', mini_fat_data, i * 4)[0] for i in range(count)]

        # Read the mini stream container
        if self.mini_stream_start not in (FAT_FREESECT, FAT_ENDOFCHAIN):
            ms_chain = self._follow_chain(self.mini_stream_start)
            self.mini_stream_data = b''.join(self._read_sector(s) for s in ms_chain)
        else:
            self.mini_stream_data = b''

    def _follow_mini_chain(self, start_sect: int) -> list:
        chain = []
        current = start_sect
        seen = set()
        while current not in (FAT_FREESECT, FAT_ENDOFCHAIN, FAT_FATSECT, FAT_DIFSECT):
            if current in seen or current >= len(self.mini_fat):
                break
            seen.add(current)
            chain.append(current)
            current = self.mini_fat[current]
        return chain

    def read_stream(self, name: str) -> bytes:
        """Read a named stream by name (exact match). Returns raw bytes."""
        for entry in self.dir_entries:
            if entry['type'] == 2 and entry['name'] == name:
                return self._read_stream_entry(entry)
        raise KeyError(f"Stream not found: {name!r}")

    def _read_stream_entry(self, entry: dict) -> bytes:
        size = entry['size']
        start = entry['start_sect']
        if size < self.mini_stream_cutoff:
            # Mini stream
            chain = self._follow_mini_chain(start)
            raw = b''.join(
                self.mini_stream_data[s * self.mini_sector_size: (s + 1) * self.mini_sector_size]
                for s in chain
            )
            return raw[:size]
        else:
            # Regular stream
            chain = self._follow_chain(start)
            raw = b''.join(self._read_sector(s) for s in chain)
            return raw[:size]

    def list_streams(self) -> list:
        """Return list of (name, size) for all stream entries."""
        return [(e['name'], e['size']) for e in self.dir_entries if e['type'] == 2]

    def get_all_streams(self) -> dict:
        """Return dict of stream_name -> bytes for all streams."""
        result = {}
        for entry in self.dir_entries:
            if entry['type'] == 2:
                result[entry['name']] = self._read_stream_entry(entry)
        return result


def load(path: str) -> CFBParser:
    """Load a CFB file from disk and return a CFBParser instance."""
    with open(path, 'rb') as f:
        data = f.read()
    return CFBParser(data)
