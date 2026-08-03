"""GUI entry point cho CTS Convert Tool.

Tool tích hợp 5 chức năng convert:
  - AL  : Luna Playable -> AppLovin build (strip CDN + remote-debug).
          Tuỳ chọn: tạo bản sao `_tracking` inject AppLovin Analytics Bridge
          (Có Tracking / Có Tracking kèm Banner).
  - MTG : Luna Playable (unityads) -> Mintegral build.
  - GG  : Mintegral build  -> Google build (dùng output của MTG làm input).
  - META: Luna Playable (unityads) -> Meta (Facebook) build.
  - MLC : Luna Playable (unityads) -> Moloco build.

Cách dùng .exe:
  1. Bấm "Chọn file HTML..." -> chọn file Luna playable gốc.
  2. Tick các network muốn convert (AL / MTG / GG / META / MLC).
     ! Tick GG sẽ tự động tick MTG (vì GG cần output của MTG).
     ! Dưới AL: tick "Có Tracking" / "Có Tracking kèm Banner" để sinh
       thêm `<basename>_AL_tracking.html` sau khi AL thành công.
  3. Bấm "Convert".
  4. Trong thư mục Output/, mỗi network 1 subfolder:
       Output/AL/<basename>_AL.html
       Output/AL/<basename>_AL_tracking.html   (nếu tick Tracking)
       Output/MTG/mintegral.html + Output/MTG/assets/*.js
       Output/GG/index.html      + Output/GG/assets/*.js  (copy từ MTG)
       Output/META/<basename>_Meta.html
       Output/MLC/<basename>_MLC.html
"""

from __future__ import annotations

import os
import shutil
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# Hỗ trợ import khi chạy frozen (PyInstaller) và khi chạy trực tiếp
try:
    from mintegra_converter import convert_html as mtg_convert
    from al_converter import convert_html as al_convert, ALConvertError
    from al_tracking_bridge import (
        bridge_html as al_bridge,
        ALTrackingBridgeError,
    )
    from gg_converter import convert_html as gg_convert, GGConvertError
    from meta_converter import convert_html as meta_convert, MetaConvertError
    from mlc_converter import convert_html as mlc_convert, MLCConvertError
except ImportError:  # pragma: no cover - fallback khi chạy ngoài src/
    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here))
    from mintegra_converter import convert_html as mtg_convert  # type: ignore[no-redef]
    from al_converter import convert_html as al_convert, ALConvertError  # type: ignore[no-redef]
    from al_tracking_bridge import (  # type: ignore[no-redef]
        bridge_html as al_bridge,
        ALTrackingBridgeError,
    )
    from gg_converter import convert_html as gg_convert, GGConvertError  # type: ignore[no-redef]
    from meta_converter import convert_html as meta_convert, MetaConvertError  # type: ignore[no-redef]
    from mlc_converter import convert_html as mlc_convert, MLCConvertError  # type: ignore[no-redef]


APP_TITLE = 'CTS Convert Tool – Luna Playable -> AL / MTG / GG / Meta / MLC'
APP_VERSION = '1.3.0'

# Danh sách network hỗ trợ. Dễ mở rộng sau (chỉ cần thêm 1 dòng).
NETWORKS: list[tuple[str, str]] = [
    ('AL',   'AppLovin  (strip CDN, remote-debug, link cứng)'),
    ('MTG',  'Mintegral (tách bundle + đổi SDK adapter)'),
    ('GG',   'Google    (dùng output MTG; tick GG sẽ tự tick MTG)'),
    ('META', 'Meta      (đổi targetPlatform "facebook" + FbPlayableAd adapter)'),
    ('MLC',  'Moloco    (đổi targetPlatform "moloco"   + FbPlayableAd adapter)'),
]

# Một số network phụ thuộc network khác (sẽ auto-tick khi tick network này).
NETWORK_DEPENDENCIES: dict[str, list[str]] = {
    'GG': ['MTG'],
}

# Thứ tự ưu tiên khi convert: MTG trước, GG sau (vì GG dùng output MTG).
# META và MLC độc lập, có thể chạy ở bất kỳ vị trí nào.
NETWORK_ORDER: list[str] = ['AL', 'MTG', 'GG', 'META', 'MLC']


class CTSConvertApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry('820x600')
        self.minsize(700, 480)

        self._input_path: Path | None = None
        self._output_root: Path | None = None
        self._network_vars: dict[str, tk.BooleanVar] = {}
        # Tuỳ chọn AL tracking (chỉ áp dụng khi AL convert thành công).
        self._al_tracking_var = tk.BooleanVar(value=False)
        self._al_tracking_banner_var = tk.BooleanVar(value=False)
        self._al_opt_checks: list[ttk.Checkbutton] = []
        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        pad = {'padx': 10, 'pady': 6}

        # --- Header ---------------------------------------------------------
        header = ttk.Frame(self)
        header.pack(fill='x', **pad)
        ttk.Label(
            header,
            text='CTS Convert Tool',
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
                'Chọn 1 file HTML Luna Playable, tick các mạng quảng cáo cần '
                'convert (AL / MTG / GG / Meta / MLC), rồi bấm "Convert". '
                'Tool sẽ tạo thư mục "Output/" cùng cấp với file input, '
                'mỗi network 1 subfolder. Dưới AL có thêm tuỳ chọn Tracking '
                '(inject AppLovin Analytics Bridge vào bản sao _tracking).'
            ),
            wraplength=780,
            justify='left',
            foreground='#444',
        ).pack(fill='x', padx=10)

        # --- Hàng chọn file -------------------------------------------------
        row = ttk.Frame(self)
        row.pack(fill='x', **pad)
        self.path_var = tk.StringVar(value='(chưa chọn file)')
        ttk.Entry(row, textvariable=self.path_var, state='readonly').pack(
            side='left', fill='x', expand=True
        )
        ttk.Button(row, text='Chọn file HTML…', command=self._pick_file).pack(
            side='left', padx=(8, 0)
        )

        # --- Network selection ----------------------------------------------
        net_frame = ttk.LabelFrame(self, text='Chọn network để convert')
        net_frame.pack(fill='x', padx=10, pady=(6, 6))
        for key, desc in NETWORKS:
            var = tk.BooleanVar(value=True)
            self._network_vars[key] = var
            ttk.Checkbutton(
                net_frame,
                text=f'{key}  —  {desc}',
                variable=var,
            ).pack(anchor='w', padx=8, pady=2)

            # Tuỳ chọn AL Tracking nằm ngay dưới checkbox AL.
            if key == 'AL':
                al_opts = ttk.Frame(net_frame)
                al_opts.pack(fill='x', padx=28, pady=(0, 4))
                cb_track = ttk.Checkbutton(
                    al_opts,
                    text='Có Tracking  (tạo bản *_AL_tracking.html, production)',
                    variable=self._al_tracking_var,
                )
                cb_track.pack(anchor='w')
                cb_banner = ttk.Checkbutton(
                    al_opts,
                    text=(
                        'Có Tracking kèm Banner  '
                        '(bản *_AL_tracking.html + overlay QA)'
                    ),
                    variable=self._al_tracking_banner_var,
                )
                cb_banner.pack(anchor='w')
                self._al_opt_checks = [cb_track, cb_banner]

        # Hook: tick network có dependency -> auto-tick dependency.
        for key, deps in NETWORK_DEPENDENCIES.items():
            var = self._network_vars[key]

            def _on_toggle(*_args: object, _k: str = key, _deps: list[str] = deps) -> None:
                if self._network_vars[_k].get():
                    for dep in _deps:
                        if not self._network_vars[dep].get():
                            self._network_vars[dep].set(True)
                            self._log(
                                f'>> Auto-tick {dep} (do {_k} cần output của {dep})'
                            )

            var.trace_add('write', _on_toggle)

        # Hook AL: tắt AL → tắt + disable tracking opts; bật lại → enable.
        # Banner tick → auto-tick Tracking (banner là biến thể của tracking).
        # Tracking opts tick khi AL tắt → auto-tick AL.
        self._network_vars['AL'].trace_add('write', self._on_al_network_toggle)
        self._al_tracking_var.trace_add('write', self._on_al_tracking_toggle)
        self._al_tracking_banner_var.trace_add(
            'write', self._on_al_tracking_banner_toggle
        )
        self._sync_al_tracking_enabled()

        # --- Hàng nút action ------------------------------------------------
        actions = ttk.Frame(self)
        actions.pack(fill='x', **pad)
        self.btn_convert = ttk.Button(
            actions,
            text='Convert',
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

        # --- Log box --------------------------------------------------------
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

        # --- Status bar -----------------------------------------------------
        self.status_var = tk.StringVar(value='Sẵn sàng')
        ttk.Label(
            self,
            textvariable=self.status_var,
            anchor='w',
            relief='sunken',
            padding=(8, 4),
        ).pack(fill='x', side='bottom')

        self._log('Sẵn sàng. Bấm "Chọn file HTML…" để bắt đầu.')

    # ------------------------------------------------------------------ AL tracking UI hooks
    def _sync_al_tracking_enabled(self) -> None:
        """Enable/disable 2 tickbox tracking theo trạng thái AL."""
        al_on = self._network_vars['AL'].get()
        state = 'normal' if al_on else 'disabled'
        for cb in self._al_opt_checks:
            cb.configure(state=state)
        if not al_on:
            # Tránh cascade log khi đang sync: tắt opts im lặng.
            if self._al_tracking_banner_var.get():
                self._al_tracking_banner_var.set(False)
            if self._al_tracking_var.get():
                self._al_tracking_var.set(False)

    def _on_al_network_toggle(self, *_args: object) -> None:
        self._sync_al_tracking_enabled()

    def _on_al_tracking_toggle(self, *_args: object) -> None:
        if self._al_tracking_var.get():
            if not self._network_vars['AL'].get():
                self._network_vars['AL'].set(True)
                self._log('>> Auto-tick AL (do bật Có Tracking)')
        else:
            # Tắt Tracking → tắt Banner (banner phụ thuộc tracking).
            if self._al_tracking_banner_var.get():
                self._al_tracking_banner_var.set(False)

    def _on_al_tracking_banner_toggle(self, *_args: object) -> None:
        if self._al_tracking_banner_var.get():
            if not self._network_vars['AL'].get():
                self._network_vars['AL'].set(True)
                self._log('>> Auto-tick AL (do bật Tracking kèm Banner)')
            if not self._al_tracking_var.get():
                self._al_tracking_var.set(True)
                self._log('>> Auto-tick Có Tracking (do bật Tracking kèm Banner)')

    def _al_tracking_options(self) -> tuple[bool, bool]:
        """Trả về (want_tracking, debug_banner). Banner chỉ có nghĩa khi tracking bật."""
        want = bool(self._al_tracking_var.get())
        banner = bool(self._al_tracking_banner_var.get()) and want
        return want, banner

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

    def _selected_networks(self) -> list[str]:
        """Lấy list network user đã tick, ÁP DỤNG dependency + đúng thứ tự convert."""
        picked: set[str] = {k for k, v in self._network_vars.items() if v.get()}
        # Bổ sung dependency (vd. GG -> MTG)
        for key in list(picked):
            for dep in NETWORK_DEPENDENCIES.get(key, []):
                picked.add(dep)
        # Sắp theo NETWORK_ORDER
        return [k for k in NETWORK_ORDER if k in picked]

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
        nets = self._selected_networks()
        if not nets:
            messagebox.showwarning(
                'Chưa chọn network', 'Bạn cần tick ít nhất 1 network.'
            )
            return
        self.btn_convert.configure(state='disabled')
        self.btn_open_out.configure(state='disabled')
        self._set_status('Đang convert…')
        threading.Thread(
            target=self._run_convert, args=(nets,), daemon=True
        ).start()

    def _run_convert(self, networks: list[str]) -> None:
        assert self._input_path is not None
        output_root = self._input_path.parent / 'Output'
        self._output_root = output_root
        self._log(f'>> Output root: {output_root}')

        successes: list[str] = []
        failures: list[tuple[str, str]] = []
        # Lưu output MTG để GG có thể dùng làm input
        mtg_html_path: Path | None = None
        mtg_assets_dir: Path | None = None

        for key in networks:
            self._log('')
            self._log(f'=== [{key}] bắt đầu ===')
            sub_dir = output_root / key
            try:
                if key == 'MTG':
                    res = mtg_convert(
                        self._input_path, sub_dir, log=self._log
                    )
                    mtg_html_path = res.output_html_path
                    mtg_assets_dir = res.assets_dir
                    self._log_mtg_result(res)
                elif key == 'AL':
                    res = al_convert(
                        self._input_path, sub_dir, log=self._log
                    )
                    self._log_al_result(res)
                    # Sau AL thành công: tuỳ chọn tạo bản sao *_tracking.
                    want_tracking, debug_banner = self._al_tracking_options()
                    if want_tracking:
                        if res.output_html_path is None or not res.output_html_path.exists():
                            raise ALTrackingBridgeError(
                                'AL convert không có file output để bridge tracking.'
                            )
                        self._log('')
                        self._log('=== [AL Tracking] bắt đầu ===')
                        bridge_res = al_bridge(
                            res.output_html_path,
                            sub_dir,
                            log=self._log,
                            debug_banner=debug_banner,
                        )
                        self._log_al_tracking_result(bridge_res)
                        self._log('=== [AL Tracking] hoàn tất ===')
                elif key == 'GG':
                    if mtg_html_path is None or not mtg_html_path.exists():
                        raise GGConvertError(
                            'Thiếu output MTG để dùng làm input cho GG. '
                            'Đảm bảo MTG được tick và convert thành công trước.'
                        )
                    res = gg_convert(mtg_html_path, sub_dir, log=self._log)
                    # Copy assets/ từ MTG sang GG để playable Google chạy được
                    if mtg_assets_dir is not None and mtg_assets_dir.exists():
                        dst_assets = sub_dir / 'assets'
                        if dst_assets.exists():
                            shutil.rmtree(dst_assets)
                        shutil.copytree(mtg_assets_dir, dst_assets)
                        self._log(
                            f'  + Copy assets MTG -> GG ({len(list(dst_assets.iterdir()))} file)'
                        )
                    self._log_gg_result(res)
                elif key == 'META':
                    res = meta_convert(
                        self._input_path, sub_dir, log=self._log
                    )
                    self._log_meta_result(res)
                elif key == 'MLC':
                    res = mlc_convert(
                        self._input_path, sub_dir, log=self._log
                    )
                    self._log_mlc_result(res)
                else:
                    raise RuntimeError(f'Network không được hỗ trợ: {key}')
                successes.append(key)
                self._log(f'=== [{key}] hoàn tất ===')
            except (
                ALConvertError,
                ALTrackingBridgeError,
                GGConvertError,
                MetaConvertError,
                MLCConvertError,
            ) as exc:
                msg = str(exc)
                self._log(f'!! [{key}] LỖI: {msg}')
                failures.append((key, msg))
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                self._log(f'!! [{key}] LỖI: {msg}')
                failures.append((key, msg))

        # --- Tổng kết --------------------------------------------------------
        self._log('')
        self._log('================ TỔNG KẾT ================')
        for k in successes:
            self._log(f'  ✓ {k}: thành công -> {output_root / k}')
        for k, msg in failures:
            self._log(f'  ✗ {k}: {msg}')

        if successes:
            self.after(0, lambda: self.btn_open_out.configure(state='normal'))
        self._set_status(
            f'Hoàn tất ({len(successes)} OK / {len(failures)} lỗi)'
        )

        # Popup tóm tắt
        if failures and not successes:
            self.after(
                0,
                lambda: messagebox.showerror(
                    'Convert thất bại',
                    '\n'.join(f'[{k}] {m}' for k, m in failures),
                ),
            )
        elif failures:
            self.after(
                0,
                lambda: messagebox.showwarning(
                    'Convert có lỗi',
                    'Thành công: ' + ', '.join(successes)
                    + '\n\nLỗi:\n'
                    + '\n'.join(f'  [{k}] {m}' for k, m in failures),
                ),
            )
        else:
            self.after(
                0,
                lambda: messagebox.showinfo(
                    'Thành công',
                    f'Đã convert xong {len(successes)} network!\n\n'
                    f'Output: {output_root}',
                ),
            )

        self.after(0, lambda: self.btn_convert.configure(state='normal'))

    # ------------------------------------------------------------------ result formatters
    def _log_mtg_result(self, res: object) -> None:
        # res: mintegra_converter.ConvertResult – tránh import type khắp nơi
        self._log('  Transforms áp dụng:')
        for t in getattr(res, 'transforms_applied', []):
            self._log('    ✓ ' + t)
        warns = getattr(res, 'warnings', [])
        if warns:
            self._log('  Cảnh báo:')
            for w in warns:
                self._log('    ! ' + w)
        self._log(
            f'  HTML : {res.output_html_size:,} ký tự -> {res.output_html_path}'  # type: ignore[attr-defined]
        )
        self._log(
            f'  Assets: {res.total_asset_size:,} bytes '  # type: ignore[attr-defined]
            f'({len(res.asset_files)} file)'  # type: ignore[attr-defined]
        )

    def _log_al_result(self, res: object) -> None:
        self._log('  Transforms áp dụng:')
        for t in getattr(res, 'transforms_applied', []):
            self._log('    ✓ ' + t)
        warns = getattr(res, 'warnings', [])
        if warns:
            self._log('  Cảnh báo:')
            for w in warns:
                self._log('    ! ' + w)
        self._log(
            f'  Removed debug-script : {res.removed_debug_scripts}'  # type: ignore[attr-defined]
        )
        self._log(
            f'  Removed CDN-script   : {res.removed_cdn_scripts}'  # type: ignore[attr-defined]
        )
        self._log(
            f'  Stripped links/href  : {res.stripped_links}'  # type: ignore[attr-defined]
        )
        self._log(
            f'  HTML : {res.output_html_size:,} ký tự -> {res.output_html_path}'  # type: ignore[attr-defined]
        )

    def _log_al_tracking_result(self, res: object) -> None:
        self._log('  Transforms áp dụng:')
        for t in getattr(res, 'transforms_applied', []):
            self._log('    ✓ ' + t)
        warns = getattr(res, 'warnings', [])
        if warns:
            self._log('  Cảnh báo:')
            for w in warns:
                self._log('    ! ' + w)
        banner = getattr(res, 'debug_banner', False)
        self._log(
            f'  Debug banner         : {"ON (QA)" if banner else "OFF (production)"}'
        )
        self._log(
            f'  Removed old bridge   : {getattr(res, "removed_old_bridge", False)}'
        )
        self._log(
            f'  HTML : {res.output_html_size:,} ký tự -> {res.output_html_path}'  # type: ignore[attr-defined]
        )

    def _log_gg_result(self, res: object) -> None:
        # res: gg_converter.GGConvertResult
        self._log('  Transforms áp dụng:')
        for t in getattr(res, 'transforms_applied', []):
            self._log('    ✓ ' + t)
        warns = getattr(res, 'warnings', [])
        if warns:
            self._log('  Cảnh báo:')
            for w in warns:
                self._log('    ! ' + w)
        self._log(
            f'  Scripts seen         : {res.scripts_seen}'  # type: ignore[attr-defined]
        )
        self._log(
            f'  Platform replaced    : {res.platform_replaced}'  # type: ignore[attr-defined]
        )
        self._log(
            f'  HTML : {res.output_html_size:,} ký tự -> {res.output_html_path}'  # type: ignore[attr-defined]
        )

    def _log_meta_result(self, res: object) -> None:
        # res: meta_converter.MetaConvertResult
        self._log('  Transforms áp dụng:')
        for t in getattr(res, 'transforms_applied', []):
            self._log('    ✓ ' + t)
        warns = getattr(res, 'warnings', [])
        if warns:
            self._log('  Cảnh báo:')
            for w in warns:
                self._log('    ! ' + w)
        self._log(
            f'  Platform replaced    : {res.platform_replaced}'  # type: ignore[attr-defined]
        )
        self._log(
            f'  pi.apply() cleaned   : {res.pi_apply_cleaned}'  # type: ignore[attr-defined]
        )
        self._log(
            f'  Scripts seen         : {res.scripts_seen}'  # type: ignore[attr-defined]
        )
        self._log(
            f'  HTML : {res.output_html_size:,} ký tự -> {res.output_html_path}'  # type: ignore[attr-defined]
        )

    def _log_mlc_result(self, res: object) -> None:
        # res: mlc_converter.MLCConvertResult
        self._log('  Transforms áp dụng:')
        for t in getattr(res, 'transforms_applied', []):
            self._log('    ✓ ' + t)
        warns = getattr(res, 'warnings', [])
        if warns:
            self._log('  Cảnh báo:')
            for w in warns:
                self._log('    ! ' + w)
        self._log(
            f'  Platform replaced    : {res.platform_replaced}'  # type: ignore[attr-defined]
        )
        self._log(
            f'  pi.apply() cleaned   : {res.pi_apply_cleaned}'  # type: ignore[attr-defined]
        )
        self._log(
            f'  Scripts seen         : {res.scripts_seen}'  # type: ignore[attr-defined]
        )
        self._log(
            f'  HTML : {res.output_html_size:,} ký tự -> {res.output_html_path}'  # type: ignore[attr-defined]
        )

    # ------------------------------------------------------------------ open output
    def _open_output(self) -> None:
        if self._output_root is None or not self._output_root.exists():
            return
        try:
            if sys.platform.startswith('win'):
                os.startfile(self._output_root)  # type: ignore[attr-defined]
            elif sys.platform == 'darwin':
                os.system(f'open "{self._output_root}"')
            else:
                os.system(f'xdg-open "{self._output_root}"')
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror('Lỗi', f'Không mở được thư mục:\n{exc}')


def main() -> None:
    app = CTSConvertApp()
    app.mainloop()


if __name__ == '__main__':
    main()
