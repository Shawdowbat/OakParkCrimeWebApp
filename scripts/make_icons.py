"""Draw the app icons (a white map pin on purple) as PNGs, with no image libraries.

Run from the project root:  python scripts/make_icons.py
"""

import math
import struct
import zlib
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "static" / "icons"
PURPLE = (126, 34, 206)
WHITE = (255, 255, 255)
SUPERSAMPLE = 4


def inside_pin(x, y):
    """Whether (x, y), in a 0..1 square, falls on the pin's white body."""
    cx, cy, r = 0.5, 0.42, 0.21
    tip_y = 0.80
    if math.hypot(x - cx, y - cy) <= r:
        return math.hypot(x - cx, y - cy) > r * 0.42  # hollow center
    # The tapering tail: between the circle's tangent lines and the tip.
    if cy <= y <= tip_y:
        half_width = r * (tip_y - y) / (tip_y - cy) * 0.92
        return abs(x - cx) <= half_width
    return False


def draw(size, padding=0.0, rounded=True):
    rows = []
    for py in range(size):
        row = bytearray([0])  # PNG filter: none
        for px in range(size):
            hits = 0
            for sy in range(SUPERSAMPLE):
                for sx in range(SUPERSAMPLE):
                    x = (px + (sx + 0.5) / SUPERSAMPLE) / size
                    y = (py + (sy + 0.5) / SUPERSAMPLE) / size
                    # Maskable icons keep artwork in the central safe zone.
                    ix = (x - padding) / (1 - 2 * padding)
                    iy = (y - padding) / (1 - 2 * padding)
                    hits += inside_pin(ix, iy)
            f = hits / SUPERSAMPLE ** 2
            color = [round(PURPLE[i] + (WHITE[i] - PURPLE[i]) * f) for i in range(3)]
            alpha = 255
            if rounded:
                corner = 0.18 * size
                dx = max(corner - px - 0.5, px + 0.5 - (size - corner), 0)
                dy = max(corner - py - 0.5, py + 0.5 - (size - corner), 0)
                alpha = round(255 * max(0.0, min(1.0, corner - math.hypot(dx, dy) + 0.5)))
            row += bytes(color + [alpha])
        rows.append(bytes(row))
    return png(size, size, b"".join(rows))


def png(width, height, raw):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "icon-192.png").write_bytes(draw(192))
    (OUT_DIR / "icon-512.png").write_bytes(draw(512))
    (OUT_DIR / "maskable-512.png").write_bytes(draw(512, padding=0.12, rounded=False))
    (OUT_DIR / "apple-touch-icon.png").write_bytes(draw(180, rounded=False))
    print(f"Icons written to {OUT_DIR}")


if __name__ == "__main__":
    main()
