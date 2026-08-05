# 小白桌宠

一只线条小狗（Maltese 小白）桌宠，住在你的桌面右下角。形象直接来自官方表情包贴纸（透明 PNG 抠图），不再是手绘抽象版。

## 启动

`./run.sh`，或者手动运行 `python3 pet.py`（先 `chmod +x *.sh`）。

## 交互

| 操作 | 效果 |
| --- | --- |
| 按住左键拖动 | 拎起小白移动（会摆出被拎着的表情） |
| 单击 / 摸摸 | 播放「30弹 开心」动图 |
| 双击 | 跳跃 + 冒爱心（睡觉时双击会叫醒它） |
| 右键 | 菜单：开心 / 散步 / 睡觉 / 管理动作… / 变大 / 变小 / 退出 |

小白会自己活动：待机时循环播放「散步 → 馋 → 爱你」三组动图，还会散步、挥手、跳跃；要睡觉时先散步至少 20 秒，再连打两个哈欠（「困困」），最后才趴下睡觉。

## 动作管理（可视化）

右键菜单点「管理动作…」（或运行 `./manager.sh`）打开可视化管理器：

- 动作分两类显示：**平常动作**（会自动触发：散步、睡觉、挥手、跳跃、坐下）和**特殊动作**（需要条件：待机贴纸、被摸、被拎、吃蛋糕）；类别可在行内下拉框切换；
- 每个动作一行，带**动画预览**；
- **勾选** = 启用，**取消勾选** = 剔除该动作（待机循环、随机行为、右键菜单都会同步调整）；
- 名称输入框可**给动图起名**（名称会显示在桌宠右键菜单里）；
- **`-` / `+` 按钮**：手动调整该动作的大小（50%~200%），预览和桌宠实时同步；
- **删除按钮**：彻底删除该动作的图片帧（重新运行 `build_all.py` 可恢复）；
- 点「保存」后桌宠约 1.5 秒内自动生效，无需重启。

配置保存在 `pet_config.json`，也可以手动编辑。

## 蛋糕投喂

**右键小白，在菜单里点「拿取蛋糕」** → 在小白的右侧生成一块蛋糕；
点击小白（或直接点蛋糕）→ 蛋糕消失，小白播放「吃蛋糕」→「爱你」；
想再喂就再右键一次。

> 蛋糕生成后停在原地，直接**点击蛋糕本身**或把鼠标移到小白身上点击，
> 都能完成喂食。

「吃蛋糕」动图素材在 `source_videos/eat.mp4`，换新素材直接覆盖同名文件后运行 `build_all.py`。

## 一键重建（抠图 + 尺寸统一）

新增/替换素材后，运行 `python build_all.py`（或 `./build.sh`）一键完成：

1. 静态动作贴纸（`stickers_src/*.png` → walk/drag/wave/jump/sit）
2. 待机 GIF 动图（`stickers_src/like.gif`、`chan.gif`、`aini.gif` → 喜欢/馋/爱你）
3. 视频 AI 抠图（`source_videos/happy.mp4`、`sleep.mp4`、`kunkun.mp4`、`wave.mp4`、`home.mp4`、`kuku.mp4` → 被摸/睡觉/困困/挥手/回家/哭哭，自动去背景）
4. 所有帧尺寸统一化（统一到 380×360，主体大小一致，不再时大时小）

素材目录：

- `stickers_src/` —— GIF 动图（`like.gif`/`chan.gif`/`aini.gif`）和静态贴纸 PNG
- `source_videos/` —— 视频素材（`happy.mp4`/`sleep.mp4`/`kunkun.mp4`/`wave.mp4`/`home.mp4`/`kuku.mp4`）

「回家」流程：
- 小白想回家时先播放 `wave.mp4` 挥手告别，弹出「我想回家」确认框；
- 点「是」后检测桌面：已经在桌面 → 直接播放 `home.mp4` 直线回家；
- 不在桌面 → 再问一次「小白找不到家，先回桌面好不好」，期间继续挥手；
- 两次回答里有一次「否」→ 播放 `kuku.mp4`（哭哭）两遍 → 播放一次
  「困困」→ 睡觉；两次都点「是」→ 回到桌面并直线回家。

## 文件说明

- `pet.py` —— 桌宠主程序（透明置顶窗口、动画、随机行为）
- `make_video_sprites.py` —— 把你提供的表情视频（被摸了/睡觉）AI 抠图拆帧成动画
- `make_animated_sprites.py` —— 从 `stickers_src/` 里的微信动图 GIF 拆帧生成待机/被摸动画
- `make_sticker_sprites.py` —— 从 `stickers_src/` 里的官方贴纸 PNG 生成全部动画帧（抠图、构图、尺寸统一）
- `pet_editor.py` —— 可视化动作管理器（启用/禁用、命名、预览）
- `pet_config.json` —— 动作配置（哪些启用、叫什么名字）
- `build_all.py` / `normalize_sprites.py` —— 一键重建：抠图 + 尺寸统一
- `repair_sprites.py` —— 修复开口线条抠图的小工具：透明像素的 5x5 邻域内
  有 >=14 个有色像素就补成白色，并**反复执行直到补白为 0 才停止**（直接
  作用于图片文件/目录；脚本开头会自动切到 dogs 环境，不需要手动
  `conda activate`）
- `unify_white.py` —— 统一白色的小工具：把所有近白（RGB>=180 且通道色差
  <=30、alpha>=96）的可见像素统一成纯白 (255,255,255) 且 alpha=255，
  亮度完全一致；黑色轮廓/粉色爱心/棕色蛋糕等彩色细节不受影响
- `stickers_src/` —— 表情包素材（17弹 like/chan/aini、30弹 happy，个人使用）
- `sprites/` —— 生成的透明 PNG 动画帧，**每个动作一个文件夹**
  （`sprites/walk/`、`sprites/chan/`、`sprites/aini/`、`sprites/eat/`、
  `sprites/sleep/`、`sprites/sleepb/`、`sprites/kunkun/`、`sprites/wave/`、
  `sprites/home/`、`sprites/kuku/`…）
- `run.sh` —— 一键启动

## 修复开口线条抠图

线条小狗的轮廓不是闭合线框，白色 flood-fill 抠图会从开口漏进身体内部。
现在视频动作（wave/home）已改用 rembg AI 抠图，不会有这个问题；如果
其他素材还有内部被误删的情况，可以直接跑修复工具：

```bash
python repair_sprites.py sprites/xxx/            # 修复整个动作的文件夹
python repair_sprites.py --dry sprites/xxx/      # 先看会补白多少，不写文件
```
工具会自动三步走：
1. 局部密度规则（5x5 邻域 >=14 个有色像素）反复执行到收敛；
2. 形态学闭运算封住 1~2px 的细缝；
3. 从图片边缘 flood-fill，把所有被可见像素（alpha >= 96，桌宠显示阈值）
   完全包围的透明/半透明区域补成白色——包括 alpha 41~95 的半透明小点，
   洞多大都能补上，且不影响外圈抗锯齿边缘。
`--max-pass` 可设密度规则轮数上限防死循环。

## 统一白色

抠图/修复后身体内部的白色可能深浅不一（240~255 混在一起），跑一遍统一
白色即可：

```bash
python unify_white.py sprites/                # 一次统一全部动作
python unify_white.py --dry sprites/eat/      # 先看统计，不写文件
python unify_white.py --white-min 200 a.png   # 调高/调低“近白”判定
```

## 桌面环境

小白在 Linux X11 桌面上运行（带合成器效果最佳，如 GNOME / KDE /
XFCE 开启合成）。透明效果直接用 X11 的 SHAPE 扩展把 alpha 通道切成窗口形状实现，
不再依赖 Tk 的 `-transparentcolor`（那是 Windows 专属属性，Linux 上会失效导致露出
品红底色）；透明区域自动点击穿透，X11 和无合成器的环境、以及 XWayland 下都能用。

依赖：

```bash
sudo apt install python3 python3-tk python3-pil python3-numpy
pip install opencv-python rembg
```

- **Linux 鼠标交互**（拖拽、右键菜单）依赖 `pip install python-xlib`；
  装了之后小白也能从桌沿「坠落」；
- Wayland 会话下建议通过 XWayland 运行（大多数发行版默认开启）；
- 快捷脚本：`./run.sh`（启动）、`./build.sh`（重建动画）、`./manager.sh`（动作管理）、
  `./cake.sh`（生成蛋糕）。

## 小技巧

- 觉得太大/太小：右键菜单里「变大一点 / 变小一点」随时调整。
- 想换表情或姿势：把新的贴纸 PNG 放进 `stickers_src/`，改 `make_sticker_sprites.py` 里对应的贴纸名，运行 `python make_sticker_sprites.py` 重新生成即可。
- 退出：右键菜单选「退出」。

> 素材仅限个人自用，请勿二次传播或商用。
