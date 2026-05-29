# RTI Binary Format Reference

This document describes the binary format of RTI `.rti` project files as reverse-engineered from Integration Designer output. All findings are confirmed by generating files that Integration Designer accepts and displays correctly.

---

## 1. Container Format — OLE2/CFB

`.rti` files are standard **OLE2 Compound File Binary** (CFB) containers, identical in structure to old `.doc` files. The format is fully specified in [\[MS-CFB\]](https://docs.microsoft.com/en-us/openspecs/windows_protocols/ms-cfb/).

Key parameters for RTI files:
- Version: CFB v3
- Sector size: 512 bytes
- Mini-sector size: 64 bytes
- Mini-stream cutoff: 4096 bytes (streams < 4096 bytes go in the mini-stream)

### Named Streams

| Stream name | Content |
|---|---|
| `Job Info` | Project metadata: GPS location, timezone, NTP server (TLV) |
| `RTI Data Directory V3` | Device catalogue: slot count, display names, timestamps |
| `Device Data Stream 0000` | First device — usually the XP processor (TLV) |
| `Device Data Stream 0001` | Second device — first remote (TLV) |
| `Device Data Stream NNNN` | Each additional device |
| `VariableIDs` | Variable/preset ID registry; `FF FF` if empty |

All stream names are UTF-16LE in the directory entry (standard CFB).

---

## 2. TLV Wire Format

Every Device Data Stream is a flat sequence of **TLV records**:

```
[TAG : 1 byte] [TYPE : 1 byte] [VALUE : variable]
```

The stream terminates with the sentinel `FF FF`. A single `FF` byte also terminates.

### Type codes

| Type byte | Name | Value layout |
|---|---|---|
| `0x20` | `BYTE` | 1 byte unsigned |
| `0x40` | `U16` | 2 bytes little-endian unsigned |
| `0x60` | `I32` | 4 bytes little-endian signed |
| `0x80` | `BLOB` | 1-byte length prefix + N data bytes |
| `0xA0` | `VARSTR` | 2-byte LE length prefix + N bytes (usually UTF-16LE) |
| `0xC0` | `CONTAINER` | 4-byte LE length prefix + nested TLV bytes |
| `0xE0` | `GUID` | 16 bytes fixed (used loosely — see image encoding) |

### Tag byte reuse

The same tag byte value appears many times with completely different meanings depending on its **position** in the stream. There is no global tag-to-field mapping. The 350 named positions are catalogued in `rti_lib/core/fields.py`.

### Indexed VARSTR

Certain tags use a VARSTR where the first 2 bytes of the value are a `uint16` index rather than text. Known indexed tags: `0x04`, `0x08`, `0x09`, `0x0C`, `0x0F`, `0x1D`.

Tag `0x0F` adds an additional `FF FF` separator after the index before the UTF-16LE text.

---

## 3. Device Stream Header (350 Common Fields)

Every device stream (U1, U2, T2i, T2+, XP) begins with the same sequence of 350 TLV records. The fields divide into four sections:

### 3.1 Device Config (positions 0–36)

Critical fields that differentiate device types:

| Position | Tag | Type | Field | T2i value | U2 value |
|---|---|---|---|---|---|
| 0 | `0x01` | BYTE | `device_type` | `0x4B` (75) | `0x1D` (29) |
| 9 | `0x0B` | BYTE | `has_physical_buttons` | 0 | 1 |
| 11 | `0x2D` | BYTE | `ui_version` | 2 (colour) | 1 (mono) |
| 16 | `0x01` | I32 | `idle_timeout_ms` | 25000 | 25000 |
| 28 | `0x16` | BYTE | `has_touchscreen` | 1 | 0 |

### 3.2 Network / Location (positions 37–53)

Includes NTP server (VARSTR), protocol GUID (fixed 16 bytes), latitude/longitude BLOBs, and location name (VARSTR).

| Position | Tag | Type | Field |
|---|---|---|---|
| 41 | `0x02` | GUID | `protocol_guid` — shared across all device types |
| 44 | `0x0D` | VARSTR | `location` — room name string |
| 46 | `0x25` | BYTE | `has_color` — 1 for T2i, 0 for mono remotes |
| 49 | `0x0D` | BLOB | `device_guid` — 16-byte unique device identifier |

### 3.3 Device Identity (positions 54–55)

| Position | Tag | Type | Field |
|---|---|---|---|
| 54 | `0x1F` | VARSTR | `mac_address` — 12 hex chars, e.g. `001526000000` |
| 55 | `0x03` | BLOB | `serial` — device serial number (usually `b'0000'`) |

### 3.4 Slot Layout (positions 56–349)

Positions 56–349 define the button/variable slot table. For a T2i with 52 hardware buttons:

- **pos 56–64**: 9 × U16 `input_slot_idx` records (values 256–264)
- **pos 65–68**: 4 × I32 `page_group_id` records
- **pos 69–84**: 16 × indexed VARSTR `group_name` records
- **pos 85–92**: 8 × BLOB `group_state` records
- **pos 93–348**: 256 × indexed VARSTR `variable_name` records
- **pos 349**: BLOB `page_cap_sentinel` — `0x0A` tag for T2i, `0x06` for U2/U1

---

## 4. T2i Page Layout (after the 350-field header)

After position 349, the T2i stream contains two CONTAINER nodes:

```
[BLOB tag=0x0A] — page-cap sentinel (9 bytes)
[CONT tag=0x01] — home page CONTAINER
[CONT tag=0x02] — secondary page CONTAINER
```

### Home Page CONTAINER (tag=0x01)

```
BYTE(01)  = 2
BYTE(02)  = 0
VARSTR(01) = page display name (UTF-16LE)
I32(01)   = 0x00FFFFFF  (observed constant)
[CONT tag=0x02] = image CONTAINER (optional)
BYTE(03)  = 2 (with image) or 1 (without)
BYTE(04)  = 0
[button CONT records × 52]
FF FF
```

### Secondary Page CONTAINER (tag=0x02)

Same structure as home page without the image CONTAINER.

### Button CONTAINER (tag=0x01, per button)

Each button occupies one CONTAINER within its page:

```
BYTE(03)  = button slot index (128–179)
BYTE(04)  = 0
BYTE(05)  = 1
VARSTR(01) = button label (UTF-16LE)
[I32 touch rect: x, y, w, h — when non-zero]
[macro reference — when assigned]
FF FF
```

---

## 5. T2i Hardware Button Slot Map (indices 128–179)

The T2i has 52 physical button slots. Each slot corresponds to a hardware function:

| Index | Function | Index | Function | Index | Function |
|---|---|---|---|---|---|
| 128 | Exit | 143 | Menu | 158 | 5 |
| 129 | Mute | 144 | Info | 159 | 6 |
| 130 | Softkey 2 | 145 | Power Off | 160 | 7 |
| 131 | Up | 146 | Play | 161 | 8 |
| 132 | Left | 147 | Pause | 162 | 9 |
| 133 | Right | 148 | Stop | 163 | 0 |
| 134 | Down | 149 | Record | 164 | -/. |
| 135 | OK / Select | 150 | Scan << | 165 | Enter |
| 136 | Softkey 1 | 151 | Scan >> | 166 | Joystick Up |
| 137 | Softkey 4 | 152 | Skip << | 167 | Joystick Click |
| 138 | Vol+ | 153 | Skip >> | 168 | Joystick Down |
| 139 | Vol- | 154 | 1 | 169 | Joystick Left |
| 140 | Ch+ | 155 | 2 | 170 | Joystick Right |
| 141 | Ch- | 156 | 3 | 171 | Power On |
| 142 | Guide | 157 | 4 | 172 | List |
| | | 173 | Red | 177 | Softkey 3 |
| | | 174 | Green | 178 | Prev |
| | | 175 | Yellow | 179 | Back |
| | | 176 | Blue | | |

---

## 6. T2i Image Encoding

Background images are stored inside the home page CONTAINER as a nested CONTAINER (tag=`0x02`). The encoding is non-standard — it uses a "GUID" TLV node as a deliberate size-header, then appends the zlib stream outside the node boundary.

### Pixel preparation

1. Start with raw **RGB top-to-bottom** pixel data (width × height × 3 bytes)
2. Convert to **BGR bottom-up**: reverse row order, swap R↔B within each pixel
3. **zlib compress** at level 1 (speed over size; RTI is picky about level)

### Hash computation

```
hash[0:4] = CRC32(BGR bottom-up pixels), little-endian uint32
hash[4:8] = 0x00 × 4
```

### Inner CONTAINER structure

The `CONT(tag=0x02)` inner bytes are assembled as:

```
I32(01)   = uncomp_size           (total uncompressed byte count)
I32(02)   = -1                    (observed constant)
BLOB(01)  = hash[0:8]             (8-byte image hash)
VARSTR(01)= BITMAPINFOHEADER[40] + 0x00*4   (44 bytes raw, not UTF-16LE)
[01 E0]   = fake GUID tag+type
  [4B]    = uncomp_size (uint32 LE)
  [4B]    = comp_size   (uint32 LE — full zlib stream length)
  [8B]    = compressed[0:8]  (first 8 bytes of zlib stream)
[rest]    = compressed[8:]   (remainder of zlib stream)
FF FF                            (required inner terminator)
```

The "GUID" node (`0x01 0xE0`) is 16 bytes by definition, but the zlib stream continues directly after it, past the CONTAINER boundary. RTI's decoder reads past the node boundary to extract the full compressed data.

### BITMAPINFOHEADER

Standard 40-byte Windows BITMAPINFOHEADER (little-endian):

```c
struct {
    uint32 biSize        = 40;
    int32  biWidth       = width;
    int32  biHeight      = height;   // positive = bottom-up (BMP convention)
    uint16 biPlanes      = 1;
    uint16 biBitCount    = 24;
    uint32 biCompression = 0;        // BI_RGB
    uint32 biSizeImage   = 0;
    int32  biXPelsPerMeter = 0;
    int32  biYPelsPerMeter = 0;
    uint32 biClrUsed     = 0;
    uint32 biClrImportant = 0;
} + uint32(0)                        // 4 zero padding bytes (44 bytes total)
```

---

## 7. Icon Library Template Format (.rtitemplate)

RTI ships icon libraries as `.rtitemplate` files. These are also OLE2/CFB containers with a different internal structure:

| Stream name | Content |
|---|---|
| `RTIBitmapIndex` | UTF-8 XML listing all images with up/down stream names |
| `IMAGE000001.png` | Raw PNG bytes for image 1 up state |
| `IMAGE000002.png` | Raw PNG bytes for image 1 down state |
| … | … |

### RTIBitmapIndex XML structure

```xml
<bitmaplibraryindex>
  <bitmaplibrary name="Source and Zone Icons">
    <image name="Icon (112x112) - Cable"
           up="IMAGE000001.png"
           down="IMAGE000002.png"
           width="112" height="112"/>
    …
  </bitmaplibrary>
</bitmaplibraryindex>
```

`rti_lib/assets/icon_library.py` parses this format and provides `get_png(name, state)` for direct access.

---

## 8. Reverse Engineering Workflow

The `stream_diff` tool (`rti_lib/tools/stream_diff.py`) supports a systematic approach:

1. Open a baseline project in Integration Designer and save it.
2. Make **one change** (e.g. enable the touchscreen flag) and save again.
3. Run `python -m rti_lib.tools.stream_diff before.rti after.rti`.
4. The diff shows the exact byte position, tag, type, old value, and new value.
5. Add the confirmed field to `STREAM_FIELDS` in `rti_lib/core/fields.py`.

The 350-field common header was fully mapped this way. All field names and descriptions in `fields.py` are the result of this process.
