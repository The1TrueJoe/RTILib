"""
RTI Device models, constants, and hardware definitions.

Device type bytes (from reverse engineering RTI Data Directory V3 and stream headers):
  0x07 = T2+    (2.4" B&W touchscreen handheld, confirmed from T2Sample.rti)
  0x11 = U1     (button-only handheld, confirmed from Test2.rti RTI Data Directory)
  0x1D = U2     (2.1" B&W 64x128px display handheld, confirmed from Test2.rti dir slot 2)
  0x31 = Controller/Processor (XP-3, XP-6, XP-8 — same category byte, model differentiates)

Controller model names (as stored in RTI Data Directory V3):
  "XP-3"  : 3 IR outputs (1 Multi-Purpose IR Output)
  "XP-6"  : 6 IR outputs
  "XP-8"  : 8 Multi-Purpose IR Outputs

USB transport (WinUSB):
  VID = 0x13BD
  PIDs = 0x0020, 0x1022 through 0x103F
  Device Interface GUID = {b0b650d9-8169-4343-89df-ca55cef25059}
  Target file on device: \\IPSM\\remotev2.dat
  Cancel event name: RTIUpgradeCancelEvent
"""

# ---- Device type bytes ----

DEVICE_TYPE_T2_PLUS   = 0x07
DEVICE_TYPE_U1        = 0x11
DEVICE_TYPE_U2        = 0x1D
DEVICE_TYPE_CONTROLLER = 0x31

DEVICE_TYPE_NAMES = {
    DEVICE_TYPE_T2_PLUS:   'T2+',
    DEVICE_TYPE_U1:        'U1',
    DEVICE_TYPE_U2:        'U2',
    DEVICE_TYPE_CONTROLLER: 'Controller',
}

# ---- Controller model strings ----

CONTROLLER_XP3 = 'XP-3'
CONTROLLER_XP6 = 'XP-6'
CONTROLLER_XP8 = 'XP-8'

CONTROLLER_MODELS = [CONTROLLER_XP3, CONTROLLER_XP6, CONTROLLER_XP8]

CONTROLLER_IR_OUTPUTS = {
    CONTROLLER_XP3: 3,
    CONTROLLER_XP6: 6,
    CONTROLLER_XP8: 8,
}

# ---- Display specs ----

U2_DISPLAY_WIDTH  = 64
U2_DISPLAY_HEIGHT = 128
U2_DISPLAY_BPP    = 1   # 1-bit B&W

T2_PLUS_DISPLAY_WIDTH  = 64
T2_PLUS_DISPLAY_HEIGHT = 128
T2_PLUS_DISPLAY_BPP    = 1

# ---- USB constants ----

RTI_USB_VID = 0x13BD
RTI_USB_PIDS = [0x0020] + list(range(0x1022, 0x1040))
RTI_DEVICE_INTERFACE_GUID = '{b0b650d9-8169-4343-89df-ca55cef25059}'
RTI_UPLOAD_TARGET_PATH = r'\IPSM\remotev2.dat'
RTI_CANCEL_EVENT_NAME = 'RTIUpgradeCancelEvent'

# ---- Stream names (within RTI OLE2 CFB) ----

STREAM_JOB_INFO        = 'Job Info'
STREAM_DIR_V3          = 'RTI Data Directory V3'
STREAM_VARIABLE_IDS    = 'VariableIDs'
STREAM_DEVICE_PREFIX   = 'Device Data Stream '   # followed by 4-digit zero-padded index

# ---- RTI Data Directory V3 constants ----

DIR_MAGIC = 0xBEEFF00D
DIR_SLOT_SIZE = 686   # approximate bytes per device slot (derived from Test2.rti analysis)

# ---- TLV stream header field TAGs ----

TAG_DEVICE_TYPE     = 0x01   # TYPE=BYTE, first occurrence = device_type_byte
TAG_MODEL_NUMBER    = 0x03   # TYPE=BYTE
TAG_TIMEOUT         = 0x34   # TYPE=I32, value=timeout_seconds
TAG_FORMAT_VERSION  = 0x01   # TYPE=U16, second occurrence (format_version = 2)


def device_type_name(type_byte: int) -> str:
    """Return human-readable name for a device type byte."""
    return DEVICE_TYPE_NAMES.get(type_byte, f'Unknown(0x{type_byte:02X})')


def controller_ir_count(model: str) -> int:
    """Return number of IR outputs for a given controller model string."""
    return CONTROLLER_IR_OUTPUTS.get(model, 0)


def device_stream_name(index: int) -> str:
    """Return the OLE2 stream name for device data stream N."""
    return f"{STREAM_DEVICE_PREFIX}{index:04d}"
