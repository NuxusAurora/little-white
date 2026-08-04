# -*- coding: utf-8 -*-
"""Generate 小白 (line-dog Maltese style) sprite frames for the desktop pet.

Character notes (based on the 线条小狗 Maltese):
- round, slightly flattened head; small droopy ears at the cheeks
- tiny dot eyes placed high and wide apart; small round nose; "ω" cat mouth
- small fluffy cloud-like body with short stubby legs; short hooked tail

Run:  python sprites.py
Output: sprites/*.png  (transparent RGBA frames)
"""

import math
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sprites")

SS = 1  # draw at the final logical size (all drawing coords are logical px)
W, H = 190 * SS, 180 * SS

BLACK = (28, 28, 28, 255)
WHITE = (255, 255, 255, 255)
PINK = (255, 166, 176, 150)
RED = (255, 92, 138, 255)
BLUE = (125, 185, 255, 255)
ZZZ_COLOR = (122, 140, 210, 255)

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]

# head geometry (logical px)
HX, HY, HRX, HRY = 95, 62, 56, 50


def _font(size):
    for p in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def new_canvas():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def save(img, name):
    if SS != 1:
        img = img.resize((W // SS, H // SS), Image.LANCZOS)
    os.makedirs(OUT, exist_ok=True)
    img.save(os.path.join(OUT, name))
    print("saved", name)


def lw(draw, p1, p2, width, fill):
    """Line with round caps."""
    draw.line([p1, p2], fill=fill, width=width, joint="curve")
    r = width / 2.0
    for px, py in (p1, p2):
        draw.ellipse([px - r, py - r, px + r, py + r], fill=fill)


def outline_line(draw, p1, p2, width, fill=WHITE, outline=BLACK, ol=3):
    lw(draw, p1, p2, width + ol * 2, outline)
    lw(draw, p1, p2, width, fill)


def ellipse(draw, cx, cy, rx, ry, fill=WHITE, outline=BLACK, width=4):
    draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry],
                 fill=fill, outline=outline, width=width)


def circle(draw, cx, cy, r, fill=BLACK, outline=None, width=3):
    if outline:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                     fill=fill, outline=outline, width=width)
    else:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)


def rcap(img, cx, cy, rx, ry, angle, fill=WHITE, outline=BLACK, width=4):
    """Rotated capsule (rounded rectangle) with outline -- floppy ears."""
    pad = int(width * 2 + 6)
    tw, th = int(2 * rx) + pad, int(2 * ry) + pad
    tmp = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(tmp)
    d.rounded_rectangle([width, width, tw - 1 - width, th - 1 - width],
                        radius=rx, fill=fill, outline=outline, width=width)
    if angle:
        tmp = tmp.rotate(angle, resample=Image.BICUBIC, expand=True)
    img.alpha_composite(tmp, (int(cx - tmp.width / 2), int(cy - tmp.height / 2)))


def ears(img, angle=12, dy=0):
    """Small droopy ears at the cheeks (drawn before the head)."""
    rcap(img, 36, 74 + dy, 15, 16, -angle)
    rcap(img, 154, 74 + dy, 15, 16, angle)


def head(img, draw, cx=HX, cy=HY, rx=HRX, ry=HRY):
    ellipse(draw, cx, cy, rx, ry)


def fluffy_body(draw, cx=95, cy=138, rx=50, ry=34, bump=5.0):
    """Cloud-like body with a wavy (fluffy) top edge."""
    pts = []
    n = 72
    for i in range(n):
        a = i * math.tau / n
        s, c = math.sin(a), math.cos(a)
        extra = 0.0
        if s > 0.18:
            extra = bump * (0.5 + 0.5 * math.sin(3 * a + 0.8))
        pts.append((cx + (rx + extra * 0.55) * c,
                    cy - (ry + extra) * s))
    draw.polygon(pts, fill=WHITE, outline=BLACK, width=4)


def legs(draw, l1=(74, 157), l2=(116, 157), rx=8, ry=9):
    ellipse(draw, l1[0], l1[1], rx, ry)
    ellipse(draw, l2[0], l2[1], rx, ry)


def tail(draw, base=(50, 134), tip=(43, 118), ball=None, up=True):
    outline_line(draw, base, tip, 8)
    circle(draw, tip[0], tip[1] - 2, 5)


def dot_eyes(draw, cx=HX, y=62, spread=34, r=3.5):
    circle(draw, cx - spread, y, r)
    circle(draw, cx + spread, y, r)


def happy_closed_eyes(draw, cx=HX, y=62, spread=34):
    for dx in (-spread, spread):
        draw.arc([cx + dx - 6, y - 5, cx + dx + 6, y + 5], 160, 340,
                 fill=BLACK, width=4)


def surprised_eyes(draw, cx, y, spread=16):
    for dx in (-spread, spread):
        ellipse(draw, cx + dx, y, 7, 8, fill=WHITE, outline=BLACK, width=3)
        circle(draw, cx + dx, y + 1, 3)


def nose_mouth(draw, cx=HX, y_nose=84, mouth="omega", mouth_open=False):
    circle(draw, cx, y_nose, 3.5)
    if mouth_open:
        ellipse(draw, cx, y_nose + 9, 5, 6, fill=BLACK)
    elif mouth == "omega":
        # classic "ω" cat mouth: two small arcs under the nose
        draw.arc([cx - 8, y_nose + 10, cx - 1, y_nose + 17], 325, 144,
                 fill=BLACK, width=3)
        draw.arc([cx + 1, y_nose + 10, cx + 8, y_nose + 17], 35, 215,
                 fill=BLACK, width=3)
    else:
        draw.arc([cx - 6, y_nose + 9, cx + 6, y_nose + 15], 20, 160,
                 fill=BLACK, width=3)


def blush(draw, cx=HX, y=76, spread=23):
    ellipse(draw, cx - spread, y, 8, 4.5, fill=PINK)
    ellipse(draw, cx + spread, y, 8, 4.5, fill=PINK)


def standing(img, draw, bob=0, blink=False, wag=False, ears_angle=12,
             leg1=(74, 157), leg2=(116, 157), body_cy=138):
    tail(draw, up=True, ball=True)
    legs(draw, leg1, leg2)
    fluffy_body(draw, cy=body_cy - bob)
    ears(img, angle=ears_angle, dy=-bob // 2)
    head(img, draw, cy=HY - bob)
    nose_mouth(draw, y_nose=84 - bob)
    if blink:
        happy_closed_eyes(draw, y=62 - bob)
    else:
        dot_eyes(draw, y=62 - bob)


# ---------------------------------------------------------------------------
# Poses
# ---------------------------------------------------------------------------

def idle(blink=False, wag=False):
    img, d = new_canvas()
    standing(img, d, blink=blink, wag=wag, ears_angle=14)
    save(img, "idle_0.png" if not blink and not wag else
         ("idle_1.png" if blink else "idle_2.png"))


def walk(frame):
    img, d = new_canvas()
    phase = math.sin(frame * math.pi / 2)
    bob = 2 if abs(phase) > 0.5 else 0
    l1 = (74 + int(4 * phase), 157 - int(3 * phase))
    l2 = (116 - int(4 * phase), 157 + int(3 * phase))
    standing(img, d, bob=bob, ears_angle=14 + int(4 * phase),
             leg1=l1, leg2=l2)
    save(img, "walk_%d.png" % frame)


def sleep():
    for s, name in [(0.0, "sleep_0.png"), (0.04, "sleep_1.png")]:
        img, d = new_canvas()
        grow = 1.0 + s
        # curled tail on the ground
        outline_line(d, (74, 158), (60, 150), 7)
        outline_line(d, (60, 150), (62, 140), 7)
        # flat body
        ellipse(d, 92, 148, int(56 * grow), int(26 * grow))
        # ear lying flat
        rcap(img, 92, 126, 13, 20, -75)
        # resting head
        ellipse(d, 118, 116, 46, 38)
        happy_closed_eyes(d, 126, 110, 13)
        circle(d, 126, 128, 3)
        draw_arc = d
        draw_arc.arc([120, 132, 132, 138], 20, 160, fill=BLACK, width=3)
        # Zzz
        d.text((150, 70), "Z", font=_font(24), fill=ZZZ_COLOR)
        d.text((166, 52), "z", font=_font(18), fill=ZZZ_COLOR)
        d.text((178, 38), "z", font=_font(13), fill=ZZZ_COLOR)
        save(img, name)


def drag():
    img, d = new_canvas()
    outline_line(d, (52, 138), (38, 128), 7)          # tail trailing
    circle(d, 37, 126, 4)
    ellipse(d, 80, 162, 8, 6)                         # dangling legs
    ellipse(d, 112, 163, 8, 6)
    fluffy_body(draw=d, cx=92, cy=146, rx=56, ry=28, bump=3.5)
    rcap(img, 88, 102, 13, 18, 55)                    # ears blown back
    rcap(img, 148, 102, 13, 18, -55)
    head(img, d, cx=126, cy=108, rx=44, ry=38)
    surprised_eyes(d, 128, 100, 15)
    nose_mouth(d, 128, 120, mouth="omega", mouth_open=True)
    ellipse(d, 76, 92, 6, 9, fill=BLUE)               # sweat drop
    save(img, "drag.png")


def wave():
    img, d = new_canvas()
    standing(img, d, blink=False, wag=True, ears_angle=10)
    # raised paw
    outline_line(d, (118, 128), (140, 96), 10)
    ellipse(d, 144, 90, 9, 10)
    save(img, "wave.png")


def jump():
    img, d = new_canvas()
    up = 16
    outline_line(d, (50, 134 - up), (42, 116 - up), 8)
    circle(d, 41, 114 - up, 5)
    ellipse(d, 82, 148 - up, 7, 6)                    # tucked legs
    ellipse(d, 108, 148 - up, 7, 6)
    fluffy_body(draw=d, cy=138 - up, bump=5.0)
    ears(img, angle=4, dy=-up // 2)
    head(img, d, cy=HY - up)
    nose_mouth(d, y_nose=84 - up, mouth_open=True)
    happy_closed_eyes(d, y=62 - up)
    save(img, "jump.png")


def sit():
    img, d = new_canvas()
    outline_line(d, (66, 156), (56, 144), 7)          # tail on the ground
    circle(d, 55, 142, 4)
    # front legs as little columns
    rcap(img, 76, 152, 9, 13, 0)
    rcap(img, 114, 152, 9, 13, 0)
    fluffy_body(draw=d, cx=95, cy=148, rx=52, ry=36, bump=4.0)
    ears(img, angle=16)
    head(img, d)
    nose_mouth(d)
    dot_eyes(d)
    save(img, "sit.png")


def heart():
    img = Image.new("RGBA", (120, 112), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([18, 10, 58, 50], fill=RED)
    d.ellipse([62, 10, 102, 50], fill=RED)
    d.polygon([(12, 40), (108, 40), (60, 104)], fill=RED)
    d.ellipse([42, 18, 62, 38], fill=(255, 190, 205, 255))
    save(img, "heart.png")


def main():
    idle()
    idle(blink=True)
    idle(wag=True)
    for i in range(4):
        walk(i)
    sleep()
    drag()
    wave()
    jump()
    sit()
    heart()
    print("all sprites done ->", OUT)


if __name__ == "__main__":
    main()
