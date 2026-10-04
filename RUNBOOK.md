# 小白桌宠运行说明

## 启动

Windows 双击 `run.bat`。脚本优先使用 `%LOCALAPPDATA%\Python\pythoncore-3.14-64\pythonw.exe`，不存在时使用 PATH 中的 Python。

本机已核验的 PowerShell 启动命令：

```powershell
cd D:\Code\pythonhouse\dogs
& "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe" pet.py
```

主程序依赖 Python、Tkinter 和 Pillow；本机上述 Python 为 3.14，Pillow 为 12.3.0。PATH 中的默认 Python 缺少 Pillow，应使用上面的解释器。Linux 启动方式见 README，本次未在 Linux 实机验证。

## 入口和资源

- `pet.py`：桌宠主程序、动作播放、导航和右键菜单。
- `desktop_icons.py`：Windows 桌面 COM 接口、位置查询与移动；不反向依赖桌宠。
- `pet_editor.py` / `manager.bat`：动作管理器。
- `cake.py`、`feed.py`、`cake.bat`：投喂；`home.py`：小屋与回家流程。
- `pet_config.json`：动作开关、名称、大小与分类。
- `sprites/<动作>/`：当前动画 PNG；`sprites/heart/heart.png`：爱心叠加素材。
- `source_videos/`、`stickers_src/`：原始素材；`build_all.py`、`build.bat`：重建入口，会改写素材。本次核验没有重建。
- `.pet.lock`、`_pet_dbg.log`、`_pet_test.log`、`__pycache__/`：本地运行产物，不提交。

## 踢图标模式

每次启动默认关闭，在右键菜单勾选「踢图标模式」后开启。关闭后不再选择新图标，已有搬运继续完成。Windows 自动排列开启时不启动踢动；网格关闭失败时不启动飞行。退出和重启会停止工作线程，尝试归还当前飞行、待捡或搬运的图标，再恢复曾关闭的网格设置。

## 验证

在项目根目录执行：

```powershell
& "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe" -B -m unittest test_regressions -v
```

回归覆盖 Windows VARIANT 布局、禁用踢动、测试模式隔离、网格关闭失败、网格恢复重试、退出时线程停止与图标恢复、必需爱心素材。

运行验收：启动桌宠，确认右键「踢图标模式」未勾选；拖动小狗、打开动作管理器查看预览，再退出。测试 GUI 时应使用独立副本，避免单实例逻辑终止用户现有进程及写入配置或日志。本次真实桌面接口仅查询位置，未移动图标。
