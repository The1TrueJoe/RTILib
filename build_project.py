#!/usr/bin/env python3
"""
build_project.py — Programmatic RTI U2 + XP project builder.

Every XP-6 macro (source shortcuts + all 35 hardware buttons) is wired to
the Simple HTTP Client driver's "Send HTTP String" function.  Edit the
BUTTON_REQUESTS dict to map each button label to the HTTP path your device
expects.

Run:
    python build_project.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from rti_lib import RTIProject, XPProcessor, U2Remote, BMLFile
from rti_lib.devices.xp.driver import RTIDriver


# ===========================================================================
# PROJECT DEFINITION — edit here to customise
# ===========================================================================

DEFAULT_OUTPUT = r"C:\Users\Admin\Downloads\RTI Research\my_project.rti"
C4_BML_PATH    = r"C:\Users\Admin\Downloads\RTI Research\C4.bml"

XP_DISPLAY_NAME = 'TestXP6'
U2_DISPLAY_NAME = 'TestU2'

# ── Driver source files ──────────────────────────────────────────────────────
DRIVER_RTIDRIVER_PATH = r"C:\Users\Admin\Downloads\RTI Research\driver\Simple HTTP Client.rtidriver"
DRIVER_TEMPLATE_RTI   = r"C:\Users\Admin\Downloads\RTI Research\my_project_v3.rti"

# ── HTTP connection settings ─────────────────────────────────────────────────
DRIVER_CONFIG = {
    'defaultHost':   '192.168.1.20',
    'defaultPort':   '80',
    'defaultMethod': 'GET',
    'DebugTrace':    'false',
}

# ── HTTP path for each U2 source shortcut (Source1-Source8) ─────────────────
SOURCE_REQUESTS = {
    1: '/source/1',
    2: '/source/2',
    3: '/source/3',
    4: '/source/4',
    5: '/source/5',
    6: '/source/6',
    7: '/source/7',
    8: '/source/8',
}

# ── HTTP path per hardware button label (all 35 physical U2 buttons) ─────────
# Keys must match the label strings from U2Remote.hardware_buttons().
# Unnamed buttons (no label) use the auto-generated key 'BtnNNN'.
BUTTON_REQUESTS = {
    'MENU':      '/nav/menu',
    'Btn129':    '/btn/129',
    'Home':      '/nav/home',
    'Btn131':    '/btn/131',
    'Left':      '/nav/left',
    'Right':     '/nav/right',
    'DOWN':      '/nav/down',
    'SELECT':    '/nav/select',
    'GUIDE':     '/guide',
    'Exit':      '/exit',
    'Vol+':      '/volume/up',
    'VOL-':      '/volume/down',
    'Btn140':    '/btn/140',
    'Channel-':  '/channel/down',
    '9':         '/num/9',
    '8':         '/num/8',
    '7':         '/num/7',
    '6':         '/num/6',
    '5':         '/num/5',
    '4':         '/num/4',
    '3':         '/num/3',
    '2':         '/num/2',
    '1':         '/num/1',
    '0':         '/num/0',
    'Enter':     '/enter',
    'Star':      '/star',
    'PLAY':      '/transport/play',
    'PAUSE':     '/transport/pause',
    'STOP':      '/transport/stop',
    'NEXT':      '/transport/next',
    'BACK':      '/transport/back',
    'FORWARD':   '/transport/forward',
    'On':        '/power/on',
    'Off':       '/power/off',
    'Favorites': '/favorites',
}

# ===========================================================================


def build(output_path: str = DEFAULT_OUTPUT) -> None:
    """Build the project and write to output_path."""

    # ── Load icon library ────────────────────────────────────────────────────
    bml = BMLFile.load(C4_BML_PATH)
    c4_icon = bml['Control4']
    print(f"\n[0] Icons loaded: {bml.names()}")

    # ── Load driver ──────────────────────────────────────────────────────────
    print(f"\n[1] Loading driver: {os.path.basename(DRIVER_RTIDRIVER_PATH)}")
    driver = RTIDriver.from_files(
        rtidriver_path=DRIVER_RTIDRIVER_PATH,
        template_rti_path=DRIVER_TEMPLATE_RTI,
    )
    print(f"    {driver.name!r}  v{driver.version}  {len(driver.get_defaults())} config settings")

    # ── XP-6 processor ───────────────────────────────────────────────────────
    print(f"\n[2] Building XP-6 macros  ({XP_DISPLAY_NAME!r})")
    xp = XPProcessor('XP-6', display_name=XP_DISPLAY_NAME)

    def _drv_macro(label: str, path: str):
        """Add a driver macro that sends the given HTTP path."""
        name = f'{U2_DISPLAY_NAME} {label}'
        return xp.add_macro(
            name,
            driver_guid=driver.guid_bytes,
            export_name='SendHTTP',
            param=path,
            slot=0,
            timeout_ms=200,
        )

    # Source shortcut macros (Source1-8)
    source_macros = []
    for i in range(1, 9):
        path = SOURCE_REQUESTS[i]
        m = _drv_macro(f'Source{i}', path)
        source_macros.append(m)
        print(f"    Macro {m.seq_num:>2}: Source{i}  →  {path}")

    # Hardware-button macros
    u2 = U2Remote(display_name=U2_DISPLAY_NAME)
    print(f"\n[3] Building hardware-button macros")
    for hw_idx, btn_label in U2Remote.hardware_buttons():
        key = btn_label if btn_label else f'Btn{hw_idx}'
        path = BUTTON_REQUESTS.get(key, f'/btn/{hw_idx}')
        m = _drv_macro(key, path)
        u2.assign_hw_button_macro(hw_idx, m)
        print(f"    Macro {m.seq_num:>2}: [{hw_idx}] {key:<12}  →  {path}")

    # Attach driver with config
    xp.add_driver(driver, settings=DRIVER_CONFIG)
    print(f"\n[4] Driver attached — host={DRIVER_CONFIG['defaultHost']}:{DRIVER_CONFIG['defaultPort']}")

    # ── U2 shortcuts ─────────────────────────────────────────────────────────
    print(f"\n[5] U2 shortcuts")
    for i, m in enumerate(source_macros):
        u2.add_shortcut(m.name, macro=m, icon=c4_icon)
        print(f"    Shortcut {i + 1}: {m.name!r}  → macro {m.seq_num}")

    # ── Save ─────────────────────────────────────────────────────────────────
    print(f"\n[6] Writing: {output_path}")
    proj = RTIProject()
    proj.add_device(xp)
    proj.add_device(u2)
    size = proj.save(output_path)
    print(f"    OK — {size:,} bytes")

    # ── Verify: decode config from the written file ───────────────────────────
    from rti_lib.devices.xp.driver import decode_config
    info = decode_config(output_path)
    print(f"\n[7] Verified driver config in output:")
    print(f"    Driver:  {info['name']}  v{info['version']}")
    print(f"    GUID:    {info['guid']}")
    print(f"    Settings ({len(info['settings'])}):")
    for k, v in sorted(info['settings'].items()):
        print(f"      {k:<28} = {v!r}")


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='Build a U2 + XP-6 HTTP driver project')
    ap.add_argument('--output', default=DEFAULT_OUTPUT, help='Output .rti path')
    args = ap.parse_args()
    build(args.output)

