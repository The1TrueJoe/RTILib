#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from rti_lib import cfb, tlv

p = cfb.load('my_project.rti')
streams = p.get_all_streams()

GROUP_SIG = bytes([0x01, 0x20, 0x02, 0x02, 0x20, 0x00])

# ---- XP macros ----
xp = streams['Device Data Stream 0001']
macro_start = next((i-6 for i in range(6, len(xp)-6)
                    if xp[i:i+6] == GROUP_SIG and xp[i-6]==0x01 and xp[i-5]==0xC0), -1)
print(f'XP macro group at 0x{macro_start:04X}')
grp_len = int.from_bytes(xp[macro_start+2:macro_start+6], 'little')
grp_content = xp[macro_start+6:macro_start+6+grp_len]
nodes = tlv.decode(grp_content)
print(f'  Container nodes: {len(nodes)}')
for node in nodes:
    if node.type_code == tlv.T_CONTAINER:
        inner = tlv.decode(node.raw_value)
        name_node = next((n for n in inner if n.tag == 0x04 and n.type_code == tlv.T_VARSTR), None)
        seq_node  = next((n for n in inner if n.tag == 0x02 and n.type_code == tlv.T_I32), None)
        if name_node:
            name = name_node.raw_value.decode('utf-16-le', errors='replace').rstrip('\x00')
            seq  = seq_node.value if seq_node else '?'
            print(f'  Macro seq={seq}: {name!r}')

print()
# ---- U1 buttons ----
u1 = streams['Device Data Stream 0000']
gb_start = next((i-6 for i in range(6, len(u1)-6)
                 if u1[i:i+6] == GROUP_SIG and u1[i-6]==0x02 and u1[i-5]==0xC0), -1)
print(f'U1 global button group at 0x{gb_start:04X}')
gb_len = int.from_bytes(u1[gb_start+2:gb_start+6], 'little')
gb_content = u1[gb_start+6:gb_start+6+gb_len]
gb_nodes = tlv.decode(gb_content)
print(f'  Container nodes: {len(gb_nodes)}')
for node in gb_nodes:
    if node.type_code == tlv.T_CONTAINER:
        inner = tlv.decode(node.raw_value)
        idx_node = next((n for n in inner if n.tag == 0x02 and n.type_code == tlv.T_I32), None)
        ref_node = next((n for n in inner if n.tag == 0x01 and n.type_code == tlv.T_CONTAINER), None)
        hw_idx = idx_node.value if idx_node else '?'
        if ref_node:
            ref_inner = tlv.decode(ref_node.raw_value)
            blob = next((n for n in ref_inner if n.tag == 0x17 and n.type_code == tlv.T_BLOB), None)
            if blob and len(blob.value) >= 2:
                macro_seq = int.from_bytes(blob.value[:2], 'little')
                print(f'  Button hw_idx={hw_idx} -> macro seq {macro_seq}')
            else:
                print(f'  Button hw_idx={hw_idx} -> no ref BLOB')
        else:
            print(f'  Button hw_idx={hw_idx} -> empty (no macro ref)')
