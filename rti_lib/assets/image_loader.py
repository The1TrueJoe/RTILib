"""
rti_lib/assets/image_loader.py

Universal image-to-T2i converter.

Takes any image source and returns raw 24-bit RGB bytes (top-to-bottom)
suitable for passing directly to encode_t2i_image().

Sources supported
-----------------
  - File path  (JPEG, PNG, BMP, GIF, TIFF, WebP — anything Pillow reads)
  - Raw PNG / JPEG bytes in memory
  - An IconLibrary entry (PNG from template)
  - Solid colour
  - Vertical or radial gradient

All outputs are exactly width × height × 3 bytes, RGB, top-to-bottom.

Usage
-----
    from rti_lib.assets.image_loader import ImageLoader

    # Load a photo and resize to T2i screen
    rgb = ImageLoader.from_file('photo.jpg')

    # Solid background
    rgb = ImageLoader.solid(r=20, g=30, b=80)

    # From an icon library (scales the icon to full screen — unusual but valid)
    rgb = ImageLoader.from_library_entry(lib, 'ABC')

    # Oasis-style dark gradient background
    rgb = ImageLoader.gradient_v(top=(10,20,60), bottom=(30,50,120))
"""

from __future__ import annotations
import io
from typing import Union, Tuple
from PIL import Image, ImageDraw

# Default T2i display resolution
T2I_WIDTH  = 240
T2I_HEIGHT = 320

Color = Tuple[int, int, int]   # (R, G, B) each 0-255


def _pil_to_rgb(img: Image.Image, width: int, height: int) -> bytes:
    """Resize *img* to (width, height), convert to RGB, return raw bytes."""
    if img.size != (width, height):
        img = img.resize((width, height), Image.LANCZOS)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    return img.tobytes()


class ImageLoader:
    """Namespace of static factory methods — instantiation is not needed."""

    # ------------------------------------------------------------------
    # File / bytes sources
    # ------------------------------------------------------------------

    @staticmethod
    def from_file(path: str,
                  width: int = T2I_WIDTH,
                  height: int = T2I_HEIGHT) -> bytes:
        """
        Load any image file Pillow can read and resize to (width, height).
        Returns width*height*3 raw RGB bytes, top-to-bottom.
        """
        img = Image.open(path)
        return _pil_to_rgb(img, width, height)

    @staticmethod
    def from_bytes(data: bytes,
                   width: int = T2I_WIDTH,
                   height: int = T2I_HEIGHT) -> bytes:
        """
        Load from in-memory bytes (PNG, JPEG, BMP, etc.) and resize.
        """
        img = Image.open(io.BytesIO(data))
        return _pil_to_rgb(img, width, height)

    @staticmethod
    def from_png(png_bytes: bytes,
                 width: int = T2I_WIDTH,
                 height: int = T2I_HEIGHT) -> bytes:
        """Alias for from_bytes — explicit name for PNG sources."""
        return ImageLoader.from_bytes(png_bytes, width, height)

    # ------------------------------------------------------------------
    # Library source
    # ------------------------------------------------------------------

    @staticmethod
    def from_library_entry(library,
                           name: str,
                           state: str = 'up',
                           width: int = T2I_WIDTH,
                           height: int = T2I_HEIGHT) -> bytes:
        """
        Load an image from an IconLibrary by name and resize to (width, height).

        Parameters
        ----------
        library : An IconLibrary instance.
        name    : Image name (case-insensitive).
        state   : 'up' or 'down'.
        """
        png = library.get_png(name, state)
        return ImageLoader.from_bytes(png, width, height)

    # ------------------------------------------------------------------
    # Programmatic sources
    # ------------------------------------------------------------------

    @staticmethod
    def solid(r: int = 0, g: int = 0, b: int = 0,
              width: int = T2I_WIDTH,
              height: int = T2I_HEIGHT) -> bytes:
        """Solid colour fill."""
        return bytes([r, g, b] * (width * height))

    @staticmethod
    def gradient_v(top: Color = (10, 20, 60),
                   bottom: Color = (30, 50, 120),
                   width: int = T2I_WIDTH,
                   height: int = T2I_HEIGHT) -> bytes:
        """
        Vertical linear gradient from *top* colour to *bottom* colour.
        Top of the image uses *top*, bottom uses *bottom*.
        """
        img = Image.new('RGB', (width, height))
        draw = ImageDraw.Draw(img)
        for y in range(height):
            t = y / (height - 1)
            r = int(top[0] + (bottom[0] - top[0]) * t)
            g = int(top[1] + (bottom[1] - top[1]) * t)
            b = int(top[2] + (bottom[2] - top[2]) * t)
            draw.line([(0, y), (width - 1, y)], fill=(r, g, b))
        return img.tobytes()

    @staticmethod
    def gradient_h(left: Color = (10, 20, 60),
                   right: Color = (30, 50, 120),
                   width: int = T2I_WIDTH,
                   height: int = T2I_HEIGHT) -> bytes:
        """Horizontal linear gradient."""
        img = Image.new('RGB', (width, height))
        pixels = img.load()
        for x in range(width):
            t = x / (width - 1)
            r = int(left[0] + (right[0] - left[0]) * t)
            g = int(left[1] + (right[1] - left[1]) * t)
            b = int(left[2] + (right[2] - left[2]) * t)
            for y in range(height):
                pixels[x, y] = (r, g, b)
        return img.tobytes()

    @staticmethod
    def gradient_radial(center: Color = (40, 70, 160),
                        edge: Color = (5, 10, 30),
                        width: int = T2I_WIDTH,
                        height: int = T2I_HEIGHT) -> bytes:
        """
        Radial gradient, bright in the centre, dark at the edges.
        Useful for Oasis-style ambient glows.
        """
        import math
        cx, cy = width / 2, height / 2
        max_r = math.sqrt(cx**2 + cy**2)
        img = Image.new('RGB', (width, height))
        pixels = img.load()
        for y in range(height):
            for x in range(width):
                d = math.sqrt((x - cx)**2 + (y - cy)**2)
                t = min(d / max_r, 1.0)
                r = int(center[0] + (edge[0] - center[0]) * t)
                g = int(center[1] + (edge[1] - center[1]) * t)
                b = int(center[2] + (edge[2] - center[2]) * t)
                pixels[x, y] = (r, g, b)
        return img.tobytes()

    # ------------------------------------------------------------------
    # Composition helpers
    # ------------------------------------------------------------------

    @staticmethod
    def overlay_png(background_rgb: bytes,
                    png_bytes: bytes,
                    x: int, y: int,
                    width: int = T2I_WIDTH,
                    height: int = T2I_HEIGHT) -> bytes:
        """
        Paste a PNG (with optional transparency) onto a background.

        Parameters
        ----------
        background_rgb : Raw RGB bytes (width*height*3) for the backdrop.
        png_bytes      : PNG image bytes to overlay (supports alpha).
        x, y           : Top-left position for the overlay.
        """
        bg = Image.frombytes('RGB', (width, height), background_rgb)
        overlay = Image.open(io.BytesIO(png_bytes)).convert('RGBA')
        bg.paste(overlay, (x, y), mask=overlay.split()[3])
        if bg.mode != 'RGB':
            bg = bg.convert('RGB')
        return bg.tobytes()
