# -*- coding: utf-8 -*-
"""生成博客配图：层级轮概览 / 顶层环扫描对比 / 触发时间线"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
import numpy as np, os

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

VER = "v7"  # 右下角版本标记，验证管线用
OUT = r"E:\项目\Tset\时间轮_timing_wheel\assets"
os.makedirs(OUT, exist_ok=True)

PAPER = "#fafaf7"
INK = "#2b2b2b"
ACCENT = "#c0392b"
GOOD = "#1e7e4e"
ORANGE = "#d98e04"
MUTED = "#8a8a8a"


def save(fig, name):
    fig.text(0.99, 0.005, VER, ha="right", va="bottom", fontsize=7, color=MUTED, alpha=0.6)
    plt.savefig(OUT + "\\" + name, facecolor=PAPER, bbox_inches="tight")
    plt.close(fig)
    print("saved", name)


# ---------- 图 1：层级轮概览 ----------
fig, ax = plt.subplots(figsize=(9, 6.6), dpi=150)
fig.patch.set_facecolor(PAPER)
ax.set_facecolor(PAPER)
ax.set_xlim(-1.7, 2.1); ax.set_ylim(-3.5, 3.7); ax.axis("off")

levels = [
    ("L0", "槽宽 1ms",    "范围 64ms"),
    ("L1", "槽宽 64ms",   "范围 ~4s"),
    ("L2", "槽宽 ~4s",    "范围 ~4min"),
    ("L3", "槽宽 ~4min",  "范围 ~4hr"),
    ("L4", "槽宽 ~4hr",   "范围 ~12day"),
    ("L5", "槽宽 ~12day", "范围 ~2yr（顶）"),
]
y0, gap, r = 2.35, 0.98, 0.44
for i, (name, sw, rng) in enumerate(levels):
    y = y0 - i * gap
    top = (name == "L5")
    ax.add_patch(plt.Circle((0.75, y), r, fc=ACCENT if top else "#d8d8d2",
                            alpha=0.16 if top else 0.40, ec=ACCENT if top else MUTED,
                            lw=2.2 if top else 1.2, zorder=1))
    for k in range(0, 64, 8):
        a = np.deg2rad(k * 360 / 64)
        ax.plot([0.75 + r * np.cos(a), 0.75 + (r + 0.05) * np.cos(a)],
                [y + r * np.sin(a), y + (r + 0.05) * np.sin(a)],
                color=ACCENT if top else MUTED, lw=1.0, zorder=2)
    ax.text(0.75, y, name, ha="center", va="center", fontsize=12,
            color=ACCENT if top else INK, weight="bold", zorder=3)
    ax.text(-1.6, y + 0.13, name + "  " + sw, ha="left", va="center", fontsize=10.5)
    ax.text(-1.6, y - 0.15, rng, ha="left", va="center", fontsize=9.5, color=MUTED)
    if i < 5:
        ax.annotate("", xy=(0.75, y - gap + r + 0.06), xytext=(0.75, y - r - 0.06),
                    arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=1.2))
ax.text(0.2, 3.5, "tokio-util 时间轮：6 层 × 64 槽，1ms 精度覆盖 ~2 年",
        ha="center", fontsize=13, weight="bold", color=INK)
ax.text(1.42, y0 + 0.1, "顶层 = 伪环形缓冲\n（绕圈，见下）", fontsize=9, color=ACCENT,
        va="center", ha="left")
ax.text(0.2, -3.35, "到期时，上层槽的条目整体下沉（级联）到下一层", ha="center",
        fontsize=9.5, color=MUTED)
save(fig, "fig1_levels.png")

# ---------- 图 2：顶层环扫描对比 ----------
SLOT0 = 90.0
SLOT1 = 90.0 - 30.0


def draw_ring(ax, title, start_slot, result_text, result_color):
    ax.set_facecolor(PAPER)
    ax.set_xlim(-1.6, 1.6); ax.set_ylim(-1.55, 1.90); ax.axis("off")
    r = 1.0
    ax.add_patch(plt.Circle((0, 0), r, fill=False, ec=INK, lw=1.6))
    for k in range(64):
        if k == 0:
            a = np.deg2rad(SLOT0)
        elif k == 1:
            a = np.deg2rad(SLOT1)
        else:
            a = np.deg2rad(SLOT1 - (k - 1) * 4.0)
        lw = 2.6 if k in (0, 1) else 0.8
        col = ACCENT if k == 0 else (ORANGE if k == 1 else MUTED)
        ax.plot([r * np.cos(a), (r + 0.06) * np.cos(a)],
                [r * np.sin(a), (r + 0.06) * np.sin(a)],
                color=col, lw=lw)

    p0 = np.array([r * np.cos(np.deg2rad(SLOT0)), r * np.sin(np.deg2rad(SLOT0))])
    p1 = np.array([r * np.cos(np.deg2rad(SLOT1)), r * np.sin(np.deg2rad(SLOT1))])
    ax.add_patch(plt.Circle(p0, 0.07, fc=ACCENT, ec="none"))
    ax.add_patch(plt.Circle(p1, 0.07, fc=ORANGE, ec="none"))
    ax.annotate("FAR = 2^36+1 ms（~795 天）\n伪环条目 · now 也落在这槽（槽 0）",
                xy=(p0[0] - 0.08, p0[1] - 0.05), xytext=(-1.55, 1.18), fontsize=9.2,
                color=ACCENT, ha="left", va="center",
                arrowprops=dict(arrowstyle="-", color=ACCENT, lw=0.9))
    ax.annotate("NEAR = 2^30+1000 ms（12 天 + 1 秒）",
                xy=(p1[0] + 0.06, p1[1] + 0.03), xytext=(1.55, 1.82), fontsize=9.2,
                color=ORANGE, ha="right", va="center",
                arrowprops=dict(arrowstyle="-", color=ORANGE, lw=0.9))

    ps = p0 if start_slot == 0 else p1
    col = result_color
    a_out = np.deg2rad(SLOT0 if start_slot == 0 else SLOT1)
    c = ps + 0.16 * np.array([np.cos(a_out), np.sin(a_out)])
    ax.add_patch(plt.Circle(c, 0.10, fill=False, ec=col, lw=2.4))
    arr = FancyArrowPatch(c + np.array([0.10, 0.02]), c + np.array([0.03, -0.08]),
                          arrowstyle="-|>", mutation_scale=15, color=col, lw=2.4)
    ax.add_patch(arr)
    ax.text(0, 0.30, "扫描从这开始\n→ 立刻命中", fontsize=9.0, color=col,
            weight="bold", ha="center", va="center")

    ax.set_title(title, fontsize=12.5, weight="bold", color=INK)
    ax.text(0, -1.32, result_text, ha="center", va="top", fontsize=9.6,
            color=result_color)
    ax.text(0, 1.86, "槽间距为示意（实际相邻槽 5.6°）", ha="right",
            fontsize=8.2, color=MUTED)


fig, axes = plt.subplots(1, 2, figsize=(12.5, 6.0), dpi=150)
fig.patch.set_facecolor(PAPER)
draw_ring(axes[0], "buggy（无 +1）：扫描从槽 0 开始", 0,
          "命中 FAR → deadline 被修正 +2^36 → poll_at = 795 天后（顶层一整圈）", ACCENT)
draw_ring(axes[1], "fixed（含 +1）：扫描从槽 1 开始", 1,
          "命中 NEAR → poll_at = 12 天后（NEAR 准点触发）", GOOD)
save(fig, "fig2_ring_scan.png")

# ---------- 图 3：触发时间线 ----------
fig, ax = plt.subplots(figsize=(11.5, 4.6), dpi=150)
fig.patch.set_facecolor(PAPER); ax.set_facecolor(PAPER)
ax.set_xlim(-60, 880); ax.set_ylim(-1.55, 2.15)
ax.axhline(0, color=INK, lw=1.4)
for d, lab, dy in [(0, "0", -0.32), (12, "12天", 0.30),
                   (795, "795天（顶层一整圈）", -0.32), (807, "807天", 0.30)]:
    ax.plot([d, d], [-0.05, 0.05], color=INK, lw=1.2)
    ax.text(d, dy, lab, ha="center", fontsize=9, color=MUTED)
ax.set_yticks([]); ax.set_xticks([])

ax.text(-4, 1.55, "fixed", fontsize=11, weight="bold", color=GOOD, ha="right")
ax.plot([0, 795], [1.55, 1.55], color=GOOD, lw=1.6, alpha=0.35)
ax.plot([12], [1.55], "o", color=GOOD, ms=9)
ax.text(45, 1.72, "NEAR 准点（12天+1秒）", ha="left", fontsize=9, color=GOOD)
ax.plot([795], [1.55], "o", color=GOOD, ms=9)
ax.text(795, 1.72, "FAR 准点（795天）", ha="center", fontsize=9, color=GOOD)

ax.text(-4, 0.72, "buggy", fontsize=11, weight="bold", color=ACCENT, ha="right")
ax.plot([0, 807], [0.72, 0.72], color=ACCENT, lw=1.6, alpha=0.35)
ax.plot([795], [0.72], "o", color=ACCENT, ms=9)
ax.text(795, 0.88, "FAR 准点", ha="left", fontsize=9, color=ACCENT)
ax.plot([807], [0.72], "o", color=ACCENT, ms=9)
ax.text(807, 0.50, "NEAR 才触发", ha="right", fontsize=9, color=ACCENT)

ax.plot([12], [0.72], "x", color=MUTED, ms=10, mew=1.8)
ax.plot([12, 12], [0.66, -0.16], color=MUTED, lw=0.9, ls=":")
ax.text(30, -0.14, "本应在这（12天）", ha="left", fontsize=8.6, color=MUTED)
ax.annotate("", xy=(806, 0.22), xytext=(12, 0.22),
            arrowprops=dict(arrowstyle="<->", color=ACCENT, lw=1.4))
ax.text(409, 0.30, "NEAR 被推迟整整一圈（795 天）—— pgdog 事故里的“挂起”",
        ha="center", fontsize=9.8, color=ACCENT)
ax.set_title("同一组 timer，两种实现的触发时刻（release 实测）",
             fontsize=12.5, weight="bold", color=INK)
save(fig, "fig3_timeline.png")

print("all saved, VER =", VER)
