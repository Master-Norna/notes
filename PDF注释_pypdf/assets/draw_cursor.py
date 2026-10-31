"""Draw the stream boundary, not another chart of the call-count results.
Run from any cwd with Python + Pillow. Font: Microsoft YaHei on Windows.
All text bounds are checked for overlap and canvas overflow before saving.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / 'fig_stream_cursor.png'
W, H = 1600, 1060
im = Image.new('RGB', (W,H), '#fbfcfd')
d = ImageDraw.Draw(im)
INK, MUTED, LINE = '#233641', '#617580', '#c8d3da'
GREEN, RED, BLUE = '#117f75', '#b04f47', '#346d9c'
FONT = Path('C:/Windows/Fonts/msyh.ttc')
assert FONT.exists(), 'Microsoft YaHei required'
boxes = []
def text(x, y, value, size=28, color=INK, center=False):
    font = ImageFont.truetype(str(FONT), size)
    bb = d.textbbox((0,0), value, font=font)
    width, height = bb[2]-bb[0], bb[3]-bb[1]
    if center: x -= width/2
    rect = (x,y,x+width,y+height)
    assert 0 <= rect[0] < rect[2] <= W and 0 <= rect[1] < rect[3] <= H, (value,rect)
    for other, label in boxes:
        assert min(rect[2],other[2])-max(rect[0],other[0]) <= 0 or min(rect[3],other[3])-max(rect[1],other[1]) <= 0, (value,label)
    boxes.append((rect,value))
    d.text((x-bb[0],y-bb[1]),value,font=font,fill=color)

def arrow(points, color=BLUE):
    d.line(points,fill=color,width=3)
    x,y=points[-1]; px,py=points[-2]
    if x>px: tip=[(x,y),(x-12,y-6),(x-12,y+6)]
    elif x<px: tip=[(x,y),(x+12,y-6),(x+12,y+6)]
    elif y>py: tip=[(x,y),(x-6,y-12),(x+6,y-12)]
    else: tip=[(x,y),(x-6,y+12),(x+6,y+12)]
    d.polygon(tip,fill=color)

text(70,48,'跳过 1000 条后：看过下一个字节，不等于消费了它',38)
text(70,112,'以下两行都停在 skip_over_comments 结束时；字节从左向右排列。',26,MUTED)

X, CELL = 670, 104

def tape(y, tokens, color):
    d.rounded_rectangle((70,y,600,y+92),radius=8,fill='#eef2f5',outline=LINE,width=2)
    text(335,y+29,'前 1000 条注释（折叠）',28,MUTED,True)
    text(632,y+29,'…',30,MUTED,True)
    for i, token in enumerate(tokens):
        left=X+i*CELL
        d.rectangle((left,y,left+CELL,y+92),fill='#ffffff' if i==0 else '#f1f4f6',outline=LINE,width=2)
        text(left+CELL/2,y+28,token,30, color if i==0 else MUTED,True)
    # The pointer denotes the position BEFORE the next byte, not its centre.
    arrow([(X,y+152),(X,y+98)],color)
    text(X+20,y+117,'指针在此',26,color)
    # Reading moves to the far side of the first cell; seeking restores it.
    arrow([(X,y-10),(X,y-57),(X+CELL,y-57),(X+CELL,y-10)],BLUE)
    text(940,y-69,'① 探读 1 字节',26,BLUE)
    arrow([(X+CELL,y-9),(X+CELL,y-24),(X,y-24),(X,y-9)],BLUE)
    text(940,y-31,'② 回退 1 字节',26,BLUE)

text(70,206,'A  下一字节是数字：工具返回，交给对象解析器',30,GREEN)
tape(345,['4','2','空格','t','a','i','l'],GREEN)
text(70,518,'随后 read_object 才读取 42，留下空格和 tail。',28,INK)

d.line((70,583,1530,583),fill=LINE,width=2)
text(70,627,'B  下一字节还是 %：在第 1001 条的入口报错',30,RED)
tape(765,['%','x','x','x','…'],RED)
text(1250,793,'正文未读',28,MUTED)
text(70,939,'LimitReachedError：指针退回 % 前；不扫描后面的 100,000 字节正文。',28,INK)
text(70,1001,'图示为最终版行为；1000 是库的处理策略，不是 PDF 规范上限。',24,MUTED)

OUT.parent.mkdir(parents=True,exist_ok=True)
im.save(OUT)
print(f'PASS {len(boxes)} text boxes: no overlap or overflow; {W}x{H}; {OUT}')
