<#
.SYNOPSIS
    RTI Remote USB Uploader (Open Source Stub)

.DESCRIPTION
    Uploads a Device Data Stream to an RTI remote via WinUSB.
    
    THIS IS A RESEARCH STUB ??? the USB packet framing protocol is not yet fully
    reversed. The parts marked "TODO: USB CAPTURE NEEDED" require a USB protocol
    capture (USBPcap + Wireshark, filter usb.idVendor == 0x13BD) to fill in.

    What IS known and implemented:
    - OLE2 CFB file parsing (reads .rti files)
    - TLV stream extraction  
    - WinUSB device enumeration (find device by Interface GUID)
    - WinUSB initialization and pipe query
    - Chunked bulk transfer framework

    What STILL needs USB capture to confirm:
    - Exact packet framing (magic bytes, length field, checksum)
    - Command byte for "write file" vs "version query"
    - ACK/NACK response format

.PARAMETER RtiFile
    Path to the .rti project file.

.PARAMETER DeviceIndex
    Which Device Data Stream to upload (0, 1, 2). Default = 0 (first device).

.PARAMETER DryRun
    Parse file and show what would be sent, without actually connecting to USB.

.EXAMPLE
    .\rti_uploader.ps1 -RtiFile "C:\Users\Admin\Documents\Integration Designer\Test2.rti" -DryRun
    .\rti_uploader.ps1 -RtiFile "C:\...\Test2.rti" -DeviceIndex 0
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$RtiFile,

    [int]$DeviceIndex = 0,

    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ????????? CONSTANTS ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

# RTI USB Device Interface GUID (from rtiwinusb.inf)
$RTI_INTERFACE_GUID = "{b0b650d9-8169-4343-89df-ca55cef25059}"

# RTI USB VID/PIDs
$RTI_VID   = 0x13BD
$RTI_PIDS  = @(0x0020) + (0x1022..0x103F)

# OLE2 CFB constants
$SECTOR_SIZE     = 512
$MINI_SECT_SIZE  = 64
$FAT_ENDOFCHAIN  = [long]0xFFFFFFFE   # 4294967294
$FAT_FREESECT    = [long]0xFFFFFFFF   # 4294967295
$MINI_CUTOFF     = 4096

# ????????? OLE2 CFB PARSER ???????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

function Read-CFBStreams([byte[]]$bytes) {
    # Validate magic
    $magic = $bytes[0..7]
    $expected = @(0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1)
    for ($i = 0; $i -lt 8; $i++) {
        if ($magic[$i] -ne $expected[$i]) { throw "Not an OLE2 CFB file" }
    }

    $fatCount     = [BitConverter]::ToUInt32($bytes, 0x2C)
    $firstDirSect = [BitConverter]::ToUInt32($bytes, 0x30)
    $firstMini    = [BitConverter]::ToUInt32($bytes, 0x3C)
    $miniCount    = [BitConverter]::ToUInt32($bytes, 0x40)

    # Collect FAT sectors from DIFAT (header slots 0..108)
    $fatSectors = @()
    for ($i = 0; $i -lt 109 -and $i -lt $fatCount; $i++) {
        $sect = [BitConverter]::ToUInt32($bytes, 0x4C + $i * 4)
        if ($sect -ne $FAT_FREESECT -and $sect -ne $FAT_ENDOFCHAIN) {
            $fatSectors += $sect
        }
    }

    # Build FAT table (store as long to avoid uint32/int32 sign issues)
    $fat = [System.Collections.Generic.List[long]]::new()
    foreach ($sect in $fatSectors) {
        $off = ($sect + 1) * $SECTOR_SIZE
        for ($j = 0; $j -lt $SECTOR_SIZE / 4; $j++) {
            $fat.Add([long][BitConverter]::ToUInt32($bytes, $off + $j * 4))
        }
    }

    # Follow a regular FAT chain
    function Get-Chain([long]$start) {
        $chunks = [System.Collections.Generic.List[byte[]]]::new()
        $sect = $start
        while ($sect -ne $FAT_ENDOFCHAIN -and $sect -ne $FAT_FREESECT -and $sect -ge 0 -and $sect -lt $fat.Count) {
            $off = ($sect + 1) * $SECTOR_SIZE
            $chunks.Add($bytes[$off..($off + $SECTOR_SIZE - 1)])
            $sect = $fat[$sect]
        }
        $total = $chunks | ForEach-Object { $_.Length } | Measure-Object -Sum
        $result = [byte[]]::new($total.Sum)
        $pos = 0
        foreach ($chunk in $chunks) { [Array]::Copy($chunk, 0, $result, $pos, $chunk.Length); $pos += $chunk.Length }
        return $result
    }

    # Build mini-FAT
    $miniFAT = [System.Collections.Generic.List[long]]::new()
    if ($firstMini -ne $FAT_ENDOFCHAIN) {
        $miniFATData = Get-Chain $firstMini
        for ($i = 0; $i -lt $miniFATData.Length / 4; $i++) {
            $miniFAT.Add([long][BitConverter]::ToUInt32($miniFATData, $i * 4))
        }
    }

    # Read directory entries
    $dirData = Get-Chain $firstDirSect
    $entries = @()
    for ($i = 0; $i -lt $dirData.Length / 128; $i++) {
        $off    = $i * 128
        $nlen   = [BitConverter]::ToUInt16($dirData, $off + 64)
        $name   = if ($nlen -gt 2) { [Text.Encoding]::Unicode.GetString($dirData, $off, $nlen - 2) } else { "" }
        $type   = $dirData[$off + 66]
        $start  = [long][BitConverter]::ToUInt32($dirData, $off + 116)
        $size   = [long][BitConverter]::ToUInt32($dirData, $off + 120)
        $entries += [PSCustomObject]@{ Name=$name; Type=$type; Start=$start; Size=$size }
    }

    $root = $entries | Where-Object { $_.Type -eq 5 } | Select-Object -First 1
    if (-not $root) { throw "No root entry found" }

    # Root stream = mini-stream container
    $rootData = Get-Chain $root.Start

    function Get-MiniChain([long]$start, [long]$size) {
        $chunks = [System.Collections.Generic.List[byte[]]]::new()
        $sect = $start
        while ($sect -ne $FAT_ENDOFCHAIN -and $sect -ne $FAT_FREESECT -and $sect -ge 0 -and $sect -lt $miniFAT.Count) {
            $off = $sect * $MINI_SECT_SIZE
            $chunks.Add($rootData[$off..($off + $MINI_SECT_SIZE - 1)])
            $sect = $miniFAT[$sect]
        }
        $total = $chunks | ForEach-Object { $_.Length } | Measure-Object -Sum
        $result = [byte[]]::new($total.Sum)
        $pos = 0
        foreach ($chunk in $chunks) { [Array]::Copy($chunk, 0, $result, $pos, $chunk.Length); $pos += $chunk.Length }
        return $result[0..([Math]::Min($size, $result.Length) - 1)]
    }

    # Extract all stream data
    $streams = @{}
    foreach ($e in $entries) {
        if ($e.Type -ne 2) { continue }
        $data = if ($e.Size -lt $MINI_CUTOFF) {
            Get-MiniChain $e.Start $e.Size
        } else {
            $raw = Get-Chain $e.Start
            $raw[0..([Math]::Min($e.Size, $raw.Length) - 1)]
        }
        $streams[$e.Name] = $data
    }

    return $streams
}

# ????????? TLV DECODER (summary only) ?????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

function Get-StreamInfo([byte[]]$data) {
    $info = @{ DeviceType=0; DeviceTypeStr="Unknown"; Version=0; Serial=""; NTP="" }
    $i = 0
    while ($i -lt $data.Length - 1) {
        $tag  = $data[$i]
        $type = $data[$i+1]
        $i   += 2
        if ($tag -eq 0xFF -and $type -eq 0xFF) { break }
        switch ($type) {
            0x20 {
                # TAG=0x01 BYTE = device type (first record in stream header)
                if ($tag -eq 0x01 -and $info.DeviceType -eq 0) {
                    $info.DeviceType = $data[$i]
                    $info.DeviceTypeStr = switch ($data[$i]) {
                        0x11 { "Handheld Remote" }
                        0x31 { "Processor/Controller" }
                        0x1D { "Touchscreen Panel" }
                        default { "Unknown(0x{0:X2})" -f $data[$i] }
                    }
                }
                $i += 1
            }
            0x40 {
                # TAG=0x01 U16 = format version
                if ($tag -eq 0x01 -and $info.Version -eq 0) {
                    $info.Version = [BitConverter]::ToUInt16($data, $i)
                }
                $i += 2
            }
            0x60 { $i += 4 }
            0x80 { $len = $data[$i]; $i += 1 + $len }
            0xA0 {
                $len = [BitConverter]::ToUInt16($data, $i); $i += 2
                if ($tag -eq 0x0A -and $len -gt 0) { $info.NTP = [Text.Encoding]::Unicode.GetString($data, $i, $len) }
                if ($tag -eq 0x1F -and $len -gt 0) { $info.Serial = [Text.Encoding]::Unicode.GetString($data, $i, $len) }
                $i += $len
            }
            0xC0 { $len = [BitConverter]::ToUInt32($data, $i); $i += 4 + $len }
            0xE0 { $i += 16 }
            default { break }
        }
    }
    return $info
}

# ????????? WinUSB PINVOKE DECLARATIONS ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

$WinUsbCode = @'
using System;
using System.Runtime.InteropServices;

public class WinUsbHelper {
    // SetupAPI
    [DllImport("setupapi.dll", CharSet = CharSet.Auto, SetLastError = true)]
    public static extern IntPtr SetupDiGetClassDevs(
        ref Guid ClassGuid, string Enumerator, IntPtr hwndParent, uint Flags);

    [DllImport("setupapi.dll", SetLastError = true)]
    public static extern bool SetupDiEnumDeviceInterfaces(
        IntPtr DeviceInfoSet, IntPtr DeviceInfoData,
        ref Guid InterfaceClassGuid, uint MemberIndex,
        ref SP_DEVICE_INTERFACE_DATA DeviceInterfaceData);

    [DllImport("setupapi.dll", CharSet = CharSet.Auto, SetLastError = true)]
    public static extern bool SetupDiGetDeviceInterfaceDetail(
        IntPtr DeviceInfoSet,
        ref SP_DEVICE_INTERFACE_DATA DeviceInterfaceData,
        IntPtr DeviceInterfaceDetailData,
        uint DeviceInterfaceDetailDataSize,
        ref uint RequiredSize,
        IntPtr DeviceInfoData);

    [DllImport("setupapi.dll")]
    public static extern bool SetupDiDestroyDeviceInfoList(IntPtr DeviceInfoSet);

    // WinUSB
    [DllImport("winusb.dll", SetLastError = true)]
    public static extern bool WinUsb_Initialize(IntPtr DeviceHandle, ref IntPtr InterfaceHandle);

    [DllImport("winusb.dll", SetLastError = true)]
    public static extern bool WinUsb_Free(IntPtr InterfaceHandle);

    [DllImport("winusb.dll", SetLastError = true)]
    public static extern bool WinUsb_QueryPipe(
        IntPtr InterfaceHandle, byte AlternateInterfaceNumber,
        byte PipeIndex, ref WINUSB_PIPE_INFORMATION PipeInformation);

    [DllImport("winusb.dll", SetLastError = true)]
    public static extern bool WinUsb_WritePipe(
        IntPtr InterfaceHandle, byte PipeID,
        byte[] Buffer, uint BufferLength,
        ref uint LengthTransferred, IntPtr Overlapped);

    [DllImport("winusb.dll", SetLastError = true)]
    public static extern bool WinUsb_ReadPipe(
        IntPtr InterfaceHandle, byte PipeID,
        byte[] Buffer, uint BufferLength,
        ref uint LengthTransferred, IntPtr Overlapped);

    [DllImport("winusb.dll", SetLastError = true)]
    public static extern bool WinUsb_ControlTransfer(
        IntPtr InterfaceHandle,
        WINUSB_SETUP_PACKET SetupPacket,
        byte[] Buffer, uint BufferLength,
        ref uint LengthTransferred, IntPtr Overlapped);

    // Kernel32
    [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    public static extern IntPtr CreateFile(
        string lpFileName, uint dwDesiredAccess, uint dwShareMode,
        IntPtr lpSecurityAttributes, uint dwCreationDisposition,
        uint dwFlagsAndAttributes, IntPtr hTemplateFile);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool CloseHandle(IntPtr hObject);

    public const uint GENERIC_READ  = 0x80000000;
    public const uint GENERIC_WRITE = 0x40000000;
    public const uint OPEN_EXISTING = 3;
    public const uint FILE_FLAG_OVERLAPPED = 0x40000000;
    public const uint DIGCF_PRESENT = 0x02;
    public const uint DIGCF_DEVICEINTERFACE = 0x10;
    public static readonly IntPtr INVALID_HANDLE_VALUE = new IntPtr(-1);

    [StructLayout(LayoutKind.Sequential)]
    public struct SP_DEVICE_INTERFACE_DATA {
        public uint cbSize;
        public Guid InterfaceClassGuid;
        public uint Flags;
        public IntPtr Reserved;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct WINUSB_PIPE_INFORMATION {
        public int PipeType;
        public byte PipeId;
        public ushort MaximumPacketSize;
        public byte Interval;
    }

    [StructLayout(LayoutKind.Sequential, Pack=1)]
    public struct WINUSB_SETUP_PACKET {
        public byte RequestType;
        public byte Request;
        public ushort Value;
        public ushort Index;
        public ushort Length;
    }

    // Helper: enumerate all device paths matching a GUID
    public static string[] GetDevicePaths(Guid guid) {
        var list = new System.Collections.Generic.List<string>();
        var devInfo = SetupDiGetClassDevs(ref guid, null, IntPtr.Zero, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE);
        if (devInfo == INVALID_HANDLE_VALUE) return list.ToArray();

        var ifaceData = new SP_DEVICE_INTERFACE_DATA();
        ifaceData.cbSize = (uint)Marshal.SizeOf(ifaceData);

        for (uint idx = 0; ; idx++) {
            if (!SetupDiEnumDeviceInterfaces(devInfo, IntPtr.Zero, ref guid, idx, ref ifaceData)) break;

            uint needed = 0;
            SetupDiGetDeviceInterfaceDetail(devInfo, ref ifaceData, IntPtr.Zero, 0, ref needed, IntPtr.Zero);

            var buffer = Marshal.AllocHGlobal((int)needed);
            try {
                // First DWORD = cbSize (must be 8 on 64-bit, 6 on 32-bit)
                Marshal.WriteInt32(buffer, IntPtr.Size == 8 ? 8 : 6);
                if (SetupDiGetDeviceInterfaceDetail(devInfo, ref ifaceData, buffer, needed, ref needed, IntPtr.Zero)) {
                    // DevicePath starts at offset 4
                    string path = Marshal.PtrToStringAuto(new IntPtr(buffer.ToInt64() + 4));
                    if (path != null) list.Add(path);
                }
            } finally {
                Marshal.FreeHGlobal(buffer);
            }
        }

        SetupDiDestroyDeviceInfoList(devInfo);
        return list.ToArray();
    }
}
'@

Add-Type -TypeDefinition $WinUsbCode -Language CSharp -ErrorAction Stop

# ????????? DEVICE ENUMERATION ?????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

function Find-RTIDevice {
    $guid = [Guid]$RTI_INTERFACE_GUID
    $paths = [WinUsbHelper]::GetDevicePaths($guid)
    if ($paths.Count -eq 0) {
        throw "No RTI device found with Interface GUID $RTI_INTERFACE_GUID`nMake sure the device is plugged in and rtiwinusb.inf driver is installed."
    }
    Write-Host "Found $($paths.Count) RTI device(s):"
    for ($i = 0; $i -lt $paths.Count; $i++) {
        Write-Host "  [$i] $($paths[$i])"
    }
    return $paths[0]
}

# ????????? USB TRANSFER HELPERS ???????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

function Open-WinUSB([string]$devicePath) {
    $ACCESS = [WinUsbHelper]::GENERIC_READ -bor [WinUsbHelper]::GENERIC_WRITE
    $hFile = [WinUsbHelper]::CreateFile(
        $devicePath, $ACCESS, 0, [IntPtr]::Zero,
        [WinUsbHelper]::OPEN_EXISTING,
        [WinUsbHelper]::FILE_FLAG_OVERLAPPED, [IntPtr]::Zero)

    if ($hFile -eq [WinUsbHelper]::INVALID_HANDLE_VALUE) {
        $err = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
        throw "CreateFile failed: Win32 error $err"
    }

    $hUsb = [IntPtr]::Zero
    if (-not [WinUsbHelper]::WinUsb_Initialize($hFile, [ref]$hUsb)) {
        $err = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
        [WinUsbHelper]::CloseHandle($hFile)
        throw "WinUsb_Initialize failed: Win32 error $err"
    }

    Write-Host "WinUSB interface opened successfully."
    return @{ File=$hFile; USB=$hUsb }
}

function Close-WinUSB($handles) {
    if ($handles.USB -ne [IntPtr]::Zero) { [WinUsbHelper]::WinUsb_Free($handles.USB) }
    if ($handles.File -ne [IntPtr]::Zero) { [WinUsbHelper]::CloseHandle($handles.File) }
}

function Find-Pipes($hUsb) {
    # Enumerate pipes on alternate setting 0
    $pipes = @{}
    for ($idx = 0; $idx -lt 8; $idx++) {
        $pipe = New-Object WinUsbHelper+WINUSB_PIPE_INFORMATION
        if ([WinUsbHelper]::WinUsb_QueryPipe($hUsb, 0, [byte]$idx, [ref]$pipe)) {
            $dir = if ($pipe.PipeId -band 0x80) { "IN" } else { "OUT" }
            Write-Host "  Pipe[$idx]: ID=0x{0:X2} ({1}), Type={2}, MaxPkt={3}" -f $pipe.PipeId, $dir, $pipe.PipeType, $pipe.MaximumPacketSize
            $pipes[$dir + $idx] = $pipe
        } else { break }
    }
    return $pipes
}

function Send-BulkData($hUsb, [byte]$pipeId, [byte[]]$data, [int]$chunkSize = 512) {
    $sent = 0
    $total = $data.Length
    while ($sent -lt $total) {
        $end = [Math]::Min($sent + $chunkSize, $total)
        $chunk = $data[$sent..($end - 1)]
        $transferred = [uint32]0
        $ok = [WinUsbHelper]::WinUsb_WritePipe($hUsb, $pipeId, $chunk, [uint32]$chunk.Length, [ref]$transferred, [IntPtr]::Zero)
        if (-not $ok) {
            $err = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
            throw ("WritePipe failed at offset {0}: Win32 error {1}" -f $sent, $err)
        }
        $sent += $chunk.Length
        $pct = [int]($sent * 100 / $total)
        Write-Progress -Activity "Uploading" -Status "$sent / $total bytes" -PercentComplete $pct
    }
    Write-Progress -Activity "Uploading" -Completed
}

function Receive-BulkData($hUsb, [byte]$pipeId, [int]$maxBytes = 4096) {
    $buf = [byte[]]::new($maxBytes)
    $transferred = [uint32]0
    $ok = [WinUsbHelper]::WinUsb_ReadPipe($hUsb, $pipeId, $buf, [uint32]$maxBytes, [ref]$transferred, [IntPtr]::Zero)
    if (-not $ok) {
        $err = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
        throw "ReadPipe failed: Win32 error $err"
    }
    return $buf[0..([int]$transferred - 1)]
}

# ????????? UPLOAD PROTOCOL (STUB ??? needs USB capture to complete) ?????????????????????????????????????????????????????????
#
# Based on reverse engineering:
#   - The device exposes \PIPE00 as a WinUSB bulk endpoint
#   - IR capture commands are sent as ASCII strings (e.g. "START_CAPTURE_IR")
#   - The upload writes \IPSM\remotev2.dat on the device
#   - Upload sequence: CheckVersion ??? ReceiveBank ??? SendBank ??? SendSystemInfo ??? Done
#
# TODO: USB CAPTURE NEEDED to determine:
#   1. Exact packet format (magic header, length field, checksum)
#   2. Command byte for "version query" and "write file"
#   3. ACK format returned by device after each packet
#
# PLACEHOLDER PROTOCOL (guessed structure ??? replace with actual captured bytes):
#   Packet format hypothesis:
#     [0x52 0x54 0x49]  = "RTI" magic header (3 bytes) ??? UNCONFIRMED
#     [cmd : 1 byte]    = command code
#     [len : 4 bytes LE] = payload length
#     [payload : N bytes]
#     [checksum : 1 byte] = XOR of all preceding bytes ??? UNCONFIRMED
#
# If the device uses a simple "write file" command like:
#   CMD_WRITE_FILE = 0x03 (guessed)
#   payload = NUL-terminated path + 4-byte file size + file data
#   e.g.: "\IPSM\remotev2.dat\0" + [size:4LE] + [data...]

function Invoke-RTIUpload {
    param($handles, [byte[]]$streamData, [int]$chunkSize = 512)

    $hUsb = $handles.USB

    Write-Host "Enumerating USB pipes..."
    $pipes = Find-Pipes $hUsb
    if ($pipes.Count -eq 0) { throw "No USB pipes found on device" }

    # TODO: Replace these with actual pipe IDs from capture
    # Typical WinUSB device: pipe 0x01 = OUT, pipe 0x81 = IN
    $outPipeId = [byte]0x01  # ??? CONFIRM WITH USB CAPTURE
    $inPipeId  = [byte]0x81  # ??? CONFIRM WITH USB CAPTURE

    # ?????? Step 1: Version Query ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    # TODO: Send actual version query command
    # Placeholder: send "VERSION\0" as ASCII command (guessed)
    Write-Host "Step 1: Querying device version..."
    # $versionCmd = [Text.Encoding]::ASCII.GetBytes("VERSION`0")
    # Send-BulkData $hUsb $outPipeId $versionCmd
    # $versionResp = Receive-BulkData $hUsb $inPipeId
    # Write-Host "Device version response: $([Text.Encoding]::ASCII.GetString($versionResp))"
    Write-Warning "TODO: Version query command not yet known ??? skipping"

    # ?????? Step 2: Send stream data ?????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    # TODO: Wrap $streamData in the actual upload packet format
    # For now, show what we would send
    Write-Host "Step 2: Preparing to send Device Data Stream ($($streamData.Length) bytes)..."
    Write-Host "  Target path on device: \IPSM\remotev2.dat"
    Write-Host "  Chunk size: $chunkSize bytes"
    Write-Host "  Number of chunks: $([Math]::Ceiling($streamData.Length / $chunkSize))"

    # ?????? PLACEHOLDER: Uncomment when packet format is known ????????????????????????????????????????????????????????????
    # $pathBytes = [Text.Encoding]::ASCII.GetBytes("\IPSM\remotev2.dat`0")
    # $sizeBytes = [BitConverter]::GetBytes([uint32]$streamData.Length)
    # $payload = $pathBytes + $sizeBytes + $streamData
    # Send-BulkData $hUsb $outPipeId $payload $chunkSize
    # $ackResp = Receive-BulkData $hUsb $inPipeId
    # Write-Host "ACK response: $($ackResp | ForEach-Object { '{0:X2}' -f $_ } | Join-String ' ')"
    Write-Warning "TODO: Upload packet format not yet confirmed ??? NOT sending data"
    Write-Warning "Use USBPcap + Wireshark to capture the actual idesign.exe upload sequence"
    Write-Warning "Filter: usb.idVendor == 0x13BD"

    Write-Host "`nUpload stub completed. Device not modified."
}

# ????????? MAIN ???????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

Write-Host "RTI Remote Open-Source Uploader" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan

# Step 1: Parse the .rti file
if (-not (Test-Path $RtiFile)) {
    Write-Error "File not found: $RtiFile"
    exit 1
}

Write-Host "`nParsing $RtiFile..."
$bytes = [IO.File]::ReadAllBytes($RtiFile)
$streams = Read-CFBStreams $bytes

$streamNames = $streams.Keys | Sort-Object
Write-Host "Found streams:"
foreach ($name in $streamNames) {
    Write-Host ("  '{0}' - {1} bytes" -f $name, $streams[$name].Length)
}

# Find the requested device stream
$deviceStreamName = "Device Data Stream {0:D4}" -f $DeviceIndex
if (-not $streams.ContainsKey($deviceStreamName)) {
    Write-Error "Stream '$deviceStreamName' not found. Available: $($streamNames -join ', ')"
    exit 1
}

$streamData = $streams[$deviceStreamName]
$info = Get-StreamInfo $streamData

Write-Host ("`nDevice Data Stream {0:D4}:" -f $DeviceIndex)
Write-Host "  Type    : $($info.DeviceTypeStr)"
Write-Host "  Version : $($info.Version)"
Write-Host "  Serial  : $($info.Serial)"
Write-Host "  NTP     : $($info.NTP)"
Write-Host "  Size    : $($streamData.Length) bytes"

if ($DryRun) {
    Write-Host "`n[DRY RUN] Would upload $($streamData.Length) bytes to \IPSM\remotev2.dat" -ForegroundColor Yellow
    Write-Host "[DRY RUN] No USB connection made." -ForegroundColor Yellow
    exit 0
}

# Step 2: Find and connect to device
Write-Host "`nSearching for RTI device..."
try {
    $devicePath = Find-RTIDevice
} catch {
    Write-Error $_
    exit 1
}

Write-Host "Opening WinUSB connection to: $devicePath"
$handles = $null
try {
    $handles = Open-WinUSB $devicePath
    Invoke-RTIUpload -handles $handles -streamData $streamData
} catch {
    Write-Error "Upload failed: $_"
} finally {
    if ($handles) {
        Close-WinUSB $handles
        Write-Host "WinUSB connection closed."
    }
}

