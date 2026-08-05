# -*- coding: utf-8 -*-
"""cmd 命令入口：在鼠标指针处生成一块蛋糕。

用法：在项目目录的 cmd 里输入 `cake`（或 `python feed.py`）。
"""

import json
import os


def _cursor_pos():
    """鼠标位置：用隐藏 Tk 窗口查询 X11 指针。"""
    import tkinter as tk
    r = tk.Tk()
    r.withdraw()
    try:
        return r.winfo_pointerxy()
    finally:
        r.destroy()


px, py = _cursor_pos()

req_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "_cake_request.json")
with open(req_path, "w", encoding="utf-8") as f:
    json.dump({"x": int(px), "y": int(py)}, f)

print("蛋糕已生成在鼠标位置！把鼠标移到小白身上，点击它喂食吧。")
