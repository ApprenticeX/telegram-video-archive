@echo off
title Local Telegram Archiver - Web UI
echo ====================================================
echo Starting Local YouTube to Telegram Archiver Web UI...
echo (Using dedicated virtual environment .venv)
echo ====================================================
echo.
start http://localhost:8000
.\.venv\Scripts\python.exe server.py
pause
