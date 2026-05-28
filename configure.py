#!/usr/bin/env python3
"""
configure.py — Interactive RTI Project Configurator

Generates RTI device streams for U1/U2 remotes paired with XP3/XP6/XP8 processors.

Usage:
    python configure.py [options]
    python configure.py --remote u2 --processor xp6 --output my_project.rti

Interactive mode (no args): guided prompts for all settings.

What this tool does:
  1. Pick remote type: U1 (button-only) or U2 (64x128 B&W display)
  2. Pick processor: XP-3, XP-6, or XP-8
  3. Configure global button options (what each source button does)
  4. For U2: pick bitmap images (64x128 B&W PNG) for shortcut buttons,
             each linked to a preset name
  5. Generate matching macros on the processor for each U2 button/preset
  6. Write output as individual .bin stream files and optionally a full .rti

IMPLEMENTATION NOTES:
  - Macro TLV encoding: fully implemented for serial and driver commands.
  - Global button encoding: fully implemented for U1 and U2 (macro reference).
  - Full stream generation requires a template project (non-decoded header
    bytes are preserved from the template). Use patch_project.py to apply
    configuration to a real .rti project file.
  - Full .rti OLE2 wrapping: not yet implemented.

DEVICE HASHES (7-byte device identifier in commands container):
  The device hash in the commands container identifies which external device
  a command targets. Known values from Test2.rti:
    Serial (custom/generic):  A0 C4 7C 06 00 00 00
    IR (RTI database):        50 C4 7C 06 00 00 00
    Driver (HTTP client):     00 C4 7C 06 00 00 00
    ADA Multi-Room serial:    F0 C9 7C 06 00 00 00
  Use DEVICE_HASH_SERIAL for custom serial commands until the hash
  derivation algorithm is reverse-engineered.
"""

import sys
import os
import struct
import argparse
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from rti_lib import tlv, models
from rti_lib.encoders import (
    DEVICE_HASH_SERIAL, DEVICE_HASH_IR, DEVICE_HASH_DRIVER,
    MACRO_REF_SUFFIX, BAUD_TABLE, SERIAL_SETTINGS_8N1,
    encode_serial_command_tlv, encode_driver_command_tlv,
    encode_commands_container, encode_inner_macro,
    encode_macro_group, encode_empty_macro_group,
    encode_macro_ref_container,
    encode_u1_button_empty, encode_u1_button_with_ref,
    encode_u2_button_empty, encode_u2_button_with_ref,
    encode_button_row, encode_global_button_group,
)

SERIAL_SETTINGS_7N2 = 0x00   # placeholder — not verified
U1_SOURCE_BUTTONS   = [f"Source{i+1}" for i in range(8)]
U2_MAX_SHORTCUTS    = 8


# ===========================================================================
# HIGH-LEVEL STREAM BUILDERS
# ===========================================================================

def build_u1_stream(config: dict) -> bytes:
    """
    Build a Device Data Stream for a U1 remote.

    Config keys:
      source_buttons : list of up to 12 dicts, each with:
                       - 'label': display name
                       - 'macro_seq': macro sequence number on processor (or None)
                       - 'is_global': if True, button goes in global group
      button_indices : list of hardware button indices (default: 128–139)
      timeout_sec    : idle timeout in seconds (default 3600)
      model_number   : RTI model number byte (default 10)
    """
    buttons_cfg  = config.get('source_buttons', [])
    btn_indices  = config.get('button_indices',
                               list(range(128, 128 + max(len(buttons_cfg), 12))))
    timeout_sec  = config.get('timeout_sec', 3600)
    model_number = config.get('model_number', 10)

    parts = []
    parts.append(tlv.encode_byte(0x01, models.DEVICE_TYPE_U1))
    parts.append(tlv.encode_byte(0x03, model_number))
    parts.append(tlv.encode_i32(0x34, timeout_sec))
    parts.append(tlv.encode_u16(0x01, 2))

    local_buttons  = []
    global_buttons = []

    for i, idx in enumerate(btn_indices):
        cfg       = buttons_cfg[i] if i < len(buttons_cfg) else {}
        macro_seq = cfg.get('macro_seq')
        is_global = cfg.get('is_global', False)

        if macro_seq is not None:
            btn = encode_u1_button_with_ref(idx, macro_seq)
        else:
            btn = encode_u1_button_empty(idx)

        if is_global:
            global_buttons.append(btn)
        else:
            local_buttons.append(btn)

    if local_buttons:
        parts.append(encode_button_row(local_buttons))
    if global_buttons:
        parts.append(encode_global_button_group(global_buttons))

    parts.append(tlv.TERMINATOR)
    return b''.join(parts)

def build_u2_stream(config: dict) -> bytes:
    """
    Build a Device Data Stream for a U2 remote.

    Config keys:
      shortcuts    : list of dicts each with:
                     - 'name': display name / preset label
                     - 'bitmap_path': path to 64x128 1-bit BMP (or None)
                     - 'macro_seq': macro sequence number on processor
                     - 'is_global': if True, button goes in global group
      button_indices: list of button hardware indices (default: 128–135)
      timeout_sec  : idle timeout in seconds (default 3600)
      model_number : RTI model number byte (default 10)
    """
    shortcuts    = config.get('shortcuts', [])
    btn_indices  = config.get('button_indices', list(range(128, 128 + max(len(shortcuts), 8))))
    timeout_sec  = config.get('timeout_sec', 3600)
    model_number = config.get('model_number', 10)

    parts = []

    # Stream header
    parts.append(tlv.encode_byte(0x01, models.DEVICE_TYPE_U2))
    parts.append(tlv.encode_byte(0x03, model_number))
    parts.append(tlv.encode_i32(0x34, timeout_sec))
    parts.append(tlv.encode_u16(0x01, 2))

    local_buttons  = []
    global_buttons = []

    for i, idx in enumerate(btn_indices):
        sc        = shortcuts[i] if i < len(shortcuts) else {}
        macro_seq = sc.get('macro_seq')
        is_global = sc.get('is_global', False)

        if macro_seq is not None:
            btn = encode_u2_button_with_ref(idx, macro_seq, bitmap_index=i)
        else:
            btn = encode_u2_button_empty(idx, bitmap_index=i)

        if is_global:
            global_buttons.append(btn)
        else:
            local_buttons.append(btn)

    if local_buttons:
        parts.append(encode_button_row(local_buttons))
    if global_buttons:
        parts.append(encode_global_button_group(global_buttons))

    parts.append(tlv.TERMINATOR)
    return b''.join(parts)

def build_controller_stream(config: dict) -> bytes:
    """
    Build a Device Data Stream for a controller (XP-3/6/8).

    Config keys:
      model      : 'XP-3', 'XP-6', or 'XP-8'
      macros     : list of macro dicts, each with:
                   - 'name': macro display name
                   - 'command': dict describing the command — see below
      timeout_sec: idle timeout (default 3600)
      model_number: RTI model number byte (default 10)

    Macro command dict formats:
      Serial:
        {'type': 'serial', 'string': b'...', 'baud': 9600, 'port': 0,
         'manufacturer': '', 'model': '', 'device': '', 'command_name': ''}

      Driver:
        {'type': 'driver', 'guid': bytes(16), 'export': 'SendHTTP',
         'param': '/path', 'slot': 0}

    Returns the macro section TLV bytes.  The complete XP-6/3/8 stream also
    contains many non-decoded header fields; use patch_project.py to insert
    these macros into an existing project.
    """
    model        = config.get('model', models.CONTROLLER_XP6)
    macros_cfg   = config.get('macros', [])
    timeout_sec  = config.get('timeout_sec', 3600)
    model_number = config.get('model_number', 10)

    parts = []

    # Stream header (partial — non-decoded device config fields not included)
    parts.append(tlv.encode_byte(0x01, models.DEVICE_TYPE_CONTROLLER))
    parts.append(tlv.encode_byte(0x03, model_number))
    parts.append(tlv.encode_i32(0x34, timeout_sec))
    parts.append(tlv.encode_u16(0x01, 2))

    # Build macro containers
    inner_macros = []
    for seq, macro in enumerate(macros_cfg, start=1):
        name    = macro.get('name', f'Macro{seq}')
        cmd_cfg = macro.get('command', {})
        cmd_type = cmd_cfg.get('type', 'serial')

        if cmd_type == 'serial':
            raw_string = cmd_cfg.get('string', b'')
            if isinstance(raw_string, str):
                raw_string = raw_string.encode('ascii', errors='replace')
            cmd_tlv = encode_serial_command_tlv(
                serial_string=raw_string,
                baud_rate=cmd_cfg.get('baud', 9600),
                port_num=cmd_cfg.get('port', 0),
                settings_byte=cmd_cfg.get('settings', SERIAL_SETTINGS_8N1),
                manufacturer=cmd_cfg.get('manufacturer', ''),
                model_str=cmd_cfg.get('model', ''),
                device_name=cmd_cfg.get('device', ''),
                command_name=cmd_cfg.get('command_name', 'Serial Command'),
            )
            device_hash = cmd_cfg.get('device_hash', DEVICE_HASH_SERIAL)

        elif cmd_type == 'driver':
            guid = cmd_cfg.get('guid', bytes(16))
            cmd_tlv = encode_driver_command_tlv(
                driver_guid=guid,
                export_name=cmd_cfg.get('export', ''),
                string_param=cmd_cfg.get('param', ''),
                slot_index=cmd_cfg.get('slot', 0),
                timeout_ms=cmd_cfg.get('timeout', 200),
            )
            device_hash = cmd_cfg.get('device_hash', DEVICE_HASH_DRIVER)

        else:
            print(f"  [!] Unknown command type {cmd_type!r} for macro {name!r}, skipping.")
            continue

        cmd_container = encode_commands_container(device_hash, cmd_tlv)
        inner_macros.append(encode_inner_macro(seq, name, cmd_container))

    # Outer macro group container + empty second container
    parts.append(encode_macro_group(inner_macros))
    parts.append(encode_empty_macro_group())

    parts.append(tlv.TERMINATOR)
    return b''.join(parts)


# ---- Bitmap loader ----


def load_bitmap_1bit(path: str) -> bytes:
    """
    Load a bitmap file and convert to 1-bit (64x128) packed bytes.
    Supports BMP format (stdlib only — no Pillow required).

    Returns 1024 bytes (64*128/8) or None on failure.
    Each row is 8 bytes (64 pixels / 8 bits per byte), MSB first.
    Row order: top to bottom.
    """
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except Exception as e:
        print(f"  [!] Cannot read bitmap {path}: {e}")
        return None

    if data[:2] == b'BM':
        return _decode_bmp_1bit(data)

    if data[:8] == b'\x89PNG\r\n\x1a\n':
        print(f"  [!] PNG support requires Pillow. Install with: pip install Pillow")
        print(f"      Use BMP format: 64x128, 1-bit monochrome.")
        return None

    print(f"  [!] Unknown image format: {path}")
    return None


def _decode_bmp_1bit(data: bytes) -> bytes:
    if len(data) < 54:
        return None

    pixel_offset = struct.unpack_from('<I', data, 10)[0]
    width        = struct.unpack_from('<i', data, 18)[0]
    height       = struct.unpack_from('<i', data, 22)[0]
    bpp          = struct.unpack_from('<H', data, 28)[0]

    if bpp != 1:
        print(f"  [!] BMP must be 1-bit (monochrome). Found {bpp}-bit.")
        return None

    if abs(width) != 64 or abs(height) != 128:
        print(f"  [!] BMP must be 64x128. Found {abs(width)}x{abs(height)}.")
        return None

    top_down  = height < 0
    row_bytes = 8  # 64 pixels / 8 bits per byte, aligned to 4 bytes

    rows = []
    for row_idx in range(128):
        off = pixel_offset + row_idx * row_bytes
        row = data[off:off + row_bytes]
        if len(row) < row_bytes:
            row = row.ljust(row_bytes, b'\x00')
        rows.append(row)

    if not top_down:
        rows.reverse()

    return b''.join(rows)


# ---- Interactive prompt helpers ----

def prompt(msg: str, default: str = None) -> str:
    if default:
        ans = input(f"{msg} [{default}]: ").strip()
        return ans if ans else default
    return input(f"{msg}: ").strip()


def prompt_choice(msg: str, choices: list, default: str = None) -> str:
    options = '/'.join(choices)
    while True:
        ans = prompt(f"{msg} ({options})", default=default).strip().upper()
        for c in choices:
            if ans == c.upper():
                return c
        print(f"  Please enter one of: {options}")


def prompt_int(msg: str, default: int = None, min_val: int = None, max_val: int = None) -> int:
    while True:
        try:
            raw = prompt(msg, default=str(default) if default is not None else None)
            val = int(raw)
            if min_val is not None and val < min_val:
                print(f"  Minimum value is {min_val}")
                continue
            if max_val is not None and val > max_val:
                print(f"  Maximum value is {max_val}")
                continue
            return val
        except ValueError:
            print("  Please enter an integer.")


def prompt_yes_no(msg: str, default: bool = True) -> bool:
    ans = prompt(msg, default='y' if default else 'n').lower()
    return ans in ('y', 'yes', '1', 'true')


def prompt_baud() -> int:
    rates = sorted(BAUD_TABLE.keys())
    print("  Available baud rates: " + ', '.join(str(r) for r in rates))
    return prompt_int("  Baud rate", default=9600)


# ---- Interactive configuration ----

def configure_serial_command_interactive(macro_name: str) -> dict:
    """Interactively configure a serial command macro."""
    print(f"\n    Serial command for macro '{macro_name}':")
    raw_str = prompt("      Serial string (use \\r for CR, \\n for LF)", default='')
    # Unescape common escape sequences
    raw_bytes = raw_str.encode('raw_unicode_escape').decode('unicode_escape').encode('latin-1')
    baud = prompt_baud()
    port = prompt_int("      Serial port number (0-based)", default=0, min_val=0)
    return {
        'type': 'serial',
        'string': raw_bytes,
        'baud': baud,
        'port': port,
    }


def configure_u1_interactive() -> dict:
    """Interactively configure a U1 remote."""
    print("\n--- U1 Remote Configuration ---")
    print("The U1 has configurable source buttons (hardware indices 128–139).")
    print("Each button can be assigned a global macro on the processor.")

    config = {'remote': 'U1', 'source_buttons': []}

    num_buttons = prompt_int("How many buttons to configure?", default=4,
                             min_val=0, max_val=12)

    for i in range(num_buttons):
        print(f"\n  Button {i+1} (hardware index {128 + i}):")
        label = prompt("    Label", default=f'Source{i+1}')
        assign = prompt_yes_no("    Assign to a processor macro?", default=True)
        macro_seq = None
        if assign:
            macro_seq = prompt_int("    Macro sequence number (1-based)", default=i+1,
                                   min_val=1)
        is_global = prompt_yes_no("    Global button (shared across all remote pages)?",
                                  default=True)
        config['source_buttons'].append({
            'label': label,
            'macro_seq': macro_seq,
            'is_global': is_global,
        })

    config['timeout_sec'] = prompt_int(
        "Idle timeout (seconds)", default=3600, min_val=0, max_val=86400)
    return config


def configure_u2_interactive() -> dict:
    """Interactively configure a U2 remote."""
    print("\n--- U2 Remote Configuration ---")
    print(f"The U2 has a {models.U2_DISPLAY_WIDTH}x{models.U2_DISPLAY_HEIGHT} B&W display.")
    print("You can configure up to 8 image shortcuts linked to processor macros.")

    config = {'remote': 'U2', 'shortcuts': []}

    num_shortcuts = prompt_int(
        "How many image shortcuts?", default=4, min_val=0, max_val=U2_MAX_SHORTCUTS)

    for i in range(num_shortcuts):
        print(f"\n  Shortcut {i+1} (hardware index {128 + i}):")
        name = prompt("    Preset/display name", default=f"Preset{i+1}")
        assign = prompt_yes_no("    Assign to a processor macro?", default=True)
        macro_seq = None
        if assign:
            macro_seq = prompt_int("    Macro sequence number (1-based)", default=i+1,
                                   min_val=1)
        is_global = prompt_yes_no("    Global button?", default=True)
        bitmap_path = prompt("    Bitmap file path (64x128 1-bit BMP, or blank)", default='')
        config['shortcuts'].append({
            'name': name,
            'macro_seq': macro_seq,
            'is_global': is_global,
            'bitmap_path': bitmap_path if bitmap_path else None,
        })

    config['timeout_sec'] = prompt_int(
        "Idle timeout (seconds)", default=3600, min_val=0, max_val=86400)
    return config


def configure_processor_interactive(remote_config: dict) -> dict:
    """Interactively configure the processor macros."""
    print("\n--- Processor Configuration ---")

    model = prompt_choice(
        "Processor model",
        [models.CONTROLLER_XP3, models.CONTROLLER_XP6, models.CONTROLLER_XP8],
        default=models.CONTROLLER_XP6)

    print(f"  {model} has {models.controller_ir_count(model)} IR output(s).")

    config = {'model': model, 'macros': []}

    remote_type = remote_config.get('remote')
    buttons = (remote_config.get('source_buttons', []) if remote_type == 'U1'
               else remote_config.get('shortcuts', []))

    # Collect macro sequence numbers used by the remote
    assigned = {}
    for btn in buttons:
        seq = btn.get('macro_seq')
        if seq:
            assigned[seq] = btn.get('label') or btn.get('name', f'Macro{seq}')

    if assigned:
        print(f"\n  Remote uses {len(assigned)} macro(s) on the processor:")
        for seq, lbl in sorted(assigned.items()):
            print(f"    Macro {seq}: '{lbl}'")

    print("\n  Configure each macro command:")
    for seq, lbl in sorted(assigned.items()):
        print(f"\n  Macro {seq} ({lbl!r}):")
        cmd_type = prompt_choice("    Command type", ['serial', 'driver'], default='serial')
        if cmd_type == 'serial':
            cmd = configure_serial_command_interactive(lbl)
        else:
            print("    Driver command configuration (manual entry):")
            export = prompt("      Export function name", default='SendHTTP')
            param  = prompt("      String parameter", default='/')
            # GUID needs to be known in advance — use placeholder zeros
            print("      NOTE: driver GUID must be set manually in the output JSON.")
            cmd = {'type': 'driver', 'guid': bytes(16), 'export': export, 'param': param}
        config['macros'].append({'name': lbl, 'sequence': seq, 'command': cmd})

    # Allow adding extra macros not already covered by remote buttons
    if prompt_yes_no("\n  Add additional processor macros not linked to remote buttons?",
                     default=False):
        while True:
            seq  = prompt_int("  Macro sequence number (0 to stop)", default=0, min_val=0)
            if seq == 0:
                break
            name = prompt("  Macro name", default=f"Macro{seq}")
            cmd_type = prompt_choice("  Command type", ['serial', 'driver'], default='serial')
            if cmd_type == 'serial':
                cmd = configure_serial_command_interactive(name)
            else:
                export = prompt("  Export function", default='SendHTTP')
                param  = prompt("  String parameter", default='/')
                cmd = {'type': 'driver', 'guid': bytes(16), 'export': export, 'param': param}
            config['macros'].append({'name': name, 'sequence': seq, 'command': cmd})

    config['timeout_sec'] = prompt_int(
        "Processor timeout (seconds)", default=3600, min_val=0, max_val=86400)
    return config


# ---- Output ----

def write_output(remote_config: dict, processor_config: dict, output_dir: str):
    """Write device stream .bin files and a JSON config summary."""
    os.makedirs(output_dir, exist_ok=True)

    remote_type     = remote_config.get('remote')
    processor_model = processor_config.get('model', 'XP-6')
    safe_model      = processor_model.replace('-', '')

    print(f"\n[*] Writing output to: {output_dir}")

    if remote_type == 'U1':
        remote_stream   = build_u1_stream(remote_config)
        remote_filename = 'stream_U1_Device_Data.bin'
    else:
        remote_stream   = build_u2_stream(remote_config)
        remote_filename = 'stream_U2_Device_Data.bin'

    remote_path = os.path.join(output_dir, remote_filename)
    with open(remote_path, 'wb') as f:
        f.write(remote_stream)
    print(f"    Wrote: {remote_filename} ({len(remote_stream)} bytes)")

    proc_stream    = build_controller_stream(processor_config)
    proc_filename  = f"stream_{safe_model}_Device_Data.bin"
    proc_path      = os.path.join(output_dir, proc_filename)
    with open(proc_path, 'wb') as f:
        f.write(proc_stream)
    print(f"    Wrote: {proc_filename} ({len(proc_stream)} bytes)")

    # JSON summary (bytes → hex for JSON serialisation)
    def json_default(obj):
        if isinstance(obj, bytes):
            return obj.hex()
        raise TypeError(type(obj))

    summary = {
        'remote': remote_config,
        'processor': processor_config,
        'output_files': {
            'remote_stream': remote_filename,
            'processor_stream': proc_filename,
        },
        'notes': [
            'Stream files contain partial TLV device configuration.',
            'Use patch_project.py to apply this config to a real .rti template.',
            'Full .rti OLE2 wrapping not yet implemented.',
        ]
    }
    summary_path = os.path.join(output_dir, 'project_config.json')
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2, default=json_default)
    print(f"    Wrote: project_config.json")

    print(f"\n[*] To apply to a real project:")
    print(f"    python patch_project.py --input <template.rti> "
          f"--config {summary_path} --output patched.rti")


# ---- Main ----

def main():
    parser = argparse.ArgumentParser(
        description='Interactive RTI U1/U2 + XP3/6/8 project configurator.')
    parser.add_argument('--remote', choices=['u1', 'u2'],
                        help='Remote type (u1 or u2)')
    parser.add_argument('--processor', choices=['xp3', 'xp6', 'xp8'],
                        help='Processor model (xp3, xp6, or xp8)')
    parser.add_argument('--output', metavar='DIR', default='./output',
                        help='Output directory for stream files (default: ./output)')
    parser.add_argument('--load-config', metavar='FILE',
                        help='Load configuration from a previously saved JSON file')
    args = parser.parse_args()

    print("=" * 60)
    print("  RTI Project Configurator")
    print("  U1/U2 Remote + XP3/XP6/XP8 Processor")
    print("=" * 60)

    if args.load_config:
        with open(args.load_config) as f:
            saved = json.load(f)
        remote_config    = saved.get('remote', {})
        processor_config = saved.get('processor', {})
        print(f"[*] Loaded config from: {args.load_config}")
    else:
        if args.remote:
            remote_type = args.remote.upper()
        else:
            remote_type = prompt_choice("\nRemote type", ['U1', 'U2'], default='U1')

        if remote_type == 'U1':
            remote_config = configure_u1_interactive()
        else:
            remote_config = configure_u2_interactive()

        processor_config = configure_processor_interactive(remote_config)

        if args.processor:
            model_map = {'xp3': 'XP-3', 'xp6': 'XP-6', 'xp8': 'XP-8'}
            processor_config['model'] = model_map[args.processor]

    write_output(remote_config, processor_config, args.output)


if __name__ == '__main__':
    main()
