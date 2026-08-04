# -*- coding: utf-8 -*-
"""小白桌面宠物 - a floppy-eared white puppy that lives on your desktop.

Run:  python3 pet.py   (Linux)
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
MENU_FONT = ("song ti", 36)
MENU_BG = "#2b2b2b"
MENU_FG = "#f0f0f0"
MENU_ACTIVE_BG = "#3c6fd0"
MENU_ACTIVE_FG = "#ffffff"

def _seq(prefix, ms):
    files = sorted(glob.glob(os.path.join(SPR, prefix + "_*.png")))
    return [(os.path.splitext(os.path.basename(f))[0], ms) for f in files]


_MS = {"like": 70, "chan": 70, "aini": 70, "happy": 33,
       "sleep": 31, "sleepb": 150, "eat": 33, "kunkun": 56}


def _seqs():
    """Frame sequences for every group, re-globbed from sprites/ each call so
    deleted actions disappear and re-added ones appear."""
    seqs = {g: _seq(g, ms) for g, ms in _MS.items()}
    seqs["walk"] = [("walk_%d" % i, 105) for i in range(4)
                    if os.path.exists(os.path.join(SPR, "walk_%d.png" % i))]
    seqs["drag"] = [("drag", 120)] if os.path.exists(os.path.join(SPR, "drag.png")) else []
    seqs["wave"] = [("wave", 150)] * 4 if os.path.exists(os.path.join(SPR, "wave.png")) else []
    seqs["jump"] = [("jump", 100), ("jump", 110), ("jump", 180)] \
        if os.path.exists(os.path.join(SPR, "jump.png")) else []
    seqs["sit"] = [("sit", 260)] * 4 if os.path.exists(os.path.join(SPR, "sit.png")) else []
    return seqs


SEQ = _seqs()

IDLE_ORDER = ["like", "chan", "aini"]   # idle plays these in order
ONE_SHOT = {"happy", "wave", "jump", "sit", "eat"}
        # one-shot actions return to idle when finished ("eat" continues to 爱你)
FRAME_NAMES = sorted(os.path.splitext(os.path.basename(f))[0]
                     for f in glob.glob(os.path.join(SPR, "*.png")))

CONFIG_PATH = os.path.join(HERE, "pet_config.json")
LOCK_FILE = os.path.join(HERE, ".pet.lock")


def _single_instance():
    """单实例锁：已有小白在跑就先终止它，再启动新的，避免堆积垃圾进程。"""
    try:
        if os.path.exists(LOCK_FILE):
            with open(LOCK_FILE, "r", encoding="utf-8") as f:
                pid = int((f.read() or "0").strip() or 0)
            if pid and pid != os.getpid():
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
    try:
        root.attributes("-transparentcolor", MAGENTA)
        return root.attributes("-transparentcolor") == MAGENTA
    except tk.TclError:
        return False


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
    """X11 顶层窗口 id（就是 Tk 的 winfo_id）。"""
    return root.winfo_id()


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
        root.configure(bg="#000000")
        self.linux_key_ok = _apply_linux_keycolor(root)

        first_idle = self.anim["idle"][0][0]
        # Linux：不创建 Tk label——像素直接画在顶层窗口上，避免子窗口
        # 黑底盖住绘制；事件由 InputOnly 窗口轮询
        self.label = None
        self.surface = self._make_surface(w, h)
        self.surface.update(self.composite(first_idle), self.x, self.y, first_idle)
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
        event_widget.bind("<Button-3>", self.popup_menu)

        self.tick()
        self.keep_topmost()
        self.watch_config()
        self._start_walk_burst()
        self._ensure_fall_loop()
        if self.label is None:
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
            display = _flatten_straight(img, key=LINUX_FILL)
            self.photos[name] = ImageTk.PhotoImage(display)
            self.frames[name] = img
            if name.startswith("walk_") or (
                    self.walk_group and
                    (name == self.walk_group or name.startswith(self.walk_group + "_"))):
                # right-facing variants
                fimg = img.transpose(Image.FLIP_LEFT_RIGHT)
                fdisplay = _flatten_straight(fimg, key=LINUX_FILL)
                self.photos[name + "_flip"] = ImageTk.PhotoImage(fdisplay)
                self.frames[name + "_flip"] = fimg

    def _make_surface(self, w, h):
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
        self.eat_flow = True
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
                self._step_with_terrain()
        elif now >= self.rest_until:
            self._start_walk_burst()
        self._ensure_fall_loop()

    def _ensure_fall_loop(self):
        if not self._fall_active:
            self._fall_active = True
            self.root.after(16, self._fall_loop)

    def _fall_loop(self):
        """持续检测重力/地形：任何显示模式下小白悬空都会下落。
        走路时保持高频（16ms）让下落平滑；跳跃期间高频水平推进穿过障碍；
        散步时每 3~10 秒自动跳一次；走着却 1 秒没挪窝（卡住）也跳。"""
        try:
            if self._is_walk_display(self.current_frame()):
                if self.jumping:
                    # 跳跃期间：高频水平推进，保持水平速度穿过障碍
                    self.move(self.vx, 0)
                elif self.walk_state == "walk" and self.vx and not self.drag_off:
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
            self.apply_gravity()
            self.root.after(16, self._fall_loop)
        except Exception:
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
        self.surface.update(self.composite(name), self.x, self.y, name)

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
        ground = near_bottom or self._strip_has_floor_linux(
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
        if getattr(self, "_xdisp", None) is None:
            try:
                from Xlib import display as _xd
                self._xdisp = _xd.Display()
            except Exception:
                self._xdisp = None
        return self._xdisp

    def _update_bg_linux(self):
        """X11: 抓取小白周围 BG_SIZE x BG_SIZE 的像素，把 RGB 量化成
        4096 个颜色桶，占比最高的桶作为"背景板"颜色（含相似桶）。
        结果缓存到 self._bg_info，固定每 BG_REFRESH_S 秒刷新一次。"""
        now = time.monotonic()
        info = getattr(self, "_bg_info", None)
        if info and now - info["t"] < BG_REFRESH_S:
            return
        try:
            import numpy as np
            from Xlib import X
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
            d = self._get_xdisp()
            if d is None:
                return
            raw = d.screen().root.get_image(
                x0, y0, ww, hh, X.ZPixmap, 0xffffffff)
            data = raw.data
            if len(data) == ww * hh * 4:
                arr = np.frombuffer(data, dtype=np.uint8).reshape(hh, ww, 4)
                rgb = arr[:, :, :3][:, :, ::-1].astype(np.int16)
            elif len(data) == ww * hh * 3:
                arr = np.frombuffer(data, dtype=np.uint8).reshape(hh, ww, 3)
                rgb = arr.astype(np.int16)
            else:
                return
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

    def _strip_has_floor_linux(self, x0, y0, w, h):
        """X11: 抓取小白脚下 strip，统计"非背景色"（地板）像素占比；
        占比超过 FLOOR_RATIO 就认为有地板可踩。"""
        self._update_bg_linux()
        info = getattr(self, "_bg_info", None)
        if info is None:
            return True   # 拿不到背景时视为始终有地面（不坠落）
        try:
            import numpy as np
            from Xlib import X
            d = self._get_xdisp()
            if d is None:
                return True
            raw = d.screen().root.get_image(
                int(x0), int(y0), int(w), int(h), X.ZPixmap, 0xffffffff)
            data = raw.data
            if len(data) == w * h * 4:
                arr = np.frombuffer(data, dtype=np.uint8).reshape(h, w, 4)
                rgb = arr[:, :, :3][:, :, ::-1].astype(np.int16)
            elif len(data) == w * h * 3:
                arr = np.frombuffer(data, dtype=np.uint8).reshape(h, w, 3)
                rgb = arr.astype(np.int16)
            else:
                return True
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
        self._update_bg_linux()
        info = getattr(self, "_bg_info", None)
        if info is None:
            return None
        try:
            import numpy as np
            from Xlib import X
            d = self._get_xdisp()
            if d is None:
                return None
            raw = d.screen().root.get_image(
                int(x0), int(y0), int(w), int(h),
                X.ZPixmap, 0xffffffff)
            data = raw.data
            if len(data) == w * h * 4:
                arr = np.frombuffer(data, dtype=np.uint8).reshape(h, w, 4)
                rgb = arr[:, :, :3][:, :, ::-1].astype(np.int16)
            elif len(data) == w * h * 3:
                arr = np.frombuffer(data, dtype=np.uint8).reshape(h, w, 3)
                rgb = arr.astype(np.int16)
            else:
                return None
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

    def _start_jump(self):
        """开始物理跳跃：受重力上抛，跳跃期间保持水平速度穿过障碍。"""
        self.jumping = True
        self._jump_y0 = self.y
        self.vy = -JUMP_SPEED
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
            if self._inside_wall():
                # 已经进入墙里：前方墙是墙体内部，别停/转身，继续走穿过去
                self.move(self.vx, 0)
                return
            if self._turn_cooldown > 0:
                return                  # 刚转身过：站住，冷却后再决定
            if self._turn_x is not None and abs(self.x - self._turn_x) < 15:
                return                  # 转身后几乎没动 -> 被困，站住不抖
            self.vx = -self.vx          # 转身
            self._turn_x = self.x
            self._turn_cooldown = 25

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
                        elif e.num == 3:
                            self.popup_menu(e)
                    elif t == _X.MotionNotify and self.drag_off:
                        self.on_drag(e)
                    elif t == _X.ButtonRelease and e.num == 1:
                        self.on_release(e)
        except Exception as e:
            if os.environ.get("PET_EV_DEBUG"):
                import traceback
                traceback.print_exc()
        self.root.after(16, self._poll_x_events)

    def on_press(self, event):
        if os.environ.get("PET_EV_DEBUG"):
            print("EV: on_press xr=%d yr=%d" % (event.x_root, event.y_root),
                  file=sys.stderr)
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
            self.show_heart()

    def popup_menu(self, event):
        menu = tk.Menu(self.root, tearoff=0,
                       font=MENU_FONT,
                       bg=MENU_BG, fg=MENU_FG,
                       activebackground=MENU_ACTIVE_BG,
                       activeforeground=MENU_ACTIVE_FG)
        # 菜单弹出期间隐藏 InputOnly 事件窗口：它每帧被 raise 到最上层，
        # 会盖住菜单、让"退出"等菜单项点不到
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
        if self.anim.get("sleep"):
            menu.add_command(label=_group_cfg(self.cfg, "sleep")["name"],
                             command=free(self.sleep))
        menu.add_command(label="醒来", command=self.wake)
        if getattr(self, "cake", None):
            menu.add_command(label="拿取蛋糕",
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
