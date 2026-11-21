"""Draw the figure for the jsonschema trailing-newline post.

One instance, two anchors: ``$`` can end a match just before a final
newline, ``\\Z`` cannot.  The character row is literal (the timestamp used
in the official suite), the two anchors are placed on the character index
they refer to, and the two bottom lines are the patterns' verdicts.

Run with --debug to print measured boxes in data units.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

plt.rcParams["font.family"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

HERE = Path(__file__).resolve().parent
DEBUG = "--debug" in sys.argv

INK = "#24313a"
INK2 = "#5b6b77"
EDGE = "#3d4a54"
RED, RED_EDGE, RED_FACE = "#8e2a20", "#b23a2e", "#fdf2f0"
TEAL, TEAL_EDGE, TEAL_FACE = "#20665a", "#2f7d6e", "#f1faf7"
GREY_FACE = "#fbfcfd"
MONO = ["Cascadia Mono", "Consolas", "DejaVu Sans Mono"]


class Canvas:
    def __init__(self, w: float, h: float):
        self.w, self.h = w, h
        self.fig = plt.figure(figsize=(w, h), dpi=110)
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, w)
        self.ax.set_ylim(0, h)
        self.ax.axis("off")
        self.boxes: list[tuple[str, tuple[float, float, float, float]]] = []

    def rect(self, x, y, w, h, *, edge=EDGE, face="#ffffff", dashed=False, lw=1.2):
        patch = FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.02,rounding_size=0.05",
            linewidth=lw, edgecolor=edge, facecolor=face,
            linestyle=(0, (4, 2)) if dashed else "solid",
        )
        self.ax.add_patch(patch)

    def text(self, x, y, s, *, size=13, color=INK, ha="left", va="center",
             family=None, weight="normal"):
        kw = {}
        if family:
            kw["family"] = family
        self.ax.text(x, y, s, fontsize=size, color=color, ha=ha, va=va,
                     weight=weight, **kw)

    def arrow(self, x1, y1, x2, y2, *, color=RED_EDGE, lw=1.3):
        self.ax.add_patch(FancyArrowPatch(
            (x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=10,
            linewidth=lw, color=color, shrinkA=0, shrinkB=0,
        ))


def draw(path: Path) -> None:
    c = Canvas(15.4, 6.6)

    # --- the instance row -------------------------------------------------
    text = "1985-04-12T23:20:50Z\n"
    cells = "1985-04-12T23:20:50Z\n"
    x0, cell = 1.05, 0.55
    y = 3.55
    c.text(x0 - 0.75, y + 0.62, 'jsonschema 的 date-time 收到的字符串：',
           size=13, color=INK2)
    for i, ch in enumerate(cells):
        fill = "#eef1f3" if ch == "\n" else "#ffffff"
        edge = EDGE
        c.rect(x0 + i * cell, y - 0.5, cell, 0.62, edge=edge, face=fill)
        shown = "\\n" if ch == "\n" else ch
        c.text(x0 + i * cell + cell / 2, y - 0.19, shown, size=15 if ch != "\n" else 12,
               ha="center", family=MONO,
               color=RED if ch == "\n" else INK)
        c.text(x0 + i * cell + cell / 2, y - 0.72, str(i + 1), size=8,
               color=INK2, ha="center", family=MONO)

    # the U+000A tag under the last cell
    last_x = x0 + (len(cells) - 1) * cell
    c.text(last_x + cell / 2, y - 1.08, "U+000A", size=9, color=RED, ha="center",
           family=MONO)

    # --- the two anchor positions ----------------------------------------
    before_lf = last_x           # between Z and \n
    after_lf = last_x + cell     # after \n

    c.arrow(before_lf, y + 1.15, before_lf, y + 0.30, color=RED_EDGE)
    c.text(before_lf - 0.12, y + 1.32, "`$` 可以在这里收尾", size=13, color=RED,
           ha="right")
    c.text(before_lf - 0.12, y + 1.05, "匹配只吃到 Z，换行留在外面", size=10.5,
           color=RED, ha="right")

    c.arrow(after_lf, y + 1.15, after_lf, y + 0.30, color=TEAL_EDGE)
    c.text(after_lf + 0.12, y + 1.32, "`\\Z` 只认串尾", size=13, color=TEAL,
           ha="left")
    c.text(after_lf + 0.12, y + 1.05, "换行还没被吃掉", size=10.5,
           color=TEAL, ha="left")

    # --- verdict lines ----------------------------------------------------
    ly = 1.55
    c.rect(1.55, ly - 0.42, 5.6, 0.66, edge=RED_EDGE, face=RED_FACE)
    c.text(1.75, ly - 0.10, 're.match(r"^…Z$",  s)', size=13, family=MONO, color=INK)
    c.text(6.95, ly - 0.10, "match", size=13, color=RED, weight="bold", ha="right")

    c.rect(7.75, ly - 0.42, 5.6, 0.66, edge=TEAL_EDGE, face=TEAL_FACE)
    c.text(7.95, ly - 0.10, 're.match(r"^…Z\\Z", s)', size=13, family=MONO, color=INK)
    c.text(13.15, ly - 0.10, "no match", size=13, color=TEAL, weight="bold", ha="right")

    # --- one-line footer --------------------------------------------------
    c.text(1.05, 0.62,
           "七个 format 的委托链（date-time / time / uri / uri-reference / iri / "
           "iri-reference / hostname）都在用前一种收尾。",
           size=11, color=INK2)

    c.fig.savefig(path, dpi=110, facecolor="white")
    plt.close(c.fig)
    print("wrote", path)


if __name__ == "__main__":
    out = HERE / "dollar-vs-Z.png"
    draw(out)
    if DEBUG:
        from PIL import Image
        im = Image.open(out)
        print("size:", im.size)
