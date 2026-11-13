"""Draw the Iceberg swap window and what the finally block does to it.

The timeline is the failure path: create the temp table and fill it, drop the
target, then fail on the rename. Between the last two steps the temp table is
the only complete copy; the finally block reaches exactly that table.

Text is placed by hand; the script checks that every label stays inside its own
frame, that no label sits on a foreign frame, and that no two labels overlap.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

plt.rcParams["font.family"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

HERE = Path(__file__).resolve().parent
OUT = HERE / "swap-window.png"
DEBUG = "--debug" in sys.argv

INK = "#24313a"
INK2 = "#5b6b77"
EDGE = "#3d4a54"
RED, RED_EDGE, RED_FACE = "#8e2a20", "#b23a2e", "#fdf2f0"
TEAL, TEAL_EDGE, TEAL_FACE = "#20665a", "#2f7d6e", "#f1faf7"
GREY_FACE = "#fbfcfd"

W, H = 14.0, 6.2
fig = plt.figure(figsize=(W, H), dpi=110)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.axis("off")

GROUPS = []
FREE = []


def rect(x, y, w, h, *, edge=EDGE, face="#ffffff", lw=1.3, dashed=False):
    patch = FancyBboxPatch((x, y), w, h,
                           boxstyle="round,pad=0.03,rounding_size=0.06",
                           linewidth=lw, edgecolor=edge, facecolor=face,
                           linestyle=(0, (4, 2)) if dashed else "solid")
    ax.add_patch(patch)
    return patch


def text(x, y, s, *, size=10.5, color=INK, ha="center", va="center", weight="normal", rotation=0):
    t = ax.text(x, y, s, fontsize=size, color=color, ha=ha, va=va, weight=weight, rotation=rotation)
    FREE.append(t)
    return t


def arrow(x1, y1, x2, y2, *, color=INK2, lw=1.3, head=True):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>" if head else "-",
                                 mutation_scale=13, linewidth=lw, color=color,
                                 shrinkA=0, shrinkB=0))


def block(x, y, w, h, s, *, edge=EDGE, face="#ffffff", color=INK, size=10.5, lw=1.3):
    patch = rect(x, y, w, h, edge=edge, face=face, lw=lw)
    made = []
    if s:
        made.append(ax.text(x + w / 2, y + h / 2, s, fontsize=size, color=color,
                            ha="center", va="center"))
    GROUPS.append((patch, made))
    return patch


# ------------------------------------------------------------------ title
text(0.38, H - 0.35, "失败停在交换窗口：finally 删的是唯一一份", size=14.5, ha="left", weight="bold")

# ------------------------------------------------------------------ stage heads
heads = [(2.55, "建临时表，写 3 行"), (5.85, "drop 目标"), (9.15, "rename 抛错")]
for cx, s in heads:
    text(cx, 5.25, s, size=10.5, color=INK)

# ------------------------------------------------------------------ lanes
text(0.5, 4.72, "demo.t（目标名）", size=9.6, color=INK2, ha="left")
text(0.5, 3.55, "demo.t__pxt_tmp_xxxxxxxx（临时名）", size=9.6, color=INK2, ha="left")

by1, by2, bh = 3.85, 2.65, 0.7
xs = [1.4, 4.7, 8.0]
bw = 2.3

block(xs[0], by1, bw, bh, "1 行（旧）")
block(xs[1], by1, bw, bh, "不存在", edge=RED_EDGE, face=RED_FACE, color=RED)
block(xs[2], by1, bw, bh, "不存在", edge=RED_EDGE, face=RED_FACE, color=RED)

block(xs[0], by2, bw, bh, "3 行（新）", edge=TEAL_EDGE, face=TEAL_FACE, color=TEAL)
block(xs[1], by2, bw, bh, "3 行（新）", edge=TEAL_EDGE, face=TEAL_FACE, color=TEAL)
block(xs[2], by2, bw, bh, "3 行（新）", edge=TEAL_EDGE, face=TEAL_FACE, color=TEAL)

for y in (by1 + bh / 2, by2 + bh / 2):
    arrow(xs[0] + bw + 0.08, y, xs[1] - 0.08, y)
    arrow(xs[1] + bw + 0.08, y, xs[2] - 0.08, y)

# the swap window, between drop and rename
ax.add_patch(Rectangle((xs[1] + bw, 2.45), xs[2] - xs[1] - bw, 2.3,
                       facecolor="#fdf2f0", edgecolor=RED_EDGE, linewidth=1.0,
                       linestyle=(0, (3, 3)), alpha=0.55))
text((xs[1] + bw + xs[2]) / 2, 3.6, "窗口", size=10.0, color=RED, rotation=90)

text(xs[2] + bw / 2, 3.6, "唯一一份完整导出", size=9.6, color=TEAL)

# ------------------------------------------------------------------ finally
ax.plot([xs[2] + bw + 0.05, 11.35], [3.0, 3.0], color="#5b6b77", linewidth=1.2)
ax.plot([11.35, 11.35], [3.0, 2.13], color="#5b6b77", linewidth=1.2)
ax.plot([11.35, xs[2] + bw / 2], [2.13, 2.13], color="#5b6b77", linewidth=1.2)
arrow(xs[2] + bw / 2, 2.13, xs[2] + bw / 2, by2 - 0.04, color="#b23a2e", lw=1.6)
text(10.42, 3.16, "父版：无条件", size=9.0, color=RED, ha="left")
text(10.3, 1.98, "finally: drop_table(temp_name)", size=9.6, color=INK2, ha="right")

# ------------------------------------------------------------------ outcomes
oy, oh = 0.55, 1.1
block(1.4, oy, 5.8, oh, "", edge=RED_EDGE, face=RED_FACE)
text(1.62, oy + oh - 0.28, "修复前：无条件删除", size=10.8, color=RED, ha="left")
text(1.62, oy + 0.48, "目标不存在，临时 0 行", size=9.8, color=RED, ha="left")
text(1.62, oy + 0.18, "5 个场景里 3 个一行不剩", size=9.8, color=RED, ha="left")

block(7.6, oy, 5.75, oh, "", edge=TEAL_EDGE, face=TEAL_FACE)
text(7.82, oy + oh - 0.28, "修复后：temp_created 且 not preserve_temp 才删", size=10.0,
     color=TEAL, ha="left")
text(7.82, oy + 0.48, "目标不存在，临时 3 行", size=9.8, color=TEAL, ha="left")
text(7.82, oy + 0.18, "错误里点名，可以读回", size=9.8, color=TEAL, ha="left")

fig.savefig(OUT, facecolor="#ffffff")

# ------------------------------------------------------------------ checks
fig.canvas.draw()
renderer = fig.canvas.get_renderer()
inv = ax.transData.inverted()

problems = []
all_texts = [t for _, ts in GROUPS for t in ts] + FREE
for t in all_texts:
    bb = t.get_window_extent(renderer=renderer)
    if bb.x0 < -1 or bb.y0 < -1 or bb.x1 > fig.bbox.width + 1 or bb.y1 > fig.bbox.height + 1:
        problems.append(f"out of canvas: {t.get_text()!r}")
for patch, ts in GROUPS:
    pb = patch.get_window_extent(renderer=renderer)
    for t in ts:
        tb = t.get_window_extent(renderer=renderer)
        if tb.x0 < pb.x0 + 1 or tb.x1 > pb.x1 - 1 or tb.y0 < pb.y0 + 1 or tb.y1 > pb.y1 - 1:
            problems.append(f"label leaves its frame: {t.get_text()!r}")
for i in range(len(all_texts)):
    a = all_texts[i].get_window_extent(renderer=renderer)
    for j in range(i + 1, len(all_texts)):
        b = all_texts[j].get_window_extent(renderer=renderer)
        ix = min(a.x1, b.x1) - max(a.x0, b.x0)
        iy = min(a.y1, b.y1) - max(a.y0, b.y0)
        if ix > 2 and iy > 2:
            problems.append(f"text overlap: {all_texts[i].get_text()!r} / {all_texts[j].get_text()!r}")

# lines must not run through a label: hide the text and look for ink
import numpy as np

fig.canvas.draw()
for t in all_texts:
    t.set_visible(False)
fig.canvas.draw()
buf = np.asarray(fig.canvas.buffer_rgba())
height = buf.shape[0]
for t in all_texts:
    bb = t.get_window_extent(renderer=renderer)
    x0, x1 = int(bb.x0) + 2, int(bb.x1) - 1
    y0, y1 = int(height - bb.y1) + 2, int(height - bb.y0) - 1
    region = buf[y0:y1, x0:x1, :3]
    ink = int(((region < 200).any(axis=2)).sum())
    if ink > 4:
        problems.append(f"ink under label: {t.get_text()!r} ({ink} px)")
for t in all_texts:
    t.set_visible(True)

if DEBUG:
    for t in all_texts:
        bb = t.get_window_extent(renderer=renderer)
        (x0, y0), (x1, y1) = inv.transform([[bb.x0, bb.y0], [bb.x1, bb.y1]])
        print(f"  {t.get_text()[:40]!r:44} x {x0:5.2f}-{x1:5.2f}  y {y0:5.2f}-{y1:5.2f}")

if problems:
    print("\n".join(problems))
    sys.exit(1)
print(f"ok {OUT.name} {OUT.stat().st_size} bytes")



