#!/usr/bin/env python3
"""
driver_info.py — Read driver information from an RTI .rti or .rtidriver file.

Usage:
    python driver_info.py <path.rti>             # read driver from .rti file
    python driver_info.py <path.rtidriver>       # read driver metadata from .rtidriver
    python driver_info.py <path.rtidriver> --defaults   # show config defaults too

Examples:
    python driver_info.py my_project_v3.rti
    python driver_info.py "driver/Simple HTTP Client.rtidriver" --defaults
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Allow running from the workspace root without installing the package.
sys.path.insert(0, str(Path(__file__).parent))

from rti_lib.core import cfb, tlv
from rti_lib.devices.xp.driver import (
    RTIDriver,
    _bytes_to_guid_str,
    _find_config_bounds,
    _read_config_from_drv_data,
)


def _read_rtidriver(path: Path, show_defaults: bool) -> None:
    """Show info from a .rtidriver file (no opaque bytes needed)."""
    streams = cfb.load(str(path)).get_all_streams()
    stream_names = sorted(streams.keys())
    print(f'File: {path}')
    print(f'Streams: {", ".join(stream_names)}')
    print()

    # Manifest
    if 'DriverManifest' in streams:
        xml = streams['DriverManifest'].decode('utf-8', errors='replace')
        root = ET.fromstring(xml)
        driver_elem = root.find('driver')
        if driver_elem is None:
            driver_elem = root
        name    = driver_elem.get('name', '?')
        guid    = driver_elem.get('id', '?')
        version = driver_elem.get('driverVersion', '?')
        proc    = driver_elem.get('processorType', '?')
        author  = driver_elem.get('author', '?')
        print(f'Driver Name:    {name}')
        print(f'GUID:           {guid}')
        print(f'Version:        {version}')
        print(f'Processor:      {proc}')
        print(f'Author:         {author}')
        print()

    # Config settings
    if show_defaults and 'ConfigSettings.xml' in streams:
        cfg_xml = streams['ConfigSettings.xml'].decode('utf-8', errors='replace')
        root = ET.fromstring(cfg_xml)
        settings = []
        for elem in root.iter():
            var = elem.get('variable') or elem.get('name')
            if var is None:
                continue
            default = elem.get('default', '')
            s_type  = elem.get('type', elem.tag)
            settings.append((var, s_type, default))
        print(f'Config settings ({len(settings)}):')
        for var, s_type, default in settings:
            print(f'  {var:<28}  [{s_type}]  default={default!r}')
        print()

    # Dynamic config summary
    if 'DynamicConfigInfo' in streams:
        di_bytes = streams['DynamicConfigInfo']
        root = ET.fromstring(di_bytes.decode('utf-8', errors='replace'))
        exprs = root.findall('.//expression')
        print(f'Dynamic config expressions: {len(exprs)}')


def _read_rti(path: Path, show_defaults: bool) -> None:
    """Show driver info embedded in a .rti file."""
    streams = cfb.load(str(path)).get_all_streams()
    # Find XP device streams
    xp_streams = {k: v for k, v in streams.items() if k.startswith('Device Data Stream')}
    if not xp_streams:
        print(f'No device streams found in {path}', file=sys.stderr)
        sys.exit(1)

    for stream_name, xp_raw in sorted(xp_streams.items()):
        xp_nodes = tlv.decode(xp_raw)
        drv_node = next(
            (n for n in xp_nodes if n.type_code == tlv.T_CONTAINER and n.tag == 0x07),
            None,
        )
        if drv_node is None:
            print(f'{stream_name}: no driver installed')
            continue

        drv_data = drv_node.value
        meta_nodes = tlv.decode(drv_data)

        name_node = next((n for n in meta_nodes if n.type_code == tlv.T_VARSTR and n.tag == 0x01), None)
        guid_node = next((n for n in meta_nodes if n.type_code == tlv.T_BLOB and n.tag == 0x01), None)
        ver_node  = next((n for n in meta_nodes if n.type_code == tlv.T_VARSTR and n.tag == 0x0a), None)

        name    = name_node.value if name_node else '?'
        version = ver_node.value  if ver_node  else '?'
        guid    = _bytes_to_guid_str(guid_node.value) if guid_node else '?'

        print(f'{stream_name}:')
        print(f'  Driver Name:  {name}')
        print(f'  Version:      {version}')
        print(f'  GUID:         {guid}')
        print(f'  Container:    {len(drv_data)} bytes')

        try:
            config_start, config_end = _find_config_bounds(drv_data)
            stored_cfg = _read_config_from_drv_data(drv_data, config_start, config_end)
            print(f'  Config pairs: {len(stored_cfg)}')
            if show_defaults:
                print(f'  Config settings:')
                for k, v in sorted(stored_cfg.items()):
                    print(f'    {k:<28} = {v!r}')
        except Exception as exc:
            print(f'  (could not parse config: {exc})')
        print()


def main() -> None:
    args = sys.argv[1:]
    show_defaults = '--defaults' in args
    paths = [a for a in args if not a.startswith('--')]

    if not paths:
        print(__doc__)
        sys.exit(0)

    for p in paths:
        path = Path(p)
        if not path.exists():
            print(f'File not found: {path}', file=sys.stderr)
            sys.exit(1)

        suffix = path.suffix.lower()
        if suffix == '.rti':
            _read_rti(path, show_defaults)
        elif suffix == '.rtidriver':
            _read_rtidriver(path, show_defaults)
        else:
            print(f'Unknown file type: {suffix}', file=sys.stderr)
            sys.exit(1)


if __name__ == '__main__':
    main()
