"""Draw the figure for the PDM #3975 article.

One artifact, two names. `path` supplies the location, `name` supplies the
filename; unearth reads a link's filename off the tail of its URL, so the fix
stages a copy under the logical name and lets the tail line up.

Character-level detail is the point: which cells of the URI carry the location,
which sixteen carry the name, and what the copy looks like on disk.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
BG, INK, MUTED = '#f7f9fa', '#253642', '#61727d'
RED, TEAL, LINE = '#b95249', '#127b73', '#dbe4e8'
RED_FILL = '#f8e8e6'
FONT = Path('C:/Windows/Fonts/msyh.ttc')
if not FONT.exists():
    raise SystemExit('Requires Microsoft YaHei: C:/Windows/Fonts/msyh.ttc')

URI = 'file:///…/locks/local%20artifacts/0123456789abcdef'
NAME_FIRST = URI.index('0123456789abcdef')          # first cell of the tail
SOURCE = 'locks/local artifacts/0123456789abcdef'
STAGED = '<下载目录>/first-2.0.2-py2.py3-none-any.whl'


class Sheet:
    def __init__(self, w, h):
        self.W, self.H = w, h
        self.image = Image.new('RGB', (self.W, self.H), BG)
        self.d = ImageDraw.Draw(self.image)
        self.boxes = []

    def text(self, x, y, value, size=28, color=INK):
        font = ImageFont.truetype(str(FONT), size)
        box = self.d.textbbox((x, y), value, font=font)
        assert 0 <= box[0] < box[2] <= self.W and 0 <= box[1] < box[3] <= self.H, (value, box)
        for old, label in self.boxes:
            assert box[2] <= old[0] or old[2] <= box[0] or box[3] <= old[1] or old[3] <= box[1], \
                (value, label)
        self.boxes.append((box, value))
        self.d.text((x, y), value, font=font, fill=color)
        return box

    def ruler(self, x, y, chars, target, h=54, size=23, hot=()):
        """One tiled cell per character, stretched to `target` so brackets line up."""
        font = ImageFont.truetype(str(FONT), size)
        advances = [font.getlength(ch) for ch in chars]
        pad = (target - x - sum(advances)) / len(chars)
        assert pad >= 5, pad
        lefts, offset = [], 0.0
        for i, ch in enumerate(chars):
            w = advances[i] + pad
            cell = (x + offset, y, x + offset + w, y + h)
            assert 0 <= cell[0] < cell[2] <= self.W and 0 <= cell[1] < cell[3] <= self.H
            is_hot = i in hot
            self.d.rectangle(cell, fill=RED_FILL if is_hot else 'white',
                             outline=RED if is_hot else LINE, width=2)
            gx0, gy0, gx1, gy1 = font.getbbox(ch)
            self.d.text((cell[0] + (w - (gx1 - gx0)) / 2 - gx0,
                         cell[1] + (h - (gy1 - gy0)) / 2 - gy0),
                        ch, font=font, fill=RED if is_hot else INK)
            lefts.append(cell[0])
            offset += w
        return lefts, x + offset

    def bracket(self, x1, x2, y, color, tick=9):
        self.d.line((x1, y - tick, x1, y), fill=color, width=2)
        self.d.line((x2, y - tick, x2, y), fill=color, width=2)
        self.d.line((x1, y, x2, y), fill=color, width=2)

    def arrow(self, x1, x2, y, color):
        self.d.line((x1, y, x2, y), fill=color, width=5)
        self.d.polygon([(x2, y), (x2 - 15, y - 9), (x2 - 15, y + 9)], fill=color)

    def save(self, name):
        out = ROOT / 'assets' / name
        out.parent.mkdir(parents=True, exist_ok=True)
        self.image.save(out)
        print(f'{out.name}: {self.image.width}x{self.image.height}; '
              f'{len(self.boxes)} text boxes; checks passed')


def draw():
    s = Sheet(1560, 790)
    t = s.text
    t(60, 30, '同一个文件，两个名字', 40)
    t(62, 96, '修前 path 没读，候选为空、回去查索引；补上 path 之后，名字还是 URL 末尾那一段。', 23, MUTED)
    s.d.line((60, 152, 1500, 152), fill=LINE, width=2)

    t(60, 182, '补上 path：位置有了，名字是摘要', 25)
    lefts, end = s.ruler(60, 236, URI, 1432, hot=range(NAME_FIRST, len(URI)))
    s.bracket(lefts[0], end, 306, MUTED)
    t(60, 312, '位置：整条 URL 指向那个文件', 22, MUTED)
    s.bracket(lefts[NAME_FIRST], end, 362, RED)
    t(lefts[NAME_FIRST], 368, '名字：Link.filename 取最后一段', 21, RED)
    t(60, 416, '尾段不以 .whl 结尾 → is_wheel 为假 → CandidateNotFound', 23, RED)

    t(60, 470, '再让 name 当名字：复制一份，尾段就对上了', 25)
    t(60, 504, '磁盘上的原件', 21, MUTED)
    t(60, 540, SOURCE, 23, MUTED)
    s.arrow(552, 672, 554, TEAL)
    t(560, 504, 'copyfile', 21, TEAL)
    t(760, 504, '副本：尾段就是 name 字段', 21, TEAL)
    t(760, 540, STAGED, 23, TEAL)

    t(60, 604, 'unearth 只看到副本：判 is_wheel、选解压器，都按它的尾段。', 21, MUTED)
    t(60, 640, '原件字节不动；哈希校验落在副本上；缓存身份仍是原 link.url。', 21, MUTED)
    t(60, 706, '基准：path 相对 pylock.toml 的父目录（locks/）拼，不是 cwd。', 21, MUTED)
    s.save('fig1_two_names.png')


draw()
