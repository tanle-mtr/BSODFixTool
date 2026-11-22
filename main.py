#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蓝屏代码查询与修复工具 · 应用入口。

离线单文件：所有蓝屏数据内置于可执行文件，运行期不发起任何网络请求。
零依赖：不需要 Python / .NET / 第三方运行库，可在 64 位 WinPE / WinRE 运行。
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import repair_engine as engine
from app.theme import T, init_fonts, mono, ui
from app.views import BrowserPanel, DetailPanel, RepairBench
from app.widgets import AnimatedButton, Card, Mascot, Pill, RichText, round_rect

APP_TITLE = "蓝屏代码查询与修复工具"
APP_VERSION = "2.0"
SOURCE_SITE = "https://www.3z9w.com/bsod"


def resource_path(*parts: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS")) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    return base.joinpath(*parts)


def apply_window_icon(win: tk.Misc) -> None:
    """把软件图标显式挂到窗口上。

    PyInstaller 的 --icon 只改 EXE 文件图标；Tk 默认仍会用自己的图标，
    导致标题栏与任务栏显示成默认图标，所以这里必须显式设置。
    """
    ico = resource_path("app", "assets", "app_icon.ico")
    png = resource_path("app", "assets", "app_icon.png")
    if ico.exists():
        for setter in ("iconbitmap", "wm_iconbitmap"):
            try:
                getattr(win, setter)(str(ico))
            except tk.TclError:
                pass
    if png.exists():
        try:
            photo = tk.PhotoImage(file=str(png))
            win._app_icon_photo = photo  # 保持引用，避免被垃圾回收
            win.iconphoto(True, photo)
        except tk.TclError:
            pass


class ConfirmOverlay(tk.Toplevel):
    """破坏性操作二次确认：逐条列出将要执行的命令与风险。"""

    def __init__(self, master, *, title: str, lines: list[tuple[str, str]], danger: bool = True):
        super().__init__(master)
        self.title(title)
        self.configure(bg=T.bg)
        self.transient(master.winfo_toplevel())
        self.resizable(False, False)
        self.result = False
        apply_window_icon(self)

        card = Card(self, bg=T.surface)
        card.pack(fill="both", expand=True, padx=2, pady=2)
        tk.Label(card, text=title, bg=T.surface, fg=T.danger if danger else T.text,
                 font=ui(14, "bold")).pack(anchor="w", padx=22, pady=(20, 8))
        tk.Label(card, text="以下操作会修改磁盘上的引导与文件系统，请确认已完成数据备份。",
                 bg=T.surface, fg=T.text_dim, font=ui(11)).pack(anchor="w", padx=22)
        body = tk.Frame(card, bg=T.surface)
        body.pack(fill="both", expand=True, padx=22, pady=(14, 4))
        for tag, text in lines:
            color = T.warning if tag == "warn" else (T.danger if tag == "danger" else T.text_dim)
            tk.Label(body, text=text, bg=T.surface, fg=color, font=mono(10) if tag == "cmd" else ui(10),
                     anchor="w", justify="left", wraplength=640).pack(fill="x", pady=2)
        actions = tk.Frame(card, bg=T.surface)
        actions.pack(fill="x", padx=22, pady=(16, 20))
        AnimatedButton(actions, text="取消", command=self._cancel, variant="ghost", font=ui(11),
                       height=36, padx=18).pack(side="right")
        AnimatedButton(actions, text="确认执行", command=self._accept, variant="danger", font=ui(11, "bold"),
                       height=36, padx=18).pack(side="right", padx=(0, 10))
        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + (master.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.grab_set()

    def _accept(self) -> None:
        self.result = True
        self.destroy()

    def _cancel(self) -> None:
        self.result = False
        self.destroy()


class ReportWindow(tk.Toplevel):
    """修复报告窗口。"""

    def __init__(self, master, report: str):
        super().__init__(master)
        self.title("修复报告")
        self.configure(bg=T.bg)
        self.geometry("880x600")
        self.transient(master.winfo_toplevel())
        apply_window_icon(self)
        text = RichText(self, bg=T.surface, font=mono(10))
        text.pack(fill="both", expand=True, padx=14, pady=(14, 8))
        text.write([("mono", report)], clear=True)
        bar = tk.Frame(self, bg=T.bg)
        bar.pack(fill="x", padx=14, pady=(0, 14))
        AnimatedButton(bar, text="保存为文件", command=self._save, variant="ghost", font=ui(11),
                       height=34, padx=16).pack(side="left")
        AnimatedButton(bar, text="关闭", command=self.destroy, variant="primary", font=ui(11),
                       height=34, padx=16).pack(side="right")
        self._report = report

    def _save(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self, title="保存修复报告", defaultextension=".txt",
            initialfile=f"BSODFix-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if path:
            Path(path).write_text(self._report, encoding="utf-8")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} v{APP_VERSION}")
        screen_h = self.winfo_screenheight()
        window_h = min(880, max(700, screen_h - 90))
        self.geometry(f"1340x{window_h}+30+20")
        self.minsize(1180, min(700, window_h))
        self.configure(bg=T.bg)

        self.fonts = init_fonts(self)
        apply_window_icon(self)
        self._build_styles()

        self.data = self._load_data()
        self.entries: list[dict] = self.data.get("entries", [])
        self.by_code = {e.get("code", "").upper(): e for e in self.entries}
        self.current: dict | None = None
        self.queue: queue.Queue = queue.Queue()
        self.running = False
        self.volumes: list[engine.Volume] = []
        self.efi_volume_number = ""
        self.ctx = engine.Context(winpe=engine.detect_winpe())
        self._bench: RepairBench | None = None

        self.asset_dir = resource_path("app", "assets")
        self._build_ui()
        self._refresh_list()
        self._scan_environment(quiet=True)
        self.after(120, self._poll_queue)
        self.bind("<Escape>", lambda _e: self._close_bench())
        self.bind("<Control-f>", self._focus_search)
        self.bind("<Control-F>", self._focus_search)

    # ------------------------------------------------------------------ #
    # 数据与样式
    # ------------------------------------------------------------------ #
    def _load_data(self) -> dict:
        path = resource_path("bsod_data.json")
        if not path.exists():
            raise FileNotFoundError(f"找不到内置数据文件：{path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not data.get("entries"):
            raise ValueError("内置数据为空")
        return data

    def _build_styles(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=T.bg, foreground=T.text, fieldbackground=T.surface_alt)
        style.configure("TCombobox", fieldbackground=T.surface_alt, background=T.surface_alt,
                        foreground=T.text, arrowcolor=T.text_dim, bordercolor=T.border,
                        lightcolor=T.border, darkcolor=T.border, padding=5, font=ui(10))
        style.map("TCombobox", fieldbackground=[("readonly", T.surface_alt)],
                  foreground=[("readonly", T.text)], bordercolor=[("focus", T.primary)])
        style.configure("Dark.TCheckbutton", background=T.bg, foreground=T.text_dim, font=ui(10))
        style.map("Dark.TCheckbutton", background=[("active", T.bg)], foreground=[("active", T.text)])
        style.configure("Vertical.TScrollbar", background=T.surface_alt, troughcolor=T.bg,
                        bordercolor=T.bg, arrowcolor=T.text_faint, width=10)
        style.map("Vertical.TScrollbar", background=[("active", T.border)])

    # ------------------------------------------------------------------ #
    # 布局
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_appbar()
        body = tk.Frame(self, bg=T.bg)
        body.grid(row=1, column=0, sticky="nsew")
        self.body = body

        self.browser = BrowserPanel(body, on_select=self._select_code, on_query=self._on_query)
        self.browser.pack(side="left", fill="y", padx=(16, 8), pady=14)
        self.browser.set_categories(
            ["全部分类"] + [c.get("name", "") for c in self.data.get("categories", []) if c.get("name")],
            "全部分类")
        self.detail = DetailPanel(body, on_open_repair=self._open_bench, asset_dir=self.asset_dir)
        self.detail.pack(side="left", fill="both", expand=True)

        self.statusbar = tk.Frame(self, bg=T.surface, height=30)
        self.statusbar.grid(row=2, column=0, sticky="ew")
        self.statusbar.grid_propagate(False)
        self.status_left = tk.Label(self.statusbar, text="", bg=T.surface, fg=T.text_faint, font=ui(9), anchor="w")
        self.status_left.pack(side="left", padx=16)
        self.status_right = tk.Label(self.statusbar, text="", bg=T.surface, fg=T.text_faint, font=ui(9), anchor="e")
        self.status_right.pack(side="right", padx=16)
        self.status_right.configure(text=f"离线数据 {self.data.get('count', 0)} 条 · 快照 {self.data.get('scraped_at', '')[:10]} · v{APP_VERSION}")

    def _build_appbar(self) -> None:
        bar = tk.Frame(self, bg=T.surface, height=T.appbar_height)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_propagate(False)

        mascot = Mascot(bar, self.asset_dir, mode="idle", height=56)
        mascot.pack(side="left", padx=(18, 0), pady=8)

        title_box = tk.Frame(bar, bg=T.surface)
        title_box.pack(side="left", padx=(12, 18))
        tk.Label(title_box, text=APP_TITLE, bg=T.surface, fg=T.text, font=ui(16, "bold")).pack(anchor="w")
        tk.Label(title_box, text="完全离线 · 单文件 · 可在 WinPE 运行", bg=T.surface, fg=T.text_faint,
                 font=ui(10)).pack(anchor="w")

        self.chip_env = Pill(bar, text="环境检测中", fg=T.text_dim, bg=T.surface_alt, font=ui(9), height=26)
        self.chip_env.pack(side="right", padx=(0, 18), pady=24)
        self.chip_admin = Pill(bar, text="权限检测中", fg=T.text_dim, bg=T.surface_alt, font=ui(9), height=26)
        self.chip_admin.pack(side="right", padx=(0, 8), pady=24)
        AnimatedButton(bar, text="关于与免责声明", command=self._show_about, variant="ghost",
                       font=ui(11), height=36, padx=16).pack(side="right", padx=(0, 8), pady=20)
        AnimatedButton(bar, text="一键修复蓝屏与引导", command=self._open_bench_one_click,
                       variant="primary", font=ui(11, "bold"), height=36, padx=18).pack(side="right", pady=20)

    def _focus_search(self, _event=None) -> str:
        self.browser.entry.focus_set()
        return "break"

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #
    def _normalize(self, value: str) -> str:
        return value.strip().upper().replace("0X", "0x").replace(" ", "")

    def _on_query(self, query: str, category: str | None = None) -> None:
        self._active_category = category or getattr(self, "_active_category", "全部分类")
        self._refresh_list()

    def _refresh_list(self) -> None:
        query = self._normalize(self.browser.var_query.get())
        category = getattr(self, "_active_category", "全部分类")
        rows = []
        matched_entries = []
        for entry in self.entries:
            if category != "全部分类" and entry.get("category") != category:
                continue
            haystack = self._normalize(" ".join([
                entry.get("code", ""), entry.get("name", ""), entry.get("category", ""),
                entry.get("summary", ""),
                " ".join(c.get("title", "") for c in entry.get("causes", [])),
            ]))
            if query and query not in haystack:
                continue
            rows.append({
                "code": entry.get("code", ""),
                "name": entry.get("name", ""),
                "category": entry.get("category", ""),
                "severity": entry.get("severity", ""),
            })
            matched_entries.append(entry)
        self.browser.set_rows(rows, len(self.entries))
        self._matched = matched_entries
        if rows:
            self._select_code(rows[0]["code"])
        else:
            self.current = None
            self.detail.show_entry(None)
            self.status_left.configure(text="没有匹配的蓝屏代码")

    def _select_code(self, code: str) -> None:
        entry = self.by_code.get(code.upper())
        if not entry:
            return
        self.current = entry
        self.detail.show_entry(entry)
        self.status_left.configure(
            text=f"当前：{entry.get('code', '')}　{entry.get('name', '')}　·　推荐方案：{engine.PLANS[engine.recommend_plan(entry)]['name']}")
        if self._bench:
            self._bench.apply_plan(engine.recommend_plan(entry), engine.PLANS[engine.recommend_plan(entry)]["steps"])

    # ------------------------------------------------------------------ #
    # 环境
    # ------------------------------------------------------------------ #
    def _scan_environment(self, quiet: bool = False) -> None:
        def job() -> None:
            try:
                vols = engine.scan_volumes(self._log_queue)
                wins = engine.find_windows_drives(vols)
                efi = engine.find_efi_volume(vols)
                system = self.ctx.system_drive or (wins[0] if wins else "")
                efi_drive = self.ctx.efi_drive or (efi.letter + ":" if efi and efi.letter else "")
                probe = engine.Context(system_drive=system, efi_drive=efi_drive, volumes=vols)
                firmware = engine.detect_firmware(probe, vols)
                self.queue.put(("scan_done", {
                    "volumes": vols, "wins": wins, "system": system, "efi": efi,
                    "efi_drive": efi_drive, "firmware": firmware,
                }))
            except Exception as exc:  # noqa: BLE001
                self.queue.put(("scan_error", str(exc)))

        threading.Thread(target=job, daemon=True).start()

    def _apply_scan(self, data: dict) -> None:
        self.volumes = data["volumes"]
        self.efi_volume_number = data["efi"].number if data["efi"] else ""
        self.ctx.volumes = self.volumes
        self.ctx.system_drive = data["system"]
        self.ctx.efi_drive = data["efi_drive"]
        self.ctx.efi_volume_number = self.efi_volume_number
        if data["firmware"] != "AUTO":
            self.ctx.firmware = data["firmware"]
        self.ctx.backup_dir = engine.make_backup_dir(self.ctx)

        is_pe = self.ctx.winpe
        self.chip_env.configure(text="环境：WinPE / WinRE" if is_pe else "环境：完整 Windows")
        self.chip_env.set_fg(T.warning if is_pe else T.text_dim)
        self.chip_admin.configure(text="权限：管理员" if engine.is_admin() else "权限：普通用户")
        self.chip_admin.set_fg(T.success if engine.is_admin() else T.danger)

        if not self.fonts.has_cjk:
            self.status_right.configure(
                text=f"⚠ 未找到中文字体，当前系统可能缺少中文支持　·　离线数据 {self.data.get('count', 0)} 条 · v{APP_VERSION}")
        if self._bench:
            self._bench.set_context(self.ctx)
            self._bench.set_env_text(self._env_text(), T.text_dim)

    def _env_text(self) -> str:
        parts = [f"系统盘 {self.ctx.system_drive or '未识别'}"]
        parts.append(f"固件 {self.ctx.firmware}")
        if self.ctx.efi_drive:
            parts.append(f"EFI {self.ctx.efi_drive}")
        parts.append(f"备份 {self.ctx.backup_dir}")
        return "　·　".join(parts)

    # ------------------------------------------------------------------ #
    # 修复台
    # ------------------------------------------------------------------ #
    def _open_bench(self) -> None:
        if self._bench is not None:
            self._bench.lift()
            return
        self._bench = RepairBench(
            self.body, asset_dir=self.asset_dir, entry=self.current,
            on_close=self._close_bench, on_run=lambda: self._run(self._bench.selected_ids()),
            on_preview=self._preview, on_rescan=lambda: self._scan_environment(),
            on_auto_backup=self._auto_backup,
            on_toggle_step=lambda sid: self._bench.toggle_step(sid),
            on_save_log=self._save_log,
            on_one_click=self._run_one_click,
        )
        self._bench.set_context(self.ctx)
        self._bench.set_env_text(self._env_text(), T.text_dim)
        self._bench.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._bench.lift()
        self._bench.set_status("待命", "确认系统盘与备份目录后即可开始。", mascot_mode="action")

    def _open_bench_one_click(self) -> None:
        self._open_bench()
        plan = engine.PLANS["ONE_CLICK"]
        self._bench.apply_plan("ONE_CLICK", plan["steps"])
        self._bench.set_status("一键修复已就绪", "将执行：备份 → 文件系统 → 系统文件 → 引导重建。",
                               mascot_mode="action")

    def _close_bench(self) -> None:
        if self._bench is not None and self.running:
            if not messagebox.askyesno("仍在执行", "修复任务正在执行，确定要关闭吗？", parent=self):
                return
        if self._bench is not None:
            self._bench.destroy()
            self._bench = None

    def _auto_backup(self) -> None:
        self.ctx.backup_dir = engine.make_backup_dir(self.ctx)
        if self._bench:
            self._bench.set_context(self.ctx)

    def _build_context(self) -> engine.Context:
        ctx = engine.Context(
            system_drive=self.ctx.system_drive,
            efi_drive=self.ctx.efi_drive,
            firmware=self.ctx.firmware,
            backup_dir=self.ctx.backup_dir,
            dry_run=bool(self._bench.var_dry.get()) if self._bench else False,
            winpe=self.ctx.winpe,
            efi_volume_number=self.efi_volume_number,
            volumes=self.volumes,
        )
        if self._bench:
            ctx.system_drive = self._bench.var_system.get().strip() or ctx.system_drive
            ctx.efi_drive = self._bench.var_efi.get().strip() or ctx.efi_drive
            ctx.firmware = self._bench.var_firmware.get().strip() or ctx.firmware
            ctx.backup_dir = self._bench.var_backup.get().strip() or ctx.backup_dir
        return ctx

    def _preview(self) -> None:
        ctx = self._build_context()
        ids = self._bench.selected_ids() if self._bench else []
        if not ids:
            messagebox.showinfo("命令预览", "请先勾选至少一个执行项目。", parent=self)
            return
        lines = ["# 一键修复命令预览",
                 f"# 系统盘 {ctx.system_drive or '未选择'}　固件 {ctx.firmware}　"
                 f"模式 {'演练' if ctx.dry_run else '实际执行'}　备份 {ctx.backup_dir or '未设置'}", ""]
        lines += engine.preview_plan(ctx, ids)
        ReportWindow(self, "\n".join(lines))

    def _confirm(self, ids: list[str], ctx: engine.Context, title: str) -> bool:
        lines: list[tuple[str, str]] = []
        for sid in ids:
            step = engine.STEPS.get(sid)
            if not step:
                continue
            lines.append(("warn", f"· {step.title}　[{engine.RISK_TEXT.get(step.risk, '')}风险]"))
            for cmd in step.preview(ctx):
                lines.append(("cmd", f"    {cmd}"))
        lines.append(("danger", ""))
        lines.append(("danger", f"备份目录：{ctx.backup_dir or '未设置'}"))
        dialog = ConfirmOverlay(self, title=title, lines=lines)
        self.wait_window(dialog)
        return dialog.result

    def _run(self, ids: list[str]) -> None:
        if not ids:
            messagebox.showinfo("无法执行", "请先勾选至少一个执行项目。", parent=self)
            return
        ctx = self._build_context()
        if not ctx.dry_run and not ctx.winpe and not engine.is_admin():
            messagebox.showwarning("权限不足", "请右键以管理员身份运行，或进入 WinPE / WinRE 后执行引导修复。", parent=self)
            return
        if not ctx.dry_run and not self._confirm(ids, ctx, "确认执行修复"):
            return
        self._execute(ctx, ids)

    def _run_one_click(self) -> None:
        ctx = self._build_context()
        ids = engine.PLANS["ONE_CLICK"]["steps"]
        if not ctx.dry_run and not self._confirm(ids, ctx, "确认一键修复蓝屏与引导"):
            return
        self._execute(ctx, ids)

    def _execute(self, ctx: engine.Context, ids: list[str]) -> None:
        self.running = True
        if self._bench:
            self._bench.set_running(True)
            self._bench.set_status("执行中", "正在按顺序执行修复步骤，日志为唯一权威进度。",
                                   mascot_mode="action", bubble="正在修…")
        self._current_step = ""

        def job() -> None:
            try:
                results = engine.execute_steps(ctx, ids, self._log_queue)
                report = engine.format_report(ctx, results, self.current)
                self.queue.put(("run_done", results, report))
            except Exception as exc:  # noqa: BLE001
                self.queue.put(("run_error", str(exc)))

        threading.Thread(target=job, daemon=True).start()

    def _save_log(self) -> None:
        if not self._bench:
            return
        content = self._bench.log.content()
        if not content.strip():
            messagebox.showinfo("保存日志", "当前没有日志内容。", parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="保存执行日志", defaultextension=".txt",
            initialfile=f"BSODFix-log-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if path:
            Path(path).write_text(content, encoding="utf-8")

    def _show_about(self) -> None:
        lines = [
            ("h1", f"{APP_TITLE} v{APP_VERSION}\n"),
            ("h2", "离线与依赖\n"),
            ("body", "所有蓝屏数据已内置在可执行文件内，运行期不联网、不下载、不依赖任何运行库；\n"),
            ("body", "只需把本文件放进 64 位 WinPE / WinRE U 盘即可运行。\n"),
            ("h2", "数据来源\n"),
            ("body", f"蓝屏条目抓取自 {SOURCE_SITE} 及其代码库详情页，共 {self.data.get('count', 0)} 条，"
                     f"快照时间 {self.data.get('scraped_at', '')[:10]}。\n"),
            ("h2", "修复边界\n"),
            ("warn", "· 引导修复命令（bootrec / bcdboot）通常只存在于 PE 与 WinRE，完整 Windows 中会自动跳过。\n"),
            ("warn", "· 执行前会自动备份 BCD，必要时备份注册表配置单元；请另行备份重要数据。\n"),
            ("warn", "· 内存、硬盘、供电、主板等硬件故障无法用命令修复，界面会如实说明。\n"),
            ("warn", "· BitLocker 加密分区需先解锁或暂停保护。\n"),
            ("h2", "角色素材\n"),
            ("faint", "界面中的鼠鼠形象由 Fantasy Mouse UI 插件的授权素材派生，仅用于本地工具界面。\n"),
        ]
        win = tk.Toplevel(self)
        win.title("关于与免责声明")
        win.configure(bg=T.bg)
        win.geometry("760x520")
        win.transient(self.winfo_toplevel())
        apply_window_icon(win)
        text = RichText(win, bg=T.surface, font=ui(11))
        text.pack(fill="both", expand=True, padx=14, pady=(14, 8))
        text.write(lines, clear=True)
        bar = tk.Frame(win, bg=T.bg)
        bar.pack(fill="x", padx=14, pady=(0, 14))
        AnimatedButton(bar, text="关闭", command=win.destroy, variant="primary", font=ui(11),
                       height=34, padx=16).pack(side="right")

    # ------------------------------------------------------------------ #
    # 日志队列
    # ------------------------------------------------------------------ #
    def _log_queue(self, level: str, message: str) -> None:
        self.queue.put(("log", level, str(message)))

    def _poll_queue(self) -> None:
        try:
            while True:
                item = self.queue.get_nowait()
                kind = item[0]
                if kind == "log":
                    _, level, message = item
                    if self._bench:
                        self._bench.append_log(level, message)
                    if message.startswith("▶ "):
                        self._current_step = message[2:].strip()
                        if self._bench:
                            self._bench.set_status(self._current_step, "执行中…", mascot_mode="action", bubble="正在修…")
                    elif level in ("ok", "warn", "error", "skip") and self._bench:
                        self._bench.set_status(self._current_step or "执行中", message,
                                               mascot_mode="action", bubble="继续观察…")
                elif kind == "scan_done":
                    self._apply_scan(item[1])
                elif kind == "scan_error":
                    self.status_left.configure(text=f"环境扫描失败：{item[1]}")
                elif kind == "run_done":
                    _, results, report = item
                    self.running = False
                    if self._bench:
                        self._bench.set_running(False)
                        ok = sum(1 for r in results if r.status == "ok")
                        fail = sum(1 for r in results if r.status == "failed")
                        self._bench.set_status(
                            "执行完成" if not fail else "有步骤失败",
                            f"成功 {ok} 项，失败 {fail} 项。请查看日志中的返回码。",
                            mascot_mode="action", bubble="修完了，重启看看")
                    ReportWindow(self, report)
                elif kind == "run_error":
                    self.running = False
                    if self._bench:
                        self._bench.set_running(False)
                        self._bench.set_status("执行异常", item[1], mascot_mode="action")
                    messagebox.showerror("执行异常", item[1], parent=self)
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
