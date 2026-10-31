"""Draw the two figures for the PDM subdirectory article.

fig1 is spatial: one ZIP holds parent, child and decoy; whether the archive
record carries `subdirectory` decides which row the read-back opens.

fig2 is character-level: `&` is data inside a directory name but the parameter
separator inside a fragment, so the same string is either one parameter or two.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
BG, INK, MUTED = '#f7f9fa', '#253642', '#61727d'
RED, TEAL, LINE = '#b95249', '#127b73', '#dbe4e8'
RED_FILL, TEAL_FILL = '#f8e8e6', '#e6f2f1'
FONT = Path('C:/Windows/Fonts/msyh.ttc')
if not FONT.exists():
    raise SystemExit('Requires Microsoft YaHei: C:/Windows/Fonts/msyh.ttc')


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
            assert box[2] <= old[0] or old[2] <= box[0] or box[3] <= old[1] or old[3] <= box[1], (value, label)
        self.boxes.append((box, value))
        self.d.text((x, y), value, font=font, fill=color)

    def card(self, rect):
        self.d.rounded_rectangle(rect, radius=18, fill='white', outline=LINE, width=2)

    def arrow(self, x1, x2, y, color):
        """Horizontal arrow from x1 to x2, head at x2 pointing that way."""
        self.d.line((x1, y, x2, y), fill=color, width=5)
        head = [(x2, y), (x2 - 15, y - 9), (x2 - 15, y + 9)] if x2 < x1 else \
               [(x2, y), (x2 + 15, y - 9), (x2 + 15, y + 9)]
        self.d.polygon(head, fill=color)

    def elbow(self, x_from, y_from, x_mid, y_to, x_to, color):
        """Leave the record sideways, drop to the row, then point at it."""
        self.d.line((x_from, y_from, x_mid, y_from), fill=color, width=5)
        self.d.line((x_mid, y_from, x_mid, y_to), fill=color, width=5)
        self.d.line((x_mid, y_to, x_to, y_to), fill=color, width=5)
        head = [(x_to, y_to), (x_to - 15, y_to - 9), (x_to - 15, y_to + 9)]
        self.d.polygon(head, fill=color)

    def down(self, x, y1, y2, color):
        self.d.line((x, y1, x, y2), fill=color, width=5)
        self.d.polygon([(x, y2), (x - 9, y2 - 15), (x + 9, y2 - 15)], fill=color)

    def cells(self, x, y, chars, h, highlight=(), color=TEAL, fill=TEAL_FILL, size=30):
        """One boxed cell per character; `highlight` marks the cells that matter."""
        font = ImageFont.truetype(str(FONT), size)
        offset = 0
        for i, ch in enumerate(chars):
            width = 34 if ch in 'mw' else 30
            cell = (x + offset, y, x + offset + width, y + h)
            assert 0 <= cell[0] < cell[2] <= self.W and 0 <= cell[1] < cell[3] <= self.H, cell
            hot = i in highlight
            self.d.rectangle(cell, fill=fill if hot else 'white',
                             outline=color if hot else LINE, width=3 if hot else 2)
            inner = self.d.textbbox((0, 0), ch, font=font)
            ch_w, ch_h = inner[2] - inner[0], inner[3] - inner[1]
            self.d.text((cell[0] + (width - ch_w) / 2 - inner[0],
                         cell[1] + (h - ch_h) / 2 - inner[1]), ch, font=font, fill=color if hot else INK)
            offset += width
        return x, offset

    def save(self, name):
        out = ROOT / 'assets' / name
        out.parent.mkdir(parents=True, exist_ok=True)
        self.image.save(out)
        print(f'{out.name}: {self.image.width}x{self.image.height}; {len(self.boxes)} text boxes; checks passed')


def fig1():
    s = Sheet(1560, 820)
    t = s.text
    t(66, 36, '同一份归档、同一个哈希，选择器决定打开谁', 42)
    t(68, 110, '左边是 bundle.zip 里的三个项目，右边是锁文件的两条 archive 记录；箭头指向重新解包时实际选中的那一行。', 24, MUTED)
    s.d.line((66, 176, 1494, 176), fill=LINE, width=2)

    s.card((60, 206, 640, 790))
    t(92, 244, 'bundle.zip', 34)
    for top, path, project, color in [
        (322, '根目录 / pyproject.toml', 'parent · parent-dep', MUTED),
        (474, 'src/a&b / pyproject.toml', 'child · child-dep', TEAL),
        (626, 'src/a / pyproject.toml', 'decoy · decoy-dep', MUTED),
    ]:
        t(92, top, path, 27)
        t(132, top + 50, project, 26, color)
        s.d.line((92, top + 96, 608, top + 96), fill=LINE, width=2)

    s.card((768, 206, 1500, 470))
    t(800, 232, '修复前：archive 表没有选择器', 28, RED)
    t(800, 292, '[packages.archive]', 24)
    t(800, 336, 'url = "…/bundle.zip"', 24, MUTED)
    t(800, 372, 'hashes.sha256 = "…"', 24, MUTED)
    t(800, 414, '重新解包选中根目录：parent', 25, RED)

    s.card((768, 520, 1500, 830))
    t(800, 546, '修复后：写出 subdirectory', 28, TEAL)
    t(800, 604, '[packages.archive]', 24)
    t(800, 644, 'url = "…/bundle.zip"', 24, MUTED)
    t(800, 680, 'subdirectory = "src/a&b"', 24, TEAL)
    t(800, 716, 'hashes.sha256 = "…"', 24, MUTED)
    t(800, 766, '重新解包选中子目录：child', 25, TEAL)

    s.arrow(768, 660, 368, RED)                   # into row 1 (parent)
    s.elbow(768, 690, 704, 520, 652, TEAL)        # drops onto row 2 (child), head pointing left
    s.save('fig1_archive_selection.png')


def fig2():
    s = Sheet(1180, 750)
    t = s.text
    t(56, 36, '同一个 &：目录名里是字符，fragment 里是分隔符', 38)
    s.d.line((56, 118, 1124, 118), fill=LINE, width=2)

    t(56, 178, 'A 写成 %26：一个参数，解码后目录完整', 28, TEAL)
    x0, _ = s.cells(56, 226, '#subdirectory=src/a%26b', 54, highlight=(19, 20, 21))
    s.down(x0 + 19 * 30 + 45, 284, 330, TEAL)
    t(x0 + 19 * 30 + 62, 288, '解码 %26 → &', 20, TEAL)
    s.card((56, 332, 1000, 424))
    t(80, 350, 'subdirectory = "src/a&b"', 24)
    t(80, 388, '解包选中 src/a&b：元数据 child · child-dep', 22, MUTED)

    t(56, 468, 'B 直接写 &：这里断成两条参数，只剩 src/a', 28, RED)
    x1, _ = s.cells(56, 516, '#subdirectory=src/a&b', 54, highlight=(19,), color=RED, fill=RED_FILL)
    cut = x1 + 19 * 30 + 15
    s.down(cut, 574, 620, RED)
    s.d.line((716, 541, 742, 541), fill=MUTED, width=2)   # leader from the cell to its label
    t(748, 528, '参数分隔符', 20, RED)
    s.card((56, 622, 1000, 714))
    t(80, 640, 'subdirectory = "src/a"，第二个参数 b 被丢掉', 24)
    t(80, 678, '解包选中 src/a：元数据 decoy · decoy-dep', 22, MUTED)

    s.save('fig2_subdirectory_encoding.png')


fig1()
fig2()
