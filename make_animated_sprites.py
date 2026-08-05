# -*- coding: utf-8 -*-
"""Extract frames from the WeChat 线条小狗 animated stickers (GIF) and build
uniform desktop-pet animation frames.

Sticker sources (personal use):
  17弹: like.gif (散步), chan.gif (馋), aini.gif (爱你)
  30弹: happy.gif (开心)

Output: sprites/<name>_NN.png, 190x180 transparent frames.
"""

import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "stickers_src")
OUT = os.path.join(HERE, "sprites")

W, H = 190, 180  # pet canvas (logical px)


def union_bbox(gif):
    nf = getattr(gif, "n_frames", 1)
    x0 = y0 = 10 ** 9
    x1 = y1 = -1
    for i in range(nf):
        gif.seek(i)
        fr = gif.convert("RGBA")
        px = fr.load()
        w, h = fr.size
        for y in range(h):
            for x in range(w):
                if px[x, y][3] > 32:
                    if x < x0:
                        x0 = x
                    if x > x1:
                        x1 = x
                    if y < y0:
                        y0 = y
                    if y > y1:
                        y1 = y
    return x0, y0, x1 + 1, y1 + 1


def extract(gif_name, prefix, fps_note="", flip=False):
    path = os.path.join(SRC, gif_name)
    gif = Image.open(path)
    nf = getattr(gif, "n_frames", 1)
    x0, y0, x1, y1 = union_bbox(gif)
    bw, bh = x1 - x0, y1 - y0
    scale = min(184 / bw, 172 / bh)
    nw, nh = max(1, int(bw * scale)), max(1, int(bh * scale))
    print("%s: %d frames, union %dx%d -> %dx%d" % (gif_name, nf, bw, bh, nw, nh))
    frames = []
    for i in range(nf):
        gif.seek(i)
        fr = gif.convert("RGBA").crop((x0, y0, x1, y1))
        fr = fr.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        px = (W - nw) // 2
        py = 172 - nh  # bottom aligned
        canvas.alpha_composite(fr, (px, py))
        if flip:
            canvas = canvas.transpose(Image.FLIP_LEFT_RIGHT)   # 散步帧水平翻转
        name = "%s_%02d.png" % (prefix, i)
        d = os.path.join(OUT, prefix)   # 每个动作一个文件夹
        os.makedirs(d, exist_ok=True)
        canvas.save(os.path.join(d, name))
        frames.append((name, i))
    return frames


def main():
    extract("like.gif", "walk", flip=True)   # like.gif 的帧用作「散步」动作
    extract("chan.gif", "chan")
    extract("aini.gif", "aini")
    print("done ->", OUT)


if __name__ == "__main__":
    main()
