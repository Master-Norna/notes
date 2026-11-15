"""Draw the figure for the pypdf image-buffer post.

fig 1 (release-7.0.1.png) is a screenshot of the GitHub release card, cropped
by .草稿/crop_release.py -- not drawn here.

fig 2 (limit-vs-actual.png): six images, one 75 MB limit.  The grey bar is what
`pixel_count * len(mode)` recorded; the red bar is what Pillow actually asked
the allocator for.  Whether the grey bar sits left or right of the limit line
is the old verdict; how far the red bar runs past it is the consequence.

Every number comes from image_buffer_demo/run.py --test --mem.

Text is placed by hand.  The figure checks that every label stays inside the
canvas, that no two labels overlap, and that no rule runs through a label.
Run with --debug to print measured boxes in data units.
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
GREY = "#c3ccd3"
LIMIT = 75_000_000
X_MAX = 300_000_000
X0, X1 = 2.62, 12.72          # data columns for 0 .. X_MAX

ROWS = [
    ("I  ·  25 Mpx", 25_000_000, 100_000_000),
    ("RGB  ·  25 Mpx", 75_000_000, 100_000_000),
    ("LA  ·  30 Mpx", 60_000_000, 120_000_000),
    ("YCbCr  ·  16 Mpx", 80_000_000, 64_000_000),
    ("I;16  ·  20 Mpx", 80_000_000, 40_000_000),
    ("I  ·  8000×8000", 64_000_000, 256_589_824),
]


def xpos(v: float) -> float:
    return X0 + v / X_MAX * (X1 - X0)


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

    def save(self, path: Path):
        self.fig.savefig(path, facecolor="#ffffff")
        self.fig.canvas.draw()
        renderer = self.fig.canvas.get_renderer()
        inv = self.ax.transData.inverted()

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

        # rules and bars must not run through a label
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
            for t in self.free:
                bb = bbox(t)
                (x0, y0), (x1, y1) = inv.transform([[bb.x0, bb.y0], [bb.x1, bb.y1]])
                print(f"  {t.get_text()[:34]!r:38} x {x0:5.2f}-{x1:5.2f}  y {y0:5.2f}-{y1:5.2f}")
        if problems:
            print("\n".join(problems))
            sys.exit(1)
        print(f"ok {path.name} {path.stat().st_size} bytes")


def millions(v: int) -> str:
    if v >= 100_000_000 and v % 1_000_000 == 0:
        return f"{v // 1_000_000} M"
    if v % 1_000_000 == 0:
        return f"{v // 1_000_000} M"
    return f"{v:,}"


def fig_limit() -> None:
    c = Canvas(14.0, 6.6)
    c.text(0.45, 6.22, "一条 75 MB 的线，六种图站在哪一边", size=15.0, ha="left", weight="bold")
    c.text(0.45, 5.86,
           "_validate_image_size() 只比一个数；灰条是它记的数，红条是 Pillow 真正要的内存。",
           size=10.2, color=INK2, ha="left")

    top = 5.42
    gap = 0.80
    ys = [top - i * gap for i in range(len(ROWS))]

    # ---- limit line and scale
    lx = xpos(LIMIT)
    c.ax.plot([lx, lx], [ys[-1] - 0.52, ys[0] + 0.42], color=EDGE, lw=1.4,
              linestyle=(0, (5, 3)), zorder=1)
    c.text(lx, ys[0] + 0.62, "上限 75,000,000", size=10.2, color=EDGE, weight="bold")

    for y, (name, recorded, actual) in zip(ys, ROWS):
        c.text(X0 - 0.22, y + 0.03, name, size=10.0, color=INK, ha="right", mono=True)

        # recorded bar (upper) -- what the old code believed
        w_rec = xpos(recorded) - X0
        c.ax.add_patch(Rectangle((X0, y + 0.09), w_rec, 0.115, facecolor=GREY,
                                 edgecolor="none", zorder=2))
        # actual bar (lower) -- what Pillow allocates
        w_act = xpos(actual) - X0
        c.ax.add_patch(Rectangle((X0, y - 0.20), w_act, 0.15, facecolor=RED_EDGE,
                                 edgecolor="none", zorder=2))

        # numbers at the bar ends, inside when they would fall off the canvas
        rec_txt = millions(recorded)
        act_txt = millions(actual)
        rx = X0 + w_rec
        rec_inside = rx > X1 - 0.62
        c.text(rx - 0.06 if rec_inside else rx + 0.08, y + 0.15, rec_txt,
               size=8.6, color="#4a555d" if rec_inside else "#6d777e",
               ha="right" if rec_inside else "left", mono=True)

        ax_ = X0 + w_act
        act_inside = ax_ > X1 - 0.72
        c.text(ax_ - 0.06 if act_inside else ax_ + 0.08, y - 0.13, act_txt,
               size=9.0, color="#f6e9e6" if act_inside else RED,
               ha="right" if act_inside else "left", mono=True,
               weight="bold")

    # ---- verdicts, right of the numbers
    vx = 13.02
    verdicts = [
        ("放行", "低估 4 倍", RED),
        ("放行", "踩线", RED),
        ("放行", "低估 2 倍", RED),
        ("拒绝", "其实够用", INK2),
        ("拒绝", "其实够用", INK2),
        ("放行", "上限的 3.4 倍", RED),
    ]
    for y, (v, note, col) in zip(ys, verdicts):
        c.text(vx, y + 0.15, v, size=9.4, color=col, ha="left")
        c.text(vx, y - 0.10, note, size=8.6, color=col, ha="left")

    # ---- legend
    ly = 0.62
    c.ax.add_patch(Rectangle((0.47, ly - 0.05), 0.42, 0.10, facecolor=GREY, edgecolor="none"))
    c.text(1.00, ly, "len(mode) 算出来的", size=9.4, color="#5b6b77", ha="left")
    c.ax.add_patch(Rectangle((3.30, ly - 0.06), 0.42, 0.12, facecolor=RED_EDGE, edgecolor="none"))
    c.text(3.84, ly, "Pillow 实际分配", size=9.4, color=RED, ha="left")
    c.text(6.30, ly, "灰条在左就放行；#4374 之后灰条改用 Pillow 的字节数，两根条一样长。",
           size=9.4, color=INK2, ha="left")

    c.save(HERE / "limit-vs-actual.png")


if __name__ == "__main__":
    fig_limit()
