"""Draw what the npm cache directory looks like with one name doing two jobs.

Two columns (parent / merged revision) and two moments (while the lock is held,
after the scan). Each moment is a small directory tree: the parent hands the
data file name to a lock that mkdir()s it, so the cache file's slot is taken by
a directory and the save is refused; the merged revision gives the lock its own
".lock" name.

Text is placed by hand; the script checks that every label stays inside its own
frame, that no label sits on a foreign frame, and that no two labels overlap.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon

plt.rcParams["font.family"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

HERE = Path(__file__).resolve().parent
OUT = HERE / "cache-path.png"
DEBUG = "--debug" in sys.argv

INK = "#24313a"
INK2 = "#5b6b77"
EDGE = "#3d4a54"
RED, RED_EDGE, RED_FACE = "#8e2a20", "#b23a2e", "#fdf2f0"
TEAL, TEAL_EDGE, TEAL_FACE = "#20665a", "#2f7d6e", "#f1faf7"
GREY = "#68747c"

W, H = 14.0, 6.4
fig = plt.figure(figsize=(W, H), dpi=110)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.axis("off")

GROUPS = []
FREE = []


def rect(x, y, w, h, *, edge=EDGE, face="#ffffff", lw=1.3, dashed=False):
    patch = FancyBboxPatch((x, y), w, h,
                           boxstyle="round,pad=0.03,rounding_size=0.05",
                           linewidth=lw, edgecolor=edge, facecolor=face,
                           linestyle=(0, (4, 2)) if dashed else "solid")
    ax.add_patch(patch)
    return patch


def text(x, y, s, *, size=10.5, color=INK, ha="left", va="center", weight="normal"):
    t = ax.text(x, y, s, fontsize=size, color=color, ha=ha, va=va, weight=weight)
    FREE.append(t)
    return t


def icon_folder(x, y, color):
    ax.add_patch(Polygon([[x, y + 0.13], [x + 0.10, y + 0.13], [x + 0.13, y + 0.19],
                          [x + 0.24, y + 0.19], [x + 0.24, y - 0.11], [x, y - 0.11]],
                         closed=True, facecolor=color, edgecolor=color, linewidth=1.0, alpha=0.9))


def icon_file(x, y, color):
    ax.add_patch(Polygon([[x, y + 0.19], [x + 0.17, y + 0.19], [x + 0.24, y + 0.11],
                          [x + 0.24, y - 0.11], [x, y - 0.11]],
                         closed=True, facecolor="#ffffff", edgecolor=color, linewidth=1.4))


def tag(x, y, s, color, face):
    w = 0.34 + 0.115 * len(s)
    patch = rect(x, y - 0.13, w, 0.26, edge=color, face=face, lw=1.0)
    t = ax.text(x + w / 2, y, s, fontsize=8.8, color=color, ha="center", va="center")
    GROUPS.append((patch, [t]))


def tree(x, y, w, h, title, rows, note, *, color_note=INK2, face="#fbfcfd"):
    """rows: list of (name, kind, tag_text, tag_color, tag_face) or ('(empty)',)."""
    rect(x, y, w, h, edge="#c9d2d8", face=face, lw=1.1)
    text(x + 0.28, y + h - 0.27, title, size=10.5, color=INK2)
    text(x + 0.28, y + h - 0.6, "$XDG_CACHE_HOME/skylos/", size=9.6, color=INK)
    trunk_x = x + 0.42
    top = y + h - 1.0
    bottom = top - 0.38 * (len(rows) - 1)
    ax.plot([trunk_x, trunk_x], [top, bottom - 0.02], color="#9aa7b0", linewidth=1.1)
    for i, row in enumerate(rows):
        yy = top - 0.38 * i
        ax.plot([trunk_x, trunk_x + 0.3], [yy, yy], color="#9aa7b0", linewidth=1.1)
        if row[0] == "(empty)":
            text(trunk_x + 0.42, yy, row[1], size=9.8, color=GREY)
            continue
        name, kind, tag_text, tcol, tface = row
        if kind == "dir":
            icon_folder(trunk_x + 0.38, yy, tcol)
        else:
            icon_file(trunk_x + 0.36, yy, tcol)
        text(trunk_x + 0.78, yy, name, size=9.6, color=INK)
        tag(x + w - 1.05, yy, tag_text, tcol, tface)
    text(x + 0.28, y + 0.28, note, size=9.4, color=color_note)


# ------------------------------------------------------------------ title
text(0.38, H - 0.34, "一个文件名，两个用途", size=14.5, weight="bold")

text(0.5, 5.52, "修复前", size=12.0, weight="bold", color=RED)
text(1.55, 5.52, "CACHE_FILE 同时交给锁和数据保存", size=9.6, color=INK2)
text(7.4, 5.52, "修复后", size=12.0, weight="bold", color=TEAL)
text(8.45, 5.52, "锁用 .lock，数据名留给文件", size=9.6, color=INK2)

tree(0.5, 3.2, 6.2, 2.15, "刚拿到锁", [
    ("npm-mirror-identities.json", "dir", "目录", RED, RED_FACE),
], "os.mkdir 把数据路径建成了目录：保存被拒，返回 False", color_note=RED)

tree(0.5, 0.75, 6.2, 2.15, "结束之后", [
    ("(empty)", "（什么都没有）"),
], "锁退出时 rmdir，盘上没有缓存文件，也没有异常", color_note=RED)

tree(7.4, 3.2, 6.2, 2.15, "刚拿到锁", [
    ("npm-mirror-identities.json.lock", "dir", "目录", TEAL, TEAL_FACE),
    ("(empty)", "（数据路径空着）"),
], "两个名字各管一件事：锁占 .lock，数据文件名留给文件", color_note=TEAL)

tree(7.4, 0.75, 6.2, 2.15, "结束之后", [
    ("npm-mirror-identities.json", "file", "1 条", TEAL, TEAL_FACE),
], "文件留下，下一次扫描命中缓存，请求数为 0", color_note=TEAL)

fig.savefig(OUT, facecolor="#ffffff")

# ------------------------------------------------------------------ checks
fig.canvas.draw()
renderer = fig.canvas.get_renderer()
inv = ax.transData.inverted()

problems = []
all_texts = [t for _, ts in GROUPS for t in ts] + FREE
for t in all_texts:
    bb = t.get_window_extent(renderer=renderer)
    if bb.x0 < -1 or bb.y0 < -1 or bb.x1 > fig.bbox.width + 1 or bb.y1 > fig.bbox.height + 1:
        problems.append(f"out of canvas: {t.get_text()!r}")
for patch, ts in GROUPS:
    pb = patch.get_window_extent(renderer=renderer)
    for t in ts:
        tb = t.get_window_extent(renderer=renderer)
        if tb.x0 < pb.x0 + 1 or tb.x1 > pb.x1 - 1 or tb.y0 < pb.y0 + 1 or tb.y1 > pb.y1 - 1:
            problems.append(f"label leaves its tag: {t.get_text()!r}")
for i in range(len(all_texts)):
    a = all_texts[i].get_window_extent(renderer=renderer)
    for j in range(i + 1, len(all_texts)):
        b = all_texts[j].get_window_extent(renderer=renderer)
        ix = min(a.x1, b.x1) - max(a.x0, b.x0)
        iy = min(a.y1, b.y1) - max(a.y0, b.y0)
        if ix > 2 and iy > 2:
            problems.append(f"text overlap: {all_texts[i].get_text()!r} / {all_texts[j].get_text()!r}")

# lines must not run through a label: hide the text and look for ink
import numpy as np

fig.canvas.draw()
for t in all_texts:
    t.set_visible(False)
fig.canvas.draw()
buf = np.asarray(fig.canvas.buffer_rgba())
height = buf.shape[0]
for t in all_texts:
    bb = t.get_window_extent(renderer=renderer)
    x0, x1 = int(bb.x0) + 2, int(bb.x1) - 1
    y0, y1 = int(height - bb.y1) + 2, int(height - bb.y0) - 1
    region = buf[y0:y1, x0:x1, :3]
    ink = int(((region < 200).any(axis=2)).sum())
    if ink > 4:
        problems.append(f"ink under label: {t.get_text()!r} ({ink} px)")
for t in all_texts:
    t.set_visible(True)

if DEBUG:
    for t in all_texts:
        bb = t.get_window_extent(renderer=renderer)
        (x0, y0), (x1, y1) = inv.transform([[bb.x0, bb.y0], [bb.x1, bb.y1]])
        print(f"  {t.get_text()[:40]!r:46} x {x0:5.2f}-{x1:5.2f}  y {y0:5.2f}-{y1:5.2f}")

if problems:
    print("\n".join(problems))
    sys.exit(1)
print(f"ok {OUT.name} {OUT.stat().st_size} bytes")



