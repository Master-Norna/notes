"""Draw the PDM archive-hash data path; validate every text box before saving."""
from pathlib import Path
import argparse
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
PAPER, INK, MUTED = '#f6f8fa', '#243440', '#566777'
RED, GREEN, LINE = '#b84e52', '#168477', '#d8e0e6'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--font', type=Path, default=Path('C:/Windows/Fonts/msyh.ttc'))
    args = parser.parse_args()
    if not args.font.is_file():
        parser.error('请用 --font 指定微软雅黑字体文件')
    image = Image.new('RGB', (1600, 1000), PAPER)
    draw = ImageDraw.Draw(image)
    boxes = []

    def text(x, y, value, size=25, color=INK):
        font = ImageFont.truetype(str(args.font), size)
        bbox = draw.textbbox((x, y), value, font=font)
        assert 35 <= bbox[0] < bbox[2] <= 1565, (value, bbox)
        assert 20 <= bbox[1] < bbox[3] <= 980, (value, bbox)
        for old, label in boxes:
            overlap = min(bbox[2], old[2]) > max(bbox[0], old[0]) and min(bbox[3], old[3]) > max(bbox[1], old[1])
            assert not overlap, (value, label)
        boxes.append((bbox, value))
        draw.text((x, y), value, font=font, fill=color)

    def card(x, y, title, lines, accent):
        draw.rounded_rectangle((x, y, x+440, y+200), radius=14, fill='white', outline=LINE, width=2)
        draw.rounded_rectangle((x, y, x+6, y+200), radius=3, fill=accent)
        start = len(boxes)
        text(x+25, y+23, title, 27)
        for i, line in enumerate(lines):
            text(x+25, y+86+i*44, line, 23, MUTED)
        for bbox, value in boxes[start:]:
            assert x+20 <= bbox[0] and bbox[2] <= x+420, ('card overflow', value, bbox)
            assert y+15 <= bbox[1] and bbox[3] <= y+185, ('card overflow', value, bbox)

    def arrow(x, y, color):
        draw.line((x, y, x+47, y), fill=color, width=4)
        draw.polygon([(x+47, y), (x+36, y-8), (x+36, y+8)], fill=color)

    text(65, 42, '哈希丢在读入时，不在导出时', 42)
    text(65, 112, '同一份 pylock 输入：archive 中已经保存了文件地址和 hashes', 27, MUTED)
    draw.line((65, 185, 1535, 185), fill=LINE, width=2)
    for y, label, color in [(285, '修复前', RED), (650, '修复后', GREEN)]:
        text(65, y-65, label, 28, color)
        if label == '修复前':
            card(65, y, '读取 archive', ['恢复 url / path', '没有把 hashes 装入候选对象'], color)
            card(580, y, '内部候选对象', ['candidate.hashes = []', '下游看见的是空列表'], color)
            card(1095, y, '两种导出', ['requirements：报缺少哈希', 'pylock：成功，但 hashes 丢失'], color)
        else:
            card(65, y, '读取 archive', ['恢复 url / path', '把每种算法转为 FileHash'], color)
            card(580, y, '内部候选对象', ['candidate.hashes 有值', 'url + file + hash'], color)
            card(1095, y, '两种导出', ['requirements：写出 --hash', 'pylock：保留 archive.hashes'], color)
        arrow(520, y+100, color)
        arrow(1035, y+100, color)
    text(65, 925, 'PDM #3956 · 修复补在两条导出路径共同依赖的读入处', 24, MUTED)
    path = HERE / 'assets/fig1_archive_hashes.png'
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    print(f'{path.name}: {image.width}x{image.height}; {len(boxes)} text boxes checked; no overlap or overflow')


if __name__ == '__main__':
    main()
