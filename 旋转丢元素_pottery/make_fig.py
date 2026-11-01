#!/usr/bin/env python3
"""Draw the 9 x 41 case matrix for Pottery #857.

Every cell is one (length, n) pair from ``rotate_demo/run.py --matrix``.
Red marks a result that differs from ``collections.deque.rotate``.

    python 旋转丢元素_pottery/make_fig.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Rectangle

HERE = Path(__file__).resolve().parent
MATRIX = HERE.parent / ".yan" / "pottery-rotate" / "runs" / "matrix.json"
OUT = HERE / "assets" / "rotate-matrix.png"

FONT = FontProperties(fname=r"C:\Windows\Fonts\msyh.ttc")
FONT_BOLD = FontProperties(fname=r"C:\Windows\Fonts\msyhbd.ttc")

BG = "#FBFAF7"
INK = "#2B2B2B"
MUTED = "#8A867E"
BAD = "#C94F5A"
NEUTRAL = "#DEDBD3"
GOOD = "#4E9C88"

LENGTHS = list(range(9))
STEPS = list(range(-20, 21))
CELL = 21
GAP = 3
LEFT = 52
TOP = 46


def draw(ax, cells, mismatch_is_red: bool, title: str, subtitle: str) -> None:
    ax.set_xlim(0, LEFT + len(STEPS) * (CELL + GAP) + 8)
    ax.set_ylim(0, TOP + len(LENGTHS) * (CELL + GAP) + 62)
    ax.axis("off")
    ax.set_facecolor(BG)

    ax.text(0, ax.get_ylim()[1] - 10, title, fontproperties=FONT_BOLD,
            fontsize=15, color=INK, va="top")
    ax.text(0, ax.get_ylim()[1] - 36, subtitle, fontproperties=FONT,
            fontsize=10.5, color=MUTED, va="top")

    by_key = {(c["length"], c["n"]): c["match"] for c in cells}
    for row, length in enumerate(LENGTHS):
        y = TOP + (len(LENGTHS) - 1 - row) * (CELL + GAP)
        ax.text(LEFT - 10, y + CELL / 2, str(length), fontproperties=FONT,
                fontsize=10, color=MUTED, ha="right", va="center")
        for col, n in enumerate(STEPS):
            match = by_key[(length, n)]
            if mismatch_is_red:
                color = NEUTRAL if match else BAD
            else:
                color = GOOD
            x = LEFT + col * (CELL + GAP)
            ax.add_patch(Rectangle((x, y), CELL, CELL, facecolor=color,
                                   edgecolor="none", linewidth=0))

    base = TOP - 16
    for col, n in enumerate(STEPS):
        if n % 5 == 0:
            x = LEFT + col * (CELL + GAP) + CELL / 2
            ax.text(x, base, str(n), fontproperties=FONT, fontsize=9.5,
                    color=MUTED, ha="center", va="top")
    ax.text(LEFT + len(STEPS) * (CELL + GAP) / 2, base - 20, "n（步数）",
            fontproperties=FONT, fontsize=10.5, color=INK, ha="center", va="top")
    ax.text(14, TOP + len(LENGTHS) * (CELL + GAP) / 2, "len", fontproperties=FONT,
            fontsize=10.5, color=INK, rotation=90, ha="center", va="center")


def check_text(fig) -> None:
    """Fail if any label overlaps another or leaves the canvas."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    width, height = fig.canvas.get_width_height()
    boxes = []
    for ax in fig.axes:
        for text in ax.texts:
            if text.get_text().strip():
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


def main() -> int:
    data = json.loads(MATRIX.read_text(encoding="utf-8"))
    fig = plt.figure(figsize=(12.0, 6.6), dpi=100, facecolor=BG)
    ax1 = fig.add_axes([0.02, 0.535, 0.96, 0.44])
    ax2 = fig.add_axes([0.02, 0.075, 0.96, 0.44])

    draw(
        ax1,
        data["parent"],
        True,
        "修前 f6e59b0：204 / 369 格与 collections.deque 不符",
        "红格是结果对不上的用例；灰格表示一致",
    )
    draw(
        ax2,
        data["merge"],
        False,
        "合并版 4e98b44：0 / 369 格不符",
        "同一组输入、同一后端，全部与 collections.deque 一致",
    )

    fig.text(0.02, 0.035,
             "每格 = 一个 (len, n) 用例，len 0–8，n −20–20；数据来自 "
             "rotate_demo/run.py --matrix",
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
