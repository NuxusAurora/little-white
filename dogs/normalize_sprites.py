# -*- coding: utf-8 -*-
"""一键统一所有动作帧的大小（抠图后处理）。

把每个动作组的内容统一缩放到一致的主体尺寸：
  - 站立/坐姿类：内容高度统一为 TARGET_H
  - 躺姿/宽幅类：内容宽度统一为 TARGET_W（高度自然适配）
输出 380x360 透明帧（显示原生分辨率），底部对齐。

用法：python normalize_sprites.py
"""

import glob
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SPR = os.path.join(HERE, "sprites")

CANVAS_W, CANVAS_H = 380, 360      # display-native canvas
TARGET_W, TARGET_H = 320, 300       # uniform subject box
BOTTOM = 352                        # where feet / base rest

GROUPS = ["like", "chan", "aini", "happy", "sleep",
          "walk", "drag", "wave", "jump", "sit", "eat", "kunkun"]


def group_files(g):
    files = sorted(glob.glob(os.path.join(SPR, g + "_*.png")))
    if not files:
        single = os.path.join(SPR, g + ".png")
        if os.path.exists(single):
            files = [single]
    return files


def content_bbox(im):
    px = im.load()
    w, h = im.size
    x0 = y0 = 10 ** 9
    x1 = y1 = -1
    for y in range(h):
        for x in range(w):
            if px[x, y][3] > 40:
                if x < x0:
                    x0 = x
                if x > x1:
                    x1 = x
                if y < y0:
                    y0 = y
                if y > y1:
                    y1 = y
    return x0, y0, x1 + 1, y1 + 1


def union_bbox(images):
    x0 = y0 = 10 ** 9
    x1 = y1 = -1
    for im in images:
        a, b, c, d = content_bbox(im)
        x0, y0 = min(x0, a), min(y0, b)
        x1, y1 = max(x1, c), max(y1, d)
    return x0, y0, x1, y1


def normalize_group(g):
    files = group_files(g)
    if not files:
        print("skip", g, "(no files)")
        return
    images = [Image.open(f).convert("RGBA") for f in files]
    x0, y0, x1, y1 = union_bbox(images)
    bw, bh = x1 - x0, y1 - y0
    scale = min(TARGET_W / bw, TARGET_H / bh)
    nw, nh = max(1, int(round(bw * scale))), max(1, int(round(bh * scale)))
    print("%-8s content %4dx%-4d -> %4dx%-4d" % (g, bw, bh, nw, nh))
    for im, f in zip(images, files):
        crop = im.crop((x0, y0, x1, y1)).resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        canvas.alpha_composite(crop, ((CANVAS_W - nw) // 2, BOTTOM - nh))
        canvas.save(f)


def clean_specks(g, min_area=40, alpha_min=30, keep_largest_only=False):
    """Remove stray semi-transparent specks outside the main subject.

    keep_largest_only=True keeps just the biggest connected blob (for
    stickers whose floating decorations must be dropped before sizing).
    """
    import cv2
    import numpy as np
    files = group_files(g)
    for f in files:
        im = Image.open(f).convert("RGBA")
        arr = np.array(im)
        a = arr[:, :, 3]
        mask = (a > alpha_min).astype(np.uint8)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        if keep_largest_only:
            keep = ({max(range(1, n), key=lambda i: stats[i, cv2.CC_STAT_AREA])}
                    if n > 1 else set())
        else:
            keep = {i for i in range(1, n)
                    if stats[i, cv2.CC_STAT_AREA] >= min_area}
        new_a = np.zeros_like(a)
        for i in keep:
            new_a[labels == i] = a[labels == i]
        # drop residual semi-transparent neutral-gray background blobs
        r, g, b = arr[:, :, 0].astype(int), arr[:, :, 1].astype(int), arr[:, :, 2].astype(int)
        grayish = (new_a > 30) & (new_a < 225) & (r > 60) & (r < 215) \
            & (np.abs(r - g) < 28) & (np.abs(g - b) < 28)
        new_a[grayish] = 0
        arr[:, :, 3] = new_a
        Image.fromarray(arr).save(f)


def main():
    for g in GROUPS:
        if g == "kunkun":
            # 先把漂浮的黄色气泡清掉，再按小狗主体统一尺寸
            clean_specks(g, keep_largest_only=True)
        normalize_group(g)
        clean_specks(g)
    print("done ->", SPR)


if __name__ == "__main__":
    main()
