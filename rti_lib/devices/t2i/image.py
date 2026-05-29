"""
rti_lib/devices/t2i/image.py

Custom image loading for T2i backgrounds.

Load any PNG, JPEG, BMP, GIF, or TIFF file as the raw 240×320 RGB bytes
required by T2iRemote.set_background().

Requires Pillow — install with:  pip install Pillow

Usage::

    from rti_lib.devices.t2i.image import load_image_rgb

    rgb = load_image_rgb('my_background.png')          # auto-resized to 240x320
    rgb = load_image_rgb('photo.jpg', width=240, height=320)

    t2i = T2iRemote()
    t2i.set_background(rgb)
"""

from rti_lib.devices.t2i.stream_profile import T2I_WIDTH, T2I_HEIGHT


def load_image_rgb(
    path: str,
    width: int  = T2I_WIDTH,
    height: int = T2I_HEIGHT,
    background: tuple = (255, 255, 255),
) -> bytes:
    """
    Load an image from *path* and return raw 24-bit RGB bytes.

    The image is:
    1. Opened in any format Pillow supports (PNG, JPEG, BMP, GIF, TIFF, …)
    2. Alpha channels are composited onto *background* (default white).
    3. Resized to *width* × *height* using high-quality Lanczos resampling.
    4. Returned as width × height × 3 raw RGB bytes (top-to-bottom).

    Parameters
    ----------
    path       : Filesystem path to the source image file.
    width      : Output width in pixels (default 240 — T2i native).
    height     : Output height in pixels (default 320 — T2i native).
    background : RGB tuple used when compositing transparent images.

    Returns
    -------
    bytes — width × height × 3 raw RGB bytes.

    Raises
    ------
    ImportError : if Pillow is not installed.
    FileNotFoundError : if the image file does not exist.
    """
    try:
        from PIL import Image
        import io as _io
    except ImportError:
        raise ImportError(
            'Pillow is required to load image files.\n'
            'Install with:  pip install Pillow'
        )

    img = Image.open(path)

    # Flatten any alpha / palette transparency onto a solid background.
    if img.mode in ('RGBA', 'LA', 'P'):
        bg = Image.new('RGB', img.size, background)
        if img.mode == 'P':
            img = img.convert('RGBA')
        if img.mode in ('RGBA', 'LA'):
            bg.paste(img, mask=img.split()[-1])   # use alpha channel as mask
        else:
            bg.paste(img)
        img = bg
    else:
        img = img.convert('RGB')

    # Resize if needed.
    if (img.width, img.height) != (width, height):
        img = img.resize((width, height), Image.LANCZOS)

    return img.tobytes()   # raw RGB, top-to-bottom, no padding


def load_image_rgb_from_bytes(
    data: bytes,
    width: int  = T2I_WIDTH,
    height: int = T2I_HEIGHT,
    background: tuple = (255, 255, 255),
) -> bytes:
    """
    Like :func:`load_image_rgb` but accepts raw image file bytes in memory
    instead of a filesystem path.  Useful when the image comes from another
    source (e.g. an OLE2 stream).
    """
    try:
        from PIL import Image
        import io
    except ImportError:
        raise ImportError(
            'Pillow is required to decode image data.\n'
            'Install with:  pip install Pillow'
        )

    img = Image.open(io.BytesIO(data))

    if img.mode in ('RGBA', 'LA', 'P'):
        bg = Image.new('RGB', img.size, background)
        if img.mode == 'P':
            img = img.convert('RGBA')
        if img.mode in ('RGBA', 'LA'):
            bg.paste(img, mask=img.split()[-1])
        else:
            bg.paste(img)
        img = bg
    else:
        img = img.convert('RGB')

    if (img.width, img.height) != (width, height):
        img = img.resize((width, height), Image.LANCZOS)

    return img.tobytes()
