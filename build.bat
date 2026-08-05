@echo off
cd /d "%~dp0"
set "PY=%LocalAppData%\Python\pythoncore-3.14-64\python.exe"
if exist "%PY%" (
    "%PY%" build_all.py
) else (
    python build_all.py
)
echo.
pause
