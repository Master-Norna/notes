"""Draw the PageRange.__add__ order-sensitivity figure (pre-fix behaviour).

Two panels: the same pair of ranges 2:5 and 2:0, added in each written
order. Their starts are equal, so the pre-fix ordering (by start only)
keeps the written order and the gap check references the stop of the
range written left: 5 when 2:5 is left (passes), 0 when 2:0 is left
(judges the segment (0, 2) a gap).
"""

from __future__ import annotations

import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch

OUT = pathlib.Path(__file__).with_name("pagerange-order.png")

INK = "#2b2b2b"
INK_SOFT = "#5a5a5a"
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


def text(x, y, s, size=13, color=INK, weight="normal", ha="center"):
    t = ax.text(
        x, y, s, fontsize=size, color=color, fontweight=weight,
        ha=ha, va="center", transform=ax.transAxes,
    )
    texts.append(t)
    return t


def box(x, y, s, edge, fill, size=12.5, weight="normal", w=0.2, h=0.135):
    patch = FancyBboxPatch(
        (x - w / 2, y - h / 2), w, h,
        boxstyle="round,pad=0.006,rounding_size=0.012",
        facecolor=fill, edgecolor=edge, linewidth=1.6,
        transform=ax.transAxes, zorder=2,
    )
    ax.add_patch(patch)
    t = text(x, y, s, size=size, color=edge, weight=weight)
    boxed_texts.append((t, patch))
    return patch


def xof(p: float) -> float:
    """Page index 0..5 -> axes x."""
    return 0.15 + (0.77 - 0.15) * p / 5


# Title block
text(0.5, 0.955, "起点相同：gap 检查参照谁的终点，看写法顺序", size=25, weight="bold")
text(
    0.5, 0.9,
    "修前只按起点排序，起点相同不换位置，写在左边的排在前面；gap 检查参照「左边那段的终点」。数轴为页下标（0–5）",
    size=14.5, color=INK_SOFT,
)

Y_A, Y_B = 0.60, 0.27


def number_line(y):
    ax.plot([0.122, 0.798], [y, y], color=INK, linewidth=2, zorder=1)
    for p in range(6):
        x = xof(p)
        ax.plot([x, x], [y - 0.008, y + 0.008], color=INK, linewidth=1.5, zorder=1)
        text(x, y - 0.045, str(p), size=11.5, color=INK_SOFT)


def pair(y, a_is_empty):
    """Draw the pair at line y. a_is_empty: a-layer holds 2:0 (bad order)."""
    layer_a, layer_b = (0.325, 0.365) if a_is_empty else (0.655, 0.695)
    if a_is_empty:
        # a = 2:0 (dashed, start dot at 2, open stop at 0); b = 2:5 (bar)
        y_a, y_b = layer_a, layer_b
        draw_empty(y_a)
        text(0.378, y_a, "a", size=11.5, color=INK_SOFT)
        draw_bar(y_b)
        text(0.378, y_b, "b", size=11.5, color=INK_SOFT)
    else:
        # a = 2:5 (bar); b = 2:0 (dashed)
        y_a, y_b = layer_a, layer_b
        draw_bar(y_a)
        text(0.378, y_a, "a", size=11.5, color=INK_SOFT)
        draw_empty(y_b)
        text(0.378, y_b, "b", size=11.5, color=INK_SOFT)
    # common start point
    ax.plot([xof(2)], [y], "o", color=INK, markersize=8, zorder=5)


def draw_bar(y):
    patch = FancyBboxPatch(
        (xof(2), y - 0.015), xof(5) - xof(2), 0.03,
        boxstyle="round,pad=0.002,rounding_size=0.006",
        facecolor=NEUTRAL, edgecolor=INK, linewidth=1.6,
        transform=ax.transAxes, zorder=2,
    )
    ax.add_patch(patch)
    text((xof(2) + xof(5)) / 2, y, "2:5", size=12)


def draw_empty(y):
    """Range 2:0: start at 2, stop at 0 (left of the start) -> empty."""
    ax.plot(
        [xof(2), xof(0)], [y, y], color=GREY, linewidth=2.2,
        linestyle=(0, (6, 4)), zorder=3,
    )
    ax.plot([xof(2)], [y], "o", color=INK, markersize=7, zorder=5)
    ax.plot(
        [xof(0)], [y], "o", color=PAPER, mfc=PAPER, mec=INK,
        markersize=7, markeredgewidth=1.8, zorder=5,
    )
    text((xof(2) + xof(0)) / 2, y - 0.028, "2:0", size=12)


# ---- panel A: 2:5 left (passes) -------------------------------------------
number_line(Y_A)
text(0.012, Y_A + 0.017, "写在左：2:5", size=13, weight="bold", ha="left")
text(0.012, Y_A - 0.017, "(a = 2:5, b = 2:0)", size=11.5, color=INK_SOFT, ha="left")
pair(Y_A, a_is_empty=False)
# the checked stop: 5 (right end of the a-bar), marked in green
ax.plot([xof(5)], [Y_A], "s", color=GREEN, mfc=PAPER, mec=GREEN,
        markersize=7.5, markeredgewidth=1.8, zorder=5)
# check bracket: b.start (2) vs a.stop (5)
ax.plot([xof(2), xof(5)], [0.745, 0.745], color=GREEN, linewidth=1.8, zorder=1)
ax.plot([xof(2), xof(2)], [0.727, 0.745], color=GREEN, linewidth=1.8, zorder=1)
ax.plot([xof(5), xof(5)], [0.727, 0.745], color=GREEN, linewidth=1.8, zorder=1)
text(0.394, 0.722, "b.start = 2", size=11, color=INK_SOFT, ha="right")
text(0.774, 0.722, "a.stop = 5", size=11, color=INK_SOFT, ha="left")
text(0.584, 0.788, "2 ≤ 5 → 无 gap", size=14, color=GREEN, weight="bold")
box(0.893, Y_A + 0.02, "gap 检查通过\n合并出 2:5\n（第 2–4 页）", GREEN, GREEN_FILL)

# ---- panel B: 2:0 left (false gap) ----------------------------------------
number_line(Y_B)
text(0.012, Y_B + 0.017, "写在左：2:0", size=13, weight="bold", ha="left")
text(0.012, Y_B - 0.017, "(a = 2:0, b = 2:5)", size=11.5, color=INK_SOFT, ha="left")
# the claimed gap segment (0, 2) on the line
ax.plot([xof(0), xof(2)], [Y_B, Y_B], color=RED, linewidth=4, zorder=4)
pair(Y_B, a_is_empty=True)
# the checked stop: 0 (open end of the empty a-range), marked in red
ax.plot([xof(0)], [Y_B], "s", color=RED, mfc=PAPER, mec=RED,
        markersize=7.5, markeredgewidth=1.8, zorder=5)
# check bracket: b.start (2) vs a.stop (0)
ax.plot([xof(0), xof(2)], [0.42, 0.42], color=RED, linewidth=1.8, zorder=1)
ax.plot([xof(0), xof(0)], [0.404, 0.42], color=RED, linewidth=1.8, zorder=1)
ax.plot([xof(2), xof(2)], [0.404, 0.42], color=RED, linewidth=1.8, zorder=1)
text(0.146, 0.397, "a.stop = 0", size=11, color=INK_SOFT, ha="right")
text(0.402, 0.397, "b.start = 2", size=11, color=INK_SOFT, ha="left")
text(0.274, 0.465, "2 > 0 → 判出 gap", size=14, color=RED, weight="bold")
text(0.274, 0.19, "判出的「gap」：(0, 2)", size=12.5, color=RED, weight="bold")
text(0.274, 0.15, "并集里并没有缺页", size=11.5, color=INK_SOFT)
box(0.893, Y_B + 0.02, "gap 检查失败\nValueError: Can't add\nPageRanges with gap",
    RED, RED_FILL, h=0.15)

# Bottom note: the fix makes both orders agree with panel A.
text(
    0.42, 0.045,
    "修后按（起点，−终点）排序：起点相同时终点大的那段永远排在前面，两种写法都按第一行处理",
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
