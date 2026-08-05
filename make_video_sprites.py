# -*- coding: utf-8 -*-
"""Turn the user-provided WeChat sticker videos into desktop-pet frames.

Happy  (被摸了): 4b5603ba...mp4  (60fps, dark bg)
Sleep  (睡觉):   3aa682b7...mp4  (32fps, light bg)
Kunkun (困困):   a14414ed...mp4  (18fps, white bg)

Pipeline per video: read frames -> AI matting (rembg) -> union content crop ->
resize onto the 190x180 pet canvas -> save sprites/<prefix>/<prefix>_NN.png.
"""

import os

import cv2
import numpy as np
from PIL import Image
from PIL import ImageFilter
from rembg import new_session, remove

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sprites")
VID = os.path.join(HERE, "source_videos")

W, H = 190, 180


def load_frames(path, step=1):
    cap = cv2.VideoCapture(path)
    frames = []
    i = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        if i % step == 0:
            frames.append(fr)
        i += 1
    cap.release()
    return frames


def crop_frames(frames, box):
    """Crop every frame to (x0, y0, x1, y1) before matting."""
    if not box:
        return frames
    x0, y0, x1, y1 = box
    return [fr[y0:y1, x0:x1] for fr in frames]


def matte(frames, session):
    out = []
    for fr in frames:
        im = Image.fromarray(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB))
        out.append(remove(im, session=session))
    return out


def keep_blue_frames(matted, frames):
    """保留所有蓝色像素：把源帧中 B 明显大于 R/G 的像素强制为不透明，
    并把 RGB 还原成源帧原色（rembg 有时会把蓝色洗浅/当背景）。
    kuku 的蓝色眼泪/水坑每帧都必须保留。"""
    outs = []
    for m, fr in zip(matted, frames):
        arr = np.array(m)
        rgb = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB).astype(int)
        blueness = rgb[..., 2] - np.maximum(rgb[..., 0], rgb[..., 1])
        blue = blueness > 20
        arr[..., 3][blue] = 255
        arr[..., 0][blue] = rgb[..., 0][blue]
        arr[..., 1][blue] = rgb[..., 1][blue]
        arr[..., 2][blue] = rgb[..., 2][blue]
        outs.append(Image.fromarray(arr))
    return outs


def key_white_border(frames):
    """Cut out line-art on a solid white band by flood-filling from the frame
    borders: the white background goes transparent, the black-outlined subject
    (and its white interior) is preserved -- no AI matting gray halos."""
    import numpy as np
    y0, y1 = 10 ** 9, -1
    for fr in frames:
        rowmeans = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY).mean(axis=1)
        ys = np.where(rowmeans > 80)[0]
        if len(ys):
            y0 = min(y0, int(ys.min()))
            y1 = max(y1, int(ys.max()))
    if y1 < 0:
        y0, y1 = 0, frames[0].shape[0]
    outs = []
    from collections import deque
    for fr in frames:
        crop = fr[max(0, y0):y1 + 1, :]
        g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        h, w = g.shape
        # outline + features act as barriers; dilate to close small gaps so
        # the white flood cannot leak into the subject's white interior
        dark = (g < 200).astype(np.uint8) * 255
        barrier = cv2.dilate(dark, np.ones((9, 9), np.uint8))
        white = (g > 218).astype(np.uint8)
        wall = (barrier > 0) | (white == 0)
        bg = np.zeros((h, w), bool)
        q = deque()
        for y in range(h):
            for x in (0, w - 1):
                if not wall[y, x] and not bg[y, x]:
                    bg[y, x] = True
                    q.append((y, x))
        for x in range(w):
            for y in (0, h - 1):
                if not wall[y, x] and not bg[y, x]:
                    bg[y, x] = True
                    q.append((y, x))
        while q:
            y, x = q.popleft()
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w \
                        and not wall[ny, nx] and not bg[ny, nx]:
                    bg[ny, nx] = True
                    q.append((ny, nx))
        # subject = dark core + enclosed white, minus the dilated barrier ring
        ring = (barrier > 0) & (dark == 0)
        alpha = ((dark > 0) | (white > 0) & ~bg) & ~ring
        alpha = (alpha.astype(np.uint8)) * 255
        alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        # drop tiny isolated specks
        n, labels, stats, _ = cv2.connectedComponentsWithStats(alpha, 8)
        keep_ids = {i for i in range(1, n)
                    if stats[i, cv2.CC_STAT_AREA] >= 25}
        cleaned = np.zeros_like(alpha)
        for i in keep_ids:
            cleaned[labels == i] = 255
        bgra = cv2.cvtColor(crop, cv2.COLOR_BGR2RGBA)
        bgra[:, :, 3] = cleaned
        outs.append(Image.fromarray(bgra, "RGBA"))
    return outs


def union_bbox(images):
    x0 = y0 = 10 ** 9
    x1 = y1 = -1
    for im in images:
        alpha = im.getchannel("A")
        bbox = alpha.point(lambda v: 255 if v > 40 else 0).getbbox()
        if not bbox:
            continue
        a, b, c, d = bbox
        x0, y0 = min(x0, a), min(y0, b)
        x1, y1 = max(x1, c), max(y1, d)
    return x0, y0, x1, y1


def clear_prefix(prefix):
    import glob
    for f in glob.glob(os.path.join(OUT, prefix, "*.png")) + \
             glob.glob(os.path.join(OUT, prefix + "_*.png")):
        try:
            os.remove(f)
        except OSError:
            pass


def group_dir(prefix):
    """每个动作一个文件夹：sprites/<prefix>/"""
    d = os.path.join(OUT, prefix)
    os.makedirs(d, exist_ok=True)
    return d


def make_sleep_breathing(base_file, prefix="sleepb", n_frames=16, amplitude=0.011,
                         ms=150):
    """Derive a slow 'breathing' loop from the final asleep frame: the blanket
    rises and falls slightly (scale anchored at the bottom centre)."""
    import math
    scales = tuple(round(1 + amplitude * math.sin(2 * math.pi * i / n_frames), 4)
                   for i in range(n_frames))
    import glob
    base_path = glob.glob(os.path.join(OUT, "**", base_file), recursive=True)
    base = Image.open(base_path[0]).convert("RGBA")
    clear_prefix(prefix)
    for i, s in enumerate(scales):
        nw = max(1, int(round(base.width * s)))
        nh = max(1, int(round(base.height * s)))
        scaled = base.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("RGBA", (base.width, base.height), (0, 0, 0, 0))
        canvas.alpha_composite(scaled, ((base.width - nw) // 2, base.height - nh))
        canvas.save(os.path.join(group_dir(prefix), "%s_%02d.png" % (prefix, i)))
    print("  breathing frames saved (%dms)" % ms)


def save_frames(images, prefix, ms, canvas=(W, H), bottom=172, sharpen=False):
    x0, y0, x1, y1 = union_bbox(images)
    bw, bh = x1 - x0, y1 - y0
    cw, ch = canvas
    scale = min((cw - 6) / bw, (bottom - 8) / bh)
    nw, nh = max(1, int(bw * scale)), max(1, int(bh * scale))
    print("%s: %d frames, union %dx%d -> %dx%d on %dx%d" %
          (prefix, len(images), bw, bh, nw, nh, cw, ch))
    clear_prefix(prefix)
    for i, im in enumerate(images):
        im = im.crop((x0, y0, x1, y1)).resize((nw, nh), Image.LANCZOS)
        if sharpen:
            im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=80, threshold=2))
        out = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        out.alpha_composite(im, ((cw - nw) // 2, bottom - nh))
        out.save(os.path.join(group_dir(prefix), "%s_%02d.png" % (prefix, i)))
    print("  saved with %dms/frame" % ms)


def main():
    import sys
    only = sys.argv[1:] if len(sys.argv) > 1 else None
    # (name, step, ms, sharpen, use_key, crop box, keep_blue)
    # wave/home: 微信视频消息里的白色贴纸框，线条小狗在纯白面板中间
    # 挥手/跑动。线条有开口，flood-fill 会把内部漏掉，改用 rembg AI 抠图。
    jobs = [("happy", 2, 33, False, False, None, False),
            ("sleep", 1, 31, True, False, None, False),
            ("eat", 2, 33, True, True, None, False),
            ("kunkun", 1, 56, True, False, None, False),
            ("wave", 1, 50, True, False, (60, 420, 534, 860), False),
            ("home", 1, 50, True, False, (100, 420, 540, 870), False),
            ("kuku", 1, 66, True, False, (0, 352, 594, 870), True)]
    session = None
    for name, step, ms, sharpen, use_key, crop, keep_blue in jobs:
        if only and name not in only:
            continue
        src = os.path.join(VID, name + ".mp4")
        if not os.path.exists(src):
            print("skip %s (missing %s)" % (name, src))
            continue
        if not use_key and session is None:
            print("loading rembg session...")
            session = new_session("u2net")
        print("processing %s..." % name)
        frames = crop_frames(load_frames(src, step=step), crop)
        processed = key_white_border(frames) if use_key else matte(frames, session)
        if keep_blue:
            processed = keep_blue_frames(processed, frames)
        save_frames(processed, name, ms,
                    canvas=(380, 360), bottom=352, sharpen=sharpen)

    print("done ->", OUT)


if __name__ == "__main__":
    main()
