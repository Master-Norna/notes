"""Draw the two roles of calendar months; checks every text box before saving."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
W, H = 1560, 950
BG, INK, MUTED = '#f7f9fa', '#253642', '#61727d'
RED, TEAL, LINE = '#b95249', '#127b73', '#dbe4e8'
FONT = Path('C:/Windows/Fonts/msyh.ttc')
if not FONT.exists():
    raise SystemExit('Requires Microsoft YaHei: C:/Windows/Fonts/msyh.ttc')
image = Image.new('RGB', (W, H), BG)
d = ImageDraw.Draw(image)
boxes = []

def text(x, y, value, size=29, color=INK):
    font = ImageFont.truetype(str(FONT), size)
    box = d.textbbox((x, y), value, font=font)
    assert 0 <= box[0] < box[2] <= W and 0 <= box[1] < box[3] <= H, (value, box)
    for old, label in boxes:
        assert box[2] <= old[0] or old[2] <= box[0] or box[3] <= old[1] or old[3] <= box[1], (value, label)
    boxes.append((box, value))
    d.text((x, y), value, font=font, fill=color)

def arrow(x1, x2, y, color):
    d.line((x1, y, x2, y), fill=color, width=5)
    d.polygon([(x2, y), (x2-15, y-9), (x2-15, y+9)], fill=color)

text(68, 42, '同一次钳制，不能替两件事作决定', 43)
text(70, 110, '先按原始日号决定整月数，再从实际落点计算余天。以下均为 2023 年、UTC 零点。', 26, MUTED)

for top in (190, 545):
    d.rounded_rectangle((48, top, 1512, top+315), radius=18, fill='white', outline=LINE, width=2)

text(82, 216, '1 月 31 日 → 2 月 28 日', 34)
text(82, 281, '28 < 31，整月数从 1 减到 0', 30, TEAL)
text(82, 339, '锚点留在 1 月 31 日，余下 28 天。', 27)
text(82, 415, '初稿：钳到 2 月 28 日就算满月', 27, RED)
text(82, 456, '最终：仍然是 28 天', 27, TEAL)
text(832, 290, '1 月 31 日', 28)
text(1250, 290, '2 月 28 日', 28)
arrow(870, 1320, 360, TEAL)
text(986, 385, '0 个月 + 28 天', 28, TEAL)

text(82, 571, '1 月 31 日 → 3 月 1 日', 34)
text(82, 636, '1 < 31，整月数从 2 减到 1', 30, TEAL)
text(82, 694, '加 1 个月钳到 2 月 28 日，再走 1 天。', 27)
text(82, 770, '修复前：借 28 天，结果仍是 −2 天', 27, RED)
text(82, 811, '最终：1 个月 1 天', 27, TEAL)
text(816, 645, '1 月 31 日', 27)
text(1080, 645, '2 月 28 日', 27)
text(1352, 645, '3 月 1 日', 27)
arrow(850, 1130, 715, TEAL)
arrow(1180, 1410, 715, TEAL)
text(887, 748, '1 个月（钳制）', 25, TEAL)
text(1280, 748, '+ 1 天', 25, TEAL)
text(70, 900, '整月的判定规则 ≠ 月份加法的落点规则', 27, MUTED)

out = ROOT / 'assets' / 'fig1_month_anchor.png'
out.parent.mkdir(parents=True, exist_ok=True)
image.save(out)
print(f'{out.name}: {W}x{H}; {len(boxes)} text boxes; overlap/bounds checks passed')
