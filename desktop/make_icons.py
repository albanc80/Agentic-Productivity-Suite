#!/usr/bin/env python3
"""Render the app icon (same design as frontend/public/icon.svg) to PNG and ICO.

    uv run --group desktop python desktop/make_icons.py

Writes desktop/assets/icon.png (512 px) and desktop/assets/icon.ico (16-256 px).
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent / "assets"
NAVY_TOP, NAVY_BOTTOM = (10, 18, 38), (20, 37, 74)
CYAN, VIOLET = (70, 217, 237), (170, 138, 255)


def render(size: int = 1024) -> Image.Image:
    s = size / 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    # Diagonal navy gradient, clipped to a rounded square.
    grad = Image.new("RGBA", (size, size))
    gp = grad.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size)
            gp[x, y] = tuple(int(a + (b - a) * t) for a, b in zip(NAVY_TOP, NAVY_BOTTOM, strict=True)) + (255,)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=int(112 * s), fill=255)
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    cx = cy = 256 * s
    nodes = [(256, 120), (374, 188), (374, 324), (256, 392), (138, 324), (138, 188)]
    for nx, ny in nodes:  # spokes
        d.line([(cx, cy), (nx * s, ny * s)], fill=CYAN + (140,), width=int(22 * s))
    for nx, ny in nodes:  # desks
        r = 26 * s
        d.ellipse([nx * s - r, ny * s - r, nx * s + r, ny * s + r], fill=CYAN)
    hexagon = [(cx + 64 * s * math.cos(math.pi / 6 + i * math.pi / 3), cy + 64 * s * math.sin(math.pi / 6 + i * math.pi / 3))
               for i in range(6)]
    d.polygon(hexagon, fill=NAVY_TOP, outline=VIOLET, width=int(20 * s))  # router
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    big = render(1024)
    big.resize((512, 512), Image.LANCZOS).save(OUT / "icon.png")
    big.resize((256, 256), Image.LANCZOS).save(OUT / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"Wrote {OUT / 'icon.png'} and {OUT / 'icon.ico'}")


if __name__ == "__main__":
    main()
