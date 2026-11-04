"""Draw the four string forms a single EPUB entry takes.

Run from the topic directory:  python make_fig.py
Output: assets/decode-layers.png
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

INK = "#222222"
MUTED = "#5b5b5b"
RED = "#b3261e"
TEAL = "#0b6b5f"
GREEN = "#2e6b34"
LINE = "#d8d4cc"
PAPER = "#fbfaf7"

OUT = Path(__file__).with_name("assets") / "decode-layers.png"


def box(ax, x, y, w, h, title, lines, edge, title_size=11.5, line_size=9.2):
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.35,rounding_size=1.0",
        linewidth=1.3,
        edgecolor=edge,
        facecolor="white",
        zorder=2,
    )
    ax.add_patch(patch)
    ax.text(
        x + w / 2,
        y + h - 1.8,
        title,
        ha="center",
        va="top",
        fontsize=title_size,
        color=edge,
        weight="bold",
        zorder=3,
    )
    for index, line in enumerate(lines):
        ax.text(
            x + w / 2,
            y + h - 5.3 - index * 3.0,
            line,
            ha="center",
            va="top",
            fontsize=line_size,
            color=INK if index == 0 else MUTED,
            zorder=3,
        )
    return patch


def arrow(ax, start, end, color=MUTED, style="-|>", connection=None):
    patch = FancyArrowPatch(
        start,
        end,
        arrowstyle=style,
        mutation_scale=13,
        linewidth=1.3,
        color=color,
        connectionstyle=connection,
        zorder=1,
    )
    ax.add_patch(patch)


def main() -> None:
    fig, ax = plt.subplots(figsize=(13.2, 7.4), dpi=150)
    fig.patch.set_facecolor(PAPER)
    ax.set_facecolor(PAPER)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    # Main chain: ZIP entry name -> request path -> old / new handling.
    box(ax, 2.5, 70, 24, 20, "ZIP 条目名", ["OEBPS/图片/封面.png", "23 个 UTF-8 字节"], INK)
    box(ax, 34.0, 70, 31, 20, "浏览器请求路径", ["OEBPS/%E5%9B%BE%E7%89%87/", "%E5%B0%81%E9%9D%A2.png", "47 个 ASCII 字符"], INK)

    arrow(ax, (26.8, 80), (33.7, 80))
    ax.text(30.3, 82.2, "编码", ha="center", va="bottom", fontsize=9, color=MUTED)

    box(ax, 7.0, 40, 33, 17, "修前：直接拿 path 查 ZIP", ["字面比较，编码后不等于条目名", "→ 404"], RED)
    box(ax, 55.0, 40, 38, 17, "修后：先 decode_uri_path", ["解出 OEBPS/图片/封面.png", "→ normalize → 200"], TEAL)

    arrow(ax, (44.0, 70), (30.0, 57.4), color=RED, connection="angle,angleA=-90,angleB=0,rad=2")
    arrow(ax, (57.0, 70), (57.0, 57.6), color=TEAL)

    ax.text(28.0, 61.0, "修前：不解码", ha="center", va="bottom", fontsize=9.2, color=RED)
    ax.text(60.0, 60.5, "解码一次", ha="left", va="bottom", fontsize=9.2, color=TEAL)

    # Boundary strip.
    ax.plot([2.5, 97.5], [31.0, 31.0], color=LINE, linewidth=1.0)
    ax.text(2.5, 28.0, "同一层边界上的两次判断", ha="left", va="top", fontsize=10, color=MUTED)

    box(
        ax,
        2.5,
        9.0,
        44.0,
        15.5,
        "save_book_image：不再解码",
        ["renderer 已给出 OEBPS/100%.png（% 已解码）", "再解一次 → 400；到这里为止才是对的"],
        GREEN,
        title_size=10.5,
        line_size=8.8,
    )
    box(
        ax,
        51.0,
        9.0,
        46.5,
        15.5,
        "normalize_entry_path：解码之后",
        ["%2E%2E/secret 先变成 ../secret", "再被拒绝 → 403"],
        TEAL,
        title_size=10.5,
        line_size=8.8,
    )

    fig.tight_layout(pad=0.8)

    # Keep every text box inside the canvas and detect accidental overlaps.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    figure_bbox = fig.bbox
    texts = [text for text in ax.texts if text.get_text().strip()]
    problems = []
    for text in texts:
        bbox = text.get_window_extent(renderer)
        if (
            bbox.x0 < figure_bbox.x0
            or bbox.y0 < figure_bbox.y0
            or bbox.x1 > figure_bbox.x1
            or bbox.y1 > figure_bbox.y1
        ):
            problems.append(f"out of canvas: {text.get_text()!r}")
    for i, left in enumerate(texts):
        for right in texts[i + 1 :]:
            a = left.get_window_extent(renderer)
            b = right.get_window_extent(renderer)
            if a.overlaps(b):
                problems.append(f"overlap: {left.get_text()!r} <> {right.get_text()!r}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, facecolor=fig.get_facecolor())
    plt.close(fig)

    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
    print(f"texts: {len(texts)}")
    if problems:
        for problem in problems:
            print("WARNING:", problem)
        raise SystemExit(1)
    print("text boxes: no overlap, no out-of-canvas")


if __name__ == "__main__":
    main()
