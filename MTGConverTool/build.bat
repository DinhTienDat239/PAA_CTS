@echo off
REM ====================================================================
REM  Build MTGConverTool.exe bang PyInstaller
REM  Yeu cau: Python 3.10+ va da `pip install -r requirements.txt`.
REM ====================================================================

setlocal
cd /d "%~dp0"

echo [1/3] Don dep thu muc build cu...
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist
if exist MTGConverTool.spec del /q MTGConverTool.spec

echo [2/3] Cai dat dependency...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo [3/3] Dong goi voi PyInstaller...
python -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "MTGConverTool" ^
    --paths "src" ^
    "src\mtg_convert_tool.py"
if errorlevel 1 goto :fail

echo.
echo === Build xong ===
echo File exe: %CD%\dist\MTGConverTool.exe
exit /b 0

:fail
echo *** Build that bai ***
exit /b 1
