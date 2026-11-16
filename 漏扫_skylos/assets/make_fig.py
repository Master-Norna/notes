"""First hint shape vs merged hint on a run of spaces.

Data: `python -B run.py --test` in ../prefilter_demo (the backtracking table).
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

FONT = FontProperties(family="Microsoft YaHei")
RED = "#c0392b"
TEAL = "#1f7a7a"
INK = "#2b2b2b"
GRID = "#dcd8d0"
PAPER = "#fdfcf9"

N = [500, 1000, 2000, 4000, 8000]
FIRST = [2.63, 10.51, 41.21, 177.01, 696.38]
MERGED = [0.028, 0.058, 0.110, 0.237, 0.433]

fig, ax = plt.subplots(figsize=(7.7, 3.4), dpi=200)
fig.patch.set_facecolor(PAPER)
ax.set_facecolor(PAPER)

ax.plot(N, FIRST, color=RED, linewidth=2.2, marker="o", markersize=5, zorder=3)
ax.plot(N, MERGED, color=TEAL, linewidth=2.2, marker="o", markersize=5, zorder=3)

ax.set_xlabel("空格数", fontproperties=FONT, fontsize=10, color=INK)
ax.set_ylabel("耗时（毫秒）", fontproperties=FONT, fontsize=10, color=INK)
ax.set_xlim(0, 8600)
ax.set_ylim(0, 790)
ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
for side in ("top", "right"):
    ax.spines[side].set_visible(False)
for side in ("left", "bottom"):
    ax.spines[side].set_color(GRID)
ax.tick_params(colors=INK, labelsize=9)
for label in ax.get_xticklabels() + ax.get_yticklabels():
    label.set_fontproperties(FONT)

texts = []
texts.append(ax.annotate(
    "第一版 hint",
    xy=(4000, 177.01), xytext=(2500, 350),
    color=RED, fontproperties=FONT, fontsize=10,
    arrowprops=dict(arrowstyle="-", color=RED, linewidth=0.9),
))
texts.append(ax.annotate(
    "约 0.7 秒",
    xy=(8000, 696.38), xytext=(6300, 700),
    color=RED, fontproperties=FONT, fontsize=9,
))
texts.append(ax.annotate(
    "每翻倍约 ×4",
    xy=(2000, 41.21), xytext=(1150, 160),
    color=RED, fontproperties=FONT, fontsize=9,
    arrowprops=dict(arrowstyle="-", color=RED, linewidth=0.8),
))
texts.append(ax.annotate(
    "合并版 hint",
    xy=(6000, 0.30), xytext=(5200, 100),
    color=TEAL, fontproperties=FONT, fontsize=10,
    arrowprops=dict(arrowstyle="-", color=TEAL, linewidth=0.9),
))
texts.append(ax.annotate(
    "< 0.5 ms",
    xy=(8000, 0.433), xytext=(6900, 45),
    color=TEAL, fontproperties=FONT, fontsize=9,
))

fig.tight_layout(pad=0.6)


def check() -> None:
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    boxes = [(t.get_text(), t.get_window_extent(renderer)) for t in texts]
    axes_box = ax.get_window_extent(renderer)
    for name, box in boxes:
        if box.x0 < axes_box.x0 or box.x1 > axes_box.x1 or box.y0 < axes_box.y0 or box.y1 > axes_box.y1:
            raise SystemExit(f"text out of axes: {name!r}")
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if boxes[i][1].overlaps(boxes[j][1]):
                raise SystemExit(f"text overlap: {boxes[i][0]!r} vs {boxes[j][0]!r}")

    # A data line must not run through a label.  Walk each polyline in pixel
    # space and test membership in every text box, shrunk by 2 px.
    for values in (FIRST, MERGED):
        for k in range(len(N) - 1):
            x0, y0 = ax.transData.transform((N[k], values[k]))
            x1, y1 = ax.transData.transform((N[k + 1], values[k + 1]))
            for step in range(201):
                t = step / 200
                px, py = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
                for name, box in boxes:
                    if box.x0 + 2 < px < box.x1 - 2 and box.y0 + 2 < py < box.y1 - 2:
                        raise SystemExit(f"line crosses label {name!r} near ({px:.0f},{py:.0f})")


check()
fig.savefig("backtrack.png", dpi=200, facecolor=PAPER)
print("wrote backtrack.png")

