# -*- coding: utf-8 -*-
"""小白桌宠 · 动作管理器

可视化编辑 pet_config.json：
  - 勾选/取消 = 启用/剔除某个动作
  - 名称输入 = 给该动图命名（会显示在桌宠右键菜单里）
  - 每行有动画预览
桌宠运行时会自动读取保存后的配置（约 1.5 秒内生效）。
"""

import glob
import json
import os

import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
from PIL import Image, ImageTk

import pet

HERE = os.path.dirname(os.path.abspath(__file__))
SPR = os.path.join(HERE, "sprites")

ORDER = ["chan", "aini", "happy", "sleep", "walk", "drag",
         "dance", "wave", "jump", "sit", "eat", "kunkun", "home",
         "kuku"]


def group_files(g):
    files = sorted(glob.glob(os.path.join(SPR, g, "*.png")))
    if not files:   # 兼容旧的平铺存放
        files = sorted(glob.glob(os.path.join(SPR, g + "_*.png")))
    if not files:
        single = os.path.join(SPR, g + ".png")
        if os.path.exists(single):
            files = [single]
    return files


class Editor:
    def __init__(self, root):
        self.root = root
        self.cfg = pet.load_config()
        self.order = [g for g in ORDER if g in self.cfg["groups"]]
        self.vars = {}
        self.checks = {}
        self.entries = {}
        self.preview_labels = {}
        self.photos = {}
        self.pidx = {}
        self.preview_rows = []
        self.scale_labels = {}
        self.scale_btns = {}
        self.del_btns = {}
        self.frame_labels = {}
        self.row_frames = {}
        self.category_boxes = {}

        root.title("小白桌宠 · 动作管理")
        root.resizable(False, False)

        header = tk.Frame(root)
        header.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(header, text="勾选启用 / 取消剔除，改名后点「保存」",
                 font=("Microsoft YaHei UI", 10)).pack(anchor="w")
        tk.Label(header, text="所有名字都会显示在桌宠右键菜单里，可直接点击触发",
                 fg="#777", font=("Microsoft YaHei UI", 9)).pack(anchor="w")

        body = tk.Frame(root)
        body.pack(fill="both", padx=12, pady=6, expand=True)
        canvas = tk.Canvas(body, highlightthickness=0, width=580, height=540)
        scroll = tk.Scrollbar(body, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        self.inner = inner
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
        canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))
        self.build_rows(inner)

        foot = tk.Frame(root)
        foot.pack(fill="x", padx=12, pady=(4, 10))
        tk.Button(foot, text="保存", width=10, command=self.save).pack(side="left")
        tk.Button(foot, text="恢复默认", width=10, command=self.reset).pack(side="left", padx=8)
        tk.Button(foot, text="重启小白", width=10, command=self.restart_pet).pack(side="left", padx=8)
        self.status = tk.Label(foot, text="", fg="#2a7f2a",
                               font=("Microsoft YaHei UI", 9))
        self.status.pack(side="left", padx=10)

        self.load_previews()
        self.tick_previews()

    # ------------------------------------------------------------- widgets
    def build_rows(self, body):
        normal = [g for g in self.order
                  if self.cfg["groups"][g].get("category", "special") == "normal"]
        special = [g for g in self.order
                   if self.cfg["groups"][g].get("category", "special") != "normal"]
        for title, groups in (("平常动作（会自动触发）", normal),
                              ("特殊动作（需要条件触发）", special)):
            if groups:
                tk.Label(body, text=title, font=("Microsoft YaHei UI", 9, "bold"),
                         fg="#666").pack(fill="x", pady=(8, 2))
            for g in groups:
                self.build_row(body, g)

    def build_row(self, body, g):
            row = tk.Frame(body)
            row.pack(fill="x", pady=2)
            self.row_frames[g] = row
            var = tk.BooleanVar(value=self.cfg["groups"][g]["enabled"])
            self.vars[g] = var
            check = tk.Checkbutton(row, variable=var, font=("Microsoft YaHei UI", 10))
            check.pack(side="left", padx=(0, 6))
            self.checks[g] = check
            preview = tk.Label(row, bg="#f2f2f4", relief="groove", bd=1)
            preview.pack(side="left", padx=6)
            self.preview_labels[g] = preview
            entry = tk.Entry(row, width=14, font=("Microsoft YaHei UI", 10))
            entry.insert(0, self.cfg["groups"][g]["name"])
            entry.pack(side="left", padx=10)
            self.entries[g] = entry
            n = len(group_files(g))
            flabel = tk.Label(row, text="%d 帧" % n, fg="#888",
                              font=("Microsoft YaHei UI", 9))
            flabel.pack(side="left", padx=6)
            self.frame_labels[g] = flabel
            # size adjust
            pct = int(round(self.cfg["groups"][g].get("scale", 1.0) * 100))
            self.scale_labels[g] = tk.Label(row, text="%d%%" % pct, width=5,
                                            fg="#444", font=("Microsoft YaHei UI", 9))
            self.scale_labels[g].pack(side="left", padx=4)
            minus = tk.Button(row, text="-", width=3, command=lambda g=g: self.bump_scale(g, 0.9))
            plus = tk.Button(row, text="+", width=3, command=lambda g=g: self.bump_scale(g, 1.1))
            minus.pack(side="left", padx=1)
            plus.pack(side="left", padx=1)
            self.scale_btns[g] = (minus, plus)
            # delete
            dbtn = tk.Button(row, text="删除", width=5, fg="#a33",
                             command=lambda g=g: self.delete_group(g))
            dbtn.pack(side="left", padx=6)
            self.del_btns[g] = dbtn
            # category dropdown
            cat = ttk.Combobox(row, values=["平常", "特殊"], width=4, state="readonly")
            cat.set("平常" if self.cfg["groups"][g].get("category", "special")
                    == "normal" else "特殊")
            cat.bind("<<ComboboxSelected>>",
                     lambda e, g=g, c=cat: self.change_category(g, c))
            cat.pack(side="left", padx=4)
            self.category_boxes[g] = cat
            self.preview_rows.append((g, var))

    def change_category(self, g, combobox):
        self.cfg["groups"][g]["category"] = \
            "normal" if combobox.get() == "平常" else "special"
        pet.save_config(self.cfg)
        self.rebuild_rows()
        self.status.config(text="「%s」已移到%s，桌宠会自动生效"
                           % (self.cfg["groups"][g]["name"], combobox.get()))

    def rebuild_rows(self):
        for w in list(self.row_frames.values()):
            w.destroy()
        for d in (self.vars, self.checks, self.entries, self.preview_labels,
                  self.scale_labels, self.scale_btns, self.del_btns,
                  self.frame_labels, self.row_frames, self.category_boxes,
                  self.photos, self.pidx):
            d.clear()
        self.build_rows(self.inner)
        self.load_previews()

    # ------------------------------------------------------------- previews
    def load_previews(self):
        for g in self.order:
            self.reload_preview(g)

    def reload_preview(self, g):
        scale = self.cfg["groups"][g].get("scale", 1.0)
        photos = []
        for f in group_files(g):
            try:
                im = Image.open(f).convert("RGBA")
                if scale != 1.0:
                    nw = max(1, int(round(im.width * scale)))
                    nh = max(1, int(round(im.height * scale)))
                    im = im.resize((nw, nh), Image.LANCZOS)
                im.thumbnail((120, 120), Image.LANCZOS)
                canvas = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
                canvas.alpha_composite(
                    im, ((120 - im.width) // 2, (120 - im.height) // 2))
                photos.append(ImageTk.PhotoImage(canvas))
            except Exception:
                pass
        self.photos[g] = photos
        self.pidx[g] = 0

    def tick_previews(self):
        for g in list(self.photos):
            photos = self.photos[g]
            if photos:
                label = self.preview_labels[g]
                label.configure(image=photos[self.pidx[g] % len(photos)])
                self.pidx[g] += 1
        self.root.after(120, self.tick_previews)

    # ------------------------------------------------------------- actions
    def bump_scale(self, g, factor):
        cur = self.cfg["groups"][g].get("scale", 1.0)
        new = max(0.5, min(2.0, round(cur * factor, 2)))
        self.cfg["groups"][g]["scale"] = new
        pet.save_config(self.cfg)
        self.scale_labels[g].configure(text="%d%%" % int(round(new * 100)))
        self.reload_preview(g)
        self.status.config(text="「%s」大小已调整，桌宠会自动生效"
                           % self.cfg["groups"][g]["name"])

    def delete_group(self, g):
        name = self.cfg["groups"][g].get("name", g)
        if not messagebox.askyesno(
                "删除动作",
                "确定彻底删除「%s」吗？\n会删除图片帧和配置。\n"
                "如需恢复：点「恢复默认」后重新运行 build_all.py。" % name):
            return
        for f in group_files(g):
            try:
                os.remove(f)
            except OSError:
                pass
        self.cfg["groups"].pop(g, None)
        pet.save_config(self.cfg)
        # remove the row from the manager entirely
        self.row_frames[g].destroy()
        for d in (self.vars, self.checks, self.entries, self.preview_labels,
                  self.scale_labels, self.scale_btns, self.del_btns,
                  self.frame_labels, self.row_frames, self.category_boxes):
            d.pop(g, None)
        self.photos.pop(g, None)
        self.pidx.pop(g, None)
        if g in self.order:
            self.order.remove(g)
        self.status.config(text="已彻底删除「%s」，桌宠会自动生效" % name)

    def save(self):
        for g in self.order:
            name = self.entries[g].get().strip()
            self.cfg["groups"][g]["enabled"] = self.vars[g].get()
            self.cfg["groups"][g]["name"] = name or pet.DEFAULT_CONFIG["groups"][g]["name"]
        pet.save_config(self.cfg)
        self.status.config(text="已保存 ✓ 桌宠会自动生效")
        self.root.after(2500, lambda: self.status.config(text=""))

    def reset(self):
        self.cfg = json.loads(json.dumps(pet.DEFAULT_CONFIG))
        pet.save_config(self.cfg)
        self.order = [g for g in ORDER if g in self.cfg["groups"]]
        self.rebuild_rows()
        self.status.config(text="已恢复默认 ✓")

    def restart_pet(self):
        import subprocess
        import sys as _sys
        # 重新启动小白（pet.py 的单实例锁会自动终止旧实例）
        subprocess.Popen([_sys.executable, os.path.join(HERE, "pet.py")])
        self.status.config(text="已重启小白 ✓")


def main():
    root = tk.Tk()
    Editor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
