# 每个专题一枚小图标，没有含义，按文件夹名取哈希定形状：几何底纹全用灰，只留一处朱色
# 用法：python assets/make_icons.py；会扫仓库里含 *_中文版.md 的专题文件夹，写进各自的 assets/icon.svg，新专题跑一次就有
import hashlib, math, pathlib, subprocess

REPO = pathlib.Path(__file__).resolve().parents[1]
GRAY, INK = "#8c959f", "#d1603d"


def rings(b):
    s = [f'<circle cx="48" cy="48" r="{r}" fill="none" stroke="{GRAY}" stroke-width="2"/>' for r in (12, 22, 32)]
    r = (12, 22, 32)[b[1] % 3]
    a0 = b[2] / 255 * 2 * math.pi
    a1 = a0 + math.pi / 3
    s.append(
        f'<path d="M{48 + r * math.cos(a0):.1f},{48 + r * math.sin(a0):.1f} A{r},{r} 0 0 1 {48 + r * math.cos(a1):.1f},{48 + r * math.sin(a1):.1f}" '
        f'fill="none" stroke="{INK}" stroke-width="4" stroke-linecap="round"/>'
    )
    return s


def dots(b):
    pick = b[1] % 16
    s = []
    for k in range(16):
        x, y = 21 + (k % 4) * 18, 21 + (k // 4) * 18
        s.append(f'<circle cx="{x}" cy="{y}" r="{5.5 if k == pick else 3}" fill="{INK if k == pick else GRAY}"/>')
    return s


def ticks(b):
    pick = b[1] % 24
    s = []
    for k in range(24):
        a = 2 * math.pi * k / 24 - math.pi / 2
        r1 = 18 if k == pick else 28
        s.append(
            f'<line x1="{48 + r1 * math.cos(a):.1f}" y1="{48 + r1 * math.sin(a):.1f}" x2="{48 + 36 * math.cos(a):.1f}" y2="{48 + 36 * math.sin(a):.1f}" '
            f'stroke="{INK if k == pick else GRAY}" stroke-width="{3.5 if k == pick else 2}" stroke-linecap="round"/>'
        )
    return s


def bars(b):
    pick = b[1] % 5
    s = []
    for k in range(5):
        w = 24 + b[2 + k] % 40
        s.append(f'<rect x="{48 - w / 2:.0f}" y="{20 + k * 12}" width="{w}" height="6" rx="3" fill="{INK if k == pick else GRAY}"/>')
    return s


def waves(b):
    pick = b[1] % 3
    s = []
    for k in range(3):
        ph = b[2 + k] / 255 * 2 * math.pi
        pts = " L".join(f"{14 + i * 2},{30 + k * 18 + 6 * math.sin(i / 34 * 2 * math.pi * 1.5 + ph):.1f}" for i in range(35))
        s.append(f'<path d="M{pts}" fill="none" stroke="{INK if k == pick else GRAY}" stroke-width="{3.5 if k == pick else 2}" stroke-linecap="round"/>')
    return s


SHAPES = [rings, dots, ticks, bars, waves]



def first_added(t):
    # 按专题进仓库的先后轮换形状，新专题排在最后，旧图标不会跟着变；还没提交的算最新
    r = subprocess.run(["git", "log", "--diff-filter=A", "--format=%at", "--", t.name], cwd=REPO, capture_output=True, text=True)
    stamps = r.stdout.split()
    return int(stamps[-1]) if stamps else float("inf")


topics = sorted({p.parent for p in REPO.glob("*/*_中文版.md")}, key=first_added)
for i, t in enumerate(topics):
    b = hashlib.sha1(t.name.encode("utf-8")).digest()
    shape = SHAPES[i % len(SHAPES)]
    body = "\n".join(shape(b))
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96" width="96" height="96">\n{body}\n</svg>\n'
    (t / "assets").mkdir(exist_ok=True)
    with open(t / "assets" / "icon.svg", "w", encoding="utf-8", newline="") as f:
        f.write(svg)
    print(t.name, shape.__name__)
