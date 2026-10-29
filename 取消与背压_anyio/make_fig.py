"""Draw the cancellation/read-state diagram; requires Pillow."""
from pathlib import Path
import os
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE / "assets" / "fig1_cancel_reading.png"
REG = os.environ.get("CJK_FONT", "C:/Windows/Fonts/msyh.ttc")
BOLD = os.environ.get("CJK_FONT_BOLD", "C:/Windows/Fonts/msyhbd.ttc")
W, H = 1600, 1130
PAPER, INK, MUTED = "#ffffff", "#26343e", "#64747c"
LINE, RED, BLUE = "#d5dee3", "#ac4e37", "#296780"
im = Image.new("RGB", (W, H), PAPER)
d = ImageDraw.Draw(im)
boxes = []


def text(x, y, value, size=28, color=INK, bold=False, center=False):
    f = ImageFont.truetype(BOLD if bold else REG, size)
    box = d.textbbox((0, 0), value, font=f)
    width = box[2] - box[0]
    if center:
        x -= width / 2
    pos = (x, y - box[1])
    bounds = d.textbbox(pos, value, font=f)
    assert bounds[0] >= 20 and bounds[1] >= 20 and bounds[2] <= W - 20 and bounds[3] <= H - 20, (value, bounds)
    for old, label in boxes:
        assert not (bounds[0] < old[2] and bounds[2] > old[0] and bounds[1] < old[3] and bounds[3] > old[1]), (value, label)
    boxes.append((bounds, value))
    d.text(pos, value, font=f, fill=color)


def arrow(x1, y1, x2, y2, color=LINE, width=4):
    d.line((x1, y1, x2, y2), fill=color, width=width)
    if y2 > y1:
        d.polygon([(x2, y2), (x2 - 8, y2 - 12), (x2 + 8, y2 - 12)], fill=color)
    elif x2 > x1:
        d.polygon([(x2, y2), (x2 - 12, y2 - 8), (x2 - 12, y2 + 8)], fill=color)


text(80, 54, "取消等待，还要收回读取许可", 46, bold=True)
text(80, 126, "同一次 receive()：开始等待相同，取消后的 transport 状态不同", 27, MUTED)
# Shared path.
for x1, x2, label, detail in [
    (80, 480, "空闲连接", "读取已暂停"),
    (600, 1000, "receive() 开始等待", "resume_reading()"),
    (1120, 1520, "等待被取消", "从 await 抛出取消异常"),
]:
    d.rounded_rectangle((x1, 205, x2, 345), radius=12, outline=LINE, width=2)
    text((x1+x2)/2, 230, label, 30, bold=True, center=True)
    text((x1+x2)/2, 287, detail, 25, MUTED, center=True)
arrow(493, 275, 586, 275)
arrow(1013, 275, 1106, 275)
# Two state cards, intentionally separated by a generous gutter.
for x1, x2, title, color in [(80, 760, "修复前", RED), (840, 1520, "修复后", BLUE)]:
    d.rounded_rectangle((x1, 410, x2, 990), radius=12, outline=LINE, width=2)
    text(x1+36, 447, title, 34, color, bold=True)
    d.line((x1+36, 506, x2-36, 506), fill=LINE, width=2)

text(116, 546, "跳过 await 后的 pause_reading()", 29)
text(116, 605, "本次 receive 已退出，读取仍开启", 28, RED)
text(876, 546, "finally 执行 pause_reading()", 29)
text(876, 605, "本次 receive 已退出，读取已暂停", 28, BLUE)
arrow(420, 659, 420, 705, RED)
arrow(1180, 659, 1180, 705, BLUE)
text(420, 734, "后续数据 → data_received()", 29, center=True)
text(1180, 734, "暂停向 protocol 交付后续数据", 29, center=True)
text(420, 791, "read_queue 持续接收数据", 30, RED, bold=True, center=True)
text(1180, 791, "下一次 receive 可恢复读取", 30, BLUE, bold=True, center=True)
text(420, 902, "应用不消费，Python 队列仍可增长", 25, MUTED, center=True)
text(1180, 902, "连接未关闭，已有数据未清空", 25, MUTED, center=True)
text(80, 1043, "pause_reading 控制交付给 protocol 的读取；它不是关闭连接，也不是立刻叫停对端发送。", 26, MUTED)
OUT.parent.mkdir(parents=True, exist_ok=True)
im.save(OUT)
print(f"{OUT}: {W}x{H}; checked {len(boxes)} text boxes")
