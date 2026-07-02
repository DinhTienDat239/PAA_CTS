"""Core converter: Luna Playable HTML (unityads) -> Moloco (MLC) build.

Tool convert 1 file Luna Playable sang build cho mạng quảng cáo Moloco.
Logic giống META converter, chỉ khác ở:
  • Chuỗi targetPlatform đích: "moloco" (META = "facebook").
  • Suffix tên file output: "_MLC" (META = "_Meta").

Template script cuối dùng FbPlayableAd cùng với META theo công thức user
cung cấp (đây không phải Facebook adapter mà là template chung mà pipeline
Moloco của user đang sử dụng).

Logic MLC convert (3 phép biến đổi):
  1. Đổi `targetPlatform:"unityads"` -> `targetPlatform:"moloco"`.
     (Bắt buộc – nếu không tìm thấy thì raise MLCConvertError.)
  2. Clean tất cả `window.pi.apply(<bất kỳ args>)` -> `window.pi.apply()`.
  3. Xoá 2 thẻ `<script>` cuối cùng (SDK adapter cũ) và thay bằng 1 template
     dùng FbPlayableAd.onCTAClick (FACEBOOK_SCRIPT).

Output: `<basename_input>_MLC.html` đặt trong output_dir.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


# ---------------------------------------------------------------------------
# Hằng số: template Facebook script (lấy NGUYÊN VĂN theo công thức user cung cấp).
# Tham chiếu chéo: nội dung này giống `meta_converter.FACEBOOK_SCRIPT`. Giữ
# duplicate có chủ ý để mỗi network module tự đứng độc lập theo quy chuẩn.
# ---------------------------------------------------------------------------

FACEBOOK_SCRIPT = (
    '<script>window.addEventListener("luna:build",(()=>{Bridge.ready((()=>{'
    'Luna.Unity.Playable.InstallFullGame=function(){'
    '"undefined"!=typeof FbPlayableAd?FbPlayableAd.onCTAClick():'
    '(console.warn("FbPlayableAd is not defined"),'
    'window.open(window.$environment.packageConfig.iosLink||'
    'window.$environment.packageConfig.androidLink,"_blank"))}}))})),'
    'window.addEventListener("open_ctalink",(()=>{FbPlayableAd.onCTAClick()})),'
    'window.addEventListener("luna:build",(()=>{window.pi.logLoaded(),'
    'window.dispatchEvent(new Event("luna:start"))}))</script>'
)


# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------

SCRIPT_PATTERN = re.compile(
    r'<script\b[^>]*>.*?</script>', re.DOTALL | re.IGNORECASE
)

PI_APPLY_PATTERN = re.compile(r'window\.pi\.apply\([^)]*\)')


# ---------------------------------------------------------------------------
# Kết quả & lỗi
# ---------------------------------------------------------------------------


@dataclass
class MLCConvertResult:
    """Tóm tắt thao tác MLC convert (dùng cho GUI hiển thị log)."""

    output_html_path: Path | None = None
    transforms_applied: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    input_size: int = 0
    output_html_size: int = 0
    platform_replaced: int = 0
    pi_apply_cleaned: int = 0
    scripts_seen: int = 0


class MLCConvertError(RuntimeError):
    """Raised khi input không đủ điều kiện để convert sang Moloco build."""


# ---------------------------------------------------------------------------
# Hàm convert chính
# ---------------------------------------------------------------------------


def convert_html(
    input_path: str | os.PathLike,
    output_dir: str | os.PathLike,
    log: Callable[[str], None] | None = None,
    output_filename: str | None = None,
) -> MLCConvertResult:
    """Convert 1 file Luna Playable (unityads) sang build Moloco.

    Args:
        input_path: file HTML Luna playable nguồn.
        output_dir: thư mục đầu ra (tự tạo nếu thiếu).
        log: callback nhận chuỗi log (tuỳ chọn).
        output_filename: tên file output (mặc định "<basename>_MLC.html").

    Returns:
        MLCConvertResult chứa thông tin convert.

    Raises:
        MLCConvertError: nếu thiếu targetPlatform "unityads" hoặc < 2 thẻ
            `<script>` để thay.
        FileNotFoundError: nếu input không tồn tại.
    """

    def _log(msg: str) -> None:
        if log is not None:
            log(msg)

    input_path = Path(input_path)
    output_dir = Path(output_dir)

    if not input_path.exists():
        raise FileNotFoundError(f'Không tìm thấy file input: {input_path}')

    _log(f'Đọc file input: {input_path}')
    with input_path.open('r', encoding='utf-8') as f:
        content = f.read()
    result = MLCConvertResult(input_size=len(content))
    _log(f'  Kích thước input: {len(content):,} ký tự')

    output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # BƯỚC 1 – Đổi targetPlatform "unityads" -> "moloco"
    # ------------------------------------------------------------------ #
    needle = 'targetPlatform:"unityads"'
    n_platform = content.count(needle)
    if n_platform == 0:
        raise MLCConvertError(
            'Không thấy chuỗi targetPlatform:"unityads" trong input. '
            'MLC converter chỉ chạy được trên file Luna playable build cho unityads.'
        )
    content = content.replace(needle, 'targetPlatform:"moloco"', 1)
    result.platform_replaced = n_platform
    result.transforms_applied.append(
        f'1. Đổi targetPlatform "unityads" -> "moloco" ({n_platform} match)'
    )
    _log(f'  + Đổi targetPlatform -> "moloco" ({n_platform} match)')

    # ------------------------------------------------------------------ #
    # BƯỚC 2 – Clean window.pi.apply(...) -> window.pi.apply()
    # ------------------------------------------------------------------ #
    content, n_pi = PI_APPLY_PATTERN.subn('window.pi.apply()', content)
    result.pi_apply_cleaned = n_pi
    if n_pi > 0:
        result.transforms_applied.append(
            f'2. Clean {n_pi} `window.pi.apply(...)` -> `window.pi.apply()`'
        )
        _log(f'  + Clean {n_pi} window.pi.apply(...)')
    else:
        result.warnings.append('Không tìm thấy window.pi.apply(...) nào để clean')

    # ------------------------------------------------------------------ #
    # BƯỚC 3 – Xoá 2 thẻ <script> cuối + thay bằng 1 template Facebook
    # ------------------------------------------------------------------ #
    matches = list(SCRIPT_PATTERN.finditer(content))
    result.scripts_seen = len(matches)
    if len(matches) < 2:
        raise MLCConvertError(
            f'Không đủ 2 thẻ <script> để thay (chỉ thấy {len(matches)}).'
        )
    second_last = matches[-2]
    last = matches[-1]
    content = (
        content[: second_last.start()]
        + FACEBOOK_SCRIPT
        + content[last.end():]
    )
    result.transforms_applied.append(
        f'3. Thay 2 <script> cuối (trong tổng {len(matches)} thẻ) '
        'bằng template FbPlayableAd'
    )
    _log(
        f'  + Thay 2 <script> cuối bằng template Facebook '
        f'(tổng {len(matches)} thẻ <script> trong file)'
    )

    # ------------------------------------------------------------------ #
    # BƯỚC 4 – Ghi file output
    # ------------------------------------------------------------------ #
    if output_filename is None:
        output_filename = f'{input_path.stem}_MLC{input_path.suffix or ".html"}'
    output_html = output_dir / output_filename

    content_out = content.replace('\r\n', '\n').replace('\n', '\r\n')
    with output_html.open('wb') as f:
        f.write(content_out.encode('utf-8'))

    result.output_html_path = output_html
    result.output_html_size = len(content)
    result.transforms_applied.append(f'4. Ghi output: {output_html.name}')
    _log(f'Ghi output: {output_html} ({len(content):,} ký tự)')

    return result


if __name__ == '__main__':
    # CLI debug: python mlc_converter.py <input.html> [output_dir]
    import sys

    try:
        sys.stdout.reconfigure(encoding='utf-8')  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding='utf-8')  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

    if len(sys.argv) < 2:
        print('Usage: python mlc_converter.py <input.html> [output_dir]')
        sys.exit(1)
    in_path = Path(sys.argv[1])
    out_dir = (
        Path(sys.argv[2]) if len(sys.argv) >= 3 else in_path.parent / 'Output'
    )
    try:
        r = convert_html(in_path, out_dir, log=print)
    except MLCConvertError as exc:
        print('!! Lỗi:', exc)
        sys.exit(2)
    print('--- DONE ---')
    print('HTML output :', r.output_html_path)
    print('Transforms  :', r.transforms_applied)
    if r.warnings:
        print('Warnings    :', r.warnings)
