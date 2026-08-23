@echo off
cd /d "%~dp0"

echo ==========================================
echo   TikTok -^> UCircle Auto Pipeline
echo ==========================================
echo.
echo [1/3] Dang kiem tra/cai dat thu vien can thiet...
python -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
    echo.
    echo [LOI] Cai dat thu vien that bai. Kiem tra da cai Python va co ket noi mang chua.
    pause
    exit /b 1
)

echo [2/3] Dang kiem tra trinh duyet Playwright (Chromium)...
python -m playwright install chromium
if errorlevel 1 (
    echo.
    echo [LOI] Cai dat trinh duyet Playwright that bai.
    pause
    exit /b 1
)

echo [3/3] Dang khoi dong giao dien...
python gui.py

pause
