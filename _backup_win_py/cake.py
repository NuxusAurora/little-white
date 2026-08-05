# -*- coding: utf-8 -*-
"""蛋糕互动（无桌子版）。

- 在 cmd 里输入 `cake`（项目目录下）-> 在鼠标指针处生成一块蛋糕
- 点击小白 -> 喂食：蛋糕消失，小白播放「吃蛋糕」->「爱你」
"""

import json
import os
import tkinter as tk
import ctypes
from ctypes import wintypes

import pet

REQUEST_FILE = os.path.join(pet.HERE, "_cake_request.json")
_EX_TRANSPARENT = 0x00000020
FEED_ZONE = 200
TOUCH_ZONE = 90          # 小白中心离蛋糕中心多近算「碰到」：跳过去自动开吃


def _raise_top(hwnd):
    """Bring a topmost window above its siblings without stealing focus."""
    if not pet.IS_WIN:
        return
    try:
        ctypes.windll.user32.SetWindowPos(
            hwnd, 0, 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0010)
    except Exception:
        pass


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
        self.was_near = False
        self.follow = False
        puppy.cake = self

        self.win = tk.Toplevel(root)
        self.win.withdraw()
        cw, ch = 64, 64
        self.cake_img = draw_cake(cw)
        self.label = tk.Label(self.win, bg=pet.MAGENTA, bd=0)
        self.label.pack(fill="both", expand=True)
        self.win.geometry("%dx%d+0+0" % (cw, ch))
        self.win.overrideredirect(True)
        if pet.IS_WIN:
            self.win.attributes("-toolwindow", True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=pet.MAGENTA)
        if pet.IS_WIN:
            self.surface = pet._LayeredSurface(
                lambda: pet._root_hwnd(self.win), cw, ch)
        else:
            try:
                self.win.attributes("-transparentcolor", pet.MAGENTA)
            except tk.TclError:
                pass
            self.surface = pet._KeyedSurface(self.win, self.label, cw, ch)
            # Linux 无法点击穿透：直接点蛋糕本身也能喂食
            self.label.bind("<Button-1>", lambda e: self.feed())

        self.heartbeat()
        self._poll_requests()

    # ------------------------------------------------------------- request
    def _poll_requests(self):
        """检测请求文件生成蛋糕；蛋糕存在时跟随鼠标指针（点击穿透）。"""
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
            if self.follow and pet.IS_WIN:
                pt = wintypes.POINT()
                ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
                self.cake_x, self.cake_y = pt.x - 32, pt.y - 32
                self._set_click_through(True)
                self.surface.update(self.cake_img, self.cake_x, self.cake_y)
            else:
                self._set_click_through(False)
            if self.follow:
                near = self.near_pet()
                if near and not self.was_near:
                    self.pet.play_sticker("chan")   # 蛋糕靠近 -> 馋
                self.was_near = near
        self.root.after(30, self._poll_requests)

    def cake_center(self):
        return self.cake_x + 32, self.cake_y + 32

    def pet_center(self):
        w, h = self.pet.window_size()
        return self.pet.x + w // 2, self.pet.y + h // 2

    def near_pet(self):
        cx, cy = self.cake_center()
        px, py = self.pet_center()
        return ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5 < FEED_ZONE

    def touching_pet(self):
        cx, cy = self.cake_center()
        px, py = self.pet_center()
        return ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5 < TOUCH_ZONE

    def _set_click_through(self, on):
        """蛋糕跟随指针时点击穿透，点小狗的动作能透过蛋糕传给小白。"""
        if not pet.IS_WIN:
            return
        hwnd = pet._root_hwnd(self.win)
        ex = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        if on:
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, ex | _EX_TRANSPARENT)
        else:
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, ex & ~_EX_TRANSPARENT)

    # -------------------------------------------------------------- cake
    def spawn_at(self, x, y, follow=False):
        """生成蛋糕；follow=True 时跟随鼠标指针。"""
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.cake_x = max(32, min(sw - 32, x - 32))
        self.cake_y = max(32, min(sh - 32, y - 32))
        self.active = True
        self.follow = follow
        self.win.geometry("+%d+%d" % (self.cake_x, self.cake_y))
        self.win.deiconify()
        self.win.lift()
        _raise_top(pet._root_hwnd(self.win))
        self.surface.update(self.cake_img, self.cake_x, self.cake_y)

    def hide(self):
        self.active = False
        self.was_near = False
        self._set_click_through(False)
        self.win.withdraw()

    def feed(self):
        """点击小白喂食：蛋糕消失，小白吃蛋糕 -> 爱你。"""
        if not self.active:
            return
        self.hide()
        self.pet.eat()

    def heartbeat(self):
        """Tk 会重置分层样式导致点击穿透/不可见，每 100ms 重申。"""
        self.surface.ensure_layered()
        self.root.after(100, self.heartbeat)


def install(root, puppy):
    return Cake(root, puppy)
