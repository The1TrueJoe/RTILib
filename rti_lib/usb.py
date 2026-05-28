"""
RTI WinUSB uploader — Windows-only, uses ctypes to call SetupAPI and WinUSB.

This module provides:
  - find_device()   : find the first connected RTI device via SetupAPI
  - RTIUploader     : class to open, communicate with, and upload to a device

NOTE: The exact wire protocol for uploading \\IPSM\\remotev2.dat is not yet
fully reverse-engineered. The connect/open code is functional; the upload
sequence is stubbed and marked TODO.

USB details (from idesign.exe / MSTRK32.dll reverse engineering):
  VID = 0x13BD
  PIDs = 0x0020, 0x1022-0x103F
  Interface GUID = {b0b650d9-8169-4343-89df-ca55cef25059}
  Target path on device: \\IPSM\\remotev2.dat
  Cancel event: RTIUpgradeCancelEvent
"""

import ctypes
import ctypes.wintypes
import struct
from .models import (
    RTI_USB_VID, RTI_USB_PIDS, RTI_DEVICE_INTERFACE_GUID,
    RTI_UPLOAD_TARGET_PATH, RTI_CANCEL_EVENT_NAME
)

# ---- Windows API structures ----

INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
ERROR_NO_MORE_ITEMS = 259
DIGCF_PRESENT = 0x02
DIGCF_DEVICEINTERFACE = 0x10
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x80
FILE_FLAG_OVERLAPPED = 0x40000000


class GUID(ctypes.Structure):
    _fields_ = [
        ('Data1', ctypes.c_ulong),
        ('Data2', ctypes.c_ushort),
        ('Data3', ctypes.c_ushort),
        ('Data4', ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_string(cls, guid_str: str):
        """Parse {xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx} format."""
        s = guid_str.strip('{}').replace('-', '')
        d1 = int(s[0:8], 16)
        d2 = int(s[8:12], 16)
        d3 = int(s[12:16], 16)
        d4 = bytes.fromhex(s[16:32])
        g = cls()
        g.Data1 = d1
        g.Data2 = d2
        g.Data3 = d3
        g.Data4 = (ctypes.c_ubyte * 8)(*d4)
        return g


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ('cbSize', ctypes.c_ulong),
        ('InterfaceClassGuid', GUID),
        ('Flags', ctypes.c_ulong),
        ('Reserved', ctypes.POINTER(ctypes.c_ulong)),
    ]


class SP_DEVICE_INTERFACE_DETAIL_DATA_W(ctypes.Structure):
    _fields_ = [
        ('cbSize', ctypes.c_ulong),
        ('DevicePath', ctypes.c_wchar * 512),
    ]


# ---- SetupAPI helpers ----

_setupapi = ctypes.windll.SetupAPI
_kernel32 = ctypes.windll.kernel32


def _get_winusb():
    try:
        return ctypes.windll.WinUsb
    except Exception:
        return None


def find_device() -> str:
    """
    Find the device path for the first connected RTI device.
    Returns the device path string (e.g. '\\\\?\\usb#...') or None.
    """
    interface_guid = GUID.from_string(RTI_DEVICE_INTERFACE_GUID)

    dev_info = _setupapi.SetupDiGetClassDevsW(
        ctypes.byref(interface_guid),
        None,
        None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
    )
    if dev_info == INVALID_HANDLE_VALUE:
        return None

    try:
        iface_data = SP_DEVICE_INTERFACE_DATA()
        iface_data.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)

        index = 0
        while True:
            ok = _setupapi.SetupDiEnumDeviceInterfaces(
                dev_info,
                None,
                ctypes.byref(interface_guid),
                index,
                ctypes.byref(iface_data)
            )
            if not ok:
                err = _kernel32.GetLastError()
                if err == ERROR_NO_MORE_ITEMS:
                    break
                break

            detail = SP_DEVICE_INTERFACE_DETAIL_DATA_W()
            # cbSize must be 8 on 64-bit, 6 on 32-bit (struct alignment)
            detail.cbSize = 8  # 64-bit Windows
            required = ctypes.c_ulong(0)

            _setupapi.SetupDiGetDeviceInterfaceDetailW(
                dev_info,
                ctypes.byref(iface_data),
                ctypes.byref(detail),
                ctypes.sizeof(detail),
                ctypes.byref(required),
                None
            )

            path = detail.DevicePath
            if path:
                return path
            index += 1

    finally:
        _setupapi.SetupDiDestroyDeviceInfoList(dev_info)

    return None


class RTIUploader:
    """
    Open a WinUSB connection to an RTI device and upload a firmware/config file.

    Usage:
        uploader = RTIUploader()
        uploader.connect()          # find and open device
        uploader.upload(data)       # send bytes to \\IPSM\\remotev2.dat (STUB)
        uploader.disconnect()
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self._device_handle = None
        self._winusb_handle = None
        self._device_path = None

    def connect(self) -> bool:
        """Find and open the RTI device. Returns True on success."""
        path = find_device()
        if path is None:
            print("[USB] No RTI device found.")
            return False

        self._device_path = path
        print(f"[USB] Found device: {path}")

        if self.dry_run:
            print("[USB] Dry run — skipping actual open.")
            return True

        handle = _kernel32.CreateFileW(
            path,
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OVERLAPPED,
            None
        )
        if handle == INVALID_HANDLE_VALUE:
            err = _kernel32.GetLastError()
            print(f"[USB] CreateFile failed: error {err}")
            return False

        self._device_handle = handle

        winusb = _get_winusb()
        if winusb is None:
            print("[USB] WinUSB DLL not available.")
            _kernel32.CloseHandle(handle)
            self._device_handle = None
            return False

        winusb_handle = ctypes.c_void_p()
        ok = winusb.WinUsb_Initialize(handle, ctypes.byref(winusb_handle))
        if not ok:
            err = _kernel32.GetLastError()
            print(f"[USB] WinUsb_Initialize failed: error {err}")
            _kernel32.CloseHandle(handle)
            self._device_handle = None
            return False

        self._winusb_handle = winusb_handle
        print("[USB] WinUSB initialized.")
        return True

    def disconnect(self):
        """Close the WinUSB connection."""
        winusb = _get_winusb()
        if self._winusb_handle and winusb:
            winusb.WinUsb_Free(self._winusb_handle)
            self._winusb_handle = None
        if self._device_handle:
            _kernel32.CloseHandle(self._device_handle)
            self._device_handle = None
        print("[USB] Disconnected.")

    def upload(self, data: bytes) -> bool:
        """
        Upload config/firmware data to the RTI device.

        TODO: The exact wire protocol (command framing, file transfer sequence,
        ACK/NACK handshake, target path specification) has not been fully
        reverse-engineered from MSTRK32.dll. This method is a STUB.

        Known facts:
          - Target path on device: \\IPSM\\remotev2.dat
          - Cancel event: RTIUpgradeCancelEvent (Windows named event)
          - Transfer uses WinUSB bulk OUT pipe
          - Device runs Windows CE
        """
        print(f"[USB] Upload requested: {len(data)} bytes -> {RTI_UPLOAD_TARGET_PATH}")
        if self.dry_run:
            print("[USB] Dry run — no data sent.")
            return True

        if not self._winusb_handle:
            print("[USB] Not connected.")
            return False

        # TODO: Implement actual upload protocol once wire format is known.
        # Expected sequence (to be confirmed):
        #   1. Send command frame: "begin upload" + filename + file size
        #   2. Receive ACK from device
        #   3. Stream data in chunks via WinUsb_WritePipe (bulk OUT)
        #   4. Receive final ACK / completion status
        #   5. Device reboots and applies new config

        print("[USB] STUB: upload protocol not yet implemented.")
        return False

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.disconnect()
