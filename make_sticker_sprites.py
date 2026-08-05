# -*- coding: utf-8 -*-
"""Build desktop-pet frames from 线条小狗 (Maltese) sticker PNGs.

Source: transparent sticker PNGs from the public Telegram sticker pack
"Maltese puppy life6 (线条小狗) @kal_pc" (s00..s23), for personal use only.

Each selected sticker is cropped to its content, resized to fit the pet
canvas (190x180) and saved under the frame names pet.py expects.
"""

import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "stickers_src")
OUT = os.path.join(HERE, "sprites")

W, H = 190, 180  # logical pet canvas
BOTTOM = 170     # where the character's feet / base should rest


def content_bbox(im):
    px = im.load()
    w, h = im.size
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            if px[x, y][3] > 32:
                xs.append(x)
                ys.append(y)
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def place(src, scale_extra=1.0, y_off=0, align_bottom=True):
    im = Image.open(os.path.join(SRC, src)).convert("RGBA")
    x0, y0, x1, y1 = content_bbox(im)
    im = im.crop((x0, y0, x1, y1))
    bw, bh = im.size
    scale = min(182 / bw, 164 / bh) * scale_extra
    im = im.resize((max(1, int(bw * scale)), max(1, int(bh * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    px = (W - im.width) // 2
    if align_bottom:
        py = BOTTOM - im.height + int(y_off)
    else:
        py = (H - im.height) // 2 + int(y_off)
    canvas.alpha_composite(im, (px, py))
    return canvas


def save(img, name):
    stem = name.split("_")[0]           # idle_0 -> idle, drag -> drag
    d = os.path.join(OUT, stem)         # 每个动作一个文件夹
    os.makedirs(d, exist_ok=True)
    img.save(os.path.join(d, name))
    print("saved", os.path.join(stem, name))


def main():
    # idle: standing on the little speech-bubble base, gentle "breathing"
    idle = place("s00.png")
    save(idle, "idle_0.png")
    save(place("s00.png", scale_extra=1.015), "idle_1.png")
    save(idle, "idle_2.png")

    # walk: side view with a small vertical bounce; base faces LEFT,
    # the pet flips the sprite horizontally when walking right
    for i, dy in enumerate([0, -3, -1, -2]):
        save(place("s06.png", y_off=dy), "walk_%d.png" % i)

    save(place("s10.png"), "drag.png")     # surprised, mouth open
    save(place("s11.png"), "wave.png")     # waving
    save(place("s03.png"), "jump.png")     # happy jump with hearts
    save(place("s15.png"), "sit.png")      # sitting

    # heart overlay: crop the red heart out of the "holding a heart" sticker
    s01 = Image.open(os.path.join(SRC, "s01.png")).convert("RGBA")
    px = s01.load()
    w, h = s01.size
    red = []
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a > 150 and r > 180 and g < 120 and b < 140:
                red.append((x, y))
    if red:
        xs = [p[0] for p in red]
        ys = [p[1] for p in red]
        heart_src = s01.crop((min(xs), min(ys), max(xs) + 1, max(ys) + 1))
        hs = min(56 / heart_src.height, 56 / heart_src.width)
        heart = heart_src.resize(
            (max(1, int(heart_src.width * hs)), max(1, int(heart_src.height * hs))),
            Image.LANCZOS)
        canvas = Image.new("RGBA", (60, 56), (0, 0, 0, 0))
        canvas.alpha_composite(heart, ((60 - heart.width) // 2, (56 - heart.height) // 2))
        save(canvas, "heart.png")
    else:
        print("heart extraction failed, keeping existing heart.png")
    print("done ->", OUT)


if __name__ == "__main__":
    main()
