#!/usr/bin/env bash
# =============================================================================
#  Build CTS.app bang PyInstaller (windowed, .app bundle cho macOS).
#  Yeu cau: Python 3.10+ (nen dung ban tu python.org de co Tcl/Tk moi).
#  Chay:  chmod +x build_mac.sh && ./build_mac.sh
#
#  LUU Y: KHONG dung --onefile cho macOS. Bundle .app da la 1 goi thu muc;
#  --onefile lam cham khoi dong va de loi voi Tkinter tren macOS.
# =============================================================================

set -euo pipefail
cd "$(dirname "$0")"

echo "[1/3] Don dep thu muc build cu..."
rm -rf build dist CTS.spec

echo "[2/3] Cai dat dependency..."
python3 -m pip install --upgrade pip >/dev/null
python3 -m pip install -r requirements.txt

echo "[3/3] Dong goi voi PyInstaller (.app)..."
python3 -m PyInstaller \
    --noconfirm \
    --windowed \
    --name "CTS" \
    --paths "src" \
    --osx-bundle-identifier "com.paa.cts" \
    "src/cts_tool.py"

echo ""
echo "=== Build xong ==="
echo "App bundle: $(pwd)/dist/CTS.app"
