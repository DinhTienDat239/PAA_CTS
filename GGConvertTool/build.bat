@echo off
setlocal

echo Thu muc dang chay: %cd%
echo.

python -m pip install --upgrade pyinstaller
python -m PyInstaller --onefile --noconsole --name GGConvertTool --distpath . --workpath build main.py

echo.
if exist "GGConvertTool.exe" (
  echo Da tao xong file exe trong thu muc hien tai
  start "" "%cd%"
) else (
  echo Khong tim thay GGConvertTool.exe. Vui long xem log o tren.
)
pause
