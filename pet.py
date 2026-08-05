# -*- coding: utf-8 -*-
"""小白桌面宠物 - a floppy-eared white puppy that lives on your desktop.

Run:  python pet.py   (Windows) / python3 pet.py (Linux)
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
LINUX_FILL = (0, 0, 0)       # Linux 上透明区填充色（形状切掉后不可见；
                             # 瞬时错位时只露出深色剪影而不是品红）
BASE_W, BASE_H = 190, 180    # sprite canvas size
GRAVITY = 1000.0             # px / s^2, v = g*t

IS_WIN = sys.platform.startswith("win")
IS_LINUX = sys.platform.startswith("linux")

# 下落/落地判定：以小白为中心抓取周围 BG_SIZE 像素，颜色量化聚类后，
# 占比最高的一类视为背景板，其余颜色都算可踩的地板。
BG_SIZE = 500
BG_QUANT = 16                # 每通道量化步长（4bit -> 4096 个颜色桶）
FLOOR_RATIO = 0.05           # 脚下 strip 中非背景像素占比超过它 = 有地板
BG_REFRESH_S = 0.1          # 背景聚类最短刷新间隔（秒）

# 前方地形：探测前进方向的非背景轮廓，决定直走 / 上台阶 / 跳跃 / 转身。
TERRAIN_PROBE = 8            # 前方探测的水平偏移（px）
CLIMB_MAX = 24               # 可直接走上台阶的最大高度（px）
JUMP_MAX = 100               # 可跳上台阶的最大高度（px）
JUMP_HEIGHT = 100            # 统一跳跃高度（px）
JUMP_SPEED = int((2 * GRAVITY * JUMP_HEIGHT) ** 0.5)   # 统一起跳初速度

# 右键菜单字体与配色：Tk 默认菜单字体会回退到位图 fixed（高 DPI 下很糊），
# 显式指定 Xft 字体（DejaVu Sans，中文自动回退到系统中文字体）即可抗锯齿。
# 右键菜单字体：这个 Tk 只支持 X core 字体（无 Xft），中文字体里
# "song ti"（宋体）在 36pt 内能完整显示且清晰；DejaVu 等西文字体
# 中文会缺字/方块。
if IS_WIN:
    MENU_FONT = ("Microsoft YaHei UI", 10)
    DIALOG_FONT = ("Microsoft YaHei UI", 11)
    DIALOG_BTN_FONT = ("Microsoft YaHei UI", 10)
    BUBBLE_FONT = ("Microsoft YaHei UI", 10)
else:
    MENU_FONT = ("song ti", 36)
    DIALOG_FONT = ("song ti", 18)
    DIALOG_BTN_FONT = ("song ti", 16)
    BUBBLE_FONT = ("song ti", 14)
MENU_BG = "#2b2b2b"
MENU_FG = "#f0f0f0"
MENU_ACTIVE_BG = "#3c6fd0"
MENU_ACTIVE_FG = "#ffffff"


def _sprite_files(pattern):
    """sprites 目录下的文件；动作已按文件夹存放（sprites/<动作>/），递归查找。"""
    return sorted(glob.glob(os.path.join(SPR, "**", pattern), recursive=True))


def _find_sprite(name):
    """按文件名（不含路径）在 sprites 下递归查找，返回完整路径或 None。"""
    files = _sprite_files(name + ".png")
    return files[0] if files else None


def _seq(prefix, ms):
    files = _sprite_files(prefix + "_*.png")
    return [(os.path.splitext(os.path.basename(f))[0], ms) for f in files]


_MS = {"walk": 70, "chan": 70, "aini": 70, "happy": 33,
       "sleep": 31, "sleepb": 150, "eat": 33, "kunkun": 56,
       "wave": 50, "home": 50, "kuku": 66, "dance": 70}


def _seqs():
    """Frame sequences for every group, re-globbed from sprites/ each call so
    deleted actions disappear and re-added ones appear."""
    seqs = {g: _seq(g, ms) for g, ms in _MS.items()}
    # 散步用 like.gif 拆出来的帧（walk_*.png）；没有视频/动图素材时才回退
    seqs["walk"] = _seq("walk", _MS["walk"]) or \
        ([("walk", 150)] * 4 if _find_sprite("walk") else [])
    seqs["drag"] = [("drag", 120)] if _find_sprite("drag") else []
    # 挥手优先用视频帧（wave_*.png），没有视频素材时才回退到静态贴纸
    seqs["wave"] = _seq("wave", _MS["wave"]) or \
        ([("wave", 150)] * 4 if _find_sprite("wave") else [])
    seqs["jump"] = [("jump", 100), ("jump", 110), ("jump", 180)] \
        if _find_sprite("jump") else []
    seqs["sit"] = [("sit", 260)] * 4 if _find_sprite("sit") else []
    return seqs


SEQ = _seqs()

IDLE_ORDER = ["walk", "chan", "aini"]   # idle plays these in order
ONE_SHOT = {"happy", "wave", "jump", "sit", "eat"}
        # one-shot actions return to idle when finished ("eat" continues to 爱你)
FRAME_NAMES = sorted(os.path.splitext(os.path.basename(f))[0]
                     for f in _sprite_files("*.png"))

CONFIG_PATH = os.path.join(HERE, "pet_config.json")
LOCK_FILE = os.path.join(HERE, ".pet.lock")


def _single_instance():
    """单实例锁：已有小白在跑就先终止它，再启动新的，避免堆积垃圾进程。"""
    try:
        if os.path.exists(LOCK_FILE):
            with open(LOCK_FILE, "r", encoding="utf-8") as f:
                pid = int((f.read() or "0").strip() or 0)
            if pid and pid != os.getpid():
                if IS_WIN:
                    try:
                        # 检查进程是否存活；是 pet.py 就结束它
                        PROCESS_TERMINATE = 0x0001
                        h = ctypes.windll.kernel32.OpenProcess(
                            PROCESS_TERMINATE, False, pid)
                        if h:
                            ctypes.windll.kernel32.TerminateProcess(h, 0)
                            ctypes.windll.kernel32.CloseHandle(h)
                            time.sleep(0.5)
                    except Exception:
                        pass
                else:
                    try:
                        with open("/proc/%d/cmdline" % pid, "rb") as f:
                            if b"pet.py" in f.read():
                                os.kill(pid, 15)      # SIGTERM
                                time.sleep(0.5)
                    except Exception:
                        pass
        with open(LOCK_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        return True
    except Exception:
        return True
DEFAULT_CONFIG = {
    "groups": {
        "walk":  {"name": "散步", "enabled": True, "category": "normal"},
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
        "home":  {"name": "回家", "enabled": True, "category": "special"},
        "kuku":  {"name": "哭哭", "enabled": True, "category": "special"},
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


def _flatten_straight(rgba, key=KEY_RGB, alpha_min=96):
    """Flatten RGBA for the SHAPE-mask path: sub-threshold pixels become the
    key color (they are cut out by the shape mask anyway), while visible
    pixels keep their exact RGB -- no magenta blending, so there is no pink
    halo even when the window manager can't honor -transparentcolor."""
    rgba = rgba.convert("RGBA")
    try:
        import numpy as np
        arr = np.asarray(rgba)
        out = arr[..., :3].copy()
        low = arr[..., 3:4] < alpha_min
        out[low.repeat(3, axis=2)] = key
        return Image.fromarray(out, "RGB")
    except Exception:
        px = rgba.load()
        out = Image.new("RGB", rgba.size)
        op = out.load()
        for y in range(rgba.height):
            for x in range(rgba.width):
                r, g, b, a = px[x, y]
                op[x, y] = key if a < alpha_min else (r, g, b)
        return out


def _apply_linux_keycolor(root):
    """Ask Tk to key out MAGENTA.  This is a Windows-only wm attribute in
    stock Tk; on Linux it usually raises TclError, which we treat as "not
    supported".  Returns True when Tk actually accepted it."""
    if IS_WIN:
        return False   # Windows 走分层窗口（per-pixel alpha），不用 -transparentcolor
    try:
        root.attributes("-transparentcolor", MAGENTA)
        return root.attributes("-transparentcolor") == MAGENTA
    except tk.TclError:
        return False


def _enable_dpi_awareness():
    """Windows：进程按监视器 DPI 感知，分层窗口命中测试才能 1:1；
    否则 125%+ 缩放下大半透明区会变成点击穿透。"""
    if not IS_WIN:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


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
    """Windows 分层窗口（per-pixel alpha）：渲染与命中测试都来自图像
    alpha 通道——透明像素点击穿透、不透明像素可点击，且不受
    -transparentcolor 在高 DPI 下的命中测试 bug 影响。"""

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
        # UpdateLayeredWindow 要求 WS_EX_LAYERED；Tk 重应用 -topmost /
        # -toolwindow 时可能清掉该样式，所以每次更新前重新断言。
        user32 = ctypes.windll.user32
        hwnd = self.get_hwnd()
        exstyle = user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
        if not (exstyle & 0x00080000):
            user32.SetWindowLongW(hwnd, -20, exstyle | 0x00080000)

    def update(self, pil_rgba, x, y, name=None):
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


def _force_topmost(hwnd):
    if not IS_WIN:
        return
    try:
        ctypes.windll.user32.SetWindowPos(
            hwnd, _HWND_TOPMOST, 0, 0, 0, 0,
            _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE)
    except Exception:
        pass


_SHAPE_BOUNDING = 0
_SHAPE_CLIP = 1
_SHAPE_INPUT = 2
_SHAPE_SET = 0
SHAPE_ALPHA_MIN = 96

class _XRectangle(ctypes.Structure):
    _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short),
                ("width", ctypes.c_ushort), ("height", ctypes.c_ushort)]


class _XWindowAttributes(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_int), ("y", ctypes.c_int),
        ("width", ctypes.c_int), ("height", ctypes.c_int),
        ("border_width", ctypes.c_int), ("depth", ctypes.c_int),
        ("visual", ctypes.c_void_p), ("root", ctypes.c_ulong),
        ("class_", ctypes.c_int), ("bit_gravity", ctypes.c_int),
        ("win_gravity", ctypes.c_int), ("backing_store", ctypes.c_int),
        ("backing_planes", ctypes.c_ulong), ("backing_pixel", ctypes.c_ulong),
        ("save_under", ctypes.c_int), ("colormap", ctypes.c_ulong),
        ("map_installed", ctypes.c_int), ("map_state", ctypes.c_int),
        ("all_event_masks", ctypes.c_long), ("your_event_mask", ctypes.c_long),
        ("do_not_propagate_mask", ctypes.c_long),
        ("override_redirect", ctypes.c_int), ("screen", ctypes.c_void_p),
    ]


# 我们自己的 X 连接上出错时不要让 libX11 的默认错误处理器把进程退出
# （Tk 的窗口还没 map 时 winfo_id 可能还不是有效 XID）。
_XErrorHandler = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)


def _ignore_x_error(dpy, event):
    return 0


_IGNORE_X_ERROR = _XErrorHandler(_ignore_x_error)


class _ShapeCutter:
    """Linux/X11 transparency via the SHAPE extension (ctypes -> libX11).

    Tk's `-transparentcolor` is documented as Windows-only, so on Linux the
    flattened magenta background is simply left visible.  Here we cut the
    transparent pixels out of the toplevel ourselves with XShapeCombineMask:
    the same 1-bit mask drives the bounding shape (pixels are not drawn) and
    the input shape (pixels are click-through).  This works on X11 with or
    without a compositor, and under XWayland."""

    def __init__(self, display_hint=None):
        self._lib = None
        self._xext = None
        self._dpy = None
        self._cache = {}
        self.fail_reason = ""
        try:
            lib = ctypes.CDLL("libX11.so.6")
            xext = ctypes.CDLL("libXext.so.6")
        except OSError as e:
            self.fail_reason = "加载 libX11/libXext 失败: %s" % e
            return
        try:
            lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
            lib.XOpenDisplay.restype = ctypes.c_void_p
            lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
            lib.XDefaultRootWindow.restype = ctypes.c_ulong
            lib.XCreateBitmapFromData.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong,
                ctypes.c_char_p, ctypes.c_uint, ctypes.c_uint]
            lib.XCreateBitmapFromData.restype = ctypes.c_ulong
            xext.XShapeCombineMask.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, ctypes.c_ulong, ctypes.c_int]
            xext.XShapeCombineRectangles.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
                ctypes.c_int, ctypes.c_int, ctypes.c_int]
            xext.XShapeQueryExtension.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
            xext.XShapeQueryExtents.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong,
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
            lib.XFreePixmap.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            lib.XFlush.argtypes = [ctypes.c_void_p]
            lib.XSetErrorHandler.argtypes = [_XErrorHandler]
            lib.XSetErrorHandler.restype = ctypes.c_void_p
            lib.XQueryTree.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong,
                ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
                ctypes.POINTER(ctypes.POINTER(ctypes.c_ulong)),
                ctypes.POINTER(ctypes.c_uint)]
            lib.XQueryTree.restype = ctypes.c_int
            lib.XFree.argtypes = [ctypes.c_void_p]
            lib.XFree.restype = ctypes.c_int
            lib.XClearArea.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong,
                ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_int]
            lib.XClearArea.restype = ctypes.c_int
            lib.XCreateImage.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_int,
                ctypes.c_int, ctypes.c_char_p, ctypes.c_uint, ctypes.c_uint,
                ctypes.c_int, ctypes.c_int]
            lib.XCreateImage.restype = ctypes.c_void_p
            lib.XPutImage.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                ctypes.c_uint, ctypes.c_uint]
            lib.XCreateGC.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
            lib.XCreateGC.restype = ctypes.c_ulong
            lib.XGetGeometry.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong,
                ctypes.POINTER(ctypes.c_ulong),
                ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint),
                ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
            lib.XGetGeometry.restype = ctypes.c_int
            lib.XGetWindowAttributes.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p]
            lib.XGetWindowAttributes.restype = ctypes.c_int
            lib.XUnmapWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            lib.XUnmapWindow.restype = ctypes.c_int
        except Exception as e:
            self.fail_reason = "绑定 libX11/libXext 符号失败: %s" % e
            return
        lib.XSetErrorHandler(_IGNORE_X_ERROR)   # 出错不退出，apply() 返回 False
        candidates = [display_hint, os.environ.get("DISPLAY"), None]
        dpy = None
        for cand in candidates:
            if cand:
                dpy = lib.XOpenDisplay(str(cand).encode("utf-8"))
            else:
                dpy = lib.XOpenDisplay(None)
            if dpy:
                break
        if not dpy:
            self.fail_reason = ("XOpenDisplay 连不上 %r（XAUTHORITY=%r）" % (
                os.environ.get("DISPLAY"), os.environ.get("XAUTHORITY")))
            return
        self._lib, self._xext, self._dpy = lib, xext, dpy
        self._gc = lib.XCreateGC(dpy, lib.XDefaultRootWindow(dpy), 0, None)
        self._paint_buf = None
        self._paint_img = None
        self._paint_ctx_win = None      # 已解析绘制上下文的窗口
        self._paint_visual = None
        self._paint_depth = 24
        self._paint_target = None      # (win_id, depth)
        self._target_age = 0
        ev_base, err_base = ctypes.c_int(), ctypes.c_int()
        try:
            self._ok = bool(xext.XShapeQueryExtension(
                dpy, ctypes.byref(ev_base), ctypes.byref(err_base)))
            if self._ok:
                self.fail_reason = ""
        except Exception as e:
            self.fail_reason = "XShapeQueryExtension 失败: %s" % e
            self._ok = False
        if not self._ok:
            self.fail_reason = "X 服务器没有 SHAPE 扩展"
        self.last_win = 0
        self.last_shaped = False

    @property
    def ok(self):
        return getattr(self, "_ok", False)

    @property
    def display_name(self):
        return getattr(self, "_dpy_name", "")

    def _connected_display(self):
        return self._dpy is not None

    def _runs(self, rgba):
        """把 alpha 掩码拆成逐行连续段（精确矩形），供
        XShapeCombineRectangles 使用。不用位图掩码——X 服务器把位图转成
        矩形时会合并掉细碎小洞（线条画的空洞会被填掉）。"""
        rgba = rgba.convert("RGBA")
        w, h = rgba.size
        try:
            import numpy as np
            a = np.asarray(rgba)[..., 3]
            mask = (a >= SHAPE_ALPHA_MIN).astype(np.uint8)
            runs = []
            for y in range(h):
                row = mask[y]
                d = np.diff(np.concatenate(([0], row, [0])))
                starts = np.flatnonzero(d == 1)
                ends = np.flatnonzero(d == -1)
                for s, e in zip(starts.tolist(), ends.tolist()):
                    runs.append((s, y, e - s))
        except Exception:
            px = rgba.load()
            runs = []
            in_run = False
            for y in range(h):
                for x in range(w):
                    op = px[x, y][3] >= SHAPE_ALPHA_MIN
                    if op and not in_run:
                        s = x
                        in_run = True
                    elif not op and in_run:
                        runs.append((s, y, x - s))
                        in_run = False
                if in_run:
                    runs.append((s, y, w - s))
                    in_run = False
        return runs, w, h

    def _top_ancestor(self, win_id):
        """Tk 的 winfo_id 返回的往往是 Toplevel 的内层窗口；必须沿父链往上
        找到真正的顶层 X 窗口（其父窗口是 root），SHAPE 施加在那里才有效。
        否则只是给内层窗口切形状，顶层窗口的品红背景依然露着。"""
        lib, dpy = self._lib, self._dpy
        xroot = lib.XDefaultRootWindow(dpy)
        w = win_id
        for _ in range(32):
            root_ret = ctypes.c_ulong()
            parent_ret = ctypes.c_ulong()
            children_ret = ctypes.POINTER(ctypes.c_ulong)()
            n_ret = ctypes.c_uint()
            st = lib.XQueryTree(
                dpy, w,
                ctypes.byref(root_ret), ctypes.byref(parent_ret),
                ctypes.byref(children_ret), ctypes.byref(n_ret))
            if children_ret:
                lib.XFree(children_ret)
            if not st or parent_ret.value == 0 or parent_ret.value == xroot:
                return w
            w = parent_ret.value
        return w

    def create_input_window(self, x, y, w, h):
        """创建不可见的 InputOnly 窗口覆盖宠物区域，用于接收鼠标事件。
        InputOnly 窗口不显示、不遮挡渲染；我们自己创建，可以自由选择
        事件（外部客户端对 Tk 窗口 XSelectInput 会 BadAccess）。用
        python-xlib 创建（ctypes 直接调 XCreateWindow 会段错误）。
        返回 (Display, Window) 或 None。"""
        try:
            from Xlib import X, display as _xd
            d = _xd.Display()
            r = d.screen().root
            win = r.create_window(
                int(x), int(y), max(1, int(w)), max(1, int(h)), 0, 0, 2,
                event_mask=(X.ButtonPressMask | X.ButtonReleaseMask |
                            X.PointerMotionMask),
                override_redirect=1)
            win.map()
            d.flush()
            return (d, win)
        except Exception:
            return None

    def move_input_window(self, io, x, y):
        """让 InputOnly 窗口跟随宠物移动，并保持在最上层。"""
        if not io:
            return
        try:
            d, win = io
            win.configure(x=int(x), y=int(y))
            win.raise_window()
            d.flush()
        except Exception:
            pass

    def _children(self, win_id):
        """返回指定窗口的直接子窗口 id 列表（ctypes XQueryTree）。"""
        lib, dpy = self._lib, self._dpy
        root_ret = ctypes.c_ulong()
        parent_ret = ctypes.c_ulong()
        children_ret = ctypes.POINTER(ctypes.c_ulong)()
        n_ret = ctypes.c_uint()
        st = lib.XQueryTree(
            dpy, win_id,
            ctypes.byref(root_ret), ctypes.byref(parent_ret),
            ctypes.byref(children_ret), ctypes.byref(n_ret))
        if not st or not children_ret:
            return []
        ids = [children_ret[i] for i in range(n_ret.value)]
        lib.XFree(children_ret)
        return ids

    def _geometry(self, win_id):
        """返回 (x, y, width, height, depth)，失败返回 None。"""
        lib, dpy = self._lib, self._dpy
        root_ret = ctypes.c_ulong()
        x, y = ctypes.c_int(), ctypes.c_int()
        w, h = ctypes.c_uint(), ctypes.c_uint()
        bw, depth = ctypes.c_uint(), ctypes.c_uint()
        st = lib.XGetGeometry(
            dpy, win_id,
            ctypes.byref(root_ret), ctypes.byref(x), ctypes.byref(y),
            ctypes.byref(w), ctypes.byref(h), ctypes.byref(bw), ctypes.byref(depth))
        if not st:
            return None
        return x.value, y.value, w.value, h.value, depth.value

    def resolve_paint_target(self, shape_win, w, h):
        """从顶层窗口沿树向下找到最深的全尺寸子窗口（Tk label 的实际
        X 窗口），并返回 (win_id, depth)。不信任 winfo_id——它在窗口真正
        map 前会返回服务器上还不存在的占位 ID。"""
        best = None
        cur = shape_win
        for _ in range(8):
            geo = self._geometry(cur)
            if geo is None:
                break
            cx, cy, cw, ch, depth = geo
            if cx == 0 and cy == 0 and cw == w and ch == h:
                best = (cur, depth)
            kids = self._children(cur)
            nxt = None
            for kid in kids:
                kg = self._geometry(kid)
                if kg and kg[0] == 0 and kg[1] == 0 and kg[2] == w and kg[3] == h:
                    nxt = kid
                    break
            if nxt is None:
                break
            cur = nxt
        return best

    def _combine(self, win_id, kind, runs):
        """把一个矩形列表设置为指定种类的 SHAPE（同一 X 连接）。"""
        n = len(runs)
        if n == 0:
            return
        RectArr = _XRectangle * n
        rects = RectArr()
        for i, (x, y, rw) in enumerate(runs):
            rects[i].x = x
            rects[i].y = y
            rects[i].width = rw
            rects[i].height = 1
        self._xext.XShapeCombineRectangles(
            self._dpy, win_id, kind, 0, 0, rects, n, _SHAPE_SET, 0)

    def _paint(self, win_id, depth, rgba, w, h):
        """把 RGBA 帧直接画到 X 窗口（BGRA、显式 stride、同连接顺序）。
        透明区填黑：它们会被 CLIP 形状切掉，只起"擦除旧内容"的兜底作用。"""
        # 每个目标窗口用自己的 visual 和 GC 绘制（顶层窗口的 visual 可能
        # 与默认/根窗口不同，用根 GC 画顶层会被服务器静默拒绝）
        if self._paint_ctx_win != win_id:
            attrs = _XWindowAttributes()
            if self._lib.XGetWindowAttributes(
                    self._dpy, win_id, ctypes.byref(attrs)):
                self._paint_visual = attrs.visual
                self._paint_depth = attrs.depth
                self._gc = self._lib.XCreateGC(self._dpy, win_id, 0, None)
                self._paint_ctx_win = win_id
            else:
                self._paint_visual = None
                self._paint_depth = depth
        rgba = rgba.convert("RGBA")
        try:
            import numpy as np
            arr = np.asarray(rgba)
            rgb = arr[..., :3].copy()
            low = arr[..., 3:4] < SHAPE_ALPHA_MIN
            rgb[low.repeat(3, axis=2)] = LINUX_FILL
            bgra = np.zeros((h, w, 4), dtype=np.uint8)
            bgra[..., 0] = rgb[..., 2]
            bgra[..., 1] = rgb[..., 1]
            bgra[..., 2] = rgb[..., 0]
            data = bgra.tobytes()
        except Exception:
            px = rgba.load()
            data = bytearray(w * h * 4)
            for y in range(h):
                for x in range(w):
                    r, g, b, a = px[x, y]
                    if a < SHAPE_ALPHA_MIN:
                        r = g = b = 0
                    i = (y * w + x) * 4
                    data[i] = b
                    data[i + 1] = g
                    data[i + 2] = r
            data = bytes(data)
        size = len(data)
        if self._paint_buf is None or len(self._paint_buf) < size:
            self._paint_buf = ctypes.create_string_buffer(size)
        ctypes.memmove(self._paint_buf, data, size)
        self._paint_img = self._lib.XCreateImage(
            self._dpy, self._paint_visual, self._paint_depth, 2, 0,
            self._paint_buf, w, h, 32, w * 4)
        self._lib.XPutImage(
            self._dpy, win_id, self._gc, self._paint_img, 0, 0, 0, 0, w, h)

    def apply_frame(self, shape_win, paint_target, rgba, cache_key=None):
        """同一 X 连接上按序完成：应用本帧形状 → 画本帧像素。

        形状 B 应用后，B 之外的内容被裁掉（不可见），B 之内会被新像素
        完整覆盖，因此不需要清屏；也避免形状反复变化触发 Expose 让 Tk
        把标签重绘成黑底。顺序确定，不会出现"旧形状裁新图像"的错位。"""
        if not self.ok:
            return False
        if cache_key is None:
            runs, w, h = self._runs(rgba)
        else:
            hit = self._cache.get(cache_key)
            if hit is None:
                hit = self._runs(rgba)
                if len(self._cache) > 512:
                    self._cache.clear()
                self._cache[cache_key] = hit
            runs, w, h = hit
        if not runs:
            return False
        if paint_target is None:
            return False
        # 应用本帧形状（Bounding 剪外框 / Clip 裁子窗口 / Input 点击穿透）
        for kind in (_SHAPE_BOUNDING, _SHAPE_CLIP, _SHAPE_INPUT):
            self._combine(shape_win, kind, runs)
        # 画本帧像素
        paint_win, depth = paint_target
        self._paint(paint_win, depth, rgba, w, h)
        self._lib.XFlush(self._dpy)
        self.last_win = shape_win
        self.last_shaped = True
        return True


class _KeyedSurface:
    """Linux/X11 surface: 宠物像素用 XPutImage 直接画在顶层窗口上，形状用
    X11 SHAPE 扩展（精确矩形）裁剪，透明区域既不可见也点击穿透。形状和
    绘制在同一个 X 连接上按序提交，不存在 Tk 跨连接绘制的错位竞态；
    Expose 后延迟 1ms 重绘，抵消 Tk 对顶层窗口背景的重绘。"""

    def __init__(self, root, label, width, height, key_ok=False):
        self.root = root
        self.label = label
        self.w, self.h = width, height
        self.key_ok = key_ok
        self._photo = None
        self._last = None
        self._last_name = None
        try:
            screen = root.tk.call("winfo", "screen", ".")
        except Exception:
            screen = None
        self._shape = _ShapeCutter(display_hint=screen)
        self._shape_ok = self._shape.ok
        self._reported_shape = False
        self._paint_target = None
        self._paint_target_age = 0
        self._repaint_queued = False
        if self._shape_ok:
            try:
                self.root.bind("<Map>", self._on_map, add="+")
                self.root.bind("<Expose>", self._on_map, add="+")
                if self.label is not None:
                    self.label.bind("<Expose>", self._on_map, add="+")
            except Exception:
                pass

    def ensure_layered(self):
        pass   # no Win32 layered style on Linux

    def _on_map(self, event=None):
        """map / Expose 后重画当前帧。

        形状每帧变化会让 X 服务器生成 Expose，Tk 随后把标签重绘成黑底、
        盖掉我们的绘制。这里不立即重画（那会被 Tk 再盖掉），而是用
        after_idle 排队：同一轮 idle 里 Tk 先画黑底、我们随后重画，
        顺序确定，宠物就不会闪黑。"""
        if self.label is None:
            self._unmap_container()
        if self._repaint_queued:
            return
        self._repaint_queued = True
        try:
            self.root.after(1, self._repaint_last)
        except Exception:
            self._repaint_queued = False

    def _repaint_last(self):
        self._repaint_queued = False
        if self._last is not None and self._shape_ok:
            try:
                shape_win = self._shape._top_ancestor(int(self.root.winfo_id()))
                paint_win = self._resolve_paint_target(shape_win)
                ok = self._shape.apply_frame(
                    shape_win, paint_win, self._last, self._last_name)
                self._report_shape(ok)
            except Exception:
                pass

    def _unmap_container(self):
        """把 Tk 的容器子窗口隐藏起来：它的黑底会盖住顶层上的绘制，
        而且父窗口形状每帧变化时合成器偶尔会丢掉这个子表面（闪黑）。
        隐藏后形状和绘制都只作用于顶层窗口本身。"""
        if not self._shape_ok:
            return
        try:
            child = int(self.root.winfo_id())
            self._shape._lib.XUnmapWindow(self._shape._dpy, child)
            self._shape._lib.XFlush(self._shape._dpy)
        except Exception:
            pass

    def _resolve_paint_target(self, shape_win):
        """解析并缓存绘制目标（真实 label 窗口），每 60 帧重新解析一次。"""
        if self.label is None:
            # 无 Tk label：直接画顶层窗口本身（用顶层自己的 visual/GC）。
            # 画子窗口会在父窗口形状变化时被合成器偶尔丢掉（闪黑）。
            geo = self._shape._geometry(shape_win)
            if geo is None:
                return None
            return (shape_win, geo[4])
        self._paint_target_age += 1
        if (self._paint_target is None or self._paint_target_age > 60):
            self._paint_target = self._shape.resolve_paint_target(
                shape_win, self.w, self.h)
            self._paint_target_age = 0
        return self._paint_target

    def _report_shape(self, ok):
        if self._reported_shape:
            return
        self._reported_shape = True
        win = getattr(self._shape, "last_win", 0)
        if ok:
            print("SHAPE: 透明形状已生效 win=0x%x" % win, file=sys.stderr)
        else:
            print("SHAPE: 服务器未接受形状 win=0x%x（窗口可能还没建好，或 "
                  "合成器不支持）" % win, file=sys.stderr)

    def update(self, pil_rgba, x, y, name=None):
        self._last = pil_rgba
        self._last_name = name
        if self._shape_ok and self.root.winfo_ismapped():
            if self.label is None:
                self._unmap_container()
            # 同一 X 连接上按序：清屏 → 本帧形状 → 本帧像素
            shape_win = self._shape._top_ancestor(int(self.root.winfo_id()))
            paint_win = self._resolve_paint_target(shape_win)
            ok = self._shape.apply_frame(shape_win, paint_win, pil_rgba, name)
            self._report_shape(ok)
        self.root.geometry("+%d+%d" % (int(x), int(y)))


def _root_hwnd(root):
    """窗口的真实 OS 顶层句柄：Windows 上 Tk 的 winfo_id 是 Toplevel 的
    子窗口，分层/置顶 API 必须作用在祖先窗口；Linux 上就是 winfo_id。"""
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
            p = _find_sprite(n)
            if p:
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
        self.eat_plays = 0            # 吃蛋糕动画播放次数（播两遍）
        self._eat_glide = False       # 吃蛋糕时带着水平速度滑行（x 不停）
        self._going_cake = False      # 正在跳向蛋糕
        self._cake_chan_wait = False  # 看到蛋糕先播「馋」，播完再跳过去
        self._cake_jump_bonus = 0     # 够不到蛋糕时，每次加跳高度（px）
        self.last_facing = 1          # 最近一次水平移动方向（右=1 / 左=-1）
        self.drag_off = None
        self._press_time = None
        self._press_pos = None
        self._drag_from_special = False   # 拖拽前处于 睡觉/想回家/吃蛋糕
        self._dragged = False             # 本次按下后是否真的拖动过
        self.heart_job = None
        self.heart_visible = False
        self.wake_job = None
        self._asleep = False
        self.sleep_prep = False       # 散步→困困→睡觉 流程进行中
        self.kunkun_plays = 0
        self.sticker_seq = []
        self._input_win = None        # Linux 鼠标事件接收用的 InputOnly 窗口
        self._bg_info = None          # Linux 背景色聚类缓存
        self._xdisp = None            # 复用的 python-xlib Display
        self.jumping = False          # 跳跃中：只受重力、不检测地面
        self._jump_y0 = 0             # 起跳时的 y
        self._stuck_pos = None               # 卡住检测：上次坐标快照
        self._stuck_since = 0                # 坐标未变化起始时刻
        self._next_jump_t = 0                # 周期性跳跃：下次跳跃时刻
        self._turn_cooldown = 0       # 转身冷却（tick 数）
        self._turn_x = None           # 上次转身时的 x
        self._menu_open = False       # 右键菜单弹出中（InputOnly 暂不抢占）
        self.home = None              # 小白之家（home.install 挂上）
        self.going_home = False       # 正在走回小家的路上
        self.at_home = False          # 已回到小家（窗口隐藏中）
        self._home_dialog = None      # 「我想回家」确认框
        self._desktop_dialog = None   # 「先回桌面好不好」确认框
        self.wave_loops = 0           # 弹窗期间挥手已播完的遍数
        self.sad_prep = False         # 被拒绝回家：哭哭→困困→睡觉 流程中
        self.sad_kunkun = False       # 哭完后的困困播放中
        self.kuku_plays = 0
        self._home_ask_t = time.monotonic() + random.uniform(60, 180)
        self._home_target_x = None    # 回家目标 x（门中心）
        self._home_target_y = None    # 回家目标 y（地面高度）

        w, h = self.window_size()
        if start_pos is not None:
            x, y = start_pos
        else:
            x = screen_w - w - 60
            y = root.winfo_screenheight() - h - 60
        self.x, self.y = x, y
        self.clamp()
        self._stuck_pos = (self.x, self.y)
        root.geometry("%dx%d+%d+%d" % (w, h, x, y))

        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=MAGENTA if IS_WIN else "#000000")
        if IS_WIN:
            root.attributes("-toolwindow", True)
        self.linux_key_ok = _apply_linux_keycolor(root)

        first_idle = self.anim["idle"][0][0]
        # Linux：不创建 Tk label——像素直接画在顶层窗口上，避免子窗口
        # 黑底盖住绘制；事件由 InputOnly 窗口轮询
        self.label = None
        self.surface = self._make_surface(w, h)
        self.surface.update(self.composite(first_idle), self.x, self.y, first_idle)
        if IS_WIN:
            print("透明初始化: 分层窗口(per-pixel alpha) 已启用", file=sys.stderr)
            _force_topmost(_root_hwnd(self.root))
            # Windows：创建一个全尺寸 Label 作为 Tk 事件接收器（分层窗口
            # 的不透明像素命中窗口后由它接收点击/拖拽；Linux 走 InputOnly）。
            self.label = tk.Label(root, bg=MAGENTA, bd=0)
            self.label.place(x=0, y=0, width=w, height=h)
            event_widget = self.label
            event_widget.bind("<ButtonPress-1>", self.on_press)
            event_widget.bind("<B1-Motion>", self.on_drag)
            event_widget.bind("<ButtonRelease-1>", self.on_release)
            event_widget.bind("<Double-Button-1>", self.on_double)
            event_widget.bind("<ButtonRelease-3>", self.popup_menu)
            self.tick()
            self.keep_topmost()
            self.watch_config()
            self._start_walk_burst()
            self._ensure_fall_loop()
            self.root.after(500, self._check_want_home)
            if not test_mode:
                self.schedule_action(2200)
            return
        shape = getattr(self.surface, "_shape", None)
        reason = shape.fail_reason if shape is not None else "未知"
        print("透明初始化: transparentcolor=%s SHAPE连接=%s %s | 会话=%s "
              "桌面=%s DISPLAY=%r 屏幕=%r" % (
                  "是" if self.linux_key_ok else "否(Windows专属,正常)",
                  "是" if getattr(self.surface, "_shape_ok", False) else "否",
                  "" if not reason else "原因: " + reason,
                  os.environ.get("XDG_SESSION_TYPE", "?"),
                  os.environ.get("XDG_CURRENT_DESKTOP", "?"),
                  os.environ.get("DISPLAY"),
                  root.tk.call("winfo", "screen", ".")), file=sys.stderr)

        event_widget = self.label if self.label is not None else root
        event_widget.bind("<ButtonPress-1>", self.on_press)
        event_widget.bind("<B1-Motion>", self.on_drag)
        event_widget.bind("<ButtonRelease-1>", self.on_release)
        event_widget.bind("<Double-Button-1>", self.on_double)
        # 右键在“松开”时才弹菜单：按下/松开右键只会开菜单，不会被当成
        # 点击去激活菜单项；菜单项只能用左键点击触发
        event_widget.bind("<ButtonRelease-3>", self.popup_menu)

        self.tick()
        self.keep_topmost()
        self.watch_config()
        self._start_walk_burst()
        self._ensure_fall_loop()
        self.root.after(500, self._check_want_home)
        if not IS_WIN and self.label is None:
            self.root.after(16, self._poll_x_events)
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
            display = img if IS_WIN else _flatten_straight(img, key=LINUX_FILL)
            self.photos[name] = ImageTk.PhotoImage(display)
            self.frames[name] = img
            if name.startswith("walk_") or (
                    self.walk_group and
                    (name == self.walk_group or name.startswith(self.walk_group + "_"))):
                # right-facing variants
                fimg = img.transpose(Image.FLIP_LEFT_RIGHT)
                fdisplay = fimg if IS_WIN else _flatten_straight(
                    fimg, key=LINUX_FILL)
                self.photos[name + "_flip"] = ImageTk.PhotoImage(fdisplay)
                self.frames[name + "_flip"] = fimg

    def _make_surface(self, w, h):
        if IS_WIN:
            return _LayeredSurface(lambda: _root_hwnd(self.root), w, h)
        return _KeyedSurface(self.root, self.label, w, h,
                             key_ok=getattr(self, "linux_key_ok", False))

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
        w, h = self.window_size()
        self.surface = self._make_surface(w, h)
        self.surface.update(self.composite(self.current_frame()), self.x, self.y,
                            self.current_frame())
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
        """被喂食：播放「吃蛋糕」两遍；素材缺失时直接播放「爱你」。
        带着当前水平速度切换进来，边吃边滑行一小段（x 移动不停止）。"""
        self.wake()
        self.eat_flow = True
        self.eat_plays = 0
        self._eat_glide = abs(self.vx) > 0
        if self.anim.get("eat"):
            self.set_mode("eat")
        else:
            self.play_sticker("aini")
        self.priority_until_idle = True       # 吃蛋糕必须完整播完

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

    def start_dance(self):
        """菜单触发「跳舞」：用跳舞动画四处走 20~40 秒，然后回待机。"""
        if not self.anim.get("dance"):
            return
        self.set_mode("dance")
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
        self._next_jump_t = time.monotonic() + random.uniform(3, 10)

    def _is_walk_display(self, name):
        if self.mode in ("walk", "dance"):
            return True
        g = self.walk_group
        return bool(g) and (name == g or name.startswith(g + "_"))

    def _walk_step(self):
        now = time.monotonic()
        if self.going_home or self._going_cake:
            return   # 回家/去蛋糕的移动由 _fall_loop 高频驱动
        if self.mode in ("walk", "dance") and now >= self.walk_mode_until:
            if self.sleep_prep:
                self._play_kunkun()
            else:
                # 菜单触发的「跳舞」只走 20~40 秒，然后回待机，
                # 让睡觉等平常动作能继续自动触发
                self.set_mode("idle")
            return
        # 散步中永不停歇：不进入「休息」状态，持续按地形移动
        if self.walk_state != "walk":
            self._start_walk_burst()
        self._step_with_terrain()
        self._ensure_fall_loop()

    def _ensure_fall_loop(self):
        if not self._fall_active:
            self._fall_active = True
            self.root.after(16, self._fall_loop)

    def _fall_loop(self):
        """持续检测重力/地形：下落是最高优先级，任何动作下悬空都会下落。
        每帧先算重力，再处理各动作的水平移动；只有直线回家豁免重力
        （用户要求无视地板规则）。单帧出错也不能让下落停掉，继续调度。"""
        try:
            if self.at_home:
                self.root.after(16, self._fall_loop)
                return
            # 下落优先：悬空就先落，再执行动作的水平移动
            if not self.going_home:
                self.apply_gravity()
            if self.jumping:
                if self._going_cake:
                    self._step_cake()
                elif self.going_home or self._is_walk_display(self.current_frame()):
                    # 跳跃期间：高频水平推进，保持水平速度穿过障碍
                    self.move(self.vx, 0)
            elif self._going_cake:
                self._step_cake()
            elif self.going_home:
                self._step_home()        # 直线回家：无视地板/地形规则
            elif self._is_walk_display(self.current_frame()):
                if self.walk_state == "walk" and self.vx and not self.drag_off:
                    now = time.monotonic()
                    if now >= self._next_jump_t:
                        # 周期性跳跃：每 3~10 秒跳一次
                        self._start_jump()
                    else:
                        # 卡住检测：散步中坐标 1 秒没变 -> 触发跳跃脱困
                        pos = (self.x, self.y)
                        if pos != self._stuck_pos:
                            self._stuck_pos = pos
                            self._stuck_since = now
                        elif now - self._stuck_since >= 1.0:
                            self._start_jump()
            self.root.after(16, self._fall_loop)
        except Exception:
            # 单帧出错不能让下落停掉：继续调度
            self._fall_active = True
            self.root.after(16, self._fall_loop)

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
        self.sad_prep = False
        self.sad_kunkun = False
        self.kuku_plays = 0
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

    # ------------------------------------------------------------ 小白之家
    def _check_want_home(self):
        """玩一会儿（60~180 秒）后想回家：弹确认框问用户。"""
        try:
            self._ensure_fall_loop()   # 兜底：下落循环万一停了立刻重启
            if (self.home and not self.at_home and not self.going_home
                    and not self._going_cake
                    and self._home_dialog is None
                    and self._desktop_dialog is None
                    and not self.drag_off and not self._asleep
                    and not self.priority_until_idle
                    and time.monotonic() >= self._home_ask_t):
                self._open_dialog("home")
            elif not self.drag_off and not self.priority_until_idle:
                if (self._home_dialog_open() and self.anim.get("wave")
                        and self.mode != "wave"):
                    # 对话框还开着：被其它动作打断后继续挥手
                    self.set_mode("wave")
                elif (self._desktop_dialog_open() and self.anim.get("wave")
                        and self.mode != "wave"):
                    # 二次询问还开着：被打断后继续挥手
                    self.set_mode("wave")
        except Exception:
            pass
        self.root.after(500, self._check_want_home)

    def _home_dialog_open(self):
        dlg = self._home_dialog
        if dlg is None:
            return False
        try:
            return dlg.winfo_exists()
        except Exception:
            return False

    def _desktop_dialog_open(self):
        dlg = self._desktop_dialog
        if dlg is None:
            return False
        try:
            return dlg.winfo_exists()
        except Exception:
            return False

    def _desktop_showing(self):
        """桌面是否已显示。Windows：直接视为是（回家时自己会最小化所有
        窗口）；Linux 查 EWMH _NET_SHOWING_DESKTOP。"""
        if IS_WIN:
            return True
        try:
            from Xlib import Xatom
            d = self._get_xdisp()
            if d is None:
                return True
            prop = d.screen().root.get_full_property(
                d.intern_atom("_NET_SHOWING_DESKTOP"), Xatom.CARDINAL)
            return bool(prop and prop.value and prop.value[0])
        except Exception:
            return True

    def _open_dialog(self, kind):
        """弹确认框。kind='home' 第一次问回家；kind='desktop' 不在桌面时再问。"""
        attr = "_%s_dialog" % kind
        if getattr(self, attr, None) is not None:
            try:
                if getattr(self, attr).winfo_exists():
                    return
            except Exception:
                pass
        self.wave_loops = 0           # 每次询问重新计数挥手遍数
        if kind == "home":
            text = "汪汪～我想回家，可以带我回家吗？"
            anim = "wave"
        else:
            text = "小白找不到家，先回桌面好不好"
            anim = "wave"
        # 弹窗期间循环播放对应动画
        if self.anim.get(anim) and self.mode != anim:
            self.set_mode(anim)
        dlg = tk.Toplevel(self.root)
        setattr(self, attr, dlg)
        dlg.title("小白之家")
        dlg.overrideredirect(True)      # 无边框气泡，悬在头顶
        dlg.attributes("-topmost", True)
        dlg.configure(bg=MENU_BG)
        dlg.resizable(False, False)
        dlg.protocol("WM_DELETE_WINDOW",
                     lambda: self._answer_dialog(kind, dlg, False))
        tk.Label(dlg, text=text,
                 bg=MENU_BG, fg=MENU_FG, font=DIALOG_FONT,
                 padx=28, pady=20).pack()
        btns = tk.Frame(dlg, bg=MENU_BG)
        btns.pack(pady=(0, 18))
        yes = tk.Button(btns, text="是", width=6, font=DIALOG_BTN_FONT,
                        bg=MENU_ACTIVE_BG, fg=MENU_ACTIVE_FG,
                        activebackground=MENU_ACTIVE_BG,
                        activeforeground=MENU_ACTIVE_FG,
                        command=lambda: self._answer_dialog(kind, dlg, True))
        no = tk.Button(btns, text="否", width=6, font=DIALOG_BTN_FONT,
                       bg=MENU_BG, fg=MENU_FG,
                       activebackground=MENU_ACTIVE_BG,
                       activeforeground=MENU_ACTIVE_FG,
                       command=lambda: self._answer_dialog(kind, dlg, False))
        yes.pack(side="left", padx=10)
        no.pack(side="left", padx=10)
        dlg.bind("<Return>", lambda e: self._answer_dialog(kind, dlg, True))
        dlg.bind("<Escape>", lambda e: self._answer_dialog(kind, dlg, False))
        dlg.update_idletasks()
        self._place_home_dialog(dlg)
        self.root.after(60, lambda: self._follow_dialog(kind))
        try:
            dlg.grab_set()
            dlg.focus_set()
        except Exception:
            pass

    def _place_home_dialog(self, dlg):
        """把「我想回家」对话框摆在小白头顶（顶部放不下就放脚下）。"""
        try:
            w, h = self.window_size()
            dw, dh = dlg.winfo_reqwidth(), dlg.winfo_reqheight()
            x = self.x + w // 2 - dw // 2
            y = self.y - dh - 6
            if y < 0:
                y = self.y + h + 6
            sw = self.root.winfo_screenwidth()
            x = max(2, min(x, sw - dw - 2))
            dlg.geometry("+%d+%d" % (x, y))
            dlg.lift()
        except Exception:
            pass

    def _follow_dialog(self, kind):
        """对话框跟随小白移动（每 60ms 对齐一次头顶位置）。"""
        dlg = getattr(self, "_%s_dialog" % kind, None)
        if dlg is None:
            return
        try:
            if not dlg.winfo_exists():
                setattr(self, "_%s_dialog" % kind, None)
                return
            self._place_home_dialog(dlg)
        except Exception:
            pass
        self.root.after(60, lambda: self._follow_dialog(kind))

    def _answer_dialog(self, kind, dlg, go):
        attr = "_%s_dialog" % kind
        if dlg is not getattr(self, attr, None):
            return
        setattr(self, attr, None)
        try:
            dlg.grab_release()
            dlg.destroy()
        except Exception:
            pass
        if kind == "home":
            if go:
                if self._desktop_showing():
                    # 已经在桌面：直接回家
                    import home
                    home.show_desktop()
                    self.go_home()
                else:
                    # 不在桌面：再问一次「先回桌面」
                    self._open_dialog("desktop")
            else:
                self._start_sad_flow()     # 两次回答里有一次「否」
        else:
            if go:
                import home
                home.show_desktop()       # 回到桌面后直线回家
                self.go_home()
            else:
                self._start_sad_flow()     # 两次回答里有一次「否」

    def _start_sad_flow(self):
        """被拒绝回家：哭哭两遍 → 困困一遍 → 睡觉。"""
        if self.sad_prep or self.sad_kunkun or self._asleep:
            return
        self.wave_loops = 0
        self.wake()
        self.priority_until_idle = False
        self._home_ask_t = time.monotonic() + random.uniform(60, 180)
        self.sad_prep = True
        self.kuku_plays = 0
        if self.anim.get("kuku"):
            self.play_sticker("kuku")
        else:
            self._play_sad_kunkun()

    def _play_sad_kunkun(self):
        """哭完两遍 → 困困一遍 → 睡觉。"""
        self.sad_prep = False
        self.kuku_plays = 0
        if self.anim.get("kunkun"):
            self.sad_kunkun = True
            self.play_sticker("kunkun")
        else:
            self.sleep()

    def _close_home_dialogs(self):
        """关掉所有回家询问对话框（挥手超时无人回答时调用）。"""
        for attr in ("_home_dialog", "_desktop_dialog"):
            dlg = getattr(self, attr, None)
            setattr(self, attr, None)
            if dlg is not None:
                try:
                    dlg.grab_release()
                    dlg.destroy()
                except Exception:
                    pass

    def go_home(self):
        """开始走回小屋：面向小屋，一路走过去（可跳/穿墙）。"""
        if not self.home:
            return
        self.wake()
        self.priority_until_idle = False
        self.eat_flow = False
        self._going_cake = False
        self.going_home = True
        self.at_home = False
        self._home_ask_t = float("inf")
        w, h = self.window_size()
        self._home_target_x = max(0, min(
            self.home.door_x() - w // 2,
            self.root.winfo_screenwidth() - w))
        # 目标在右下角家门口：y 落到地面线，避免只往右跑然后悬空消失
        self._home_target_y = max(0, min(
            self.home.ground_y() - h,
            self.root.winfo_screenheight() - h))
        if self.anim.get("home"):
            self.set_mode("home")        # 用「回家」专属动作
        elif self.anim.get("walk"):
            self.set_mode("walk")
        self.walk_state = "walk"
        self.vx = int(6 * self.scale) if self._home_target_x > self.x \
            else -int(6 * self.scale)
        if self.vx == 0:
            self.vx = 1 if self._home_target_x > self.x else -1

    def _step_home(self):
        """回家路上的一步：一步能到就进门，否则无视地板/地形，
        斜线直线走向右下角家门口（x 对齐门中心、y 落到地面）。"""
        tx, ty = self._home_target_x, self._home_target_y
        vy = 6 * self.scale
        if (abs(self.x - tx) <= abs(self.vx)
                and abs(self.y - ty) <= max(1, vy)):
            self.move(tx - self.x, ty - self.y)
            self._arrive_home()
            return
        dx = self.vx if abs(self.x - tx) > abs(self.vx) else (tx - self.x)
        if self.y < ty:
            dy = min(vy, ty - self.y)
        elif self.y > ty:
            dy = -min(vy, self.y - ty)
        else:
            dy = 0
        self.move(dx, dy)

    def go_to_cake(self):
        """蛋糕生成后：先播「馋」约 0.5 秒，播完换回散步、跳过去拿
        （碰到自动开吃，水平速度不停）。"""
        c = self.cake
        if not c or not c.active:
            return
        self.wake()
        self.priority_until_idle = False
        self.going_home = False
        self._going_cake = False
        self._cake_chan_wait = True
        if self.anim.get("chan"):
            # 馋只播约 0.5s（chan 每帧 70ms，取前 7 帧）
            chan = self.anim["chan"]
            self.sticker_seq = chan[:7] or chan
            self.mode = "sticker"
            self.fi = 0
            self._asleep = False
            self.priority_until_idle = True   # 馋播放中不可打断
        else:
            self._finish_cake_chan()

    def _finish_cake_chan(self):
        """馋播完：先朝蛋糕方向走过去，到正下方再原地起跳（碰到自动开吃）。"""
        self._cake_chan_wait = False
        c = self.cake
        if not c or not c.active:
            return
        self.priority_until_idle = False
        self._cake_jump_bonus = 0
        self._going_cake = True
        if self.anim.get("walk"):
            self.set_mode("walk")
        self.walk_state = "walk"
        self.jumping = False      # 先走过去，不急着跳

    def _step_cake(self):
        """走向蛋糕的一步：只朝蛋糕方向前进（不回头），到正下方后原地
        起跳；碰到就自动开吃，够不到就每次 +20px 跳高，直到拿到。"""
        c = self.cake
        if not c or not c.active:
            self._cake_jump_bonus = 0
            self._going_cake = False
            self.jumping = False
            return
        if c.touching_pet():
            self._cake_jump_bonus = 0    # 拿到了就恢复默认跳高
            self._going_cake = False
            self.jumping = False
            c.feed()
            return
        if self._cake_jump_bonus > 400:
            # 安全兜底：跳了很久还够不到（例如悬空时蛋糕变远）就直接吃
            self._cake_jump_bonus = 0
            self._going_cake = False
            self.jumping = False
            c.feed()
            return
        cx = c.cake_center()[0]
        px = self.x + self.window_size()[0] // 2
        step = max(1, int(3 * self.scale))
        dx = cx - px
        if abs(dx) > step:
            # 还没到蛋糕正下方：朝一个方向走过去，不跳
            self.vx = step if dx > 0 else -step
            self.move(self.vx, 0)
            return
        # 已到蛋糕正下方：原地起跳，够不到就每次 +20px 跳高
        self.vx = 0
        if not self.jumping:
            self._cake_jump_bonus += 20
            self._start_jump(JUMP_HEIGHT + self._cake_jump_bonus)

    def _arrive_home(self):
        """走到门口：躲进小屋（窗口隐藏），等主人敲门。"""
        self.going_home = False
        self.at_home = True
        self.vx = 0
        self.vy = 0
        self._home_target_x = None
        self.set_mode("idle")
        try:
            self.root.withdraw()
            if self._input_win:
                self._input_win[1].unmap()
                self._input_win[0].flush()
        except Exception:
            pass
        if self.home:
            self.home.bubble("回家啦～")

    def come_out(self):
        """主人敲了主目录（开门）：从右下角冒出来，开心一下再正常玩。"""
        if not self.at_home or not self.home:
            return
        if self.root.winfo_ismapped():
            # 小白已经出现在桌面上：绝不重复出来，避免“第二个小白”
            return
        self.at_home = False
        self.going_home = False
        self.x, self.y = self.home.appear_xy()
        self.clamp()
        self.root.geometry("+%d+%d" % (self.x, self.y))
        try:
            self.root.deiconify()
            self.root.lift()
        except Exception:
            pass
        if self._input_win:
            try:
                self._input_win[1].map()
                self._input_win[1].raise_window()
                self._input_win[0].flush()
            except Exception:
                pass
        self._home_ask_t = time.monotonic() + random.uniform(60, 180)
        self.wake()
        self.priority_until_idle = False
        self.schedule_action(1500)
        if self.anim.get("happy"):
            self.set_mode("happy")
            self.show_heart()

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
            p = _find_sprite(n)
            if p:
                new_base[n] = Image.open(p)
        if new_base:
            self.base = new_base
        self.build_photos()
        if self.anim.get(self.mode) or self.anim.get("idle"):
            self.surface.update(self.composite(self.current_frame()), self.x, self.y,
                                self.current_frame())

    def open_editor(self):
        editor = os.path.join(HERE, "pet_editor.py")
        try:
            subprocess = __import__("subprocess")
            subprocess.Popen([sys.executable, editor])
        except Exception:
            pass

    def restart_pet(self):
        """重启小白：先释放 InputOnly 事件窗口和单实例锁（否则新进程的
        事件窗口会被旧窗口挡住、鼠标无响应），再启动新进程并退出当前。"""
        if self._input_win:
            try:
                self._input_win[1].destroy()
                self._input_win[0].flush()
            except Exception:
                pass
            self._input_win = None
        try:
            if os.path.exists(LOCK_FILE):
                os.remove(LOCK_FILE)
        except Exception:
            pass
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
                if self.sleep_prep:
                    # 困困要连播两遍，播完才睡觉
                    self.kunkun_plays += 1
                    if self.kunkun_plays >= 2:
                        self._finish_sleep_prep()
                        seq = self.anim["sleep"] or self.anim["idle"]
                    else:
                        self._play_kunkun()
                        seq = self.sticker_seq
                elif self.sad_prep:
                    # 被拒绝回家：哭哭要连播两遍
                    self.kuku_plays += 1
                    if self.kuku_plays >= 2:
                        self._play_sad_kunkun()
                        seq = self.sticker_seq
                    else:
                        self.play_sticker("kuku")
                        seq = self.sticker_seq
                elif self.sad_kunkun:
                    # 哭完后的困困播一遍就睡觉
                    self.sad_kunkun = False
                    self.sleep()
                    seq = self.anim["sleep"] or self.anim["idle"]
                elif self._cake_chan_wait:
                    # 看到蛋糕后的「馋」播完：跳过去吃
                    self._finish_cake_chan()
                    seq = self.anim.get(self.mode) or self.anim["idle"]
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
                    self.eat_plays += 1
                    if self.eat_plays < 2:
                        # 吃蛋糕动画播放两遍
                        self.fi = 0
                        seq = self.anim["eat"]
                    elif self.anim.get("aini"):
                        # 吃完两遍 -> 无缝切换到「爱你」（不经过待机帧）
                        self.play_sticker("aini")
                        seq = self.sticker_seq
                    else:
                        self.set_mode("idle")
                        seq = self.anim["idle"]
                else:
                    if (self.mode == "wave"
                            and (self._home_dialog_open()
                                 or self._desktop_dialog_open())):
                        # 对话框还没回答：循环播放挥手；
                        # 连续播完 10 遍还没人回答 -> 关掉对话框，哭哭→睡觉
                        self.wave_loops += 1
                        if self.wave_loops >= 10:
                            self._close_home_dialogs()
                            self._start_sad_flow()
                            seq = self.sticker_seq or self.anim["idle"]
                        else:
                            self.fi = 0
                            seq = self.anim[self.mode]
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
        if self.mode == "eat" and self._eat_glide:
            # 吃蛋糕时水平速度不停：继续滑行并逐渐减速
            if abs(self.vx) > 1:
                self.move(self.vx, 0)
                self.vx = int(self.vx * 0.86)
            else:
                self._eat_glide = False
        walking = self._is_walk_display(name)
        if walking and self.vx != 0:
            if name.startswith("walk_"):
                if self.vx < 0:
                    name += "_flip"   # 散步贴纸: 向左移动时水平翻转
            elif name.startswith("dance_"):
                if self.vx > 0:
                    name += "_flip"   # 跳舞: 向右移动时水平翻转
            elif (self.walk_group
                    and (name == self.walk_group
                         or name.startswith(self.walk_group + "_"))
                    and self.vx < 0):
                name += "_flip"       # 散步贴纸: 向左移动时水平翻转
        if self.falling and walking:
            self.fi -= 1               # 冻结动画帧，只更新位置
        self.surface.update(self.composite(name), self.x, self.y, name)

        if walking:
            self._walk_step()

        self.root.after(ms, self.tick)

    def move(self, dx, dy):
        self.x += int(dx)
        self.y += int(dy)
        if int(dx) > 0:
            self.last_facing = 1
        elif int(dx) < 0:
            self.last_facing = -1
        self.clamp()
        self.root.geometry("+%d+%d" % (self.x, self.y))
        if self.test_log:
            self.test_log.write("move %d %d\n" % (self.x, self.y))
            self.test_log.flush()

    def apply_gravity(self):
        """No dark pixel underfoot -> fall with v = g*t (g = GRAVITY px/s^2)."""
        now = time.monotonic()
        dt = min(now - self._last_grav, 0.25) if self._last_grav else 0.0
        self._last_grav = now
        if self.jumping:
            # 跳跃中：只受重力，不检测脚下地面，直到落回起跳高度
            self.vy += GRAVITY * dt
            self._y_frac += self.vy * dt
            dy = int(self._y_frac)
            if dy:
                self._y_frac -= dy
                self.move(0, dy)
            if self.vy >= 0 and self.y >= self._jump_y0:
                self.jumping = False
                self.vy = 0
            self.falling = False
            return
        w, h = self.window_size()
        cx = self.x + w // 2
        bottom = self.y + h
        near_bottom = bottom >= self.root.winfo_screenheight() - 6
        ground = near_bottom or self._strip_has_floor(
            cx - int(w * 0.35), bottom + 1, int(w * 0.7), 5)
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

    def _get_xdisp(self):
        """复用 python-xlib Display 连接（每帧新建会连接泄漏，最终导致
        鼠标事件轮询失效）。"""
        if IS_WIN:
            return None   # Windows 抓屏用 GDI，不走 X11
        if getattr(self, "_xdisp", None) is None:
            try:
                from Xlib import display as _xd
                self._xdisp = _xd.Display()
            except Exception:
                self._xdisp = None
        return self._xdisp

    def _grab_rgb(self, x0, y0, w, h):
        """抓取屏幕矩形，返回 (h, w, 3) 的 uint8 RGB 数组；失败返回 None。
        Windows 用 BitBlt/GetDIBits，Linux 用 X11 get_image。"""
        if w <= 0 or h <= 0:
            return None
        if IS_WIN:
            try:
                import numpy as np
                user32 = ctypes.windll.user32
                gdi32 = ctypes.windll.gdi32
                hdc = user32.GetDC(0)
                mdc = gdi32.CreateCompatibleDC(hdc)
                hbm = gdi32.CreateCompatibleBitmap(hdc, int(w), int(h))
                old = gdi32.SelectObject(mdc, hbm)
                gdi32.BitBlt(mdc, 0, 0, int(w), int(h), hdc,
                             int(x0), int(y0), 0x00CC0020)

                class _BMI(ctypes.Structure):
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
                        ("biClrImportant", ctypes.c_uint32)]
                bmi = _BMI()
                bmi.biSize = ctypes.sizeof(_BMI)
                bmi.biWidth = int(w)
                bmi.biHeight = -int(h)
                bmi.biPlanes = 1
                bmi.biBitCount = 32
                bmi.biCompression = 0
                bmi.biSizeImage = int(w) * int(h) * 4
                buf = ctypes.create_string_buffer(int(w) * int(h) * 4)
                gdi32.GetDIBits(mdc, hbm, 0, int(h), buf, ctypes.byref(bmi), 0)
                gdi32.SelectObject(mdc, old)
                gdi32.DeleteObject(hbm)
                gdi32.DeleteDC(mdc)
                user32.ReleaseDC(0, hdc)
                arr = np.frombuffer(buf.raw, dtype=np.uint8).reshape(h, w, 4)
                return arr[:, :, :3][:, :, ::-1].copy()   # BGRA -> RGB
            except Exception:
                return None
        try:
            import numpy as np
            from Xlib import X
            d = self._get_xdisp()
            if d is None:
                return None
            raw = d.screen().root.get_image(
                int(x0), int(y0), int(w), int(h), X.ZPixmap, 0xffffffff)
            data = raw.data
            if len(data) == w * h * 4:
                arr = np.frombuffer(data, dtype=np.uint8).reshape(h, w, 4)
                return arr[:, :, :3][:, :, ::-1].copy()
            if len(data) == w * h * 3:
                arr = np.frombuffer(data, dtype=np.uint8).reshape(h, w, 3)
                return arr.copy()
        except Exception:
            pass
        return None

    def _update_bg(self):
        """抓取小白周围 BG_SIZE x BG_SIZE 的像素，把 RGB 量化成
        4096 个颜色桶，占比最高的桶作为"背景板"颜色（含相似桶）。
        结果缓存到 self._bg_info，固定每 BG_REFRESH_S 秒刷新一次。"""
        now = time.monotonic()
        info = getattr(self, "_bg_info", None)
        if info and now - info["t"] < BG_REFRESH_S:
            return
        try:
            import numpy as np
            w, h = self.window_size()
            cx, cy = self.x + w // 2, self.y + h // 2
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            half = BG_SIZE // 2
            x0 = max(0, cx - half)
            y0 = max(0, cy - half)
            x1 = min(sw, cx + half)
            y1 = min(sh, cy + half)
            ww, hh = x1 - x0, y1 - y0
            if ww <= 0 or hh <= 0:
                return
            rgb = self._grab_rgb(x0, y0, ww, hh)
            if rgb is None:
                return
            rgb = rgb.astype(np.int16)
            q = rgb // BG_QUANT
            flat = q[..., 0] * 256 + q[..., 1] * 16 + q[..., 2]
            counts = np.bincount(flat.ravel(), minlength=16 ** 3)
            top = int(counts.argmax())
            top_rgb = (
                (top // 256) * BG_QUANT,
                ((top // 16) % 16) * BG_QUANT,
                (top % 16) * BG_QUANT)
            self._bg_info = {
                "t": now, "x": self.x, "y": self.y,
                "rgb": top_rgb, "ratio": float(counts[top] / counts.sum()),
            }
        except Exception:
            pass

    def _strip_has_floor(self, x0, y0, w, h):
        """抓取小白脚下 strip，统计"非背景色"（地板）像素占比；
        占比超过 FLOOR_RATIO 就认为有地板可踩。"""
        self._update_bg()
        info = getattr(self, "_bg_info", None)
        if info is None:
            return True   # 拿不到背景时视为始终有地面（不坠落）
        try:
            import numpy as np
            rgb = self._grab_rgb(int(x0), int(y0), int(w), int(h))
            if rgb is None:
                return True
            rgb = rgb.astype(np.int16)
            # 按量化桶判同类：与背景量化到同一桶的像素 = 背景，
            # 其他 = 地板。渐变/相近色自然归为一类。
            bq = tuple(c // BG_QUANT for c in info["rgb"])
            q = rgb // BG_QUANT
            floor = ((q[..., 0] != bq[0]) |
                     (q[..., 1] != bq[1]) |
                     (q[..., 2] != bq[2]))
            return bool(floor.mean() > FLOOR_RATIO)
        except Exception:
            return True   # 无法抓屏时视为始终有地面（不坠落）

    def _probe_nonbg_top(self, x0, y0, w, h):
        """抓取一块屏幕区域，返回最上方"非背景"像素的行号；
        没有非背景像素或抓屏失败时返回 None。"""
        self._update_bg()
        info = getattr(self, "_bg_info", None)
        if info is None:
            return None
        try:
            import numpy as np
            rgb = self._grab_rgb(int(x0), int(y0), int(w), int(h))
            if rgb is None:
                return None
            rgb = rgb.astype(np.int16)
            bq = tuple(c // BG_QUANT for c in info["rgb"])
            q = rgb // BG_QUANT
            floor = ((q[..., 0] != bq[0]) |
                     (q[..., 1] != bq[1]) |
                     (q[..., 2] != bq[2]))
            rows = np.where(floor.any(axis=1))[0]
            if len(rows) == 0:
                return None
            return y0 + int(rows.min())
        except Exception:
            return None

    def _terrain_ahead(self):
        """探测前进方向的非背景轮廓，返回 (kind, height)。
        kind: "none" 无障碍 / "step" 低台阶(<=CLIMB_MAX) / "jump" 中台阶
        (<=JUMP_MAX) / "wall" 高墙(过不去)。"""
        w, h = self.window_size()
        direction = 1 if self.vx > 0 else -1
        foot = self.y + h
        scan_h = h + 24
        px = self.x + (w if direction > 0 else 0) + direction * TERRAIN_PROBE
        x0 = px if direction > 0 else px - 8
        top_y = self._probe_nonbg_top(x0, foot - scan_h + 1, 8, scan_h)
        if top_y is None:
            return ("none", 0)
        if top_y >= foot - 2:
            return ("none", 0)      # 只有脚下同高的地面，不是障碍
        obstacle_h = foot - top_y
        if obstacle_h <= CLIMB_MAX:
            return ("step", obstacle_h)
        if obstacle_h <= JUMP_MAX:
            return ("jump", obstacle_h)
        return ("wall", obstacle_h)

    def _inside_wall(self):
        """小白是否已身处墙中：运动反方向（身后）也有高墙。
        是 -> 前方探测到的"墙"其实是穿行中的墙体内部，继续走即可。"""
        w, h = self.window_size()
        direction = 1 if self.vx > 0 else -1
        foot = self.y + h
        scan_h = h + 24
        px = self.x + (0 if direction > 0 else w)
        x0 = px - 8 if direction > 0 else px
        top_y = self._probe_nonbg_top(x0, foot - scan_h + 1, 8, scan_h)
        if top_y is None:
            return False
        obstacle_h = foot - top_y
        return obstacle_h > JUMP_MAX

    def _start_jump(self, height=None):
        """开始物理跳跃：受重力上抛，跳跃期间保持水平速度穿过障碍。"""
        self.jumping = True
        self._jump_y0 = self.y
        h = JUMP_HEIGHT if height is None else height
        self.vy = -int((2 * GRAVITY * h) ** 0.5)
        self._next_jump_t = time.monotonic() + random.uniform(3, 10)

    def _step_with_terrain(self):
        """按前方地形移动：无障碍直走；低台阶走上；中台阶跳上；
        高墙过不去就转身；已进入墙内则继续走穿过去。"""
        if self.jumping:
            # 跳跃中继续冲：保持水平速度，即使有障碍也穿过去
            self.move(self.vx, 0)
            return
        if self._turn_cooldown > 0:
            self._turn_cooldown -= 1
        kind, height = self._terrain_ahead()
        if kind == "none":
            self.move(self.vx, 0)
        elif kind == "step":
            self.y -= height
            self.move(self.vx, 0)
        elif kind == "jump":
            if not self.jumping:
                self._start_jump()
            self.move(self.vx, 0)
        else:   # wall
            if self.going_home or self._inside_wall():
                # 已进入墙里 / 回家路上：继续走穿过去
                self.move(self.vx, 0)
                return
            if self._turn_cooldown > 0:
                # 刚转身：朝新方向继续走，不停
                self.move(self.vx, 0)
                return
            if self._turn_x is not None and abs(self.x - self._turn_x) < 15:
                # 转身后几乎没动 -> 被卡住：跳起来穿过去，别原地停
                self._start_jump()
                return
            self.vx = -self.vx          # 转身
            self._turn_x = self.x
            self._turn_cooldown = 25
            self.move(self.vx, 0)       # 转身后立即继续走

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
    def _poll_x_events(self):
        """Linux 自绘窗口的鼠标事件轮询：用一个不可见的 InputOnly 窗口
        覆盖宠物区域接收鼠标事件（Tk 只处理容器子窗口的事件，而容器已
        unmap；外部客户端也不能对 Tk 窗口 XSelectInput）。事件转发给
        on_press / on_drag / on_release / popup_menu。"""
        if self.label is not None:
            return
        if self.at_home:
            # 在家（隐藏）时不接收鼠标事件
            if self._input_win:
                try:
                    self._input_win[1].unmap()
                    self._input_win[0].flush()
                except Exception:
                    pass
            self.root.after(16, self._poll_x_events)
            return
        try:
            shape = getattr(self.surface, "_shape", None)
            if shape is None or not shape.ok:
                self.root.after(16, self._poll_x_events)
                return
            dpy = shape._dpy
            if self._input_win is None:
                w, h = self.window_size()
                self._input_win = shape.create_input_window(
                    self.x, self.y, w, h)
                if os.environ.get("PET_EV_DEBUG"):
                    print("EV: input win=%s" % (
                        hex(self._input_win[1].id)
                        if self._input_win else None), file=sys.stderr)
            else:
                shape.move_input_window(self._input_win, self.x, self.y)
            if self._input_win:
                from Xlib import X as _X
                d, _win = self._input_win
                while d.pending_events():
                    ev = d.next_event()
                    t = ev.type
                    if os.environ.get("PET_EV_DEBUG"):
                        print("EV: type=%s detail=%s root=(%s,%s)" % (
                            t, getattr(ev, "detail", None),
                            getattr(ev, "root_x", None),
                            getattr(ev, "root_y", None)), file=sys.stderr)
                    from types import SimpleNamespace
                    e = SimpleNamespace(
                        x_root=getattr(ev, "root_x", 0),
                        y_root=getattr(ev, "root_y", 0),
                        x=getattr(ev, "x", 0), y=getattr(ev, "y", 0),
                        num=getattr(ev, "detail", 0),
                        state=getattr(ev, "state", 0))
                    if t == _X.ButtonPress:
                        if e.num == 1:
                            now = int(self.root.tk.call("clock", "milliseconds"))
                            if (self._press_time is not None and
                                    now - self._press_time < 350):
                                self.on_double(e)
                            else:
                                self.on_press(e)
                    elif t == _X.MotionNotify and self.drag_off:
                        self.on_drag(e)
                    elif t == _X.ButtonRelease:
                        if e.num == 1:
                            self.on_release(e)
                        elif e.num == 3:
                            # 右键只弹菜单，不触发其它动作
                            self.popup_menu(e)
        except Exception as e:
            if os.environ.get("PET_EV_DEBUG"):
                import traceback
                traceback.print_exc()
        self.root.after(16, self._poll_x_events)

    def on_press(self, event):
        if getattr(event, "num", 1) != 1:
            return   # 只有左键触发
        if os.environ.get("PET_EV_DEBUG"):
            print("EV: on_press xr=%d yr=%d" % (event.x_root, event.y_root),
                  file=sys.stderr)
        if self.priority_until_idle and self.mode != "eat":
            return   # 馋播放中不响应；吃蛋糕允许被拎走
        # 记录拖拽前的特殊状态：睡觉 / 想回家弹窗 / 吃蛋糕
        self._drag_from_special = bool(
            self.mode == "sleep" or self._asleep
            or self._home_dialog_open() or self._desktop_dialog_open()
            or self.mode == "eat" or self.eat_flow)
        self._dragged = False
        self.wake()
        self.drag_off = (event.x_root - self.x, event.y_root - self.y)
        self._press_time = int(self.root.tk.call("clock", "milliseconds"))
        self._press_pos = (event.x_root, event.y_root)
        if self.anim.get("drag"):
            self.set_mode("drag")
        if self.test_log:
            self.test_log.write("press %d %d off=%s\n" % (event.x_root, event.y_root, self.drag_off))
            self.test_log.flush()

    def on_drag(self, event):
        # 注意：MotionNotify 事件的 num 不是按键号（是移动提示），
        # 拖拽合法性由 self.drag_off（左键按下才置位）把关
        self._dragged = True
        if os.environ.get("PET_EV_DEBUG"):
            print("EV: on_drag xr=%d x=%d" % (event.x_root, self.x),
                  file=sys.stderr)
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
        if getattr(event, "num", 1) != 1:
            return   # 只有左键触发
        if self.priority_until_idle and self.mode != "eat":
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
        if (self._drag_from_special and self._dragged
                and self.anim.get("kuku")):
            # 从 睡觉/想回家/吃蛋糕 状态被拖走再放下 -> 委屈地哭一次
            self.play_sticker("kuku")
        self._drag_from_special = False
        self._dragged = False
        if self.test_log:
            self.test_log.write("release %d %d\n" % (event.x_root, event.y_root))
            self.test_log.flush()

    def on_double(self, event):
        if getattr(event, "num", 1) != 1:
            return   # 只有左键触发
        if self.priority_until_idle:
            return
        self.wake()
        if self._is_walk_display(self.current_frame()) and not self.jumping:
            # 散步中双击：物理跳跃并保持水平速度，不停下来
            self._start_jump()
            self.show_heart()
        elif self.anim.get("jump"):
            self.set_mode("jump")
            self.show_heart()

    def popup_menu(self, event):
        if self._menu_open:
            return   # Linux：菜单开着时不再重复弹出（防 InputOnly 盖菜单）
        menu = tk.Menu(self.root, tearoff=0,
                       font=MENU_FONT,
                       bg=MENU_BG, fg=MENU_FG,
                       activebackground=MENU_ACTIVE_BG,
                       activeforeground=MENU_ACTIVE_FG)
        # 菜单弹出期间隐藏 InputOnly 事件窗口：它每帧被 raise 到最上层，
        # 会盖住菜单、让"退出"等菜单项点不到
        if not IS_WIN:
            # Windows 没有 InputOnly 窗口，也不需要这个开关；而且 Windows
            # 上菜单关闭不触发 <Unmap>，开关会卡死导致之后右键全部失效。
            self._menu_open = True
            if self._input_win:
                try:
                    self._input_win[1].unmap()
                    self._input_win[0].flush()
                except Exception:
                    pass

        def _close(_e=None):
            self._menu_open = False
            if self._input_win:
                try:
                    self._input_win[1].map()
                    self._input_win[0].flush()
                except Exception:
                    pass
        menu.bind("<Unmap>", _close)

        def free(fn):
            return fn if not self.priority_until_idle else (lambda: None)
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
        if self.anim.get("dance"):
            menu.add_command(label=_group_cfg(self.cfg, "dance")["name"],
                             command=free(self.start_dance))
        if self.anim.get("sleep"):
            menu.add_command(label=_group_cfg(self.cfg, "sleep")["name"],
                             command=free(self.sleep))
        menu.add_command(label="醒来", command=self.wake)
        if self.home:
            menu.add_command(label="想回家", command=free(lambda: self._open_dialog("home")))
        if getattr(self, "cake", None):
            menu.add_command(label="投喂",
                             command=free(self.cake.spawn_near_me))
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
    _enable_dpi_awareness()
    if not test_mode:
        _single_instance()
    root = tk.Tk()
    root.withdraw()
    pet = Pet(root, test_mode=test_mode, start_pos=start_pos)
    root.deiconify()
    pet.surface.update(pet.composite(pet.current_frame()), pet.x, pet.y,
                       pet.current_frame())
    if not test_mode:
        import cake
        cake.install(root, pet)
        import home
        home.install(root, pet)
    if auto_close_ms:
        root.after(auto_close_ms, root.destroy)
    try:
        root.mainloop()
    finally:
        if not test_mode:
            try:
                if os.path.exists(LOCK_FILE):
                    with open(LOCK_FILE, "r", encoding="utf-8") as f:
                        if f.read().strip() == str(os.getpid()):
                            os.remove(LOCK_FILE)   # 只删自己的锁
            except Exception:
                pass


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    pos_args = [a.split("=", 1)[1] for a in args if a.startswith("--pos=")]
    main(
        test_mode="--no-random" in args,
        start_pos=tuple(int(v) for v in pos_args[0].split(",")) if pos_args else None,
    )
