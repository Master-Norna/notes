"""Draw the yearday=366 mechanism figure.

Three rows: day 365 as the correct reference, day 366 before the fix, and
day 366 after the fix. Each row walks the same five stages that
relativedelta applies in leap year 2000.
"""

from __future__ import annotations

import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = pathlib.Path(__file__).with_name("yearday-map.png")

INK = "#2b2b2b"
INK_SOFT = "#5a5a5a"
LINE = "#d8d3c8"
PAPER = "#fbfaf7"
NEUTRAL = "#f2efe8"
RED = "#bf3b2b"
RED_FILL = "#fbe6e2"
GREEN = "#0f7f63"
GREEN_FILL = "#dff0e9"
GREY = "#8b857a"

FONT = "Microsoft YaHei"
if font_manager.findfont(FONT, fallback_to_default=False) is None:
    raise SystemExit("Microsoft YaHei not found")
plt.rcParams["font.family"] = FONT
plt.rcParams["axes.unicode_minus"] = False

FIGSIZE = (16, 9)
DPI = 100

fig = plt.figure(figsize=FIGSIZE, dpi=DPI, facecolor=PAPER)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")

texts: list = []
boxed_texts: list = []


def text(x, y, s, size=13, color=INK, weight="normal", ha="center", va="center"):
    t = ax.text(
        x, y, s, fontsize=size, color=color, fontweight=weight,
        ha=ha, va=va, transform=ax.transAxes,
    )
    texts.append(t)
    return t


def box(x, y, s, edge, fill, size=13.5, weight="normal", w=0.14, h=0.115):
    patch = FancyBboxPatch(
        (x - w / 2, y - h / 2), w, h,
        boxstyle="round,pad=0.006,rounding_size=0.012",
        facecolor=fill, edgecolor=edge, linewidth=1.6,
        transform=ax.transAxes, zorder=2,
    )
    ax.add_patch(patch)
    t = text(x, y, s, size=size, color=edge if edge != GREY else INK, weight=weight)
    boxed_texts.append((t, patch))
    return patch


def arrow(x_from, x_to, y, color=GREY):
    ax.add_patch(
        FancyArrowPatch(
            (x_from, y), (x_to, y),
            arrowstyle="-|>,head_width=4,head_length=7",
            color=color, linewidth=1.5, shrinkA=0, shrinkB=0,
            transform=ax.transAxes, zorder=1,
        )
    )


COLS = [0.175, 0.35, 0.525, 0.70, 0.875]
HALF = 0.07
ROWS = [0.655, 0.455, 0.245]

# Title block
text(0.5, 0.945, "闰年的第 366 天，走到了哪一天", size=25, weight="bold")
text(
    0.5, 0.888,
    "dateutil 的 relativedelta 把 yearday 换成 month/day，闰年再补一天；修复前后差在最后一步",
    size=14.5, color=INK_SOFT,
)

headers = ["yearday", "ydayidx 查表", "min(月末, day)", "闰年 leapdays", "2000-01-01 + Δ"]
for x, h in zip(COLS, headers):
    text(x, 0.795, h, size=13, color=INK_SOFT, weight="bold")

row_labels = [
    "yearday=365\n闰年对照",
    "yearday=366\n修前",
    "yearday=366\n修后",
]
for y, label, color in zip(ROWS, row_labels, [INK_SOFT, RED, GREEN]):
    text(0.012, y, label, size=12.5, color=color, ha="left", weight="bold")

rows = [
    # (input, table lookup, clamp, leapdays, result, edge, fill, arrow colour)
    ("365", "12 / 31", "31", "−1 天", "2000-12-30", GREY, NEUTRAL, GREY),
    ("366", "12 / 32", "31", "−1 天", "2000-12-30", RED, RED_FILL, RED),
    ("366", "12 / 32", "31", "不补偿", "2000-12-31", GREEN, GREEN_FILL, GREEN),
]

for y, row in zip(ROWS, rows):
    values, edge, fill, arrow_color = row[:5], row[5], row[6], row[7]
    for i, (x, value) in enumerate(zip(COLS, values)):
        if i == 0:
            box(x, y, value, edge if edge != GREY else GREY, NEUTRAL, weight="bold")
        elif i == 1 and edge == RED:
            box(x, y, value, edge, fill, weight="bold")
        elif i == 4:
            box(x, y, value, edge, fill, weight="bold")
        else:
            box(x, y, value, edge, fill)
        if i < len(COLS) - 1:
            arrow(x + HALF + 0.008, COLS[i + 1] - HALF - 0.008, y, arrow_color)

# Clarify the collision and the fix without crossing rows.
text(
    COLS[4], ROWS[1] - 0.085,
    "与 365 同一天", size=12.5, color=RED, weight="bold",
)
text(
    COLS[4], ROWS[2] - 0.085,
    "多出来的一天落回 12 月 31 日", size=12.5, color=GREEN, weight="bold",
)

text(
    0.5, 0.075,
    "ydayidx = [31, 59, 90, …, 334, 366]，366 − 334 = 32：十二月被算出第 32 天",
    size=12.5, color=INK_SOFT,
)

# --- text-box checks -------------------------------------------------------
fig.canvas.draw()
renderer = fig.canvas.get_renderer()
boxes = []
for t in texts:
    patch = t.get_bbox_patch()
    bb = patch.get_window_extent(renderer) if patch else t.get_window_extent(renderer)
    boxes.append((t, bb))

problems = []
for i in range(len(boxes)):
    for j in range(i + 1, len(boxes)):
        a, b = boxes[i][1], boxes[j][1]
        if a.overlaps(b):
            problems.append(
                f"overlap: {boxes[i][0].get_text()!r} <-> {boxes[j][0].get_text()!r}"
            )

boxed_ids = set()
for t, patch in boxed_texts:
    boxed_ids.add(id(t))
    bb = t.get_window_extent(renderer)
    pb = patch.get_window_extent(renderer)
    if not (pb.x0 <= bb.x0 and pb.x1 >= bb.x1 and pb.y0 <= bb.y0 and pb.y1 >= bb.y1):
        problems.append(f"text outside its box: {t.get_text()!r}")

patches = [patch.get_window_extent(renderer) for _, patch in boxed_texts]
for t, bb in boxes:
    if id(t) in boxed_ids:
        continue
    for pb in patches:
        if bb.overlaps(pb):
            problems.append(f"non-box text overlaps a box: {t.get_text()!r}")

width, height = fig.bbox.width, fig.bbox.height
for t, bb in boxes:
    if bb.x0 < -0.5 or bb.y0 < -0.5 or bb.x1 > width + 0.5 or bb.y1 > height + 0.5:
        problems.append(f"outside canvas: {t.get_text()!r} {bb}")

fig.savefig(OUT, dpi=DPI, facecolor=PAPER)
print(f"wrote {OUT} ({width:.0f}x{height:.0f})")
if problems:
    print("\n".join(problems))
    raise SystemExit(1)
print(f"checked {len(boxes)} text boxes: no overlap, no out-of-bounds")
