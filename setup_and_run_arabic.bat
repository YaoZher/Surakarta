@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3.12 -m venv .venv
    if errorlevel 1 py -3 -m venv .venv
    if not exist ".venv\Scripts\python.exe" python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
set "SURAKARTA_LANGUAGE=ar"
call run_game.bat
exit /b %errorlevel%
:failed
echo Setup failed. Install Python 3.12, check the network, and try again.
pause
exit /b 1
