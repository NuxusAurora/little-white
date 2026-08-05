# -*- coding: utf-8 -*-
"""统一精灵图里的白色：把所有近白色的可见像素统一成纯白 (255,255,255)。

背景：AI 抠图 / flood-fill 修复后，身体内部的白色深浅不一（180~255 甚至
更低，含边缘的半透明灰边），而且透明度也不一致（有的 alpha=255 很亮，
有的 alpha 200~254 半透明偏暗）。本工具把所有近白可见像素统一成纯白
(255,255,255) 且 alpha=255，亮度完全一致；其它颜色（黑色轮廓、粉色爱心、
棕色蛋糕等）不受影响。

判定“近白”：RGB 三个通道都 >= WHITE_MIN，且通道间最大色差 <= SPREAD，
且 alpha >= ALPHA_MIN（桌宠显示阈值）。色差条件用来保护粉色/棕色等
浅色细节（它们有一个通道明显偏低）。

只依赖 Pillow，脚本开头自动切到 dogs 环境。

用法：
    python unify_white.py image.png
    python unify_white.py some_dir/                    # 递归处理目录下所有 PNG
    python unify_white.py sprites/                     # 一次统一全部动作
    python unify_white.py --dry sprites/eat/           # 只统计，不写文件
    python unify_white.py --white-min 235 --spread 20 a.png
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys

from PIL import Image, ImageChops


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


def unify_file(path, white_min=180, spread=30, alpha_min=96, dry_run=False):
    """统一单个图片的白色；返回被改成纯白的像素数。"""
    im = Image.open(path).convert("RGBA")
    r, g, b, a = im.split()

    def ge(ch):
        return ch.point(lambda v: 255 if v >= white_min else 0)

    rm, gm, bm = ge(r), ge(g), ge(b)
    am = a.point(lambda v: 255 if v >= alpha_min else 0)
    mx = ImageChops.lighter(r, ImageChops.lighter(g, b))      # 通道最大值
    mn = ImageChops.darker(r, ImageChops.darker(g, b))        # 通道最小值
    spread_ok = ImageChops.subtract(mx, mn) \
        .point(lambda v: 255 if v <= spread else 0)

    mask = ImageChops.multiply(ImageChops.multiply(
        ImageChops.multiply(rm, gm), bm), am)
    mask = ImageChops.multiply(mask, spread_ok)
    # 保护蓝色：B 明显大于 R/G 的像素（如 kuku 的眼泪/水坑）一律不统一成白色
    blueness = ImageChops.subtract(b, ImageChops.lighter(r, g))
    blue_guard = blueness.point(lambda v: 0 if v > 15 else 255)
    mask = ImageChops.multiply(mask, blue_guard)
    n = mask.histogram()[255]

    if n and not dry_run:
        white = Image.new("RGB", im.size, (255, 255, 255))
        new_rgb = Image.composite(white, im.convert("RGB"), mask)
        new_a = ImageChops.add(a, mask)     # 近白可见像素 alpha 提到 255
        # 保留蓝色：蓝色像素（B 明显大于 R/G）alpha 提到 255，
        # 眼泪/水坑等蓝色元素完全不丢、不半透明
        blueness = ImageChops.subtract(b, ImageChops.lighter(r, g))
        blue = blueness.point(lambda v: 255 if v > 20 else 0)
        blue_a = a.point(lambda v: 255 if v > 20 else 0)
        blue_solid = ImageChops.multiply(blue, blue_a)
        full = Image.new("L", im.size, 255)
        new_a = Image.composite(full, new_a, blue_solid)
        im = Image.merge("RGBA", (*new_rgb.split(), new_a))
        im.save(path)
    return n


def main():
    ap = argparse.ArgumentParser(
        description="把所有近白色的可见像素统一成纯白 (255,255,255)。")
    ap.add_argument("paths", nargs="*", help="图片文件或目录（目录会递归）")
    ap.add_argument("--white-min", type=int, default=180,
                    help="RGB 各通道最低值才算近白，默认 180")
    ap.add_argument("--spread", type=int, default=30,
                    help="通道间最大色差，超过则视为彩色不处理，默认 30")
    ap.add_argument("--alpha-min", type=int, default=96,
                    help="alpha 最低值（桌宠显示阈值），默认 96")
    ap.add_argument("--dry", action="store_true", help="只统计不写文件")
    args = ap.parse_args()

    if not args.paths:
        ap.print_help()
        return

    files = collect(args.paths)
    if not files:
        print("没有找到 PNG 文件")
        return

    total = 0
    for f in files:
        n = unify_file(f, args.white_min, args.spread, args.alpha_min, args.dry)
        if n:
            print("%s: 统一 %d px" % (f, n))
        total += n
    print("完成：%d 个文件，共统一 %d px%s" % (
        len(files), total, " (dry run，未写文件)" if args.dry else ""))


if __name__ == "__main__":
    main()
