"""
rti_lib/devices/xp/driver.py — RTI driver embedding for XP-series processors.

Drivers are stored in the XP device stream as a ``CONT(tag=0x07)`` container
immediately after the macro group containers.  The container content has two
major sections (called "block A" and "block B") separated by double ``FF FF``
terminators, with config settings stored as ``VARSTR(0x03, name) +
VARSTR(0x04, value)`` pairs inside block B.

Typical usage::

    # Load defaults from the .rtidriver file and opaque template from a
    # reference .rti that already has the driver imported:
    driver = RTIDriver.from_files(
        rtidriver_path='driver/Simple HTTP Client.rtidriver',
        template_rti_path='my_project_v3.rti',
    )

    # Read all configurable settings with their defaults:
    defaults = driver.get_defaults()   # dict[str, str]

    # Build a modified driver container:
    my_settings = {**defaults, 'defaultHost': '10.0.0.50', 'request1String': '/on'}
    cont_bytes = driver.build_container(my_settings)

    # Attach to a processor:
    xp = XPProcessor('XP-6')
    xp.add_driver(driver, settings=my_settings)

Format notes (from reverse-engineering my_project_v3.rti):
  Block A (before first FF FF pair):
    [0] TLV metadata: name, GUID, compressed RTF help, version, flags, second GUID
    [rest] Opaque binary blobs + zlib(SystemEvents.xml) + zlib(SystemFunctions.xml)
  Double FF FF separator
  Block B (after second FF FF):
    GUID(0x08) + opaque binary + VARSTR(0x05, scriptname) + CONT(0x02, compressed_JS)
    BYTE(0x02) + I32(0x04)
    [config pairs]: VARSTR(0x03, name) + VARSTR(0x04, value) — alphabetical order
    [dynamic config]: VARSTR(0x0b, expr) + VARSTR(0x0d, name) + VARSTR(0x0c, ...) + I32(0x07, X)
  Final FF FF (driver container terminator)
"""

import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional

from rti_lib.core import cfb, tlv

# --------------------------------------------------------------------- #
# GUID encoding helper                                                   #
# --------------------------------------------------------------------- #

def _guid_str_to_bytes(guid: str) -> bytes:
    """
    Convert a Windows GUID string like ``{B9226EE9-C8D7-4A5B-A021-704694E0DB88}``
    to the 16-byte little-endian binary form used by RTI (first 3 groups reversed,
    last 2 groups as-is).
    """
    g = guid.strip('{}').replace('-', '')
    # Groups: 8-4-4-4-12 hex digits
    p1 = bytes.fromhex(g[0:8])[::-1]   # Data1: 4 bytes, reversed
    p2 = bytes.fromhex(g[8:12])[::-1]  # Data2: 2 bytes, reversed
    p3 = bytes.fromhex(g[12:16])[::-1] # Data3: 2 bytes, reversed
    p4 = bytes.fromhex(g[16:32])       # Data4: 8 bytes, as-is
    return p1 + p2 + p3 + p4


# --------------------------------------------------------------------- #
# Config settings parser                                                 #
# --------------------------------------------------------------------- #

def _parse_config_defaults(xml_bytes: bytes) -> Dict[str, str]:
    """
    Parse ``ConfigSettings.xml`` from a .rtidriver stream and return
    a dict of {variable_name: default_value_str} for all settings.

    Only ``<setting variable="...">`` elements are included.  Category and
    choice elements are ignored.
    """
    root = ET.fromstring(xml_bytes.decode('utf-8'))
    defaults: Dict[str, str] = {}
    for elem in root.iter('setting'):
        var = elem.get('variable')
        if var is None:
            continue
        default = elem.get('default', '')
        defaults[var] = default
    return defaults


# --------------------------------------------------------------------- #
# Config pairs builder                                                   #
# --------------------------------------------------------------------- #

def _build_config_pairs(settings: Dict[str, str]) -> bytes:
    """
    Build the binary VARSTR pairs for the config section.
    Settings are emitted in alphabetical order (matching Integration Designer).
    Each setting is ``VARSTR(0x03, name) + VARSTR(0x04, value)``.
    Empty-string values are included (VARSTR with slen=0).
    """
    out = b''
    for name in sorted(settings.keys()):
        value = str(settings[name])
        name_utf = name.encode('utf-16-le')
        val_utf = value.encode('utf-16-le')
        out += b'\x03\xa0' + struct.pack('<H', len(name_utf)) + name_utf
        out += b'\x04\xa0' + struct.pack('<H', len(val_utf)) + val_utf
    return out


# --------------------------------------------------------------------- #
# RTIDriver                                                              #
# --------------------------------------------------------------------- #

class RTIDriver:
    """
    An RTI driver ready to be embedded in an XP device stream.

    Holds the opaque binary template bytes of the driver container
    (extracted from a reference .rti file) and knows how to splice in
    custom config settings before writing.

    Attributes
    ----------
    name           : driver display name (from DriverManifest)
    guid_bytes     : 16-byte little-endian GUID
    version        : version string (e.g. '1.0')
    _drv_data      : raw CONT(0x07) content bytes (7365 bytes for Simple HTTP Client)
    _config_start  : absolute offset in _drv_data where config pairs begin
    _config_end    : absolute offset in _drv_data where config pairs end (exclusive)
    _defaults      : {name: default_value} from ConfigSettings.xml
    """

    def __init__(
        self,
        name: str,
        guid_bytes: bytes,
        version: str,
        drv_data: bytes,
        config_start: int,
        config_end: int,
        defaults: Dict[str, str],
    ):
        self.name = name
        self.guid_bytes = guid_bytes
        self.version = version
        self._drv_data = drv_data
        self._config_start = config_start
        self._config_end = config_end
        self._defaults = defaults

    # ----------------------------------------------------------------- #
    # Constructors                                                        #
    # ----------------------------------------------------------------- #

    @classmethod
    def from_files(
        cls,
        rtidriver_path: str,
        template_rti_path: str,
        device_stream: str = 'Device Data Stream 0000',
    ) -> 'RTIDriver':
        """
        Create an RTIDriver by combining:
          - driver metadata and config defaults from the .rtidriver file
          - opaque binary template bytes from a reference .rti file

        Parameters
        ----------
        rtidriver_path    : path to the .rtidriver file
        template_rti_path : path to a .rti file that already has this driver imported
        device_stream     : name of the XP device stream in the .rti file
        """
        # ── Read .rtidriver streams ──────────────────────────────────────
        rtidrv_streams = cfb.load(str(rtidriver_path)).get_all_streams()

        manifest_xml = rtidrv_streams['DriverManifest'].decode('utf-8')
        root = ET.fromstring(manifest_xml)
        driver_elem = root.find('driver') or root  # handle both <driverManifest><driver> and flat
        name = driver_elem.get('name', 'Unknown')
        guid_str = driver_elem.get('id', '')
        version = driver_elem.get('driverVersion', '1.0')
        guid_bytes = _guid_str_to_bytes(guid_str) if guid_str else b'\x00' * 16

        cfg_xml = rtidrv_streams.get('ConfigSettings.xml', b'')
        defaults = _parse_config_defaults(cfg_xml)

        # ── Extract driver container from template .rti ──────────────────
        rti_streams = cfb.load(str(template_rti_path)).get_all_streams()
        xp_raw = rti_streams[device_stream]
        xp_nodes = tlv.decode(xp_raw)
        drv_node = next(
            (n for n in xp_nodes if n.type_code == tlv.T_CONTAINER and n.tag == 0x07),
            None,
        )
        if drv_node is None:
            raise ValueError(
                f"No driver container (CONT tag=0x07) found in {device_stream} "
                f"of {template_rti_path}"
            )
        drv_data = drv_node.value  # raw container content

        # ── Locate config pairs section in drv_data ──────────────────────
        config_start, config_end = _find_config_bounds(drv_data)

        return cls(name, guid_bytes, version, drv_data, config_start, config_end, defaults)

    @classmethod
    def from_rtifile(
        cls,
        rti_path: str,
        device_stream: str = 'Device Data Stream 0000',
    ) -> 'RTIDriver':
        """
        Extract driver info directly from an existing .rti file.
        Config defaults are read from the TLV metadata (driver name/GUID/version)
        and the config values currently stored in the file.

        Use this when you only have the .rti and not the original .rtidriver.
        """
        rti_streams = cfb.load(str(rti_path)).get_all_streams()
        xp_raw = rti_streams[device_stream]
        xp_nodes = tlv.decode(xp_raw)
        drv_node = next(
            (n for n in xp_nodes if n.type_code == tlv.T_CONTAINER and n.tag == 0x07),
            None,
        )
        if drv_node is None:
            raise ValueError(
                f"No driver container (CONT tag=0x07) found in {device_stream} of {rti_path}"
            )
        drv_data = drv_node.value

        # Read metadata from TLV children
        meta_nodes = tlv.decode(drv_data)
        name_node = next((n for n in meta_nodes if n.type_code == tlv.T_VARSTR and n.tag == 0x01), None)
        guid_node = next((n for n in meta_nodes if n.type_code == tlv.T_BLOB and n.tag == 0x01), None)
        ver_node  = next((n for n in meta_nodes if n.type_code == tlv.T_VARSTR and n.tag == 0x0a), None)
        name = name_node.value if name_node else 'Unknown'
        guid_bytes = guid_node.value if guid_node else b'\x00' * 16
        version = ver_node.value if ver_node else '1.0'

        config_start, config_end = _find_config_bounds(drv_data)

        # Read stored config values as defaults
        defaults = _read_config_from_drv_data(drv_data, config_start, config_end)

        return cls(name, guid_bytes, version, drv_data, config_start, config_end, defaults)

    # ----------------------------------------------------------------- #
    # Public API                                                          #
    # ----------------------------------------------------------------- #

    def get_defaults(self) -> Dict[str, str]:
        """Return a copy of the default config settings {name: value}."""
        return dict(self._defaults)

    def build_container(self, settings: Optional[Dict[str, str]] = None) -> bytes:
        """
        Build the raw CONT(0x07) content bytes with custom config settings.

        If ``settings`` is None or empty, the defaults are used.
        Any keys not in ``settings`` fall back to their defaults.

        Returns bytes suitable for passing to ``tlv.encode_container(0x07, ...)``.
        """
        merged = dict(self._defaults)
        if settings:
            merged.update(settings)
        new_pairs = _build_config_pairs(merged)
        return (
            self._drv_data[:self._config_start]
            + new_pairs
            + self._drv_data[self._config_end:]
        )

    def build_tlv(self, settings: Optional[Dict[str, str]] = None) -> bytes:
        """Return the complete encoded ``CONT(0x07)`` TLV record."""
        return tlv.encode_container(0x07, self.build_container(settings))

    def describe(self) -> str:
        """Return a human-readable description of the driver."""
        lines = [
            f'Driver: {self.name}',
            f'Version: {self.version}',
            f'GUID: {_bytes_to_guid_str(self.guid_bytes)}',
            f'Config settings ({len(self._defaults)}):',
        ]
        for name, val in sorted(self._defaults.items()):
            lines.append(f'  {name} = {val!r}')
        return '\n'.join(lines)


# --------------------------------------------------------------------- #
# Internal helpers                                                       #
# --------------------------------------------------------------------- #

def _find_config_bounds(drv_data: bytes) -> tuple:
    """
    Locate the config pairs section (VARSTR(0x03)+VARSTR(0x04) pairs) within
    the driver container content bytes.

    Strategy:
    1. Block B starts at offset 2342 (after block A + 2×FF FF separators).
    2. In block B, find VARSTR(0x05, scriptname) then CONT(0x02, compressed_JS).
    3. After those, skip BYTE/I32 records to reach the first 0x03 0xa0 = config start.
    4. Config end = first 0x0b 0xa0 (dynamic config VARSTR) after config start.

    Returns (config_start, config_end) as absolute offsets into drv_data.
    Raises ValueError if the expected markers are not found.
    """
    BLOCK_B_OFF = 2342  # fixed: 2338 bytes block A + 2-byte FF FF + 2-byte FF FF
    bb = drv_data[BLOCK_B_OFF:]

    pos = 0
    # Find VARSTR(0x05, ...) — script filename
    script_varstr_found = False
    while pos < len(bb) - 1:
        if bb[pos] == 0x05 and bb[pos + 1] == 0xa0:
            slen = struct.unpack_from('<H', bb, pos + 2)[0]
            pos += 4 + slen
            script_varstr_found = True
            break
        pos += 1

    if not script_varstr_found:
        raise ValueError('Script filename VARSTR(0x05) not found in driver block B')

    # Skip CONT(0x02, compressed_JS)
    if pos + 6 > len(bb) or bb[pos] != 0x02 or bb[pos + 1] != 0xc0:
        raise ValueError(f'Expected CONT(0x02) at block B offset {pos}, got {bb[pos:pos+2].hex()}')
    clen = struct.unpack_from('<I', bb, pos + 2)[0]
    pos += 6 + clen  # skip header + content

    # Skip any BYTE (0x20) or I32 (0x60) records
    while pos < len(bb) - 1:
        typ = bb[pos + 1]
        if typ == 0x20:   # BYTE: 3 bytes total
            pos += 3
        elif typ == 0x60: # I32: 6 bytes total
            pos += 6
        else:
            break

    # First 0x03 0xa0 is config start
    if pos >= len(bb) or bb[pos] != 0x03 or bb[pos + 1] != 0xa0:
        raise ValueError(f'Expected config VARSTR(0x03) at block B offset {pos}, got {bb[pos:pos+2].hex()}')
    config_start = BLOCK_B_OFF + pos

    # Find config end: first VARSTR that is NOT 0x03 or 0x04
    cp = pos
    while cp < len(bb) - 1:
        tag = bb[cp]
        typ = bb[cp + 1]
        if typ != 0xa0:
            break
        if tag not in (0x03, 0x04):
            break  # reached dynamic config (0x0b) or something else
        slen = struct.unpack_from('<H', bb, cp + 2)[0]
        cp += 4 + slen

    config_end = BLOCK_B_OFF + cp

    return config_start, config_end


def _read_config_from_drv_data(drv_data: bytes, config_start: int, config_end: int) -> Dict[str, str]:
    """
    Read the config key-value pairs from the driver container content.
    Returns {name: value} dict.
    """
    section = drv_data[config_start:config_end]
    pos = 0
    result = {}
    while pos < len(section) - 1:
        if section[pos] == 0x03 and section[pos + 1] == 0xa0:
            # Name
            slen = struct.unpack_from('<H', section, pos + 2)[0]
            name = section[pos + 4:pos + 4 + slen].decode('utf-16-le', errors='replace')
            pos += 4 + slen
            # Value (should be 0x04 0xa0)
            if pos < len(section) - 1 and section[pos] == 0x04 and section[pos + 1] == 0xa0:
                slen2 = struct.unpack_from('<H', section, pos + 2)[0]
                value = section[pos + 4:pos + 4 + slen2].decode('utf-16-le', errors='replace')
                pos += 4 + slen2
                result[name] = value
            else:
                result[name] = ''
        else:
            break
    return result


def _bytes_to_guid_str(b: bytes) -> str:
    """Convert 16-byte LE GUID to Windows string form {XXXXXXXX-...}."""
    if len(b) != 16:
        return ''
    d1 = b[0:4][::-1].hex().upper()
    d2 = b[4:6][::-1].hex().upper()
    d3 = b[6:8][::-1].hex().upper()
    d4a = b[8:10].hex().upper()
    d4b = b[10:16].hex().upper()
    return f'{{{d1}-{d2}-{d3}-{d4a}-{d4b}}}'


# --------------------------------------------------------------------- #
# Public decoder                                                         #
# --------------------------------------------------------------------- #

def decode_config(
    rti_path: str,
    device_stream: str = 'Device Data Stream 0000',
) -> dict:
    """
    Decode the driver config embedded in a .rti file.

    Returns a dict with the following keys:

    ``name``           : driver display name string
    ``guid``           : GUID in Windows string form, e.g. ``{B9226EE9-...}``
    ``guid_bytes``     : raw 16-byte little-endian GUID
    ``version``        : driver version string
    ``container_size`` : total byte size of the driver container in the stream
    ``settings``       : ``{name: value}`` dict of all config key-value pairs

    Raises ``ValueError`` if no driver is found in the specified stream.

    Example::

        info = decode_config('my_project.rti')
        print(info['name'])                # 'Simple HTTP Client'
        print(info['settings']['defaultHost'])  # '192.168.1.20'
    """
    rti_streams = cfb.load(str(rti_path)).get_all_streams()
    if device_stream not in rti_streams:
        raise ValueError(f'Stream {device_stream!r} not found in {rti_path}')

    xp_raw = rti_streams[device_stream]
    xp_nodes = tlv.decode(xp_raw)
    drv_node = next(
        (n for n in xp_nodes if n.type_code == tlv.T_CONTAINER and n.tag == 0x07),
        None,
    )
    if drv_node is None:
        raise ValueError(
            f'No driver container (CONT tag=0x07) found in {device_stream!r} of {rti_path!r}'
        )

    drv_data = drv_node.value
    meta_nodes = tlv.decode(drv_data)

    name_node = next((n for n in meta_nodes if n.type_code == tlv.T_VARSTR and n.tag == 0x01), None)
    guid_node = next((n for n in meta_nodes if n.type_code == tlv.T_BLOB  and n.tag == 0x01), None)
    ver_node  = next((n for n in meta_nodes if n.type_code == tlv.T_VARSTR and n.tag == 0x0a), None)

    name       = name_node.value if name_node else ''
    guid_bytes = guid_node.value if guid_node else b'\x00' * 16
    version    = ver_node.value  if ver_node  else ''

    config_start, config_end = _find_config_bounds(drv_data)
    settings = _read_config_from_drv_data(drv_data, config_start, config_end)

    return {
        'name':           name,
        'guid':           _bytes_to_guid_str(guid_bytes),
        'guid_bytes':     guid_bytes,
        'version':        version,
        'container_size': len(drv_data),
        'settings':       settings,
    }
