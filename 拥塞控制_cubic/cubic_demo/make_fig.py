"""重绘 CUBIC 一文的配图。

- ../assets/fig1_ssthresh_two_cuts.png（Pillow）：讲机制——事件后 ssthresh 去了哪里，
  事件前窗口、一次 0.7、0.49 画在同一把尺子上。数字与单元测试断言一致
  （4704/6720/2352→2400/3360）。
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
SCALE = 0.125  # px / byte：9600B → 1200px，三行条共用这一把尺子


def make_fig1() -> Path:
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1600, 1150
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)

    def text(x, y, value, size=28, color=INK, bold=False):
        d.text(
            (x, y),
            value,
            font=ImageFont.truetype(str(FONT_BOLD if bold else FONT), size),
            fill=color,
        )

    def bar(x, y, value, fill, outline, label, lab_color, note=None, note_y=18):
        w = int(value * SCALE)
        d.rounded_rectangle((x, y, x + w, y + 60), radius=10, fill=fill, outline=outline, width=2)
        text(x + 22, y + 12, label, 30, lab_color, bold=True)
        if note:
            text(x + w + 20, y + note_y, note, 23, MUTED)

    M = 120  # 全图统一左边距（文字与条形共用）
    B1, B2, B3, B0 = 224, 478, 604, 6720 * int(SCALE)  # 各行 y 与 6720 的位置
    text(M, 55, "两次削减之后的 ssthresh", 46, bold=True)
    text(M, 122, "quinn 修复前，一次持久拥塞事件过后 ssthresh 落在哪里 · 事件前窗口 9600B（上游回归测试初值）", 27, MUTED)

    text(M, 192, "事件前窗口（两版相同）", 26, MUTED)
    bar(M, 224, 9600, "#e9eef7", BLUE, "9600B（8 × 1200B）", INK)

    text(M, 320, "① 公共路径：乘一次 0.7（两版都走）", 26)
    bar(M, 352, 6720, "#e9eef7", BLUE, "6720B", INK, note="= 0.7 × 9600B")

    text(M, 446, "② 修复后（#2903）：持久拥塞分支不再加削", 26, GREEN)
    bar(M, 478, 6720, "#dcebe4", GREEN, "6720B", GREEN)

    text(M, 572, "③ 修复前：分支又走一遍同一个公式，读到的已是削过的 6720B", 26, RED)
    bar(M, 604, 4704, "#f6e3df", RED, "4704B", RED, note="= 0.7 × 6720B")

    # 6720 的刻度位置：从 ① 条底缘向下引浅灰虚线（与条形右边框错开 12px），
    # ③ 条下方用红线标出 4704 到 6720 的差距，虚线落到红线之上的位置形成 L 形标记
    x6720 = M + int(6720 * SCALE)  # ①② 条右缘 = 6720 的位置
    xr = x6720 + 12                # 虚线 x，避开条形 2px 边框
    for y in range(412, 676, 14):
        d.line((xr, y, xr, min(y + 7, 676)), fill="#b7c4c7", width=2)
    d.line((M + int(4704 * SCALE), 676, xr, 676), fill=RED, width=2)  # ③ 条右缘 → 6720 刻度
    text(M, 708, "差距 2016B：修复前的 ssthresh 比应有的矮 30%", 25, RED, bold=True)

    text(M, 772, "两版 cwnd 都压到最小窗口 2400B（= 2 × 1200B），差别只在 ssthresh。", 24)
    text(M, 822, "小窗口（事件前 4800B）：0.49 × 4800 = 2352 已在最小窗口之下，被钳制顶到 2400B；0.7 × 4800 = 3360B 不受影响。", 24, MUTED)

    text(M, 896, "0.7 × 0.7 = 0.49，不是 0.7", 44, bold=True)
    text(M, 968, "公式和注释单独看都对；错在第二次削减到来时，乘数基准已经从 9600 变成了 6720。", 26, MUTED)

    text(M, 1062, "复现：cargo run --example recovery（cubic_demo） · 出处：quinn 2a9f45e congestion/cubic.rs", 23, MUTED)

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
