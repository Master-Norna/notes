"""Draw the three-paths-one-brush diagram; requires Pillow."""
from pathlib import Path
import math
import os
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE / "assets" / "fig1_escape_paths.png"
REG = os.environ.get("CJK_FONT", "C:/Windows/Fonts/msyh.ttc")
BOLD = os.environ.get("CJK_FONT_BOLD", "C:/Windows/Fonts/msyhbd.ttc")
MONO = os.environ.get("MONO_FONT", "C:/Windows/Fonts/consola.ttf")
W, H = 1600, 1120
PAPER, INK, MUTED = "#ffffff", "#26343e", "#64747c"
LINE, RED, BLUE = "#d5dee3", "#ac4e37", "#296780"
BRUSH_FILL = "#eef3f5"
im = Image.new("RGB", (W, H), PAPER)
d = ImageDraw.Draw(im)
boxes, segs = [], []


def text(x, y, value, size=28, color=INK, bold=False, mono=False):
    f = ImageFont.truetype(MONO if mono else (BOLD if bold else REG), size)
    box = d.textbbox((0, 0), value, font=f)
    pos = (x, y - box[1])
    bounds = d.textbbox(pos, value, font=f)
    assert bounds[0] >= 20 and bounds[1] >= 20 and bounds[2] <= W - 20 and bounds[3] <= H - 20, (value, bounds)
    for old, label in boxes:
        assert not (bounds[0] < old[2] and bounds[2] > old[0] and bounds[1] < old[3] and bounds[3] > old[1]), (value, label)
    boxes.append((bounds, value))
    d.text(pos, value, font=f, fill=color)


def card(x1, y1, x2, y2, fill=PAPER, outline=LINE, width=2):
    d.rounded_rectangle((x1, y1, x2, y2), radius=12, fill=fill, outline=outline, width=width)


def head(x, y, direction, color):
    if direction == "down":
        d.polygon([(x, y), (x - 8, y - 12), (x + 8, y - 12)], fill=color)
    elif direction == "up":
        d.polygon([(x, y), (x - 8, y + 12), (x + 8, y + 12)], fill=color)
    else:
        d.polygon([(x, y), (x - 12, y - 8), (x - 12, y + 8)], fill=color)


def seg(x1, y1, x2, y2, color, width=4):
    d.line((x1, y1, x2, y2), fill=color, width=width)
    segs.append((x1, y1, x2, y2))


def dashed(x1, y1, x2, y2, color, width=4, on=16, off=10):
    length = math.hypot(x2 - x1, y2 - y1)
    n = max(1, round(length / (on + off)))
    ux, uy = (x2 - x1) / n, (y2 - y1) / n
    t = 0.0
    while t < length:
        e = min(t + on, length)
        d.line((x1 + ux * t, y1 + uy * t, x1 + ux * e, y1 + uy * e), fill=color, width=width)
        t = e + off
    segs.append((x1, y1, x2, y2))


def varrow(x, y1, y2, color, width=4):
    seg(x, y1, x, y2, color, width)
    head(x, y2, "down" if y2 > y1 else "up", color)


# Header.
text(80, 54, "三条进源文本的路，一把转义刷", 46, bold=True)
text(80, 128, "tomlkit #612 —— 值和写法分开存：值怎么拼都不会错，出岔子的只有源文本这一份", 27, MUTED)

# Three entrances.
card(80, 200, 480, 352)
text(104, 226, "构造字符串", 29, bold=True)
text(104, 278, 'item(\'a"b\')', 26, mono=True)
text(104, 320, "from_raw：查表转义", 22, MUTED)

card(540, 200, 1000, 352)
text(564, 226, "拼接普通 str", 29, bold=True)
text(564, 278, "i + '\"'", 26, mono=True)
text(564, 320, "#612 的洞在这", 23, RED, bold=True)

card(1020, 200, 1520, 352)
text(1044, 226, "拼接 String 值", 29, bold=True)
text(1044, 278, "i + other_str", 26, mono=True)
text(1044, 320, "右边已是转义好的源文本", 22, MUTED)

# Entrance arrows: construction (ink) and plain-str after the fix (blue) go through the brush;
# plain str before the fix (red, dashed) bypasses it, like String+String since #235 (ink).
varrow(280, 352, 428, INK)
varrow(770, 352, 428, BLUE)
text(548, 386, "修后：过刷子再拼", 23, BLUE)
dashed(900, 352, 900, 366, RED)
dashed(900, 366, 1440, 366, RED)
dashed(1440, 366, 1440, 608, RED)
head(1440, 608, "down", RED)
text(920, 378, "修前：原样直入", 23, RED, bold=True)
varrow(1480, 352, 608, INK)
text(1250, 470, "#235：已转义", 22, MUTED)

# The shared brush.
card(80, 430, 1240, 570, fill=BRUSH_FILL, outline=INK)
text(200, 448, "转义刷", 29, bold=True)
text(320, 452, "escape_string(t, esc)", 26, mono=True)
text(200, 508, "构造与修后的拼接共用；按左侧类型查表，字面串的表为空", 23, MUTED)

# Exits into the raw literal.
varrow(280, 570, 608, INK)
varrow(770, 570, 608, INK)

card(80, 610, 1520, 740, outline=INK)
text(108, 636, "源文本 _original", 29, bold=True)
text(430, 644, "不带引号、已转义——序列化只认这一格", 25, MUTED)
text(980, 640, 'a\\"b    foo\\"', 26, mono=True)

# Serialization.
varrow(800, 740, 788, INK)
text(820, 748, "夹上定界符", 24, MUTED)
card(80, 790, 1520, 880)
text(108, 812, "as_string()", 29, bold=True)
text(330, 816, "t + _original + t", 26, mono=True)
text(700, 822, "修前修后一字不变——变的只是上面一格", 25, MUTED)

# The other copy: the logical value never diverges.
card(80, 930, 1520, 1010)
text(108, 952, "逻辑值（str 本体）", 27, MUTED, bold=True)
text(430, 958, "三条路都走 str.__add__，值两版一致——失同步的从来只有源文本", 25, MUTED)

text(80, 1048, "字面串转义表为空：刷子对它恒等，修与不修都原样拼；追加路径也没有 from_raw 的构造校验。", 24, MUTED)

# No line may run through a text box.
for x1, y1, x2, y2 in segs:
    for i in range(61):
        t = i / 60
        px, py = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
        for b, label in boxes:
            if b[0] + 1 < px < b[2] - 1 and b[1] + 1 < py < b[3] - 1:
                raise AssertionError((label, (x1, y1, x2, y2)))

OUT.parent.mkdir(parents=True, exist_ok=True)
im.save(OUT)
print(f"{OUT}: {W}x{H}; {len(boxes)} text boxes, {len(segs)} segments checked")
