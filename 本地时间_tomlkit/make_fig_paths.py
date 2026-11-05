#!/usr/bin/env python3
"""Draw the three write paths of a tomlkit ``Time``.

Which paths re-render ``raw`` (item / _new) and which one copies it verbatim
(parse -> dumps). Same palette and checks as ``make_fig.py``.

    python 本地时间_tomlkit/make_fig_paths.py
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = Path(__file__).resolve().parent
OUT = HERE / "assets" / "three-paths.png"

FONT = FontProperties(fname=r"C:\Windows\Fonts\msyh.ttc")
FONT_BOLD = FontProperties(fname=r"C:\Windows\Fonts\msyhbd.ttc")
MONO = FontProperties(fname=r"C:\Windows\Fonts\consola.ttf")

BG = "#FBFAF7"
INK = "#2B2B2B"
MUTED = "#8A867E"
BAD = "#C94F5A"
GOOD = "#3E8E7E"
LINE = "#D9D4CA"

W, H = 1400, 620


def check_text(fig) -> None:
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    width, height = fig.canvas.get_width_height()
    boxes = []
    for ax in fig.axes:
        for text in ax.texts:
            if not text.get_text().strip():
                continue
            patch = text.get_bbox_patch()
            if patch is not None:
                boxes.append((text.get_text(), patch.get_window_extent(renderer=renderer)))
            else:
                boxes.append((text.get_text(), text.get_window_extent(renderer=renderer)))
    for text in fig.texts:
        if text.get_text().strip():
            boxes.append((text.get_text(), text.get_window_extent(renderer=renderer)))

    problems = []
    for i, (name, box) in enumerate(boxes):
        if box.x0 < -1 or box.y0 < -1 or box.x1 > width + 1 or box.y1 > height + 1:
            problems.append(f"越界: {name!r} -> {box}")
        for other_name, other in boxes[i + 1:]:
            overlap_w = min(box.x1, other.x1) - max(box.x0, other.x0)
            overlap_h = min(box.y1, other.y1) - max(box.y0, other.y0)
            if overlap_w > 1.5 and overlap_h > 1.5:
                problems.append(
                    f"重叠: {name!r} / {other_name!r} ({overlap_w:.1f}x{overlap_h:.1f})"
                )
    if problems:
        raise SystemExit("figure check failed:\n" + "\n".join(problems))


def box(ax, x0, y0, x1, y1, color=LINE, fill="#FFFFFF"):
    ax.add_patch(
        FancyBboxPatch(
            (x0, y0), x1 - x0, y1 - y0,
            boxstyle="round,pad=0,rounding_size=10",
            linewidth=1.0, edgecolor=color, facecolor=fill,
        )
    )


def arrow(ax, x0, x1, y, color):
    ax.add_patch(
        FancyArrowPatch(
            (x0, y), (x1, y), arrowstyle="-|>", mutation_scale=14,
            linewidth=1.6, color=color, shrinkA=0, shrinkB=0,
        )
    )


def main() -> int:
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor=BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")
    ax.set_facecolor(BG)

    ax.text(60, H - 34, "同一个 time，三条写出去的路径", fontproperties=FONT_BOLD,
            fontsize=17, color=INK, va="top")
    ax.text(60, H - 66, "前两条从 Python 对象现场渲染 raw；第三条把读进来的原文原样写回去",
            fontproperties=FONT, fontsize=11, color=MUTED, va="top")

    rows = [
        ("item(t)", "_format_time(t)", "t = 07:32:00", "t = 07:32:00+02:00"),
        ("Time._new()\nreplace() 走这里", "_format_time(r)", "t = 13:32:00", "t = 13:32:00+02:00"),
        ("parse() 得到的 Time\n带着原文 raw", "dumps()", "t = 07:32:00.123450", "t = 07:32:00.123450"),
    ]

    top = H - 130
    row_h = 128
    for index, (left, mid, good, bad) in enumerate(rows):
        y1 = top - index * row_h
        y0 = y1 - 96
        # 入口
        box(ax, 60, y0, 300, y1)
        ax.text(180, (y0 + y1) / 2, left, fontproperties=FONT, fontsize=12,
                color=INK, ha="center", va="center", linespacing=1.5)
        arrow(ax, 306, 356, (y0 + y1) / 2, MUTED)
        # 处理
        box(ax, 362, y0, 700, y1, color=LINE)
        ax.text(531, (y0 + y1) / 2, mid, fontproperties=MONO, fontsize=14,
                color=INK, ha="center", va="center")
        arrow(ax, 706, 756, (y0 + y1) / 2, MUTED)
        # 结果
        box(ax, 762, y0, 1180, y1, color=LINE)
        if index < 2:
            ax.text(971, (y0 + y1) / 2 + 18, good, fontproperties=MONO, fontsize=15,
                    color=GOOD, ha="center", va="center")
            ax.text(971, (y0 + y1) / 2 - 22, bad, fontproperties=MONO, fontsize=15,
                    color=BAD, ha="center", va="center")
            ax.text(1210, (y0 + y1) / 2 + 18, "修后", fontproperties=FONT, fontsize=10.5,
                    color=GOOD, va="center")
            ax.text(1210, (y0 + y1) / 2 - 22, "修前", fontproperties=FONT, fontsize=10.5,
                    color=BAD, va="center")
        else:
            ax.text(971, (y0 + y1) / 2, good, fontproperties=MONO, fontsize=15,
                    color=INK, ha="center", va="center")
            ax.text(1210, (y0 + y1) / 2, "两版相同", fontproperties=FONT, fontsize=10.5,
                    color=MUTED, va="center")

    ax.text(60, 74,
            "tzinfo 留在 Python 对象上，不进文本；要带上偏移，只能写成带日期的 Offset Date-Time。",
            fontproperties=FONT, fontsize=11.5, color=INK, va="top")
    fig.text(0.043, 0.045,
             "三行输出与 local_time_demo/run.py 的 boundary cases 一致",
             fontproperties=FONT, fontsize=9.5, color=MUTED, ha="left", va="bottom")

    out = OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    check_text(fig)
    fig.savefig(out, facecolor=BG)
    plt.close(fig)
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
