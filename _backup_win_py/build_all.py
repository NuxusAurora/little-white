# -*- coding: utf-8 -*-
"""一键重建全部桌宠动画：抠图 + 尺寸统一。

素材位置：
  stickers_src/*.gif   -> 待机动图（like/chan/aini）
  stickers_src/*.png   -> 静态动作（walk/drag/wave/jump/sit）
  source_videos/*.mp4  -> 视频抠图（happy/sleep）

运行：python build_all.py
"""

import make_animated_sprites
import make_sticker_sprites
import make_video_sprites
import normalize_sprites
import pet
import glob
import os


def prune_deleted():
    """Remove sprite files of actions that were deleted from pet_config.json,
    so a rebuild does not resurrect them."""
    cfg = pet.load_config()
    known = set(cfg["groups"].keys())
    removed = 0
    for g in pet.IDLE_ORDER + ["happy", "sleep", "walk", "drag", "wave",
                               "jump", "sit", "eat", "kunkun"]:
        if g in known:
            continue
        for f in glob.glob(os.path.join(pet.SPR, g + "_*.png")) + \
                 glob.glob(os.path.join(pet.SPR, g + ".png")):
            try:
                os.remove(f)
                removed += 1
            except OSError:
                pass
    # sleepb 是「睡觉」的派生呼吸动画：只有 sleep 被删除时才一起清理，
    # 否则重建后刚生成的呼吸帧会被误删
    if "sleep" not in known:
        for f in glob.glob(os.path.join(pet.SPR, "sleepb_*.png")):
            try:
                os.remove(f)
                removed += 1
            except OSError:
                pass
    if removed:
        print("pruned %d frame(s) of deleted actions" % removed)


def ensure_eat_placeholder():
    """「吃蛋糕」素材还没提供，先用占位帧（小白旁边放一块小蛋糕）。"""
    from PIL import Image
    import cake
    path = os.path.join(pet.SPR, "eat_00.png")
    if os.path.exists(path):
        return
    base = Image.open(os.path.join(pet.SPR, "like_00.png")).convert("RGBA")
    cake_img = cake.draw_cake(96)
    base.alpha_composite(cake_img, (base.width - 110, base.height - 120))
    base.save(path)
    print("created eat_00.png placeholder (等待你的吃蛋糕动图)")


def main():
    print("== 0/5 清理已删除动作的残留帧 ==")
    prune_deleted()
    print("== 1/4 静态动作贴纸 ==")
    make_sticker_sprites.main()
    print("== 2/4 待机 GIF 动图 ==")
    make_animated_sprites.main()
    print("== 3/4 视频 AI 抠图 ==")
    make_video_sprites.main()
    print("== 3.5/4 吃蛋糕占位帧 ==")
    ensure_eat_placeholder()
    print("== 4/4 尺寸统一化 ==")
    normalize_sprites.main()
    print("== 4.5/4 睡觉呼吸帧（从归一化后的最后一帧生成，保证对齐） ==")
    from make_video_sprites import make_sleep_breathing
    make_sleep_breathing("sleep_36.png")
    print("== 5/5 再次清理 ==")
    prune_deleted()
    print("全部完成！重启桌宠即可生效。")


if __name__ == "__main__":
    main()
