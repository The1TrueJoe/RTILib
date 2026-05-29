"""
rti_lib/tools/stream_diff.py

Universal TLV stream diff and inspection tool for RTI .rti project files.

Decodes any two .rti files and prints a field-by-field comparison of their
device streams, annotating every record with its known field name from the
field registry (rti_lib.core.fields).  Identical records are collapsed into
a summary line; only differences are printed in full.

Intended use: open two .rti files that differ by exactly one change in RTI
Integration Designer, run the diff, and identify which stream position and
tag correspond to that setting.

----

Command-line usage::

    python -m rti_lib.tools.stream_diff file_a.rti file_b.rti
    python -m rti_lib.tools.stream_diff file_a.rti file_b.rti --slot 3
    python -m rti_lib.tools.stream_diff file_a.rti file_b.rti --all

Print a full annotated decode of a single stream::

    python -m rti_lib.tools.stream_diff --print file.rti
    python -m rti_lib.tools.stream_diff --print file.rti --slot 0

Python API::

    from rti_lib.tools import diff_files, print_stream

    diff_files('before.rti', 'after.rti')
    diff_files('before.rti', 'after.rti', slot=3, print_all=True)
    print_stream('project.rti', slot=0)
"""

import argparse
import sys
from typing import List, Optional, Tuple

from rti_lib.core import cfb as _cfb
from rti_lib.core import tlv as _tlv
from rti_lib.core.models import STREAM_DEVICE_PREFIX, DEVICE_TYPE_NAMES
from rti_lib.core.fields import STREAM_FIELDS, FieldDef, field_label

# Width of the field-name column in output.
_NAME_COL = 28
# Max bytes to show inline for BLOB / GUID values.
_MAX_BLOB_DISPLAY = 16


# ---------------------------------------------------------------------------
# Value formatting helpers
# ---------------------------------------------------------------------------

def _fmt_value(node: _tlv.TLVNode, field: Optional[FieldDef] = None) -> str:
    """Return a human-readable string for a TLV node's decoded value."""
    v = node.value
    tc = node.type_code

    if tc == _tlv.T_BYTE:
        s = str(v)
        if field and v in field.known_values:
            s += f'  ({field.known_values[v]})'
    elif tc == _tlv.T_U16:
        s = str(v)
    elif tc == _tlv.T_I32:
        s = str(v)
    elif tc in (_tlv.T_BLOB, _tlv.T_GUID):
        if isinstance(v, bytes):
            if len(v) <= _MAX_BLOB_DISPLAY:
                s = v.hex()
            else:
                s = v[:_MAX_BLOB_DISPLAY].hex() + f'...  ({len(v)} bytes)'
        else:
            s = repr(v)
    elif tc == _tlv.T_VARSTR:
        if isinstance(v, tuple):
            idx, text = v
            s = f'[{idx}] {text!r}'
        elif isinstance(v, str):
            s = repr(v)
        else:
            s = repr(v)
    elif tc == _tlv.T_CONTAINER:
        n_children = len(node.children) if node.children else '?'
        size = len(v) if isinstance(v, bytes) else '?'
        s = f'<CONTAINER {size} bytes, {n_children} children>'
    else:
        s = repr(v)

    return s


def _values_equal(a: _tlv.TLVNode, b: _tlv.TLVNode) -> bool:
    """Return True if two TLV nodes carry the same value."""
    if a.type_code != b.type_code:
        return False
    if a.type_code == _tlv.T_CONTAINER:
        # Compare raw container bytes (not recursively decoded).
        return a.raw_value == b.raw_value
    return a.value == b.value


# ---------------------------------------------------------------------------
# File loading
# ---------------------------------------------------------------------------

def _list_device_slots(cfb_parser) -> List[Tuple[int, str]]:
    """Return [(slot_index, stream_name), ...] for all device data streams."""
    slots = []
    for name, _size in cfb_parser.list_streams():
        if name.startswith(STREAM_DEVICE_PREFIX):
            suffix = name[len(STREAM_DEVICE_PREFIX):]
            try:
                idx = int(suffix)
            except ValueError:
                continue
            slots.append((idx, name))
    return sorted(slots)


def _load_nodes(cfb_parser, stream_name: str) -> List[_tlv.TLVNode]:
    """Decode a device data stream and return its top-level TLV node list."""
    data = cfb_parser.read_stream(stream_name)
    return _tlv.decode(data)


def _device_type_label(nodes: List[_tlv.TLVNode]) -> str:
    """Return a label like 'U2 (0x1D)' from the first node of a stream."""
    if nodes:
        n = nodes[0]
        if n.type_code == _tlv.T_BYTE:
            name = DEVICE_TYPE_NAMES.get(n.value, 'Unknown')
            return f'{name} (0x{n.value:02X})'
    return 'unknown device type'


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def print_stream(path: str, slot: int = 0, max_nodes: int = None) -> None:
    """
    Decode and print a full annotated listing of one device data stream.

    Parameters
    ----------
    path      : Path to the .rti file.
    slot      : Device slot index (0 = first stream).
    max_nodes : If given, stop after this many top-level nodes.
    """
    cfb_parser = _cfb.load(path)
    stream_name = f'{STREAM_DEVICE_PREFIX}{slot:04d}'
    nodes = _load_nodes(cfb_parser, stream_name)
    dtype = _device_type_label(nodes)

    print(f'Stream: {stream_name}  device={dtype}  total={len(nodes)} nodes')
    print(f'{"pos":>5}  {"tag":>5}  {"type":<10}  {"field name":<{_NAME_COL}}  value')
    print('-' * 100)

    limit = max_nodes if max_nodes is not None else len(nodes)
    for pos, node in enumerate(nodes[:limit]):
        fdef = STREAM_FIELDS[pos] if pos < len(STREAM_FIELDS) else None
        fname = fdef.name if fdef else f'pos_{pos}'
        tname = node.type_name()
        val_s = _fmt_value(node, fdef)
        print(f'{pos:>5}  0x{node.tag:02X}   {tname:<10}  {fname:<{_NAME_COL}}  {val_s}')


def diff_files(path_a: str, path_b: str,
               slot: int = None,
               print_all: bool = False) -> None:
    """
    Print a field-by-field diff between two .rti files.

    Parameters
    ----------
    path_a, path_b : Paths to the two .rti files to compare.
    slot           : If given, compare only that device slot index.
                     If None, all slots present in both files are compared.
    print_all      : If True, print identical records too (verbose mode).
    """
    cfb_a = _cfb.load(path_a)
    cfb_b = _cfb.load(path_b)

    slots_a = dict(_list_device_slots(cfb_a))
    slots_b = dict(_list_device_slots(cfb_b))

    if slot is not None:
        compare_slots = [slot] if slot in slots_a and slot in slots_b else []
        only_in_a = [slot] if slot in slots_a and slot not in slots_b else []
        only_in_b = [slot] if slot in slots_b and slot not in slots_a else []
    else:
        all_slots = sorted(set(slots_a) | set(slots_b))
        compare_slots = [s for s in all_slots if s in slots_a and s in slots_b]
        only_in_a = [s for s in all_slots if s in slots_a and s not in slots_b]
        only_in_b = [s for s in all_slots if s in slots_b and s not in slots_a]

    print(f'RTI Stream Diff')
    print(f'  A: {path_a}')
    print(f'  B: {path_b}')

    if only_in_a:
        print(f'  Slots only in A: {only_in_a}')
    if only_in_b:
        print(f'  Slots only in B: {only_in_b}')
    print()

    for s in compare_slots:
        sname = f'{STREAM_DEVICE_PREFIX}{s:04d}'
        nodes_a = _load_nodes(cfb_a, sname)
        nodes_b = _load_nodes(cfb_b, sname)
        dtype_a = _device_type_label(nodes_a)
        dtype_b = _device_type_label(nodes_b)
        same_type = dtype_a == dtype_b

        print('=' * 100)
        print(f'Slot {s:04d}  A={dtype_a}  B={dtype_b}')
        print(f'{"pos":>5}  {"tag":>5}  {"type":<10}  {"field name":<{_NAME_COL}}  A value  ->  B value')
        print('-' * 100)

        n_same = 0
        n_diff = 0
        run_start = None   # start of a run of identical records

        def _flush_run(up_to: int):
            nonlocal n_same, run_start
            if run_start is not None and up_to > run_start:
                count = up_to - run_start
                if print_all:
                    pass   # already printed individually
                else:
                    print(f'      ... {count} identical record(s) [{run_start}..{up_to-1}]')
                run_start = None
            n_same += 0  # already counted inline

        max_pos = max(len(nodes_a), len(nodes_b))
        last_same_run_start = None
        same_run_count = 0

        for pos in range(max_pos):
            na = nodes_a[pos] if pos < len(nodes_a) else None
            nb = nodes_b[pos] if pos < len(nodes_b) else None

            fdef = STREAM_FIELDS[pos] if pos < len(STREAM_FIELDS) else None
            fname = fdef.name if fdef else f'pos_{pos}'

            if na is None:
                # B has extra node
                val_b = _fmt_value(nb, fdef)
                tname = nb.type_name()
                if same_run_count:
                    _print_same_run(last_same_run_start, same_run_count, print_all)
                    same_run_count = 0
                print(f'{pos:>5}  0x{nb.tag:02X}   {tname:<10}  {fname:<{_NAME_COL}}  <missing>  ->  {val_b}')
                n_diff += 1
                continue

            if nb is None:
                # A has extra node
                val_a = _fmt_value(na, fdef)
                tname = na.type_name()
                if same_run_count:
                    _print_same_run(last_same_run_start, same_run_count, print_all)
                    same_run_count = 0
                print(f'{pos:>5}  0x{na.tag:02X}   {tname:<10}  {fname:<{_NAME_COL}}  {val_a}  ->  <missing>')
                n_diff += 1
                continue

            equal = _values_equal(na, nb)
            tname = na.type_name()

            if equal:
                if print_all:
                    val_a = _fmt_value(na, fdef)
                    print(f'{pos:>5}  0x{na.tag:02X}   {tname:<10}  {fname:<{_NAME_COL}}  {val_a}')
                else:
                    if same_run_count == 0:
                        last_same_run_start = pos
                    same_run_count += 1
                n_same += 1
            else:
                if same_run_count:
                    _print_same_run(last_same_run_start, same_run_count, print_all)
                    same_run_count = 0
                val_a = _fmt_value(na, fdef)
                val_b = _fmt_value(nb, fdef)
                print(f'{pos:>5}  0x{na.tag:02X}   {tname:<10}  {fname:<{_NAME_COL}}  {val_a}')
                print(f'       {"":>5}   {"":10}  {"":>{_NAME_COL}}  -> {val_b}')
                n_diff += 1

        if same_run_count:
            _print_same_run(last_same_run_start, same_run_count, print_all)

        print()
        print(f'  Summary: {n_diff} difference(s), {n_same} identical record(s)')
        print()


def _print_same_run(start: int, count: int, verbose: bool) -> None:
    if not verbose and count > 0:
        end = start + count - 1
        if count == 1:
            print(f'      ... [{start}] identical')
        else:
            print(f'      ... [{start}..{end}] {count} identical records')


# ---------------------------------------------------------------------------
# Command-line entry point
# ---------------------------------------------------------------------------

def _main():
    ap = argparse.ArgumentParser(
        prog='python -m rti_lib.tools.stream_diff',
        description='Diff or inspect RTI .rti device streams.',
    )
    ap.add_argument('files', nargs='+', metavar='FILE',
                    help='.rti file(s) — one file for --print, two for diff')
    ap.add_argument('--slot', type=int, default=None,
                    help='Compare / print only this device slot index')
    ap.add_argument('--all', dest='print_all', action='store_true',
                    help='Print identical records too (verbose diff)')
    ap.add_argument('--print', dest='do_print', action='store_true',
                    help='Print a full annotated decode of one stream')
    args = ap.parse_args()

    if args.do_print:
        if len(args.files) != 1:
            ap.error('--print requires exactly one FILE')
        print_stream(args.files[0], slot=args.slot or 0)
    else:
        if len(args.files) != 2:
            ap.error('diff requires exactly two FILEs')
        diff_files(args.files[0], args.files[1],
                   slot=args.slot, print_all=args.print_all)


if __name__ == '__main__':
    _main()
