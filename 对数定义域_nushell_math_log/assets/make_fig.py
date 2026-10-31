"""Draw the domain figure for the Nushell `math log` article.

One canvas, two axes: the base axis, where the fix removes points from the
accepted set, and the value axis, where the accepted set is unchanged and only
`NaN` (which is on neither axis) changes side.  Run from the repository root:

    python 对数定义域_nushell_math_log/assets/make_fig.py

The script fails if any two text boxes overlap or a text box leaves the canvas.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, Rectangle

HERE = Path(__file__).resolve().parent
OUT = HERE / "fig_domain.png"

BG = "#F7F8FA"
INK = "#2C3E50"
GRAY = "#7F8C8D"
RED = "#C0392B"
RED_FILL = "#F5D7D2"
TEAL = "#0E8A7D"
TEAL_FILL = "#D5EEE9"

FONT = Path("C:/Windows/Fonts/msyh.ttc")
if FONT.exists():
    font_manager.fontManager.addfont(str(FONT))
plt.rcParams["font.family"] = "Microsoft YaHei"
plt.rcParams["axes.unicode_minus"] = False

W, H = 14.0, 6.4
fig = plt.figure(figsize=(W, H), dpi=100, facecolor=BG)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.axis("off")

texts = []


def text(x, y, value, size=12, color=INK, weight="normal", ha="left", va="center"):
    artist = ax.text(
        x, y, value, fontsize=size, color=color, fontweight=weight,
        ha=ha, va=va, zorder=5,
    )
    texts.append(artist)
    return artist


def axis(x0, x1, y, ticks, color=INK):
    ax.add_patch(
        FancyArrowPatch(
            (x0, y), (x1 + 0.14, y), arrowstyle="-|>", mutation_scale=14,
            color=color, lw=1.4, zorder=3,
        )
    )
    for x, label in ticks:
        ax.plot([x, x], [y - 0.06, y + 0.06], color=color, lw=1.2, zorder=3)
        text(x, y - 0.27, label, size=11, color=INK, ha="center")


def band(x0, x1, y, edge, fill, height=0.16):
    ax.add_patch(
        Rectangle((x0, y - height / 2), x1 - x0, height,
                  facecolor=fill, edgecolor=edge, linewidth=1.6, zorder=2)
    )


def hole(x, y, color=RED):
    ax.add_patch(plt.Circle((x, y), 0.10, facecolor=BG, edgecolor=color, lw=2.0, zorder=4))


def nan_marker(x, y):
    ax.add_patch(
        plt.Circle((x, y), 0.20, facecolor="#EDEFF2", edgecolor=GRAY,
                   lw=1.4, linestyle=(0, (2, 2)), zorder=3)
    )
    text(x, y, "NaN", size=10, color=GRAY, ha="center")


# ---------------------------------------------------------------- title
text(0.6, 6.02, "两根轴、三种点：好数、坏数，以及不在轴上的 NaN", size=19, weight="bold")

# ---------------------------------------------------------------- base axis
text(0.6, 5.27, "底数 b", size=13, weight="bold")
BASE_Y = 4.55
ticks_b = [(3.2, "0"), (4.45, "1"), (5.45, "2"), (6.85, "10"), (8.85, "∞")]
axis(1.1, 9.3, BASE_Y, ticks_b)
band(1.1, 3.08, BASE_Y, RED, RED_FILL)
band(3.32, 4.33, BASE_Y, TEAL, TEAL_FILL)
band(4.57, 8.73, BASE_Y, TEAL, TEAL_FILL)
hole(3.2, BASE_Y, GRAY)
hole(4.45, BASE_Y)
hole(8.85, BASE_Y)

text(2.15, 4.92, "旧判据在这里就拒绝：b ≤ 0", size=11, color=RED, ha="center")
text(4.45, 5.04, "b = 1", size=11, color=RED, ha="center")
text(8.85, 5.04, "b = ∞", size=11, color=RED, ha="center")
text(1.15, 4.05, "合并版只放行 (0, 1) ∪ (1, ∞) 里的有限数；1 与 ∞ 是这次补上的两个洞",
     size=11, color=TEAL)

nan_marker(10.6, 5.24)
text(10.95, 5.24, "不在轴上：b <= 0 与 b == 1 都是假", size=10, color=GRAY)
ax.plot([9.55, 10.36], [5.02, 5.2], color=GRAY, lw=1.0, linestyle=(0, (2, 2)), zorder=3)

# ---------------------------------------------------------------- value axis
text(0.6, 3.16, "输入 x", size=13, weight="bold")
VALUE_Y = 2.44
ticks_v = [(3.2, "0"), (4.35, "0.5"), (5.3, "1"), (6.3, "2"), (7.6, "10"), (8.85, "∞")]
axis(1.1, 9.3, VALUE_Y, ticks_v)
band(1.1, 3.08, VALUE_Y, RED, RED_FILL)
band(3.32, 8.95, VALUE_Y, TEAL, TEAL_FILL)
hole(3.2, VALUE_Y, GRAY)
text(2.15, 2.81, "两版都拒绝：x ≤ 0", size=11, color=RED, ha="center")
text(6.1, 2.81, "x > 0 放行，∞ 也放行（极限）", size=11, color=TEAL, ha="center")
text(1.15, 1.94, "轴上每个点，新旧判定给出的答案都一样；变的是轴外那一个",
     size=11, color=INK)

nan_marker(10.6, 2.44)
text(10.95, 2.44, "旧判据漏过去，新判据报错", size=10, color=RED)
ax.plot([9.55, 10.36], [2.44, 2.44], color=GRAY, lw=1.0, linestyle=(0, (2, 2)), zorder=3)

# ---------------------------------------------------------------- legend
text(0.6, 1.16, "青：合并版放行　　红圈：合并版新拦下的点　　红底：两版都拒绝　　灰虚线框：不在这根轴上", size=10, color=GRAY)
text(0.6, 0.74, "三版 log.rs 的提取运行，不是完整 Nushell；轴为示意，不按比例", size=9, color=GRAY)

# ---------------------------------------------------------------- checks
fig.canvas.draw()
renderer = fig.canvas.get_renderer()
boxes = [(artist.get_text(), artist.get_window_extent(renderer)) for artist in texts]
canvas = fig.bbox
for value, box in boxes:
    if box.x0 < 0 or box.y0 < 0 or box.x1 > canvas.width or box.y1 > canvas.height:
        raise SystemExit(f"text outside canvas: {value!r} -> {box}")
for i in range(len(boxes)):
    for j in range(i + 1, len(boxes)):
        if boxes[i][1].overlaps(boxes[j][1]):
            raise SystemExit(f"text boxes overlap: {boxes[i][0]!r} and {boxes[j][0]!r}")

fig.savefig(OUT, dpi=100, facecolor=BG)
print(f"wrote {OUT} ({OUT.stat().st_size} bytes), {len(texts)} text boxes checked")


