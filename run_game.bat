@echo off
setlocal
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
set SURAKARTA_AI_DEPTH=5
set SURAKARTA_AI_MS=5000
set SURAKARTA_TOTAL_TIME_MS=900000
set SURAKARTA_EVAL_PROFILE=paper_2022
set SURAKARTA_PAPER_OPENING_ORDERING=1
set SURAKARTA_DEFENSIVE_EXTENSION_LIMIT=0
set SURAKARTA_REPLY_CAPTURE_PENALTY_SCALE=1.0
set SURAKARTA_OPENING_BOOK=
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -B main.py
) else (
    python -B main.py
)
if errorlevel 1 pause
endlocal
