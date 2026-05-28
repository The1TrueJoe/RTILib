"""
rti_lib/devices/xp/processor.py — XP-series processor device class.

An XPProcessor holds a collection of Macro objects.  Each macro stores one
command (serial or driver) and knows how to encode itself as TLV bytes.

Typical usage::

    xp = XPProcessor('XP-6', display_name='Living Room')
    m1 = xp.add_macro('Watch TV',    serial=b'src tv\\r')
    m2 = xp.add_macro('Watch Movie', serial=b'src bd\\r')
    m3 = xp.add_macro('All Off',     serial=b'all off\\r')
"""

from typing import Dict, List, Optional
from ...core import tlv
from .encoders import (
    encode_serial_command_tlv,
    encode_driver_command_tlv,
    encode_commands_container,
    encode_inner_macro,
    encode_macro_group,
    encode_empty_macro_group,
    DEVICE_HASH_SERIAL,
    DEVICE_HASH_DRIVER,
    SERIAL_SETTINGS_8N1,
)
from .stream_profile import build_xp6_base_stream
from .driver import RTIDriver


class Macro:
    """
    A named macro on an XP processor.

    Obtain instances via XPProcessor.add_macro(), then pass them to
    U1Remote.add_global_button() or U2Remote.add_shortcut() to wire a
    remote button to this macro.

    Attributes
    ----------
    name    : display name shown in Integration Designer
    seq_num : 1-based sequence number assigned when the macro was added
    """

    def __init__(self, name: str, seq_num: int, _command: dict):
        self.name    = name
        self.seq_num = seq_num
        self._cmd    = _command

    def __repr__(self) -> str:
        return f"Macro({self.name!r}, seq={self.seq_num})"

    def _build_tlv(self) -> bytes:
        """Internal — build the complete inner-macro TLV container bytes."""
        cmd  = self._cmd
        kind = cmd.get('type', 'serial')

        if kind == 'serial':
            raw = cmd.get('serial_bytes', b'')
            if isinstance(raw, str):
                raw = raw.encode('latin-1')
            cmd_tlv = encode_serial_command_tlv(
                serial_string=raw,
                baud_rate=cmd.get('baud', 9600),
                port_num=cmd.get('port', 0),
                settings_byte=cmd.get('settings', SERIAL_SETTINGS_8N1),
                manufacturer=cmd.get('manufacturer', ''),
                model_str=cmd.get('model', ''),
                device_name=cmd.get('device_name', ''),
                command_name=self.name,
            )
            device_hash = DEVICE_HASH_SERIAL

        elif kind == 'driver':
            cmd_tlv = encode_driver_command_tlv(
                driver_guid=cmd['driver_guid'],
                export_name=cmd.get('export_name', ''),
                string_param=cmd.get('param', ''),
                slot_index=cmd.get('slot', 0),
                timeout_ms=cmd.get('timeout_ms', 200),
            )
            device_hash = DEVICE_HASH_DRIVER

        else:
            # Placeholder / no-op macro
            return encode_inner_macro(self.seq_num, self.name, b'')

        container = encode_commands_container(device_hash, cmd_tlv)
        return encode_inner_macro(self.seq_num, self.name, container)


class XPProcessor:
    """
    RTI XP-3, XP-6, or XP-8 processor.

    The processor holds all project macros.  Macros are referenced by
    sequence number from remote button records.

    Example::

        xp = XPProcessor('XP-6')
        m  = xp.add_macro('Watch TV', serial=b'src tv\\r', baud=9600)
    """

    # All XP models share the same binary base-stream profile.
    # The model name is stored separately in the project directory.
    _MODEL_PREFIXES = {
        'XP-3': build_xp6_base_stream,
        'XP-6': build_xp6_base_stream,
        'XP-8': build_xp6_base_stream,
    }

    def __init__(self, model: str = 'XP-6', display_name: str = None):
        if model not in self._MODEL_PREFIXES:
            raise ValueError(
                f"model must be one of {list(self._MODEL_PREFIXES)}; got {model!r}"
            )
        self.model        = model
        self.display_name = display_name or model
        self._macros: Dict[str, Macro] = {}
        self._seq = 0
        self._driver: Optional[RTIDriver] = None
        self._driver_settings: Dict[str, str] = {}

    # ---- public API -------------------------------------------------------

    def add_macro(
            self,
            name: str,
            *,
            serial: bytes = None,
            baud: int = 9600,
            port: int = 0,
            settings: int = SERIAL_SETTINGS_8N1,
            manufacturer: str = '',
            model_str: str = '',
            device_name: str = '',
            driver_guid: bytes = None,
            export_name: str = '',
            param: str = '',
            slot: int = 0,
            timeout_ms: int = 200,
    ) -> 'Macro':
        """
        Add a macro and return the Macro object.

        Provide exactly one of ``serial`` or ``driver_guid``.
        If neither is given a no-op placeholder is stored.

        Parameters
        ----------
        name         : macro display name (shown in Integration Designer)
        serial       : raw bytes sent over serial  (e.g. ``b'src tv\\r\``)
        baud         : baud rate in bps (default 9600)
        port         : serial port index on the processor (0-based)
        settings     : serial settings byte (0x88 = 8-N-1, see SERIAL_SETTINGS_8N1)
        manufacturer : optional label visible in Integration Designer UI
        model_str    : optional label visible in Integration Designer UI
        device_name  : optional label visible in Integration Designer UI
        driver_guid  : 16-byte driver GUID (for RTI driver commands)
        export_name  : driver function name (e.g. 'SendHTTP')
        param        : string argument passed to the driver function
        slot         : driver slot index (0-based)
        timeout_ms   : driver command timeout in milliseconds
        """
        self._seq += 1

        if serial is not None:
            cmd = {
                'type': 'serial',
                'serial_bytes': serial,
                'baud': baud,
                'port': port,
                'settings': settings,
                'manufacturer': manufacturer,
                'model': model_str,
                'device_name': device_name,
            }
        elif driver_guid is not None:
            cmd = {
                'type': 'driver',
                'driver_guid': driver_guid,
                'export_name': export_name,
                'param': param,
                'slot': slot,
                'timeout_ms': timeout_ms,
            }
        else:
            cmd = {'type': 'noop'}

        macro = Macro(name, self._seq, cmd)
        self._macros[name] = macro
        return macro

    def add_driver(
        self,
        driver: RTIDriver,
        settings: Dict[str, str] = None,
    ) -> None:
        """
        Attach a driver to this processor.

        Parameters
        ----------
        driver   : RTIDriver instance (from RTIDriver.from_files() etc.)
        settings : Optional overrides for the driver's config settings.
                   Any key not provided falls back to the driver's defaults.
        """
        self._driver = driver
        self._driver_settings = settings or {}

    def macro(self, name: str) -> Optional['Macro']:
        """Look up a macro by name; returns None if not found."""
        return self._macros.get(name)

    @property
    def macros(self) -> List['Macro']:
        """All macros in insertion order."""
        return list(self._macros.values())

    # ---- internal ---------------------------------------------------------

    def build_stream(self) -> bytes:
        """
        Build the complete device data stream bytes for this processor.

        Layout:
          [XP6 base stream — 397 TLV records, 6633 bytes]
          [primary macro group container — TAG=01]
          [empty secondary macro group  — TAG=02]
          [FF FF terminator]
        """
        prefix       = self._MODEL_PREFIXES[self.model](self.display_name)
        inner_macros = [m._build_tlv() for m in self._macros.values()]

        if self._driver is not None:
            # When a driver is present the stream gains an extra BLOB(0x0a)
            # marker (9 bytes: 0x34 followed by eight zero bytes) before the
            # macro group, and the driver CONT(0x07) is appended after the
            # empty secondary macro group.
            driver_count_marker = tlv.encode_blob(
                0x0a, bytes([0x34, 0, 0, 0, 0, 0, 0, 0, 0])
            )
            driver_tlv = self._driver.build_tlv(self._driver_settings)
            return (
                prefix
                + driver_count_marker
                + encode_macro_group(inner_macros)
                + encode_empty_macro_group()
                + driver_tlv
                + tlv.TERMINATOR
            )
        else:
            return (
                prefix
                + encode_macro_group(inner_macros)
                + encode_empty_macro_group()
                + tlv.TERMINATOR
            )
