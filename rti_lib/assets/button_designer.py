"""
rti_lib/assets/button_designer.py

Programmatic button and background graphic generator for the T2i (240×320).

Provides preset styles including "oasis" (dark navy→teal ambient glow),
plus utilities to composite button labels and icons on top of backgrounds.

Usage
-----
    from rti_lib.assets.button_designer import ButtonDesigner, Style

    # Full-screen Oasis background
    bg = ButtonDesigner.background(Style.OASIS)

    # Oasis background with a channel icon overlaid at centre
    bg = ButtonDesigner.background(Style.OASIS, icon_png=png_bytes,
                                   icon_x=89, icon_y=137)

    # Individual rounded-rect button chip (for compositing onto a background)
    chip = ButtonDesigner.button_chip(
        width=90, height=40,
        label='Play',
        style=Style.OASIS,
    )

    # Composite: put a chip onto an existing background
    rgb = ButtonDesigner.composite(background_rgb, chip, x=75, y=140)
"""

from __future__ import annotations
import io
import math
from dataclasses import dataclass, field
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter

T2I_WIDTH  = 240
T2I_HEIGHT = 320
Color = Tuple[int, int, int]


# ---------------------------------------------------------------------------
# Style presets
# ---------------------------------------------------------------------------

@dataclass
class StyleDef:
    """Visual style definition."""
    # Background gradient (top-left → bottom) for full-screen backdrop
    bg_top_left:   Color = (7,   22,  44)
    bg_top_right:  Color = (21,  64, 110)
    bg_bottom:     Color = (100, 210, 160)
    # Accent glow: painted as a soft radial at a specific spot
    glow_center:   Color = (90, 200, 220)
    glow_pos:      Tuple[float, float] = (0.6, 0.35)   # (x_frac, y_frac)
    glow_radius:   float = 0.45                         # fraction of screen height
    glow_alpha:    int   = 120                          # 0-255
    # Button chip
    chip_top:      Color = (40,  100, 130)
    chip_bottom:   Color = (10,   30,  50)
    chip_border:   Color = (80,  180, 200)
    chip_text:     Color = (220, 240, 255)
    chip_radius:   int   = 8                            # corner radius px
    chip_gloss:    bool  = True


class Style:
    """Named style presets."""

    OASIS = StyleDef(
        bg_top_left   = (7,   22,  44),
        bg_top_right  = (21,  64, 110),
        bg_bottom     = (100, 210, 160),
        glow_center   = (60,  190, 215),
        glow_pos      = (0.62, 0.30),
        glow_radius   = 0.50,
        glow_alpha    = 110,
        chip_top      = (35,   95, 125),
        chip_bottom   = (8,    25,  45),
        chip_border   = (70,  175, 200),
        chip_text     = (215, 240, 255),
        chip_radius   = 8,
        chip_gloss    = True,
    )

    DARK_STEEL = StyleDef(
        bg_top_left   = (25,  25,  30),
        bg_top_right  = (40,  40,  50),
        bg_bottom     = (15,  15,  20),
        glow_center   = (100, 120, 160),
        glow_pos      = (0.5, 0.3),
        glow_radius   = 0.35,
        glow_alpha    = 80,
        chip_top      = (60,  65,  80),
        chip_bottom   = (20,  22,  28),
        chip_border   = (100, 110, 140),
        chip_text     = (220, 225, 235),
        chip_radius   = 6,
        chip_gloss    = True,
    )

    NIGHT_BLUE = StyleDef(
        bg_top_left   = (5,   10,  40),
        bg_top_right  = (10,  20,  70),
        bg_bottom     = (15,  30, 100),
        glow_center   = (40,  80, 200),
        glow_pos      = (0.5, 0.5),
        glow_radius   = 0.45,
        glow_alpha    = 90,
        chip_top      = (30,  60, 160),
        chip_bottom   = (8,   18,  60),
        chip_border   = (60, 100, 220),
        chip_text     = (200, 220, 255),
        chip_radius   = 7,
        chip_gloss    = True,
    )

    MINIMAL = StyleDef(
        bg_top_left   = (18,  18,  18),
        bg_top_right  = (18,  18,  18),
        bg_bottom     = (10,  10,  10),
        glow_center   = (50,  50,  50),
        glow_pos      = (0.5, 0.5),
        glow_radius   = 0.3,
        glow_alpha    = 40,
        chip_top      = (50,  50,  50),
        chip_bottom   = (25,  25,  25),
        chip_border   = (90,  90,  90),
        chip_text     = (240, 240, 240),
        chip_radius   = 5,
        chip_gloss    = False,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _lerp_color(a: Color, b: Color, t: float) -> Color:
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _build_background(style: StyleDef, width: int, height: int) -> Image.Image:
    """
    Generate a bilinear-gradient background:
      - Top edge: left→right from bg_top_left to bg_top_right
      - Bottom: converges to bg_bottom (same across x)
    Plus a soft radial glow overlay.
    """
    img = Image.new('RGB', (width, height))
    pixels = img.load()

    for y in range(height):
        yt = y / (height - 1)
        for x in range(width):
            xt = x / (width - 1)
            # Horizontal blend along top
            top_col = _lerp_color(style.bg_top_left, style.bg_top_right, xt)
            # Vertical blend toward bottom
            col = _lerp_color(top_col, style.bg_bottom, yt)
            pixels[x, y] = col

    # Radial glow overlay
    gx = int(style.glow_pos[0] * width)
    gy = int(style.glow_pos[1] * height)
    max_r = style.glow_radius * height

    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    opx = overlay.load()
    for y in range(height):
        for x in range(width):
            d = math.sqrt((x - gx)**2 + (y - gy)**2)
            if d < max_r:
                t = 1.0 - (d / max_r)
                a = int(style.glow_alpha * t * t)
                opx[x, y] = (*style.glow_center, a)

    img = img.convert('RGBA')
    img.alpha_composite(overlay)
    return img.convert('RGB')


def _try_font(size: int) -> ImageFont.ImageFont:
    """Return a font, falling back to default if truetype not available."""
    try:
        return ImageFont.truetype('arial.ttf', size)
    except OSError:
        try:
            return ImageFont.truetype(
                r'C:\Windows\Fonts\arial.ttf', size)
        except OSError:
            return ImageFont.load_default()


def _draw_chip(draw: ImageDraw.Draw,
               x0: int, y0: int, x1: int, y1: int,
               style: StyleDef) -> None:
    """Draw a rounded-rect button chip at the given coords on *draw*."""
    r = style.chip_radius

    # Gradient fill (simulated by drawing horizontal lines)
    h = y1 - y0
    for dy in range(h):
        t = dy / max(h - 1, 1)
        col = _lerp_color(style.chip_top, style.chip_bottom, t)
        # Clip to rounded rect by checking corner distance
        draw.line([(x0, y0 + dy), (x1, y0 + dy)], fill=col)

    # Border
    draw.rounded_rectangle([x0, y0, x1, y1], radius=r,
                            outline=style.chip_border, width=1, fill=None)

    # Gloss highlight: top quarter, semi-transparent white
    if style.chip_gloss and h > 8:
        gloss_h = max(h // 4, 4)
        for dy in range(gloss_h):
            t = dy / gloss_h
            alpha = int(60 * (1 - t))
            # We can't do alpha easily per-line; just draw a lighter stripe
            col = _lerp_color(
                (min(style.chip_top[0] + 60, 255),
                 min(style.chip_top[1] + 60, 255),
                 min(style.chip_top[2] + 60, 255)),
                style.chip_top, t)
            draw.line([(x0 + r if dy < 2 else x0, y0 + dy),
                       (x1 - r if dy < 2 else x1, y0 + dy)], fill=col)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class ButtonDesigner:
    """Namespace of static generator methods."""

    @staticmethod
    def background(style: StyleDef = Style.OASIS,
                   width: int = T2I_WIDTH,
                   height: int = T2I_HEIGHT,
                   icon_png: Optional[bytes] = None,
                   icon_x: Optional[int] = None,
                   icon_y: Optional[int] = None) -> bytes:
        """
        Generate a full-screen background in the given style.

        Optionally composites a PNG icon (with alpha) centred at
        (icon_x, icon_y).  If icon_x/y are omitted, the icon is centred.

        Returns raw RGB bytes (width * height * 3), top-to-bottom.
        """
        img = _build_background(style, width, height)

        if icon_png is not None:
            icon = Image.open(io.BytesIO(icon_png)).convert('RGBA')
            ix = icon_x if icon_x is not None else (width - icon.width) // 2
            iy = icon_y if icon_y is not None else (height - icon.height) // 2
            img.paste(icon, (ix, iy), mask=icon.split()[3])

        return img.tobytes()

    @staticmethod
    def button_chip(width: int, height: int,
                    label: str = '',
                    style: StyleDef = Style.OASIS,
                    font_size: int = 12,
                    icon_png: Optional[bytes] = None) -> bytes:
        """
        Generate a standalone button-chip graphic (PNG bytes with alpha).

        The returned PNG can be overlaid onto a background using
        ``composite()`` or ``ImageLoader.overlay_png()``.

        Parameters
        ----------
        width, height : Chip dimensions in pixels.
        label         : Optional text label drawn centred in the chip.
        style         : Visual style preset.
        font_size     : Point size for the label.
        icon_png      : Optional small PNG icon to show above the label.
        """
        img  = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        r = style.chip_radius

        # Gradient fill
        for dy in range(height):
            t = dy / max(height - 1, 1)
            col = _lerp_color(style.chip_top, style.chip_bottom, t)
            draw.line([(0, dy), (width - 1, dy)], fill=(*col, 220))

        # Mask to rounded rect
        mask = Image.new('L', (width, height), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([0, 0, width - 1, height - 1],
                                    radius=r, fill=255)
        img.putalpha(mask)

        # Redraw on masked image
        draw = ImageDraw.Draw(img)

        # Gloss top stripe
        if style.chip_gloss:
            gloss_h = max(height // 4, 4)
            for dy in range(gloss_h):
                t = dy / gloss_h
                a = int(80 * (1 - t))
                bright = tuple(min(c + 70, 255) for c in style.chip_top)
                draw.line([(0, dy), (width - 1, dy)],
                          fill=(*bright, a))

        # Border
        draw.rounded_rectangle([0, 0, width - 1, height - 1],
                                radius=r, outline=(*style.chip_border, 200),
                                width=1)

        # Icon
        icon_bottom = 4
        if icon_png is not None:
            icon = Image.open(io.BytesIO(icon_png)).convert('RGBA')
            # Scale icon to fit in top half of chip
            max_icon_h = height // 2 - 4
            max_icon_w = width - 8
            icon.thumbnail((max_icon_w, max_icon_h), Image.LANCZOS)
            ix = (width - icon.width) // 2
            iy = 4
            img.paste(icon, (ix, iy), mask=icon.split()[3])
            icon_bottom = iy + icon.height + 2

        # Label text
        if label:
            font = _try_font(font_size)
            # PIL 10+ uses textbbox; older uses textsize
            try:
                bb = draw.textbbox((0, 0), label, font=font)
                tw, th = bb[2] - bb[0], bb[3] - bb[1]
            except AttributeError:
                tw, th = draw.textsize(label, font=font)
            tx = (width - tw) // 2
            ty = icon_bottom + (height - icon_bottom - th) // 2
            # Shadow
            draw.text((tx + 1, ty + 1), label, font=font,
                      fill=(0, 0, 0, 160))
            draw.text((tx, ty), label, font=font,
                      fill=(*style.chip_text, 240))

        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()

    @staticmethod
    def composite(background_rgb: bytes,
                  overlay_png: bytes,
                  x: int, y: int,
                  width: int = T2I_WIDTH,
                  height: int = T2I_HEIGHT) -> bytes:
        """
        Paste a PNG (with alpha) on top of a raw RGB background.

        Returns updated raw RGB bytes (width * height * 3).
        """
        bg = Image.frombytes('RGB', (width, height), background_rgb)
        ov = Image.open(io.BytesIO(overlay_png)).convert('RGBA')
        bg.paste(ov, (x, y), mask=ov.split()[3])
        return bg.tobytes()

    @staticmethod
    def save_preview(rgb: bytes,
                     path: str,
                     width: int = T2I_WIDTH,
                     height: int = T2I_HEIGHT) -> None:
        """Save raw RGB bytes as a PNG preview image."""
        Image.frombytes('RGB', (width, height), rgb).save(path)

    @staticmethod
    def preview_png(rgb: bytes,
                    width: int = T2I_WIDTH,
                    height: int = T2I_HEIGHT) -> bytes:
        """Convert raw RGB bytes to PNG bytes (for embedding or saving)."""
        buf = io.BytesIO()
        Image.frombytes('RGB', (width, height), rgb).save(buf, format='PNG')
        return buf.getvalue()
