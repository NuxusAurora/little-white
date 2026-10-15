"""Per-user Windows installer. Never launches the pet automatically."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox
import zipfile

if '--verify-package' in sys.argv:
    with zipfile.ZipFile(Path(__file__).parent / 'application.zip') as archive:
        assert archive.testzip() is None
        assert 'Xiaobai.exe' in archive.namelist()
        assert any(name.startswith('_internal/sprites/') for name in archive.namelist())
    sys.exit(0)

target = Path(os.environ['LOCALAPPDATA']) / 'Programs' / 'XiaobaiPet'
def install():
    try:
        with zipfile.ZipFile(Path(__file__).parent / 'application.zip') as archive:
            for entry in archive.infolist():
                path = (target / entry.filename).resolve()
                if not path.is_relative_to(target.resolve()):
                    raise ValueError('Invalid package path')
            target.mkdir(parents=True, exist_ok=True)
            archive.extractall(target)
        # Shell COM only creates the standard per-user Start Menu shortcut.
        exe = str(target / 'Xiaobai.exe').replace("'", "''")
        script = "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([IO.Path]::Combine([Environment]::GetFolderPath('Programs'),'Xiaobai.lnk'));$s.TargetPath='" + exe + "';$s.Save()"
        subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],creationflags=0x08000000,check=True)
        messagebox.showinfo('小白桌宠', '安装完成。请从开始菜单打开 Xiaobai。')
        root.destroy()
    except Exception as error:
        messagebox.showerror('安装失败', str(error))
root=tk.Tk();root.title('安装小白桌宠');root.geometry('460x190');root.resizable(False,False)
tk.Label(root,text='小白桌宠 · Windows',font=('Segoe UI',16)).pack(pady=(22,10))
tk.Label(root,text='安装到当前用户，不需要管理员权限。').pack()
tk.Button(root,text='安装',command=install,width=16).pack(pady=20)
root.mainloop()
