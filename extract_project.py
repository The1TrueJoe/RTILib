#!/usr/bin/env python3
"""
extract_project.py — Parse and display the contents of an RTI .rti project file.

Usage:
    python extract_project.py <file.rti> [options]

Options:
    --json               Output as JSON instead of human-readable text
    --extract-streams DIR  Also write raw stream bytes to DIR/
    --tlv                Show full TLV decode of each device stream

Example:
    python extract_project.py Test2.rti
    python extract_project.py Test2.rti --json
    python extract_project.py Test2.rti --extract-streams ./streams/
"""

import sys
import os
import json
import struct
import argparse

# Allow running from repo root without installing the package
sys.path.insert(0, os.path.dirname(__file__))

from rti_lib import cfb, tlv, models


def _extract_text_value(value):
    """Return normalized text from a TLV value, or None if it is not usable text."""
    if isinstance(value, tuple):
        _, value = value

    if not isinstance(value, str):
        return None

    if not value:
        return None

    stripped = value.strip()
    if not stripped:
        return None

    printable = 0
    for char in stripped:
        if char.isprintable() and char not in ('\x00', '\ufffd'):
            printable += 1

    if printable / len(stripped) < 0.85:
        return None

    return stripped


def parse_device_stream_header(data: bytes) -> dict:
    """
    Decode the device type byte, model number, timeout, and format version
    from the first ~20 bytes of a Device Data Stream.

    Returns a dict with keys: device_type, model_number, timeout_sec, format_version
    """
    nodes = tlv.decode(data, offset=0, length=min(64, len(data)))

    result = {
        'device_type': None,
        'model_number': None,
        'timeout_sec': None,
        'format_version': None,
    }

    found_type_byte = False
    for node in nodes:
        if node.tag == 0x01 and node.type_code == tlv.T_BYTE and not found_type_byte:
            result['device_type'] = node.value
            found_type_byte = True
        elif node.tag == 0x03 and node.type_code == tlv.T_BYTE:
            result['model_number'] = node.value
        elif node.tag == 0x34 and node.type_code == tlv.T_I32:
            result['timeout_sec'] = node.value
        elif node.tag == 0x01 and node.type_code == tlv.T_U16:
            result['format_version'] = node.value

    return result


def parse_job_info(data: bytes) -> dict:
    """Decode the Job Info stream (TLV), keeping only plausible text metadata."""
    nodes = tlv.decode(data)
    result = {}
    opaque_varstr_tags = []
    empty_varstr_count = 0

    for node in nodes:
        if node.type_code == tlv.T_VARSTR:
            text = _extract_text_value(node.value)
            if text is None:
                if isinstance(node.value, str) and not node.value:
                    empty_varstr_count += 1
                else:
                    opaque_varstr_tags.append(node.tag)
                continue

            if node.tag == 0x01:
                result['project_name'] = text
            elif node.tag == 0x02:
                result['author'] = text
            elif node.tag == 0x03:
                result['created'] = text
            elif node.tag == 0x04:
                result['modified'] = text
            else:
                key = f'field_0x{node.tag:02X}'
                result[key] = text
        elif node.type_code == tlv.T_I32:
            result[f'i32_0x{node.tag:02X}'] = node.value
        elif node.type_code == tlv.T_BYTE:
            result[f'byte_0x{node.tag:02X}'] = node.value
        elif node.type_code == tlv.T_U16:
            result[f'u16_0x{node.tag:02X}'] = node.value

    if empty_varstr_count:
        result['_empty_varstr_count'] = empty_varstr_count
    if opaque_varstr_tags:
        result['_opaque_varstr_tags'] = [f'0x{tag:02X}' for tag in opaque_varstr_tags]

    return result


def parse_directory_v3(data: bytes) -> list:
    """
    Decode the RTI Data Directory V3 stream.
    Returns list of device slot dicts.

    Structure (derived from Test2.rti analysis):
      [0x00] magic = 0xBEEFF00D (LE)
      [0x04] version (LE uint32)
      [0x24] device_count (LE uint16)
      Device slots follow, each ~686 bytes:
        +0x00: unknown header bytes
        +0x03: type byte (01 XX pattern, XX = device type)
        +0x07: manufacturer name (UTF-16LE, 0x80 chars = 128 bytes)
        +0x87: model name (UTF-16LE, 0x80 chars = 128 bytes)
        +0x107: user-assigned name (UTF-16LE, 0x80 chars = 128 bytes)
    """
    if len(data) < 8:
        return []

    magic = struct.unpack_from('<I', data, 0)[0]
    if magic != models.DIR_MAGIC:
        return []

    version = struct.unpack_from('<I', data, 4)[0]

    if len(data) < 0x26:
        return []
    device_count = struct.unpack_from('<H', data, 0x24)[0]

    devices = []

    # Scan for device type pattern: look for manufacturer "Remote Technologies"
    # and extract nearby type byte
    # We use the known offsets from reverse engineering:
    #   Slot 0: type at 0x27, manufacturer at 0x2F, model at 0xAF, name at 0x12F
    #   Slot 1: type at 0x2D5, manufacturer at 0x2DD, model at 0x35B, name at 0x3D3
    #   Slot 2: type at 0x583, manufacturer at 0x58B, model at 0x60B, name at 0x68B
    # Each slot is 686 (0x2AE) bytes after the previous

    SLOT_0_TYPE_OFFSET = 0x27
    SLOT_SIZE = 0x2AE  # 686 bytes
    MANUFACTURER_IN_SLOT = 0x08   # offset of manufacturer within slot
    MODEL_IN_SLOT = 0x88           # offset of model within slot
    NAME_IN_SLOT = 0x108           # offset of user name within slot

    def read_utf16(buf: bytes, off: int, max_chars: int = 64) -> str:
        """Read null-terminated UTF-16LE string."""
        end = off
        while end + 1 < len(buf) and (buf[end] != 0 or buf[end + 1] != 0):
            end += 2
            if end - off >= max_chars * 2:
                break
        return buf[off:end].decode('utf-16-le', errors='replace')

    for i in range(device_count):
        slot_start = SLOT_0_TYPE_OFFSET - MANUFACTURER_IN_SLOT + i * SLOT_SIZE
        type_off = slot_start + MANUFACTURER_IN_SLOT - 8  # type byte is 8 bytes before manufacturer
        # Exact offsets from analysis:
        type_off = 0x27 + i * SLOT_SIZE
        mfr_off = 0x2F + i * SLOT_SIZE
        model_off = 0xAF + i * SLOT_SIZE
        name_off = 0x12F + i * SLOT_SIZE

        if type_off >= len(data):
            break

        type_byte = data[type_off]
        manufacturer = read_utf16(data, mfr_off) if mfr_off < len(data) else ''
        model = read_utf16(data, model_off) if model_off < len(data) else ''
        user_name = read_utf16(data, name_off) if name_off < len(data) else ''

        devices.append({
            'index': i,
            'type_byte': type_byte,
            'type_name': models.device_type_name(type_byte),
            'manufacturer': manufacturer,
            'model': model,
            'user_name': user_name,
        })

    return devices


def extract_project(rti_path: str, show_tlv: bool = False,
                    extract_dir: str = None) -> dict:
    """Parse an .rti file and return a structured project dict."""
    print(f"[*] Parsing: {rti_path}")

    with open(rti_path, 'rb') as f:
        raw = f.read()

    parser = cfb.CFBParser(raw)
    all_streams = parser.get_all_streams()

    result = {
        'file': os.path.basename(rti_path),
        'streams': {},
        'job_info': {},
        'directory': [],
        'devices': [],
    }

    # List all streams
    print(f"\n[*] OLE2 Streams ({len(all_streams)} total):")
    for name, data in sorted(all_streams.items()):
        print(f"    {name!r:40s}  {len(data):6d} bytes")
        result['streams'][name] = len(data)

    # Extract raw stream files if requested
    if extract_dir:
        os.makedirs(extract_dir, exist_ok=True)
        for name, data in all_streams.items():
            safe_name = name.replace(' ', '_').replace('/', '_')
            path = os.path.join(extract_dir, f"stream_{safe_name}.bin")
            with open(path, 'wb') as f:
                f.write(data)
            print(f"    Wrote: {path}")

    # Job Info
    if models.STREAM_JOB_INFO in all_streams:
        job_data = all_streams[models.STREAM_JOB_INFO]
        job = parse_job_info(job_data)
        result['job_info'] = job
        print(f"\n[*] Job Info:")
        if job:
            for k, v in job.items():
                print(f"    {k}: {v!r}")
        else:
            print("    (no printable metadata extracted)")

    # RTI Data Directory V3
    if models.STREAM_DIR_V3 in all_streams:
        dir_data = all_streams[models.STREAM_DIR_V3]
        directory = parse_directory_v3(dir_data)
        result['directory'] = directory
        print(f"\n[*] Device Directory ({len(directory)} devices):")
        for d in directory:
            print(f"    [{d['index']}] Type=0x{d['type_byte']:02X} ({d['type_name']:12s}) "
                  f"Model={d['model']!r:10s} Name={d['user_name']!r}")

    # Device Data Streams
    print(f"\n[*] Device Data Streams:")
    device_index = 0
    while True:
        stream_name = models.device_stream_name(device_index)
        if stream_name not in all_streams:
            break
        stream_data = all_streams[stream_name]
        header = parse_device_stream_header(stream_data)
        type_byte = header.get('device_type')
        type_name = models.device_type_name(type_byte) if type_byte is not None else 'Unknown'

        print(f"    Stream {device_index:04d}: "
              f"type=0x{type_byte:02X} ({type_name}), "
              f"model_num={header.get('model_number')}, "
              f"timeout={header.get('timeout_sec')}s, "
              f"format_ver={header.get('format_version')}, "
              f"size={len(stream_data)} bytes")

        if show_tlv:
            print(f"      --- TLV decode (first 256 bytes) ---")
            nodes = tlv.decode(stream_data, length=256)
            tlv.print_nodes(nodes, indent=3)

        device_entry = {
            'stream_index': device_index,
            'stream_name': stream_name,
            'size': len(stream_data),
            **header,
            'type_name': type_name,
        }
        result['devices'].append(device_entry)
        device_index += 1

    if device_index == 0:
        print("    (none found)")

    return result


def main():
    parser = argparse.ArgumentParser(
        description='Parse and inspect an RTI .rti project file.')
    parser.add_argument('rti_file', help='Path to .rti project file')
    parser.add_argument('--json', action='store_true',
                        help='Output as JSON')
    parser.add_argument('--extract-streams', metavar='DIR',
                        help='Write raw stream bytes to this directory')
    parser.add_argument('--tlv', action='store_true',
                        help='Show TLV decode of device streams')
    args = parser.parse_args()

    if not os.path.isfile(args.rti_file):
        print(f"ERROR: File not found: {args.rti_file}", file=sys.stderr)
        sys.exit(1)

    result = extract_project(
        args.rti_file,
        show_tlv=args.tlv,
        extract_dir=args.extract_streams,
    )

    if args.json:
        print('\n--- JSON Output ---')
        print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    main()
