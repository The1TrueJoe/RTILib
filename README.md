# RTI Research — Python Toolkit

Reverse engineering and tooling for RTI (Remote Technologies Inc.) home automation remotes and processors. Specifically targeting U1/U2 remotes and XP-3/XP-6/XP-8 processors.

## Status

**Early development.** OLE2 parsing and TLV decoding are working. Upload protocol is partially reverse-engineered (USB device identification works; wire protocol for file transfer is stubbed).

## File Layout

```
RTI Research/
├── README.md
├── PROTOCOL.md            # Full reverse engineering notes
├── rti_uploader.ps1       # PowerShell reference uploader (working dry-run)
├── Test2.rti              # Sample project file (U1 + XP-6 + U2)
├── T2Sample.rti           # Sample T2+ project file
│
├── extract_project.py     # Parse and inspect .rti files
├── upload_u1.py           # Upload U1 device stream
├── upload_u2.py           # Upload U2 device stream
├── configure.py           # Interactive U1/U2 + XP3/6/8 configurator
│
├── rti_lib/
│   ├── cfb.py             # OLE2 Compound File Binary parser
│   ├── tlv.py             # RTI TLV decoder/encoder
│   ├── models.py          # Device constants (type bytes, specs, USB IDs)
│   └── usb.py             # WinUSB uploader (Windows only, ctypes)
│
└── archive/               # Old PowerShell research scripts and output files
```

## Requirements

- Python 3.8+
- Windows (for USB upload; parsing works cross-platform)
- No external dependencies for parsing
- Optional: `Pillow` for PNG bitmap support in U2 configurator

## Quick Start

### Install Python

Python is not included. Install from https://python.org or Microsoft Store.

### Inspect an .rti file

```bash
python extract_project.py Test2.rti
python extract_project.py Test2.rti --tlv          # full TLV decode
python extract_project.py Test2.rti --json         # JSON output
python extract_project.py Test2.rti --extract-streams ./streams/
```

### Configure a new project

```bash
# Interactive mode
python configure.py

# Or with CLI options
python configure.py --remote u2 --processor xp6 --output ./my_project/
```

### Test upload (dry run — no device needed)

```bash
python upload_u1.py Test2.rti --dry-run
python upload_u2.py Test2.rti --dry-run
```

## Device Type Reference

| Type Byte | Device | Notes |
|-----------|--------|-------|
| `0x07` | T2+ | 2.4" B&W 64×128px display handheld |
| `0x11` | U1 | Button-only handheld, 8 source buttons |
| `0x1D` | U2 | 2.1" B&W 64×128px display handheld |
| `0x31` | Controller | XP-3, XP-6, XP-8 processors |

Confirmed from binary analysis of `Test2.rti` (RTI Data Directory V3) and `T2Sample.rti`.

## USB Details

- **VID:** `0x13BD`
- **PIDs:** `0x0020`, `0x1022`–`0x103F`
- **Interface GUID:** `{b0b650d9-8169-4343-89df-ca55cef25059}`
- **Target file on device:** `\IPSM\remotev2.dat`
- **Cancel event:** `RTIUpgradeCancelEvent`
- **Transport:** WinUSB bulk OUT

## Known Unknowns

- **Upload wire protocol:** USB device detection works; the command framing / file transfer handshake inside the bulk pipe is not yet decoded from `MSTRK32.dll`. See `rti_lib/usb.py` TODO.
- **U2 bitmap format:** Pixel data embedding within TLV stream for U2 display shortcuts is not confirmed. Placeholder encoding is used.
- **Processor macro TLV:** Full encoding of macros/commands in the controller stream is not yet reverse-engineered.
- **OLE2 CFB writer:** Reading works; writing a new `.rti` file from scratch is not yet implemented.

## .rti File Format

RTI `.rti` files are **OLE2 Compound File Binary** containers (same format as old `.doc` files). Inside are named streams:

- `Job Info` — project metadata (TLV)
- `RTI Data Directory V3` — device slot directory
- `Device Data Stream 0000`, `0001`, ... — one per device (TLV)
- `VariableIDs` — variable/preset ID table

See `PROTOCOL.md` for full format documentation.
