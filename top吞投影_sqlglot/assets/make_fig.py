"""Draw the figure for the sqlglot TOP post (top-limit-slots.png).

Three silent shapes, two destination slots.  The projection list never
starts on that path: the TOP word is consumed as a limit introducer and
whatever follows lands in exp.Limit(expression=<rows>, offset=<skip>).
Grey cell = slot left empty, light-red cell = a value landed in the wrong
slot (or a required slot stayed empty and validation failed).

Every value comes from top吞投影_sqlglot/top_demo/run.py --test
(30.33.0 vs 30.33.0+dc4afaf5).

Text is placed by hand.  The figure checks that every label stays inside
the canvas, that no two labels overlap, and that no rule runs through a
label.  Run with --debug to print measured boxes in data units.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

plt.rcParams["font.family"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

HERE = Path(__file__).resolve().parent
DEBUG = "--debug" in sys.argv

INK = "#24313a"
INK2 = "#5b6b77"
MUTED = "#8b959d"
EDGE = "#3d4a54"
RED, RED_EDGE = "#8e2a20", "#b23a2e"
BADR = "#f3ded9"      # light red fill: wrong slot / missing required slot
EMPTYF = "#eef1f3"    # grey fill: slot left empty


class Canvas:
    def __init__(self, w: float, h: float):
        self.w, self.h = w, h
        self.fig = plt.figure(figsize=(w, h), dpi=110)
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, w)
        self.ax.set_ylim(0, h)
        self.ax.axis("off")
        self.free: list = []

    def text(self, x, y, s, *, size=11.0, color=INK, ha="center", va="center",
             weight="normal", mono=False):
        t = self.ax.text(x, y, s, fontsize=size, color=color, ha=ha, va=va,
                         weight=weight,
                         family=["Consolas", "DejaVu Sans Mono"] if mono
                         else plt.rcParams["font.family"])
        self.free.append(t)
        return t

    def box(self, x, y, w, h, face, edge, lw=1.2):
        self.ax.add_patch(Rectangle((x, y), w, h, facecolor=face,
                                    edgecolor=edge, linewidth=lw, zorder=2))

    def save(self, path: Path):
        self.fig.savefig(path, facecolor="#ffffff")
        self.fig.canvas.draw()
        renderer = self.fig.canvas.get_renderer()

        def bbox(t):
            return t.get_window_extent(renderer=renderer)

        problems = []
        for t in self.free:
            bb = bbox(t)
            if bb.x0 < -1 or bb.y0 < -1 or bb.x1 > self.fig.bbox.width + 1 or bb.y1 > self.fig.bbox.height + 1:
                problems.append(f"out of canvas: {t.get_text()!r}")
        for i in range(len(self.free)):
            a = bbox(self.free[i])
            for j in range(i + 1, len(self.free)):
                b = bbox(self.free[j])
                ix = min(a.x1, b.x1) - max(a.x0, b.x0)
                iy = min(a.y1, b.y1) - max(a.y0, b.y0)
                if ix > 2 and iy > 2:
                    problems.append(
                        f"text overlap: {self.free[i].get_text()!r} / {self.free[j].get_text()!r}")

        import numpy as np

        fig = self.fig
        fig.canvas.draw()
        for t in self.free:
            t.set_visible(False)
        fig.canvas.draw()
        buf = np.asarray(fig.canvas.buffer_rgba())
        height = buf.shape[0]
        for t in self.free:
            bb = bbox(t)
            x0, x1 = int(bb.x0) + 2, int(bb.x1) - 1
            y0, y1 = int(height - bb.y1) + 2, int(height - bb.y0) - 1
            region = buf[y0:y1, x0:x1, :3]
            ink = int(((region < 200).any(axis=2)).sum())
            if ink > 4:
                problems.append(f"ink under label: {t.get_text()!r} ({ink} px)")
        for t in self.free:
            t.set_visible(True)

        if DEBUG:
            inv = self.ax.transData.inverted()
            for t in self.free:
                bb = bbox(t)
                (x0, y0), (x1, y1) = inv.transform([[bb.x0, bb.y0], [bb.x1, bb.y1]])
                print(f"  {t.get_text()[:34]!r:38} x {x0:5.2f}-{x1:5.2f}  y {y0:5.2f}-{y1:5.2f}")
        if problems:
            print("\n".join(problems))
            sys.exit(1)
        print(f"ok {path.name} {path.stat().st_size} bytes")


def main() -> None:
    c = Canvas(14.0, 6.3)
    c.text(0.45, 5.92, "三行输入，两个槽位：值没有消失，是挪了位", size=15.0,
           ha="left", weight="bold")
    c.text(0.45, 5.54,
           "_parse_select 在投影之前先读 limit；top 被当成 TOP 词吃掉，其余的词逐个落进槽里。",
           size=10.2, color=INK2, ha="left")

    ys = [4.28, 3.03, 1.78]

    # ---- column headers
    c.text(6.95, ys[0] + 0.62, "projections 投影", size=9.8, weight="bold", mono=False)
    c.text(10.90, ys[0] + 0.62, "exp.Limit(expression, offset)", size=9.8, weight="bold", mono=True)

    # (sql, verdict, verdict color, proj text, expr value, expr face, offset value)
    ROWS = [
        ("SELECT top, x FROM t",
         "安静：两列变零列，x 成了行数", RED,
         "x", BADR, "—"),
        ("SELECT top FROM t",
         "响亮：expression 空着，校验直接失败", INK2,
         "缺失", BADR, "—"),
        ("SELECT TOP(5), x FROM t",
         "安静：5 是跳过数，x 是行数", RED,
         "x", BADR, "5"),
    ]
    label_w, label_h = 2.10, 0.52
    px, ax_, bx = 5.90, 9.30, 10.95
    slot_w = 1.55

    for y, (sql, verdict, vcol, expr_v, expr_face, off_v) in zip(ys, ROWS):
        c.text(4.92, y + 0.03, sql, size=10.2, ha="right", mono=True)
        c.text(4.92, y - 0.44, verdict, size=9.2, ha="right", color=vcol)

        # projections: always empty on this path
        c.box(px, y - label_h / 2, label_w, label_h, BADR, RED_EDGE, 1.4)
        c.text(px + label_w / 2, y, "[]", size=11.0, color=RED, weight="bold", mono=True)

        # expression slot
        c.box(ax_, y - label_h / 2, slot_w, label_h, expr_face, RED_EDGE, 1.4)
        c.text(ax_ + slot_w / 2, y + 0.12, "expression 行数", size=8.2, color=INK2)
        if expr_v == "缺失":
            c.text(ax_ + slot_w / 2, y - 0.13, "缺失", size=10.0, color=RED, weight="bold")
        else:
            c.text(ax_ + slot_w / 2, y - 0.13, expr_v, size=11.0, color=RED, weight="bold", mono=True)

        # offset slot
        off_bad = off_v != "—"
        c.box(bx, y - label_h / 2, slot_w, label_h,
              BADR if off_bad else EMPTYF, RED_EDGE if off_bad else "#c9d2d8", 1.4)
        c.text(bx + slot_w / 2, y + 0.12, "offset 跳过", size=8.2, color=INK2)
        c.text(bx + slot_w / 2, y - 0.13, off_v, size=11.0,
               color=RED if off_bad else MUTED, weight="bold" if off_bad else "normal",
               mono=True)

    # ---- legend
    c.box(0.45, 0.60, 0.30, 0.16, BADR, RED_EDGE, 1.2)
    c.text(0.86, 0.68, "值落错了槽（列名成了行数 / 跳过数，或必填槽空着）", size=9.2,
           color=INK2, ha="left")
    c.box(7.05, 0.60, 0.30, 0.16, EMPTYF, "#c9d2d8", 1.2)
    c.text(7.46, 0.68, "空槽（offset 未用）", size=9.2, color=INK2, ha="left")
    c.text(0.45, 0.24,
           "三行里的 top 本身一处都没有：被当成 TOP 词吃掉，LIMIT 有了词没有值，投影还没开始读。",
           size=9.4, color=INK2, ha="left")

    c.save(HERE / "top-limit-slots.png")


if __name__ == "__main__":
    main()
