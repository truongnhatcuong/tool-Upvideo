@echo off
cd /d "%~dp0"

echo ==========================================
echo   TikTok -^> UCircle Auto Pipeline
echo ==========================================
echo.

REM Kiem tra neu co moi truong ao thi dung, neu khong thi dung python he thong
set "PY_CMD=python"
if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
) else if exist "venv\Scripts\python.exe" (
    set "PY_CMD=venv\Scripts\python.exe"
)

echo [1/3] Dang kiem tra/cai dat thu vien can thiet...
%PY_CMD% -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
    echo.
    echo [LOI] Cai dat thu vien that bai. Kiem tra da cai Python va co ket noi mang chua.
    pause
    exit /b 1
)

echo [2/3] Dang kiem tra trinh duyet Playwright (Chromium)...
%PY_CMD% -m playwright install chromium
if errorlevel 1 (
    echo.
    echo [LOI] Cai dat trinh duyet Playwright that bai.
    pause
    exit /b 1
)

echo [3/3] Dang khoi dong giao dien...
%PY_CMD% gui.py

pause
