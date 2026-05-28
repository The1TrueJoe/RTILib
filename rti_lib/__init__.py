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
"""

# ---- public surface ------------------------------------------------------
from .project.project  import RTIProject
from .devices.xp       import XPProcessor, Macro
from .devices.u1       import U1Remote
from .devices.u2       import U2Remote
from .devices.u2.bml   import BMLFile

__all__ = ['RTIProject', 'XPProcessor', 'Macro', 'U1Remote', 'U2Remote', 'BMLFile']
