import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox


NEW_SCRIPT_1 = (
    '<script>window.addEventListener("DOMContentLoaded", (() => { window.devicePixelRatio = 2 })), '
    'window.addEventListener("luna:build", (function () { window.pi.logLoaded(), '
    'window.dispatchEvent(new Event("luna:start")) }))</script>'
)
NEW_SCRIPT_2 = (
    '  <script>window.addEventListener("luna:build", (() => { Bridge.ready((() => { '
    'Luna.Unity.Playable.InstallFullGame = function () { window.ExitApi.exit() } })) }))</script>'
)


def replace_target_platform(html_text: str) -> tuple[str, bool, int]:
    needle = 'targetPlatform:"mintegral"'
    count = html_text.count(needle)
    if count == 0:
        return html_text, False, 0
    return html_text.replace(needle, 'targetPlatform:"google"', 1), True, count


def replace_last_two_scripts(html_text: str) -> tuple[str, bool, int]:
    pattern = re.compile(r"<script\b[^>]*>.*?</script>", re.DOTALL | re.IGNORECASE)
    matches = list(pattern.finditer(html_text))
    if len(matches) < 2:
        return html_text, False, len(matches)

    updated = html_text
    # Replace from end to start to keep spans valid.
    last_match = matches[-1]
    updated = updated[: last_match.start()] + NEW_SCRIPT_2 + updated[last_match.end() :]

    second_last_match = matches[-2]
    updated = updated[: second_last_match.start()] + NEW_SCRIPT_1 + updated[second_last_match.end() :]

    return updated, True, len(matches)


def convert_html_file(file_path: str) -> tuple[bool, str]:
    try:
        with open(file_path, "r", encoding="utf-8") as handle:
            content = handle.read()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="latin-1") as handle:
            content = handle.read()

    content, platform_ok, platform_count = replace_target_platform(content)
    content, scripts_ok, script_count = replace_last_two_scripts(content)

    if not platform_ok or not scripts_ok:
        issues = []
        if not platform_ok:
            issues.append('Không thấy chuỗi targetPlatform:"mintegral".')
        if not scripts_ok:
            issues.append(f"Không đủ 2 thẻ <script> (tìm thấy {script_count}).")
        log_detail = " | ".join(issues)
        _write_log(file_path, False, platform_count, script_count, log_detail)
        return False, log_detail

    folder = os.path.dirname(file_path)
    output_path = os.path.join(folder, "index.html")

    input_abs = os.path.abspath(file_path)
    output_abs = os.path.abspath(output_path)

    if input_abs == output_abs:
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(content)
    else:
        temp_path = os.path.join(folder, "index.html.tmp")
        with open(temp_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temp_path, output_path)

        try:
            os.remove(file_path)
        except OSError as exc:
            try:
                os.chmod(file_path, 0o666)
                os.remove(file_path)
            except OSError as exc2:
                detail = f"Da luu index.html nhung khong xoa duoc file goc. Loi: {exc2}"
                _write_log(file_path, False, platform_count, script_count, detail)
                return False, "Da luu index.html nhung khong xoa duoc file goc."

    _write_log(file_path, True, platform_count, script_count, f"Da luu: {output_path}")
    return True, output_path


def _write_log(file_path: str, success: bool, platform_count: int, script_count: int, detail: str) -> None:
    folder = os.path.dirname(file_path)
    log_path = os.path.join(folder, "ggconvert_log.txt")
    status = "SUCCESS" if success else "FAIL"
    lines = [
        f"File: {file_path}",
        f"Status: {status}",
        f"targetPlatform occurrences: {platform_count}",
        f"script tags found: {script_count}",
        f"Detail: {detail}",
        "-" * 40,
    ]
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def main() -> None:
    root = tk.Tk()
    root.withdraw()

    file_path = filedialog.askopenfilename(
        title="Chọn file HTML",
        filetypes=[("HTML files", "*.html"), ("All files", "*.*")],
    )

    if not file_path:
        return

    success, message = convert_html_file(file_path)
    folder = os.path.dirname(file_path)

    if success:
        os.startfile(folder)
        messagebox.showinfo("Hoàn tất", f"Convert thành công. Đã lưu: {message}", parent=root)
    else:
        messagebox.showerror("Lỗi", f"Convert thất bại. {message}", parent=root)

    root.destroy()


if __name__ == "__main__":
    main()
