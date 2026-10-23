"""Plot the measured error growth of the single-pass variance formula.

Reads `out/curve.csv` (written by `cargo run --release`) and writes
`../assets/fig1_variance_error.png`.

Each sample is 64 values a..a+63 with a = 10^t * (1 + j/16); its true population
variance is (64^2 - 1) / 12 = 341.25.
"""

import csv
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE = Path(__file__).resolve().parent
CSV = HERE / "out" / "curve.csv"
OUT = HERE.parent / "assets" / "fig1_variance_error.png"
OUT.parent.mkdir(parents=True, exist_ok=True)

for name in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Source Han Sans SC"):
    if any(f.name == name for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.sans-serif"] = [name]
        break
plt.rcParams["axes.unicode_minus"] = False

rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
by_t = defaultdict(list)
for r in rows:
    by_t[int(r["t"])].append(r)

ts = sorted(by_t)
med_err, zero_frac, neg_frac, xs = [], [], [], []
for t in ts:
    rs = by_t[t]
    n = len(rs)
    errs = [abs(float(r["rel_naive"])) for r in rs]
    med_err.append(statistics.median(errs))
    zero_frac.append(sum(1 for r in rs if float(r["naive"]) == 0.0) / n)
    neg_frac.append(sum(int(r["negative"]) for r in rs) / n)
    xs.append(float(rs[0]["a"]))

FLOOR = 1e-17  # drawn only so the exact (zero-error) series is visible
naive_plot = [max(e, FLOOR) for e in med_err]

fig, (ax1, ax2) = plt.subplots(
    2, 1, figsize=(9.2, 6.8), dpi=200, sharex=True,
    gridspec_kw={"height_ratios": [2.1, 1.0], "hspace": 0.10},
)

ax1.set_xscale("log")
ax1.set_yscale("log")
ax1.plot(xs, naive_plot, color="#b4453a", lw=2.0, marker="o", ms=5, zorder=3,
         label="单遍恒等式  Σx² − (Σx)²/n")
ax1.plot(xs, [FLOOR] * len(xs), color="#1f7a6b", lw=2.0, ls="--", marker="s", ms=4,
         zorder=4, label="平移原点 + 两遍法（每个样本都精确）")
ax1.axhline(1.0, color="#555555", lw=1.0, ls=":")
ax1.text(1.35, 1.7, "相对误差 100%：结果已不可用", fontsize=9, color="#555555")
ax1.axvline(5.0625e8, color="#333333", lw=1.0, ls="-.")
ax1.annotate(
    "bug 报告里的 5.06×10⁸\n单遍算出 −32.0（负方差）",
    xy=(5.0625e8, 129.0), xytext=(3.0e6, 3.0e6),
    fontsize=9, color="#333333",
    arrowprops=dict(arrowstyle="->", color="#333333", lw=1.0,
                    connectionstyle="arc3,rad=-0.2"),
)
ax1.text(2.0e9, FLOOR * 1.8, "平移后误差为 0（画在此处只为可见）", fontsize=8.5, color="#1f7a6b")
ax1.set_ylabel("相对误差（16 个样本的中位数）", fontsize=10)
ax1.set_ylim(FLOOR / 2, 1e16)
ax1.grid(True, which="major", color="#dddddd", lw=0.8)
ax1.grid(True, which="minor", color="#f2f2f2", lw=0.5)
ax1.legend(loc="upper left", fontsize=9, frameon=False)
ax1.set_title("同一份数据（64 个值，真方差 341.25），两种公式算出来的误差", fontsize=11, pad=10)

ax2.set_xscale("log")
ax2.fill_between(xs, 0, zero_frac, step="mid", color="#d9a441", alpha=0.85,
                 label="单遍结果恰为 0")
ax2.fill_between(xs, zero_frac, [a + b for a, b in zip(zero_frac, neg_frac)],
                 step="mid", color="#b4453a", alpha=0.85, label="单遍结果为负")
ax2.set_ylabel("样本占比", fontsize=10)
ax2.set_xlabel("数据量级 a（样本为 a, a+1, …, a+63）", fontsize=10)
ax2.set_ylim(0, 1.0)
ax2.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
ax2.legend(loc="upper left", fontsize=9, frameon=False, ncol=2)
ax2.grid(True, axis="y", color="#dddddd", lw=0.8)

ax2.set_xticks([10.0 ** t for t in ts])
ax2.set_xticklabels([f"10$^{{{t}}}$" for t in ts], fontsize=8.5)

fig.align_ylabels([ax1, ax2])
fig.savefig(OUT, bbox_inches="tight", facecolor="white")
print("wrote", OUT, f"({OUT.stat().st_size} bytes)")

