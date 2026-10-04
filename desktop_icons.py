# -*- coding: utf-8 -*-
"""桌面图标踢飞（Windows）：小白在桌面时，把身体附近的图标朝外推开。

Windows 11 上向桌面 SysListView32 发送 LVM_SETITEMPOSITION 已经失效，这里改用
官方支持的 COM 接口：IShellWindows -> IServiceProvider -> IShellBrowser ->
IShellView -> IFolderView，用 IFolderView::SelectAndPositionItems 移动图标，
读取位置用 IFolderView::Item + GetItemPosition。接口的 vtable 槽位按
Windows SDK 10.0.16299.0 头文件核对。
"""

import ctypes
import threading
import time
from ctypes import wintypes

COOLDOWN_S = 2.0      # 同一个图标被踢后的冷却秒数
KICK_RADIUS = 120     # 图标中心与小白中心的距离阈值（px）
KICK_PUSH = 34        # 每次踢飞的位移（px）

_lv = None            # 缓存的桌面 SysListView32 句柄
_cooldown = {}        # 图标索引 -> 上次被踢的 monotonic 时间

# COM 对象是公寓绑定的：每个线程要用自己的 IFolderView/缓存。
_tls = threading.local()


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid(d1, d2, d3, b):
    g = GUID()
    g.Data1 = d1
    g.Data2 = d2
    g.Data3 = d3
    g.Data4 = (ctypes.c_ubyte * 8)(*b)
    return g


CLSID_ShellWindows = _guid(0x9BA05972, 0xF6A8, 0x11CF,
                           (0xA4, 0x42, 0x00, 0xA0, 0xC9, 0x0A, 0x8F, 0x39))
IID_IShellWindows = _guid(0x85CB6900, 0x4D95, 0x11CF,
                          (0x96, 0x0C, 0x00, 0x80, 0xC7, 0xF4, 0xEE, 0x85))
IID_IServiceProvider = _guid(0x6D5140C1, 0x7436, 0x11CE,
                             (0x80, 0x34, 0x00, 0xAA, 0x00, 0x60, 0x09, 0xFA))
IID_IShellBrowser = _guid(0x000214E2, 0x0000, 0x0000,
                          (0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46))
IID_IFolderView = _guid(0xCDE725B0, 0xCCC9, 0x4519,
                        (0x91, 0x7E, 0x32, 0x5D, 0x72, 0xFA, 0xB4, 0xCE))
IID_IFolderView2 = _guid(0x1AF3A467, 0x214F, 0x4298,
                         (0x90, 0x8E, 0x06, 0xB0, 0x3E, 0x0B, 0x39, 0xF9))
SID_STopLevelBrowser = _guid(0x4C96BE40, 0x915C, 0x11CF,
                             (0x99, 0xD3, 0x00, 0xAA, 0x00, 0x4A, 0xE8, 0x37))

FWF_AUTOARRANGE = 0x1
FWF_SNAPTOGRID = 0x4
SWC_DESKTOP = 0x8
SWFO_NEEDDISPATCH = 0x1
SVGIO_ALLVIEW = 0x2
SVSI_POSITIONITEM = 0x80
CLSCTX_ALL = 0x17
COINIT_APARTMENTTHREADED = 0x2
VT_EMPTY = 0
VT_I4 = 3


class _BRECORD(ctypes.Structure):
    _fields_ = [("pvRecord", ctypes.c_void_p), ("pRecInfo", ctypes.c_void_p)]


class _VARIANT_BODY(ctypes.Union):
    _fields_ = [
        ("llVal", ctypes.c_longlong),
        ("lVal", ctypes.c_long),
        ("pdispVal", ctypes.c_void_p),
        ("brecord", _BRECORD),
    ]


class VARIANT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("vt", ctypes.c_ushort),
        ("wReserved1", ctypes.c_ushort),
        ("wReserved2", ctypes.c_ushort),
        ("wReserved3", ctypes.c_ushort),
        ("u", _VARIANT_BODY),
    ]


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _user32():
    user32 = ctypes.windll.user32
    user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND,
                                     wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowExW.restype = wintypes.HWND
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    return user32


def find_listview():
    """找到桌面的 SysListView32 窗口（用于把客户区坐标换算成屏幕坐标）。"""
    global _lv
    user32 = _user32()
    if _lv and user32.IsWindow(_lv):
        return _lv
    _lv = None
    tops = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, lparam):
        cls = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(hwnd, cls, 128)
        if cls.value in ("Progman", "WorkerW"):
            tops.append(hwnd)
        return True

    user32.EnumWindows(_cb, 0)
    for top in tops:
        defview = user32.FindWindowExW(top, 0, "SHELLDLL_DefView", None)
        if defview:
            lv = user32.FindWindowExW(defview, 0, "SysListView32", None)
            if lv:
                _lv = lv
                return lv
    return None


def _vtbl(obj, slot, restype, *argtypes):
    """取出 COM 对象 vtable 第 slot 个方法（this 为第一个参数）。"""
    p = ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p))
    vtable_addr = p.contents.value
    funcs = ctypes.cast(vtable_addr,
                        ctypes.POINTER(ctypes.c_void_p * (slot + 1))).contents
    fn_addr = funcs[slot]
    proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    return proto(fn_addr)


def _release(obj):
    if obj:
        try:
            _vtbl(obj, 2, ctypes.c_ulong)(obj)
        except Exception:
            pass


def _qi(obj, iid):
    out = ctypes.c_void_p()
    hr = _vtbl(obj, 0, ctypes.c_long,
               ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))(
        obj, ctypes.byref(iid), ctypes.byref(out))
    if hr < 0 or not out.value:
        return 0
    return out.value


def _free_pidl(pidl):
    if pidl:
        try:
            free = ctypes.windll.ole32.CoTaskMemFree
            free.argtypes = [ctypes.c_void_p]
            free.restype = None
            free(pidl)
        except Exception:
            pass


def _ensure_com():
    if getattr(_tls, "com_ready", False):
        return True
    try:
        hr = ctypes.windll.ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
        if hr < 0:
            return False
    except Exception:
        return False
    _tls.com_ready = True
    return True


def _invalidate_view():
    _tls.view = 0
    _tls.view_fail_at = time.monotonic()


def _acquire_view():
    """拿到桌面文件夹的 IFolderView 指针（本线程独立），失败返回 0。"""
    v = getattr(_tls, "view", 0)
    if v:
        return v
    if not _ensure_com():
        return 0
    if time.monotonic() - getattr(_tls, "view_fail_at", 0.0) < 0.5:
        return 0
    ole32 = ctypes.windll.ole32
    sw = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(ctypes.byref(CLSID_ShellWindows), None,
                                CLSCTX_ALL, ctypes.byref(IID_IShellWindows),
                                ctypes.byref(sw))
    if hr < 0 or not sw.value:
        _tls.view_fail_at = time.monotonic()
        return 0
    disp = ctypes.c_void_p()
    sp = 0
    browser = ctypes.c_void_p()
    view = ctypes.c_void_p()
    fv = 0
    try:
        vt_loc = VARIANT()
        vt_loc.vt = VT_I4
        vt_loc.lVal = 0  # CSIDL_DESKTOP
        vt_empty = VARIANT()
        hwnd = ctypes.c_long(0)
        hr = _vtbl(sw.value, 15, ctypes.c_long,
                   ctypes.POINTER(VARIANT), ctypes.POINTER(VARIANT),
                   ctypes.c_int, ctypes.POINTER(ctypes.c_long),
                   ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))(
            sw.value, ctypes.byref(vt_loc), ctypes.byref(vt_empty),
            SWC_DESKTOP, ctypes.byref(hwnd), SWFO_NEEDDISPATCH,
            ctypes.byref(disp))
        if hr < 0 or not disp.value:
            return 0
        sp = _qi(disp.value, IID_IServiceProvider)
        if not sp:
            return 0
        hr = _vtbl(sp, 3, ctypes.c_long,
                   ctypes.POINTER(GUID), ctypes.POINTER(GUID),
                   ctypes.POINTER(ctypes.c_void_p))(
            sp, ctypes.byref(SID_STopLevelBrowser),
            ctypes.byref(IID_IShellBrowser), ctypes.byref(browser))
        if hr < 0 or not browser.value:
            return 0
        hr = _vtbl(browser.value, 15, ctypes.c_long,
                   ctypes.POINTER(ctypes.c_void_p))(
            browser.value, ctypes.byref(view))
        if hr < 0 or not view.value:
            return 0
        fv = _qi(view.value, IID_IFolderView)
        if fv:
            _tls.view = fv
            return fv
        return 0
    finally:
        _release(sw.value)
        _release(disp.value)
        _release(sp)
        _release(browser.value)
        _release(view.value)


def _fv_count(fv):
    n = ctypes.c_int(0)
    hr = _vtbl(fv, 7, ctypes.c_long, ctypes.c_uint,
               ctypes.POINTER(ctypes.c_int))(fv, SVGIO_ALLVIEW, ctypes.byref(n))
    if hr < 0:
        _invalidate_view()
        return 0
    return n.value


def _fv_item(fv, i):
    pidl = ctypes.c_void_p()
    hr = _vtbl(fv, 6, ctypes.c_long, ctypes.c_int,
               ctypes.POINTER(ctypes.c_void_p))(fv, i, ctypes.byref(pidl))
    if hr < 0 or not pidl.value:
        return 0
    return pidl.value


def _fv_pos(fv, pidl):
    pt = _POINT()
    hr = _vtbl(fv, 11, ctypes.c_long, ctypes.c_void_p,
               ctypes.POINTER(_POINT))(fv, pidl, ctypes.byref(pt))
    if hr < 0:
        _invalidate_view()
        return None
    return pt.x, pt.y


def _fv_move(fv, pidls, pts):
    n = len(pidls)
    if n == 0:
        return True
    arr_pidl = (ctypes.c_void_p * n)(*pidls)
    arr_pt = (_POINT * n)(*pts)
    hr = _vtbl(fv, 16, ctypes.c_long, ctypes.c_uint,
               ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(_POINT),
               ctypes.c_uint)(fv, n, arr_pidl, arr_pt, SVSI_POSITIONITEM)
    if hr < 0:
        _invalidate_view()
        return False
    return True


def _get_spacing(fv):
    """返回桌面图标网格间距 (x, y)，缓存 60 秒。"""
    now = time.monotonic()
    sp = getattr(_tls, "spacing", None)
    if sp and now - getattr(_tls, "spacing_t", 0.0) < 60:
        return sp
    pt = _POINT()
    hr = _vtbl(fv, 12, ctypes.c_long, ctypes.POINTER(_POINT))(
        fv, ctypes.byref(pt))
    if hr < 0:
        _invalidate_view()
        return sp or (152, 204)
    sp = (max(1, pt.x), max(1, pt.y))
    _tls.spacing = sp
    _tls.spacing_t = now
    return sp


def _client_origin():
    """列表视图客户区原点在屏幕上的坐标 (x, y)。"""
    lv = find_listview()
    if not lv:
        return None
    org = wintypes.POINT(0, 0)
    if not _user32().ClientToScreen(lv, ctypes.byref(org)):
        return None
    return org.x, org.y


def _work_area_client():
    """屏幕工作区换算成列表视图客户区坐标 (l, t, r, b)，失败返回 None。"""
    rect = wintypes.RECT()
    if not ctypes.windll.user32.SystemParametersInfoW(
            0x0030, 0, ctypes.byref(rect), 0):   # SPI_GETWORKAREA
        return None
    org = _client_origin()
    if org is None:
        return None
    return (rect.left - org[0], rect.top - org[1],
            rect.right - org[0], rect.bottom - org[1])


def work_area():
    """返回屏幕工作区 (l, t, r, b)（屏幕坐标，已避开任务栏）。"""
    rect = wintypes.RECT()
    if not ctypes.windll.user32.SystemParametersInfoW(
            0x0030, 0, ctypes.byref(rect), 0):   # SPI_GETWORKAREA
        return None
    return rect.left, rect.top, rect.right, rect.bottom


def _fv2(fv):
    """从 IFolderView 拿 IFolderView2（返回指针，用完要 _release）。"""
    out = ctypes.c_void_p()
    hr = _vtbl(fv, 0, ctypes.c_long,
               ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))(
        fv, ctypes.byref(IID_IFolderView2), ctypes.byref(out))
    if hr < 0 or not out.value:
        return 0
    return out.value


def get_folder_flags():
    """读取桌面文件夹视图的标志位（FWF_*），失败返回 None。"""
    fv = _acquire_view()
    if not fv:
        return None
    fv2 = _fv2(fv)
    if not fv2:
        return None
    try:
        flags = ctypes.c_uint(0)
        hr = _vtbl(fv2, 25, ctypes.c_long, ctypes.POINTER(ctypes.c_uint))(
            fv2, ctypes.byref(flags))
        if hr < 0:
            _invalidate_view()
            return None
        return flags.value
    finally:
        _release(fv2)


def set_folder_flags(mask, flags):
    """按 mask 设置桌面文件夹视图标志位，返回是否成功。"""
    fv = _acquire_view()
    if not fv:
        return False
    fv2 = _fv2(fv)
    if not fv2:
        return False
    try:
        hr = _vtbl(fv2, 24, ctypes.c_long, ctypes.c_uint, ctypes.c_uint)(
            fv2, mask, flags)
        if hr < 0:
            _invalidate_view()
            return False
        return True
    finally:
        _release(fv2)


def set_snap_grid(on):
    """开/关桌面图标的“对齐到网格”。返回是否成功。"""
    return set_folder_flags(FWF_SNAPTOGRID, FWF_SNAPTOGRID if on else 0)


def arrange_icons():
    """把桌面图标整理成标准网格（临时开一下自动排列再关掉）。"""
    if not set_folder_flags(FWF_AUTOARRANGE, FWF_AUTOARRANGE):
        return False
    time.sleep(0.35)
    set_folder_flags(FWF_AUTOARRANGE, 0)
    _tls.pos_cache = {}
    return True


def move_icon(index, sx, sy):
    """把图标移动到精确屏幕坐标（左上角）。

    需要先关掉“对齐到网格”才能自由定位；带每个图标的冷却，避免同一帧重复发。
    """
    fv = _acquire_view()
    if not fv:
        return False
    org = _client_origin()
    if org is None:
        return False
    pidl = _fv_item(fv, index)
    if not pidl:
        return False
    try:
        ok = _fv_move(fv, [pidl],
                      [_POINT(int(sx) - org[0], int(sy) - org[1])])
        if ok:
            _tls.pos_cache = {}
        return ok
    finally:
        _free_pidl(pidl)


def icon_count():
    fv = _acquire_view()
    if not fv:
        return 0
    return _fv_count(fv)


def icon_screen_positions(ttl=1.0):
    """返回 {index: (sx, sy)}：所有桌面图标的屏幕坐标（左上角），带缓存。"""
    now = time.monotonic()
    cache = getattr(_tls, "pos_cache", None)
    if cache and now - getattr(_tls, "pos_cache_t", 0.0) < ttl:
        return dict(cache)
    fv = _acquire_view()
    if not fv:
        return {}
    n = _fv_count(fv)
    org = _client_origin()
    if org is None:
        return {}
    out = {}
    for i in range(n):
        pidl = _fv_item(fv, i)
        if not pidl:
            continue
        pos = _fv_pos(fv, pidl)
        if pos is not None:
            out[i] = (pos[0] + org[0], pos[1] + org[1])
        _free_pidl(pidl)
    _tls.pos_cache = out
    _tls.pos_cache_t = now
    return dict(out)


def kick_icon(index, pet_cx, pet_cy, now=None):
    """把第 index 个桌面图标朝远离小白的方向推一格网格。

    pet_cx/pet_cy 是小白的中心（屏幕坐标）。同一图标带冷却，返回是否真的移动。
    """
    if now is None:
        now = time.monotonic()
    last = _cooldown.get(index, 0.0)
    if now - last < COOLDOWN_S:
        return False
    fv = _acquire_view()
    if not fv:
        return False
    pidl = _fv_item(fv, index)
    if not pidl:
        return False
    try:
        pos = _fv_pos(fv, pidl)
        if pos is None:
            return False
        cx, cy = pos
        org = _client_origin()
        if org is None:
            return False
        dx = cx + org[0] + 32 - pet_cx
        dy = cy + org[1] + 32 - pet_cy
        if dx == 0 and dy == 0:
            dx = 1
        px, py = _get_spacing(fv)
        if abs(dx) >= abs(dy):
            nx = cx + (px if dx > 0 else -px)
            ny = cy
        else:
            nx = cx
            ny = cy + (py if dy > 0 else -py)
        wa = _work_area_client()
        if wa:
            l, t, r, b = wa
            if nx < l or nx > r - 48 or ny < t or ny > b - 48:
                return False
        # 网格吸附：推的方向必须超过半格，否则会被吸回原位
        if abs(nx - cx) < px * 0.55 and abs(ny - cy) < py * 0.55:
            return False
        if _fv_move(fv, [pidl], [_POINT(nx, ny)]):
            _cooldown[index] = now
            _tls.pos_cache = {}      # 位置变了，下次重新读
            if len(_cooldown) > 512:
                _cooldown.clear()
            return True
        return False
    finally:
        _free_pidl(pidl)


def kick_icons_near(px, py, pw, ph, now=None):
    """把小白身体附近半径 KICK_RADIUS 内的桌面图标朝外踢开一格。

    px/py/pw/ph 是小白的窗口矩形（屏幕坐标）。返回被踢动的图标数量。
    """
    if now is None:
        now = time.monotonic()
    pcx = px + pw // 2
    pcy = py + ph // 2
    icons = icon_screen_positions()
    if not icons:
        return 0
    kicked = 0
    for index, (sx, sy) in icons.items():
        dx = sx + 32 - pcx
        dy = sy + 32 - pcy
        if dx * dx + dy * dy >= KICK_RADIUS * KICK_RADIUS:
            continue
        if kick_icon(index, pcx, pcy, now):
            kicked += 1
    return kicked


def get_all_positions():
    """返回 {index: (x, y)}（列表视图客户区坐标），供测试备份/恢复。"""
    fv = _acquire_view()
    if not fv:
        return {}
    n = _fv_count(fv)
    out = {}
    for i in range(n):
        pidl = _fv_item(fv, i)
        if not pidl:
            continue
        pos = _fv_pos(fv, pidl)
        if pos is not None:
            out[i] = pos
        _free_pidl(pidl)
    return out


def set_all_positions(mapping):
    """把图标位置恢复为 mapping（get_all_positions 的结果）。"""
    fv = _acquire_view()
    if not fv:
        return False
    pidls = []
    pts = []
    for i, (x, y) in sorted(mapping.items()):
        pidl = _fv_item(fv, i)
        if pidl:
            pidls.append(pidl)
            pts.append(_POINT(int(x), int(y)))
    ok = _fv_move(fv, pidls, pts)
    for pidl in pidls:
        _free_pidl(pidl)
    return ok
