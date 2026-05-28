# RTI Research — Python Toolkit

Tooling for RTI home automation remotes and processors. Specifically targeting U1/U2 remotes and XP-3/XP-6/XP-8 processors.


## Quick Start

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

## Device Type Reference

| Type Byte | Device | Notes |
|-----------|--------|-------|
| `0x07` | T2+ | 2.4" B&W 64×128px display handheld |
| `0x11` | U1 | Button-only handheld, 8 source buttons |
| `0x1D` | U2 | 2.1" B&W 64×128px display handheld |
| `0x31` | Controller | XP-3, XP-6, XP-8 processors |


## Limitations

- **USB upload:** The command framing and file transfer handshake over the USB bulk pipe is not yet implemented. Creating `.rti` files works fully; pushing them to a device requires further work.

## .rti File Format

RTI `.rti` files are **OLE2 Compound File Binary** containers (same format as old `.doc` files). Inside are named streams:

- `Job Info` — project metadata (TLV)
- `RTI Data Directory V3` — device slot directory
- `Device Data Stream 0000`, `0001`, ... — one per device (TLV)
- `VariableIDs` — variable/preset ID table

See `PROTOCOL.md` for full format documentation.
