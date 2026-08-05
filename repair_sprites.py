# -*- coding: utf-8 -*-
"""修复开口线条抠图的小工具：把被误删的内部透明区域补成白色。

原理：线条小狗的轮廓有开口时，flood-fill 白色抠图会把白底从开口处漏进
身体内部，把内部区域也删成透明。内部空洞四周全是轮廓线（有色像素），
而真正的外部背景周围没有这么多轮廓，所以可以用局部密度区分：

    一个透明像素的 NxN 邻域（默认 5x5）内，若有 >= THRESH 个有色
    （不透明）像素，就把它改成不透明白色。

执行方式：反复执行上述规则，直到某一轮补白为 0 px（已收敛）才停止。
刚补上的白像素会参与下一轮的邻域计数，所以较大的空洞也能逐步填满。
收敛后还会再做两步收尾：形态学闭合封住 1~2px 细缝，并把所有被可见
像素（alpha >= 96，桌宠显示阈值）完全包围的透明/半透明区域补成白色，
包括 alpha 41~95 的“半透明小点”。这些都只发生在主体内部，不影响外圈
抗锯齿边缘。另外还有一条“白黑接壤”规则：一个透明像素只要同时与白色
像素和黑色像素接壤，就把它变成白色（填补黑轮廓与白色身体之间的细缝）。
对 AI 抠图把身体内部整片抠空的情况，可加大 `--close-kernel`（如 15）用
闭运算把轮廓开口封住后再填洞。
只依赖 Pillow，任何 Python 环境都能跑；脚本开头还会自动切到 dogs 环境。

用法：
    python repair_sprites.py image.png
    python repair_sprites.py some_dir/              # 递归处理目录下所有 PNG
    python repair_sprites.py --dry sprites/home     # 只统计，不写文件
    python repair_sprites.py --win 5 --thresh 14 a.png b.png
    python repair_sprites.py --max-pass 200 sprites/wave/   # 轮数上限
    python repair_sprites.py --close-kernel 15 sprites/wave/     # 大核封口填洞
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys

from PIL import Image, ImageChops, ImageFilter, ImageOps


def _ensure_dogs_env():
    """开头自动切换：如果当前不是 dogs conda 环境，就用 dogs 环境的
    Python 重新执行本脚本（和 run.sh 里 `conda activate dogs` 等价）。"""
    if os.path.basename(getattr(sys, "prefix", "")) == "dogs":
        return
    conda = shutil.which("conda")
    if not conda:
        return
    try:
        base = subprocess.check_output(
            [conda, "info", "--base"], text=True).strip()
        env_py = os.path.join(base, "envs", "dogs", "bin", "python")
    except Exception:
        return
    if os.path.exists(env_py):
        print("自动切换到 dogs 环境运行...", flush=True)
        os.execv(env_py, [env_py] + sys.argv)


_ensure_dogs_env()


def collect(paths):
    """把文件/目录参数展开成 PNG 文件列表（目录递归）。"""
    files = []
    for p in paths:
        if os.path.isdir(p):
            files.extend(glob.glob(os.path.join(p, "**", "*.png"), recursive=True))
        elif os.path.isfile(p):
            files.append(p)
    return sorted(set(files))


def _box_count(alpha, win, alpha_min):
    """返回一张 L 图：每个像素 = win x win 邻域内“有色”像素个数。
    用 0/1 掩码，邻域和最大 win*win，8 位不会截断；边界按透明（0）补齐。"""
    pad = win // 2
    mask = alpha.point(lambda a: 1 if a > alpha_min else 0)
    padded = ImageOps.expand(mask, border=pad, fill=0)
    count = padded.filter(ImageFilter.Kernel(
        (win, win), [1] * (win * win), scale=1, offset=0))
    return count.crop((pad, pad, pad + alpha.width, pad + alpha.height))


def _colorless_mask(im, alpha_min=40, gray_spread=24):
    """可填充掩码：alpha <= alpha_min 的透明像素，或 alpha 在 (alpha_min, 96)
    之间的半透明灰色像素（通道色差 <= gray_spread）——半透明灰也当作
    “无色”可被补白（但邻域计数时仍算有色，避免削弱轮廓屏障）。"""
    r, g, b, a = im.split()
    base = a.point(lambda v: 255 if v <= alpha_min else 0)
    semi = a.point(lambda v: 255 if alpha_min < v < 96 else 0)
    spread = ImageChops.subtract(
        ImageChops.lighter(r, ImageChops.lighter(g, b)),
        ImageChops.darker(r, ImageChops.darker(g, b)))
    gray = spread.point(lambda v: 255 if v <= gray_spread else 0)
    return ImageChops.add(base, ImageChops.multiply(semi, gray))


def repair_file(path, win=5, thresh=14, alpha_min=40, dry_run=False,
                max_pass=1000, close_kernel=5, gray_spread=24):
    """修复单个图片：密度规则反复执行到收敛，再形态学封缝 + 填包围洞
    （含半透明小点）。返回 (每轮补白数, 收尾补的像素数)。"""
    im = Image.open(path).convert("RGBA")
    per_pass = []
    for _ in range(max_pass):
        colorless = _colorless_mask(im, alpha_min, gray_spread)
        alpha = im.getchannel("A")
        count = _box_count(alpha, win, alpha_min)
        cand = count.point(lambda c: 255 if c >= thresh else 0)
        hole = ImageChops.multiply(cand, colorless)  # 无色且邻域密集 -> 补白
        n = hole.histogram()[255]
        per_pass.append(n)
        if n == 0:
            break                                     # 本轮没补任何像素 = 收敛
        rgb = im.convert("RGB")
        white = Image.new("RGB", im.size, (255, 255, 255))
        new_rgb = Image.composite(white, rgb, hole)
        new_alpha = ImageChops.add(alpha, hole)
        im = Image.merge("RGBA", (*new_rgb.split(), new_alpha))
    else:
        print("  警告：达到最大轮数 %d 仍未收敛" % max_pass)

    # 收尾：封住细缝 + 填掉所有被可见像素包围的透明/半透明区域
    enclosed_filled = _seal_and_fill(im, alpha_min, close_kernel)
    # 白黑接壤规则：透明像素同时挨着白色和黑色 -> 变白
    enclosed_filled += _fill_bw_gap(im)

    if not dry_run and (sum(per_pass) or enclosed_filled):
        im.save(path)
    return per_pass, enclosed_filled


def _seal_and_fill(im, alpha_min=40, kernel=5):
    """形态学闭合（封细缝）+ 填包围洞（含半透明小点），反复直到不再变化。
    原地修改 im；返回一共补了多少像素。"""
    from PIL import ImageDraw
    total = 0
    while True:
        alpha = im.getchannel("A")
        visible_min = 96    # 桌宠显示阈值：alpha >= 96 才算可见/有色
        mask = alpha.point(lambda a: 255 if a >= visible_min else 0)
        closed = mask.filter(ImageFilter.MaxFilter(kernel)) \
                     .filter(ImageFilter.MinFilter(kernel))     # 闭运算
        gap = ImageChops.subtract(closed, mask)                 # 被封住的细缝
        n1 = gap.histogram()[255]
        if n1:
            gpix = gap.load()
            pts = [(x, y) for y in range(im.height) for x in range(im.width)
                   if gpix[x, y] == 255]
            ImageDraw.Draw(im).point(pts, fill=(255, 255, 255, 255))
            total += n1
        n2 = _fill_enclosed_holes(im, visible_min)
        total += n2
        if n1 == 0 and n2 == 0:
            break
    return total


def _fill_bw_gap(im, white_min=230, black_max=60, visible_min=96,
                 max_iter=50):
    """白黑接壤规则：透明像素（alpha < visible_min）只要 8-邻域里同时有
    白色像素和黑色像素，就把它改成不透明白色。反复执行直到收敛。"""
    from PIL import ImageDraw

    total = 0
    for _ in range(max_iter):
        r, g, b, a = im.split()
        am = a.point(lambda v: 255 if v >= visible_min else 0)

        def ge(ch):
            return ch.point(lambda v: 255 if v >= white_min else 0)
        white = ImageChops.multiply(ImageChops.multiply(
            ImageChops.multiply(ge(r), ge(g)), ge(b)), am)

        def le(ch):
            return ch.point(lambda v: 255 if v <= black_max else 0)
        black = ImageChops.multiply(ImageChops.multiply(
            ImageChops.multiply(le(r), le(g)), le(b)), am)

        has_white = white.filter(ImageFilter.MaxFilter(3))
        has_black = black.filter(ImageFilter.MaxFilter(3))
        trans = a.point(lambda v: 255 if v < visible_min else 0)
        cand = ImageChops.multiply(
            ImageChops.multiply(trans, has_white), has_black)
        n = cand.histogram()[255]
        if n == 0:
            break
        cpix = cand.load()
        pts = [(x, y) for y in range(im.height) for x in range(im.width)
               if cpix[x, y] == 255]
        ImageDraw.Draw(im).point(pts, fill=(255, 255, 255, 255))
        total += n
    return total


def _fill_enclosed_holes(im, visible_min=96):
    """把被可见像素（alpha >= visible_min）完全包围的透明/半透明区域
    填成白色；返回补了多少像素。"""
    from collections import deque

    alpha = im.getchannel("A")
    w, h = alpha.size
    mask = alpha.point(lambda a: 1 if a >= visible_min else 0)
    pix = mask.load()

    visited = bytearray(w * h)        # 1 = 透明且与图片边缘连通（真背景）
    q = deque()

    def mark(y, x):
        idx = y * w + x
        if visited[idx] == 0 and pix[x, y] == 0:
            visited[idx] = 1
            q.append((y, x))

    for y in range(h):
        mark(y, 0)
        mark(y, w - 1)
    for x in range(w):
        mark(0, x)
        mark(h - 1, x)
    while q:
        y, x = q.popleft()
        if y > 0:
            mark(y - 1, x)
        if y < h - 1:
            mark(y + 1, x)
        if x > 0:
            mark(y, x - 1)
        if x < w - 1:
            mark(y, x + 1)

    pts = [(x, y) for y in range(h) for x in range(w)
           if visited[y * w + x] == 0 and pix[x, y] == 0]
    if not pts:
        return 0
    from PIL import ImageDraw
    ImageDraw.Draw(im).point(pts, fill=(255, 255, 255, 255))
    return len(pts)


def main():
    ap = argparse.ArgumentParser(
        description="把透明空洞补成白色并反复执行直到收敛（补白为 0 px）。")
    ap.add_argument("paths", nargs="*", help="图片文件或目录（目录会递归）")
    ap.add_argument("--win", type=int, default=5, help="邻域窗口边长（奇数），默认 5")
    ap.add_argument("--thresh", type=int, default=14, help="邻域内有色像素阈值，默认 14")
    ap.add_argument("--alpha-min", type=int, default=40, help="alpha 超过它算有色，默认 40")
    ap.add_argument("--max-pass", type=int, default=1000,
                    help="最大轮数上限（防止意外死循环），默认 1000")
    ap.add_argument("--close-kernel", type=int, default=5,
                    help="形态学闭运算核大小（封轮廓开口），默认 5；"
                         "AI 抠图把身体整片抠空时可调大到 15")
    ap.add_argument("--gray-spread", type=int, default=24,
                    help="半透明灰色判定：通道色差上限，默认 24")
    ap.add_argument("--dry", action="store_true", help="只统计不写文件")
    args = ap.parse_args()

    if not args.paths:
        ap.print_help()
        return
    if args.win % 2 == 0:
        print("错误：--win 需要奇数（如 5）")
        return
    if args.max_pass < 1:
        print("错误：--max-pass 至少为 1")
        return

    files = collect(args.paths)
    if not files:
        print("没有找到 PNG 文件")
        return

    total = 0
    for f in files:
        per_pass, enclosed = repair_file(
            f, args.win, args.thresh, args.alpha_min,
            args.dry, args.max_pass, args.close_kernel, args.gray_spread)
        n = sum(per_pass)
        if n:
            print("%s: 每轮补白 %s，共 %d px，%d 轮后收敛" % (
                f, per_pass, n, len(per_pass)))
        if enclosed:
            print("%s: 填掉完全包围的洞 %d px" % (f, enclosed))
        total += n
    print("完成：%d 个文件，共补白 %d px%s" % (
        len(files), total, " (dry run，未写文件)" if args.dry else ""))


if __name__ == "__main__":
    main()
