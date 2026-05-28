#!/usr/bin/env python3
"""
example_project.py — Demo of the rti_lib project API.

Creates a complete RTI project from scratch (no template .rti file):
  - XP-6 processor with 4 macros (serial commands)
  - U1 remote with 4 global buttons linked to those macros
  - U2 remote with 4 shortcuts using an icon from C4.bml (if present)

Run:
    python example_project.py
Output: example_project.rti
"""

import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from rti_lib.project import RTIProject, XPProcessor, U1Remote, U2Remote
from rti_lib.bml    import BMLFile

# ── Buttons / macros to create ──────────────────────────────────────────────
SOURCES = [
    # (button_label,  serial_command,    baud)
    ('Watch TV',    b'src tv\r',        9600),
    ('Watch Movie', b'src bd\r',        9600),
    ('Listen Music',b'src cd\r',        9600),
    ('All Off',     b'all off\r',       9600),
]

# ── Build XP-6 processor with one macro per source ──────────────────────────
xp = XPProcessor('XP-6')
macros = []
for label, cmd, baud in SOURCES:
    m = xp.add_macro(label, serial=cmd, baud=baud, port=0)
    macros.append(m)
    print(f'  XP macro {m.seq_num}: {m.name!r}  →  {cmd!r}')

# ── Build U1 remote: global button for each source ──────────────────────────
u1 = U1Remote()
for m in macros:
    btn = u1.add_global_button(m.name, macro=m)
    print(f'  U1 global btn idx={btn.hw_index}: {btn.label!r}')

# ── Build U2 remote: shortcut for each source (with icon if available) ───────
u2 = U2Remote()
bml_path = os.path.join(os.path.dirname(__file__), 'C4.bml')
bml = None
if os.path.exists(bml_path):
    bml = BMLFile.load(bml_path)
    print(f'\nLoaded {bml_path}: {len(bml)} icon(s): {bml.names()}')

for m in macros:
    icon = None
    if bml:
        icon = bml.get(m.name)         # match icon by exact name
        if icon is None and len(bml):
            icon = bml.icons[0]        # fallback: first icon
    sc = u2.add_shortcut(m.name, macro=m, icon=icon)
    print(f'  U2 shortcut idx={sc.hw_index}: {sc.label!r}'
          + (f' icon={icon.name!r}' if icon else ''))

# ── Assemble project ─────────────────────────────────────────────────────────
proj = RTIProject()
proj.add_device(xp)   # Device Data Stream 0000  (XP-6)
proj.add_device(u1)   # Device Data Stream 0001  (U1)
proj.add_device(u2)   # Device Data Stream 0002  (U2)

out_path = os.path.join(os.path.dirname(__file__), 'example_project.rti')
size = proj.save(out_path)
print(f'\nWrote {out_path} ({size:,} bytes)')

# ── Verify by reading back ────────────────────────────────────────────────────
from rti_lib import cfb
p = cfb.load(out_path)
streams = p.get_all_streams()
print(f'\nStream summary ({len(streams)} streams):')
for name, data in sorted(streams.items()):
    print(f'  {name}: {len(data):,} bytes')
print('\nOK - project created successfully from code, no template file used.')
