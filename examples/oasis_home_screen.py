"""
examples/oasis_home_screen.py
==============================
Full Oasis-style T2i home screen: background + chips + icons + RTI buttons.

Demonstrates every tool in rti_lib.assets:
  - IconLibrary   → loads 112×112 icons from RTI template files
  - ButtonDesigner → Oasis gradient background + rounded-rect button chips
  - ImageLoader   → alpha-composite PNG overlays onto the background

Screen layout (240 × 320 px):

    ┌──────────────────────────────┐
    │       LIVING ROOM (header)   │  y   0-34   dark overlay + cyan text
    ├─────────────┬────────────────┤
    │  [Cable TV] │  [Satellite]   │  y  38-117  source row 0
    ├─────────────┼────────────────┤
    │  [Apple TV] │  [Blu-ray]     │  y 119-199  source row 1
    ├─────────────┼────────────────┤
    │ [Streaming] │  [Power Off]   │  y 201-279  source row 2
    ├──────────────────────────────┤
    │  [|<] [> ] [||] [>|]  [[] ] │  y 283-319  transport strip
    └──────────────────────────────┘

Outputs:
    examples/out_oasis_home.png  — visual preview (open in any image viewer)
    examples/out_oasis.rti       — loadable project file for Integration Designer

Prerequisites
-------------
    pip install Pillow
    RTI Integration Designer installed at the default path (for icon libraries)

Usage
-----
    python examples/oasis_home_screen.py

To browse available icons:
    python -m rti_lib.tools.browse_template list "Source and Zone Icons.rtitemplate"
    python -m rti_lib.tools.browse_template grid "Source and Zone Icons.rtitemplate" grid.png
    python -m rti_lib.tools.browse_template sheet "Source and Zone Icons.rtitemplate" sheet.html
"""

import io
import os
import sys

# Allow running from the repo root without installing the package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from PIL import Image, ImageDraw, ImageFont

from rti_lib import RTIProject, T2iRemote
from rti_lib.devices.xp import XPProcessor
from rti_lib.assets.icon_library import IconLibrary
from rti_lib.assets.button_designer import ButtonDesigner, Style

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REMOTE_NAME   = 'Living Room T2i'
TEMPLATE_DIR  = r'C:\Program Files (x86)\RTI\Integration Designer\Templates'
STYLE         = Style.OASIS

# Screen dimensions (T2i hardware)
W, H = 240, 320

# Layout metrics
HDR_H        = 35   # header bar height (px)
GAP          = 3    # gap between chips (px)
SRC_ROWS     = 3    # source button rows
SRC_COLS     = 2    # source button columns
SRC_Y0       = HDR_H + GAP
SRC_TOTAL_H  = 244  # total height consumed by the 3 source rows
SRC_CHIP_W   = (W - GAP * (SRC_COLS + 1)) // SRC_COLS      # ≈115 px
SRC_CHIP_H   = (SRC_TOTAL_H - GAP * (SRC_ROWS + 1)) // SRC_ROWS  # ≈78 px

TRANSPORT = [
    ('|<',  'Prev'),
    ('> ',  'Play'),
    ('||',  'Pause'),
    ('>|',  'Next'),
    ('[]',  'Stop'),
]
TRN_Y0      = H - 37
TRN_H       = H - TRN_Y0
TRN_CHIP_W  = (W - GAP * (len(TRANSPORT) + 1)) // len(TRANSPORT)

# ---------------------------------------------------------------------------
# Load RTI icon libraries
# ---------------------------------------------------------------------------
src_lib = IconLibrary.load(TEMPLATE_DIR + r'\Source and Zone Icons.rtitemplate')
usi_lib = IconLibrary.load(TEMPLATE_DIR + r'\Universal Source Icons 2.rtitemplate')
print(f'Loaded {src_lib.summary()}')
print(f'Loaded {usi_lib.summary()}')

# Source button definitions: (grid_col, grid_row, label, library, icon_name)
# Use `browse_template list` or `browse_template sheet` to find other icon names.
SOURCES = [
    (0, 0, 'Cable TV',   src_lib, 'Icon (112x112) - Cable'),
    (1, 0, 'Satellite',  src_lib, 'Icon (112x112) - Satellite'),
    (0, 1, 'Apple TV',   src_lib, 'Icon (112x112) - Apple TV'),
    (1, 1, 'Blu-ray',    src_lib, 'Icon (112x112) - Disc BD'),
    (0, 2, 'Streaming',  usi_lib, 'Icon (112 x 112) - Monitor Blue'),
    (1, 2, 'Power Off',  usi_lib, 'Icon (112 x 112) - Power Red'),
]

# ---------------------------------------------------------------------------
# Font helper
# ---------------------------------------------------------------------------
def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in [r'C:\Windows\Fonts\arialbd.ttf',
                 r'C:\Windows\Fonts\arial.ttf',
                 'arial.ttf']:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Build background (Oasis gradient)
# ---------------------------------------------------------------------------
bg_rgb = ButtonDesigner.background(STYLE, width=W, height=H)
bg = Image.frombytes('RGB', (W, H), bg_rgb)

# ---------------------------------------------------------------------------
# Header bar: dark translucent overlay + centred room name
# ---------------------------------------------------------------------------
hdr = Image.new('RGBA', (W, HDR_H), (5, 15, 35, 200))
bg  = bg.convert('RGBA')
bg.alpha_composite(hdr)
bg  = bg.convert('RGB')

draw     = ImageDraw.Draw(bg)
title    = 'LIVING ROOM'
font_hdr = _font(16)
try:
    bb = draw.textbbox((0, 0), title, font=font_hdr)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
except AttributeError:
    tw, th = draw.textsize(title, font=font_hdr)
draw.text(((W - tw) // 2, (HDR_H - th) // 2), title,
          font=font_hdr, fill=(160, 220, 230))

# ---------------------------------------------------------------------------
# Source button chips (icon + label, composited onto the background)
# ---------------------------------------------------------------------------
# src_button_rects maps each label → (x, y, w, h) pixel rectangle.
# These same coordinates are registered as RTI touch-button regions below.
src_button_rects: dict = {}

for col, row, label, lib, icon_name in SOURCES:
    cx = GAP + col * (SRC_CHIP_W + GAP)
    cy = SRC_Y0 + GAP + row * (SRC_CHIP_H + GAP)

    src_button_rects[label] = (cx, cy, SRC_CHIP_W, SRC_CHIP_H)

    # Load icon PNG from the library (silently skip on KeyError)
    try:
        icon_png = lib.get_png(icon_name)
    except KeyError as e:
        print(f'  WARNING: icon not found — {e}')
        icon_png = None

    # Generate the chip PNG (RGBA with rounded corners)
    chip_png = ButtonDesigner.button_chip(
        SRC_CHIP_W, SRC_CHIP_H,
        label=label,
        style=STYLE,
        font_size=11,
        icon_png=icon_png,
    )

    # Alpha-composite the chip onto the background
    chip_img = Image.open(io.BytesIO(chip_png)).convert('RGBA')
    bg.paste(chip_img, (cx, cy), mask=chip_img.split()[3])
    print(f'  Source chip: {label:12s} at ({cx},{cy}) {SRC_CHIP_W}×{SRC_CHIP_H}')

# ---------------------------------------------------------------------------
# Transport strip (ASCII label chips at the bottom)
# ---------------------------------------------------------------------------
trn_button_rects: dict = {}

for i, (symbol, name) in enumerate(TRANSPORT):
    tx = GAP + i * (TRN_CHIP_W + GAP)
    trn_button_rects[name] = (tx, TRN_Y0, TRN_CHIP_W, TRN_H)

    chip_png = ButtonDesigner.button_chip(
        TRN_CHIP_W, TRN_H,
        label=symbol,
        style=STYLE,
        font_size=14,
    )
    chip_img = Image.open(io.BytesIO(chip_png)).convert('RGBA')
    bg.paste(chip_img, (tx, TRN_Y0), mask=chip_img.split()[3])
    print(f'  Transport:   {name:8s} [{symbol}] at ({tx},{TRN_Y0}) {TRN_CHIP_W}×{TRN_H}')

# ---------------------------------------------------------------------------
# Save preview PNG
# ---------------------------------------------------------------------------
preview_path = os.path.join(os.path.dirname(__file__), 'out_oasis_home.png')
bg.save(preview_path)
print(f'\nPreview saved: {preview_path}')

# Convert to raw RGB bytes for the T2i encoder
bg_rgb = bg.tobytes()

# ---------------------------------------------------------------------------
# XP Processor — one macro per user action
# ---------------------------------------------------------------------------
xp = XPProcessor('XP-6', display_name='Living Room AV')


def macro(label: str, cmd: bytes, port: int = 0, baud: int = 9600):
    """Add a serial macro to the XP processor."""
    return xp.add_macro(
        f'{REMOTE_NAME} - {label}',
        serial=cmd, baud=baud, port=port,
        device_name='AV Receiver', manufacturer='Generic', model_str='AVR',
    )


# Source selection
m_cable   = macro('Cable TV',   b'src hdmi1\r')
m_sat     = macro('Satellite',  b'src hdmi2\r')
m_atv     = macro('Apple TV',   b'src hdmi3\r')
m_bluray  = macro('Blu-ray',    b'src hdmi5\r')
m_stream  = macro('Streaming',  b'src hdmi4\r')
m_alloff  = macro('All Off',    b'pwr off\r')

# Transport
m_prev    = macro('Prev',   b'prev\r')
m_play    = macro('Play',   b'play\r')
m_pause   = macro('Pause',  b'pause\r')
m_next    = macro('Next',   b'next\r')
m_stop    = macro('Stop',   b'stop\r')

# Navigation + system (hardware buttons only — not on touchscreen)
m_volup      = macro('Vol+',     b'vol+\r')
m_voldn      = macro('Vol-',     b'vol-\r')
m_mute       = macro('Mute',     b'mute\r')
m_up         = macro('Up',       b'nav up\r')
m_down       = macro('Down',     b'nav down\r')
m_left       = macro('Left',     b'nav left\r')
m_right      = macro('Right',    b'nav right\r')
m_select     = macro('Select',   b'nav ok\r')
m_back       = macro('Back',     b'nav back\r')
m_menu       = macro('Menu',     b'nav menu\r')
m_info       = macro('Info',     b'nav info\r')
m_guide      = macro('Guide',    b'nav guide\r')
m_chup       = macro('Ch+',      b'ch+\r')
m_chdn       = macro('Ch-',      b'ch-\r')
m_exit       = macro('Exit',     b'nav exit\r')
m_on         = macro('On',       b'pwr on\r')
m_off        = macro('Off',      b'pwr off\r')
m_rec        = macro('Record',   b'rec\r')
m_fav        = macro('Fav',      b'fav\r')
m_home       = macro('Home',     b'nav home\r')
m_prev_btn   = macro('Prev btn', b'prev\r')
m_next_btn   = macro('Next btn', b'next\r')
m_sk1        = macro('Softkey 1', b'custom sk1\r')
m_sk2        = macro('Softkey 2', b'custom sk2\r')
m_sk3        = macro('Softkey 3', b'custom sk3\r')
m_sk4        = macro('Softkey 4', b'custom sk4\r')
m_joy_up    = macro('Joy Up',    b'joy up\r')
m_joy_click = macro('Joy Click', b'joy click\r')
m_joy_dn    = macro('Joy Down',  b'joy dn\r')
m_joy_left  = macro('Joy Left',  b'joy left\r')
m_joy_right = macro('Joy Right', b'joy right\r')
m_red    = macro('Red',    b'color red\r')
m_green  = macro('Green',  b'color green\r')
m_yellow = macro('Yellow', b'color yellow\r')
m_blue   = macro('Blue',   b'color blue\r')

# Number pad
m_1 = macro('1', b'key 1\r');  m_2 = macro('2', b'key 2\r');  m_3 = macro('3', b'key 3\r')
m_4 = macro('4', b'key 4\r');  m_5 = macro('5', b'key 5\r');  m_6 = macro('6', b'key 6\r')
m_7 = macro('7', b'key 7\r');  m_8 = macro('8', b'key 8\r');  m_9 = macro('9', b'key 9\r')
m_0 = macro('0', b'key 0\r');  m_enter = macro('Enter', b'key enter\r')
m_clear = macro('Clear', b'key clear\r')

# ---------------------------------------------------------------------------
# T2i Remote
# ---------------------------------------------------------------------------
t2i = T2iRemote(display_name=REMOTE_NAME)
t2i.set_background(bg_rgb)

# --- Touchscreen source buttons (pixel regions matching the rendered chips) ---
src_macro_map = {
    'Cable TV':   m_cable,
    'Satellite':  m_sat,
    'Apple TV':   m_atv,
    'Blu-ray':    m_bluray,
    'Streaming':  m_stream,
    'Power Off':  m_alloff,
}
for label, (x, y, w, h) in src_button_rects.items():
    t2i.add_source_button(label, macro=src_macro_map[label], x=x, y=y, w=w, h=h)
    print(f'  RTI source btn: {label} @ ({x},{y}) {w}×{h}')

# --- Touchscreen transport buttons ---
trn_macro_map = {
    'Prev':  m_prev,
    'Play':  m_play,
    'Pause': m_pause,
    'Next':  m_next,
    'Stop':  m_stop,
}
for name, (x, y, w, h) in trn_button_rects.items():
    t2i.add_source_button(name, macro=trn_macro_map[name], x=x, y=y, w=w, h=h)
    print(f'  RTI transport:  {name} @ ({x},{y}) {w}×{h}')

# --- Physical hardware button macros (all 52 slots 128-179) ---
#
# T2i hardware slot reference:
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
    130: m_sk2,    # Softkey 2
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

# Secondary page: volume row (reachable via swipe / hardware nav)
bw = W // 3
for col, (m, label) in enumerate([(m_voldn, 'Vol-'), (m_mute, 'Mute'), (m_volup, 'Vol+')]):
    t2i.add_secondary_button(label, macro=m, x=col * bw, y=270, w=bw, h=50)

# ---------------------------------------------------------------------------
# Assemble and save
# ---------------------------------------------------------------------------
proj = RTIProject()
proj.add_device(xp)
proj.add_device(t2i)

out_path = os.path.join(os.path.dirname(__file__), 'out_oasis.rti')
size = proj.save(out_path)
print(f'\nSaved {size:,} bytes -> {os.path.basename(out_path)}')
print('Open out_oasis.rti in RTI Integration Designer to verify.')
