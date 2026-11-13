"""Draw the two figures for the null page-box post.

fig 1 (box-fallback.png): the chain /TrimBox -> /CropBox -> /MediaBox with the
emptiness check between the last two links; the parent stops at the null, the
merged revision skips it.

fig 2 (writeback.png): the same page dictionary at three moments, showing that
the resolved rectangle is written back into the key that was *requested*, not
into the key it came from.

Text is placed by hand. Each figure checks that every label stays inside its
own frame, that no label sits on a foreign frame, and that no two labels
overlap. Run with --debug to print measured boxes in data units.
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


class Canvas:
    def __init__(self, w: float, h: float):
        self.w, self.h = w, h
        self.fig = plt.figure(figsize=(w, h), dpi=110)
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, w)
        self.ax.set_ylim(0, h)
        self.ax.axis("off")
        self.groups: list[tuple[FancyBboxPatch, list]] = []
        self.free: list = []

    # ---------------------------------------------------------------- shapes
    def rect(self, x, y, w, h, *, edge=EDGE, face="#ffffff", dashed=False, lw=1.4):
        patch = FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.03,rounding_size=0.06",
            linewidth=lw, edgecolor=edge, facecolor=face,
            linestyle=(0, (4, 2)) if dashed else "solid",
        )
        self.ax.add_patch(patch)
        return patch

    def text(self, x, y, s, *, size=11.0, color=INK, ha="center", va="center", weight="normal"):
        t = self.ax.text(x, y, s, fontsize=size, color=color, ha=ha, va=va, weight=weight)
        self.free.append(t)
        return t

    def arrow(self, x1, y1, x2, y2, *, color=INK2, ls="-"):
        self.ax.add_patch(
            FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=13,
                            linewidth=1.3, color=color, shrinkA=0, shrinkB=0, linestyle=ls)
        )

    def frame(self, x, y, w, h, lines, *, edge=EDGE, face="#ffffff", dashed=False):
        patch = self.rect(x, y, w, h, edge=edge, face=face, dashed=dashed)
        made = []
        n = len(lines)
        for i, (s, sz, col) in enumerate(lines):
            yy = y + h * (n - i) / (n + 1)
            made.append(self.ax.text(x + w / 2, yy, s, fontsize=sz, color=col,
                                     ha="center", va="center"))
        self.groups.append((patch, made))
        return patch, made

    # ---------------------------------------------------------------- checks
    def save(self, path: Path):
        self.fig.savefig(path, facecolor="#ffffff")
        self.fig.canvas.draw()
        renderer = self.fig.canvas.get_renderer()
        inv = self.ax.transData.inverted()

        def bbox(t):
            return t.get_window_extent(renderer=renderer)

        def data_bbox(t):
            bb = bbox(t)
            (x0, y0), (x1, y1) = inv.transform([[bb.x0, bb.y0], [bb.x1, bb.y1]])
            return x0, y0, x1, y1

        all_texts = [t for _, ts in self.groups for t in ts] + self.free
        problems = []
        for t in all_texts:
            bb = bbox(t)
            if bb.x0 < -1 or bb.y0 < -1 or bb.x1 > self.fig.bbox.width + 1 or bb.y1 > self.fig.bbox.height + 1:
                problems.append(f"out of canvas: {t.get_text()!r}")
        for patch, ts in self.groups:
            pb = patch.get_window_extent(renderer=renderer)
            for t in ts:
                tb = bbox(t)
                if tb.x0 < pb.x0 + 2 or tb.x1 > pb.x1 - 2 or tb.y0 < pb.y0 + 2 or tb.y1 > pb.y1 - 2:
                    problems.append(f"label leaves its frame: {t.get_text()!r}")
            for t in all_texts:
                if t in ts:
                    continue
                tb = bbox(t)
                ix = min(tb.x1, pb.x1) - max(tb.x0, pb.x0)
                iy = min(tb.y1, pb.y1) - max(tb.y0, pb.y0)
                if ix > 3 and iy > 3:
                    problems.append(f"label on a foreign frame: {t.get_text()!r}")
        for i in range(len(all_texts)):
            a = bbox(all_texts[i])
            for j in range(i + 1, len(all_texts)):
                b = bbox(all_texts[j])
                ix = min(a.x1, b.x1) - max(a.x0, b.x0)
                iy = min(a.y1, b.y1) - max(a.y0, b.y0)
                if ix > 2 and iy > 2:
                    problems.append(f"text overlap: {all_texts[i].get_text()!r} / {all_texts[j].get_text()!r}")

        # lines/arrows must not run through a label: hide the text and look for ink
        import numpy as np

        fig = self.fig
        fig.canvas.draw()
        for t in all_texts:
            t.set_visible(False)
        fig.canvas.draw()
        buf = np.asarray(fig.canvas.buffer_rgba())
        height = buf.shape[0]
        for t in all_texts:
            bb = bbox(t)
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
                x0, y0, x1, y1 = data_bbox(t)
                print(f"  {t.get_text()[:34]!r:40} x {x0:5.2f}-{x1:5.2f}  y {y0:5.2f}-{y1:5.2f}")
        if problems:
            print("\n".join(problems))
            sys.exit(1)
        print(f"ok {path.name} {path.stat().st_size} bytes")


def fig_chain() -> None:
    c = Canvas(14.0, 4.9)
    c.text(0.38, c.h - 0.34, "同一次读取，停在哪一格", size=14.5, ha="left", weight="bold")

    cy, ch = 2.55, 0.92
    c.frame(0.5, cy, 3.2, ch, [("/TrimBox", 11.5, INK), ("请求：键不存在", 10.0, INK2)])
    c.arrow(3.72, cy + ch / 2, 4.34, cy + ch / 2)
    c.text(4.03, cy + ch / 2 + 0.24, "回退 1", size=9.5, color=INK2)

    c.frame(4.38, cy, 3.2, ch, [("/CropBox", 11.5, RED), ("null", 11.5, RED)],
            edge=RED_EDGE, face=RED_FACE)

    dx, dy = 8.35, cy + ch / 2
    c.ax.add_patch(plt.Polygon([(dx, dy + 0.24), (dx + 0.26, dy), (dx, dy - 0.24), (dx - 0.26, dy)],
                               closed=True, facecolor="#ffffff", edgecolor=INK2, linewidth=1.2))
    c.arrow(7.62, dy, dx - 0.27, dy)
    c.arrow(dx + 0.27, dy, 8.96, dy)
    c.text(dx, cy + ch + 0.36, "判空", size=10.0, color="#33424c")
    c.text(dx, cy + ch + 0.14, "空值算不算“有值”", size=9.5, color=INK2)

    c.frame(8.99, cy, 3.4, ch, [("/MediaBox", 11.5, TEAL), ("[0 0 100 200]", 10.5, TEAL)],
            edge=TEAL_EDGE, face=TEAL_FACE)

    oy, oh = 0.62, 1.12
    c.frame(2.6, oy, 5.2, oh,
            [("修复前：null 通过“不是 None”", 11.0, RED),
             ("break 停在 /CropBox", 10.0, RED),
             ("ValueError: … got NullObject", 9.5, RED)],
            edge=RED_EDGE, face=RED_FACE)
    c.arrow(5.65, cy - 0.01, 5.3, oy + oh)

    c.frame(8.6, oy, 5.15, oh,
            [("修复后：空值被跳过", 11.0, TEAL),
             ("落到 /MediaBox，返回 [0 0 100 200]", 10.0, TEAL),
             ("取值与判空合成一步", 10.0, TEAL)],
            edge=TEAL_EDGE, face=TEAL_FACE)
    c.arrow(10.75, cy - 0.01, 11.35, oy + oh, color=TEAL_EDGE)

    c.save(HERE / "box-fallback.png")


def fig_writeback() -> None:
    c = Canvas(14.0, 4.3)
    c.text(0.38, c.h - 0.32, "写回的是请求的那个键", size=14.0, ha="left", weight="bold")

    cards = [
        (0.5, "打开文件", [("/MediaBox", "[0 0 100 200]", INK), ("/CropBox", "null", RED),
                         ("/TrimBox", "（缺）", INK2)]),
        (5.25, "page.cropbox", [("/MediaBox", "[0 0 100 200]", INK),
                                ("/CropBox", "[0 0 100 200]", TEAL),
                                ("/TrimBox", "（缺）", INK2)]),
        (10.0, "page.trimbox", [("/MediaBox", "[0 0 100 200]", INK),
                                ("/CropBox", "[0 0 100 200]", INK),
                                ("/TrimBox", "[0 0 100 200]", TEAL)]),
    ]
    cw, chh, y0 = 3.55, 2.25, 0.85
    for x, head, rows in cards:
        c.text(x + cw / 2, y0 + chh + 0.24, head, size=11.0, color=INK, weight="bold")
        c.rect(x, y0, cw, chh, edge="#c9d2d8", face=GREY_FACE, lw=1.2)
        for i, (key, val, col) in enumerate(rows):
            yy = y0 + chh - 0.42 - i * 0.62
            c.text(x + 0.2, yy, key, size=10.0, color=INK, ha="left")
            c.text(x + 1.55, yy, val, size=10.0, color=col, ha="left")

    c.arrow(4.1, y0 + chh / 2, 5.2, y0 + chh / 2, color=TEAL_EDGE)
    c.arrow(8.85, y0 + chh / 2, 9.95, y0 + chh / 2, color=TEAL_EDGE)

    c.text(6.55, 0.42, "值来自 /MediaBox，落进 /CropBox", size=9.5, color=TEAL)
    c.text(11.35, 0.42, "回退到 /CropBox 已是数组", size=9.5, color=TEAL)
    c.text(2.3, 0.42, "文件里的原始状态", size=9.5, color=INK2)

    c.save(HERE / "writeback.png")


if __name__ == "__main__":
    fig_chain()
    fig_writeback()


