# -*- coding: utf-8 -*-
"""蛋糕互动（Linux 版）。

- 右键小白，菜单点「拿取蛋糕」-> 在小白的右侧生成一块蛋糕
- 点击蛋糕本身或点击小白 -> 喂食：蛋糕消失，小白播放「吃蛋糕」->「爱你」
"""

import json
import os
import tkinter as tk

import pet

REQUEST_FILE = os.path.join(pet.HERE, "_cake_request.json")
TOUCH_ZONE = 90          # 小白中心离蛋糕中心多近算「碰到」


def draw_cake(size=64):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = size / 2
    O = (35, 25, 18, 255)
    TOP = (202, 146, 104, 255)
    CHIP = (62, 40, 26, 255)
    CUP = (252, 248, 240, 255)
    CUP_LINE = (128, 118, 108, 255)

    d.ellipse([c - 24, size - 10, c + 24, size - 1], fill=(215, 228, 238, 255),
              outline=O, width=2)
    d.polygon([(c - 13, size - 40), (c + 13, size - 40),
               (c + 18, size - 12), (c - 18, size - 12)],
              fill=CUP, outline=O)
    for dx in (-9.0, -4.5, 0.0, 4.5, 9.0):
        d.line([c + dx, size - 38, c + dx + dx * 0.35, size - 14],
               fill=CUP_LINE, width=2)
    d.ellipse([c - 17, size - 58, c + 17, size - 34], fill=TOP, outline=O)
    d.ellipse([c - 13, size - 52, c + 13, size - 38], fill=TOP)
    for dx, dy in ((-8, -48), (-2, -51), (5, -50), (9, -46), (-5, -44), (3, -44)):
        d.ellipse([c + dx - 3, size + dy, c + dx + 3, size + dy + 4], fill=CHIP)
    return img


class Cake:
    def __init__(self, root, puppy):
        self.root = root
        self.pet = puppy
        self.active = False
        self.cake_x = self.cake_y = 0
        puppy.cake = self

        self.win = tk.Toplevel(root)
        self.win.withdraw()
        cw, ch = 64, 64
        self.cake_img = draw_cake(cw)
        self.label = None
        self.win.geometry("%dx%d+0+0" % (cw, ch))
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg="#000000")
        key_ok = pet._apply_linux_keycolor(self.win)
        self.surface = pet._KeyedSurface(
            self.win, self.label, cw, ch, key_ok=key_ok)

        self._poll_requests()

    # ------------------------------------------------------------- request
    def _poll_requests(self):
        """检测请求文件生成蛋糕。"""
        try:
            if os.path.exists(REQUEST_FILE):
                with open(REQUEST_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                try:
                    os.remove(REQUEST_FILE)
                except OSError:
                    pass
                self.spawn_at(int(data.get("x", 0)), int(data.get("y", 0)))
        except Exception:
            pass
        if self.active:
            if self.touching_pet():
                self.feed()   # 小白碰到蛋糕就自动开吃，不需要点击
        self.root.after(30, self._poll_requests)

    def cake_center(self):
        return self.cake_x + 32, self.cake_y + 32

    def pet_center(self):
        w, h = self.pet.window_size()
        return self.pet.x + w // 2, self.pet.y + h // 2

    def touching_pet(self):
        cx, cy = self.cake_center()
        px, py = self.pet_center()
        return ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5 < TOUCH_ZONE

    # -------------------------------------------------------------- cake
    def spawn_at(self, x, y):
        """在指定位置生成蛋糕（指针居中）。"""
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.cake_x = max(32, min(sw - 32, x - 32))
        self.cake_y = max(32, min(sh - 32, y - 32))
        self.active = True
        self.win.geometry("+%d+%d" % (self.cake_x, self.cake_y))
        self.win.deiconify()
        self.win.lift()
        self.surface.update(self.cake_img, self.cake_x, self.cake_y)
        self.pet.go_to_cake()   # 生成后小白跳过去

    def spawn_near_me(self):
        """右键小白菜单触发：生成在小白面朝方向的前上方。"""
        w, h = self.pet.window_size()
        if self.pet.vx >= 0:     # 面朝右
            x = self.pet.x + w // 2 + 65
        else:                    # 面朝左
            x = self.pet.x - 65
        y = self.pet.y - 80      # 略高于小白头顶
        self.spawn_at(x, y)

    def hide(self):
        self.active = False
        self.win.withdraw()

    def feed(self):
        """碰到蛋糕：蛋糕消失，小白吃蛋糕（两遍）-> 爱你。"""
        if not self.active:
            return
        self.hide()
        self.pet.eat()


def install(root, puppy):
    return Cake(root, puppy)
