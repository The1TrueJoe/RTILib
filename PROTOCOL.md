# RTI Integration Designer — Reverse-Engineered Protocol Reference

> Status: **RESEARCH IN PROGRESS** — based on static analysis of `.rti` files and `idesign.exe`.  
> USB wire protocol is partially known; USB capture is needed to confirm packet framing.

---

## 1. Project File Format — `.rti`

### Container: OLE2 Compound File Binary (CFB)

- **Magic bytes**: `D0 CF 11 E0 A1 B1 1A E1` (standard Microsoft CFB)
- **Sector size**: 512 bytes
- **Tool to open**: `python-oletools`, `libgsf`, or any OLE2 library

### Streams inside `Test2.rti`

| Stream Name                | Size    | Location         | Notes |
|----------------------------|---------|------------------|-------|
| `RTI Data Directory V3`    | 2096 B  | Mini-stream      | Magic `0xBEEFF00D`; directory of device slots |
| `Job Info`                 | 1937 B  | Mini-stream      | X.509 cert + GPS coords + device serial |
| `Device Data Stream 0000`  | 9285 B  | FAT sectors      | Handheld remote (type `0x11`) |
| `Device Data Stream 0001`  | 6938 B  | FAT sectors      | Controller/processor (type `0x31`) |
| `Device Data Stream 0002`  | 11567 B | FAT sectors      | Touchscreen/app device (type `0x1D`) |
| `VariableIDs`              | 2 B     | Mini-stream      | `FF FF` — always |

---

## 2. TLV Encoding — Device Data Streams

Every **Device Data Stream** is encoded as a flat (then nested) TLV sequence.

### Record structure

```
[TAG : 1 byte] [TYPE : 1 byte] [VALUE : variable]
```

### TYPE codes

| Code   | Name      | Value Length | Notes |
|--------|-----------|--------------|-------|
| `0x20` | BYTE      | 1 byte       | unsigned byte |
| `0x40` | U16       | 2 bytes      | little-endian uint16 |
| `0x60` | I32       | 4 bytes      | little-endian int32 |
| `0x80` | BLOB      | `1 + N` bytes | 1-byte length prefix, then N raw bytes |
| `0xA0` | VARSTR    | `2 + N` bytes | 2-byte LE length prefix, then UTF-16LE string |
| `0xC0` | CONTAINER | `4 + N` bytes | 4-byte LE length prefix, then nested TLV records |
| `0xE0` | GUID      | 16 bytes     | fixed 16-byte raw GUID / UUID |

### Terminator

`FF FF` — two bytes that terminate a CONTAINER block.

---

## 3. Stream Header (common to all Device Data Streams)

The first ~40 bytes of every Device Data Stream form a header block:

| Offset | TAG  | TYPE | Meaning |
|--------|------|------|---------|
| 0x00   | 0x01 | 0x40 | Format version (`0x0005` observed) |
| 0x03   | 0x02 | 0x20 | Device type code (`0x11`=handheld, `0x31`=controller, `0x1D`=touchscreen) |
| 0x05   | 0x03 | 0x60 | Device model number |
| 0x0A   | 0x01 | 0xE0 | Device UUID (16 bytes) |

---

## 4. TAG meanings (Stream 0000 — handheld remote)

### Global settings section (flat TLV, before containers)

| TAG  | TYPE  | Meaning |
|------|-------|---------|
| 0x01 | U16   | Format version |
| 0x02 | BYTE  | Device type |
| 0x03 | I32   | Device model |
| 0x01 | GUID  | Device UUID |
| 0x0A | VARSTR | NTP server hostname (e.g. `time.windows.com`) |
| 0x08 | BLOB  | GPS latitude (8-byte IEEE 754 double) |
| 0x09 | BLOB  | GPS longitude (8-byte IEEE 754 double) |
| 0x0D | VARSTR | City name string |
| 0x1F | VARSTR | Device serial number / ID (e.g. `001526000000`) |
| 0x08 | VARSTR | **Indexed** — source names (idx=0,1,2,...) |
| 0x09 | VARSTR | **Indexed** — activity names |
| 0x04 | VARSTR | **Indexed** — source enables |
| 0x0C | BLOB  | **Indexed** — source colors (8-byte: `[idx:4] [ARGB:4]`) |
| 0x0F | VARSTR | **Indexed** — port/zone names |
| 0x1D | VARSTR | **Indexed** — channel data |

### Indexed VARSTR tags

For these tags, the first 2 bytes of the string data are a **little-endian uint16 index**, followed by UTF-16LE text:

```
TAG  A0  [len_lo] [len_hi]  [idx_lo] [idx_hi]  [UTF-16LE text...]
```

Tags that use this indexed format: `0x04`, `0x08`, `0x09`, `0x0C`, `0x0F`, `0x1D`

---

## 5. CONTAINER (0xC0) Structures

### Source command container (Stream 0000, 48 bytes)

One container per source × 12 command slots per source.  
Each 48-byte inner container holds one button-command assignment:

| TAG  | TYPE   | Meaning |
|------|--------|---------|
| 0x01 | I32    | Command ID (`0xFE` = unassigned) |
| 0x02 | I32    | Flags / mode bits |
| 0x03 | I32    | Always 0 |
| 0x02 | BYTE   | Channel / preset number (`0xFF` = none) |
| 0x03 | BYTE   | Flag byte |
| 0x04 | BYTE   | Flag byte |
| 0x05 | BYTE   | Flag byte |
| 0x06 | BYTE   | Flag byte |
| 0x0E | I32    | Device reference ID (`0xFFFFFFFF` = no device) |
| 0x0E | BYTE   | Device type byte |
| 0x04 | VARSTR | Command name (empty string = unassigned) |
| FF FF |       | TERMINATOR |

### Page container (Stream 0002 — touchscreen, 2877 bytes)

One container per page. Contains:
- `TAG=0x01 VARSTR` = page name (e.g. `'Home Page'`)
- N × 75-byte button containers

### Button container (Stream 0002, 75 bytes)

| TAG  | TYPE   | Meaning |
|------|--------|---------|
| 0x01 | I32    | Command ID (`0xFE` = unassigned) |
| 0x02 | I32    | Flags |
| 0x03 | I32    | Always 0 |
| 0x02 | BYTE   | Channel (`0xFF` = none) |
| 0x03 | BYTE   | Flag byte |
| 0x04 | BYTE   | Flag byte |
| 0x05 | BYTE   | Flag byte |
| 0x06 | BYTE   | Flag byte |
| 0x0E | I32    | Device reference ID (`0xFFFFFFFF` = none) |
| 0x0E | BYTE   | Device type |
| 0x04 | VARSTR | Command name |
| 0x04 | I32    | Additional flags |
| 0x07 | BYTE   | Button style/type |
| 0x08 | BYTE   | Button state |
| 0x09 | BYTE   | Repeat mode |
| 0x0C | I32    | Button position/ID (`0x0A` = 10, etc.) |
| 0x0D | I32    | Layout flags |
| FF FF |       | TERMINATOR |

---

## 6. IR Code Storage

IR codes are **NOT stored directly** in the Device Data Streams. They reside in a separate IR code library accessed via `IREng32.dll`:

- `IROpenLibrary(path)` — opens an `.irlib` database file
- `IRFetchRemoteRecord(...)` — retrieves IR timing data for a specific manufacturer/model/command
- `IRWriteRemoteRecord(...)` — writes IR data to the library
- `IRFindAllManufacturers/Models/Types(...)` — searches the library

On-device, the IR driver database is at `\IPSM\drivers.db` (SQLite format).

---

## 7. Device Filesystem (IPSM)

The device exposes an internal filesystem accessible over USB, with the following known paths:

| Path | Purpose |
|------|---------|
| `\IPSM\remotev2.dat` | Main remote configuration (uploaded file) |
| `\IPSM\remote.dat`   | Legacy format config |
| `\IPSM\t2design.dat` | T2 design data |
| `\IPSM\settings.dat` | Device settings |
| `\IPSM\drivers.db`   | SQLite IR driver database |
| `\IPSM\security.dat` | Security/pairing data |
| `\IPSM\filemeta.dat` | Filesystem metadata |
| `\IPSM\slaveid.dat`  | Slave/processor ID |
| `\IPSM\TEMP\remotev2.dat` | Staging area during upload |
| `\IPSM\%04d.js`      | JavaScript pages/scripts |
| `\IPSM\xp8data.bin`  | XP8 processor binary |
| `\IPSM\XP8Config.cfg`| XP8 processor config |
| `D:\IPSM\*`          | Same paths with `D:` drive prefix |

---

## 8. Device Operating System

RTI handheld remotes (T3, T4-V, etc.) run **Windows CE** internally.

Evidence from `IRCapEn.dll`:
- Class `CWinCECommUSBDirect` — "Windows CE USB Direct" communication
- Path `\windows\CaptureData` — WinCE filesystem path on device
- Classes `CPro24rManager`, `CPro24zManager` — Pro24R/Pro24Z protocols (hardware variants)

---

## 9. USB Transport

### Device identification

| Property | Value |
|----------|-------|
| Vendor ID (VID) | `0x13BD` (Remote Technologies Inc.) |
| Product IDs (PID) | `0x0020`, `0x1022`–`0x103F` |
| Driver | `WinUSB.sys` |
| INF file | `%SystemRoot%\System32\DriverStore\FileRepository\rtiwinusb.inf_amd64_*/rtiwinusb.inf` |
| Device Interface GUID | `{b0b650d9-8169-4343-89df-ca55cef25059}` |
| INF class GUID | `{88bae032-5a81-49f0-bc3d-a4ff138216d6}` |

### WinUSB API usage (from `idesign.exe` + `IRCapEn.dll` imports)

```
WinUsb_Initialize
WinUsb_Free
WinUsb_GetAssociatedInterface
WinUsb_QueryInterfaceSetting
WinUsb_SetCurrentAlternateSetting
WinUsb_QueryPipe
WinUsb_SetPipePolicy / WinUsb_GetPipePolicy
WinUsb_ReadPipe        ← bulk IN (device → host)
WinUsb_WritePipe       ← bulk OUT (host → device)
WinUsb_ControlTransfer ← control transfers (handshake/init)
WinUsb_ResetPipe / WinUsb_AbortPipe / WinUsb_FlushPipe
```

### USB Pipe / Endpoint

From `IRCapEn.dll`: `\PIPE00` is the bulk endpoint name **as seen from the WinCE device side**.  
On the host, `WinUsb_QueryPipe` locates the corresponding bulk OUT/IN endpoint indices.

### Registry settings (upload tuning, from `idesign.exe`)

| Registry value | Purpose |
|----------------|---------|
| `Min Send Packet Size` | Minimum bulk write chunk size in bytes |
| `Progress Bar Divisor` | `total_bytes / divisor` = number of progress bar increments |
| `Use Slow USB Transfers` | Enables conservative, slower bulk transfer mode |
| `Disable Progress Bar` | Skips UI progress updates |

### Upload sequence (from `idesign.exe` status strings)

```
1. "Uploading RTiPanel Data..."      → connect to device via WinUSB
2. "Checking version..."             → query device firmware version
3. "Receiving Bank %d..."            → read current config from device (backup)
4. "Sending New Firmware Bank %d..." → send firmware update bank(s) [optional]
5. "Sending Bank %d..."              → send configuration bank N
6. "Sending Bank 2..."               → send bank 2 specifically (config bank?)
7. "Sending system info..."          → send system configuration data
8. "Updating options..."             → write device options
9. "Beginning Firmware Update..."    → trigger flash write on device
10. "Displaying New Program..."      → device reboots / shows new config
```

Cancel: `RTIUpgradeCancelEvent` Windows named Event is set to abort the upload mid-sequence.

### IR Capture over USB (from `IRCapEn.dll` — `CWinCECommUSBDirect`)

Commands sent as **ASCII strings** to the bulk OUT endpoint:

| Command | Purpose |
|---------|---------|
| `START_CAPTURE_CARRIER` | Begin carrier frequency capture |
| `START_CAPTURE_IR` | Begin IR code timing capture |
| `PRO24Z` | Protocol variant identifier (Pro24Z hardware) |

Response:
- `CAPTURE_COMPLETE_EVENT` — a named Windows Event signaled by the driver when capture finishes
- Data file `\windows\CaptureData` on device is read back via USB after capture

IR data debug paths on PC (when debug registry key is set):
- `C:\temp\proirdata_in.bin` — raw IR timing data
- `c:\temp\proirdata-capture-%010d.bin` — per-capture dumps
- `c:\temp\proirdata-align-%010d.bin` — aligned timing data

### USB packet format — PARTIALLY KNOWN

> **⚠️ USB wire capture required** to confirm exact packet framing.  
> The following is inferred from static analysis only.

**What we know:**
- Transport: WinUSB raw bulk transfers (NOT HID, NOT CDC serial, NOT ActiveSync/WMDC)
- Direction: `WritePipe` (host → device) and `ReadPipe` (device → host)
- The device filesystem target is `\IPSM\remotev2.dat` (or `D:\IPSM\remotev2.dat`)
- IR capture commands are sent as plain ASCII strings: `"START_CAPTURE_IR"` etc.
- The upload is chunked ("Bank" = chunk or region, multiple banks sent sequentially)
- `CCommManager::requestPackets` is the low-level method for packet exchange
- `CWinCECommUSBDirect` is the USB transport class that wraps WinUSB

**What needs capture to confirm:**
- Start-of-packet magic bytes or framing (length-prefixed vs. delimiter-based)
- Command byte encoding for upload (e.g. `0x01` = write file, `0x02` = read file)
- Checksum algorithm (CRC-16? XOR? none?)
- Handshake / ACK after each packet
- Exact packet size (check `Min Send Packet Size` registry value — default probably 64 or 512)

**Recommended capture tool:** USBPcap + Wireshark (filter `usb.idVendor == 0x13BD`)

---

## 10. Runtime Control — TCP Protocol (PCEmu findings)

Beyond USB config upload, the RTI processor communicates with remotes at runtime over **TCP/HTTP**. PCEmu emulates the RTI processor and exposes this TCP interface:

| Message type | Purpose |
|---|---|
| `TT_MSG_TYPE_CONNECT_CMD` | Remote connects to processor |
| `TT_MSG_TYPE_CONNECT2_CMD` | Connect (variant 2) |
| `TT_MSG_TYPE_PING_CMD` | Keepalive heartbeat |
| `HTTPCP_MSG_TYPE_REQUEST_CMD` | HTTP command proxy request |

The **PCEmu.exe** acts as a PC-based RTI processor, receiving button-press events from the remote over TCP and driving the remote's display. This means:

- **USB** (WinUSB bulk): Config upload only — writes `\IPSM\remotev2.dat` to device
- **TCP/HTTP**: Runtime control — button events from remote, page navigation commands to remote

To build a "virtual processor" that receives button presses from the remote, implement the TCP server that speaks the `TT_MSG_TYPE_*` protocol. The exact framing needs a network capture (e.g. Wireshark on the loopback when PCEmu is running).

---

## 11. `remotev2.dat` — Upload Payload

The file written to `\IPSM\remotev2.dat` during upload is believed to be a **binary encoding of the Device Data Stream** extracted from the `.rti` file. The exact format (whether it is the raw TLV stream, a re-serialized form, or a compressed variant) needs to be confirmed by:

1. Extracting `remotev2.dat` from a programmed device via USB
2. Comparing it byte-for-byte with the `Device Data Stream 000x.bin` extracted from the `.rti` file

---

## 10. Open Questions

| Question | Status |
|----------|--------|
| Exact USB packet framing (magic bytes, length, checksum) | ❌ Needs USB capture |
| Is `remotev2.dat` the raw TLV stream or a transformed format? | ❌ Needs device read |
| What is `RTI Data Directory V3` (magic `0xBEEFF00D`) used for? | ❌ Not decoded |
| What is in `Job Info` beyond the X.509 cert? | ❌ Partially decoded |
| How does X.509 cert relate to upload authorization? | ❌ Unknown |
| How are IR codes stored in `\IPSM\drivers.db`? | ❌ Need SQLite dump |
| What "Bank" numbers correspond to which Device Data Streams? | ❌ Needs capture |
| Does `WinUsb_ControlTransfer` carry init / teardown commands? | ❌ Needs capture |

---

## 11. Tools

| Tool | Purpose |
|------|---------|
| `parse_rti.ps1` | Minimal OLE2 CFB parser (PowerShell) |
| `parse_rti_full.ps1` | Full OLE2 parser — extracts all streams to `.bin` |
| `full_decode2.ps1` | Recursive TLV decoder — produces `full_decode_output.txt` |
| `decode_streams.ps1` | Flat (non-recursive) TLV decoder |
| `find_protocol.ps1` | Extracts protocol strings from `idesign.exe` |
| `rti_uploader.ps1` | **(PLANNED)** Open-source uploader stub |
| USBPcap + Wireshark | USB traffic capture for protocol confirmation |

---

*Last updated: reverse engineering session, 2025.*
