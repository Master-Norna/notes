"""Where the two-line ignore window sits in three skylos versions.

Data: `python -B run.py --table` in ../cicd_ignore_demo (case
d340_quoted_name_block). The window is the anchor line and the line above it;
`_is_inline_ignored` searches exactly those two raw lines.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Rectangle

SANS = FontProperties(family="Microsoft YaHei")
MONO = FontProperties(family="Consolas")

RED = "#c0392b"
TEAL = "#1f7a7a"
INK = "#2b2b2b"
SOFT = "#6b6459"
PAPER = "#fdfcf9"
BAND = "#efe9df"
WARN = "#f6e2de"

LINES = [
    '6    - name: "note: skylos: ignore[SKY-D340]"',
    "7      run: |",
    "8        twine upload dist/*",
]

# (label, window lines, does the quoted line sit inside the window, verdict, colour)
ROWS = [
    ("v5.6.0", (7, 8), False, "报出 · 第 8 行", SOFT),
    ("父版", (6, 7), True, "消失", RED),
    ("合并版", (6, 7), True, "报出 · 第 7 行", TEAL),
]

Y = [0.80, 0.48, 0.16]
LINE_H = 0.072

fig = plt.figure(figsize=(7.7, 3.9), dpi=200)
fig.patch.set_facecolor(PAPER)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_facecolor(PAPER)
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")

for (label, window, quoted_inside, verdict, colour), y0 in zip(ROWS, Y):
    ax.text(0.02, y0 + 0.062, label, fontproperties=SANS, fontsize=10.5,
            color=INK, va="center", ha="left", fontweight="bold")

    for index, line in enumerate(LINES):
        number = 6 + index
        y = y0 - index * LINE_H
        if number in window:
            ax.add_patch(Rectangle((0.145, y - 0.030), 0.575, LINE_H - 0.004,
                                   facecolor=WARN if quoted_inside else BAND,
                                   edgecolor="none", zorder=0))
        ax.text(0.158, y, line, fontproperties=MONO, fontsize=8.6,
                color=RED if (quoted_inside and number == 6) else INK,
                va="center", ha="left", zorder=2)

    ax.text(0.735, y0, "两行窗口", fontproperties=SANS, fontsize=8.4,
            color=SOFT, va="center", ha="left")
    ax.text(0.98, y0 - LINE_H, verdict, fontproperties=SANS, fontsize=9.6,
            color=colour, va="center", ha="right")

ax.text(0.02, 0.95, "锚所在行 + 上一行，是唯一被查的两行",
        fontproperties=SANS, fontsize=9.2, color=SOFT, va="center", ha="left")

out = __file__.replace("make_fig.py", "ignore-window.png")
fig.savefig(out, facecolor=PAPER)

# Self-check: no two text boxes may overlap, and none may leave the canvas.
fig.canvas.draw()
renderer = fig.canvas.get_renderer()
boxes = [(artist.get_text(), artist.get_window_extent(renderer)) for artist in ax.texts]
problems = []
for i, (text_a, box_a) in enumerate(boxes):
    for text_b, box_b in boxes[i + 1 :]:
        if box_a.overlaps(box_b):
            problems.append(f"overlap: {text_a!r} / {text_b!r}")
for text, box in boxes:
    if not (0 <= box.x0 and box.x1 <= fig.bbox.x1 and 0 <= box.y0 and box.y1 <= fig.bbox.y1):
        problems.append(f"outside: {text!r}")
print("self-check:", "; ".join(problems) if problems else "no overlap, all inside")
print("wrote", out)
