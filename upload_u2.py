#!/usr/bin/env python3
"""
upload_u2.py — Extract and upload the U2 device stream from an RTI project file.

Usage:
    python upload_u2.py <file.rti> [options]

Options:
    --dry-run         Parse and show what would be uploaded, but don't connect USB
    --device-index N  Use device at index N in the file (default: auto-detect U2)
    --save-stream FILE  Save the extracted stream bytes to a file

RTI U2 device type byte: 0x1D
U2 display: 2.1" B&W, 64x128 pixels
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(__file__))

from rti_lib import cfb, tlv, models
from rti_lib.usb import RTIUploader

# Re-use the helper functions from upload_u1 (import them)
from upload_u1 import find_device_stream, show_stream_info


def main():
    parser = argparse.ArgumentParser(
        description='Upload U2 device stream from an RTI project file.')
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

    print(f"[*] RTI U2 Uploader")
    print(f"[*] Project file: {args.rti_file}")
    print(f"[*] U2 display: {models.U2_DISPLAY_WIDTH}x{models.U2_DISPLAY_HEIGHT}px B&W")
    if args.dry_run:
        print(f"[*] DRY RUN mode — no USB connection will be made")

    # Find the U2 stream
    try:
        stream_name, stream_data = find_device_stream(
            args.rti_file,
            device_type=models.DEVICE_TYPE_U2,
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
