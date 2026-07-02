# MTG Convert Tool

Tool nhỏ viết bằng Python 3 + Tkinter, có giao diện cửa sổ và bản
**.exe** đóng gói bằng PyInstaller. Chức năng: chọn 1 file HTML Luna
Playable (build cho `unityads`) → tự động convert sang build
**Mintegral** theo công thức trong `công thức convert Mintegra.txt`.

## Cấu trúc thư mục

```
MTGConverTool/
├── src/
│   ├── mtg_convert_tool.py    # GUI Tkinter – entry point
│   └── mintegra_converter.py  # Core: 5 phép biến đổi
├── dist/
│   └── MTGConverTool.exe      # Bản build sẵn (sinh ra sau khi chạy build.bat)
├── requirements.txt           # pyinstaller
├── build.bat                  # Script build .exe
└── README.md
```

## Chạy nhanh (đã có .exe)

1. Vào `dist/`, double-click **`MTGConverTool.exe`**.
2. Bấm **"Chọn file HTML…"** → chọn file `Input.html`.
3. Bấm **"Convert sang Mintegral"**.
4. Thư mục `Output/` được tạo cùng cấp với file input và chứa:
   - `mintegral.html`
   - `assets/scripts.js`
   - `assets/jsons.js`
   - `assets/blobs.js`
5. Bấm **"Mở thư mục output"** để xem kết quả.

## Chạy bản Python (không cần build)

```powershell
cd MTGConverTool
python src\mtg_convert_tool.py
```

## CLI (không cần GUI)

```powershell
python src\mintegra_converter.py <input.html> [output_dir]
```

Mặc định `output_dir` là `<thư mục chứa input>/Output`.

## Build lại .exe

```powershell
cd MTGConverTool
pip install -r requirements.txt
.\build.bat
```

PyInstaller sẽ sinh ra **`dist/MTGConverTool.exe`** (one-file, windowed,
không hiện console).

## Các phép biến đổi áp dụng (tóm tắt)

| # | Mô tả                                                                                       |
|---|---------------------------------------------------------------------------------------------|
| 1 | Tách 3 khối `<script data-startup-only>` (sounds/jsons/blobs) ra `assets/*.js` ngoài file. |
| 2 | Xoá script remote-debug `insertYourRemoteDebuggingTokenHere` (console.re).                 |
| 3 | Đổi `targetPlatform:"unityads"` → `targetPlatform:"mintegral"`.                            |
| 4 | Rút gọn `window.pi.apply(window,[]||[])` → `window.pi.apply()`.                            |
| 5 | Thay 2 đoạn SDK adapter MRAID ở cuối `<body>` bằng template Mintegral.                     |

Chi tiết đầy đủ xem file `công thức convert Mintegra.txt` (ngoài thư mục
này).
