"""
rti_lib/tools/browse_template.py

CLI tool: browse and export images from any RTI icon-library .rtitemplate.

Usage
-----
    # List all image names
    python -m rti_lib.tools.browse_template list "Channel Icons - TV.rtitemplate"

    # Save a single image
    python -m rti_lib.tools.browse_template get "Channel Icons - TV.rtitemplate" "ABC" out.png

    # Export ALL images to a folder
    python -m rti_lib.tools.browse_template export "Channel Icons - TV.rtitemplate" ./icons/

    # Save a visual HTML contact sheet (grid of all thumbnails)
    python -m rti_lib.tools.browse_template sheet "Channel Icons - TV.rtitemplate" sheet.html

    # Save a PNG grid (easier to view in image viewer)
    python -m rti_lib.tools.browse_template grid "Channel Icons - TV.rtitemplate" grid.png

Can also be invoked as a function from code:
    from rti_lib.tools.browse_template import print_list, save_grid
"""

from __future__ import annotations
import os
import io
import sys
import math
import html
import textwrap
from PIL import Image

# Resolve the template directory automatically
_TEMPLATE_DIR = r'C:\Program Files (x86)\RTI\Integration Designer\Templates'


def _resolve(path: str) -> str:
    """If path has no directory separators, look in the RTI Templates folder."""
    if not os.path.dirname(path) and not os.path.exists(path):
        candidate = os.path.join(_TEMPLATE_DIR, path)
        if os.path.exists(candidate):
            return candidate
    return path


def _load(path: str):
    """Load an IconLibrary, resolving shortcuts to the Templates folder."""
    from rti_lib.assets.icon_library import IconLibrary
    return IconLibrary.load(_resolve(path))


# ---------------------------------------------------------------------------
# print_list
# ---------------------------------------------------------------------------

def print_list(template_path: str) -> None:
    """Print all image names in an icon-library template."""
    lib = _load(template_path)
    print(f'{lib.summary()}')
    print(f'{"#":>4}  {"Name":<50}  {"Size":>10}  Streams')
    print('-' * 85)
    for i, entry in enumerate(lib.entries):
        print(f'{i:>4}  {entry.name:<50}  '
              f'{entry.width}x{entry.height}  '
              f'{entry.up_stream} / {entry.down_stream}')


# ---------------------------------------------------------------------------
# save_image
# ---------------------------------------------------------------------------

def save_image(template_path: str, name: str, out_path: str,
               state: str = 'up') -> None:
    """Save a single named image from the template to *out_path*."""
    lib = _load(template_path)
    png = lib.get_png(name, state)
    with open(out_path, 'wb') as f:
        f.write(png)
    print(f'Saved: {out_path}')


# ---------------------------------------------------------------------------
# export_all
# ---------------------------------------------------------------------------

def export_all(template_path: str, out_dir: str,
               state: str = 'up') -> None:
    """Export all images to *out_dir* as individual PNG files."""
    lib = _load(template_path)
    os.makedirs(out_dir, exist_ok=True)
    for entry in lib.entries:
        png = lib.get_png(entry.name, state)
        safe = entry.name.replace('/', '-').replace('\\', '-').replace(':', '-')
        out_path = os.path.join(out_dir, f'{safe}.png')
        with open(out_path, 'wb') as f:
            f.write(png)
        print(f'  {entry.name} → {out_path}')
    print(f'Exported {len(lib.entries)} images to {out_dir}')


# ---------------------------------------------------------------------------
# save_grid
# ---------------------------------------------------------------------------

def save_grid(template_path: str, out_path: str,
              cols: int = 10,
              thumb_w: int = 80,
              thumb_h: int = 60,
              state: str = 'up') -> None:
    """
    Save a PNG contact-sheet grid of all images in the template.

    Parameters
    ----------
    cols    : Number of columns in the grid.
    thumb_w, thumb_h : Thumbnail size for each image.
    state   : 'up' or 'down'.
    """
    lib = _load(template_path)
    n = len(lib.entries)
    rows = math.ceil(n / cols)

    label_h = 14
    cell_w = thumb_w + 4
    cell_h = thumb_h + label_h + 6

    grid_w = cell_w * cols
    grid_h = cell_h * rows

    grid = Image.new('RGB', (grid_w, grid_h), (30, 30, 30))

    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(grid)
    try:
        font = ImageFont.truetype(r'C:\Windows\Fonts\arial.ttf', 9)
    except OSError:
        font = ImageFont.load_default()

    for i, entry in enumerate(lib.entries):
        col = i % cols
        row = i // cols
        cx = col * cell_w + 2
        cy = row * cell_h + 2

        try:
            png = lib.get_png(entry.name, state)
            thumb = Image.open(io.BytesIO(png)).convert('RGB')
            thumb = thumb.resize((thumb_w, thumb_h), Image.LANCZOS)
            grid.paste(thumb, (cx, cy))
        except Exception:
            draw.rectangle([cx, cy, cx + thumb_w, cy + thumb_h], fill=(60, 0, 0))

        # Label: truncate to fit
        label = entry.name
        if len(label) > 14:
            label = label[:13] + '…'
        draw.text((cx, cy + thumb_h + 2), label, font=font, fill=(200, 200, 200))
        # Index
        draw.text((cx, cy + 1), str(i), font=font, fill=(255, 200, 80))

    grid.save(out_path)
    print(f'Grid saved: {out_path}  ({grid_w}×{grid_h}px, {n} images)')


# ---------------------------------------------------------------------------
# save_sheet (HTML contact sheet)
# ---------------------------------------------------------------------------

def save_sheet(template_path: str, out_path: str) -> None:
    """
    Save an HTML contact sheet with all images inline as base64 PNGs.
    Open in any browser to browse and identify images by name.
    """
    import base64
    lib = _load(template_path)

    cards = []
    for i, entry in enumerate(lib.entries):
        try:
            up_png  = lib.get_png(entry.name, 'up')
            dn_png  = lib.get_png(entry.name, 'down')
            up_b64  = base64.b64encode(up_png).decode()
            dn_b64  = base64.b64encode(dn_png).decode()
            esc = html.escape(entry.name)
            cards.append(
                f'<div class="card" title="{esc}">'
                f'  <img class="up"   src="data:image/png;base64,{up_b64}">'
                f'  <img class="down" src="data:image/png;base64,{dn_b64}">'
                f'  <div class="idx">#{i}</div>'
                f'  <div class="lbl">{esc}</div>'
                f'</div>'
            )
        except Exception as e:
            cards.append(f'<div class="card err">{i}: {html.escape(str(e))}</div>')

    page = textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8">
        <title>{html.escape(lib.name)}</title>
        <style>
          body {{ background:#1a1a1a; color:#ddd; font-family:sans-serif; margin:8px; }}
          h1 {{ font-size:16px; color:#aef; }}
          .grid {{ display:flex; flex-wrap:wrap; gap:8px; }}
          .card {{ background:#2a2a2a; border:1px solid #444; border-radius:6px;
                   padding:6px; width:100px; text-align:center; cursor:pointer;
                   transition:border-color .15s; }}
          .card:hover {{ border-color:#8cf; }}
          .card img {{ display:block; margin:0 auto 2px; max-width:90px; }}
          .card .down {{ display:none; }}
          .card:hover .up {{ display:none; }}
          .card:hover .down {{ display:block; }}
          .idx {{ font-size:9px; color:#888; }}
          .lbl {{ font-size:10px; color:#cdf; word-break:break-word; }}
          .err {{ color:#f88; }}
          input#search {{ width:280px; padding:4px 8px; margin-bottom:10px;
                          background:#333; border:1px solid #666; color:#eee;
                          border-radius:4px; font-size:13px; }}
        </style>
        </head>
        <body>
        <h1>{html.escape(lib.name)} — {len(lib.entries)} images
            (hover card to preview pressed state)</h1>
        <input id="search" placeholder="Filter by name…"
               oninput="filter(this.value)">
        <div class="grid" id="grid">
        {''.join(cards)}
        </div>
        <script>
        function filter(q) {{
          q = q.toLowerCase();
          document.querySelectorAll('.card').forEach(c => {{
            const lbl = c.querySelector('.lbl');
            c.style.display = (!q || (lbl && lbl.textContent.toLowerCase().includes(q)))
                              ? '' : 'none';
          }});
        }}
        </script>
        </body></html>
    """)

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(page)
    print(f'Sheet saved: {out_path}  ({len(lib.entries)} images)')


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv=None):
    args = (argv or sys.argv)[1:]
    if not args:
        print(__doc__)
        return

    cmd = args[0].lower()

    if cmd == 'list':
        print_list(args[1])

    elif cmd == 'get':
        state = args[3] if len(args) > 3 else 'up'
        save_image(args[1], args[2], args[3] if len(args) > 3 else args[2] + '.png',
                   state='up')

    elif cmd == 'export':
        state = args[3] if len(args) > 3 else 'up'
        export_all(args[1], args[2], state=state)

    elif cmd == 'grid':
        save_grid(args[1], args[2] if len(args) > 2 else 'grid.png')

    elif cmd == 'sheet':
        save_sheet(args[1], args[2] if len(args) > 2 else 'sheet.html')

    else:
        print(f'Unknown command: {cmd!r}')
        print('Commands: list, get, export, grid, sheet')


if __name__ == '__main__':
    main()
