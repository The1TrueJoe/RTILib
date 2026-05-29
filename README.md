# rti_lib — RTI Integration Designer Toolkit

A pure-Python library for programmatically building `.rti` project files for RTI home automation remotes and processors.

**No Integration Designer required at build time** — this library encodes the full binary format from scratch, including image compression, TLV records, and OLE2 container structure.

> **Confirmed working:** Generated files open and display correctly in RTI Integration Designer, including full-colour background images on the T2i touchscreen.

---

## What This Does

RTI `.rti` project files are OLE2 Compound File Binary containers (the same low-level format as old `.doc` files). Each device — processor and remotes — stores its configuration as a stream of custom TLV (Tag-Length-Value) binary records inside named streams in that container.

This library:
- **Encodes the complete TLV wire format** from scratch, including all 350 header fields shared by every RTI remote type
- **Builds OLE2/CFB containers** without any external dependencies (no `olefile`, no `compoundfiles`)
- **Encodes T2i background images**: raw RGB → bottom-up BGR → zlib compress → BITMAPINFOHEADER → nested TLV CONT
- **Provides a graphic design layer** for building Oasis-style button layouts with icon loading, gradient backgrounds, and rounded-rect chips
- **Ships a reverse-engineering toolkit** for diffing and decoding existing `.rti` files field-by-field

---

## Supported Devices

| Device   | Type byte | Display                        | Notes |
|----------|-----------|--------------------------------|-------|
| T2i      | `0x4B`    | 240×320 24-bit colour touchscreen | **Fully supported**, with image encoding |
| U2       | `0x1D`    | 64×128 2-bit mono              | Supported |
| U1       | `0x11`    | None (button-only)             | Supported |
| XP-3/6/8 | `0x31`   | — (processor)                  | Macro/command encoding |

---

## Quick Start

### Prerequisites

```bash
pip install Pillow   # required for image encoding and ButtonDesigner
```

Python 3.10+ required.

### Minimal T2i project

```python
from rti_lib import RTIProject, T2iRemote
from rti_lib.devices.xp import XPProcessor

xp  = XPProcessor('XP-6', display_name='Living Room AV')
m1  = xp.add_macro('Watch TV', serial=b'src hdmi1\r', baud=9600, port=0,
                    device_name='AV Receiver', manufacturer='Generic', model_str='AVR')

t2i = T2iRemote(display_name='Living Room')
t2i.add_source_button('Watch TV', macro=m1, x=0, y=80, w=120, h=80)

proj = RTIProject()
proj.add_device(xp)
proj.add_device(t2i)
proj.save('my_project.rti')
```

### Oasis gradient background with icons

```python
from rti_lib.assets.icon_library import IconLibrary
from rti_lib.assets.button_designer import ButtonDesigner, Style

TEMPLATE_DIR = r'C:\Program Files (x86)\RTI\Integration Designer\Templates'

# Load icons from the bundled RTI template library
lib      = IconLibrary.load(TEMPLATE_DIR + r'\Source and Zone Icons.rtitemplate')
icon_png = lib.get_png('Icon (112x112) - Cable')

# Generate Oasis-style gradient background (240×320 raw RGB bytes)
bg_rgb   = ButtonDesigner.background(Style.OASIS)

# Generate a rounded-rect button chip with an icon
chip_png = ButtonDesigner.button_chip(
    width=115, height=78, label='Cable TV',
    style=Style.OASIS, icon_png=icon_png,
)

# Composite the chip onto the background and assign it to the T2i
bg_rgb = ButtonDesigner.composite(bg_rgb, chip_png, x=3, y=38)
t2i.set_background(bg_rgb)
```

### Running the examples

```bash
# Simple T2i project with gradient background + all hardware buttons
python examples/basic_t2i_project.py

# Full Oasis home screen with library icons, chips, and all hardware buttons
python examples/oasis_home_screen.py
```

Both write a `.rti` file to `examples/` that opens directly in RTI Integration Designer.

---

## Library Structure

```
rti_lib/
├── __init__.py             Public surface: RTIProject, T2iRemote, XPProcessor, …
│
├── core/
│   ├── tlv.py              TLV encode / decode (the RTI binary wire format)
│   ├── cfb.py              OLE2/CFB container reader
│   ├── cfb_writer.py       OLE2/CFB container writer
│   ├── fields.py           Named field constants + 350-field stream registry
│   └── models.py           Device-type byte constants
│
├── devices/
│   ├── common.py           Shared TLV builders (button CONT, group headers)
│   ├── xp/                 XP processor — XPProcessor, Macro
│   ├── u1/                 U1 button-only handheld — U1Remote
│   ├── u2/                 U2 mono touchscreen — U2Remote, BMLFile
│   └── t2i/
│       ├── remote.py       T2iRemote — high-level API
│       ├── stream_profile.py  T2i base stream builder + image encoder
│       ├── encoders.py     Low-level button CONT encoder
│       └── image.py        load_image_rgb() convenience wrapper
│
├── assets/
│   ├── icon_library.py     IconLibrary — reads icons from .rtitemplate files
│   ├── image_loader.py     ImageLoader — any-source → raw RGB bytes
│   └── button_designer.py  ButtonDesigner — gradient backgrounds, button chips
│
├── project/
│   ├── project.py          RTIProject — assembles devices, writes .rti
│   └── metadata.py         Job Info, VariableIDs, RTI Data Directory V3
│
└── tools/
    ├── stream_diff.py      Stream diff / annotated decode tool
    └── browse_template.py  Icon-library browser (list, grid, HTML sheet, export)
```

---

## API Reference

### RTIProject

```python
proj = RTIProject()
proj.add_device(xp)    # → Device Data Stream 0000
proj.add_device(t2i)   # → Device Data Stream 0001
size = proj.save('my_project.rti')   # returns bytes written
```

### XPProcessor

```python
xp = XPProcessor('XP-6', display_name='Living Room AV')

macro = xp.add_macro(
    name='Watch TV',
    serial=b'src hdmi1\r',
    baud=9600,
    port=0,                  # RS-232 port index
    device_name='Receiver',
    manufacturer='Denon',
    model_str='AVR-X3700H',
)
```

### T2iRemote

```python
t2i = T2iRemote(display_name='Living Room')

# Background image (240×320 raw RGB bytes — use ImageLoader or ButtonDesigner)
t2i.set_background(rgb_bytes)

# Home page: touchscreen buttons (register touch region + macro)
t2i.add_source_button('Watch TV', macro=m, x=0, y=80, w=120, h=80)
t2i.assign_button(index=128, label='Watch TV', macro=m, x=0, y=80, w=120, h=80)

# Secondary page (swipe or nav button to reach)
t2i.add_secondary_button('Play', macro=m_play, x=0, y=60, w=120, h=60)

# Physical hardware buttons (apply to every page regardless of touch layout)
t2i.assign_hw_button_macro(index=138, macro=m_volup)   # Vol+ physical button

stream = t2i.build_stream()   # → raw TLV bytes
```

### IconLibrary

```python
from rti_lib.assets.icon_library import IconLibrary

TEMPLATE_DIR = r'C:\Program Files (x86)\RTI\Integration Designer\Templates'
lib = IconLibrary.load(TEMPLATE_DIR + r'\Source and Zone Icons.rtitemplate')

print(lib.summary())   # 'IconLibrary("Source and Zone Icons", 1230 images, 112x112px)'
png = lib.get_png('Icon (112x112) - Cable')          # normal / up state
png = lib.get_png('Icon (112x112) - Cable', 'down')  # pressed / down state
up, down = lib.get_all_png('Icon (112x112) - Cable')

for entry in lib:   # iterate ImageEntry dataclass objects
    print(entry.name, entry.width, entry.height)
```

### ImageLoader

```python
from rti_lib.assets.image_loader import ImageLoader

rgb = ImageLoader.from_file('photo.jpg')                    # any Pillow-readable file
rgb = ImageLoader.from_bytes(png_data)                      # from memory
rgb = ImageLoader.from_library_entry(lib, 'Icon (112x112) - Cable')

rgb = ImageLoader.solid(r=20, g=30, b=80)
rgb = ImageLoader.gradient_v(top=(10, 20, 60), bottom=(100, 200, 160))
rgb = ImageLoader.gradient_h(left=(10, 20, 60), right=(40, 100, 120))
rgb = ImageLoader.gradient_radial(center=(60, 180, 200), edge=(5, 10, 30))
rgb = ImageLoader.overlay_png(bg_rgb, chip_png, x=3, y=38)
```

All methods return `width × height × 3` raw RGB bytes (top-to-bottom), ready for `t2i.set_background()`.

### ButtonDesigner

```python
from rti_lib.assets.button_designer import ButtonDesigner, Style

# Available styles: Style.OASIS, Style.DARK_STEEL, Style.NIGHT_BLUE, Style.MINIMAL

# Full-screen background → raw RGB bytes
bg_rgb = ButtonDesigner.background(Style.OASIS)
bg_rgb = ButtonDesigner.background(Style.OASIS, width=240, height=320,
                                   icon_png=png_bytes, icon_x=89, icon_y=137)

# Rounded-rect button chip → PNG bytes with RGBA transparency
chip_png = ButtonDesigner.button_chip(
    width=115, height=78, label='Cable TV',
    style=Style.OASIS, font_size=11, icon_png=icon_png,
)

# Paste a chip (alpha-composite) onto a background
rgb = ButtonDesigner.composite(bg_rgb, chip_png, x=3, y=38)

# Save or retrieve as PNG
ButtonDesigner.save_preview(rgb, 'preview.png')
png_bytes = ButtonDesigner.preview_png(rgb)
```

---

## Tools

### Stream diff / decoder

Compare two `.rti` files field-by-field — invaluable for reverse-engineering unknown fields:

```bash
# Show only changed fields across all device streams
python -m rti_lib.tools.stream_diff before.rti after.rti

# Diff a specific device slot (0-based)
python -m rti_lib.tools.stream_diff before.rti after.rti --slot 0

# Show all fields including identical ones
python -m rti_lib.tools.stream_diff before.rti after.rti --all

# Annotated decode of a single stream
python -m rti_lib.tools.stream_diff --print project.rti --slot 0
```

Example diff output:

```
RTI Stream Diff
  A: before.rti
  B: after.rti

====================================================================================================
Slot 0001  A=U2 (0x1D)  B=T2i (0x4B)
pos    tag    type        field name                    A value  ->  B value
----------------------------------------------------------------------------------------------------
    0  0x01   BYTE        device_type                   29  (U2)
                                                     -> 75  (T2i)
   11  0x2D   BYTE        ui_version                    1  (mono B&W (U1/U2))
                                                     -> 2  (colour (T2i))
  Summary: 7 difference(s), 343 identical record(s)
```

### Icon library browser

Explore and export icons from RTI's bundled `.rtitemplate` icon libraries:

```bash
# List all images in a library
python -m rti_lib.tools.browse_template list "Source and Zone Icons.rtitemplate"

# Save a single icon as PNG
python -m rti_lib.tools.browse_template get "Source and Zone Icons.rtitemplate" "Icon (112x112) - Cable" cable.png

# Export all icons to a folder
python -m rti_lib.tools.browse_template export "Source and Zone Icons.rtitemplate" ./icons/

# Generate a PNG contact sheet
python -m rti_lib.tools.browse_template grid "Source and Zone Icons.rtitemplate" grid.png

# Generate an HTML contact sheet (hover shows pressed state, filterable)
python -m rti_lib.tools.browse_template sheet "Source and Zone Icons.rtitemplate" sheet.html
```

Bare filenames are automatically resolved against:
`C:\Program Files (x86)\RTI\Integration Designer\Templates\`

---

## Inspect an Existing .rti File

### Inspect an .rti file

```bash
python extract_project.py Test2.rti
python extract_project.py Test2.rti --tlv          # full TLV decode
python extract_project.py Test2.rti --json         # JSON output
python extract_project.py Test2.rti --extract-streams ./streams/
```

---

## Named Field Constants

All 350 common header positions are named in `rti_lib/core/fields.py`. Import them in device-stream code to avoid raw magic numbers:

```python
from rti_lib.core.fields import CFG_HAS_TOUCHSCREEN, NET_HAS_COLOR, STREAM_FIELDS

# Look up a field definition by stream position
fdef = STREAM_FIELDS[28]   # pos 28 = has_touchscreen
print(fdef.name)            # 'has_touchscreen'
print(fdef.description)     # 'Has touchscreen display'
print(fdef.known_values)    # {0: 'no', 1: 'yes'}
```

The diff tool uses these names as column headers so the output is immediately readable without cross-referencing source code.

---

## Known Limitations

- **USB upload not implemented.** Generating `.rti` files works fully; pushing them directly to a device over USB requires the USB bulk-pipe handshake, which has not yet been reverse-engineered. Use Integration Designer's built-in sync for now.
- **Read-back is partial.** `cfb.py` and `tlv.py` can decode any `.rti` file for inspection; modifying and re-saving an existing project (round-trip) is not yet supported.
- **T4/T4+ not yet supported.** The T4 uses a different page-layout container structure.

---

## Binary Format

See [`PROTOCOL.md`](PROTOCOL.md) for the complete binary format reference, including:
- OLE2/CFB stream layout
- TLV type codes and encoding rules
- The 350-field common device stream header
- T2i image CONTAINER encoding (zlib + BITMAPINFOHEADER + GUID sentinel)
- Button CONT structure and hardware slot map

