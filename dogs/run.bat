@echo off
cd /d "%~dp0"
set "PYW=%LocalAppData%\Python\pythoncore-3.14-64\pythonw.exe"
if exist "%PYW%" (
    start "" "%PYW%" pet.py
) else (
    where pythonw >nul 2>nul
    if %errorlevel%==0 (
        start "" pythonw pet.py
    ) else (
        start "" python pet.py
    )
)
