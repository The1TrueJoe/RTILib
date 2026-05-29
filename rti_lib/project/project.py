"""
rti_lib/project/project.py — RTIProject: assembles devices into a .rti file.

A .rti file is an OLE2/CFB container (rti_lib/core/cfb_writer.py) whose
streams are:
  'Device Data Stream 0000'  ← first device (usually XP processor)
  'Device Data Stream 0001'  ← second device (U1 or U2 remote)
  ...
  'Job Info'               ← GPS/timezone metadata (static)
  'VariableIDs'            ← variable-ID registry (empty = FF FF)
  'RTI Data Directory V3' ← device catalogue (name, type, timestamp)

Usage::

    proj = RTIProject()
    proj.add_device(xp)
    proj.add_device(u1)
    proj.add_device(u2)
    proj.save('my_project.rti')
"""

import os
from rti_lib.core import cfb_writer
from rti_lib.core.models import DEVICE_TYPE_U1, DEVICE_TYPE_U2, DEVICE_TYPE_CONTROLLER, DEVICE_TYPE_T2I
from rti_lib.devices.xp import XPProcessor
from rti_lib.devices.u1 import U1Remote
from rti_lib.devices.u2 import U2Remote
from rti_lib.devices.t2i import T2iRemote
from rti_lib.project.metadata import (
    build_job_info_stream,
    build_variable_ids_stream,
    build_directory_stream,
)

# Manufacturer string stored in the RTI Data Directory for all our devices.
_MANUFACTURER = 'Remote Technologies'


class RTIProject:
    """
    A complete RTI project: one processor plus one or more remotes.

    Devices are added in order; each becomes a numbered
    'Device Data Stream NNNN' stream in the .rti file.

    Example::

        proj = RTIProject()
        proj.add_device(xp)    # → Device Data Stream 0000
        proj.add_device(u1)    # → Device Data Stream 0001
        proj.add_device(u2)    # → Device Data Stream 0002
        proj.save('project.rti')
    """

    def __init__(self):
        self._devices = []

    def add_device(self, device) -> None:
        """
        Add a device (XPProcessor, U1Remote, or U2Remote) to the project.

        Devices are assigned stream slots in the order they are added.
        """
        self._devices.append(device)

    def save(self, path: str) -> int:
        """
        Build and write the .rti file.

        Each device's build_stream() is called, and the results are assembled
        into an OLE2/CFB container together with the metadata streams.

        Returns the number of bytes written.
        """
        streams      = {}
        stream_order = []
        dir_entries  = []

        # ---- device streams (one per device, numbered 0000, 0001, …) ------
        for slot, dev in enumerate(self._devices):
            sname = f'Device Data Stream {slot:04d}'
            streams[sname] = dev.build_stream()
            stream_order.append(sname)

            # Collect directory entry for this device
            if isinstance(dev, XPProcessor):
                dir_entries.append(
                    (DEVICE_TYPE_CONTROLLER, _MANUFACTURER, dev.display_name))
            elif isinstance(dev, U1Remote):
                dir_entries.append(
                    (DEVICE_TYPE_U1, _MANUFACTURER, dev.display_name))
            elif isinstance(dev, U2Remote):
                dir_entries.append(
                    (DEVICE_TYPE_U2, _MANUFACTURER, dev.display_name))
            elif isinstance(dev, T2iRemote):
                dir_entries.append(
                    (DEVICE_TYPE_T2I, _MANUFACTURER, dev.display_name))

        # ---- metadata streams --------------------------------------------
        # Job Info: GPS/timezone data decoded from reference project.
        streams['Job Info'] = build_job_info_stream()
        stream_order.append('Job Info')

        # VariableIDs: always empty (just the TLV terminator FF FF).
        streams['VariableIDs'] = build_variable_ids_stream()
        stream_order.append('VariableIDs')

        # RTI Data Directory V3: device catalogue built from dir_entries.
        streams['RTI Data Directory V3'] = build_directory_stream(dir_entries)
        stream_order.append('RTI Data Directory V3')

        # ---- write OLE2/CFB file -----------------------------------------
        data = cfb_writer.write_cfb(streams, stream_order=stream_order)

        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data)

        return len(data)
