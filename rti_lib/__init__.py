"""
rti_lib — RTI Integration Designer project builder.

Builds complete .rti project files programmatically with no template files.
All stream data is encoded as structured TLV — no compressed opaque blobs.

Quick start
-----------
::

    from rti_lib import RTIProject, XPProcessor, U2Remote, BMLFile

    bml = BMLFile.load('icons.bml')
    xp  = XPProcessor('XP-6', display_name='Living Room Processor')
    m1  = xp.add_macro('Watch TV',    serial=b'src tv\\r')
    m2  = xp.add_macro('Watch Movie', serial=b'src bd\\r')

    u2  = U2Remote(display_name='Living Room Remote')
    u2.add_shortcut('Watch TV',    icon=bml['TV'],    macro=m1)
    u2.add_shortcut('Watch Movie', icon=bml['Movie'], macro=m2)

    proj = RTIProject()
    proj.add_device(xp)
    proj.add_device(u2)
    proj.save('my_project.rti')

Package layout
--------------
core/
    tlv.py          TLV encode/decode (the RTI binary wire format)
    cfb.py          OLE2/CFB container reader
    cfb_writer.py   OLE2/CFB container writer
    models.py       Device-type byte constants

devices/
    common.py       Shared TLV builders (button base, group header, …)
    xp/             XP-series processors — XPProcessor, Macro
    u1/             U1 handheld remote  — U1Remote
    u2/             U2 touchscreen      — U2Remote, BMLFile

project/
    project.py      RTIProject (assembles streams, writes .rti)
    metadata.py     Job Info, VariableIDs, RTI Data Directory V3

devices/t2i/
    remote.py       T2iRemote (240×320 colour touchscreen)
    stream_profile.py T2i base stream builder + image encoder
    image.py        load_image_rgb() — load any image as T2i background

tools/
    stream_diff.py  Universal stream diff / inspect tool for reverse engineering
"""

# ---- public surface ------------------------------------------------------
from rti_lib.project.project  import RTIProject
from rti_lib.devices.xp       import XPProcessor, Macro
from rti_lib.devices.u1       import U1Remote
from rti_lib.devices.u2       import U2Remote
from rti_lib.devices.u2.bml   import BMLFile
from rti_lib.devices.t2i      import T2iRemote, load_image_rgb
from rti_lib.tools            import diff_files, print_stream

__all__ = [
    'RTIProject', 'XPProcessor', 'Macro',
    'U1Remote', 'U2Remote', 'BMLFile',
    'T2iRemote', 'load_image_rgb',
    'diff_files', 'print_stream',
]
