# 小白桌宠

一只线条小狗（Maltese 小白）桌宠，住在你的桌面右下角。形象直接来自官方表情包贴纸（透明 PNG 抠图），不再是手绘抽象版。

## 启动

- 双击 `run.bat`，或者手动运行 `python pet.py`。
- **Linux**：`./run.sh`，或者手动运行 `python3 pet.py`（先 `chmod +x *.sh`）。

## 交互

| 操作 | 效果 |
| --- | --- |
| 按住左键拖动 | 拎起小白移动（会摆出被拎着的表情） |
| 单击 / 摸摸 | 播放「30弹 开心」动图 |
| 双击 | 跳跃 + 冒爱心（睡觉时双击会叫醒它） |
| 右键 | 菜单：开心 / 散步 / 睡觉 / 管理动作… / 变大 / 变小 / 退出 |

小白会自己活动：待机时循环播放「17弹：喜欢 → 馋 → 爱你」三组动图，还会散步、挥手、跳跃；要睡觉时先散步至少 20 秒，再连打两个哈欠（「困困」），最后才趴下睡觉。

## 动作管理（可视化）

右键菜单点「管理动作…」（或双击 `manager.bat`）打开可视化管理器：

- 动作分两类显示：**平常动作**（会自动触发：散步、睡觉、挥手、跳跃、坐下）和**特殊动作**（需要条件：待机贴纸、被摸、被拎、吃蛋糕）；类别可在行内下拉框切换；
- 每个动作一行，带**动画预览**；
- **勾选** = 启用，**取消勾选** = 剔除该动作（待机循环、随机行为、右键菜单都会同步调整）；
- 名称输入框可**给动图起名**（名称会显示在桌宠右键菜单里）；
- **`-` / `+` 按钮**：手动调整该动作的大小（50%~200%），预览和桌宠实时同步；
- **删除按钮**：彻底删除该动作的图片帧（重新运行 `build_all.py` 可恢复）；
- 点「保存」后桌宠约 1.5 秒内自动生效，无需重启。

配置保存在 `pet_config.json`，也可以手动编辑。

## 蛋糕投喂

没有桌子了，改用命令生成蛋糕：

- 在项目目录的 cmd 里输入 **`cake`**（或 `python feed.py`）→ 在鼠标指针位置生成一块蛋糕；
- 把鼠标移到小白身上，**点击小白** → 蛋糕消失，小白播放「吃蛋糕」→「爱你」；
- 想再喂就再输入一次 `cake`。

> Linux 上蛋糕不跟随鼠标（点击穿透需要 Win32 API），生成后蛋糕停在原地，
> 直接**点击蛋糕本身**或把鼠标移到小白身上点击，都能完成喂食。

「吃蛋糕」动图素材在 `source_videos/eat.mp4`，换新素材直接覆盖同名文件后运行 `build_all.py`。

## 一键重建（抠图 + 尺寸统一）

新增/替换素材后，运行 `python build_all.py`（或双击 `build.bat`）一键完成：

1. 静态动作贴纸（`stickers_src/*.png` → walk/drag/wave/jump/sit）
2. 待机 GIF 动图（`stickers_src/like.gif`、`chan.gif`、`aini.gif` → 喜欢/馋/爱你）
3. 视频 AI 抠图（`source_videos/happy.mp4`、`sleep.mp4`、`kunkun.mp4` → 被摸/睡觉/困困，自动去背景）
4. 所有帧尺寸统一化（统一到 380×360，主体大小一致，不再时大时小）

素材目录：

- `stickers_src/` —— GIF 动图（`like.gif`/`chan.gif`/`aini.gif`）和静态贴纸 PNG
- `source_videos/` —— 视频素材（`happy.mp4`/`sleep.mp4`/`kunkun.mp4`）

## 文件说明

- `pet.py` —— 桌宠主程序（透明置顶窗口、动画、随机行为）
- `make_video_sprites.py` —— 把你提供的表情视频（被摸了/睡觉）AI 抠图拆帧成动画
- `make_animated_sprites.py` —— 从 `stickers_src/` 里的微信动图 GIF 拆帧生成待机/被摸动画
- `make_sticker_sprites.py` —— 从 `stickers_src/` 里的官方贴纸 PNG 生成全部动画帧（抠图、构图、尺寸统一）
- `pet_editor.py` —— 可视化动作管理器（启用/禁用、命名、预览）
- `pet_config.json` —— 动作配置（哪些启用、叫什么名字）
- `build_all.py` / `normalize_sprites.py` —— 一键重建：抠图 + 尺寸统一
- `stickers_src/` —— 表情包素材（17弹 like/chan/aini、30弹 happy，个人使用）
- `sprites/` —— 生成的透明 PNG 动画帧
- `run.bat` —— 一键启动（无控制台窗口）

## Linux 支持

小白现在可以在 Linux 桌面上运行（X11 桌面，带合成器效果最佳，如 GNOME / KDE /
XFCE 开启合成）。透明效果直接用 X11 的 SHAPE 扩展把 alpha 通道切成窗口形状实现，
不再依赖 Tk 的 `-transparentcolor`（那是 Windows 专属属性，Linux 上会失效导致露出
品红底色）；透明区域自动点击穿透，X11 和无合成器的环境、以及 XWayland 下都能用。

依赖：

```bash
sudo apt install python3 python3-tk python3-pil python3-numpy
pip install opencv-python rembg
```

- 想让小白从桌沿「坠落」：再装 `pip install python-xlib`（可选，不装则始终站在地面上）；
- Wayland 会话下建议通过 XWayland 运行（大多数发行版默认开启）；
- 快捷脚本：`./run.sh`（启动）、`./build.sh`（重建动画）、`./manager.sh`（动作管理）、
  `./cake.sh`（生成蛋糕）。

## 小技巧

- 觉得太大/太小：右键菜单里「变大一点 / 变小一点」随时调整。
- 想换表情或姿势：把新的贴纸 PNG 放进 `stickers_src/`，改 `make_sticker_sprites.py` 里对应的贴纸名，运行 `python make_sticker_sprites.py` 重新生成即可。
- 退出：右键菜单选「退出」。

> 素材仅限个人自用，请勿二次传播或商用。
