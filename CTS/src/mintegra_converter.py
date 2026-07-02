"""Core converter: Luna Playable HTML (unityads) -> Mintegral build.

Cài đặt 5 phép biến đổi mô tả trong "công thức convert Mintegra.txt".
Module này KHÔNG phụ thuộc GUI, có thể dùng trực tiếp từ CLI hoặc test.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


# ---------------------------------------------------------------------------
# Hằng số: 4 template SDK adapter (lấy nguyên văn từ Input/Output mẫu)
# ---------------------------------------------------------------------------

MRAID_VIEWABILITY_SCRIPT = (
    '<script>!function(){var n=!1,e=!1;function t(){return mraid.isViewable()'
    '&&"hidden"!==mraid.getState()}function a(){n?t()&&e?(window.dispatchEvent'
    '(new Event("luna:resume")),e=!1):t()||e||(window.dispatchEvent'
    '(new Event("luna:pause")),e=!0):t()&&(window.dispatchEvent'
    '(new Event("luna:start")),n=!0)}function i(){}function d(n){'
    'window.dispatchEvent(new Event(n?"luna:unsafe:unmute":"luna:unsafe:mute"))'
    '}var r=function(){"undefined"!=typeof mraid?('
    'mraid.removeEventListener("ready",r),'
    'mraid.addEventListener("viewableChange",a),'
    'mraid.addEventListener("stateChange",a),'
    'mraid.addEventListener("orientationchange",i),'
    'mraid.addEventListener("audioVolumeChange",d),a()):'
    'window.dispatchEvent(new Event("luna:start"))};'
    'window.addEventListener("luna:build",(function(){'
    'window.pi.logLoaded(),"undefined"!=typeof mraid?'
    '"loading"===mraid.getState()?mraid.addEventListener("ready",r):r():'
    'window.dispatchEvent(new Event("luna:start"))}))}()</script>'
)

MINTEGRAL_LIFECYCLE_SCRIPT = (
    '<script>window.gameClose = function () { window.dispatchEvent(new Event('
    '"luna:pause")) }, window.addEventListener("luna:build", (() => { '
    'Bridge.ready((() => { Luna.Unity.Playable.InstallFullGame = function () { '
    'window.pi.logCta(), window.install && window.install() } })) })), '
    'window.addEventListener("luna:ended", (() => { window.gameEnd && '
    'window.gameEnd() }))</script>'
)

MRAID_INSTALL_SCRIPT = (
    '<script>window.addEventListener("luna:build",(function(){'
    'Bridge.ready((function(){'
    'Luna.Unity.Playable.InstallFullGame=function(n,i){'
    'window.pi.logCta(),'
    'n=n||window.$environment.packageConfig.iosLink,'
    'i=i||window.$environment.packageConfig.androidLink;'
    'const o=/iphone|ipad|ipod|macintosh/i.test('
    'window.navigator.userAgent.toLowerCase())?n:i;'
    '"undefined"!=typeof mraid?mraid.open(o):('
    'console.warn("Mraid is not defined"),window.open(o,"_blank"))'
    '}}))}))</script>'
)

MINTEGRAL_INSTALL_SCRIPT = (
    '<script>window.addEventListener("luna:build", (() => { '
    'window.pi.logLoaded(), window.dispatchEvent(new Event('
    '"luna:unsafe:pause")), window.dispatchEvent(new Event('
    '"luna:start")) })), window.addEventListener("luna:started", (() => { '
    'window.gameReady && window.gameReady() })), window.gameStart = '
    'function () { window.dispatchEvent(new Event("luna:unsafe:resume")) }'
    '</script>'
)


# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------

# Tách 3 khối <script data-startup-only>...</script> (Transform 1)
RE_STARTUP_BLOCK = re.compile(
    r'<script data-startup-only>(.*?)</script>',
    re.DOTALL,
)

# Cắt script remote-debug console.re (Transform 2)
RE_REMOTE_DEBUG = re.compile(
    r'<script>\(\(\)=>\{let e=window\.insertYourRemoteDebuggingTokenHere'
    r'.*?</script>',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Kết quả convert (báo log cho GUI)
# ---------------------------------------------------------------------------


@dataclass
class ConvertResult:
    """Tóm tắt thao tác convert (dùng cho GUI hiển thị log)."""

    output_html_path: Path | None = None
    assets_dir: Path | None = None
    asset_files: list[Path] = field(default_factory=list)
    transforms_applied: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    input_size: int = 0
    output_html_size: int = 0
    total_asset_size: int = 0


# ---------------------------------------------------------------------------
# Hàm convert chính
# ---------------------------------------------------------------------------


def _classify_startup_block(body: str) -> str | None:
    """Phân loại 1 block <script data-startup-only>...</script>.

    Trong file Luna playable có TỚI 7 khối <script data-startup-only>, nhưng
    chỉ 3 trong số đó là bundle data cần tách ra ngoài. 4 khối còn lại
    (startup, spector, makeBrotliDecodeStr, _base64ToArrayBuffer) phải giữ
    NGUYÊN inline trong HTML.

    Returns:
        "scripts" | "jsons" | "blobs" nếu là bundle cần tách,
        None nếu khối đó phải giữ nguyên.
    """
    head = body.lstrip()[:80]
    if head.startswith('window.blobs'):
        return 'blobs'
    if head.startswith('window.jsons'):
        return 'jsons'
    # "scripts" bundle (chứa sounds) bắt đầu bằng:
    #   window._compressedAssets = window._compressedAssets || [];
    # Đồng thời phải có lời gọi push() chứa decompressString (sound bundle).
    if (
        head.startswith('window._compressedAssets')
        and '_compressedAssets.push' in body
        and 'decompressString' in body
    ):
        return 'scripts'
    return None


def convert_html(
    input_path: str | os.PathLike,
    output_dir: str | os.PathLike,
    log: Callable[[str], None] | None = None,
) -> ConvertResult:
    """Convert 1 file Luna Playable (unityads) sang build Mintegral.

    Args:
        input_path: file HTML nguồn.
        output_dir: thư mục đầu ra (sẽ tự tạo, kể cả assets/ bên trong).
        log: callback nhận chuỗi log (tuỳ chọn).

    Returns:
        ConvertResult chứa các thông tin về file đã sinh.
    """
    def _log(msg: str) -> None:
        if log is not None:
            log(msg)

    input_path = Path(input_path)
    output_dir = Path(output_dir)

    if not input_path.exists():
        raise FileNotFoundError(f'Không tìm thấy file input: {input_path}')

    _log(f'Đọc file input: {input_path}')
    # newline='' để KHÔNG normalize line endings (giữ nguyên CRLF/LF như input)
    with input_path.open('r', encoding='utf-8', newline='') as f:
        html = f.read()
    result = ConvertResult(input_size=len(html))
    _log(f'  Kích thước input: {len(html):,} ký tự')

    assets_dir = output_dir / 'assets'
    assets_dir.mkdir(parents=True, exist_ok=True)
    result.assets_dir = assets_dir

    # ------------------------------------------------------------------ #
    # TRANSFORM 1 – Tách 3 khối <script data-startup-only>...
    # ------------------------------------------------------------------ #
    seen_types: set[str] = set()
    asset_files: dict[str, Path] = {}

    def _replace_block(match: re.Match[str]) -> str:
        body = match.group(1)
        kind = _classify_startup_block(body)
        if kind is None:
            # Block startup-only KHÔNG phải bundle (startup/spector/brotli/base64)
            # → giữ NGUYÊN, không động đến.
            return match.group(0)
        if kind in seen_types:
            result.warnings.append(
                f'Tìm thấy 2 block "{kind}" – block sau đè block trước'
            )
        seen_types.add(kind)
        asset_path = assets_dir / f'{kind}.js'
        with asset_path.open('w', encoding='utf-8', newline='') as f:
            f.write(body)
        asset_files[kind] = asset_path
        _log(f'  + Tách {kind:>7} -> {asset_path} ({len(body):,} ký tự)')
        return (
            f'<script src="assets/{kind}.js" defer data-startup-only></script>'
        )

    new_html = RE_STARTUP_BLOCK.sub(_replace_block, html)
    n_extracted = len(seen_types)
    if n_extracted == 0:
        result.warnings.append('Không tìm thấy bundle <script data-startup-only> nào để tách')
    else:
        result.transforms_applied.append(
            f'1. Tách {n_extracted}/3 bundle <script data-startup-only> ra ngoài'
        )
    html = new_html
    result.asset_files = sorted(asset_files.values())

    # ------------------------------------------------------------------ #
    # TRANSFORM 2 – Xoá script remote-debug
    # ------------------------------------------------------------------ #
    new_html, n_dbg = RE_REMOTE_DEBUG.subn('', html)
    if n_dbg > 0:
        result.transforms_applied.append(
            f'2. Xoá {n_dbg} script remote-debug (console.re)'
        )
        _log(f'  + Xoá script remote-debug ({n_dbg} block)')
    else:
        result.warnings.append('Không tìm thấy script remote-debug để xoá')
    html = new_html

    # ------------------------------------------------------------------ #
    # TRANSFORM 3 – Đổi targetPlatform
    # ------------------------------------------------------------------ #
    if 'targetPlatform:"unityads"' in html:
        html = html.replace('targetPlatform:"unityads"', 'targetPlatform:"mintegral"', 1)
        result.transforms_applied.append('3. Đổi targetPlatform "unityads" -> "mintegral"')
        _log('  + Đổi targetPlatform -> "mintegral"')
    elif 'targetPlatform:"mintegral"' in html:
        result.warnings.append('targetPlatform đã là "mintegral" – bỏ qua')
    else:
        result.warnings.append('Không tìm thấy targetPlatform:"unityads"')

    # ------------------------------------------------------------------ #
    # TRANSFORM 4 – Đơn giản hoá window.pi.apply(...)
    # ------------------------------------------------------------------ #
    if 'window.pi.apply(window,[]||[])' in html:
        html = html.replace(
            'window.pi.apply(window,[]||[])', 'window.pi.apply()', 1
        )
        result.transforms_applied.append('4. window.pi.apply(window,[]||[]) -> window.pi.apply()')
        _log('  + Đơn giản hoá window.pi.apply()')
    else:
        result.warnings.append(
            'Không tìm thấy window.pi.apply(window,[]||[])'
        )

    # ------------------------------------------------------------------ #
    # TRANSFORM 5 – Thay 2 đoạn SDK adapter MRAID -> Mintegral
    # ------------------------------------------------------------------ #
    if MRAID_VIEWABILITY_SCRIPT in html:
        html = html.replace(MRAID_VIEWABILITY_SCRIPT, MINTEGRAL_LIFECYCLE_SCRIPT, 1)
        result.transforms_applied.append('5A. Thay MRAID viewability -> Mintegral lifecycle')
        _log('  + Thay MRAID viewability adapter')
    else:
        result.warnings.append('Không tìm thấy MRAID viewability script (5A)')

    if MRAID_INSTALL_SCRIPT in html:
        html = html.replace(MRAID_INSTALL_SCRIPT, MINTEGRAL_INSTALL_SCRIPT, 1)
        result.transforms_applied.append('5B. Thay MRAID install -> Mintegral install')
        _log('  + Thay MRAID install adapter')
    else:
        result.warnings.append('Không tìm thấy MRAID install script (5B)')

    # ------------------------------------------------------------------ #
    # Ghi file output
    # ------------------------------------------------------------------ #
    output_html = output_dir / 'mintegral.html'
    # Ghi với CRLF line endings để khớp đầu ra mẫu của pipeline Luna trên Windows.
    # (Trình duyệt không quan tâm CRLF/LF, nhưng giữ vậy để diff byte-perfect.)
    html_out = html.replace('\r\n', '\n').replace('\n', '\r\n')
    with output_html.open('wb') as f:
        f.write(html_out.encode('utf-8'))
    result.output_html_path = output_html
    result.output_html_size = len(html)
    result.total_asset_size = sum(p.stat().st_size for p in result.asset_files)

    _log(f'Ghi output: {output_html} ({len(html):,} ký tự)')
    _log(f'Tổng asset: {result.total_asset_size:,} bytes')
    return result


if __name__ == '__main__':
    # CLI debug: python mintegra_converter.py <input.html> [output_dir]
    import sys

    # Đảm bảo console Windows in được tiếng Việt
    try:
        sys.stdout.reconfigure(encoding='utf-8')  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding='utf-8')  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

    if len(sys.argv) < 2:
        print('Usage: python mintegra_converter.py <input.html> [output_dir]')
        sys.exit(1)
    in_path = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) >= 3 else in_path.parent / 'Output'
    r = convert_html(in_path, out_dir, log=print)
    print('--- DONE ---')
    print('HTML output :', r.output_html_path)
    print('Assets dir  :', r.assets_dir)
    print('Transforms  :', r.transforms_applied)
    if r.warnings:
        print('Warnings    :', r.warnings)
