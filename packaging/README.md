# 小白安装包

Windows运行源码取main的 `7ca66610d09d10c9cee637432d91b895bc310ada`，Linux取本地已存在的origin/linux `5bfd89fa03e494a78b580c0cd314ef38ffba8a69`。两平台分别从Git归档读取运行源码、配置和sprites，不把Windows实现混入Linux包；不包含原始视频、日志、锁或旧压缩包。

- `windows_entry.py`：PyInstaller应用启动适配；资源初始化到用户LocalAppData/XiaobaiPet/data，配置不写安装目录，动作管理器与重启调用冻结应用。
- `windows_setup.py`：Windows当前用户安装器，把应用解包到LocalAppData/Programs/XiaobaiPet并创建开始菜单快捷方式，不自动启动。`--verify-package`只检查内嵌ZIP及必需文件，不安装。
- `build_linux_deb.py <含Xiaobai-Linux.zip的独立目录>`：在Linux用dpkg-deb生成Debian/Ubuntu包；依赖系统Python/Tkinter/Pillow，安装后用应用菜单或xiaobai启动，需要X11桌面。运行文件和默认素材位于/usr/lib，用户配置在XDG_DATA_HOME/xiaobai-pet；不在服务器安装该桌宠。

Windows构建使用Python3.14、PyInstaller6.22.3、Pillow12.3.0的独立虚拟环境。应用采用onedir/windowed，加入sprites与pet_config.json，显式包含pet_editor/cake/home/desktop_icons；将输出目录内容压缩为application.zip，再用PyInstaller onefile/windowed打包windows_setup.py，包含application.zip。所有输出指定独立dist/work/spec目录。

候选位于installer-artifacts/20261014。Windows冻结程序在隔离用户目录自动关闭启动检查通过；Linux语法和deb结构验证通过，真实X11桌面安装/交互尚未验收。安装器未签名；本次未覆盖运行中的桌宠或自动安装。

发布渠道：`https://nuxusaurora.cn/downloads/xiaobai/20261014/Xiaobai-Windows-Setup.exe`（46704007字节，SHA256 b7538ea9679b5baa656faab7ed2dd615930d7e5cab2918265a918e4061888cc3）及同目录`Xiaobai-Linux.deb`（10477894字节，SHA256 42b5685e439f485e1d0f483aa1a2fb3a4fe3130676982a83246b71efe9d58ad5）。Linux依赖已包含python3-xlib。网站工具页已替换原源码ZIP入口；服务器安装包前端/账号不相互依赖。
