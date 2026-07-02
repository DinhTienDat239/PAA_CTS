"""Core converter: Luna Playable HTML -> AppLovin (AL) build.

Port từ `ALConvertTool/convert.py` (giữ NGUYÊN logic gốc), được refactor
thành 1 hàm `convert_html(...)` có cùng chữ ký với `mintegra_converter`
để GUI có thể gọi đồng nhất.

Logic AL convert (3 bước):
  1. Quét toàn bộ thẻ <script>...</script>, XOÁ:
     a. Bất cứ <script> nào chứa 'insertYourRemoteDebugging'.
     b. Bất cứ <script data-startup-only> nào có chứa URL http(s)://
        (= script load asset từ CDN bên ngoài – AL không cho phép).
     => Bắt buộc cả 2 loại đều phải có ≥1 match, nếu không -> lỗi.
  2. Strip mọi URL hard-coded trong attributes:
     - Chuỗi "link"  -> ""
     - Chuỗi "http(s)://..."  -> ""
     - href="..."  -> href=""
  3. Ghi file output (mặc định: <basename>_AL.html).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


SCRIPT_PATTERN = re.compile(
    r'<script\b[^>]*>.*?</script>', re.DOTALL | re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Kết quả convert
# ---------------------------------------------------------------------------


@dataclass
class ALConvertResult:
    """Tóm tắt thao tác AL convert (dùng cho GUI hiển thị log)."""

    output_html_path: Path | None = None
    transforms_applied: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    input_size: int = 0
    output_html_size: int = 0
    removed_debug_scripts: int = 0
    removed_cdn_scripts: int = 0
    stripped_links: int = 0


class ALConvertError(RuntimeError):
    """Raised khi không đủ điều kiện convert (thiếu 1 trong 2 loại script)."""


# ---------------------------------------------------------------------------
# Hàm convert chính
# ---------------------------------------------------------------------------


def convert_html(
    input_path: str | os.PathLike,
    output_dir: str | os.PathLike,
    log: Callable[[str], None] | None = None,
    output_filename: str | None = None,
) -> ALConvertResult:
    """Convert 1 file Luna Playable HTML sang build AppLovin.

    Args:
        input_path: file HTML nguồn.
        output_dir: thư mục đầu ra (tự tạo).
        log: callback nhận chuỗi log (tuỳ chọn).
        output_filename: tên file output (mặc định "<basename>_AL.html").

    Returns:
        ALConvertResult chứa thông tin convert.

    Raises:
        ALConvertError: nếu không tìm thấy đủ 2 loại script bắt buộc.
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
    # AL tool gốc dùng read_text mặc định (universal newlines -> LF).
    # Giữ NGUYÊN hành vi để byte-output ổn định.
    with input_path.open('r', encoding='utf-8') as f:
        content = f.read()
    result = ALConvertResult(input_size=len(content))
    _log(f'  Kích thước input: {len(content):,} ký tự')

    output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # BƯỚC 1 – Quét + xoá 2 loại <script>
    # ------------------------------------------------------------------ #
    count_removed_debug = 0
    count_removed_cdn = 0

    def _replacer(match: re.Match[str]) -> str:
        nonlocal count_removed_debug, count_removed_cdn
        text = match.group(0)
        if 'insertYourRemoteDebugging' in text:
            count_removed_debug += 1
            return ''
        if 'data-startup-only' in text and re.search(
            r'https?://', text, re.IGNORECASE
        ):
            count_removed_cdn += 1
            return ''
        return text

    content = SCRIPT_PATTERN.sub(_replacer, content)
    result.removed_debug_scripts = count_removed_debug
    result.removed_cdn_scripts = count_removed_cdn

    _log(
        f'  + Xoá {count_removed_debug} script remote-debug, '
        f'{count_removed_cdn} script data-startup-only chứa URL CDN'
    )

    if count_removed_debug == 0 or count_removed_cdn == 0:
        # Match đúng hành vi gốc: bắt buộc cả 2 đều phải > 0.
        raise ALConvertError(
            'Không tìm thấy hoặc không thể xoá đủ 2 loại script yêu cầu '
            "(insertYourRemoteDebugging và <script data-startup-only> "
            'chứa link http/https).'
        )

    result.transforms_applied.append(
        f'1. Xoá {count_removed_debug} script remote-debug + '
        f'{count_removed_cdn} script CDN data-startup-only'
    )

    # ------------------------------------------------------------------ #
    # BƯỚC 2 – Strip mọi URL hard-coded trong attributes
    # ------------------------------------------------------------------ #
    n_links = 0

    # 2a. Literal "link" và 'link'
    content, n = re.subn(r'"link"', '""', content)
    n_links += n
    content, n = re.subn(r"'link'", "''", content)
    n_links += n

    # 2b. Absolute URL trong dấu nháy kép / nháy đơn
    content, n = re.subn(
        r'"https?://[^"]+"', '""', content, flags=re.IGNORECASE
    )
    n_links += n
    content, n = re.subn(
        r"'https?://[^']+'", "''", content, flags=re.IGNORECASE
    )
    n_links += n

    # 2c. href="..." và href='...' (để chắc chắn)
    content, n = re.subn(
        r'(href\s*=\s*)"[^"]+"', r'\1""', content, flags=re.IGNORECASE
    )
    n_links += n
    content, n = re.subn(
        r"(href\s*=\s*)'[^']+'", r"\1''", content, flags=re.IGNORECASE
    )
    n_links += n

    result.stripped_links = n_links
    if n_links > 0:
        result.transforms_applied.append(
            f'2. Strip {n_links} URL/href hard-coded thành ""'
        )
        _log(f'  + Strip {n_links} link/href trong attributes')
    else:
        result.warnings.append('Không tìm thấy URL hard-coded nào để strip')

    # ------------------------------------------------------------------ #
    # BƯỚC 3 – Ghi file output
    # ------------------------------------------------------------------ #
    if output_filename is None:
        output_filename = f'{input_path.stem}_AL{input_path.suffix or ".html"}'
    output_html = output_dir / output_filename

    # AL tool gốc dùng `open('w', encoding='utf-8')` mà không có newline=...,
    # nên trên Windows Python sẽ translate '\n' -> '\r\n' khi ghi. Muốn
    # BYTE-PERFECT khớp đầu ra của AL tool gốc, phải làm điều tương tự.
    content_out = content.replace('\r\n', '\n').replace('\n', '\r\n')
    with output_html.open('wb') as f:
        f.write(content_out.encode('utf-8'))

    result.output_html_path = output_html
    result.output_html_size = len(content)
    result.transforms_applied.append(f'3. Ghi output: {output_html.name}')
    _log(f'Ghi output: {output_html} ({len(content):,} ký tự)')

    return result


if __name__ == '__main__':
    # CLI debug: python al_converter.py <input.html> [output_dir]
    import sys

    try:
        sys.stdout.reconfigure(encoding='utf-8')  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding='utf-8')  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

    if len(sys.argv) < 2:
        print('Usage: python al_converter.py <input.html> [output_dir]')
        sys.exit(1)
    in_path = Path(sys.argv[1])
    out_dir = (
        Path(sys.argv[2]) if len(sys.argv) >= 3 else in_path.parent / 'Output'
    )
    try:
        r = convert_html(in_path, out_dir, log=print)
    except ALConvertError as exc:
        print('!! Lỗi:', exc)
        sys.exit(2)
    print('--- DONE ---')
    print('HTML output :', r.output_html_path)
    print('Transforms  :', r.transforms_applied)
    if r.warnings:
        print('Warnings    :', r.warnings)
