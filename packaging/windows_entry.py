"""Frozen launcher: keep editable pet data in the user's profile."""
import os
from pathlib import Path
import shutil
import sys

bundle = Path(__file__).resolve().parent
data = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'XiaobaiPet' / 'data'
data.mkdir(parents=True, exist_ok=True)
if not (data / 'sprites').exists():
    shutil.copytree(bundle / 'sprites', data / 'sprites')
if not (data / 'pet_config.json').exists():
    shutil.copyfile(bundle / 'pet_config.json', data / 'pet_config.json')
import pet
pet.HERE = str(data)
pet.SPR = str(data / 'sprites')
pet.LOCK_FILE = str(data / '.pet.lock')
pet.CONFIG_PATH = str(data / 'pet_config.json')
def open_editor(self):
    import subprocess
    subprocess.Popen([sys.executable, '--editor'])
def restart(self):
    self._cleanup_icons()
    self.root.destroy()
    import subprocess
    subprocess.Popen([sys.executable])
pet.Pet.open_editor = open_editor
pet.Pet.restart_pet = restart
if '--editor' in sys.argv:
    import pet_editor
    pet_editor.HERE = str(data)
    pet_editor.SPR = str(data / 'sprites')
    pet_editor.Editor.restart_pet = lambda self: __import__('subprocess').Popen([sys.executable])
    pet_editor.main()
else:
    pet.main(auto_close_ms=1500 if '--package-smoke' in sys.argv else None, test_mode='--package-smoke' in sys.argv)
