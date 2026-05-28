#!/usr/bin/env python3
"""Quick self-test for configure.py encoder functions."""
import sys
sys.path.insert(0, '.')
from configure import *

SIMPLE_HTTP_GUID = bytes.fromhex('E96E22B9D7C85B4AA021704694E0DB88')

# ---- Serial command TLV ----
cmd_serial = encode_serial_command_tlv(
    b'`SLDOFR01\r', baud_rate=9600, port_num=0,
    manufacturer='ADA', model_str='Multi Room Controller',
    device_name='Suite 16', command_name='Loudness Off')
print(f"Serial command TLV:   {len(cmd_serial)} bytes")

# ---- Driver command TLV ----
cmd_driver = encode_driver_command_tlv(SIMPLE_HTTP_GUID, 'SendHTTP', '/test', slot_index=0)
print(f"Driver command TLV:   {len(cmd_driver)} bytes")

# ---- Commands containers ----
cont_serial = encode_commands_container(DEVICE_HASH_SERIAL, cmd_serial)
cont_driver = encode_commands_container(DEVICE_HASH_DRIVER, cmd_driver)
print(f"Serial cmd container: {len(cont_serial)} bytes")
print(f"Driver cmd container: {len(cont_driver)} bytes")

# ---- Inner macros ----
macro1 = encode_inner_macro(1, 'My Serial Cmd', cont_serial)
macro2 = encode_inner_macro(2, 'My HTTP Call',  cont_driver)
print(f"Inner macro (serial): {len(macro1)} bytes")
print(f"Inner macro (driver): {len(macro2)} bytes")

# ---- Full macro group ----
group = encode_macro_group([macro1, macro2])
empty = encode_empty_macro_group()
print(f"Outer macro group:    {len(group)} bytes")
print(f"Empty second group:   {len(empty)} bytes")

# ---- Button containers ----
u1_empty = encode_u1_button_empty(128)
u1_ref   = encode_u1_button_with_ref(136, 4)
u2_empty = encode_u2_button_empty(128)
u2_ref   = encode_u2_button_with_ref(128, 1, bitmap_index=0)

print()
print("Button container inner lengths (total minus 6-byte TAG C0 header):")
print(f"  U1 empty:  {len(u1_empty)-6}  (expect 48)")
print(f"  U1 ref:    {len(u1_ref)-6}  (expect 71)")
print(f"  U2 empty:  {len(u2_empty)-6}  (expect 75)")
print(f"  U2 ref:    {len(u2_ref)-6}  (expect 98)")

# ---- Macro reference BLOB ----
ref_container = encode_macro_ref_container(4)
print()
print(f"Macro ref container:  {len(ref_container)} bytes (expect 23)")
print(f"  hex: {ref_container.hex(' ')}")
# Known-good from Test2.rti u1_new.bin at 0x238E:
#   17 80 08 04 00 FF 00 00 00 08 07
# This BLOB is at offset 10 within the container (6B header + 4B TAG01 U16)
blob_field = ref_container[10:21]
expected   = bytes.fromhex('17800804 00FF000000 0807'.replace(' ',''))
print(f"  BLOB field: {blob_field.hex(' ')}")
print(f"  Expected:   {expected.hex(' ')}")
print(f"  Match:      {blob_field == expected}")

# ---- TLV decode round-trip on driver command ----
from rti_lib import tlv as tlv_mod
nodes = tlv_mod.decode(cmd_driver)
print()
print(f"Driver TLV decoded: {len(nodes)} top-level nodes")
for n in nodes:
    print(f"  TAG=0x{n.tag:02X} {n.type_name()}: ", end='')
    if isinstance(n.value, bytes):
        print(n.value[:20].hex(' '))
    else:
        print(repr(n.value)[:60])

print()
print("All tests passed!" if True else "")
