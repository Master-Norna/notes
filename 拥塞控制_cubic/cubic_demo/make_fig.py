"""重绘 CUBIC 一文的配图。

- ../assets/fig1_ssthresh_two_cuts.png（Pillow）：讲机制——事件后 ssthresh 去了哪里，
  事件前窗口、一次 0.7、0.49 画在同一把尺子上。数字与单元测试断言一致
  （9600→6720/4704）。
- ../assets/fig2_recovery.png（matplotlib）：讲后果——持久拥塞事件后两版窗口的
  逐 RTT 轨迹，数据经 `cargo run --example plot_data` 实时导出。

在本目录运行：python make_fig.py
设 CJK_FONT / CJK_FONT_BOLD 可覆盖平台字体路径。
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "Cargo.toml"
ASSETS = HERE.parent / "assets"  # 图存专题根的 assets/
FONT = Path(os.environ.get("CJK_FONT", "C:/Windows/Fonts/msyh.ttc"))
FONT_BOLD = Path(os.environ.get("CJK_FONT_BOLD", str(FONT.with_name("msyhbd.ttc"))))
if not FONT.exists():
    raise SystemExit("Set CJK_FONT to a CJK font (e.g. Noto Sans CJK).")
if not FONT_BOLD.exists():
    FONT_BOLD = FONT

INK, MUTED, LINE = "#202c33", "#59676e", "#d4dbda"
BLUE, GREEN, RED = "#306ca0", "#20725a", "#ad5144"
BG = "#f6f5f0"
SCALE = 0.125  # px / byte：9600B → 1200px，各行条形共用这一把尺子


def make_fig1() -> Path:
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1600, 1200
    M = 120
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    text_boxes = []

    def text(x, y, value, size=28, color=INK, bold=False):
        font = ImageFont.truetype(str(FONT_BOLD if bold else FONT), size)
        box = d.textbbox((x, y), value, font=font, anchor="lt")
        assert M <= box[0] and box[2] <= W - M, (value, box)
        assert 0 <= box[1] and box[3] <= H, (value, box)
        for previous, previous_box in text_boxes:
            overlap = (min(box[2], previous_box[2]) > max(box[0], previous_box[0])
                       and min(box[3], previous_box[3]) > max(box[1], previous_box[1]))
            assert not overlap, (previous, value)
        text_boxes.append((value, box))
        d.text((x, y), value, font=font, fill=color, anchor="lt")
        return box

    def row(label_y, value, fill, outline, label, color=INK, note=None):
        # 行标题、条形和下一行之间均留独立净空；不是靠画布变大后缩小字号。
        bar_y = label_y + 50
        bar_h = 64
        title_box = text(M, label_y, label, 28, color)
        assert bar_y - title_box[3] >= 20
        width = int(value * SCALE)
        d.rounded_rectangle((M, bar_y, M + width, bar_y + bar_h), radius=10,
                            fill=fill, outline=outline, width=2)
        text(M + 22, bar_y + 17, f"{value}B", 32, color, bold=True)
        if note:
            text(M + width + 24, bar_y + 21, note, 25, MUTED)

    text(M, 64, "两次削减之后的 ssthresh", 46, bold=True)
    text(M, 144, "同一尺度对照 · 事件前 cwnd = 9600B · quinn #2903", 28, MUTED)

    row(230, 9600, "#e9eef7", BLUE, "事件前 cwnd（两版相同）")
    row(400, 6720, "#e9eef7", BLUE, "① 公共路径：两版都乘一次 0.7",
        note="= 0.7 × 9600B")
    row(570, 6720, "#dcebe4", GREEN, "② 修复后：分支不再削减", GREEN)
    row(740, 4704, "#f6e3df", RED, "③ 修复前：分支对 6720B 又乘一次 0.7", RED,
        note="= 0.7 × 6720B")

    # 不再叠加跨行虚线、小窗口算例和重复的大公式；小窗口在正文第四节解释。
    text(M, 950, "多出的那次 0.7，让 ssthresh 少了 2016B（30%）。", 32, RED, bold=True)
    text(M, 1020, "两版 cwnd 都压到最小窗口 2400B，差别只在 ssthresh。", 28)
    text(M, 1132, "来源：quinn 2a9f45e · congestion/cubic.rs · cubic_demo", 23, MUTED)

    out = ASSETS / "fig1_ssthresh_two_cuts.png"
    im.save(out)
    print(out)
    return out


def parse_plot_data() -> dict:
    out = subprocess.run(
        ["cargo", "run", "--manifest-path", str(MANIFEST), "--example", "plot_data", "--quiet"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    data: dict[str, dict[str, list[int]]] = {}
    for line in out.splitlines():
        if "\t" not in line:
            continue
        key, val = line.split("\t", 1)
        scene, version = key.split()
        data.setdefault(scene, {})[version] = [int(v) for v in val.split()]
    return data


def make_fig2() -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    for p in (FONT, FONT_BOLD):
        font_manager.fontManager.addfont(str(p))
    plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(FONT)).get_name()

    data = parse_plot_data()
    std, small = data["std"], data["small"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.8, 5.2), dpi=140)
    fig.patch.set_facecolor(BG)

    def style(ax):
        ax.set_facecolor(BG)
        for s in ax.spines.values():
            s.set_color("#b7c4c7")
        ax.tick_params(colors=MUTED, labelsize=11)
        ax.grid(True, color=LINE, linewidth=0.7)

    def curves(ax, series, xs):
        for key, color in (("bug", RED), ("fix", GREEN)):
            ax.plot(xs, series[key], color=color, linewidth=2.2, marker="o", markersize=4.5)

    # 左：标准窗口 9600B
    xs = list(range(13))
    style(ax1)
    curves(ax1, std, xs)
    ax1.axhline(6720, color=GREEN, linestyle="--", linewidth=1.1)
    ax1.axhline(4704, color=RED, linestyle="--", linewidth=1.1)
    ax1.set_yticks(range(2400, 9601, 1200))
    ax1.set_ylim(2000, 11100)
    ax1.set_xlim(-0.4, 13.9)  # 右侧留出一列，承载两句 A 字形结论
    ax1.set_xticks(xs)
    ax1.set_title("标准窗口（事件前 9600B，rtt = 100ms）", fontsize=14, color=INK)
    ax1.set_xlabel("事件后 RTT 数", fontsize=11, color=MUTED)
    ax1.set_ylabel("窗口（字节）", fontsize=11, color=MUTED)
    ax1.text(0.75, 3050, "事件后即时 = 最小窗口 2400B", fontsize=11, color=MUTED)
    ax1.text(5.9, 5100, "停在 4800 四个 RTT", fontsize=11, color=RED)
    ax1.text(1.2, 4000, "ssthresh 4704（修复前）", fontsize=11, color=RED)
    # x=1.4 处绿线正从 4800 斜上至 9600，故此标签从 x=2.6 起（斜线已毕）
    ax1.text(2.6, 7250, "ssthresh 6720（修复后）", fontsize=11, color=GREEN)
    # 两句结论放右侧留白列（数据止于 x=12，此列全空），颜色与各自曲线对应
    ax1.text(13.7, 10350, "修复前 · 12 个 RTT 才回", fontsize=11, color=RED, ha="right")
    ax1.text(13.7, 9950, "修复后 · 2 个 RTT 已回", fontsize=11, color=GREEN, ha="right")

    # 右：小窗口 4800B
    xs2 = list(range(7))
    style(ax2)
    curves(ax2, small, xs2)
    ax2.axhline(2400, color=MUTED, linestyle="dashdot", linewidth=1.1)
    ax2.axhline(3360, color=GREEN, linestyle="--", linewidth=1.1)
    ax2.set_yticks(range(2400, 4801, 600))
    ax2.set_xlim(-0.4, 6.6)
    ax2.set_xticks(xs2)
    ax2.set_title("小窗口（事件前 4800B，最小窗口钳制介入）", fontsize=14, color=INK)
    ax2.set_xlabel("事件后 RTT 数", fontsize=11, color=MUTED)
    ax2.set_ylim(1800, 5480)
    ax2.text(0.3, 1900, "最小窗口 2400B（修复前 ssthresh 被钳到这里）", fontsize=11, color=MUTED)
    ax2.text(0.4, 2870, "ssthresh 3360B（修复后）", fontsize=11, color=GREEN)
    ax2.text(0.95, 3950, "修复前 · 6 个 RTT", fontsize=11, color=RED)
    ax2.text(0.35, 5120, "修复后 · 1 个 RTT", fontsize=11, color=GREEN)

    fig.tight_layout(w_pad=3.0)
    out = ASSETS / "fig2_recovery.png"
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(out)
    return out


if __name__ == "__main__":
    ASSETS.mkdir(exist_ok=True)
    make_fig1()
    make_fig2()
