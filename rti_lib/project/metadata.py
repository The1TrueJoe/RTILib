"""
rti_lib/project/metadata.py — RTI project metadata stream builders.

Three streams appear in every .rti file alongside the device data:

  Job Info (TLV)
      Contains GPS location, timezone, and system metadata decoded from a
      reference project (Minneapolis, MN).  This is static — Integration
      Designer reads but does not validate the content.

  VariableIDs (2 bytes)
      Always FF FF (empty TLV terminator).  Stores variable-ID registrations
      for driver variables; empty means no variables are defined.

  RTI Data Directory V3 (binary)
      A fixed-layout binary table listing every device in the project.
      Each 686-byte entry holds: device type, manufacturer name, device name,
      project name, and a Unix timestamp.
      Header: 38 bytes  (magic + version + device count LE uint16)
      Entry layout (offsets are within the 686-byte entry):
        [0x000] = 0x01                 (valid flag)
        [0x001] = device_type_byte     (0x31=XP, 0x11=U1, 0x1D=U2)
        [0x009:0x089] UTF-16LE manufacturer name (128 bytes, null-terminated)
        [0x089:0x109] UTF-16LE device name       (128 bytes, null-terminated)
        [0x109:0x189] UTF-16LE project name      (128 bytes, null-terminated)
        [0x21d:0x221] Unix timestamp LE uint32
"""

import struct
import time as _time
from rti_lib.devices.common import encode_profile
from rti_lib.core import tlv

JOB_INFO_PROFILE = [('varstr_raw', 20, ''),
 ('varstr_raw', 21, ''),
 ('varstr_raw', 22, ''),
 ('varstr_raw', 23, ''),
 ('varstr_raw', 24, ''),
 ('varstr_raw', 25, ''),
 ('varstr_raw', 26, ''),
 ('varstr_raw', 27, ''),
 ('varstr_raw', 28, ''),
 ('varstr_raw', 29, ''),
 ('varstr_raw', 30, ''),
 ('varstr_raw', 31, ''),
 ('varstr_raw', 32, ''),
 ('varstr_raw', 33, ''),
 ('varstr_raw', 34, ''),
 ('varstr_raw', 35, ''),
 ('varstr_raw', 36, ''),
 ('varstr_raw', 37, ''),
 ('i32', 1, 0),
 ('varstr_raw', 38, ''),
 ('byte', 1, 0),
 ('blob', 1, '6ebc2f79dea6ae4d92ce78343911c809'),
 ('varstr_raw',
  39,
  '52004e005700410077006900490054005400360068003800340061006e007e0048005700620075006d00690040005700'),
 ('varstr_raw', 43, ''),
 ('i32', 3, -1),
 ('i32', 2, -1),
 ('varstr_raw',
  40,
  '0100010610334a0600000000000000000000b3000200000000000000090000000000b300dc01b3000000000040000000b40eb3000000000000006003b00eb300000000007cf34f00ae60997740000000ae60997700000000000000003302df5b40000000100000009cf34f006902df5b00006003000000004000000060f54f00c855a71d6ffb83d7d9e0721cf4d0abedcafd2482c42e91dd707b8885fd441605b60c88d474af828c2f0a0be70e417cc887992da648b0418c0c27b4fbe8b0a7329ed3f919cdeefe889d12b7c77289eaef7daee4031fbc8ae378c1ff64f1b4f3cf49ce09d43c7aea5d4afb8a9f6ee442a2fcd52d3f1e3ba87b99c30f8dbabd5b83'),
 ('varstr_raw',
  41,
  '2746236cf1f72cf1b414fc4a10f497c0167b6a1cf8b8e87fb0fd86d63dc08b50b34fe1c344dce38af7edd0478bd3ead2a542b26056ffb6d9edc81b0307ab1a1bc993657084547addcfe965af05abce6d71881c5c8d046fd5801c4f09381966b8b5f0acec5f744d6e76b78c66faf32075f8883da38cc4b37d508343d179599d01c855a71d6ffb83d7d9e0721cf4d0abedcafd2482c42e91dd707b8885fd441605b60c88d474af828c2f0a0be70e417cc887992da648b0418c0c27b4fbe8b0a7329ed3f919cdeefe889d12b7c77289eaef7daee4031fbc8ae378c1ff64f1b4f3cf49ce09d43c7aea5d4afb8a9f6ee442a2fcd52d3f1e3ba87b99c30f8dbabd5b83'),
 ('varstr_raw',
  44,
  '308202cb30820234a003020102020900ba2e18f6694a8e1f300d06092a864886f70d01010505003050310b300906035504061302555331123010060355040813094d696e6e65736f74613111300f060355040713085368616b6f706565310c300a060355040a1303525449310c300a060355040b13035254493020170d3236303532363036313531375a180f32303736303531333036313531375a3050310b300906035504061302555331123010060355040813094d696e6e65736f74613111300f060355040713085368616b6f706565310c300a060355040a1303525449310c300a060355040b130352544930819f300d06092a864886f70d010101050003818d0030818902818100c855a71d6ffb83d7d9e0721cf4d0abedcafd2482c42e91dd707b8885fd441605b60c88d474af828c2f0a0be70e417cc887992da648b0418c0c27b4fbe8b0a7329ed3f919cdeefe889d12b7c77289eaef7daee4031fbc8ae378c1ff64f1b4f3cf49ce09d43c7aea5d4afb8a9f6ee442a2fcd52d3f1e3ba87b99c30f8dbabd5b830203010001a381aa3081a7301d0603551d0e04160414da39a3ee5e6b4b0d3255bfef95601890afd8070930780603551d230471306f8014da39a3ee5e6b4b0d3255bfef95601890afd80709a154a4523050310b300906035504061302555331123010060355040813094d696e6e65736f74613111300f060355040713085368616b6f706565310c300a060355040a1303525449310c300a060355040b1303525449820100300c0603551d13040530030101ff300d06092a864886f70d0101050500038181001b0ac4af8f834d99201a4834dc35939fea51c74687e6f9f02f5011a880731cb9c8aadf4c5aca73119649a034ca703b563ef84ea9fb420c9f93721f75e2f1f1ab47beb67b6111314c295be1c028ad927cdb0ed9a2fad16bb93f4a77072d68c376c13a72666bc7fe8c5dd6f212c8a30bbffc2e902f0c5e5ca9f39aa02a009340a9'),
 ('varstr_raw',
  45,
  '0100010610334a0600000000000000000000b3000200000000000000090000000000b300dc01b3000000000040000000b40eb3000000000000006003b00eb300000000007cf34f00ae60997740000000ae60997700000000000000003302df5b40000000100000009cf34f006902df5b00006003000000004000000060f54f00c855a71d6ffb83d7d9e0721cf4d0abedcafd2482c42e91dd707b8885fd441605b60c88d474af828c2f0a0be70e417cc887992da648b0418c0c27b4fbe8b0a7329ed3f919cdeefe889d12b7c77289eaef7daee4031fbc8ae378c1ff64f1b4f3cf49ce09d43c7aea5d4afb8a9f6ee442a2fcd52d3f1e3ba87b99c30f8dbabd5b83'),
 ('varstr_raw',
  46,
  '2746236cf1f72cf1b414fc4a10f497c0167b6a1cf8b8e87fb0fd86d63dc08b50b34fe1c344dce38af7edd0478bd3ead2a542b26056ffb6d9edc81b0307ab1a1bc993657084547addcfe965af05abce6d71881c5c8d046fd5801c4f09381966b8b5f0acec5f744d6e76b78c66faf32075f8883da38cc4b37d508343d179599d01c855a71d6ffb83d7d9e0721cf4d0abedcafd2482c42e91dd707b8885fd441605b60c88d474af828c2f0a0be70e417cc887992da648b0418c0c27b4fbe8b0a7329ed3f919cdeefe889d12b7c77289eaef7daee4031fbc8ae378c1ff64f1b4f3cf49ce09d43c7aea5d4afb8a9f6ee442a2fcd52d3f1e3ba87b99c30f8dbabd5b83')]


def build_job_info_stream() -> bytes:
    """Build the Job Info stream (31 TLV records + FF FF terminator)."""
    return encode_profile(JOB_INFO_PROFILE) + tlv.TERMINATOR


def build_variable_ids_stream() -> bytes:
    """Build the VariableIDs stream — always just the TLV terminator FF FF."""
    return tlv.TERMINATOR


# ---------------------------------------------------------------------------
# RTI Data Directory V3 builder
# ---------------------------------------------------------------------------

_DIR_HEADER_MAGIC = b'\x0d\xf0\xef\xbe\x1a\x00\x00\x00' + b'\x00' * 28
_DIR_ENTRY_SIZE = 686


def _utf16le_field(text: str, field_bytes: int = 128) -> bytes:
    """Encode *text* as UTF-16LE, null-terminated, zero-padded to *field_bytes*."""
    enc = text.encode('utf-16-le')
    enc = enc[:field_bytes - 2]          # leave 2 bytes for the null terminator
    return enc + b'\x00\x00' + b'\x00' * (field_bytes - len(enc) - 2)


def _make_directory_entry(device_type: int, manufacturer: str,
                          device_name: str, project_name: str = '',
                          timestamp: int = None) -> bytes:
    """Build one 686-byte device entry for the RTI Data Directory V3."""
    if timestamp is None:
        timestamp = int(_time.time())
    entry = bytearray(_DIR_ENTRY_SIZE)
    entry[0x000] = 0x01                                   # valid flag
    entry[0x001] = device_type                            # device type byte
    entry[0x009:0x089] = _utf16le_field(manufacturer, 128)
    entry[0x089:0x109] = _utf16le_field(device_name,  128)
    entry[0x109:0x189] = _utf16le_field(project_name, 128)
    struct.pack_into('<I', entry, 0x21d, timestamp & 0xFFFFFFFF)
    return bytes(entry)


def build_directory_stream(device_entries, project_name: str = '') -> bytes:
    """
    Build the RTI Data Directory V3 stream.

    *device_entries* is a sequence of ``(device_type_byte, manufacturer, device_name)``
    tuples, one per device, in the same order as the Device Data Streams.
    """
    ts = int(_time.time())
    header  = _DIR_HEADER_MAGIC + struct.pack('<H', len(device_entries))
    entries = b''.join(
        _make_directory_entry(dt, mfr, name, project_name, ts)
        for dt, mfr, name in device_entries
    )
    return header + entries
