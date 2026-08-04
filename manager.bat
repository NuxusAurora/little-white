@echo off
cd /d "%~dp0"
set "PYW=%LocalAppData%\Python\pythoncore-3.14-64\pythonw.exe"
if exist "%PYW%" (
    start "" "%PYW%" pet_editor.py
) else (
    start "" python pet_editor.py
)
