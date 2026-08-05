# -*- coding: utf-8 -*-
"""小白之家：屏幕右下角的主目录快捷方式就是小白的家。

- 小白玩一会儿会弹窗说「我想回家」，确认后让屏幕回到桌面、走回右下角
  的主目录图标并躲起来；
- 双击主目录快捷方式会照常打开主目录文件夹，小白这时从右下角冒出来。
  Windows 监听资源管理器窗口，Linux 监听 Nautilus 窗口。
"""

import tkinter as tk

import pet

# 右下角「家」的区域：主目录快捷方式大概在这里（约 180x180）。
HOME_ZONE_W, HOME_ZONE_H = 180, 180
HOME_MARGIN = 12          # 距屏幕右/下边缘
NAUTILUS_POLL_MS = 300    # 探测新打开的文件管理器窗口的间隔


def show_desktop():
    """让窗口管理器收起所有窗口、回到桌面。
    Windows 用 Shell.Application.MinimizeAll；Linux 用 EWMH。"""
    if pet.IS_WIN:
        try:
            import subprocess
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command",
                 "(New-Object -ComObject Shell.Application).MinimizeAll()"],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return
        except Exception:
            pass
    try:
        from Xlib import X, protocol
        from Xlib.display import Display
        d = Display()
        root_win = d.screen().root
        ev = protocol.event.ClientMessage(
            window=root_win,
            client_type=d.intern_atom("_NET_SHOWING_DESKTOP"),
            data=(32, [1, 0, 0, 0, 0]))
        root_win.send_event(
            ev, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        d.flush()
    except Exception:
        pass


class Home:
    """右下角的主目录快捷方式 = 小白之家。

    不做自己的窗口、不抢双击：靠监听新打开的文件管理器窗口（双击主目录
    的结果）来知道主人敲门了，然后让小白从右下角出来。
    """

    def __init__(self, root, puppy):
        self.root = root
        self.pet = puppy
        puppy.home = self
        self._bubble = None
        self._known_nautilus = {}   # wid -> 是否已显示（mapped）
        self.root.after(NAUTILUS_POLL_MS, self._watch_nautilus)

    # ---------------------------------------------------------- 家的位置
    def zone(self):
        """右下角家的区域 (x0, y0, x1, y1)。"""
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        return (sw - HOME_ZONE_W - HOME_MARGIN, sh - HOME_ZONE_H - HOME_MARGIN,
                sw - HOME_MARGIN, sh - HOME_MARGIN)

    def door_x(self):
        """家的门口（区域中心）屏幕 x：小白回家时停在这里。"""
        x0, y0, x1, y1 = self.zone()
        return (x0 + x1) // 2

    def ground_y(self):
        """地面线（屏幕底部）。"""
        return self.root.winfo_screenheight() - 6

    def appear_xy(self):
        """小白从家出来的位置：右下角。"""
        w, h = self.pet.window_size()
        return (self.root.winfo_screenwidth() - w - 10,
                self.ground_y() - h)

    # ------------------------------------------------------------ 敲门
    def _watch_nautilus(self):
        """监听新打开的文件管理器窗口：双击主目录快捷方式会新建/显示
        一个资源管理器（或 Nautilus）窗口，此时就当作敲门。"""
        try:
            if pet.IS_WIN:
                self._check_new_explorer()
            else:
                self._check_new_nautilus()
        except Exception:
            pass
        try:
            self.root.after(NAUTILUS_POLL_MS, self._watch_nautilus)
        except Exception:
            pass

    def _check_new_explorer(self):
        """Windows：枚举可见的资源管理器窗口（类名 CabinetWClass），
        出现新的就当作敲门。"""
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _cb(hwnd, lparam):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                cls = ctypes.create_unicode_buffer(128)
                user32.GetClassNameW(hwnd, cls, 128)
                if not cls.value.startswith("CabinetWClass"):
                    return True
                if user32.GetWindowTextLengthW(hwnd) > 0:
                    found.append(hwnd)
            except Exception:
                pass
            return True

        user32.EnumWindows(_cb, 0)
        current = set(found)
        for hwnd in current:
            was = self._known_nautilus.get(hwnd)
            if was is None:
                self._known_nautilus[hwnd] = True
                self._on_home_opened()
            elif was is False:
                self._known_nautilus[hwnd] = True
                self._on_home_opened()
        self._known_nautilus = {
            k: v for k, v in self._known_nautilus.items() if k in current}

    def _check_new_nautilus(self):
        d = self.pet._get_xdisp()
        if d is None:
            return
        from Xlib import Xatom
        root_win = d.screen().root
        prop = root_win.get_full_property(
            d.intern_atom("_NET_CLIENT_LIST"), Xatom.WINDOW)
        if prop is None:
            return
        current = set()
        for wid in prop.value:
            w = d.create_resource_object("window", wid)
            try:
                cls = w.get_wm_class() or ("", "")
                if "nautilus" not in " ".join(cls).lower():
                    continue
            except Exception:
                continue
            current.add(wid)
            try:
                mapped = w.get_attributes().map_state == 2   # IsViewable
            except Exception:
                continue
            was = self._known_nautilus.get(wid)
            if was is None:
                self._known_nautilus[wid] = mapped
                if mapped:
                    self._on_home_opened()
            elif was is False and mapped:
                self._known_nautilus[wid] = mapped
                self._on_home_opened()
        # 清掉已销毁的窗口
        self._known_nautilus = {
            k: v for k, v in self._known_nautilus.items() if k in current}

    def _on_home_opened(self):
        """主目录被打开：小白在家的话就从右下角出来。"""
        if getattr(self.pet, "at_home", False):
            self.pet.come_out()

    # ------------------------------------------------------------ 气泡
    def bubble(self, text, ms=1400):
        """右下角家的上方冒出一句话。"""
        try:
            self._hide_bubble()
            b = tk.Toplevel(self.root)
            self._bubble = b
            b.overrideredirect(True)
            b.attributes("-topmost", True)
            b.configure(bg=pet.MENU_BG)
            tk.Label(b, text=text, bg=pet.MENU_BG, fg=pet.MENU_FG,
                     font=pet.BUBBLE_FONT, padx=10, pady=4).pack()
            b.update_idletasks()
            bw, bh = b.winfo_reqwidth(), b.winfo_reqheight()
            x0, y0, x1, y1 = self.zone()
            b.geometry("+%d+%d" % ((x0 + x1) // 2 - bw // 2, y0 - bh - 8))
            b.deiconify()
            self.root.after(ms, self._hide_bubble)
        except Exception:
            pass

    def _hide_bubble(self):
        try:
            if self._bubble is not None and self._bubble.winfo_exists():
                self._bubble.destroy()
        except Exception:
            pass
        self._bubble = None


def install(root, puppy):
    return Home(root, puppy)
