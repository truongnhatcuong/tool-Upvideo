@echo off
title TikTok Link Extractor - Excel Export
cd /d "%~dp0"
python gui.py
if errorlevel 1 (
    echo.
    echo Co loi khi mo giao dien GUI, dang thu mo bang giao dien dong lenh (main.py)...
    python main.py
)
pause
