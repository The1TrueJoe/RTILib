#!/usr/bin/env python3
"""
upload_u1.py — Extract and upload the U1 device stream from an RTI project file.

Usage:
    python upload_u1.py <file.rti> [options]

Options:
    --dry-run         Parse and show what would be uploaded, but don't connect USB
    --device-index N  Use device at index N in the file (default: auto-detect U1)
    --save-stream FILE  Save the extracted stream bytes to a file

This script is a staged development tool. Stage 1: extract and identify the
U1 stream. Stage 2: USB connect. Stage 3: actual upload (protocol TBD).

RTI U1 device type byte: 0x11
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(__file__))

from rti_lib import cfb, tlv, models
from rti_lib.usb import RTIUploader


def find_device_stream(rti_path: str, device_type: int, device_index: int = None) -> tuple:
    """
    Find the device data stream matching device_type in the .rti file.

    Returns (stream_name, stream_data) or raises RuntimeError if not found.
    If device_index is specified, use that stream index directly.
    """
    with open(rti_path, 'rb') as f:
        raw = f.read()

    parser = cfb.CFBParser(raw)
    all_streams = parser.get_all_streams()

    if device_index is not None:
        stream_name = models.device_stream_name(device_index)
        if stream_name not in all_streams:
            raise RuntimeError(f"Stream {stream_name!r} not found in {rti_path}")
        return stream_name, all_streams[stream_name]

    # Auto-detect: find first stream with matching device type
    i = 0
    while True:
        stream_name = models.device_stream_name(i)
        if stream_name not in all_streams:
            break
        data = all_streams[stream_name]
        if len(data) >= 3:
            # Device type is at stream byte 2 (TAG=0x01 BYTE)
            # Pattern: 01 20 XX
            if data[0] == 0x01 and data[1] == 0x20 and data[2] == device_type:
                return stream_name, data
        i += 1

    raise RuntimeError(
        f"No device stream with type 0x{device_type:02X} "
        f"({models.device_type_name(device_type)}) found in {rti_path}"
    )


def show_stream_info(stream_name: str, data: bytes):
    """Print information about a device stream."""
    print(f"\n[*] Stream: {stream_name!r}")
    print(f"    Size: {len(data)} bytes")

    if len(data) >= 3:
        type_byte = data[2]
        print(f"    Device Type: 0x{type_byte:02X} ({models.device_type_name(type_byte)})")

    # Decode the header TLV nodes
    nodes = tlv.decode(data, length=min(64, len(data)))
    found_type = False
    for node in nodes:
        if node.tag == 0x01 and node.type_code == tlv.T_BYTE and not found_type:
            print(f"    Device Type Byte: 0x{node.value:02X} = {models.device_type_name(node.value)}")
            found_type = True
        elif node.tag == 0x03 and node.type_code == tlv.T_BYTE:
            print(f"    Model Number: {node.value}")
        elif node.tag == 0x34 and node.type_code == tlv.T_I32:
            print(f"    Timeout: {node.value}s")
        elif node.tag == 0x01 and node.type_code == tlv.T_U16:
            print(f"    Format Version: {node.value}")


def main():
    parser = argparse.ArgumentParser(
        description='Upload U1 device stream from an RTI project file.')
    parser.add_argument('rti_file', help='Path to .rti project file')
    parser.add_argument('--dry-run', action='store_true',
                        help='Parse only, do not attempt USB upload')
    parser.add_argument('--device-index', type=int, default=None,
                        help='Force use of device stream index N (0-based)')
    parser.add_argument('--save-stream', metavar='FILE',
                        help='Save extracted stream bytes to this file')
    args = parser.parse_args()

    if not os.path.isfile(args.rti_file):
        print(f"ERROR: File not found: {args.rti_file}", file=sys.stderr)
        sys.exit(1)

    print(f"[*] RTI U1 Uploader")
    print(f"[*] Project file: {args.rti_file}")
    if args.dry_run:
        print(f"[*] DRY RUN mode — no USB connection will be made")

    # Find the U1 stream
    try:
        stream_name, stream_data = find_device_stream(
            args.rti_file,
            device_type=models.DEVICE_TYPE_U1,
            device_index=args.device_index,
        )
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    show_stream_info(stream_name, stream_data)

    # Optionally save the stream
    if args.save_stream:
        with open(args.save_stream, 'wb') as f:
            f.write(stream_data)
        print(f"\n[*] Saved stream to: {args.save_stream}")

    # Upload
    print(f"\n[*] Uploading {len(stream_data)} bytes to device...")
    uploader = RTIUploader(dry_run=args.dry_run)
    try:
        if not uploader.connect():
            if args.dry_run:
                print("[*] Dry run complete.")
            else:
                print("ERROR: Could not connect to RTI device.", file=sys.stderr)
                sys.exit(1)
            return

        success = uploader.upload(stream_data)
        if success:
            print("[*] Upload complete.")
        else:
            print("[!] Upload failed or not implemented.", file=sys.stderr)
            sys.exit(1)
    finally:
        uploader.disconnect()


if __name__ == '__main__':
    main()
