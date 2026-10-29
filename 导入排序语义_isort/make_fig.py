"""Draw how grid() loses (or keeps) the trailing comment; validate text boxes."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
PAPER, INK, MUTED = '#f6f8fa', '#243440', '#566777'
RED, GREEN, LINE = '#b84e52', '#168477', '#d8e0e6'


def main():
    font_path = Path('C:/Windows/Fonts/msyh.ttc')
    image = Image.new('RGB', (1600, 1000), PAPER)
    draw = ImageDraw.Draw(image)
    boxes = []

    def text(x, y, value, size=25, color=INK):
        font = ImageFont.truetype(str(font_path), size)
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
            text(x+25, y+90+i*44, line, 23, MUTED)
        for bbox, value in boxes[start:]:
            assert x+20 <= bbox[0] and bbox[2] <= x+420, ('card overflow', value, bbox)
            assert y+15 <= bbox[1] and bbox[3] <= y+185, ('card overflow', value, bbox)

    def arrow(x, y, color):
        draw.line((x, y, x+47, y), fill=color, width=4)
        draw.polygon([(x+47, y), (x+36, y-8), (x+36, y+8)], fill=color)

    text(65, 42, '注释丢在 grid() 的出口', 42)
    text(65, 112, 'isort 把导入行拆成 imports 和 comments，连同语句一起交给折行模式；默认模式就是 grid', 27, MUTED)
    draw.line((65, 185, 1535, 185), fill=LINE, width=2)
    text(65, 225, '输入　from ugly import a, b  # noqa: F401', 26)
    text(65, 268, '配置　force_grid_wrap=2 · multi_line_output=GRID（默认）· line_length=79', 23, MUTED)
    for y, label, color, exit_title, exit_lines in [
        (400, '修复前', RED, '出口直接 return',
         ['f-string 只拼回右括号', 'comments 没人接收 → noqa 丢失']),
        (690, '修复后', GREEN, '出口经 add_to_line()',
         ['未消费的注释接回行尾', 'noqa 保留，lint 干净']),
    ]:
        text(65, y-55, label, 28, color)
        card(65, y, '进入 grid()', ['comments=["noqa: F401"]', '随 imports 一起传入'], color)
        card(580, y, '不触发折行', ['2 个名字、不超 79 列', '折行分支没有执行'], color)
        card(1095, y, exit_title, exit_lines, color)
        arrow(520, y+100, color)
        arrow(1035, y+100, color)
    text(65, 935, '折行分支两版行为相同：注释落在折行处；vertical 等模式进函数即接回注释，均不受影响', 23, MUTED)
    text(1245, 935, 'isort #2675', 23, MUTED)
    path = HERE / 'assets/fig1_grid_comment.png'
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    print(f'{path.name}: {image.width}x{image.height}; {len(boxes)} text boxes checked; no overlap or overflow')


if __name__ == '__main__':
    main()
