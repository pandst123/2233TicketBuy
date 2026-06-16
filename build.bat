@echo off
chcp 65001 >nul
echo ========================================
echo 2233TicketBuy Build Script
echo ========================================
echo.

echo [1/3] Checking PyInstaller...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller
)

echo [2/3] Building...
python -m PyInstaller --clean 2233TicketBuy.spec

echo [3/3] Done!
echo.
echo Output: dist\2233TicketBuy.exe
echo.
pause
