"""GUI entry point cho MTG Convert Tool.

Khi chạy .exe, người dùng:
  1. Bấm "Chọn file HTML..." và chỉ vào file Luna playable đã build (unityads).
  2. Tool tự tạo thư mục "Output" cùng cấp với file input và đặt
     mintegral.html + assets/ vào đó.
  3. Log hiển thị real-time, có nút "Mở thư mục output" sau khi xong.
"""

from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# Cho phép import khi chạy bằng PyInstaller (frozen) hoặc trực tiếp
try:
    from mintegra_converter import convert_html, ConvertResult
except ImportError:  # pragma: no cover - fallback khi chạy ngoài src/
    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here))
    from mintegra_converter import convert_html, ConvertResult


APP_TITLE = 'MTG Convert Tool – Luna Playable -> Mintegral'
APP_VERSION = '1.0.0'


class MTGConvertApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry('780x520')
        self.minsize(660, 420)

        self._input_path: Path | None = None
        self._output_dir: Path | None = None
        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        pad = {'padx': 10, 'pady': 6}

        header = ttk.Frame(self)
        header.pack(fill='x', **pad)
        ttk.Label(
            header,
            text='MTG Convert Tool',
            font=('Segoe UI', 16, 'bold'),
        ).pack(side='left')
        ttk.Label(
            header,
            text=f'v{APP_VERSION}',
            font=('Segoe UI', 9),
            foreground='#666',
        ).pack(side='left', padx=(8, 0), pady=(8, 0))

        ttk.Label(
            self,
            text=(
                'Chọn 1 file HTML Luna Playable (build cho unityads) – '
                'tool sẽ tạo thư mục "Output/" cùng cấp với file input và '
                'sinh ra mintegral.html + assets/scripts.js + assets/jsons.js + assets/blobs.js.'
            ),
            wraplength=720,
            justify='left',
            foreground='#444',
        ).pack(fill='x', padx=10)

        # --- Hàng chọn file --------------------------------------------------
        row = ttk.Frame(self)
        row.pack(fill='x', **pad)
        self.path_var = tk.StringVar(value='(chưa chọn file)')
        ttk.Entry(row, textvariable=self.path_var, state='readonly').pack(
            side='left', fill='x', expand=True
        )
        ttk.Button(row, text='Chọn file HTML…', command=self._pick_file).pack(
            side='left', padx=(8, 0)
        )

        # --- Hàng nút action -------------------------------------------------
        actions = ttk.Frame(self)
        actions.pack(fill='x', **pad)
        self.btn_convert = ttk.Button(
            actions,
            text='Convert sang Mintegral',
            command=self._start_convert,
            state='disabled',
        )
        self.btn_convert.pack(side='left')

        self.btn_open_out = ttk.Button(
            actions,
            text='Mở thư mục output',
            command=self._open_output,
            state='disabled',
        )
        self.btn_open_out.pack(side='left', padx=(8, 0))

        ttk.Button(actions, text='Xoá log', command=self._clear_log).pack(
            side='right'
        )

        # --- Log box ---------------------------------------------------------
        log_frame = ttk.LabelFrame(self, text='Log')
        log_frame.pack(fill='both', expand=True, padx=10, pady=(6, 10))

        self.log_text = tk.Text(
            log_frame,
            wrap='word',
            height=18,
            font=('Consolas', 9),
            background='#1e1e1e',
            foreground='#dcdcdc',
            insertbackground='#ffffff',
            state='disabled',
        )
        self.log_text.pack(fill='both', expand=True, padx=4, pady=4)

        sb = ttk.Scrollbar(self.log_text, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')

        # --- Status bar ------------------------------------------------------
        self.status_var = tk.StringVar(value='Sẵn sàng')
        ttk.Label(
            self,
            textvariable=self.status_var,
            anchor='w',
            relief='sunken',
            padding=(8, 4),
        ).pack(fill='x', side='bottom')

        self._log('Sẵn sàng. Bấm "Chọn file HTML…" để bắt đầu.')

    # ------------------------------------------------------------------ helpers
    def _log(self, msg: str) -> None:
        def _append() -> None:
            self.log_text.configure(state='normal')
            self.log_text.insert('end', msg + '\n')
            self.log_text.see('end')
            self.log_text.configure(state='disabled')

        self.after(0, _append)

    def _clear_log(self) -> None:
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', 'end')
        self.log_text.configure(state='disabled')

    def _set_status(self, msg: str) -> None:
        self.after(0, lambda: self.status_var.set(msg))

    # ------------------------------------------------------------------ actions
    def _pick_file(self) -> None:
        path = filedialog.askopenfilename(
            title='Chọn file Luna Playable HTML',
            filetypes=[('HTML files', '*.html;*.htm'), ('All files', '*.*')],
        )
        if not path:
            return
        self._input_path = Path(path)
        self.path_var.set(str(self._input_path))
        self.btn_convert.configure(state='normal')
        self.btn_open_out.configure(state='disabled')
        self._set_status(f'Đã chọn: {self._input_path.name}')
        self._log(f'>> Chọn input: {self._input_path}')

    def _start_convert(self) -> None:
        if self._input_path is None:
            return
        self.btn_convert.configure(state='disabled')
        self.btn_open_out.configure(state='disabled')
        self._set_status('Đang convert…')
        threading.Thread(target=self._run_convert, daemon=True).start()

    def _run_convert(self) -> None:
        assert self._input_path is not None
        try:
            out_dir = self._input_path.parent / 'Output'
            self._log(f'>> Output dir: {out_dir}')
            result: ConvertResult = convert_html(
                self._input_path, out_dir, log=self._log
            )
            self._output_dir = out_dir
            self._log('--- Hoàn tất ---')
            self._log('Transforms áp dụng:')
            for t in result.transforms_applied:
                self._log('  ✓ ' + t)
            if result.warnings:
                self._log('Cảnh báo:')
                for w in result.warnings:
                    self._log('  ! ' + w)
            self._log(
                f'Input  : {result.input_size:,} ký tự\n'
                f'HTML   : {result.output_html_size:,} ký tự '
                f'-> {result.output_html_path}\n'
                f'Assets : {result.total_asset_size:,} bytes '
                f'({len(result.asset_files)} file)'
            )
            self.after(0, lambda: self.btn_open_out.configure(state='normal'))
            self._set_status('Hoàn tất')
            self.after(
                0,
                lambda: messagebox.showinfo(
                    'Thành công',
                    f'Đã convert xong!\n\nOutput: {out_dir}',
                ),
            )
        except Exception as exc:  # noqa: BLE001
            self._log(f'!! Lỗi: {exc}')
            self._set_status('Lỗi')
            self.after(
                0,
                lambda: messagebox.showerror('Lỗi convert', str(exc)),
            )
        finally:
            self.after(
                0, lambda: self.btn_convert.configure(state='normal')
            )

    def _open_output(self) -> None:
        if self._output_dir is None or not self._output_dir.exists():
            return
        try:
            if sys.platform.startswith('win'):
                os.startfile(self._output_dir)  # type: ignore[attr-defined]
            elif sys.platform == 'darwin':
                os.system(f'open "{self._output_dir}"')
            else:
                os.system(f'xdg-open "{self._output_dir}"')
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror('Lỗi', f'Không mở được thư mục:\n{exc}')


def main() -> None:
    app = MTGConvertApp()
    app.mainloop()


if __name__ == '__main__':
    main()
