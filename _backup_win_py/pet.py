# -*- coding: utf-8 -*-
"""小白桌面宠物 - a floppy-eared white puppy that lives on your desktop.

Run:  python pet.py   (or double-click run.bat)
"""

import os
import random
import ctypes
import glob
import json
import sys
import time

import tkinter as tk
from PIL import Image, ImageTk

HERE = os.path.dirname(os.path.abspath(__file__))
SPR = os.path.join(HERE, "sprites")

MAGENTA = "#ff00fe"          # transparent key color (Windows)
KEY_RGB = (255, 0, 254)      # same key as an RGB tuple (Linux -transparentcolor)
BASE_W, BASE_H = 190, 180    # sprite canvas size
GRAVITY = 1000.0             # px / s^2, v = g*t
JUMP_HEIGHT = 100            # 投喂/跳跃时的弹跳高度（px）

IS_WIN = sys.platform.startswith("win")
IS_LINUX = sys.platform.startswith("linux")

def _seq(prefix, ms):
    files = sorted(glob.glob(os.path.join(SPR, prefix + "_*.png")))
    return [(os.path.splitext(os.path.basename(f))[0], ms) for f in files]


_MS = {"like": 70, "chan": 70, "aini": 70, "happy": 33,
       "sleep": 31, "sleepb": 150, "eat": 33, "kunkun": 56}


def _jump_frames():
    """跳跃动作的显示帧：有 jump.png 用原图；没有就用「馋」的贪吃脸
    （投喂时跳向蛋糕的脸正好匹配），再退而求其次用任意现有帧。"""
    if os.path.exists(os.path.join(SPR, "jump.png")):
        return [("jump", 100), ("jump", 110), ("jump", 180)]
    for base in ("chan_00", "eat_00", "like_00", "idle_0"):
        if os.path.exists(os.path.join(SPR, base + ".png")):
            return [(base, 100), (base, 110), (base, 180)]
    return []


def _seqs():
    """Frame sequences for every group, re-globbed from sprites/ each call so
    deleted actions disappear and re-added ones appear."""
    seqs = {g: _seq(g, ms) for g, ms in _MS.items()}
    seqs["walk"] = [("walk_%d" % i, 105) for i in range(4)
                    if os.path.exists(os.path.join(SPR, "walk_%d.png" % i))]
    seqs["drag"] = [("drag", 120)] if os.path.exists(os.path.join(SPR, "drag.png")) else []
    seqs["wave"] = [("wave", 150)] * 4 if os.path.exists(os.path.join(SPR, "wave.png")) else []
    seqs["jump"] = _jump_frames()
    seqs["sit"] = [("sit", 260)] * 4 if os.path.exists(os.path.join(SPR, "sit.png")) else []
    return seqs


SEQ = _seqs()

IDLE_ORDER = ["like", "chan", "aini"]   # idle plays these in order
ONE_SHOT = {"happy", "wave", "jump", "sit", "eat"}
        # one-shot actions return to idle when finished ("eat" continues to 爱你)
FRAME_NAMES = sorted(os.path.splitext(os.path.basename(f))[0]
                     for f in glob.glob(os.path.join(SPR, "*.png")))

CONFIG_PATH = os.path.join(HERE, "pet_config.json")
DEFAULT_CONFIG = {
    "groups": {
        "like":  {"name": "喜欢", "enabled": True, "category": "normal"},
        "chan":  {"name": "馋",   "enabled": True, "category": "normal"},
        "aini":  {"name": "爱你", "enabled": True, "category": "normal"},
        "happy": {"name": "开心", "enabled": True, "category": "special"},
        "sleep": {"name": "睡觉", "enabled": True, "category": "normal"},
        "walk":  {"name": "散步", "enabled": True, "category": "normal"},
        "drag":  {"name": "被拎", "enabled": True, "category": "special"},
        "wave":  {"name": "挥手", "enabled": True, "category": "normal"},
        "jump":  {"name": "跳跃", "enabled": True, "category": "normal"},
        "sit":   {"name": "坐下", "enabled": True, "category": "normal"},
        "eat":   {"name": "吃蛋糕", "enabled": True, "category": "special"},
        "kunkun": {"name": "困困", "enabled": True, "category": "special"},
    }
}

for _g in DEFAULT_CONFIG["groups"]:
    DEFAULT_CONFIG["groups"][_g]["scale"] = 1.0


def load_config():
    """Read pet_config.json. Only groups actually present in the file exist;
    deleted groups are treated as absent (disabled, hidden from the editor)."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        groups = {}
        for g, d in (data.get("groups") or {}).items():
            if not isinstance(d, dict):
                continue
            try:
                scale = float(d.get("scale", 1.0))
            except (TypeError, ValueError):
                scale = 1.0
            default_cat = DEFAULT_CONFIG["groups"].get(g, {}).get(
                "category", "special")
            groups[g] = {
                "name": str(d.get("name", g)).strip() or g,
                "enabled": bool(d.get("enabled", False)),
                "scale": scale or 1.0,
                "category": str(d.get("category", default_cat)),
            }
        return {"groups": groups}
    except Exception:
        return json.loads(json.dumps(DEFAULT_CONFIG))


def _group_cfg(cfg, g):
    d = cfg.get("groups", {}).get(g)
    if isinstance(d, dict):
        return d
    return {"name": g, "enabled": False, "scale": 1.0, "category": "special"}


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def build_anim(cfg):
    """Build the per-mode frame sequences from the enabled groups."""
    seqs = _seqs()
    anim = {}
    idle = []
    for g in IDLE_ORDER:
        enabled = _group_cfg(cfg, g)["enabled"]
        normal = _group_cfg(cfg, g)["category"] == "normal"
        if enabled and normal:
            idle.extend(seqs[g])
        anim[g] = seqs[g] if enabled else []
    anim["idle"] = idle or next((s for s in seqs.values() if s), [])
    for key in seqs:
        if key not in IDLE_ORDER:
            if key == "sleepb":
                anim[key] = seqs[key] if _group_cfg(cfg, "sleep")["enabled"] else []
            else:
                anim[key] = seqs[key] if _group_cfg(cfg, key)["enabled"] else []
    return anim

_HWND_TOPMOST = -1
_SWP_NOMOVE = 0x0002
_SWP_NOSIZE = 0x0001
_SWP_NOACTIVATE = 0x0010

_ULW_ALPHA = 0x00000002
_AC_SRC_OVER = 0x00
_AC_SRC_ALPHA = 0x01


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_int32),
        ("biHeight", ctypes.c_int32),
        ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 1)]


class _BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte),
        ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


class _LayeredSurface:
    """Per-pixel-alpha layered window: rendering AND hit-testing come from the
    image alpha channel, so transparent pixels are click-through and opaque
    pixels are clickable -- immune to the -transparentcolor DPI hit-test bug."""

    def __init__(self, get_hwnd, width, height):
        self.get_hwnd = get_hwnd
        self.w, self.h = width, height
        self.ensure_layered()
        self.hdc = ctypes.windll.gdi32.CreateCompatibleDC(None)
        bmi = _BITMAPINFO()
        hdr = bmi.bmiHeader
        hdr.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        hdr.biWidth = width
        hdr.biHeight = -height  # top-down
        hdr.biPlanes = 1
        hdr.biBitCount = 32
        hdr.biCompression = 0  # BI_RGB
        hdr.biSizeImage = width * height * 4
        self.bits = ctypes.c_void_p()
        self.hbm = ctypes.windll.gdi32.CreateDIBSection(
            None, ctypes.byref(bmi), 0, ctypes.byref(self.bits), None, 0)
        self.old = ctypes.windll.gdi32.SelectObject(self.hdc, self.hbm)
        self.blend = _BLENDFUNCTION(_AC_SRC_OVER, 0, 255, _AC_SRC_ALPHA)

    def ensure_layered(self):
        # UpdateLayeredWindow requires the WS_EX_LAYERED style. Tk sometimes
        # rewrites the extended style (e.g. when it re-applies -topmost /
        # -toolwindow after mapping), so re-assert it whenever we update.
        user32 = ctypes.windll.user32
        hwnd = self.get_hwnd()
        exstyle = user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
        if not (exstyle & 0x00080000):
            user32.SetWindowLongW(hwnd, -20, exstyle | 0x00080000)

    def update(self, pil_rgba, x, y):
        self.ensure_layered()
        hwnd = self.get_hwnd()
        pre = pil_rgba.convert("RGBa")  # premultiplied alpha
        data = bytearray(pre.tobytes())
        data[0::4], data[2::4] = data[2::4], data[0::4]  # RGBA -> BGRA
        ctypes.memmove(self.bits, bytes(data), len(data))
        ctypes.windll.user32.UpdateLayeredWindow(
            hwnd, None,
            ctypes.byref(_POINT(x, y)),
            ctypes.byref(_SIZE(self.w, self.h)),
            self.hdc,
            ctypes.byref(_POINT(0, 0)),
            0, ctypes.byref(self.blend), _ULW_ALPHA)


def _flatten_key(rgba, key=KEY_RGB, alpha_min=96):
    """Flatten RGBA onto the transparent key color for Linux/X11:
    pixels below the alpha threshold become exactly the key color (click-
    through / transparent), the rest are alpha-blended. Returns an RGB image.
    """
    rgba = rgba.convert("RGBA")
    try:
        import numpy as np
        arr = np.asarray(rgba).astype(np.float32)
        a = (arr[..., 3:4] / 255.0).astype(np.float32)
        flat = arr[..., :3] * a + np.array(key, np.float32) * (1.0 - a)
        flat = np.clip(flat, 0, 255).astype(np.uint8)
        low = (arr[..., 3:4] < alpha_min)
        flat[low.repeat(3, axis=2)] = key
        return Image.fromarray(flat, "RGB")
    except Exception:
        bg = Image.new("RGBA", rgba.size, key + (255,))
        bg.alpha_composite(rgba)
        return bg.convert("RGB")


class _KeyedSurface:
    """Linux/X11 surface: the Tk label shows the sprite flattened onto the
    transparent key color, and `-transparentcolor` keys that color out of the
    window (needs a compositing window manager). Transparent pixels become
    click-through because X11 shapes the window to the visible content."""

    def __init__(self, root, label, width, height):
        self.root = root
        self.label = label
        self.w, self.h = width, height
        self._photo = None

    def ensure_layered(self):
        pass   # no Win32 layered style on Linux

    def update(self, pil_rgba, x, y):
        self._photo = ImageTk.PhotoImage(_flatten_key(pil_rgba))
        self.label.configure(image=self._photo)
        self.root.geometry("+%d+%d" % (int(x), int(y)))


def _enable_dpi_awareness():
    """Make the process DPI aware so the layered window hit-tests 1:1.
    Without this, at 125%+ display scaling most of the transparent window
    becomes click-through (clicks fall through to whatever is underneath)."""
    if not IS_WIN:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _force_topmost(hwnd):
    if not IS_WIN:
        return
    try:
        ctypes.windll.user32.SetWindowPos(
            hwnd, _HWND_TOPMOST, 0, 0, 0, 0,
            _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE)
    except Exception:
        pass


def _root_hwnd(root):
    """The real OS top-level window. Tk's winfo_id() on Windows returns a
    child window of the actual toplevel (class TkTopLevel), and Win32 window
    APIs (layered style, UpdateLayeredWindow, topmost) must target the
    ancestor."""
    hwnd = root.winfo_id()
    if not IS_WIN:
        return hwnd
    try:
        return ctypes.windll.user32.GetAncestor(hwnd, 2)  # GA_ROOT
    except Exception:
        return hwnd


class Pet:
    def __init__(self, root, test_mode=False, start_pos=None):
        self.root = root
        self.base = {}
        for n in FRAME_NAMES:
            p = os.path.join(SPR, n + ".png")
            if os.path.exists(p):
                self.base[n] = Image.open(p)
        self.frames = {}
        self.test_mode = test_mode
        self.test_log = None
        if test_mode:
            self.test_log = open(os.path.join(HERE, "_pet_test.log"), "a", encoding="utf-8")

        self.cfg = load_config()
        self.anim = build_anim(self.cfg)
        self.walk_group = self._find_walk_group()
        try:
            self.cfg_mtime = os.path.getmtime(CONFIG_PATH)
        except OSError:
            self.cfg_mtime = None
            save_config(self.cfg)   # create a visible default config
            self.cfg_mtime = os.path.getmtime(CONFIG_PATH)

        screen_w = root.winfo_screenwidth()
        try:
            dpi = root.winfo_fpixels("1i")
        except Exception:
            dpi = 96.0
        self.scale = max(1.0, round(dpi / 96.0, 2))
        self.photos = {}
        self.build_photos()

        self.mode = "idle"
        self.fi = 0
        self.vx = 0
        self.vy = 0
        self.walk_state = "rest"
        self.walk_until = 0.0
        self.rest_until = 0.0
        self.walk_mode_until = 0.0
        self._y_frac = 0.0
        self._last_grav = 0.0
        self.falling = False
        self._fall_active = False
        self.priority_until_idle = False
        self.eat_flow = False
        self.last_facing = 1
        self._going_cake = False       # 正在跳向蛋糕
        self._cake_chan_wait = False   # 看到蛋糕先播「馋」，播完再跳过去
        self._cake_taken = False       # 空中够到蛋糕：落回地面再开吃
        self._cake_jump_bonus = 0      # 够不到蛋糕时，每次加跳高度（px）
        self.jumping = False           # 物理弹跳中：只受重力
        self._jump_y0 = 0              # 起跳时的 y
        self.drag_off = None
        self._press_time = None
        self._press_pos = None
        self.heart_job = None
        self.heart_visible = False
        self.wake_job = None
        self._asleep = False
        self.sleep_prep = False       # 散步→困困→睡觉 流程进行中
        self.kunkun_plays = 0
        self.sticker_seq = []

        w, h = self.window_size()
        if start_pos is not None:
            x, y = start_pos
        else:
            x = screen_w - w - 60
            y = root.winfo_screenheight() - h - 60
        self.x, self.y = x, y
        self.clamp()
        root.geometry("%dx%d+%d+%d" % (w, h, x, y))

        root.overrideredirect(True)
        if IS_WIN:
            root.attributes("-toolwindow", True)
        root.attributes("-topmost", True)
        root.configure(bg=MAGENTA)
        if not IS_WIN:
            try:
                root.attributes("-transparentcolor", MAGENTA)
            except tk.TclError:
                pass   # 无合成器的 X11/部分 Wayland 环境不支持透明色

        first_idle = self.anim["idle"][0][0]
        self.label = tk.Label(root, image=self.photos[first_idle], bg=MAGENTA, bd=0)
        self.label.pack()
        self.surface = self._make_surface(w, h)
        self.surface.update(self.composite(first_idle), self.x, self.y)

        self.label.bind("<ButtonPress-1>", self.on_press)
        self.label.bind("<B1-Motion>", self.on_drag)
        self.label.bind("<ButtonRelease-1>", self.on_release)
        self.label.bind("<Double-Button-1>", self.on_double)
        self.label.bind("<Button-3>", self.popup_menu)

        self.tick()
        self.keep_topmost()
        self.watch_config()
        self._start_walk_burst()
        self._ensure_fall_loop()
        if not test_mode:
            self.schedule_action(2200)

    # ------------------------------------------------------------- images
    def group_scale(self, name):
        """Per-group manual size factor from pet_config.json."""
        g = name.rsplit("_", 1)[0] if name.rsplit("_", 1)[-1].isdigit() else name
        if g == "sleepb":
            g = "sleep"
        try:
            return float(self.cfg["groups"].get(g, {}).get("scale", 1.0))
        except (TypeError, ValueError):
            return 1.0

    def build_photos(self):
        s = self.scale
        self.photos = {}
        self.frames = {}
        target = (int(BASE_W * s), int(BASE_H * s))
        for name, img in self.base.items():
            if img.size != target:   # hi-res frames (e.g. sleep) keep native size
                img = img.resize(target, Image.LANCZOS)
            gs = self.group_scale(name)
            if gs != 1.0:
                img = self._scale_content(img, gs, target)
            display = img if IS_WIN else _flatten_key(img)
            self.photos[name] = ImageTk.PhotoImage(display)
            self.frames[name] = img
            if name.startswith("walk_") or (
                    self.walk_group and
                    (name == self.walk_group or name.startswith(self.walk_group + "_"))):
                # right-facing variants
                fimg = img.transpose(Image.FLIP_LEFT_RIGHT)
                fdisplay = fimg if IS_WIN else _flatten_key(fimg)
                self.photos[name + "_flip"] = ImageTk.PhotoImage(fdisplay)
                self.frames[name + "_flip"] = fimg

    def _make_surface(self, w, h):
        if IS_WIN:
            return _LayeredSurface(lambda: _root_hwnd(self.root), w, h)
        return _KeyedSurface(self.root, self.label, w, h)

    def _scale_content(self, img, gs, target):
        # cap the zoom so the subject always stays fully inside the window
        px = img.load()
        w, h = img.size
        x0 = y0 = 10 ** 9
        x1 = y1 = -1
        for y in range(h):
            for x in range(w):
                if px[x, y][3] > 40:
                    x0, y0 = min(x0, x), min(y0, y)
                    x1, y1 = max(x1, x), max(y1, y)
        if x1 >= 0:
            tw, th = target
            m = 4  # keep a few px of breathing room
            max_gs = (th - m) / max(1, th - y0)
            max_gs = min(max_gs, (tw - m) / max(1, tw - 2 * x0))
            max_gs = min(max_gs, (tw - m) / max(1, 2 * x1 - tw))
            gs = min(gs, max_gs)
        nw = max(1, int(round(img.width * gs)))
        nh = max(1, int(round(img.height * gs)))
        scaled = img.resize((nw, nh), Image.LANCZOS)
        out = Image.new("RGBA", target, (0, 0, 0, 0))
        out.alpha_composite(scaled, ((target[0] - nw) // 2, target[1] - nh))
        return out

    def composite(self, name):
        img = self.frames[name].convert("RGBA")
        if self.heart_visible:
            heart = self.frames["heart"]
            img.alpha_composite(heart, (int(70 * self.scale), int(8 * self.scale)))
        return img

    def window_size(self):
        return int(BASE_W * self.scale), int(BASE_H * self.scale)

    def set_scale(self, factor):
        self.scale = max(0.7, min(2.6, self.scale * factor))
        self.build_photos()
        self.label.configure(image=self.photos[self.current_frame()])
        w, h = self.window_size()
        self.surface = self._make_surface(w, h)
        self.surface.update(self.composite(self.current_frame()), self.x, self.y)
        self.clamp()
        self.root.geometry("%dx%d+%d+%d" % (w, h, self.x, self.y))

    def keep_topmost(self):
        if IS_WIN:
            self.surface.ensure_layered()
            _force_topmost(_root_hwnd(self.root))
        else:
            try:
                self.root.attributes("-topmost", True)
            except tk.TclError:
                pass
        self.root.after(3000, self.keep_topmost)

    def current_frame(self):
        if self.mode == "sticker":
            seq = self.sticker_seq
        else:
            seq = self.anim[self.mode] or self.anim["idle"]
        return seq[min(self.fi, len(seq) - 1) % len(seq)][0]

    # ------------------------------------------------------------ behavior
    def set_mode(self, mode):
        if self.priority_until_idle and mode != "idle":
            return   # 馋/吃蛋糕播放中，任何其他动作都不能打断
        if self.mode != mode and self.anim.get(mode):
            self.mode = mode
            self.fi = 0
            self._asleep = False
            if mode == "idle":
                self.priority_until_idle = False
                self.eat_flow = False

    def play_sticker(self, group):
        """Play one idle sticker group once by its custom name."""
        if self.priority_until_idle and not (group == "aini" and self.eat_flow):
            return   # 只允许吃蛋糕流程里的「爱你」继续
        seq = self.anim.get(group)
        if not seq:
            return
        if group == "chan":
            self.priority_until_idle = True   # 馋必须完整播完
        self.sticker_seq = seq
        self.mode = "sticker"
        self.fi = 0
        self._asleep = False

    def eat(self):
        """被投喂蛋糕：播放「吃蛋糕」；素材缺失时直接播放「爱你」."""
        self.wake()
        if getattr(self, "cake", None):
            self.cake.hide()
        self.eat_flow = True
        if self.anim.get("eat"):
            # 直接切换（优先级流程内部允许），保证跳->吃->爱你连续
            self.mode = "eat"
            self.fi = 0
            self._asleep = False
        else:
            self.play_sticker("aini")
        self.priority_until_idle = True       # 吃蛋糕必须完整播完

    def feed_menu(self):
        """右键「投喂」：蛋糕出现在小白面朝方向的前上方，小白馋→跳过去→吃→爱你。"""
        if self.priority_until_idle:
            return
        if getattr(self, "cake", None):
            w, h = self.window_size()
            cx = self.x + w // 2 + self.last_facing * 110
            cy = self.y + h // 4
            self.cake.spawn_at(cx, cy, follow=False)
        self.go_to_cake()

    def go_to_cake(self):
        """蛋糕生成后：先播「馋」，播完跳过去吃（碰到自动开吃）。"""
        c = getattr(self, "cake", None)
        if not c or not c.active:
            return
        self.wake()
        self._going_cake = False
        self._cake_taken = False
        self._cake_chan_wait = True
        if self.anim.get("chan"):
            self.play_sticker("chan")     # 馋 本身会置优先级
            self.priority_until_idle = True   # 馋/跳/吃整个过程都不允许打断
        else:
            self.priority_until_idle = True
            self._finish_cake_chan()

    def _finish_cake_chan(self):
        """馋播完：开始跳向蛋糕（碰到会自动开吃）。"""
        self._cake_chan_wait = False
        c = getattr(self, "cake", None)
        if not c or not c.active:
            self._going_cake = False
            self.set_mode("idle")
            return
        self._cake_jump_bonus = 0
        self._going_cake = True
        if self.anim.get("jump"):
            # 直接切模式（优先级流程内部允许），保证 馋→跳→吃 连续
            self.mode = "jump"
            self.fi = 0
            self._asleep = False
        self._start_jump()
        self._ensure_fall_loop()

    def _start_jump(self, height=None):
        """开始物理弹跳：初速度 v=sqrt(2*g*h) 上抛，跳跃期间保持水平推进。"""
        self.jumping = True
        self._jump_y0 = self.y
        h = JUMP_HEIGHT if height is None else height
        self.vy = -int((2 * GRAVITY * h) ** 0.5)
        self._last_grav = time.monotonic()

    def _step_jump(self):
        """弹跳的一步：只受重力（v=gt），落回起跳高度即落地。"""
        now = time.monotonic()
        dt = min(now - self._last_grav, 0.25)
        self._last_grav = now
        self.vy += GRAVITY * dt
        self._y_frac += self.vy * dt
        dy = int(self._y_frac)
        if dy:
            self._y_frac -= dy
            self.move(0, dy)
        if self.vy >= 0 and self.y >= self._jump_y0:
            self.jumping = False

    def _step_cake(self):
        """跳向蛋糕的一步：碰到就自动开吃，否则朝蛋糕方向继续推进；
        落回地面还没碰到就再次起跳（每次 +20px 跳高），直到够到蛋糕。"""
        c = getattr(self, "cake", None)
        if self._cake_taken:
            # 空中已经够到蛋糕：把这一跳落完（落地瞬间无缝转吃蛋糕）
            cx = c.cake_center()[0] if c else (
                self.x + self.window_size()[0] // 2 + self.last_facing * 110)
            px = self.x + self.window_size()[0] // 2
            self.vx = int(3 * self.scale) if cx > px else -int(3 * self.scale)
            if self.vx == 0:
                self.vx = 1 if cx > px else -1
            if self.jumping:
                self._step_jump()
                if not self.jumping:
                    self._cake_taken = False
                    self._cake_jump_bonus = 0
                    self._going_cake = False
                    self.move(self.vx, 0)
                    self.eat()
                    return
            else:
                self._cake_taken = False
                self._cake_jump_bonus = 0
                self._going_cake = False
                self.eat()
                return
            self.move(self.vx, 0)
            return
        if not c or not c.active:
            self._cake_jump_bonus = 0
            self._going_cake = False
            self.jumping = False
            return
        if c.touching_pet():
            self._cake_taken = True
            c.hide()                     # 蛋糕到手，先落回地面再开吃
            return
        if self._cake_jump_bonus > 400:
            c.feed()                     # 安全兜底：跳了很久还够不到就直接吃
            return
        cx = c.cake_center()[0]
        px = self.x + self.window_size()[0] // 2
        self.vx = int(3 * self.scale) if cx > px else -int(3 * self.scale)
        if self.vx == 0:
            self.vx = 1 if cx > px else -1
        if self.jumping:
            self._step_jump()
        else:
            # 没碰到 -> 下一次跳高 +20px，直到拿到蛋糕
            self._cake_jump_bonus += 20
            self._start_jump(JUMP_HEIGHT + self._cake_jump_bonus)
        self.move(self.vx, 0)

    def schedule_action(self, delay=None):
        if self.test_mode:
            return
        delay = delay or random.randint(3500, 9000)
        self.root.after(delay, self.choose_action)

    def choose_action(self):
        if self.mode == "idle":
            pool = []
            for key in ("walk", "sleep", "wave", "jump", "sit", "happy", "eat"):
                if key == "sleep" and self.falling:
                    continue   # 掉落时不要睡觉
                if self.anim.get(key) and \
                        _group_cfg(self.cfg, key)["category"] == "normal":
                    pool.append(key)
            if pool:
                name = random.choice(pool)
                if name == "walk":
                    self.start_walk()
                elif name == "sleep":
                    self.prep_sleep()
                else:
                    self.set_mode(name)
        self.schedule_action()

    def prep_sleep(self):
        """自动睡觉流程：先散步至少 20 秒，再播两遍「困困」，最后才睡觉。"""
        if self.falling or self.sleep_prep:
            return
        if not self.anim.get("kunkun"):
            self.sleep()   # 困困素材缺失时保持原来的直接睡觉
            return
        self.sleep_prep = True
        self.kunkun_plays = 0
        idle_name = self.anim["idle"][0][0] if self.anim.get("idle") else None
        if idle_name and self._is_walk_display(idle_name):
            self._start_walk_burst()   # 用散步贴纸走 20~40 秒（至少 20 秒）
        elif self.anim.get("walk"):
            self.start_walk()          # 散步贴纸不在待机里时，用走路动画走满
        else:
            self._play_kunkun()

    def _play_kunkun(self):
        """开始播放「困困」（散步结束后、睡觉前的打哈欠动画）。"""
        seq = self.anim.get("kunkun")
        if not seq:
            self._finish_sleep_prep()
            return
        self.sticker_seq = seq
        self.mode = "sticker"
        self.fi = 0
        self._asleep = False

    def _finish_sleep_prep(self):
        """困困播完两遍，进入正式睡觉。"""
        self.sleep_prep = False
        self.kunkun_plays = 0
        self.sleep()

    def start_walk(self):
        if not self.anim.get("walk"):
            return
        self.set_mode("walk")
        self.walk_mode_until = time.monotonic() + random.uniform(20, 40)
        self._start_walk_burst()

    def _find_walk_group(self):
        """The group the user calls 「散步」 (by custom name) gets the
        walk-around behavior; fall back to the built-in walk group."""
        for g, d in self.cfg.get("groups", {}).items():
            if d.get("name") == "散步":
                return g
        return "walk"

    def _start_walk_burst(self):
        self.walk_state = "walk"
        self.walk_until = time.monotonic() + random.uniform(20, 40)   # >= 20s
        self.vx = int(random.choice((-3, -2, 2, 3)) * self.scale) or 1
        self.vy = 0
        self._y_frac = 0.0
        self._last_grav = time.monotonic()

    def _is_walk_display(self, name):
        if self.mode == "walk":
            return True
        g = self.walk_group
        return bool(g) and (name == g or name.startswith(g + "_"))

    def _walk_step(self):
        now = time.monotonic()
        if self.mode == "walk" and now >= self.walk_mode_until:
            if self.sleep_prep:
                self._play_kunkun()
            else:
                # 菜单触发的「跳舞」只走 20~40 秒，然后回待机，
                # 让睡觉等平常动作能继续自动触发
                self.set_mode("idle")
            return
        if self.walk_state == "walk":
            if now >= self.walk_until:
                self.walk_state = "rest"
                self.rest_until = now + random.uniform(3, 8)
                self.vx = 0
                if self.sleep_prep:
                    self._play_kunkun()
                    return
            else:
                self.move(self.vx, 0)
                if self.vx > 0:
                    self.last_facing = 1
                elif self.vx < 0:
                    self.last_facing = -1
        elif now >= self.rest_until:
            self._start_walk_burst()
        self._ensure_fall_loop()

    def _ensure_fall_loop(self):
        if not self._fall_active:
            self._fall_active = True
            self.root.after(16, self._fall_loop)

    def _fall_loop(self):
        """High-frequency position updates while the 散步 display is active:
        falling stays smooth (60fps) instead of following the animation rate."""
        try:
            if self._going_cake:
                self._step_cake()
                self.root.after(16, self._fall_loop)
                return
            if self.jumping:
                self._step_jump()
                self.root.after(16, self._fall_loop)
                return
            if self._is_walk_display(self.current_frame()):
                self.apply_gravity()
                self.root.after(16, self._fall_loop)
                return
        except Exception:
            pass
        self._fall_active = False

    def sleep(self):
        if self.falling:
            return   # 掉落时不要睡觉
        if self.mode != "sleep" and self.anim.get("sleep"):
            self.set_mode("sleep")
            if self.wake_job:
                self.root.after_cancel(self.wake_job)
            # wake up on its own after a while
            self.wake_job = self.root.after(
                random.randint(20000, 40000), self.wake)   # 至少 20 秒

    def wake(self):
        if self.wake_job:
            self.root.after_cancel(self.wake_job)
            self.wake_job = None
        self.sleep_prep = False
        self.kunkun_plays = 0
        if self.mode == "sleep":
            self.set_mode("idle")

    def show_heart(self, ms=1200):
        if self.heart_job:
            self.root.after_cancel(self.heart_job)
            self.heart_job = None
        self.heart_visible = True
        self.heart_job = self.root.after(ms, self.hide_heart)

    def hide_heart(self):
        self.heart_visible = False
        self.heart_job = None

    def watch_config(self):
        """Reload pet_config.json when the editor saves it."""
        try:
            m = os.path.getmtime(CONFIG_PATH)
            if m != self.cfg_mtime:
                self.cfg_mtime = m
                self.cfg = load_config()
                self.anim = build_anim(self.cfg)
                self.walk_group = self._find_walk_group()
                self.reload_frames()
                if not self.anim.get(self.mode):
                    self.set_mode("idle")
        except OSError:
            pass
        self.root.after(1500, self.watch_config)

    def reload_frames(self):
        """Rescan sprites/ (deleted actions drop out) and rebuild images with
        the current per-group size factors."""
        new_base = {}
        for n in FRAME_NAMES:
            p = os.path.join(SPR, n + ".png")
            if os.path.exists(p):
                new_base[n] = Image.open(p)
        if new_base:
            self.base = new_base
        self.build_photos()
        if self.anim.get(self.mode) or self.anim.get("idle"):
            self.label.configure(image=self.photos[self.current_frame()])
            self.surface.update(self.composite(self.current_frame()), self.x, self.y)

    def open_editor(self):
        editor = os.path.join(HERE, "pet_editor.py")
        try:
            subprocess = __import__("subprocess")
            subprocess.Popen([sys.executable, editor])
        except Exception:
            pass

    def restart_pet(self):
        """重启小白：启动新进程后退出当前进程。"""
        try:
            subprocess = __import__("subprocess")
            subprocess.Popen([sys.executable, os.path.abspath(__file__)])
        except Exception:
            pass
        self.root.destroy()

    # ------------------------------------------------------------ animation
    def tick(self):
        if self.mode == "sticker":
            seq = self.sticker_seq
            if not seq or self.fi >= len(seq):
                if self._cake_chan_wait:
                    # 看到蛋糕后的「馋」播完：跳过去吃
                    self._finish_cake_chan()
                    seq = self.anim.get(self.mode) or self.anim["idle"]
                elif self.sleep_prep:
                    # 困困要连播两遍，播完才睡觉
                    self.kunkun_plays += 1
                    if self.kunkun_plays >= 2:
                        self._finish_sleep_prep()
                        seq = self.anim["sleep"] or self.anim["idle"]
                    else:
                        self._play_kunkun()
                        seq = self.sticker_seq
                else:
                    self.set_mode("idle")
                    seq = self.anim["idle"]
        else:
            seq = self.anim[self.mode]
            if not seq:
                self.set_mode("idle")
                seq = self.anim["idle"]
            if self.mode in ONE_SHOT and self.fi >= len(seq):
                if self.mode == "eat":
                    # 吃完蛋糕 -> 无缝切换到「爱你」（不经过待机帧）
                    if self.anim.get("aini"):
                        self.play_sticker("aini")
                        seq = self.sticker_seq
                    else:
                        self.set_mode("idle")
                        seq = self.anim["idle"]
                elif self.mode == "jump" and self._going_cake:
                    self.fi = 0        # 跳跃中保持跳姿，直到碰到蛋糕
                else:
                    self.set_mode("idle")
                    seq = self.anim["idle"]

        if self.mode == "sleep" and (self._asleep or self.fi >= len(seq)):
            # finished falling asleep: blanket breathes until woken
            if not self._asleep:
                self._asleep = True
                self.fi = 0
            breath = self.anim.get("sleepb") or [(seq[-1][0], 250)]
            name, ms = breath[self.fi % len(breath)]
            self.fi += 1
        else:
            name, ms = seq[self.fi % len(seq)]
            self.fi += 1
        walking = self._is_walk_display(name)
        if walking and self.vx != 0:
            if name.startswith("walk_"):
                if self.vx > 0:
                    name += "_flip"   # side-view: face the walking direction
            elif self.vx < 0:
                name += "_flip"       # 散步贴纸: 向左移动时水平翻转
        if self.falling and walking:
            self.fi -= 1               # 冻结动画帧，只更新位置
        self.label.configure(image=self.photos[name])
        self.surface.update(self.composite(name), self.x, self.y)

        if walking:
            self._walk_step()

        self.root.after(ms, self.tick)

    def move(self, dx, dy):
        self.x += int(dx)
        self.y += int(dy)
        self.clamp()
        self.root.geometry("+%d+%d" % (self.x, self.y))
        if self.test_log:
            self.test_log.write("move %d %d\n" % (self.x, self.y))
            self.test_log.flush()

    def _pixel_dark(self, x, y):
        """Screen pixel below the feet: dark (black) = ground."""
        if not IS_WIN:
            return True
        try:
            hdc = ctypes.windll.user32.GetDC(0)
            c = ctypes.windll.gdi32.GetPixel(hdc, int(x), int(y))
            ctypes.windll.user32.ReleaseDC(0, hdc)
        except Exception:
            return True
        if c == 0xFFFFFFFF:   # CLR_INVALID
            return True
        r, g, b = c & 0xFF, (c >> 8) & 0xFF, (c >> 16) & 0xFF
        return (r + g + b) / 3 < 50

    def apply_gravity(self):
        """No dark pixel underfoot -> fall with v = g*t (g = GRAVITY px/s^2)."""
        now = time.monotonic()
        dt = min(now - self._last_grav, 0.25) if self._last_grav else 0.0
        self._last_grav = now
        w, h = self.window_size()
        cx = self.x + w // 2
        bottom = self.y + h
        near_bottom = bottom >= self.root.winfo_screenheight() - 6
        ground = near_bottom or self._strip_has_dark(
            cx - int(w * 0.35), bottom + 2, int(w * 0.7), 42)
        if ground:
            self.vy = 0
            self._y_frac = 0.0
            self.falling = False
        else:
            self.vy += GRAVITY * dt          # v = g * t
            self._y_frac += self.vy * dt     # s = v * t
            dy = int(self._y_frac)
            if dy:
                self._y_frac -= dy
                self.move(0, dy)
            self.falling = True

    def _strip_has_dark(self, x0, y0, w, h):
        """One BitBlt grab of the strip below the pet; any dark pixel = ground."""
        if w <= 0 or h <= 0:
            return True
        if not IS_WIN:
            return self._strip_has_dark_linux(x0, y0, w, h)
        try:
            import numpy as np
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32
            hdc = user32.GetDC(0)
            mdc = gdi32.CreateCompatibleDC(hdc)
            hbm = gdi32.CreateCompatibleBitmap(hdc, w, h)
            old = gdi32.SelectObject(mdc, hbm)
            gdi32.BitBlt(mdc, 0, 0, w, h, hdc, int(x0), int(y0), 0x00CC0020)

            class _BMI(ctypes.Structure):
                _fields_ = [("biSize", ctypes.c_uint32),
                            ("biWidth", ctypes.c_int32),
                            ("biHeight", ctypes.c_int32),
                            ("biPlanes", ctypes.c_uint16),
                            ("biBitCount", ctypes.c_uint16),
                            ("biCompression", ctypes.c_uint32),
                            ("biSizeImage", ctypes.c_uint32),
                            ("biXPelsPerMeter", ctypes.c_int32),
                            ("biYPelsPerMeter", ctypes.c_int32),
                            ("biClrUsed", ctypes.c_uint32),
                            ("biClrImportant", ctypes.c_uint32)]
            bmi = _BMI()
            bmi.biSize = ctypes.sizeof(_BMI)
            bmi.biWidth = w
            bmi.biHeight = -h
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0
            bmi.biSizeImage = w * h * 4
            buf = ctypes.create_string_buffer(w * h * 4)
            gdi32.GetDIBits(mdc, hbm, 0, h, buf, ctypes.byref(bmi), 0)
            gdi32.SelectObject(mdc, old)
            gdi32.DeleteObject(hbm)
            gdi32.DeleteDC(mdc)
            user32.ReleaseDC(0, hdc)
            arr = np.frombuffer(buf.raw, dtype=np.uint8).reshape(h, w, 4)
            b = arr[:, :, 0].astype(np.int16)
            g = arr[:, :, 1].astype(np.int16)
            r = arr[:, :, 2].astype(np.int16)
            return bool(((r + g + b) < 150).any())
        except Exception:
            return True

    def _strip_has_dark_linux(self, x0, y0, w, h):
        """X11: grab the strip below the pet via python-xlib (optional);
        without it we assume ground is always present so the pet never falls."""
        try:
            import numpy as np
            from Xlib import X, display
            d = display.Display()
            raw = d.screen().root.get_image(
                int(x0), int(y0), int(w), int(h), X.ZPixmap, 0xffffffff)
            data = raw.data
            bpl = int(getattr(raw, "bytes_per_line", 0) or 0)
            if bpl >= w * 4:
                buf = np.frombuffer(data, dtype=np.uint8)
                arr = buf[:bpl * h].reshape(h, bpl)[:, :w * 4].reshape(h, w, 4)
            elif bpl >= w * 3:
                buf = np.frombuffer(data, dtype=np.uint8)
                arr = buf[:bpl * h].reshape(h, bpl)[:, :w * 3].reshape(h, w, 3)
            else:
                return True
            b = arr[:, :, 0].astype(np.int16)
            g = arr[:, :, 1].astype(np.int16)
            r = arr[:, :, 2].astype(np.int16)
            return bool(((r + g + b) < 150).any())
        except Exception:
            return True   # 无法抓屏时视为始终有地面（不坠落）

    def clamp(self):
        w, h = self.window_size()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        if self.x < 0:
            self.x = 0
            self.vx = abs(self.vx)
        if self.x + w > sw:
            self.x = sw - w
            self.vx = -abs(self.vx)
        if self.y < 0:
            self.y = 0
        if self.y + h > sh:
            self.y = sh - h

    # ---------------------------------------------------------------- mouse
    def on_press(self, event):
        if self.priority_until_idle:
            return   # 馋/吃蛋糕播放中，不响应点击
        self.wake()
        if getattr(self, "cake", None) and self.cake.active:
            self.cake.feed()   # 点击小狗喂食
            self._press_time = int(self.root.tk.call("clock", "milliseconds"))
            self._press_pos = (event.x_root, event.y_root)
            return
        self.drag_off = (event.x_root - self.x, event.y_root - self.y)
        self._press_time = int(self.root.tk.call("clock", "milliseconds"))
        self._press_pos = (event.x_root, event.y_root)
        if self.anim.get("drag"):
            self.set_mode("drag")
        if self.test_log:
            self.test_log.write("press %d %d off=%s\n" % (event.x_root, event.y_root, self.drag_off))
            self.test_log.flush()

    def on_drag(self, event):
        if self.drag_off:
            if self.test_log:
                self.test_log.write("motion %d %d\n" % (event.x_root, event.y_root))
                self.test_log.flush()
            self.x = event.x_root - self.drag_off[0]
            self.y = event.y_root - self.drag_off[1]
            self.x = int(self.x)
            self.y = int(self.y)
            self.clamp()
            self.root.geometry("+%d+%d" % (self.x, self.y))

    def on_release(self, event):
        if self.priority_until_idle:
            return
        self.drag_off = None
        self.set_mode("idle")
        now = int(self.root.tk.call("clock", "milliseconds"))
        moved = False
        if self._press_pos:
            moved = abs(event.x_root - self._press_pos[0]) + \
                abs(event.y_root - self._press_pos[1]) > 6
        if self._press_time and self._press_pos and \
                (now - self._press_time) < 260 and not moved:
            if self.anim.get("happy"):
                self.set_mode("happy")
        self._press_time = None
        if self.test_log:
            self.test_log.write("release %d %d\n" % (event.x_root, event.y_root))
            self.test_log.flush()

    def on_double(self, event):
        if self.priority_until_idle:
            return
        self.wake()
        if self.anim.get("jump"):
            self.set_mode("jump")
            self._start_jump()
            self._ensure_fall_loop()
            self.show_heart()

    def popup_menu(self, event):
        menu = tk.Menu(self.root, tearoff=0)
        def free(fn):
            return fn if not self.priority_until_idle else (lambda: None)
        if getattr(self, "cake", None):
            menu.add_command(label="投喂", command=free(self.feed_menu))
            menu.add_separator()
        # idle stickers by their custom names
        for grp in IDLE_ORDER:
            if self.anim.get(grp):
                menu.add_command(label=_group_cfg(self.cfg, grp)["name"],
                                 command=free(lambda grp=grp: self.play_sticker(grp)))
        if any(self.anim.get(grp) for grp in IDLE_ORDER):
            menu.add_separator()
        if self.anim.get("happy"):
            menu.add_command(label=_group_cfg(self.cfg, "happy")["name"],
                             command=free(lambda: (self.wake(), self.set_mode("happy"))))
        if self.anim.get("walk"):
            menu.add_command(label=_group_cfg(self.cfg, "walk")["name"],
                             command=free(self.start_walk))
        if self.anim.get("sleep"):
            menu.add_command(label=_group_cfg(self.cfg, "sleep")["name"],
                             command=free(self.sleep))
        menu.add_command(label="醒来", command=self.wake)
        menu.add_command(label="重启小白", command=self.restart_pet)
        menu.add_command(label="管理动作…", command=self.open_editor)
        menu.add_separator()
        menu.add_command(label="变大一点", command=lambda: self.set_scale(1.2))
        menu.add_command(label="变小一点", command=lambda: self.set_scale(1 / 1.2))
        menu.add_separator()
        menu.add_command(label="退出", command=self.root.destroy)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()


def main(auto_close_ms=None, test_mode=False, start_pos=None):
    root = tk.Tk()
    root.withdraw()
    pet = Pet(root, test_mode=test_mode, start_pos=start_pos)
    root.deiconify()
    pet.surface.update(pet.composite(pet.current_frame()), pet.x, pet.y)
    if not test_mode:
        import cake
        cake.install(root, pet)
    if auto_close_ms:
        root.after(auto_close_ms, root.destroy)
    root.mainloop()


if __name__ == "__main__":
    import sys
    _enable_dpi_awareness()
    args = sys.argv[1:]
    pos_args = [a.split("=", 1)[1] for a in args if a.startswith("--pos=")]
    main(
        test_mode="--no-random" in args,
        start_pos=tuple(int(v) for v in pos_args[0].split(",")) if pos_args else None,
    )
