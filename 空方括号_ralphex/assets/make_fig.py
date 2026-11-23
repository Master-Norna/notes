"""Draw two-paths.png for the ralphex empty-brackets post.

One plan file, two readings, one verdict method.  With task sections the
gate walks the parsed tasks; with zero tasks it scans the file line by
line.  The two routes never run in the same pass, but each checkbox goes
through the same predicate and both end in Checkbox.IsActionable(), whose
single regex is where `[]string` gets read as a format example.

Names and expressions are quoted from pkg/processor/phase/task.go and
pkg/plan/parse.go at the merge commit 904f2302.

Text is placed by hand.  The figure checks that every label stays inside
the canvas, that no two labels overlap, that no rule runs through a label,
and that the boxes do not overlap each other.  Run with --debug to print
measured boxes in data units.
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
MUTED = "#8b959d"
RULE = "#aab4bb"
EDGE = "#3d4a54"
RED, RED_EDGE, RED_FACE = "#8e2a20", "#b23a2e", "#fdf2f0"
FACE = "#fbfcfd"
MONO = ["Consolas", "DejaVu Sans Mono"]


class Canvas:
    def __init__(self, w: float, h: float):
        self.w, self.h = w, h
        self.fig = plt.figure(figsize=(w, h), dpi=110)
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, w)
        self.ax.set_ylim(0, h)
        self.ax.axis("off")
        self.free: list = []
        self.rects: list[tuple[str, tuple[float, float, float, float]]] = []

    def text(self, x, y, s, *, size=10.0, color=INK, ha="left", va="center",
             mono=False):
        t = self.ax.text(x, y, s, fontsize=size, color=color, ha=ha, va=va,
                         family=MONO if mono else plt.rcParams["font.family"])
        self.free.append(t)
        return t

    def box(self, name, x, y, w, h, face=FACE, edge=EDGE, lw=1.2, nested=False):
        self.ax.add_patch(FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.02,rounding_size=0.06",
            linewidth=lw, edgecolor=edge, facecolor=face, zorder=1,
        ))
        if not nested:
            self.rects.append((name, (x, y, w, h)))

    def line(self, x1, y1, x2, y2, *, color=EDGE, lw=1.4):
        self.ax.plot([x1, x2], [y1, y2], color=color, lw=lw,
                     solid_capstyle="round", zorder=3)

    def arrow(self, x1, y1, x2, y2, *, color=EDGE, lw=1.4):
        self.ax.add_patch(FancyArrowPatch(
            (x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=11,
            linewidth=lw, color=color, shrinkA=0, shrinkB=0, zorder=3,
        ))

    def save(self, path: Path):
        self.fig.savefig(path, facecolor="#ffffff")
        self.fig.canvas.draw()
        renderer = self.fig.canvas.get_renderer()

        def bbox(t):
            return t.get_window_extent(renderer=renderer)

        problems = []
        for t in self.free:
            bb = bbox(t)
            if bb.x0 < -1 or bb.y0 < -1 or bb.x1 > self.fig.bbox.width + 1 \
                    or bb.y1 > self.fig.bbox.height + 1:
                problems.append(f"out of canvas: {t.get_text()!r}")
        for i in range(len(self.free)):
            a = bbox(self.free[i])
            for j in range(i + 1, len(self.free)):
                b = bbox(self.free[j])
                ix = min(a.x1, b.x1) - max(a.x0, b.x0)
                iy = min(a.y1, b.y1) - max(a.y0, b.y0)
                if ix > 2 and iy > 2:
                    problems.append(
                        f"text overlap: {self.free[i].get_text()!r} / "
                        f"{self.free[j].get_text()!r}")
        for i in range(len(self.rects)):
            ni, (xi, yi, wi, hi) = self.rects[i]
            for j in range(i + 1, len(self.rects)):
                nj, (xj, yj, wj, hj) = self.rects[j]
                ix = min(xi + wi, xj + wj) - max(xi, xj)
                iy = min(yi + hi, yj + hj) - max(yi, yj)
                if ix > 0 and iy > 0:
                    problems.append(f"box overlap: {ni} / {nj}")

        import numpy as np

        self.fig.canvas.draw()
        for t in self.free:
            t.set_visible(False)
        self.fig.canvas.draw()
        buf = np.asarray(self.fig.canvas.buffer_rgba())
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
                (x0, y0), (x1, y1) = inv.transform(
                    [[bb.x0, bb.y0], [bb.x1, bb.y1]])
                print(f"  {t.get_text()[:36]!r:40} x {x0:5.2f}-{x1:5.2f}"
                      f"  y {y0:5.2f}-{y1:5.2f}")

        # text whose centre sits inside a box must fit inside that box
        inv = self.ax.transData.inverted()
        for t in self.free:
            bb = bbox(t)
            (x0, y0), (x1, y1) = inv.transform([[bb.x0, bb.y0], [bb.x1, bb.y1]])
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            for name, (bx, by, bw, bh) in self.rects:
                if bx < cx < bx + bw and by < cy < by + bh:
                    if x0 < bx + 0.05 or x1 > bx + bw - 0.05 \
                            or y0 < by + 0.02 or y1 > by + bh - 0.02:
                        problems.append(
                            f"text escapes {name}: {t.get_text()!r}")

        if problems:
            print("\n".join(problems))
            sys.exit(1)
        print(f"ok {path.name} {path.stat().st_size} bytes")


def main() -> None:
    c = Canvas(11.6, 7.2)

    c.text(0.45, 6.86, "两条路，同一道判定", size=16.5)
    c.text(0.45, 6.48,
           "完成门读同一份计划有两条路：有任务节时逐个任务看，零任务节时逐行扫文件。",
           size=10.4, color=INK2)
    c.text(0.45, 6.20,
           "两条路不会同时走，可是每个框最后都交给同一个方法判断。",
           size=10.4, color=INK2)

    # ---- the one input ---------------------------------------------------
    c.box("plan", 0.45, 3.05, 1.90, 1.22)
    c.text(0.72, 4.00, "计划文件", size=9.8)
    c.text(0.72, 3.66, "plan.md", size=8.8, color=INK2, mono=True)
    c.text(0.72, 3.30, "两种读法", size=9.0, color=INK2)

    # ---- the fork --------------------------------------------------------
    c.line(2.37, 3.66, 2.72, 3.66)
    c.line(2.72, 2.47, 2.72, 4.87)
    c.arrow(2.72, 4.87, 3.02, 4.87)
    c.arrow(2.72, 2.47, 3.02, 2.47)

    # ---- route A: parsed tasks ------------------------------------------
    c.text(3.05, 5.82, "① 有任务节", size=9.8, color=INK2)
    c.text(3.90, 5.82, "len(parsed.Tasks) > 0", size=9.2, color=MUTED, mono=True)
    c.box("A", 3.05, 4.12, 3.75, 1.50)
    c.text(3.32, 5.26, "Task.HasUncompletedActionableWork()", size=9.6, mono=True)
    c.text(3.32, 4.86, "只看任务节里解析出的框", size=9.4, color=INK2)
    c.text(3.32, 4.38, "!cb.Checked && cb.IsActionable()", size=9.4, mono=True)

    # ---- route B: whole-file scan ---------------------------------------
    c.text(3.05, 3.42, "② 零任务节", size=9.8, color=INK2)
    c.text(3.90, 3.42, "len(parsed.Tasks) == 0", size=9.2, color=MUTED, mono=True)
    c.box("B", 3.05, 1.72, 3.75, 1.50)
    c.text(3.32, 2.86, "FileHasUncompletedCheckbox(path)", size=9.6, mono=True)
    c.text(3.32, 2.46, "整份文件逐行扫，围栏里的行跳过", size=9.4, color=INK2)
    c.text(3.32, 1.98, "!cb.Checked && cb.IsActionable()", size=9.4, mono=True)

    # ---- both routes reach the same method ------------------------------
    c.arrow(6.84, 4.87, 7.25, 4.87)
    c.arrow(6.84, 2.47, 7.25, 2.47)

    c.box("IsActionable", 7.25, 1.72, 3.90, 3.90)
    c.text(7.55, 5.26, "Checkbox.IsActionable()", size=10.4, color=RED, mono=True)
    c.text(7.55, 4.86, "return !formatInText.MatchString(cb.Text)",
           size=8.6, color=INK2, mono=True)
    c.box("regex", 7.55, 4.14, 1.72, 0.47, face=RED_FACE, edge=RED_EDGE, lw=1.1,
          nested=True)
    c.text(8.41, 4.375, r"\[\s*[ xX]?\s*\]", size=9.2, ha="center", mono=True)
    c.text(7.55, 3.84, "问号在这里：字符类可以整格不出现", size=9.0, color=INK2)
    c.line(7.50, 3.50, 10.90, 3.50, color=RULE, lw=0.9)

    c.text(7.55, 3.06, "[]string", size=9.6, mono=True)
    c.text(8.36, 3.06, "命中 →", size=9.2)
    c.text(9.22, 3.06, "false", size=10.6, color=RED, mono=True)
    c.text(7.55, 2.50, "框还没勾，但已经不算任务了", size=9.2, color=INK2)
    c.text(7.55, 2.02, "兜底就算跑起来，问的也是这一格", size=9.2, color=INK2)

    # ---- what the gate prints -------------------------------------------
    c.arrow(9.20, 1.66, 9.20, 1.46)
    c.text(9.36, 1.56, "两条路都返回 false", size=8.6, color=INK2)

    c.box("band", 0.45, 0.52, 10.70, 0.90, face=RED_FACE, edge=RED_EDGE, lw=1.1)
    c.text(0.75, 1.14, "all tasks completed, starting code review...",
           size=9.6, mono=True)
    c.text(0.75, 0.78, "TaskPhase.Run 收到完成信号后打印的就是这一行",
           size=8.8, color=INK2)
    c.text(4.95, 1.14, "计划里这行没动过：", size=8.8, color=INK2)
    c.text(6.45, 1.14, "- [ ] convert []string to []T ...", size=8.4, mono=True)
    c.text(4.95, 0.78, "它还是未勾，code review 已经开始", size=8.8, color=INK2)

    c.save(HERE / "two-paths.png")


if __name__ == "__main__":
    main()
