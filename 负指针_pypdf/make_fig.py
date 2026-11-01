#!/usr/bin/env python3
"""Draw the negative-startxref map for pypdf #4144.

Top: the 431-byte sample PDF the demo builds, with the two offsets that
matter (the xref table at 256, EOF at 431) and where ``seek(-257)`` lands.
Bottom: one value, three consumers, and the guard that only knows zero.

    python 负指针_pypdf/make_fig.py
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = Path(__file__).resolve().parent
OUT = HERE / "assets" / "startxref-map.png"

FONT = FontProperties(fname=r"C:\Windows\Fonts\msyh.ttc")
FONT_BOLD = FontProperties(fname=r"C:\Windows\Fonts\msyhbd.ttc")

BG = "#FBFAF7"
INK = "#2B2B2B"
MUTED = "#8A867E"
BAD = "#C94F5A"
GOOD = "#3E8E7E"
LINE = "#C9C5BC"

# The sample PDF: 431 bytes, xref table at 256, "startxref" at 411.
FILE_LEN = 431
XREF_AT = 256
NEG = -XREF_AT - 1  # -257


def x_of(value: float) -> float:
    return 100 + (value + 290) * (1200 / 760)


def check_text(fig) -> None:
    """Fail if any label overlaps another or leaves the canvas."""
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
    fig = plt.figure(figsize=(14.0, 8.0), dpi=100, facecolor=BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1400)
    ax.set_ylim(0, 800)
    ax.axis("off")
    ax.set_facecolor(BG)

    # ---- top: the byte axis -------------------------------------------
    y = 650
    ax.text(60, 760, "同样一次读取，指针的两个落点", fontproperties=FONT_BOLD,
            fontsize=16, color=INK, va="top")
    ax.text(60, 728, "样例 PDF 共 431 字节；末尾的 startxref 写着 256，指针落在文件内的 xref 表上",
            fontproperties=FONT, fontsize=10.5, color=MUTED, va="top")

    ax.add_patch(plt.Rectangle((x_of(NEG), y - 9), x_of(0) - x_of(NEG), 18,
                               facecolor=BAD, alpha=0.16, edgecolor="none"))
    ax.plot([x_of(NEG), x_of(FILE_LEN)], [y, y], color=LINE, lw=6, solid_capstyle="butt")
    ax.plot([x_of(0), x_of(FILE_LEN)], [y, y], color="#6F6A60", lw=6, solid_capstyle="butt")
    ax.plot([x_of(0), x_of(0)], [y - 22, y + 40], color=INK, lw=1.4)

    ax.text(x_of(0), y - 28, "0", fontproperties=FONT_BOLD, fontsize=11,
            color=INK, ha="center", va="top")
    ax.text(x_of(XREF_AT), y + 16, "xref 表 @ 256", fontproperties=FONT, fontsize=10.5,
            color=INK, ha="center", va="bottom")
    ax.plot([x_of(XREF_AT), x_of(XREF_AT)], [y + 2, y + 12], color=INK, lw=1.2)
    ax.text(x_of(FILE_LEN), y - 28, "EOF @ 431", fontproperties=FONT, fontsize=10.5,
            color=INK, ha="center", va="top")

    ax.plot([x_of(NEG)], [y], marker="o", markersize=9, color=BAD, zorder=5)
    ax.text(x_of(NEG), y - 28, "seek(−257)", fontproperties=FONT_BOLD, fontsize=11,
            color=BAD, ha="center", va="top")
    ax.annotate("", xy=(x_of(NEG), y - 18), xytext=(x_of(NEG), y + 6),
                arrowprops=dict(arrowstyle="-", color=BAD, lw=1.2))
    ax.text(x_of(NEG) + 16, y + 22, "文件起点之前 257 字节", fontproperties=FONT,
            fontsize=10.5, color=BAD, ha="left", va="bottom")

    ax.text(60, 560,
            "int(b\"-256\") 合法，seek(-256) 也合法；它只是把读取位置放到了文件外面。",
            fontproperties=FONT, fontsize=11, color=MUTED, va="top")

    # ---- bottom: one value, three consumers ---------------------------
    ax.text(60, 500, "同一个值，三个去处", fontproperties=FONT_BOLD,
            fontsize=16, color=INK, va="top")

    read_box = FancyBboxPatch((60, 300), 170, 92, boxstyle="round,pad=2,rounding_size=8",
                              facecolor="#EFECE5", edgecolor=LINE, lw=1.2)
    ax.add_patch(read_box)
    ax.text(145, 360, "read()", fontproperties=FONT_BOLD, fontsize=12.5,
            color=INK, ha="center", va="center")
    ax.text(145, 332, "startxref = −256", fontproperties=FONT, fontsize=10.5,
            color=BAD, ha="center", va="center")

    boxes = [
        (420, 394, "_get_xref_issues()", "if startxref == 0: return 4",
         "seek(startxref - 1)   →   -257", True),
        (420, 286, "_read_xref_tables_and_trailers()", None,
         "seek(startxref)   →   -256", False),
        (420, 178, "self._startxref", None,
         "writer 写 /Prev 时原样带走", False),
    ]

    for bx, by, title, guard, action, has_guard in boxes:
        ax.add_patch(FancyBboxPatch((bx, by), 470, 84,
                                    boxstyle="round,pad=2,rounding_size=8",
                                    facecolor="#FFFFFF", edgecolor=LINE, lw=1.2))
        title_y = by + 66 if guard else by + 56
        action_y = by + 14 if guard else by + 24
        ax.text(bx + 18, title_y, title, fontproperties=FONT_BOLD, fontsize=11.5,
                color=INK, va="center")
        if guard:
            ax.text(bx + 18, by + 36, guard, fontproperties=FONT, fontsize=9.8,
                    color=GOOD, va="center",
                    bbox=dict(boxstyle="round,pad=0.28", facecolor="#EAF3EF",
                              edgecolor=GOOD, lw=1.0))
            ax.text(bx + 238, by + 36, "只挡 0", fontproperties=FONT, fontsize=10,
                    color=GOOD, va="center")
        ax.text(bx + 18, action_y, action, fontproperties=FONT, fontsize=10.5,
                color=BAD, va="center")
        ax.text(bx + 488, by + 42, "×" if "seek" in action else "-256",
                fontproperties=FONT_BOLD, fontsize=15 if "seek" in action else 11,
                color=BAD, ha="left", va="center")

        ax.add_patch(FancyArrowPatch((232, 346), (bx - 6, by + 42),
                                     arrowstyle="-|>", mutation_scale=13,
                                     color=BAD, lw=1.3,
                                     connectionstyle="arc3,rad=0.0"))

    ax.text(60, 120,
            "合并版在 read() 出口把负数归一化为 0，三个去处拿到同一个值；"
            "恢复逻辑仍然走 #3157 已经建立的零路径。",
            fontproperties=FONT, fontsize=11, color=MUTED, va="top")

    fig.text(0.043, 0.032, "样例 PDF 与偏移量来自 negative_startxref_demo/run.py",
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
