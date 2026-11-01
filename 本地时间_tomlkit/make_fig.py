#!/usr/bin/env python3
"""Draw the field/character map for tomlkit #613.

One line of output from ``time.isoformat()``, split into the characters a
TOML Local Time can hold and the offset it cannot.

    python 本地时间_tomlkit/make_fig.py
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

HERE = Path(__file__).resolve().parent
OUT = HERE / "assets" / "local-time-slots.png"

FONT = FontProperties(fname=r"C:\Windows\Fonts\msyh.ttc")
FONT_BOLD = FontProperties(fname=r"C:\Windows\Fonts\msyhbd.ttc")
MONO = FontProperties(fname=r"C:\Windows\Fonts\consola.ttf")

BG = "#FBFAF7"
INK = "#2B2B2B"
MUTED = "#8A867E"
BAD = "#C94F5A"
GOOD = "#3E8E7E"

TEXT = "07:32:00.123450+02:00"
SIZE = 36
X0 = 90
BASE = 210

SEGMENTS = [
    ("hour", 0, 2, INK),
    ("minute", 3, 5, INK),
    ("second", 6, 8, INK),
    ("microsecond", 8, 15, INK),
    ("tzinfo", 15, 21, BAD),
]


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


def main() -> int:
    fig = plt.figure(figsize=(12.0, 3.6), dpi=100, facecolor=BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1200)
    ax.set_ylim(0, 360)
    ax.axis("off")
    ax.set_facecolor(BG)

    ax.text(60, 340, "一行输出，逐字符看它能不能放进 TOML", fontproperties=FONT_BOLD,
            fontsize=16, color=INK, va="top")
    ax.text(60, 312, "Python 的 time.isoformat() 把 tzinfo 渲染成偏移；"
                     "TOML 的 Local Time 没有这一段",
            fontproperties=FONT, fontsize=10.5, color=MUTED, va="top")

    # character advance for Consolas at this size: the width difference
    # between "00" and "0" cancels the side bearing
    probe1 = ax.text(0, -400, "0", fontproperties=MONO, fontsize=SIZE)
    probe2 = ax.text(0, -400, "00", fontproperties=MONO, fontsize=SIZE)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    advance = (probe2.get_window_extent(renderer=renderer).width
               - probe1.get_window_extent(renderer=renderer).width)
    probe1.remove()
    probe2.remove()

    ax.text(X0, BASE, TEXT[:15], fontproperties=MONO, fontsize=SIZE, color=INK,
            va="bottom")
    ax.text(X0 + 15 * advance, BASE, TEXT[15:], fontproperties=MONO, fontsize=SIZE,
            color=BAD, va="bottom")

    # field labels above the string
    for name, start, end, color in SEGMENTS:
        x = X0 + (start + (end - start) / 2) * advance
        ax.text(x, BASE + 58, name, fontproperties=FONT, fontsize=10.5,
                color=color, ha="center", va="bottom")

    # the two spans under the string
    y = BASE - 22
    ax.plot([X0, X0 + 15 * advance], [y, y], color=GOOD, lw=2.4, solid_capstyle="round")
    ax.plot([X0, X0], [y - 7, y + 7], color=GOOD, lw=2.4)
    ax.plot([X0 + 15 * advance, X0 + 15 * advance], [y - 7, y + 7], color=GOOD, lw=2.4)
    ax.plot([X0 + 15 * advance, X0 + 21 * advance], [y, y], color=BAD, lw=2.4,
            solid_capstyle="round")
    ax.plot([X0 + 21 * advance, X0 + 21 * advance], [y - 7, y + 7], color=BAD, lw=2.4)

    ax.text(X0 + 7.5 * advance, y - 16, "TOML Local Time 的槽位：时、分、秒、可选小数秒",
            fontproperties=FONT, fontsize=10.5, color=GOOD, ha="center", va="top")
    ax.text(X0 + 18 * advance, y - 16, "没有槽位", fontproperties=FONT_BOLD, fontsize=10.5,
            color=BAD, ha="center", va="top")

    ax.text(60, 110,
            "要写偏移，只能写成 Offset Date-Time：1979-05-27T07:32:00+02:00",
            fontproperties=FONT, fontsize=11, color=INK, va="top")
    ax.text(60, 84,
            "日期和偏移必须一起出现；单独一个 time 在 TOML 里没有地方放时区。",
            fontproperties=FONT, fontsize=11, color=MUTED, va="top")

    fig.text(0.05, 0.045, "字符串与字段来自 local_time_demo/run.py；语法见 TOML 1.0 Local Time",
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


