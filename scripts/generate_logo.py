"""Generates the Podcast Clipper logo (SVG + PNG + ICO) from one shared geometry.

Run: poetry run python scripts/generate_logo.py
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SIZE = 512
RADIUS = 112
# Same hues as the UI: primary (magenta) -> purple-600 -> indigo-600.
STOPS = [(0.0, (225, 29, 116)), (0.55, (147, 51, 234)), (1.0, (79, 70, 229))]

# 9:16 crop frame (corner brackets) with a podcast waveform inside.
FRAME = (162, 92, 350, 420)
BRACKET = 58
STROKE = 18
BAR_WIDTH = 22
BAR_GAP = 18
BAR_HEIGHTS = [64, 132, 208, 132, 64]


def _bars() -> list[tuple[float, float, float, float]]:
    total = len(BAR_HEIGHTS) * BAR_WIDTH + (len(BAR_HEIGHTS) - 1) * BAR_GAP
    x = (SIZE - total) / 2
    bars = []

    for height in BAR_HEIGHTS:
        bars.append((x, (SIZE - height) / 2, BAR_WIDTH, height))
        x += BAR_WIDTH + BAR_GAP

    return bars


def _brackets() -> list[list[tuple[float, float]]]:
    left, top, right, bottom = FRAME
    b = BRACKET
    return [
        [(left, top + b), (left, top), (left + b, top)],
        [(right - b, top), (right, top), (right, top + b)],
        [(left, bottom - b), (left, bottom), (left + b, bottom)],
        [(right - b, bottom), (right, bottom), (right, bottom - b)],
    ]


def write_svg(path: Path) -> None:
    stops = "".join(
        f'<stop offset="{offset}" stop-color="#{r:02x}{g:02x}{b:02x}"/>' for offset, (r, g, b) in STOPS
    )
    bars = "".join(
        f'<rect x="{x:g}" y="{y:g}" width="{w}" height="{h}" rx="{w / 2:g}"/>' for x, y, w, h in _bars()
    )
    brackets = "".join(
        f'<polyline points="{" ".join(f"{x:g},{y:g}" for x, y in points)}"/>' for points in _brackets()
    )
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}" width="{SIZE}" height="{SIZE}">'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">{stops}</linearGradient></defs>'
        f'<rect width="{SIZE}" height="{SIZE}" rx="{RADIUS}" fill="url(#g)"/>'
        f'<g fill="none" stroke="#fff" stroke-width="{STROKE}" stroke-linecap="round" stroke-linejoin="round">{brackets}</g>'
        f'<g fill="#fff">{bars}</g></svg>\n',
        encoding="utf-8",
    )


def render_png(scale: int = 4) -> Image.Image:
    size = SIZE * scale
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float32)
    t = (xs + ys) / (2 * (size - 1))
    channels = []

    for index in range(3):
        offsets = [stop[0] for stop in STOPS]
        values = [stop[1][index] for stop in STOPS]
        channels.append(np.interp(t, offsets, values))

    gradient = Image.fromarray(np.stack(channels, axis=-1).astype(np.uint8), "RGB").convert("RGBA")

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), RADIUS * scale, fill=255)
    gradient.putalpha(mask)

    draw = ImageDraw.Draw(gradient)
    white = (255, 255, 255, 255)
    half = STROKE * scale / 2

    for points in _brackets():
        scaled = [(x * scale, y * scale) for x, y in points]
        draw.line(scaled, fill=white, width=STROKE * scale, joint="curve")

        for x, y in (scaled[0], scaled[-1]):
            draw.ellipse((x - half, y - half, x + half, y + half), fill=white)

    for x, y, w, h in _bars():
        draw.rounded_rectangle(
            (x * scale, y * scale, (x + w) * scale, (y + h) * scale), w * scale / 2, fill=white
        )

    return gradient.resize((SIZE, SIZE), Image.LANCZOS)


def main() -> None:
    svg_targets = [ROOT / "client" / "public" / "logo.svg", ROOT / "client" / "public" / "favicon.svg"]

    for target in svg_targets:
        write_svg(target)

    icons_dir = ROOT / "assets" / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    write_svg(icons_dir / "logo.svg")
    image = render_png()
    image.save(icons_dir / "icon.png")
    image.save(icons_dir / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    print("Logo gerada em", icons_dir)


if __name__ == "__main__":
    main()
