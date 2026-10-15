"""Build the Linux branch as a Debian/Ubuntu package without touching the host."""
from pathlib import Path
import ast
import json
import shutil
import subprocess
import sys
import zipfile

base=Path(sys.argv[1]).resolve();source=base/'linux-source';source.mkdir()
with zipfile.ZipFile(base/'Xiaobai-Linux.zip') as archive: archive.extractall(source)
for path in source.glob('*.py'):ast.parse(path.read_text(encoding='utf-8-sig'))
root=base/'deb'; app=root/'usr/lib/xiaobai-pet';app.mkdir(parents=True)
for name in ('pet.py','home.py','cake.py','feed.py','pet_editor.py','pet_config.json','sprites'):
 p=source/name
 if p.is_dir():shutil.copytree(p,app/name)
 else:shutil.copyfile(p,app/name)
launcher=root/'usr/bin/xiaobai';launcher.parent.mkdir(parents=True)
launcher.write_text('''#!/usr/bin/python3
from pathlib import Path
import os,shutil,sys
source=Path('/usr/lib/xiaobai-pet')
data=Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share'))))/'xiaobai-pet'
data.mkdir(parents=True,exist_ok=True)
for file in source.iterdir():
 target=data/file.name
 if file.is_dir():
  if not target.exists():shutil.copytree(file,target)
 elif file.suffix=='.py' or not target.exists():shutil.copyfile(file,target)
os.chdir(data)
os.execv(sys.executable,[sys.executable,str(data/'pet.py'),*sys.argv[1:]])
'''.replace("str(Path.home()/'.local/share'))))","str(Path.home()/'.local/share')))") )
launcher.chmod(0o755);ast.parse(launcher.read_text())
desktop=root/'usr/share/applications/xiaobai.desktop';desktop.parent.mkdir(parents=True)
desktop.write_text('[Desktop Entry]\nType=Application\nName=小白桌宠\nName[en]=Xiaobai Pet\nExec=xiaobai\nTerminal=false\nCategories=Game;\n')
control=root/'DEBIAN/control';control.parent.mkdir()
control.write_text('Package: xiaobai-pet\nVersion: 1.0.0\nArchitecture: all\nMaintainer: NuxusAurora\nDepends: python3 (>= 3.10), python3-tk, python3-pil, python3-pil.imagetk, python3-xlib, libx11-6, libxext6\nSection: games\nPriority: optional\nDescription: Xiaobai desktop pet for X11 desktops\n Includes animation assets and a per-user data launcher.\n')
for path in root.rglob('*'):
 if path.is_dir():path.chmod(0o755)
 elif path!=launcher:path.chmod(0o644)
subprocess.run(['dpkg-deb','--root-owner-group','--build',str(root),str(base/'Xiaobai-Linux.deb')],check=True)
print('Linux .deb built; real X11 GUI acceptance still required')
