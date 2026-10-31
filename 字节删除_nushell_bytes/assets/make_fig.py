"""Draw the byte-position figure for the Nushell bytes-remove article.

The figure shows where the old backward scan starts, which bytes it collects,
and which leading bytes never enter `result`.  Run from the repository root:

    python 字节删除_nushell_bytes/assets/make_fig.py

The script fails if any two text boxes overlap or a text box leaves the canvas.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, Rectangle

HERE = Path(__file__).resolve().parent
OUT = HERE / "fig_prefix_loss.png"

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

W, H = 14.0, 7.6
fig = plt.figure(figsize=(W, H), dpi=100, facecolor=BG)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.axis("off")

texts = []


def text(x, y, value, size=12, color=INK, weight="normal", ha="left", va="center"):
    artist = ax.text(
        x,
        y,
        value,
        fontsize=size,
        color=color,
        fontweight=weight,
        ha=ha,
        va=va,
        zorder=5,
    )
    texts.append(artist)
    return artist


def cell(x, y, value, edge, fill, width=1.0, height=0.7, size=15, color=INK):
    ax.add_patch(
        Rectangle(
            (x, y),
            width,
            height,
            facecolor=fill,
            edgecolor=edge,
            linewidth=2.0,
            zorder=2,
        )
    )
    text(x + width / 2, y + height / 2, value, size=size, color=color, ha="center")


def bracket(x1, x2, y, label, color=GRAY):
    ax.plot([x1, x1, x2, x2], [y + 0.12, y, y, y + 0.12], color=color, lw=1.6, zorder=3)
    text(x2 + 0.15, y + 0.06, label, size=11, color=color)


# ---------------------------------------------------------------- old behaviour
text(0.55, 7.18, "修前：窗口向左滑，前面的字节没有进入结果", size=20, weight="bold")

base_x, base_y, cell_w, cell_h = 0.6, 5.25, 1.0, 0.7
bytes_ = ["10", "11", "12", "13"]
for index, value in enumerate(bytes_):
    edge = RED if index == 0 else TEAL
    fill = RED_FILL if index == 0 else TEAL_FILL
    cell(base_x + index * cell_w, base_y, value, edge, fill)

for index in range(4):
    text(
        base_x + index * cell_w + cell_w / 2,
        base_y + cell_h + 0.22,
        f"下标 {index}",
        size=10,
        color=GRAY,
        ha="center",
    )

text(base_x, base_y + cell_h + 0.62, "输入", size=12, color=INK, weight="bold")
text(base_x + cell_w * 0.5, base_y - 0.3, "从未收集", size=11, color=RED, ha="center")
text(base_x + cell_w * 2.0, base_y - 0.3, "已收集，等待反转", size=11, color=TEAL, ha="center")

# Three window positions: [2,4), [1,3), [0,2)
for step, (start, y) in enumerate([(2, 4.55), (1, 4.05), (0, 3.55)]):
    x1 = base_x + start * cell_w
    x2 = x1 + 2 * cell_w
    bracket(x1, x2, y, "AA BB 不匹配" if step == 0 else "继续左移，仍不匹配")

# An arrow showing the scan direction.
ax.add_patch(
    FancyArrowPatch(
        (4.75, 3.95),
        (1.0, 3.95),
        arrowstyle="-|>",
        mutation_scale=16,
        color=GRAY,
        lw=1.4,
        zorder=3,
    )
)
text(2.9, 3.2, "扫描方向", size=10, color=GRAY, ha="center")

text(6.15, 5.9, "result 里只有后段", size=13, color=INK, weight="bold")
for index, value in enumerate(["13", "12", "11"]):
    cell(6.15 + index * 0.62, 5.05, value, TEAL, TEAL_FILL, width=0.55, height=0.55, size=12)

text(6.15, 4.55, "反转后返回", size=10, color=GRAY)
for index, value in enumerate(["11", "12", "13"]):
    cell(6.15 + index * 0.62, 3.75, value, TEAL, TEAL_FILL, width=0.55, height=0.55, size=12)

text(6.15, 3.25, "left = -1", size=12, color=RED, weight="bold")
text(7.35, 3.25, "→ if left > 0 跳过回填", size=11, color=RED)
text(6.15, 2.9, "10 从未被 push，回填分支也没有执行", size=11, color=RED)

# ---------------------------------------------------------------- final behaviour
text(0.55, 2.45, "修后：先找位置，找不到就原样返回", size=20, weight="bold")

base_y2 = 1.05
for index, value in enumerate(bytes_):
    cell(base_x + index * cell_w, base_y2, value, TEAL, TEAL_FILL)

text(base_x, base_y2 + cell_h + 0.28, "输入", size=12, color=INK, weight="bold")
text(base_x + cell_w * 2.0, base_y2 + cell_h + 0.28, "rposition(AA BB) = None", size=11, color=TEAL, ha="center")

ax.add_patch(
    FancyArrowPatch(
        (4.75, base_y2 - 0.18),
        (1.0, base_y2 - 0.18),
        arrowstyle="-|>",
        mutation_scale=16,
        color=TEAL,
        lw=1.4,
        zorder=3,
    )
)
text(2.9, base_y2 - 0.42, "从右往左找，整段都没有匹配", size=10, color=TEAL, ha="center")

text(6.15, 1.55, "None → 返回原输入", size=13, color=TEAL, weight="bold")
for index, value in enumerate(bytes_):
    cell(6.15 + index * 0.62, 0.55, value, TEAL, TEAL_FILL, width=0.55, height=0.55, size=12)

# ---------------------------------------------------------------- legend / note
ax.add_patch(Rectangle((11.0, 6.75), 0.32, 0.32, facecolor=RED_FILL, edgecolor=RED, lw=1.5))
text(11.45, 6.91, "丢失 / 未收集", size=10, color=RED)
ax.add_patch(Rectangle((11.0, 6.28), 0.32, 0.32, facecolor=TEAL_FILL, edgecolor=TEAL, lw=1.5))
text(11.45, 6.44, "保留 / 已收集", size=10, color=TEAL)

text(
    0.55,
    0.18,
    "五个固定提交的 remove_impl 提取运行；不是完整 Nushell",
    size=9,
    color=GRAY,
)

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
            raise SystemExit(
                f"text boxes overlap: {boxes[i][0]!r} and {boxes[j][0]!r}"
            )

fig.savefig(OUT, dpi=100, facecolor=BG)
print(f"wrote {OUT} ({OUT.stat().st_size} bytes), {len(texts)} text boxes checked")
