"""
examples/basic_t2i_project.py
==============================
Minimal end-to-end example: build a complete T2i project file from scratch.

Creates a Living Room project with:
  - XP-6 processor (serial commands to an AV receiver)
  - T2i handheld remote, Oasis gradient background
  - 6 source buttons on the home page (2-col × 3-row touchscreen grid)
  - 6 transport / playback buttons on the secondary page
  - Volume strip on the secondary page
  - All 52 physical hardware buttons mapped (slots 128-179)

Output: examples/out_basic_t2i.rti  (open in RTI Integration Designer)

Prerequisites
-------------
    pip install Pillow

Usage
-----
    python examples/basic_t2i_project.py
"""

import os
import sys

# Allow running from the repo root without installing the package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from rti_lib import RTIProject, T2iRemote
from rti_lib.devices.xp import XPProcessor
from rti_lib.assets.button_designer import ButtonDesigner, Style

# ---------------------------------------------------------------------------
# Project constants
# ---------------------------------------------------------------------------
REMOTE_NAME = 'Living Room T2i'

# ---------------------------------------------------------------------------
# XP Processor — one macro per user action
# ---------------------------------------------------------------------------
xp = XPProcessor('XP-6', display_name='Living Room AV')


def macro(label: str, cmd: bytes, port: int = 0, baud: int = 9600):
    """Helper: add a serial macro to the XP processor."""
    return xp.add_macro(
        f'{REMOTE_NAME} - {label}',
        serial=cmd, baud=baud, port=port,
        device_name='AV Receiver', manufacturer='Generic', model_str='AVR',
    )


# Source selection
m_cable   = macro('Cable TV',    b'src hdmi1\r')
m_sat     = macro('Satellite',   b'src hdmi2\r')
m_atv     = macro('Apple TV',    b'src hdmi3\r')
m_stream  = macro('Streaming',   b'src hdmi4\r')
m_bluray  = macro('Blu-ray',     b'src hdmi5\r')
m_alloff  = macro('All Off',     b'pwr off\r')

# Volume / audio
m_volup   = macro('Vol+',        b'vol+\r')
m_voldn   = macro('Vol-',        b'vol-\r')
m_mute    = macro('Mute',        b'mute\r')

# Media transport
m_play    = macro('Play',        b'play\r')
m_pause   = macro('Pause',       b'pause\r')
m_stop    = macro('Stop',        b'stop\r')
m_prev    = macro('Rewind',      b'prev\r')
m_next    = macro('Fast Fwd',    b'next\r')
m_rec     = macro('Record',      b'rec\r')

# Navigation
m_up      = macro('Up',          b'nav up\r')
m_down    = macro('Down',        b'nav down\r')
m_left    = macro('Left',        b'nav left\r')
m_right   = macro('Right',       b'nav right\r')
m_select  = macro('Select',      b'nav ok\r')
m_back    = macro('Back',        b'nav back\r')
m_home    = macro('Home',        b'nav home\r')
m_menu    = macro('Menu',        b'nav menu\r')
m_info    = macro('Info',        b'nav info\r')
m_exit    = macro('Exit',        b'nav exit\r')
m_guide   = macro('Guide',       b'nav guide\r')
m_chup    = macro('Ch+',         b'ch+\r')
m_chdn    = macro('Ch-',         b'ch-\r')

# Number pad
m_1 = macro('1', b'key 1\r');  m_2 = macro('2', b'key 2\r');  m_3 = macro('3', b'key 3\r')
m_4 = macro('4', b'key 4\r');  m_5 = macro('5', b'key 5\r');  m_6 = macro('6', b'key 6\r')
m_7 = macro('7', b'key 7\r');  m_8 = macro('8', b'key 8\r');  m_9 = macro('9', b'key 9\r')
m_0 = macro('0', b'key 0\r');  m_enter = macro('Enter', b'key enter\r')
m_clear = macro('Clear', b'key clear\r')

# Miscellaneous
m_fav      = macro('Fav',         b'fav\r')
m_on       = macro('On',          b'pwr on\r')
m_off      = macro('Off',         b'pwr off\r')
m_prev_btn = macro('Prev',        b'prev\r')
m_next_btn = macro('Next',        b'next\r')

# Softkeys (hardware-only; custom actions defined here)
m_sk1  = macro('Softkey 1',   b'custom sk1\r')   # slot 136
m_sk2  = macro('Softkey 2',   b'custom sk2\r')   # slot 130
m_sk3  = macro('Softkey 3',   b'custom sk3\r')   # slot 177
m_sk4  = macro('Softkey 4',   b'custom sk4\r')   # slot 137

# Joystick (slots 166-170)
m_joy_up    = macro('Joy Up',    b'joy up\r')
m_joy_click = macro('Joy Click', b'joy click\r')
m_joy_dn    = macro('Joy Down',  b'joy dn\r')
m_joy_left  = macro('Joy Left',  b'joy left\r')
m_joy_right = macro('Joy Right', b'joy right\r')

# Colour buttons (slots 173-176)
m_red    = macro('Red',    b'color red\r')
m_green  = macro('Green',  b'color green\r')
m_yellow = macro('Yellow', b'color yellow\r')
m_blue   = macro('Blue',   b'color blue\r')

# ---------------------------------------------------------------------------
# T2i Remote
# ---------------------------------------------------------------------------
t2i = T2iRemote(display_name=REMOTE_NAME, style=Style.OASIS)

# Background: Oasis navy→teal ambient gradient (uses ButtonDesigner)
t2i.set_background(ButtonDesigner.background(Style.OASIS))


# ---------- Home page: 6 source buttons in a 2-col × 3-row grid ----------

def home_rect(col: int, row: int,
              cols: int = 2, rows: int = 3,
              x0: int = 0, y0: int = 80,
              total_w: int = 240, total_h: int = 240) -> tuple:
    """Return (x, y, w, h) for a grid cell on the home page."""
    bw, bh = total_w // cols, total_h // rows
    return x0 + col * bw, y0 + row * bh, bw, bh


for m, label, col, row in [
    (m_cable,  'Cable TV',   0, 0),
    (m_sat,    'Satellite',  1, 0),
    (m_atv,    'Apple TV',   0, 1),
    (m_stream, 'Streaming',  1, 1),
    (m_bluray, 'Blu-ray',    0, 2),
    (m_alloff, 'All Off',    1, 2),
]:
    x, y, w, h = home_rect(col, row)
    t2i.add_source_button(label, macro=m, x=x, y=y, w=w, h=h)


# ---------- Secondary page: transport row + volume strip + nav buttons ----

def sec_rect(col: int, row: int,
             cols: int = 2, rows: int = 3,
             x0: int = 0, y0: int = 60,
             total_w: int = 240, total_h: int = 180) -> tuple:
    """Return (x, y, w, h) for a grid cell on the secondary page."""
    bw, bh = total_w // cols, total_h // rows
    return x0 + col * bw, y0 + row * bh, bw, bh


# Transport row
for m, label, col, row in [
    (m_prev, 'Rewind', 0, 0), (m_play,  'Play',   1, 0),
    (m_next, 'Fwd',    0, 1), (m_pause, 'Pause',  1, 1),
    (m_stop, 'Stop',   0, 2), (m_rec,   'Record', 1, 2),
]:
    x, y, w, h = sec_rect(col, row)
    t2i.add_secondary_button(label, macro=m, x=x, y=y, w=w, h=h)

# Volume strip
bw = 240 // 3
for col, (m, label) in enumerate([(m_voldn, 'Vol-'), (m_mute, 'Mute'), (m_volup, 'Vol+')]):
    t2i.add_secondary_button(label, macro=m, x=col * bw, y=240, w=bw, h=60)

# Back / Home row
for col, (m, label) in enumerate([(m_back, 'Back'), (m_home, 'Home')]):
    t2i.add_secondary_button(label, macro=m, x=col * 120, y=300, w=120, h=20)


# ---------- Physical hardware button macros (all 52 slots 128-179) --------
#
# T2i hardware slot reference (relative to base index 128):
#   128=Exit      129=Mute       130=Softkey2  131=Up       132=Left
#   133=Right     134=Down       135=OK        136=Softkey1 137=Softkey4
#   138=Vol+      139=Vol-       140=Ch+       141=Ch-      142=Guide
#   143=Menu      144=Info       145=PwrOff    146=Play     147=Pause
#   148=Stop      149=Record     150=Scan<<    151=Scan>>   152=Skip<<
#   153=Skip>>    154-163=1-0    164=-/.       165=Enter
#   166=JoyUp     167=JoyClick   168=JoyDn     169=JoyLeft  170=JoyRight
#   171=PwrOn     172=List       173=Red       174=Green    175=Yellow
#   176=Blue      177=Softkey3   178=Prev      179=Back

hw = {
    128: m_exit,   129: m_mute,
    130: m_atv,    # Softkey 2 repurposed as Apple TV shortcut
    131: m_up,     132: m_left,    133: m_right,
    134: m_down,   135: m_select,
    136: m_sk1,    # Softkey 1
    137: m_sk4,    # Softkey 4
    138: m_volup,  139: m_voldn,
    140: m_chup,   141: m_chdn,
    142: m_guide,  143: m_menu,
    144: m_info,   145: m_off,
    146: m_play,   147: m_pause,   148: m_stop,
    149: m_rec,
    150: m_prev,   151: m_next,
    152: m_prev_btn, 153: m_next_btn,
    154: m_1,  155: m_2,  156: m_3,
    157: m_4,  158: m_5,  159: m_6,
    160: m_7,  161: m_8,  162: m_9,
    163: m_0,  164: m_clear,  165: m_enter,
    166: m_joy_up, 167: m_joy_click, 168: m_joy_dn,
    169: m_joy_left, 170: m_joy_right,
    171: m_on,
    172: m_fav,
    173: m_red,  174: m_green,  175: m_yellow,  176: m_blue,
    177: m_sk3,    # Softkey 3
    178: m_prev_btn,
    179: m_back,
}
for slot_index, slot_macro in hw.items():
    t2i.assign_hw_button_macro(slot_index, slot_macro)


# ---------------------------------------------------------------------------
# Assemble and save
# ---------------------------------------------------------------------------
proj = RTIProject()
proj.add_device(xp)
proj.add_device(t2i)

out_path = os.path.join(os.path.dirname(__file__), 'out_basic_t2i.rti')
size = proj.save(out_path)
print(f'Saved {size:,} bytes -> {os.path.basename(out_path)}')
print('Open out_basic_t2i.rti in RTI Integration Designer to verify.')
