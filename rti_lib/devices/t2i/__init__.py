"""rti_lib/devices/t2i — RTI T2i colour touchscreen remote support."""

from rti_lib.devices.t2i.remote import T2iRemote
from rti_lib.devices.t2i.image  import load_image_rgb, load_image_rgb_from_bytes

__all__ = ['T2iRemote', 'load_image_rgb', 'load_image_rgb_from_bytes']
