@echo off
chcp 65001 > nul

echo =====================================================
echo   Naver Pay Auto Clicker - Setup
echo =====================================================
echo.

python --version > nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo Please install Python 3.11+ from https://www.python.org
    echo Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

echo [1/3] Python OK:
python --version

echo.
echo [2/3] Installing packages...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)

echo.
echo [3/3] Installing Playwright browser...
python -m playwright install chromium
if errorlevel 1 (
    echo [ERROR] Playwright install failed.
    pause
    exit /b 1
)

echo.
echo =====================================================
echo   Setup complete!
echo.
echo   Usage:
echo     1. Run login.bat  (first time only)
echo     2. Run run.bat    (every time)
echo =====================================================
echo.
pause
