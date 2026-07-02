"""Core converter: Mintegral HTML -> Google (GG) build.

Port từ `GGConvertTool/main.py` (giữ NGUYÊN logic gốc), refactor thành
1 hàm `convert_html(...)` cùng chữ ký với 2 converter còn lại.

LƯU Ý QUAN TRỌNG:
  Input của GG converter **không phải** file HTML gốc, mà là file
  `mintegral.html` – tức là output đã qua MTG converter. Hàm gọi từ GUI
  phải đảm bảo MTG được chạy trước và truyền file mintegral.html vào đây.

Logic GG convert (2 bước):
  1. Đổi `targetPlatform:"mintegral"` -> `targetPlatform:"google"`.
  2. Quét toàn bộ <script>...</script>, thay:
     - <script> cuối cùng (last)        -> NEW_SCRIPT_2 (Install Full Game)
     - <script> kế cuối (second-last)   -> NEW_SCRIPT_1 (devicePixelRatio + luna:start)
  3. Cả 2 bước đều BẮT BUỘC – nếu không tìm được thì raise GGConvertError.
  4. Ghi output thành "index.html" trong output_dir.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


# ---------------------------------------------------------------------------
# Hằng số: 2 script template thay 2 <script> cuối
# (lấy NGUYÊN VĂN từ GGConvertTool/main.py)
# ---------------------------------------------------------------------------

NEW_SCRIPT_1 = (
    '<script>window.addEventListener("DOMContentLoaded", (() => { '
    'window.devicePixelRatio = 2 })), '
    'window.addEventListener("luna:build", (function () { '
    'window.pi.logLoaded(), '
    'window.dispatchEvent(new Event("luna:start")) }))</script>'
)

NEW_SCRIPT_2 = (
    '  <script>window.addEventListener("luna:build", (() => { '
    'Bridge.ready((() => { '
    'Luna.Unity.Playable.InstallFullGame = function () { '
    'window.ExitApi.exit() } })) }))</script>'
)


SCRIPT_PATTERN = re.compile(
    r'<script\b[^>]*>.*?</script>', re.DOTALL | re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Kết quả & lỗi
# ---------------------------------------------------------------------------


@dataclass
class GGConvertResult:
    """Tóm tắt thao tác GG convert."""

    output_html_path: Path | None = None
    transforms_applied: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    input_size: int = 0
    output_html_size: int = 0
    platform_replaced: int = 0
    scripts_seen: int = 0


class GGConvertError(RuntimeError):
    """Raised khi không đủ điều kiện để convert sang GG."""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _replace_target_platform(html: str) -> tuple[str, int]:
    needle = 'targetPlatform:"mintegral"'
    count = html.count(needle)
    if count == 0:
        return html, 0
    return html.replace(needle, 'targetPlatform:"google"', 1), count


def _replace_last_two_scripts(html: str) -> tuple[str, int]:
    matches = list(SCRIPT_PATTERN.finditer(html))
    if len(matches) < 2:
        return html, len(matches)
    updated = html
    last = matches[-1]
    updated = updated[: last.start()] + NEW_SCRIPT_2 + updated[last.end():]
    second_last = matches[-2]
    updated = (
        updated[: second_last.start()]
        + NEW_SCRIPT_1
        + updated[second_last.end():]
    )
    return updated, len(matches)


# ---------------------------------------------------------------------------
# Hàm convert chính
# ---------------------------------------------------------------------------


def convert_html(
    input_path: str | os.PathLike,
    output_dir: str | os.PathLike,
    log: Callable[[str], None] | None = None,
) -> GGConvertResult:
    """Convert 1 file mintegral.html sang build Google.

    Args:
        input_path: file mintegral.html (output của MTG converter).
        output_dir: thư mục đầu ra (sẽ tự tạo). File output đặt tên "index.html".
        log: callback nhận chuỗi log.

    Returns:
        GGConvertResult.

    Raises:
        GGConvertError: nếu không tìm thấy targetPlatform mintegral hoặc
            không đủ 2 thẻ <script> để thay.
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
    # Khớp tool gốc: read text mode (universal newlines -> '\n' trong memory).
    try:
        with input_path.open('r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        with input_path.open('r', encoding='latin-1') as f:
            content = f.read()

    result = GGConvertResult(input_size=len(content))
    _log(f'  Kích thước input: {len(content):,} ký tự')

    output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # BƯỚC 1 – Đổi targetPlatform "mintegral" -> "google"
    # ------------------------------------------------------------------ #
    content, n_platform = _replace_target_platform(content)
    result.platform_replaced = n_platform
    if n_platform == 0:
        raise GGConvertError(
            'Không thấy chuỗi targetPlatform:"mintegral" trong input. '
            'GG converter chỉ chạy được trên output của MTG.'
        )
    result.transforms_applied.append(
        f'1. Đổi targetPlatform "mintegral" -> "google" ({n_platform} match)'
    )
    _log(f'  + Đổi targetPlatform -> "google" ({n_platform} match)')

    # ------------------------------------------------------------------ #
    # BƯỚC 2 – Thay 2 thẻ <script> cuối
    # ------------------------------------------------------------------ #
    content, n_scripts = _replace_last_two_scripts(content)
    result.scripts_seen = n_scripts
    if n_scripts < 2:
        raise GGConvertError(
            f'Không đủ 2 thẻ <script> để thay (chỉ thấy {n_scripts}).'
        )
    result.transforms_applied.append(
        f'2. Thay 2 <script> cuối (trong tổng {n_scripts} thẻ) bằng template Google'
    )
    _log(
        f'  + Thay 2 <script> cuối bằng template Google '
        f'(tổng {n_scripts} thẻ <script> trong file)'
    )

    # ------------------------------------------------------------------ #
    # BƯỚC 3 – Ghi output "index.html"
    # ------------------------------------------------------------------ #
    output_html = output_dir / 'index.html'

    # GG tool gốc dùng open('w', encoding='utf-8') (mặc định Windows -> CRLF).
    # Khớp lại bằng cách normalize tất cả \n -> \r\n.
    content_out = content.replace('\r\n', '\n').replace('\n', '\r\n')
    with output_html.open('wb') as f:
        f.write(content_out.encode('utf-8'))

    result.output_html_path = output_html
    result.output_html_size = len(content)
    result.transforms_applied.append(f'3. Ghi output: {output_html.name}')
    _log(f'Ghi output: {output_html} ({len(content):,} ký tự)')

    return result


if __name__ == '__main__':
    # CLI debug: python gg_converter.py <mintegral.html> [output_dir]
    import sys

    try:
        sys.stdout.reconfigure(encoding='utf-8')  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding='utf-8')  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

    if len(sys.argv) < 2:
        print('Usage: python gg_converter.py <mintegral.html> [output_dir]')
        sys.exit(1)
    in_path = Path(sys.argv[1])
    out_dir = (
        Path(sys.argv[2]) if len(sys.argv) >= 3 else in_path.parent / 'GG_output'
    )
    try:
        r = convert_html(in_path, out_dir, log=print)
    except GGConvertError as exc:
        print('!! Lỗi:', exc)
        sys.exit(2)
    print('--- DONE ---')
    print('HTML output :', r.output_html_path)
    print('Transforms  :', r.transforms_applied)
    if r.warnings:
        print('Warnings    :', r.warnings)
