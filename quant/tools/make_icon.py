"""Generate the quantos app icon with the standard library only (no Pillow).

Draws a 256x256 mark — a rounded teal tile with a white upward chart line and
an end dot — and writes it as PNG, ICO (PNG-compressed, Vista+) and a
hand-clean SVG into ``quantos/dashboard/assets/``. Deterministic (I8): run it
again and the bytes are identical.

    python tools/make_icon.py
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

SIZE = 256
ASSETS = Path(__file__).resolve().parents[1] / "quantos" / "dashboard" / "assets"

# Brand palette (the dashboard's teal on a deep ink tile).
TILE_TOP = (0x1B, 0xC7, 0xB4)
TILE_BOT = (0x0E, 0x9C, 0x8C)
INK = (0x0B, 0x10, 0x17)
WHITE = (0xF4, 0xFB, 0xFF)

# The chart polyline, in 0..1 tile coordinates (y down); it climbs to the right.
LINE = [(0.16, 0.70), (0.34, 0.55), (0.48, 0.62), (0.66, 0.38), (0.84, 0.25)]


def _rounded(x: float, y: float, margin: float, radius: float) -> bool:
    lo, hi = margin, SIZE - margin
    if not (lo <= x <= hi and lo <= y <= hi):
        return False
    cx = min(max(x, lo + radius), hi - radius)
    cy = min(max(y, lo + radius), hi - radius)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius**2


def _dist_to_polyline(px: float, py: float, pts: list[tuple[float, float]]) -> float:
    best = 1e9
    for (x0, y0), (x1, y1) in zip(pts, pts[1:], strict=False):
        dx, dy = x1 - x0, y1 - y0
        length2 = dx * dx + dy * dy or 1.0
        t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / length2))
        qx, qy = x0 + t * dx, y0 + t * dy
        best = min(best, ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5)
    return best


def _blend(bg: tuple[int, int, int], fg: tuple[int, int, int], a: float) -> tuple[int, int, int]:
    return tuple(round(bg[i] * (1 - a) + fg[i] * a) for i in range(3))  # type: ignore[return-value]


def _pixels() -> bytearray:
    pts = [(x * SIZE, y * SIZE) for x, y in LINE]
    end = pts[-1]
    buf = bytearray(SIZE * SIZE * 4)
    for j in range(SIZE):
        for i in range(SIZE):
            o = (j * SIZE + i) * 4
            inside = _rounded(i + 0.5, j + 0.5, margin=14, radius=52)
            if not inside:
                continue  # transparent outside the tile
            grad = j / SIZE
            color = _blend(TILE_TOP, TILE_BOT, grad)
            # white chart line (anti-aliased by the distance falloff)
            d = _dist_to_polyline(i + 0.5, j + 0.5, pts)
            line_a = max(0.0, min(1.0, (7.0 - d) / 2.0))
            # end dot
            dot = ((i + 0.5 - end[0]) ** 2 + (j + 0.5 - end[1]) ** 2) ** 0.5
            dot_a = max(0.0, min(1.0, (11.0 - dot) / 2.0))
            a = max(line_a, dot_a)
            if a > 0:
                color = _blend(color, WHITE, a)
            buf[o : o + 4] = bytes((*color, 255))
    return buf


def _png(pixels: bytearray) -> bytes:
    raw = bytearray()
    for j in range(SIZE):
        raw.append(0)  # filter type 0 for the scanline
        raw.extend(pixels[j * SIZE * 4 : (j + 1) * SIZE * 4])

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    ihdr = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def _ico(png: bytes) -> bytes:
    # ICONDIR + one ICONDIRENTRY pointing at a PNG-compressed 256x256 image.
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 6 + 16)
    return header + entry + png


SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" role="img" aria-label="quantos">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#1BC7B4"/>
      <stop offset="1" stop-color="#0E9C8C"/>
    </linearGradient>
  </defs>
  <rect x="14" y="14" width="228" height="228" rx="52" fill="url(#g)"/>
  <polyline points="41,179 87,141 123,159 169,97 215,64" fill="none"
    stroke="#F4FBFF" stroke-width="13" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="215" cy="64" r="12" fill="#F4FBFF"/>
</svg>
"""


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    pixels = _pixels()
    png = _png(pixels)
    (ASSETS / "quantos.png").write_bytes(png)
    (ASSETS / "quantos.ico").write_bytes(_ico(png))
    (ASSETS / "quantos.svg").write_text(SVG, encoding="utf-8")
    print(f"wrote quantos.png ({len(png)} B), quantos.ico, quantos.svg to {ASSETS}")


if __name__ == "__main__":
    main()
