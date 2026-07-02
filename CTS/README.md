# CTS Convert Tool

Tool **CTS** (Convert To SDK) tích hợp **5 chức năng convert** Luna Playable
HTML trong cùng 1 .exe + 1 cửa sổ Tkinter:

| Network | Mô tả | Input |
|---------|------|-------|
| **AL**   | AppLovin – strip script remote-debug, strip script `data-startup-only` chứa URL CDN, strip mọi URL/`href` hard-coded. | File HTML gốc |
| **MTG**  | Mintegral – tách 3 bundle `<script data-startup-only>` ra `assets/*.js`, xoá remote-debug, đổi `targetPlatform` "unityads" → "mintegral", thay SDK adapter MRAID → Mintegral. | File HTML gốc |
| **GG**   | Google – đổi `targetPlatform` "mintegral" → "google", thay 2 `<script>` cuối bằng template Google (`window.devicePixelRatio = 2`, `Luna.Unity.Playable.InstallFullGame = window.ExitApi.exit`). | **`mintegral.html` của MTG** (tick GG sẽ tự tick MTG) |
| **META** | Meta / Facebook – đổi `targetPlatform` "unityads" → "facebook", clean `window.pi.apply(...)` → `window.pi.apply()`, thay 2 `<script>` cuối bằng template `FbPlayableAd.onCTAClick`. | File HTML gốc |
| **MLC**  | Moloco – đổi `targetPlatform` "unityads" → "moloco", clean `window.pi.apply(...)`, thay 2 `<script>` cuối bằng cùng template FbPlayableAd với META. | File HTML gốc |

AL / MTG / GG đã verify **byte-perfect** với tool gốc tương ứng. META / MLC
là spec mới (không có tool legacy đối chiếu) – kiểm tra bằng checklist trong
`Quy chuẩn dự án CTS.txt` mục 4.6.

## Cấu trúc thư mục

```
CTS/
├── src/
│   ├── cts_tool.py            # GUI Tkinter – entry point
│   ├── mintegra_converter.py  # Core MTG  (5 phép biến đổi)
│   ├── al_converter.py        # Core AL   (port từ ALConvertTool)
│   ├── gg_converter.py        # Core GG   (port từ GGConvertTool)
│   ├── meta_converter.py      # Core META (Meta / Facebook playable)
│   └── mlc_converter.py       # Core MLC  (Moloco playable)
├── dist/
│   ├── CTS.exe                # Bản build Windows (sinh sau khi chạy build.bat)
│   └── CTS.app               # Bản build macOS  (sinh sau khi chạy build_mac.sh)
├── requirements.txt           # pyinstaller
├── build.bat                  # Script build .exe (Windows)
├── build_mac.sh               # Script build .app (macOS)
└── README.md
```

## Chạy nhanh (đã có .exe)

1. Vào `dist/`, double-click **`CTS.exe`**.
2. Bấm **"Chọn file HTML…"** → chọn file Luna playable gốc (build cho `unityads`).
3. Tick các network cần convert (mặc định cả 3 đều tick).
   - **Tick GG sẽ tự động tick MTG** (vì GG cần `mintegral.html` của MTG làm input).
4. Bấm **"Convert"**.
5. Thư mục `Output/` được tạo cùng cấp với file input, mỗi network 1 subfolder:
   - `Output/AL/<basename>_AL.html`
   - `Output/MTG/mintegral.html`  +  `Output/MTG/assets/{scripts,jsons,blobs}.js`
   - `Output/GG/index.html`       +  `Output/GG/assets/{scripts,jsons,blobs}.js`
     *(assets được copy y nguyên từ thư mục MTG để playable Google chạy được)*
   - `Output/META/<basename>_Meta.html`
   - `Output/MLC/<basename>_MLC.html`
6. Bấm **"Mở thư mục output"** để xem kết quả.

## Chạy bản Python (không cần build)

```powershell
cd CTS
python src\cts_tool.py
```

## CLI (không cần GUI)

```powershell
python src\mintegra_converter.py <input.html> [output_dir]       # convert MTG
python src\al_converter.py        <input.html> [output_dir]       # convert AL
python src\gg_converter.py        <mintegral.html> [output_dir]   # convert GG
python src\meta_converter.py      <input.html> [output_dir]       # convert META
python src\mlc_converter.py       <input.html> [output_dir]       # convert MLC
```

## Build lại .exe

```powershell
cd CTS
pip install -r requirements.txt
.\build.bat
```

PyInstaller sinh ra **`dist/CTS.exe`** (one-file, windowed, không hiện console).

## Build bản macOS (.app)

> ⚠️ PyInstaller KHÔNG cross-compile: **phải build trên macOS** (máy Mac thật
> hoặc CI runner macOS). Không thể build `.app` từ Windows.

Trên máy Mac:

```bash
cd CTS
chmod +x build_mac.sh
./build_mac.sh
```

Sinh ra **`dist/CTS.app`** (windowed bundle, KHÔNG dùng `--onefile`).
Lần đầu mở app chưa ký: chuột phải vào `CTS.app` → **Open** để bỏ qua
Gatekeeper.

### Build cho macOS mà KHÔNG có máy Mac (GitHub Actions)

Repo có sẵn workflow `.github/workflows/build.yml`. Mỗi lần push (hoặc bấm
"Run workflow" trong tab **Actions**), GitHub build song song:

- `CTS-windows-exe`  → `CTS.exe`  (runner `windows-latest`)
- `CTS-macos-app`    → `CTS.app`  (runner `macos-14`, Apple Silicon / arm64)

Tải kết quả trong tab **Actions → lần chạy → mục Artifacts**.

## Các phép biến đổi (tóm tắt)

### MTG (Mintegral)
1. Tách 3 bundle `<script data-startup-only>` (sounds/jsons/blobs) ra `assets/*.js`.
   *(Có TỚI 7 khối `data-startup-only`, chỉ tách 3 bundle thật;
   4 khối còn lại — `startup`/`spector`/`brotli`/`base64` — giữ nguyên inline.)*
2. Xoá `<script>` `insertYourRemoteDebuggingTokenHere` (console.re).
3. `targetPlatform:"unityads"` → `targetPlatform:"mintegral"`.
4. `window.pi.apply(window,[]||[])` → `window.pi.apply()`.
5. Thay 2 đoạn SDK adapter MRAID ở cuối `<body>` bằng template Mintegral
   (`window.gameClose/Start/Ready/End`, `window.install`).

### AL (AppLovin)
1. Quét toàn bộ `<script>...</script>`, xoá:
   - Script chứa `insertYourRemoteDebugging`.
   - Script có `data-startup-only` đồng thời chứa URL `http(s)://`.
   - **Bắt buộc** cả 2 loại phải có ≥1 match.
2. Strip URL hard-coded khắp file: `"link"` → `""`, `"https?://…"` → `""`, `href="…"` → `href=""`.
3. Ghi `<basename>_AL.html` vào `Output/AL/`.

### GG (Google) – chạy SAU MTG
1. Đọc file `Output/MTG/mintegral.html`.
2. Đổi `targetPlatform:"mintegral"` → `targetPlatform:"google"`.
3. Tìm tất cả `<script>...</script>`, lấy 2 thẻ cuối cùng:
   - Thay thẻ kế cuối bằng template `window.devicePixelRatio = 2 + luna:start`.
   - Thay thẻ cuối bằng template `Luna.Unity.Playable.InstallFullGame = window.ExitApi.exit`.
4. Ghi `index.html` vào `Output/GG/`.
5. Copy `assets/` từ `Output/MTG/` sang `Output/GG/`.

### META (Meta / Facebook)
1. Đổi `targetPlatform:"unityads"` → `targetPlatform:"facebook"` (bắt buộc).
2. Clean tất cả `window.pi.apply(<bất kỳ args>)` → `window.pi.apply()`
   (regex `window\.pi\.apply\([^)]*\)`).
3. Xoá 2 thẻ `<script>` cuối + thay bằng 1 template duy nhất dùng
   `FbPlayableAd.onCTAClick` (bắt buộc có ≥ 2 thẻ `<script>` trong file).
4. Ghi `<basename>_Meta.html` vào `Output/META/`.

### MLC (Moloco)
Giống META, chỉ khác:
1. `targetPlatform` đích là `"moloco"`.
2. Tên file output là `<basename>_MLC.html` (vào `Output/MLC/`).

## Mở rộng thêm network sau này

Để thêm network mới (ví dụ `IS` cho ironSource):
1. Tạo file `src/is_converter.py` có hàm `convert_html(input_path, output_dir, log=...)`.
2. Trong `cts_tool.py` thêm 1 dòng vào list `NETWORKS` và `NETWORK_ORDER`.
3. Nếu network mới phụ thuộc network khác (giống GG → MTG), thêm vào `NETWORK_DEPENDENCIES`.
4. Thêm nhánh `elif key == 'IS':` trong `_run_convert()`.
5. Viết hàm `_log_is_result(res)` (giống `_log_meta_result` / `_log_mlc_result`).

Rebuild bằng `build.bat`.
