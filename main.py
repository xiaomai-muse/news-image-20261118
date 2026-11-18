#!/usr/bin/env python3
"""Generate the 1024x1024 front-page news poster for Wednesday 18 November 2026."""

import math
import os
import struct
import zlib

WIDTH = 1024
HEIGHT = 1024

# ---------------------------------------------------------------------------
# 1. PALETTE
# ---------------------------------------------------------------------------
PAPER_BG = (244, 238, 224)
PAPER_ALT = (237, 229, 212)
ICON_BG = (250, 246, 236)
INK_BLACK = (22, 22, 26)
INK_MUTED = (72, 68, 62)
INK_LIGHT = (244, 238, 224)
ACCENT_RED = (186, 36, 36)
ACCENT_BLUE = (26, 58, 108)
ACCENT_BLUE_LIGHT = (76, 114, 168)
ACCENT_GOLD = (202, 152, 42)
RULE_DARK = (40, 38, 36)
RULE_LIGHT = (188, 178, 158)
FOOTER_BG = (24, 26, 32)
WHITE = (255, 255, 255)


# ---------------------------------------------------------------------------
# 2. CANVAS PRIMITIVES
# ---------------------------------------------------------------------------
class Canvas:
    """1024x1024 RGB framebuffer backed by a bytearray."""

    def __init__(self, width: int, height: int, bg: tuple[int, int, int]) -> None:
        self.width = width
        self.height = height
        r, g, b = bg
        self.buf = bytearray([r, g, b]) * (width * height)

    def set_pixel(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            idx = (y * self.width + x) * 3
            self.buf[idx] = color[0]
            self.buf[idx + 1] = color[1]
            self.buf[idx + 2] = color[2]

    def fill_rect(
        self, x: int, y: int, w: int, h: int, color: tuple[int, int, int]
    ) -> None:
        if w <= 0 or h <= 0:
            return
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.width, x + w)
        y1 = min(self.height, y + h)
        if x0 >= x1 or y0 >= y1:
            return
        row_bytes = bytes(color) * (x1 - x0)
        stride = self.width * 3
        start_x = x0 * 3
        end_x = x1 * 3
        for py in range(y0, y1):
            base = py * stride
            self.buf[base + start_x : base + end_x] = row_bytes

    def stroke_rect(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        color: tuple[int, int, int],
        thickness: int = 1,
    ) -> None:
        if w <= 0 or h <= 0 or thickness <= 0:
            return
        t = min(thickness, w // 2 + 1, h // 2 + 1)
        self.fill_rect(x, y, w, t, color)
        self.fill_rect(x, y + h - t, w, t, color)
        self.fill_rect(x, y, t, h, color)
        self.fill_rect(x + w - t, y, t, h, color)

    def fill_circle(
        self, cx: int, cy: int, radius: int, color: tuple[int, int, int]
    ) -> None:
        if radius < 0:
            return
        if radius == 0:
            self.set_pixel(cx, cy, color)
            return
        r2 = radius * radius
        for dy in range(-radius, radius + 1):
            py = cy + dy
            if py < 0 or py >= self.height:
                continue
            dx_max = int((r2 - dy * dy) ** 0.5)
            x0 = max(0, cx - dx_max)
            x1 = min(self.width, cx + dx_max + 1)
            if x0 < x1:
                row_bytes = bytes(color) * (x1 - x0)
                base = py * self.width * 3
                self.buf[base + x0 * 3 : base + x1 * 3] = row_bytes

    def draw_line(
        self,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        color: tuple[int, int, int],
        thickness: int = 1,
    ) -> None:
        """Draw a thick line using Bresenham's algorithm."""
        x0 = int(round(x0))
        y0 = int(round(y0))
        x1 = int(round(x1))
        y1 = int(round(y1))
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy

        rad = max(0, (thickness - 1) // 2)
        even_extra = 1 if (thickness > 1 and thickness % 2 == 0) else 0

        while True:
            if thickness <= 1:
                self.set_pixel(x0, y0, color)
            elif thickness == 2:
                self.fill_rect(x0, y0, 2, 2, color)
            else:
                self.fill_circle(x0, y0, rad + even_extra // 2, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def fill_polygon(
        self, points: list[tuple[int, int]], color: tuple[int, int, int]
    ) -> None:
        """Scanline-fill a simple polygon."""
        if len(points) < 3:
            return
        ys = [p[1] for p in points]
        min_y = max(0, min(ys))
        max_y = min(self.height - 1, max(ys))
        n = len(points)
        for py in range(min_y, max_y + 1):
            intersections: list[float] = []
            for i in range(n):
                x1, y1 = points[i]
                x2, y2 = points[(i + 1) % n]
                if y1 == y2:
                    continue
                if (y1 <= py < y2) or (y2 <= py < y1):
                    ix = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
                    intersections.append(ix)
            intersections.sort()
            for i in range(0, len(intersections) - 1, 2):
                xa = max(0, int(round(intersections[i])))
                xb = min(self.width - 1, int(round(intersections[i + 1])))
                if xb >= xa:
                    row_bytes = bytes(color) * (xb - xa + 1)
                    base = py * self.width * 3
                    self.buf[base + xa * 3 : base + (xb + 1) * 3] = row_bytes


# ---------------------------------------------------------------------------
# 3. PNG ENCODER
# ---------------------------------------------------------------------------
def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def encode_png(canvas: Canvas) -> bytes:
    """Encode an RGB Canvas into a deterministic PNG byte stream."""
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(
        ">IIBBBBB",
        canvas.width,
        canvas.height,
        8,  # bit depth
        2,  # color type: RGB
        0,  # compression method
        0,  # filter method
        0,  # interlace method
    )
    stride = canvas.width * 3
    raw = bytearray((stride + 1) * canvas.height)
    for y in range(canvas.height):
        dst = y * (stride + 1)
        src = y * stride
        raw[dst] = 0  # filter type 0 (None)
        raw[dst + 1 : dst + 1 + stride] = canvas.buf[src : src + stride]

    compressed = zlib.compress(bytes(raw), level=6)
    return (
        signature
        + _png_chunk(b"IHDR", ihdr_data)
        + _png_chunk(b"IDAT", compressed)
        + _png_chunk(b"IEND", b"")
    )


# ---------------------------------------------------------------------------
# 4. FONT (Stroke-vector font on a 6x10 grid: x in 0..6, y in 0..10)
# ---------------------------------------------------------------------------
GLYPH_W = 6
GLYPH_H = 10
CHAR_ADVANCE = 8  # 6-unit glyph + 2-unit inter-character gap

FONT: dict[str, tuple[tuple[tuple[int, int], ...], ...]] = {
    " ": (),
    "A": (((0, 10), (3, 0), (6, 10)), ((1, 7), (5, 7))),
    "B": (
        ((0, 10), (0, 0), (4, 0), (5, 1), (5, 4), (4, 5), (0, 5)),
        ((4, 5), (6, 6), (6, 9), (4, 10), (0, 10)),
    ),
    "C": (((6, 2), (4, 0), (2, 0), (0, 2), (0, 8), (2, 10), (4, 10), (6, 8)),),
    "D": (((0, 0), (0, 10), (4, 10), (6, 8), (6, 2), (4, 0), (0, 0)),),
    "E": (((6, 0), (0, 0), (0, 10), (6, 10)), ((0, 5), (4, 5))),
    "F": (((6, 0), (0, 0), (0, 10)), ((0, 5), (4, 5))),
    "G": (
        ((6, 2), (4, 0), (2, 0), (0, 2), (0, 8), (2, 10), (5, 10), (6, 8), (6, 5), (3, 5)),
    ),
    "H": (((0, 0), (0, 10)), ((6, 0), (6, 10)), ((0, 5), (6, 5))),
    "I": (((1, 0), (5, 0)), ((3, 0), (3, 10)), ((1, 10), (5, 10))),
    "J": (((2, 0), (6, 0)), ((5, 0), (5, 8), (3, 10), (1, 10), (0, 8))),
    "K": (((0, 0), (0, 10)), ((6, 0), (0, 6)), ((2, 4), (6, 10))),
    "L": (((0, 0), (0, 10), (6, 10)),),
    "M": (((0, 10), (0, 0), (3, 5), (6, 0), (6, 10)),),
    "N": (((0, 10), (0, 0), (6, 10), (6, 0)),),
    "O": (((2, 0), (4, 0), (6, 2), (6, 8), (4, 10), (2, 10), (0, 8), (0, 2), (2, 0)),),
    "P": (((0, 10), (0, 0), (4, 0), (6, 2), (6, 4), (4, 5), (0, 5)),),
    "Q": (
        ((2, 0), (4, 0), (6, 2), (6, 8), (4, 10), (2, 10), (0, 8), (0, 2), (2, 0)),
        ((4, 7), (6, 10)),
    ),
    "R": (
        ((0, 10), (0, 0), (4, 0), (6, 2), (6, 4), (4, 5), (0, 5)),
        ((3, 5), (6, 10)),
    ),
    "S": (
        ((6, 2), (4, 0), (2, 0), (0, 2), (0, 4), (6, 6), (6, 8), (4, 10), (2, 10), (0, 8)),
    ),
    "T": (((0, 0), (6, 0)), ((3, 0), (3, 10))),
    "U": (((0, 0), (0, 8), (2, 10), (4, 10), (6, 8), (6, 0)),),
    "V": (((0, 0), (3, 10), (6, 0)),),
    "W": (((0, 0), (1, 10), (3, 5), (5, 10), (6, 0)),),
    "X": (((0, 0), (6, 10)), ((6, 0), (0, 10))),
    "Y": (((0, 0), (3, 5), (6, 0)), ((3, 5), (3, 10))),
    "Z": (((0, 0), (6, 0), (0, 10), (6, 10)),),
    "0": (
        ((2, 0), (4, 0), (6, 2), (6, 8), (4, 10), (2, 10), (0, 8), (0, 2), (2, 0)),
        ((1, 8), (5, 2)),
    ),
    "1": (((1, 2), (3, 0), (3, 10)), ((1, 10), (5, 10))),
    "2": (((0, 2), (2, 0), (4, 0), (6, 2), (6, 4), (0, 10), (6, 10)),),
    "3": (
        ((0, 2), (2, 0), (4, 0), (6, 2), (6, 4), (4, 5), (2, 5)),
        ((4, 5), (6, 6), (6, 8), (4, 10), (2, 10), (0, 8)),
    ),
    "4": (((5, 10), (5, 0), (0, 6), (6, 6)),),
    "5": (((6, 0), (0, 0), (0, 4), (4, 4), (6, 6), (6, 8), (4, 10), (2, 10), (0, 8)),),
    "6": (
        ((5, 0), (2, 0), (0, 2), (0, 8), (2, 10), (4, 10), (6, 8), (6, 6), (4, 4), (0, 4)),
    ),
    "7": (((0, 0), (6, 0), (2, 10)),),
    "8": (
        ((2, 5), (0, 4), (0, 2), (2, 0), (4, 0), (6, 2), (6, 4), (4, 5), (2, 5)),
        ((2, 5), (0, 6), (0, 8), (2, 10), (4, 10), (6, 8), (6, 6), (4, 5)),
    ),
    "9": (
        ((6, 6), (2, 6), (0, 4), (0, 2), (2, 0), (4, 0), (6, 2), (6, 8), (4, 10), (1, 10)),
    ),
    ".": (((2, 9), (3, 9), (3, 10), (2, 10), (2, 9)),),
    ",": (((3, 8), (3, 9), (2, 11)),),
    ":": (
        ((2, 3), (3, 3), (3, 4), (2, 4), (2, 3)),
        ((2, 8), (3, 8), (3, 9), (2, 9), (2, 8)),
    ),
    ";": (
        ((2, 3), (3, 3), (3, 4), (2, 4), (2, 3)),
        ((3, 8), (3, 9), (2, 11)),
    ),
    "'": (((3, 0), (3, 2), (2, 3)),),
    '"': (((2, 0), (2, 3)), ((4, 0), (4, 3))),
    "-": (((1, 5), (5, 5)),),
    "/": (((0, 10), (6, 0)),),
    "(": (((4, 0), (2, 2), (2, 8), (4, 10)),),
    ")": (((2, 0), (4, 2), (4, 8), (2, 10)),),
    "%": (
        ((0, 9), (6, 1)),
        ((0, 1), (2, 1), (2, 3), (0, 3), (0, 1)),
        ((4, 7), (6, 7), (6, 9), (4, 9), (4, 7)),
    ),
    "$": (
        ((5, 2), (4, 1), (2, 1), (1, 2), (1, 4), (5, 6), (5, 8), (4, 9), (2, 9), (1, 8)),
        ((3, 0), (3, 10)),
    ),
    "&": (
        ((6, 10), (1, 4), (1, 2), (2, 0), (4, 0), (5, 2), (5, 3), (0, 7), (0, 9), (2, 10), (4, 10), (6, 7)),
    ),
    "+": (((1, 5), (5, 5)), ((3, 3), (3, 7))),
    "!": (((3, 0), (3, 6)), ((2, 9), (3, 9), (3, 10), (2, 10), (2, 9))),
    "?": (
        ((1, 2), (2, 0), (4, 0), (5, 2), (5, 4), (3, 5), (3, 7)),
        ((2, 9), (3, 9), (3, 10), (2, 10), (2, 9)),
    ),
    "•": (((2, 4), (4, 4), (4, 6), (2, 6), (2, 4)), ((3, 3), (3, 7))),
}


# ---------------------------------------------------------------------------
# 5. TEXT HELPERS
# ---------------------------------------------------------------------------
def measure_text(text: str, scale: int) -> int:
    """Return pixel width of single-line text at integer scale."""
    if not text:
        return 0
    return (len(text) - 1) * CHAR_ADVANCE * scale + GLYPH_W * scale


def draw_text(
    canvas: Canvas,
    text: str,
    x: int,
    y: int,
    scale: int,
    color: tuple[int, int, int],
    thickness: int | None = None,
) -> None:
    """Render text using the stroke-vector font."""
    if thickness is None:
        thickness = max(1, scale + (1 if scale >= 2 else 0))
    cx = x
    for ch in text.upper():
        glyph = FONT.get(ch, FONT[" "])
        for poly in glyph:
            for i in range(len(poly) - 1):
                x0, y0 = poly[i]
                x1, y1 = poly[i + 1]
                canvas.draw_line(
                    cx + x0 * scale,
                    y + y0 * scale,
                    cx + x1 * scale,
                    y + y1 * scale,
                    color,
                    thickness=thickness,
                )
        cx += CHAR_ADVANCE * scale


def draw_text_centered(
    canvas: Canvas,
    text: str,
    center_x: int,
    y: int,
    scale: int,
    color: tuple[int, int, int],
    thickness: int | None = None,
) -> None:
    w = measure_text(text, scale)
    draw_text(canvas, text, center_x - w // 2, y, scale, color, thickness=thickness)


def wrap_text(text: str, max_width: int, scale: int) -> list[str]:
    """Greedy word-wrap so each line fits within max_width."""
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if measure_text(candidate, scale) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


# ---------------------------------------------------------------------------
# 6. MASTHEAD
# ---------------------------------------------------------------------------
def draw_masthead(canvas: Canvas) -> int:
    """Draw the newspaper masthead and return the y-coordinate below it."""
    # Top accent stripes
    canvas.fill_rect(24, 14, WIDTH - 48, 5, INK_BLACK)
    canvas.fill_rect(24, 21, WIDTH - 48, 2, ACCENT_RED)

    # Overline
    draw_text_centered(
        canvas, "THE WORLD IN ONE IMAGE", WIDTH // 2, 31, scale=2, color=ACCENT_RED, thickness=2
    )

    # Big title
    draw_text_centered(
        canvas,
        "WEDNESDAY 18 NOVEMBER 2026",
        WIDTH // 2,
        61,
        scale=4,
        color=INK_BLACK,
        thickness=5,
    )

    # Subline with flanking gold rules
    sub = "SIX STORIES THAT DEFINED THE DAY"
    sub_w = measure_text(sub, scale=2)
    draw_text_centered(canvas, sub, WIDTH // 2, 111, scale=2, color=ACCENT_BLUE, thickness=2)
    left_end = WIDTH // 2 - sub_w // 2 - 16
    right_start = WIDTH // 2 + sub_w // 2 + 16
    if left_end > 32:
        canvas.fill_rect(24, 120, left_end - 24, 2, ACCENT_GOLD)
        canvas.fill_rect(right_start, 120, WIDTH - 24 - right_start, 2, ACCENT_GOLD)

    # Bottom masthead double rule
    canvas.fill_rect(24, 139, WIDTH - 48, 3, INK_BLACK)
    canvas.fill_rect(24, 144, WIDTH - 48, 1, RULE_DARK)
    return 154


# ---------------------------------------------------------------------------
# 7. FOOTER
# ---------------------------------------------------------------------------
FOOTER_LINE_1 = (
    "US LOSES MEASLES-FREE STATUS AFTER 5,400 CASES"
    " • "
    "MODI RETURNS TO DELHI AFTER ASEAN SUMMIT IN MANILA"
)
FOOTER_LINE_2 = (
    "INDIA AND JAPAN HOLD 2+2 TALKS IN TOKYO"
    " • "
    "GOLD SLIDES TO ONE-YEAR LOW"
)


def draw_footer(canvas: Canvas) -> None:
    """Draw the dark footer strip with the two-line news ticker."""
    fy = 954
    fh = HEIGHT - fy
    canvas.fill_rect(0, fy, WIDTH, fh, FOOTER_BG)
    canvas.fill_rect(0, fy, WIDTH, 4, ACCENT_GOLD)
    canvas.fill_rect(0, fy + 4, WIDTH, 2, ACCENT_RED)

    draw_text_centered(
        canvas, FOOTER_LINE_1, WIDTH // 2, fy + 20, scale=1, color=INK_LIGHT, thickness=1
    )
    draw_text_centered(
        canvas, FOOTER_LINE_2, WIDTH // 2, fy + 40, scale=1, color=ACCENT_GOLD, thickness=1
    )


# ---------------------------------------------------------------------------
# 8. ICONS (Flat vector-style scenes inside each panel's light icon box)
# ---------------------------------------------------------------------------
def _draw_waves(
    canvas: Canvas, x: int, y: int, w: int, sea_h: int, sea_top: int
) -> None:
    """Helper to draw a gulf/bay sea band with simple triangular wave crests."""
    canvas.fill_rect(x, sea_top, w, sea_h, ACCENT_BLUE)
    crest_w = 28
    cx = x
    while cx < x + w:
        nx = min(x + w, cx + crest_w)
        mid = (cx + nx) // 2
        canvas.fill_polygon(
            [(cx, sea_top), (mid, sea_top - 6), (nx, sea_top)], ACCENT_BLUE_LIGHT
        )
        cx += crest_w


def draw_icon_gulf(canvas: Canvas, x: int, y: int, w: int, h: int) -> None:
    """Ship on waves with a flame and incoming missile streaks."""
    sea_h = 30
    sea_top = y + h - sea_h
    _draw_waves(canvas, x, y, w, sea_h, sea_top)

    # Tanker ship hull & superstructure
    sx = x + w // 2 - 40
    sy = sea_top - 16
    canvas.fill_polygon(
        [(sx, sy), (sx + 150, sy), (sx + 136, sy + 20), (sx + 14, sy + 20)],
        INK_BLACK,
    )
    canvas.fill_rect(sx + 12, sy + 12, 124, 4, ACCENT_RED)
    # Bridge
    canvas.fill_rect(sx + 106, sy - 18, 28, 18, INK_BLACK)
    canvas.fill_rect(sx + 112, sy - 14, 16, 6, PAPER_BG)

    # Flame rising from mid-deck
    fx = sx + 56
    fy = sy
    canvas.fill_polygon(
        [
            (fx - 18, fy),
            (fx - 14, fy - 24),
            (fx - 4, fy - 14),
            (fx + 4, fy - 38),
            (fx + 14, fy - 16),
            (fx + 22, fy - 26),
            (fx + 24, fy),
        ],
        ACCENT_RED,
    )
    canvas.fill_polygon(
        [(fx - 8, fy), (fx + 2, fy - 22), (fx + 12, fy)],
        ACCENT_GOLD,
    )

    # Incoming missile/drone streaks from top-left
    for idx, (mx0, my0, mx1, my1) in enumerate(
        [(x + 28, y + 16, sx + 14, sy - 20), (x + 74, y + 12, sx + 48, sy - 28)]
    ):
        canvas.draw_line(mx0, my0, mx1, my1, ACCENT_RED if idx == 0 else INK_BLACK, thickness=3)
        canvas.draw_line(mx0 - 12, my0 - 4, mx0 - 2, my0 - 1, ACCENT_GOLD, thickness=2)
        dx, dy = mx1 - mx0, my1 - my0
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length
        px, py = -uy, ux
        canvas.fill_polygon(
            [
                (int(round(mx1 + ux * 6)), int(round(my1 + uy * 6))),
                (int(round(mx1 - ux * 6 + px * 5)), int(round(my1 - uy * 6 + py * 5))),
                (int(round(mx1 - ux * 6 - px * 5)), int(round(my1 - uy * 6 - py * 5))),
            ],
            ACCENT_RED,
        )


def draw_icon_summit(canvas: Canvas, x: int, y: int, w: int, h: int) -> None:
    """Three small flags side by side: China, USA, Russia."""
    base_y = y + h - 14
    canvas.fill_rect(x + 36, base_y, w - 72, 4, RULE_DARK)

    flag_w = 88
    flag_h = 54
    gap = 34
    total_w = 3 * flag_w + 2 * gap
    start_x = x + (w - total_w) // 2
    top_y = y + 18

    for idx in range(3):
        fx = start_x + idx * (flag_w + gap)
        # Flagpole + gold finial
        canvas.fill_rect(fx - 5, top_y - 4, 4, base_y - top_y + 4, INK_BLACK)
        canvas.fill_circle(fx - 3, top_y - 6, 4, ACCENT_GOLD)

        if idx == 0:
            # China
            canvas.fill_rect(fx, top_y, flag_w, flag_h, ACCENT_RED)
            canvas.fill_polygon(
                [
                    (fx + 18, top_y + 8),
                    (fx + 21, top_y + 16),
                    (fx + 29, top_y + 16),
                    (fx + 23, top_y + 21),
                    (fx + 25, top_y + 29),
                    (fx + 18, top_y + 24),
                    (fx + 11, top_y + 29),
                    (fx + 13, top_y + 21),
                    (fx + 7, top_y + 16),
                    (fx + 15, top_y + 16),
                ],
                ACCENT_GOLD,
            )
        elif idx == 1:
            # USA
            stripe_h = flag_h // 7
            for s in range(7):
                col = ACCENT_RED if s % 2 == 0 else WHITE
                canvas.fill_rect(fx, top_y + s * stripe_h, flag_w, stripe_h, col)
            canvas.fill_rect(fx, top_y + 7 * stripe_h, flag_w, flag_h - 7 * stripe_h, ACCENT_RED)
            canton_w = 38
            canton_h = stripe_h * 4
            canvas.fill_rect(fx, top_y, canton_w, canton_h, ACCENT_BLUE)
            for ry in (7, 15, 23):
                for rx in (8, 18, 28):
                    canvas.fill_circle(fx + rx, top_y + ry, 2, WHITE)
        else:
            # Russia
            band_h = flag_h // 3
            canvas.fill_rect(fx, top_y, flag_w, band_h, WHITE)
            canvas.fill_rect(fx, top_y + band_h, flag_w, band_h, ACCENT_BLUE)
            canvas.fill_rect(fx, top_y + 2 * band_h, flag_w, flag_h - 2 * band_h, ACCENT_RED)

        canvas.stroke_rect(fx, top_y, flag_w, flag_h, INK_BLACK, thickness=1)


def draw_icon_markets(canvas: Canvas, x: int, y: int, w: int, h: int) -> None:
    """Steep rising revenue chart with an upward arrow."""
    gx = x + 48
    gy = y + 14
    gw = w - 96
    gh = h - 28

    # Subtle grid
    for i in range(1, 4):
        ly = gy + (gh * i) // 4
        canvas.draw_line(gx, ly, gx + gw, ly, RULE_LIGHT, thickness=1)
    for i in range(1, 6):
        lx = gx + (gw * i) // 6
        canvas.draw_line(lx, gy, lx, gy + gh, RULE_LIGHT, thickness=1)

    # Axes
    canvas.draw_line(gx, gy, gx, gy + gh, INK_BLACK, thickness=2)
    canvas.draw_line(gx, gy + gh, gx + gw, gy + gh, INK_BLACK, thickness=2)

    # Monotonically rising points
    pts = [
        (gx + 16, gy + gh - 8),
        (gx + 82, gy + gh - 16),
        (gx + 148, gy + gh - 26),
        (gx + 214, gy + gh - 42),
        (gx + 278, gy + gh - 64),
        (gx + 332, gy + 12),
    ]

    # Subtle rising bars underneath
    for px, py in pts:
        canvas.fill_rect(px - 10, py, 20, (gy + gh) - py, PAPER_ALT)

    # Thick rising line
    for i in range(len(pts) - 1):
        canvas.draw_line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], ACCENT_BLUE, thickness=5)

    for px, py in pts[:-1]:
        canvas.fill_circle(px, py, 5, ACCENT_GOLD)
        canvas.fill_circle(px, py, 2, INK_BLACK)

    # Bold upward arrow at peak aligned with final segment
    px0, py0 = pts[-2]
    tx, ty = pts[-1]
    dx, dy = tx - px0, ty - py0
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    canvas.fill_polygon(
        [
            (int(round(tx + ux * 10)), int(round(ty + uy * 10))),
            (int(round(tx - ux * 6 + nx * 8)), int(round(ty - uy * 6 + ny * 8))),
            (int(round(tx - ux * 6 - nx * 8)), int(round(ty - uy * 6 - ny * 8))),
        ],
        ACCENT_RED,
    )


def draw_icon_storm(canvas: Canvas, x: int, y: int, w: int, h: int) -> None:
    """Smooth spiral cyclone swirl over Bay of Bengal waves."""
    sea_top = y + h - 24
    _draw_waves(canvas, x, y, w, 24, sea_top)

    # Andhra coastline on the left with dark shoreline edge
    coast = [
        (x, sea_top - 24),
        (x + 34, sea_top - 18),
        (x + 56, sea_top - 8),
        (x + 76, sea_top),
        (x, sea_top + 6),
    ]
    canvas.fill_polygon(coast, ACCENT_GOLD)
    for i in range(len(coast) - 2):
        canvas.draw_line(
            coast[i][0], coast[i][1], coast[i + 1][0], coast[i + 1][1], RULE_DARK, thickness=2
        )

    cx = x + w // 2 + 22
    cy = y + 45

    # Two primary tapered spiral arms + two secondary outer cloud bands
    steps = 36
    for arm_idx, (base_ang, r_start, r_end, max_t, col) in enumerate(
        [
            (0.15, 11.0, 82.0, 7, ACCENT_BLUE),
            (0.15 + math.pi, 11.0, 82.0, 7, ACCENT_BLUE),
            (0.15 + math.pi * 0.5, 18.0, 62.0, 4, ACCENT_BLUE_LIGHT),
            (0.15 + math.pi * 1.5, 18.0, 62.0, 4, ACCENT_BLUE_LIGHT),
        ]
    ):
        prev_pt: tuple[int, int] | None = None
        for s in range(steps + 1):
            t = s / steps
            theta = base_ang + t * 1.45 * math.pi
            rad = r_start + (r_end - r_start) * (t ** 0.85)
            # Slightly elliptical perspective (1.28x horizontal, 0.50x vertical)
            px = int(round(cx + math.cos(theta) * rad * 1.28))
            py = int(round(cy + math.sin(theta) * rad * 0.48))
            if prev_pt is not None:
                thick = max(2, int(round(max_t * (1.0 - 0.7 * t))))
                canvas.draw_line(prev_pt[0], prev_pt[1], px, py, col, thickness=thick)
            prev_pt = (px, py)

    # Clear cyclone eye: blue wall, cream eye ring, red core
    canvas.fill_circle(cx, cy, 13, ACCENT_BLUE)
    canvas.fill_circle(cx, cy, 8, ICON_BG)
    canvas.fill_circle(cx, cy, 4, ACCENT_RED)


def draw_icon_siberia(canvas: Canvas, x: int, y: int, w: int, h: int) -> None:
    """Side-view airliner silhouette pitched nose-down with smoke and warning triangle."""
    cx = x + 156
    cy = y + 58
    ang = math.radians(12.0)  # Slight nose-down descent angle
    cos_a = math.cos(ang)
    sin_a = math.sin(ang)

    def rot(lx: float, ly: float) -> tuple[int, int]:
        return (
            int(round(cx + lx * cos_a - ly * sin_a)),
            int(round(cy + lx * sin_a + ly * cos_a)),
        )

    # Vertical tail fin (swept back)
    canvas.fill_polygon(
        [rot(-52, -7), rot(-78, -36), rot(-92, -36), rot(-78, -3)],
        INK_BLACK,
    )
    # Horizontal tailplane
    canvas.fill_polygon(
        [rot(-74, -2), rot(-92, -8), rot(-94, -3), rot(-78, 3)],
        ACCENT_BLUE,
    )
    # Fuselage (cigar profile with rounded nose)
    fuselage = [
        rot(-86, -2),
        rot(-52, -9),
        rot(54, -9),
        rot(74, -6),
        rot(88, 0),
        rot(90, 5),
        rot(82, 10),
        rot(62, 12),
        rot(-38, 12),
        rot(-86, 3),
    ]
    canvas.fill_polygon(fuselage, INK_BLACK)

    # Cockpit windshield
    canvas.fill_polygon(
        [rot(62, -6), rot(76, -4), rot(79, 1), rot(62, 1)],
        ICON_BG,
    )
    # Cabin window row
    for wx in (-28, -12, 4, 20, 36):
        wcx, wcy = rot(wx, -2)
        canvas.fill_rect(wcx - 3, wcy - 2, 6, 4, ICON_BG)

    # Single swept main wing + underwing engine nacelle
    canvas.fill_polygon(
        [rot(-4, 4), rot(-28, 28), rot(-10, 28), rot(24, 6)],
        ACCENT_BLUE,
    )
    canvas.fill_polygon(
        [rot(2, 16), rot(18, 16), rot(20, 23), rot(0, 23)],
        INK_BLACK,
    )

    # Trailing smoke puffs behind tail
    for sx, sy, sr, scol in (
        (-102, -16, 4, ACCENT_RED),
        (-116, -24, 5, RULE_DARK),
        (-130, -30, 4, RULE_LIGHT),
    ):
        px, py = rot(sx, sy)
        canvas.fill_circle(px, py, sr, scol)

    # Warning triangle on the right
    tx = x + w - 82
    ty = y + 23
    tri = [(tx, ty), (tx + 46, ty + 68), (tx - 46, ty + 68)]
    canvas.fill_polygon(tri, ACCENT_RED)
    inner = [(tx, ty + 13), (tx + 34, ty + 61), (tx - 34, ty + 61)]
    canvas.fill_polygon(inner, ACCENT_GOLD)
    canvas.fill_rect(tx - 3, ty + 27, 6, 18, INK_BLACK)
    canvas.fill_circle(tx, ty + 53, 4, INK_BLACK)


def draw_icon_quake(canvas: Canvas, x: int, y: int, w: int, h: int) -> None:
    """Unified cracked-ground fault with seismic arcs and full-width seismograph trace."""
    gx0 = x + 16
    gx1 = x + w - 16
    ex = x + w // 2
    gy = y + h - 32

    # Smooth semicircular seismic shockwave arcs radiating from the epicenter
    arc_steps = 28
    for rad, col in ((22, ACCENT_GOLD), (36, ACCENT_BLUE_LIGHT), (50, RULE_LIGHT)):
        prev_pt: tuple[int, int] | None = None
        for s in range(arc_steps + 1):
            a = math.pi + (math.pi * s) / arc_steps
            px = int(round(ex + math.cos(a) * rad * 1.4))
            py = int(round(gy + math.sin(a) * rad))
            if prev_pt is not None:
                canvas.draw_line(prev_pt[0], prev_pt[1], px, py, col, thickness=2)
            prev_pt = (px, py)

    # Unified full-width seismograph baseline and red trace peaking over the epicenter
    mid_y = y + 36
    canvas.draw_line(gx0 + 4, mid_y, gx1 - 4, mid_y, RULE_LIGHT, thickness=1)
    trace = [
        (gx0 + 6, mid_y),
        (ex - 130, mid_y),
        (ex - 112, mid_y - 4),
        (ex - 94, mid_y + 6),
        (ex - 74, mid_y - 12),
        (ex - 54, mid_y + 16),
        (ex - 36, mid_y - 26),
        (ex - 18, mid_y + 28),
        (ex, mid_y - 30),
        (ex + 18, mid_y + 26),
        (ex + 36, mid_y - 22),
        (ex + 54, mid_y + 14),
        (ex + 74, mid_y - 10),
        (ex + 94, mid_y + 5),
        (ex + 112, mid_y - 3),
        (ex + 130, mid_y),
        (gx1 - 6, mid_y),
    ]
    for i in range(len(trace) - 1):
        canvas.draw_line(
            trace[i][0], trace[i][1], trace[i + 1][0], trace[i + 1][1], ACCENT_RED, thickness=3
        )

    # Ruptured earth blocks separated by a V-shaped jagged fault at the center
    canvas.fill_polygon(
        [
            (gx0, gy + 4),
            (ex - 14, gy - 4),
            (ex - 4, gy + 10),
            (ex - 10, gy + 20),
            (ex - 2, gy + 26),
            (gx0, gy + 26),
        ],
        RULE_DARK,
    )
    canvas.fill_polygon(
        [
            (ex + 14, gy),
            (gx1, gy + 4),
            (gx1, gy + 26),
            (ex + 4, gy + 26),
            (ex + 12, gy + 16),
            (ex + 2, gy + 8),
        ],
        RULE_DARK,
    )
    # Red fault fissure highlight down the crack
    fissure = [(ex - 8, gy - 3), (ex + 2, gy + 8), (ex - 6, gy + 18), (ex + 2, gy + 26)]
    for i in range(len(fissure) - 1):
        canvas.draw_line(
            fissure[i][0], fissure[i][1], fissure[i + 1][0], fissure[i + 1][1], ACCENT_RED, thickness=3
        )


# ---------------------------------------------------------------------------
# 9. PANELS (Story data + panel layout)
# ---------------------------------------------------------------------------
STORIES = [
    {
        "kicker": "GULF",
        "headline": "IRAN HITS US BASES IN THE GULF",
        "deck": "DRONES AND MISSILES AT BASES IN BAHRAIN AND KUWAIT; GULF STATES INTERCEPT; ADNOC SHIP HIT IN HORMUZ",
        "icon": draw_icon_gulf,
    },
    {
        "kicker": "SUMMIT",
        "headline": "TRUMP LANDS IN SHENZHEN FOR APEC",
        "deck": "XI GREETS TRUMP AT AIRPORT; XI AND PUTIN MEET FOR 50TH TIME; FIRST TRILATERAL SET FOR THURSDAY",
        "icon": draw_icon_summit,
    },
    {
        "kicker": "MARKETS",
        "headline": "NVIDIA REVENUE DOUBLES TO $115.8BN",
        "deck": "FIRST QUARTER OVER $100BN; DATA CENTRE $107.6BN; BOARD RULES OUT HUANG'S RETURN",
        "icon": draw_icon_markets,
    },
    {
        "kicker": "STORM",
        "headline": "CYCLONE AKVAN BEARS DOWN ON ANDHRA",
        "deck": "SEVERE STORM OVER BAY OF BENGAL; LANDFALL DUE FRIDAY NEAR NELLORE",
        "icon": draw_icon_storm,
    },
    {
        "kicker": "SIBERIA",
        "headline": "RUSSIAN MILITARY PLANE CRASHES, 19 DEAD",
        "deck": "AN-12 DOWN NEAR KEMEROVO; ALL 19 ABOARD KILLED; TECHNICAL FAULT SUSPECTED",
        "icon": draw_icon_siberia,
    },
    {
        "kicker": "QUAKE",
        "headline": "MAGNITUDE 6 QUAKE HITS PAPUA NEW GUINEA",
        "deck": "GFZ REPORTS M6 TREMOR ON WEDNESDAY",
        "icon": draw_icon_quake,
    },
]


def draw_panel(
    canvas: Canvas, x: int, y: int, w: int, h: int, story: dict[str, object]
) -> None:
    """Draw one story card with kicker, wrapped headline, wrapped deck, and icon."""
    # Panel frame & top accent
    canvas.fill_rect(x, y, w, h, PAPER_ALT)
    canvas.stroke_rect(x, y, w, h, RULE_LIGHT, thickness=1)
    canvas.fill_rect(x, y, w, 4, INK_BLACK)

    pad = 16
    inner_w = w - 2 * pad
    tx = x + pad

    # Kicker
    kicker = str(story["kicker"])
    draw_text(canvas, kicker, tx, y + 14, scale=1, color=ACCENT_RED, thickness=2)
    kw = measure_text(kicker, scale=1)
    canvas.fill_rect(tx + kw + 10, y + 18, inner_w - kw - 10, 1, RULE_LIGHT)

    # Headline (scale 2, max 2 lines)
    headline_lines = wrap_text(str(story["headline"]), inner_w, scale=2)[:2]
    hy = y + 32
    for line in headline_lines:
        draw_text(canvas, line, tx, hy, scale=2, color=INK_BLACK, thickness=3)
        hy += 26

    # Deck (scale 1, max 2 lines)
    deck_lines = wrap_text(str(story["deck"]), inner_w, scale=1)[:2]
    dy = y + 88
    for line in deck_lines:
        draw_text(canvas, line, tx, dy, scale=1, color=INK_MUTED, thickness=1)
        dy += 15

    # Icon box
    ix = tx
    iy = y + 124
    iw = inner_w
    ih = h - 138
    canvas.fill_rect(ix, iy, iw, ih, ICON_BG)
    canvas.stroke_rect(ix, iy, iw, ih, RULE_LIGHT, thickness=1)
    icon_fn = story["icon"]
    icon_fn(canvas, ix, iy, iw, ih)  # type: ignore[operator]


# ---------------------------------------------------------------------------
# 10. RENDER
# ---------------------------------------------------------------------------
def render_poster() -> Canvas:
    """Compose the full 1024x1024 newspaper front page."""
    canvas = Canvas(WIDTH, HEIGHT, PAPER_BG)
    grid_top = draw_masthead(canvas)

    margin_x = 24
    col_gap = 20
    row_gap = 16
    panel_w = (WIDTH - 2 * margin_x - col_gap) // 2  # 478
    panel_h = 252

    for idx, story in enumerate(STORIES):
        row = idx // 2
        col = idx % 2
        px = margin_x + col * (panel_w + col_gap)
        py = grid_top + row * (panel_h + row_gap)
        draw_panel(canvas, px, py, panel_w, panel_h, story)

    draw_footer(canvas)
    return canvas


# ---------------------------------------------------------------------------
# 11. MAIN
# ---------------------------------------------------------------------------
def main() -> None:
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "entry.png")
    canvas = render_poster()
    png_bytes = encode_png(canvas)
    with open(out_path, "wb") as f:
        f.write(png_bytes)


if __name__ == "__main__":
    main()
