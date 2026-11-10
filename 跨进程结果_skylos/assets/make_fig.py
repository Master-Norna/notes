"""Draw the object chain that makes a danger worker result unpicklable.

Left: the parent revision. Right: the merged revision. Text boxes are laid out
by hand; the script checks that no two text boxes overlap and that everything
stays inside the canvas.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

plt.rcParams["font.family"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

HERE = Path(__file__).resolve().parent
OUT = HERE / "pickle-chain.png"

W, H = 14.0, 6.6
fig = plt.figure(figsize=(W, H), dpi=110)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.axis("off")

boxed = []


def box(x, y, w, h, text, *, edge="#3d4a54", face="#ffffff", color="#24313a", dashed=False, size=11.5):
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.03,rounding_size=0.06",
        linewidth=1.4,
        edgecolor=edge,
        facecolor=face,
        linestyle=(0, (4, 2)) if dashed else "solid",
    )
    ax.add_patch(patch)
    label = ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size, color=color)
    boxed.append((patch, label))
    return patch, label


def arrow(x1, y1, x2, y2, label=None, color="#5b6b77", lx=None, ly=None):
    ax.add_patch(
        FancyArrowPatch(
            (x1, y1),
            (x2, y2),
            arrowstyle="-|>",
            mutation_scale=13,
            linewidth=1.3,
            color=color,
            shrinkA=0,
            shrinkB=0,
        )
    )
    if label:
        ax.text(lx if lx is not None else (x1 + x2) / 2 + 0.08, ly if ly is not None else (y1 + y2) / 2, label,
                fontsize=9.5, color=color, ha="left", va="center")


ax.text(0.35, 6.28, "修复前：结果顺着 parent 走回 module", fontsize=13.5, color="#24313a", weight="bold")
ax.text(7.45, 6.28, "修复后：__getstate__ 只送 module", fontsize=13.5, color="#24313a", weight="bold")

left_x, left_w, node_h = 0.35, 3.9, 0.52
right_x = 7.45

# left column
pairs = []
pairs.append(box(left_x, 5.35, left_w, node_h, "Definition（worker 结果里的一项）"))
pairs.append(box(left_x, 4.45, left_w, node_h, "node: FunctionDef"))
pairs.append(box(left_x, 3.55, left_w, node_h, "Module（AST）"))
pairs.append(box(left_x, 2.65, left_w, node_h, "_CallableIndex（module.__dict__）"))
pairs.append(box(left_x, 1.75, left_w, node_h, "flows[id(scope)] = (engine, result)", size=10.5))
pairs.append(box(left_x, 0.55, left_w, node_h, "outer：flow() 里的局部函数", edge="#b23a2e", face="#fdf2f0", color="#8e2a20", size=10.5))

for y1, y2 in ((5.35, 5.04), (4.45, 4.14), (3.55, 3.24), (2.65, 2.34), (1.75, 1.14)):
    arrow(left_x + left_w / 2, y1, left_x + left_w / 2, y2)
ax.text(left_x + left_w / 2 + 0.1, 3.30, "parent / __dict__ / 缓存", fontsize=9.5, color="#5b6b77")
ax.text(left_x + left_w + 0.18, 0.81, "pickle 找不到\n这个局部名字", fontsize=10.5, color="#8e2a20", va="center")

# right column
pairs.append(box(right_x, 5.35, left_w, node_h, "Definition（worker 结果里的一项）"))
pairs.append(box(right_x, 4.45, left_w, node_h, "node: FunctionDef"))
pairs.append(box(right_x, 3.55, left_w, node_h, "Module（AST）"))
pairs.append(box(right_x, 2.65, left_w, node_h, "_CallableIndex（只留 module 引用）", edge="#2f7d6e", face="#f1faf7", color="#20665a", size=10.5, dashed=True))
pairs.append(box(right_x, 1.75, left_w, node_h, "flows：反序列化后不存在", face="#f7f8f9", color="#68747c", dashed=True, size=10.5))
pairs.append(box(right_x, 0.55, left_w, node_h, "outer：首次使用时重建", face="#f7f8f9", color="#68747c", dashed=True, size=10.5))

for y1, y2 in ((5.35, 5.04), (4.45, 4.14), (3.55, 3.24)):
    arrow(right_x + left_w / 2, y1, right_x + left_w / 2, y2)
arrow(right_x + left_w / 2, 2.65, right_x + left_w / 2, 2.34, color="#9aa7b0")
arrow(right_x + left_w / 2, 1.75, right_x + left_w / 2, 1.14, color="#9aa7b0")
ax.text(right_x + left_w + 0.18, 2.45, "pickle 不进来", fontsize=10.5, color="#68747c", va="center")
ax.text(right_x + left_w + 0.18, 1.15, "第一次 scope()/flow()\n时 __init__(module)", fontsize=10.5, color="#20665a", va="center")

fig.savefig(OUT, facecolor="#ffffff")

# overlap / bounds check
fig.canvas.draw()
renderer = fig.canvas.get_renderer()
texts = [t for t in ax.texts]
boxes = []
for t in texts:
    bb = t.get_window_extent(renderer=renderer)
    boxes.append((t.get_text(), bb))

problems = []
for patch, label in boxed:
    pb = patch.get_window_extent(renderer=renderer)
    tb = label.get_window_extent(renderer=renderer)
    if tb.x0 < pb.x0 + 2 or tb.x1 > pb.x1 - 2 or tb.y0 < pb.y0 + 2 or tb.y1 > pb.y1 - 2:
        problems.append(f"text outside its box: {label.get_text()!r}")

for i in range(len(boxes)):
    name, bb = boxes[i]
    if bb.x0 < -1 or bb.y0 < -1 or bb.x1 > fig.bbox.width + 1 or bb.y1 > fig.bbox.height + 1:
        problems.append(f"out of canvas: {name!r}")
    for j in range(i + 1, len(boxes)):
        other, ob = boxes[j]
        if bb.overlaps(ob):
            problems.append(f"overlap: {name!r} / {other!r}")

if problems:
    print("\n".join(problems))
    sys.exit(1)
print(f"ok {OUT} {OUT.stat().st_size} bytes")
