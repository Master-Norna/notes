# 每个专题一枚小图标：灰色画一个规律，朱色只画规律里不对的那一处，那一处对着文章里 bug 的形状挑
# 图标由三张登记表拼成：排布（规律怎么排）× 记号（每格画什么）× 异常（哪里不对）；异常落在哪一格、条有多长由文件夹名的哈希定
# 用法：python assets/make_icons.py；会扫仓库里含 *_中文版.md 的专题文件夹，写进各自的 assets/icon.svg
# 新专题在 TOPICS 里登记一行；没登记的用哈希在可行组合里挑一个
import hashlib, math, pathlib
from types import SimpleNamespace as NS

REPO = pathlib.Path(__file__).resolve().parents[1]
GRAY, INK = "#8c959f", "#d1603d"

TOPICS = {
    "时间轮_timing_wheel": ("ring", "tick", "extra"),  # 轮子里多出来的 +1
    "方差稳定性_nushell_variance": ("row", "bar", "flip"),  # 方差成了负数
    "拥塞控制_cubic": ("stack", "bar", "double"),  # 同一个窗口乘了两遍 0.7
    "取消与背压_anyio": ("grid", "dot", "overflow"),  # 取消了还在往队列里堆
    "锁文件哈希_pdm": ("ring", "dot", "missing"),  # 往返一圈，哈希没了
    "导入排序语义_isort": ("stack", "bar", "truncate"),  # 一行的尾巴 noqa 被截掉
    "转义往返_tomlkit": ("fence", "bar", "double"),  # 转义多做了一遍
}

# ---- 记号：point 画在线段中点，line 画整条线段 ----
# 每格的样式："" 灰、"ink" 朱、"thin" 细一号的朱、"big" 放大的朱、"ghost" 朱色虚线的空位


def _circle(seg, style, r, rb, hollow):
    cx, cy = (seg[0] + seg[2]) / 2, (seg[1] + seg[3]) / 2
    if style == "ghost":
        return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="none" stroke="{INK}" stroke-width="2" stroke-dasharray="2.5 2"/>'
    rr = {"": r, "ink": rb, "thin": r, "big": rb * 1.5}[style]
    color = GRAY if style == "" else INK
    if hollow:
        return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{rr}" fill="none" stroke="{color}" stroke-width="{1.6 if style == "" else 2.4}"/>'
    return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{rr}" fill="{color}"/>'


def _block(seg, style):
    cx, cy = (seg[0] + seg[2]) / 2, (seg[1] + seg[3]) / 2
    if style == "ghost":
        return f'<rect x="{cx - 4.5:.1f}" y="{cy - 4.5:.1f}" width="9" height="9" fill="none" stroke="{INK}" stroke-width="2" stroke-dasharray="2.5 2"/>'
    h = {"": 3, "ink": 4, "thin": 3, "big": 6}[style]
    return f'<rect x="{cx - h:.1f}" y="{cy - h:.1f}" width="{2 * h}" height="{2 * h}" rx="1.5" fill="{GRAY if style == "" else INK}"/>'


def _line(seg, style, w, wb):
    x1, y1, x2, y2 = seg
    if style == "ghost":
        tail = f'stroke="{INK}" stroke-width="2.2" stroke-dasharray="3 3"'
    else:
        tail = f'stroke="{GRAY if style == "" else INK}" stroke-width="{w if style == "" else wb * 0.55 if style == "thin" else wb}"'
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" {tail} stroke-linecap="round"/>'


MARKS = {
    "dot": NS(kind="point", size=4.5, draw=lambda seg, st: _circle(seg, st, 3, 4.5, False)),
    "hollow": NS(kind="point", size=4.5, draw=lambda seg, st: _circle(seg, st, 3.5, 4.5, True)),
    "block": NS(kind="point", size=4, draw=_block),
    "tick": NS(kind="line", size=3.6, draw=lambda seg, st: _line(seg, st, 2.2, 3.6)),
    "bar": NS(kind="line", size=6, draw=lambda seg, st: _line(seg, st, 6, 6)),
}

# ---- 排布：slot(t) 给出第 t 格的线段 (x1, y1, x2, y2)，(x1, y1) 是锚点；t 可以是小数（插在两格之间）或越过 n（溢出） ----
# room 是越过末尾还能画几格，ends 是有没有头尾，ordered 是长短有没有顺序；画不了的记号返回 None


def ring(mark, b):
    point = MARKS[mark].kind == "point"
    n = 12
    r0, r1 = (30, 30) if point else (18, 34) if mark == "bar" else (24, 36)
    ang = lambda t: 2 * math.pi * t / n - math.pi / 2
    return NS(n=n, room=0, ends=False, ordered=False,
              slot=lambda t: (48 + r0 * math.cos(ang(t)), 48 + r0 * math.sin(ang(t)), 48 + r1 * math.cos(ang(t)), 48 + r1 * math.sin(ang(t))),
              away=lambda t: (8 * math.cos(ang(t)), 8 * math.sin(ang(t))))


def grid(mark, b):
    half = 0 if MARKS[mark].kind == "point" else 5 if mark == "tick" else 4

    def slot(t):
        k = int(t)
        x, y = 24 + (k % 4 + t - k) * 16, 24 + k // 4 * 16
        return (x - half, y, x + half, y)

    return NS(n=16, room=2, ends=True, ordered=False, slot=slot, away=lambda t: (6, 6))


def tri(mark, b):
    # 三角点阵，一至五排；第六排留给溢出
    if MARKS[mark].kind != "point":
        return None
    cells = [(r, c) for r in range(6) for c in range(r + 1)]

    def slot(t):
        k = int(t)
        r, c = cells[k]
        x, y = 48 + (c + t - k - r / 2) * 15, 20 + r * 14
        return (x, y, x, y)

    return NS(n=15, room=2, ends=True, ordered=False, slot=slot, away=lambda t: (7, -7))


def fan(mark, b):
    # 上半圆的九道放射线
    if MARKS[mark].kind != "line":
        return None
    ang = lambda t: math.pi + math.pi * t / 8
    return NS(n=9, room=1, ends=True, ordered=False,
              slot=lambda t: (48 + 14 * math.cos(ang(t)), 60 + 14 * math.sin(ang(t)), 48 + 34 * math.cos(ang(t)), 60 + 34 * math.sin(ang(t))),
              away=lambda t: (8 * math.cos(ang(t)), 8 * math.sin(ang(t))))


def hatch(mark, b):
    # 圆里七道 45° 斜线
    if MARKS[mark].kind != "line":
        return None

    def slot(t):
        d = (t - 3) * 10
        half = math.sqrt(max(34 ** 2 - d ** 2, 16))
        cx = cy = 48 + d / math.sqrt(2)
        u = half / math.sqrt(2)
        return (cx - u, cy + u, cx + u, cy - u)

    return NS(n=7, room=0, ends=True, ordered=False, slot=slot, away=lambda t: (6, -6))


def _vertical(name, n, height, ordered):
    def make(mark, b):
        if MARKS[mark].kind != "line":
            return None
        return NS(n=n, room=1, ends=True, ordered=ordered,
                  slot=lambda t: (24 + t * 11, 70, 24 + t * 11, 70 - height(int(t), b)),
                  away=lambda t: (0, -10))
    make.__name__ = name
    return make


row = _vertical("row", 6, lambda k, b: 18 + b[3 + k % 8] % 34, False)  # 竖条，长短随哈希
steps = _vertical("steps", 6, lambda k, b: 12 + 7 * k, True)  # 竖条，一格比一格高
fence = _vertical("fence", 6, lambda k, b: 40, False)  # 竖条，一样高


def stack(mark, b):
    # 一摞居中的横条，长短随哈希
    if MARKS[mark].kind != "line":
        return None

    def slot(t):
        w = 24 + b[3 + int(t) % 8] % 40
        y = 22 + t * 12
        return (48 - w / 2, y, 48 + w / 2, y)

    return NS(n=5, room=2, ends=True, ordered=False, slot=slot, away=lambda t: (10, 0))


LAYOUTS = {f.__name__: f for f in (ring, grid, tri, fan, hatch, row, steps, fence, stack)}

# ---- 异常：(排布, 记号, 第 k 格) -> ({格号: [(线段, 样式)]} 的替换, 另外画的 [(线段, 样式)])；不适用返回 None ----


def _len(seg):
    return math.hypot(seg[2] - seg[0], seg[3] - seg[1])


def _part(seg, a, z):
    x1, y1, x2, y2 = seg
    return (x1 + (x2 - x1) * a, y1 + (y2 - y1) * a, x1 + (x2 - x1) * z, y1 + (y2 - y1) * z)


def extra(L, m, k):  # 多出一个：+1
    k = min(k, L.n - 2) if L.ends else k
    return {}, [(L.slot(k + 0.5), "ink")]


def missing(L, m, k):  # 该在的没了，只留虚线的空位
    return {k: [(L.slot(k), "ghost")]}, []


def double(L, m, k):  # 同一件事做了两遍：这一格劈成并排的两份
    # 不另画一份重影：格距只有十来像素，重影会和邻格糊成一块
    seg = L.slot(k)
    d, off = _len(seg), MARKS[m].size * 0.6
    ox, oy = ((seg[1] - seg[3]) / d * off, (seg[2] - seg[0]) / d * off) if d else (off * 1.2, 0)
    return {k: [((seg[0] + ox, seg[1] + oy, seg[2] + ox, seg[3] + oy), "thin"),
                ((seg[0] - ox, seg[1] - oy, seg[2] - ox, seg[3] - oy), "thin")]}, []


def outlier(L, m, k):  # 离群：位置偏了
    x1, y1, x2, y2 = L.slot(k)
    ax, ay = L.away(k)
    return {k: [((x1 + ax, y1 + ay, x2 + ax, y2 + ay), "ink")]}, []


def flip(L, m, k):  # 方向反了：从锚点往反方向长，长度截到 24 以内
    x1, y1, x2, y2 = seg = L.slot(k)
    if MARKS[m].kind != "line":
        return None
    f = min(_len(seg), 24) / _len(seg)
    return {k: [((x1, y1, x1 - (x2 - x1) * f, y1 - (y2 - y1) * f), "ink")]}, []


def overflow(L, m, k):  # 越过容量还在往后堆
    if not L.room:
        return None
    return {}, [(L.slot(L.n + j), "ink") for j in range(L.room)]


def swap(L, m, k):  # 顺序错了：相邻两格的长短对调
    if not L.ordered:
        return None
    k = min(k, L.n - 2)
    a, z = L.slot(k), L.slot(k + 1)
    return {k: [((a[0], a[1], a[0] + z[2] - z[0], a[1] + z[3] - z[1]), "ink")],
            k + 1: [((z[0], z[1], z[0] + a[2] - a[0], z[1] + a[3] - a[1]), "ink")]}, []


def gap(L, m, k):  # 中间断开
    seg = L.slot(k)
    if MARKS[m].kind != "line" or _len(seg) < 12:
        return None
    return {k: [(_part(seg, 0, 0.36), "ink"), (_part(seg, 0.64, 1), "ink")]}, []


def tilt(L, m, k):  # 歪了：绕中点转 30°
    x1, y1, x2, y2 = L.slot(k)
    if MARKS[m].kind != "line":
        return None
    cx, cy, c, s = (x1 + x2) / 2, (y1 + y2) / 2, math.cos(math.pi / 6), math.sin(math.pi / 6)
    rot = lambda x, y: (cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c)
    return {k: [((*rot(x1, y1), *rot(x2, y2)), "ink")]}, []


def grow(L, m, k):  # 比别的都大
    seg = L.slot(k)
    if MARKS[m].kind == "point":
        return {k: [(seg, "big")]}, []
    return {k: [(_part(seg, 0, 1.5), "ink")]}, []


def truncate(L, m, k):  # 截掉一截，丢的那段留虚线
    seg = L.slot(k)
    if MARKS[m].kind != "line" or _len(seg) < 12:
        return None
    return {k: [(_part(seg, 0, 0.45), "ink"), (_part(seg, 0.62, 1), "ghost")]}, []


def shift(L, m, k):  # 错位：从这一格起，后面都挪了半格；朱色只落在断开的那一格
    if not L.ends:
        return None
    k = max(1, min(k, L.n - 2))
    return {i: [(L.slot(i + 0.5), "ink" if i == k else "")] for i in range(k, L.n)}, []


ANOMALIES = {f.__name__: f for f in (extra, missing, double, outlier, flip, overflow, swap, gap, tilt, grow, truncate, shift)}


def icon(spec, seed, size=96):
    layout, mark, anomaly = spec
    b = hashlib.sha1(seed.encode("utf-8")).digest()
    L = LAYOUTS[layout](mark, b)
    r = L and ANOMALIES[anomaly](L, mark, b[1] % L.n)
    if r is None:
        return None
    swaps, more = r
    parts = [p for i in range(L.n) for p in swaps.get(i, [(L.slot(i), "")])] + more
    # 各排布的原点不一，异常又会把图形往一边撑，统一按外框居中
    xs = [v for seg, _ in parts for v in seg[0::2]]
    ys = [v for seg, _ in parts for v in seg[1::2]]
    dx, dy = 48 - (min(xs) + max(xs)) / 2, 48 - (min(ys) + max(ys)) / 2
    body = "\n".join(MARKS[mark].draw((x1 + dx, y1 + dy, x2 + dx, y2 + dy), st) for (x1, y1, x2, y2), st in parts)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96" width="{size}" height="{size}">\n{body}\n</svg>\n'


def combos(seed):
    return [(l, m, a) for l in LAYOUTS for m in MARKS for a in ANOMALIES if icon((l, m, a), seed)]


def spec_for(name):
    if name in TOPICS:
        return TOPICS[name]
    c = combos(name)
    return c[int.from_bytes(hashlib.sha1(name.encode("utf-8")).digest()[8:12], "big") % len(c)]


if __name__ == "__main__":
    for t in sorted({p.parent for p in REPO.glob("*/*_中文版.md")}):
        spec = spec_for(t.name)
        (t / "assets").mkdir(exist_ok=True)
        with open(t / "assets" / "icon.svg", "w", encoding="utf-8", newline="") as f:
            f.write(icon(spec, t.name))
        print(t.name, "·".join(spec), "" if t.name in TOPICS else "(哈希)")
