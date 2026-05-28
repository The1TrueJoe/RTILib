"""
cfb_writer.py — Minimal OLE2 Compound File Binary (v3) writer.
Pure Python, no external dependencies.

Generates a valid v3 CFB file from a flat dict of stream_name -> bytes.
All streams are stored as direct children of the root storage (no sub-storages).
Streams < 4096 bytes are stored in the mini-stream.
Streams >= 4096 bytes are stored in regular 512-byte sectors.

Reference: [MS-CFB] v20211006
"""

import struct

SECTOR_SIZE        = 512
MINI_SECTOR_SIZE   = 64
MINI_STREAM_CUTOFF = 4096

FAT_FREE = 0xFFFFFFFF   # FREESECT  — sector is unused
FAT_EOC  = 0xFFFFFFFE   # ENDOFCHAIN — end of a chain
FAT_FAT  = 0xFFFFFFFD   # FATSECT   — sector contains FAT data
# Mini-FAT sectors are NOT special-marked in the regular FAT; they chain with EOC.


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ceil_div(a: int, b: int) -> int:
    return (a + b - 1) // b


def _pad(data: bytes, alignment: int) -> bytes:
    n = (-len(data)) % alignment
    return data + b'\x00' * n if n else data


def _pack_u32(v: int) -> bytes:
    return struct.pack('<I', v & 0xFFFFFFFF)


def _rti_name_key(name: str):
    """
    OLE2 directory-entry comparison key: (name_length, uppercase_name).
    Shorter names sort lower; equal-length names sort lexicographically
    case-insensitive. This matches the [MS-CFB] directory ordering rules.
    """
    return (len(name), name.upper())


def _build_bst(sorted_names: list) -> dict:
    """
    Build a balanced BST from a list already sorted by _rti_name_key.
    Returns dict: name -> (left_child_name_or_None, right_child_name_or_None)
    where left/right are the ROOTS of the respective subtrees.

    Uses median-split, which produces a height-balanced binary search tree.
    All nodes are coloured 'black' in the directory entry; while this is not
    a strict red-black tree, it is valid for searching (most OLE2 readers
    simply traverse left/right links without validating RB properties).
    """
    if not sorted_names:
        return {}
    mid   = len(sorted_names) // 2
    root  = sorted_names[mid]
    left  = sorted_names[:mid]
    right = sorted_names[mid + 1:]
    result = {
        root: (
            left[len(left) // 2]   if left  else None,
            right[len(right) // 2] if right else None,
        )
    }
    result.update(_build_bst(left))
    result.update(_build_bst(right))
    return result


def _make_dir_entry(
    name: str,
    obj_type: int,
    color: int,
    left_sib: int,
    right_sib: int,
    child: int,
    start_sect: int,
    size: int,
) -> bytes:
    """Build a 128-byte OLE2 directory entry."""
    FREE = 0xFFFFFFFF
    name_enc = (name + '\x00').encode('utf-16-le')
    if len(name_enc) > 64:
        name_enc = name_enc[:64]
    name_len = len(name_enc)  # includes null terminator, in bytes

    entry = bytearray(128)
    entry[0:len(name_enc)] = name_enc
    struct.pack_into('<H', entry, 0x40, name_len)
    entry[0x42] = obj_type   # 0=free, 1=storage, 2=stream, 5=root
    entry[0x43] = color      # 0=red, 1=black
    struct.pack_into('<I', entry, 0x44, left_sib  & 0xFFFFFFFF)
    struct.pack_into('<I', entry, 0x48, right_sib & 0xFFFFFFFF)
    struct.pack_into('<I', entry, 0x4C, child     & 0xFFFFFFFF)
    # CLSID (0x50–0x5F): zeros
    # State flags (0x60–0x63): 0
    # Created / Modified timestamps (0x64–0x73): 0
    struct.pack_into('<I', entry, 0x74, start_sect & 0xFFFFFFFF)
    struct.pack_into('<I', entry, 0x78, size       & 0xFFFFFFFF)
    return bytes(entry)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_cfb(streams: dict, stream_order: list = None) -> bytes:
    """
    Serialize a dict of stream_name -> bytes as an OLE2 CFB v3 file.

    Parameters
    ----------
    streams      : dict mapping stream name (str) to content (bytes).
    stream_order : optional list of stream names controlling the order of
                   directory entries (e.g., to match an original file).
                   If None, entries are written in OLE2 sort order.
                   The BST links are always derived from OLE2 sort order
                   regardless of stream_order, so searching works correctly.

    Returns
    -------
    bytes — the complete CFB file.
    """
    FREE = 0xFFFFFFFF

    all_names = list(streams.keys())

    if stream_order is not None:
        assert set(stream_order) == set(all_names), (
            "stream_order must contain exactly the same names as streams"
        )
        index_order = stream_order
    else:
        index_order = sorted(all_names, key=_rti_name_key)

    # OLE2-sorted names for BST construction
    rti_sorted = sorted(all_names, key=_rti_name_key)

    # Directory entry index: entry 0 = Root Entry, entries 1..N = streams
    name_to_idx = {name: i + 1 for i, name in enumerate(index_order)}

    # BST links (keys = stream names, values = (left_subtree_root, right_subtree_root))
    bst = _build_bst(rti_sorted)
    bst_root_name = rti_sorted[len(rti_sorted) // 2] if rti_sorted else None

    # ---- Classify: regular (>= cutoff) vs mini (< cutoff) ----------------
    regular = [(n, streams[n]) for n in index_order if len(streams[n]) >= MINI_STREAM_CUTOFF]
    mini    = [(n, streams[n]) for n in index_order if len(streams[n]) <  MINI_STREAM_CUTOFF]

    # ---- Build mini-stream container data ---------------------------------
    mini_start_msect = {}   # name -> first mini-sector number
    mini_cursor      = 0
    mini_parts       = []
    for name, data in mini:
        mini_start_msect[name] = mini_cursor
        padded = _pad(data, MINI_SECTOR_SIZE)
        mini_parts.append(padded)
        mini_cursor += len(padded) // MINI_SECTOR_SIZE
    mini_data         = b''.join(mini_parts)
    total_mini_sects  = mini_cursor

    # The mini-stream container is stored in the root entry's regular-sector chain
    mini_container       = _pad(mini_data, SECTOR_SIZE) if mini_data else b''
    mini_container_sects = len(mini_container) // SECTOR_SIZE  # regular sectors needed

    # ---- Sector counts ----------------------------------------------------
    mini_fat_entries_per_sect = SECTOR_SIZE // 4
    mini_fat_sects = (
        _ceil_div(total_mini_sects, mini_fat_entries_per_sect)
        if total_mini_sects > 0 else 0
    )

    reg_sect_counts = {name: _ceil_div(len(data), SECTOR_SIZE) for name, data in regular}
    total_reg_data_sects = sum(reg_sect_counts.values())

    entries_per_dir_sect = SECTOR_SIZE // 128
    n_dir_entries = 1 + len(streams)   # root + all streams
    dir_sects     = _ceil_div(n_dir_entries, entries_per_dir_sect)

    # Iterate to find how many FAT sectors are needed (circular dependency)
    fat_sects = 1
    for _ in range(10):
        total = dir_sects + fat_sects + mini_fat_sects + mini_container_sects + total_reg_data_sects
        needed = _ceil_div(total, SECTOR_SIZE // 4)
        if needed <= fat_sects:
            break
        fat_sects = needed
    assert fat_sects <= 109, "File too large: DIFAT chain would be needed (not implemented)"

    # ---- Assign sector numbers (layout: dir | fat | minifat | mini-container | streams) ---
    cur = 0
    dir_start = cur;  cur += dir_sects
    fat_start = cur;  cur += fat_sects

    if mini_fat_sects > 0:
        mini_fat_start      = cur; cur += mini_fat_sects
        mini_fat_first_sect = mini_fat_start
    else:
        mini_fat_start      = FAT_EOC
        mini_fat_first_sect = FAT_EOC

    if mini_container_sects > 0:
        mini_cont_start       = cur
        mini_cont_sect_list   = list(range(cur, cur + mini_container_sects))
        cur += mini_container_sects
    else:
        mini_cont_start     = FAT_EOC
        mini_cont_sect_list = []

    reg_start_sect = {}
    for name, data in regular:
        reg_start_sect[name] = cur
        cur += reg_sect_counts[name]

    # ---- Build FAT --------------------------------------------------------
    fat_len = fat_sects * (SECTOR_SIZE // 4)
    fat = [FREE] * fat_len

    # Directory sector chain
    for i in range(dir_sects - 1):
        fat[dir_start + i] = dir_start + i + 1
    fat[dir_start + dir_sects - 1] = FAT_EOC

    # FAT sectors (self-referential)
    for i in range(fat_sects):
        fat[fat_start + i] = FAT_FAT

    # Mini-FAT sector chain (through regular FAT)
    if mini_fat_sects > 0:
        for i in range(mini_fat_sects - 1):
            fat[mini_fat_start + i] = mini_fat_start + i + 1
        fat[mini_fat_start + mini_fat_sects - 1] = FAT_EOC

    # Mini-stream container chain
    for i, s in enumerate(mini_cont_sect_list):
        fat[s] = (mini_cont_sect_list[i + 1]
                  if i < len(mini_cont_sect_list) - 1 else FAT_EOC)

    # Regular stream chains
    for name, data in regular:
        start = reg_start_sect[name]
        count = reg_sect_counts[name]
        for i in range(count - 1):
            fat[start + i] = start + i + 1
        fat[start + count - 1] = FAT_EOC

    fat_data = b''.join(_pack_u32(v) for v in fat)

    # ---- Build mini-FAT ---------------------------------------------------
    if total_mini_sects > 0:
        mf_len   = mini_fat_sects * (SECTOR_SIZE // 4)
        mini_fat = [FREE] * mf_len
        cursor   = 0
        for name, data in mini:
            n = _ceil_div(len(data), MINI_SECTOR_SIZE)
            for i in range(n - 1):
                mini_fat[cursor + i] = cursor + i + 1
            mini_fat[cursor + n - 1] = FAT_EOC
            cursor += n
        mini_fat_data = b''.join(_pack_u32(v) for v in mini_fat)
    else:
        mini_fat_data = b''

    # ---- Build directory entries ------------------------------------------
    def get_idx(name_or_none):
        return name_to_idx[name_or_none] if name_or_none is not None else FREE

    root_child_idx = get_idx(bst_root_name) if bst_root_name else FREE

    dir_entry_list = [_make_dir_entry(
        name='Root Entry', obj_type=5, color=1,
        left_sib=FREE, right_sib=FREE, child=root_child_idx,
        start_sect=mini_cont_start,
        size=len(mini_data),
    )]

    for name in index_order:
        data = streams[name]
        left_name, right_name = bst.get(name, (None, None))

        if len(data) < MINI_STREAM_CUTOFF:
            start = mini_start_msect[name]
        else:
            start = reg_start_sect[name]

        dir_entry_list.append(_make_dir_entry(
            name=name, obj_type=2, color=1,
            left_sib=get_idx(left_name),
            right_sib=get_idx(right_name),
            child=FREE,
            start_sect=start,
            size=len(data),
        ))

    # Pad directory to fill complete sectors with free entries
    free_entry = _make_dir_entry('', 0, 1, FREE, FREE, FREE, 0, 0)
    while len(dir_entry_list) % entries_per_dir_sect != 0:
        dir_entry_list.append(free_entry)
    dir_data = b''.join(dir_entry_list)

    # ---- Build file header (512 bytes, precedes sector 0) -----------------
    header = bytearray(512)
    header[0:8] = b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1'  # OLE2 magic
    # CLSID at 0x08–0x17: all zeros
    struct.pack_into('<H', header, 0x18, 0x003E)          # minor version
    struct.pack_into('<H', header, 0x1A, 0x0003)          # major version (v3)
    struct.pack_into('<H', header, 0x1C, 0xFFFE)          # byte order (LE)
    struct.pack_into('<H', header, 0x1E, 9)               # sector size = 2^9 = 512
    struct.pack_into('<H', header, 0x20, 6)               # mini-sector size = 2^6 = 64
    # 0x22–0x27: reserved (zeros)
    struct.pack_into('<I', header, 0x28, 0)               # dir sector count (0 for v3)
    struct.pack_into('<I', header, 0x2C, fat_sects)
    struct.pack_into('<I', header, 0x30, dir_start)
    struct.pack_into('<I', header, 0x34, 0)               # transaction signature
    struct.pack_into('<I', header, 0x38, MINI_STREAM_CUTOFF)
    struct.pack_into('<I', header, 0x3C, mini_fat_first_sect)
    struct.pack_into('<I', header, 0x40, mini_fat_sects)
    struct.pack_into('<I', header, 0x44, FAT_EOC)         # first DIFAT sector
    struct.pack_into('<I', header, 0x48, 0)               # DIFAT sector count
    # First 109 DIFAT entries at 0x4C (FAT sector locations)
    for i in range(fat_sects):
        struct.pack_into('<I', header, 0x4C + i * 4, fat_start + i)
    for i in range(fat_sects, 109):
        struct.pack_into('<I', header, 0x4C + i * 4, FREE)

    # ---- Regular stream data (in index_order, each padded to SECTOR_SIZE) -
    regular_data = b''.join(_pad(data, SECTOR_SIZE) for _, data in regular)

    # ---- Assemble final file ----------------------------------------------
    # Sector layout: [dir_sects][fat_sects][mini_fat_sects][mini_container][regular_data]
    return (
        bytes(header)
        + dir_data
        + fat_data
        + mini_fat_data
        + mini_container
        + regular_data
    )
