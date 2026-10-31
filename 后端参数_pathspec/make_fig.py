"""Draw the three real strategies, with text overlap and bounds checks."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
W, H = 1560, 1000
BG, INK, MUTED = '#f7f9fa', '#253642', '#61727d'
RED, TEAL, LINE = '#b95249', '#127b73', '#dbe4e8'
FONT = Path('C:/Windows/Fonts/msyh.ttc')
im = Image.new('RGB', (W, H), BG)
d = ImageDraw.Draw(im)
boxes = []

def text(x, y, value, size=28, color=INK):
    font = ImageFont.truetype(str(FONT), size)
    box = d.textbbox((x, y), value, font=font)
    assert 0 <= box[0] < box[2] <= W and 0 <= box[1] < box[3] <= H, (value, box)
    for old, label in boxes:
        assert box[2] <= old[0] or old[2] <= box[0] or box[3] <= old[1] or old[3] <= box[1], (value, label)
    boxes.append((box, value))
    d.text((x, y), value, font=font, fill=color)

def card(rect):
    d.rounded_rectangle(rect, radius=18, fill='white', outline=LINE, width=2)

def arrow(x, y1, y2, color):
    d.line((x, y1, x, y2), fill=color, width=4)
    d.polygon([(x, y2), (x-9, y2-14), (x+9, y2-14)], fill=color)

text(64, 36, '同一个编译对象，三种处理方式', 43)
text(66, 109, '输入：re.compile("^secret$", re.I)     待匹配：SECRET', 30)
text(66, 164, '表达式文本里没有 (?i)；忽略大小写的要求保存在 .flags 中。', 28, MUTED)
for left in (48, 552, 1056):
    card((left, 250, left+456, 714))
text(80, 280, '修复前：丢下参数', 32, RED)
text(584, 280, '初稿：保守退出', 32, MUTED)
text(1088, 280, '最终：翻译后再加速', 30, TEAL)
text(80, 364, '只取 .pattern', 29)
text(584, 364, '探测到外部 flags', 29)
text(1088, 364, '取 .pattern 与 .flags', 29)
arrow(276, 425, 468, RED)
arrow(780, 425, 468, MUTED)
arrow(1284, 425, 468, TEAL)
text(80, 492, '^secret$ → RE2', 29, RED)
text(584, 492, '自动选择 → simple', 29)
text(1088, 492, '(?i)^secret$ → RE2', 28, TEAL)
text(80, 584, 'False：大写不再命中', 29, RED)
text(584, 584, 'True：留在 Python', 29)
text(1088, 584, 'True：仍用原生后端', 29, TEAL)
text(80, 653, '默认后端取决于可导入的库', 23, MUTED)
text(584, 653, '显式原生选择则报错', 24, MUTED)
text(1088, 653, '这里的 i 是可表达的参数', 23, MUTED)
card((48, 766, 1512, 938))
text(80, 789, '最终版遇到不能保留的 flags，例如 VERBOSE', 30)
text(80, 854, '自动 best：整份 spec 回退 simple', 27, TEAL)
text(824, 854, '显式 re2 / hyperscan：ValueError', 27, RED)
out = ROOT / 'assets' / 'fig1_flags_backends.png'
out.parent.mkdir(parents=True, exist_ok=True)
im.save(out)
print(f'{out.name}: {W}x{H}; {len(boxes)} text boxes; overlap/bounds checks passed')
