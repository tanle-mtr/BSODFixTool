#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""界面视图：代码浏览器、代码详情、修复台。

布局与组件来自目标产品推导（离线诊断控制台），与 Fantasy Mouse 参考构图无关。
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

import repair_engine as engine

from .theme import T, mono, severity_color, ui
from .widgets import AnimatedButton, Card, Mascot, Pill, RichText, RowList, fit_text, round_rect


def _pill_text(text: str) -> str:
    return text


class BrowserPanel(tk.Frame):
    """左栏：搜索 + 分类 + 结果列表。"""

    def __init__(self, master, *, on_select, on_query):
        super().__init__(master, bg=T.bg, width=T.left_width)
        self.pack_propagate(False)
        self._on_select = on_select
        self._on_query = on_query
        self._rows: list[dict] = []
        self._active_index = -1

        self._build_search()
        self._build_filters()
        self._build_list()

    # -- 搜索 ---------------------------------------------------------------
    def _build_search(self) -> None:
        holder = tk.Frame(self, bg=T.bg)
        holder.pack(fill="x", padx=16, pady=(16, 10))
        self.var_query = tk.StringVar()
        entry_wrap = tk.Frame(holder, bg=T.surface_alt, highlightthickness=1,
                              highlightbackground=T.border, highlightcolor=T.primary)
        entry_wrap.pack(fill="x")
        self.entry = tk.Entry(entry_wrap, textvariable=self.var_query, bg=T.surface_alt,
                              fg=T.text, insertbackground=T.primary, relief="flat", bd=0,
                              font=mono(12), highlightthickness=0)
        self.entry.pack(fill="x", padx=12, pady=11)
        self.var_query.trace_add("write", lambda *_: self._on_query(self.var_query.get()))
        self.hint = tk.Label(holder, text="输入蓝屏代码或名称，例如 0x0000007B / MEMORY_MANAGEMENT",
                             bg=T.bg, fg=T.text_faint, font=ui(10), anchor="w")
        self.hint.pack(fill="x", pady=(6, 0))
        self.entry.focus_set()

    # -- 分类 ---------------------------------------------------------------
    def _build_filters(self) -> None:
        holder = tk.Frame(self, bg=T.bg)
        holder.pack(fill="x", padx=16, pady=(4, 6))
        self._chips: dict[str, Pill] = {}
        self._chip_holder = holder

    def set_categories(self, categories: list[str], active: str) -> None:
        for chip in self._chips.values():
            chip.destroy()
        self._chips.clear()
        for index, name in enumerate(categories):
            row, col = divmod(index, 3)
            chip = Pill(self._chip_holder, text=name, fg=T.text_dim, bg=T.surface_alt,
                        font=ui(10), active=(name == active),
                        command=lambda n=name: self._on_chip(n))
            chip.grid(row=row, column=col, sticky="ew", padx=(0, 6), pady=3)
            self._chips[name] = chip
        for col in range(3):
            self._chip_holder.grid_columnconfigure(col, weight=1)

    def _on_chip(self, name: str) -> None:
        for chip_name, chip in self._chips.items():
            chip.set_active(chip_name == name)
        self._on_query(self.var_query.get(), name)

    # -- 列表 ---------------------------------------------------------------
    def _build_list(self) -> None:
        self.count_label = tk.Label(self, text="", bg=T.bg, fg=T.text_faint, font=ui(10), anchor="w")
        self.count_label.pack(fill="x", padx=16, pady=(2, 6))
        wrap = tk.Frame(self, bg=T.bg)
        wrap.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.list = RowList(wrap, row_height=T.row_height, draw_row=self._draw_row,
                            on_activate=self._activate, bg=T.surface)
        self.list.pack(fill="both", expand=True)

    def _draw_row(self, canvas, row, x, y, w, h, state) -> None:
        bg = T.elevated if state["active"] else (T.surface_alt if state["hover"] else T.surface)
        canvas.create_rectangle(x, y, x + w, y + h, fill=bg, outline="")
        if state["active"]:
            canvas.create_rectangle(x, y + 10, x + 3, y + h - 10, fill=T.primary, outline="")
        canvas.create_text(x + 16, y + h / 2, text=row["code"], font=mono(10, "bold"),
                           fill=T.info, anchor="w")
        name_font = ui(10, "bold")
        name = fit_text(canvas, row["name"], name_font, w - 108 - 34)
        canvas.create_text(x + 108, y + h / 2 - 8, text=name, font=name_font,
                           fill=T.text, anchor="w")
        canvas.create_text(x + 108, y + h / 2 + 10, text=row["category"], font=ui(9),
                           fill=T.text_faint, anchor="w")
        dot = severity_color(row["severity"])
        canvas.create_oval(x + w - 22, y + h / 2 - 4, x + w - 14, y + h / 2 + 4, fill=dot, outline="")

    def set_rows(self, rows: list[dict], total: int) -> None:
        self._rows = rows
        self.list.set_rows(rows)
        self.count_label.configure(text=f"匹配 {len(rows)} 条 / 全部 {total} 条")

    def set_active(self, index: int) -> None:
        self._active_index = index
        self.list.set_active(index)

    def _activate(self, index: int, row: dict) -> None:
        self._on_select(row["code"])


class DetailPanel(tk.Frame):
    """右栏：当前蓝屏代码的概览与细节。"""

    TABS = ("原因分析", "排查步骤", "参数与常见问题", "相关代码")

    def __init__(self, master, *, on_open_repair, asset_dir: Path):
        super().__init__(master, bg=T.bg)
        self._on_open_repair = on_open_repair
        self._asset_dir = asset_dir
        self._entry: dict | None = None
        self._tab = 0

        self.hero = Card(self, bg=T.surface)
        self.hero.pack(fill="x", padx=20, pady=(16, 12))
        self._build_hero()

        tab_bar = tk.Frame(self, bg=T.bg)
        tab_bar.pack(fill="x", padx=20)
        self._tab_pills: list[Pill] = []
        for index, name in enumerate(self.TABS):
            pill = Pill(tab_bar, text=name, fg=T.text_dim, bg=T.surface_alt, font=ui(10),
                        active=(index == 0), command=lambda i=index: self._set_tab(i))
            pill.pack(side="left", padx=(0, 8))
            self._tab_pills.append(pill)

        body = tk.Frame(self, bg=T.bg)
        body.pack(fill="both", expand=True, padx=20, pady=(10, 16))
        self.text = RichText(body, bg=T.surface, font=ui(11))
        self.text.pack(fill="both", expand=True)

        self.empty = tk.Frame(self, bg=T.bg)
        self.empty_mascot = Mascot(self.empty, asset_dir, mode="idle", height=200)
        self.empty_mascot.pack(pady=(28, 0))
        tk.Label(self.empty, text="先输入蓝屏代码或名称",
                 bg=T.bg, fg=T.text, font=ui(14, "bold")).pack(pady=(14, 4))
        tk.Label(self.empty, text="内置 73 条离线数据，不需要联网，也不需要安装任何东西",
                 bg=T.bg, fg=T.text_dim, font=ui(11)).pack()

    # -- 概览卡 -------------------------------------------------------------
    def _build_hero(self) -> None:
        left = tk.Frame(self.hero, bg=T.surface)
        left.pack(side="left", fill="both", expand=True, padx=18, pady=16)
        self.hero_code = tk.Label(left, text="—", bg=T.surface, fg=T.info, font=mono(17, "bold"), anchor="w")
        self.hero_code.pack(fill="x")
        self.hero_name = tk.Label(left, text="尚未选择蓝屏代码", bg=T.surface, fg=T.text,
                                  font=ui(15, "bold"), anchor="w")
        self.hero_name.pack(fill="x", pady=(2, 8))
        self.hero_summary = tk.Label(left, text="", bg=T.surface, fg=T.text_dim, font=ui(11),
                                     anchor="w", justify="left", wraplength=640)
        self.hero_summary.pack(fill="x")
        self.hero_tips = tk.Label(left, text="", bg=T.surface, fg=T.text_faint, font=ui(10),
                                  anchor="w", justify="left")
        self.hero_tips.pack(fill="x", pady=(8, 0))

        right = tk.Frame(self.hero, bg=T.surface)
        right.pack(side="right", padx=(10, 18), pady=14)
        self.mascot = Mascot(right, self._asset_dir, mode="idle", height=56)
        self.mascot.pack()
        self.pill_row = tk.Frame(right, bg=T.surface)
        self.pill_row.pack(pady=(8, 0))
        self.severity_pill = Pill(self.pill_row, text="—", fg=T.text_dim, bg=T.surface_alt, font=ui(9))
        self.severity_pill.pack(side="left", padx=(0, 6))
        self.category_pill = Pill(self.pill_row, text="—", fg=T.text_dim, bg=T.surface_alt, font=ui(9))
        self.category_pill.pack(side="left")
        AnimatedButton(right, text="打开修复台", command=self._on_open_repair, variant="ghost",
                       font=ui(10), height=32, padx=14).pack(pady=(12, 0))

    # -- 渲染 ---------------------------------------------------------------
    def show_entry(self, entry: dict | None) -> None:
        self._entry = entry
        if not entry:
            self.hero.pack_forget()
            self.text.master.pack_forget()
            self.empty.pack(fill="both", expand=True)
            return
        self.empty.pack_forget()
        self.hero.pack(fill="x", padx=20, pady=(16, 12))
        self.text.master.pack(fill="both", expand=True, padx=20, pady=(10, 16))

        self.hero_code.configure(text=entry.get("code", ""))
        self.hero_name.configure(text=entry.get("name", ""))
        self.hero_summary.configure(text=entry.get("summary", ""))
        tips = entry.get("quick_tips", [])
        self.hero_tips.configure(text="\n".join(f"· {t}" for t in tips))
        severity = entry.get("severity", "")
        self.severity_pill.configure(text=severity or "严重度未知")
        self.severity_pill.set_fg(severity_color(severity))
        self.category_pill.configure(text=entry.get("category", ""))
        self._set_tab(self._tab, force=True)

    def _set_tab(self, index: int, force: bool = False) -> None:
        self._tab = index
        for i, pill in enumerate(self._tab_pills):
            pill.set_active(i == index)
        entry = self._entry
        if not entry:
            return
        segs: list[tuple[str, str]] = []
        if index == 0:
            segs.append(("h1", "常见原因\n"))
            for cause in entry.get("causes", []):
                level = cause.get("level", "")
                color = "danger" if level.startswith("高") else ("warn" if level.startswith("中") else "dim")
                segs.append(("h2", f"{cause.get('title', '')}　[{level}]\n"))
                segs.append(("body", f"{cause.get('desc', '')}\n"))
            if entry.get("warnings"):
                segs.append(("h1", "以下情况请不要继续自行折腾\n"))
                for warn in entry["warnings"]:
                    segs.append(("danger", f"! {warn}\n"))
        elif index == 1:
            segs.append(("h1", "排查步骤\n"))
            for i, step in enumerate(entry.get("steps", []), 1):
                segs.append(("h2", f"{i}. {step.get('title', '')}\n"))
                segs.append(("body", f"{step.get('desc', '')}\n"))
            segs.append(("h1", "数据来源与说明\n"))
            segs.append(("dim", f"{entry.get('disclaimer', '')}\n"))
        elif index == 2:
            segs.append(("h1", "参数含义\n"))
            for param in entry.get("params", []):
                segs.append(("bullet", f"· {param.get('name', '')}：{param.get('desc', '')}\n"))
            segs.append(("h1", "常见问题\n"))
            for faq in entry.get("faqs", []):
                segs.append(("h2", f"Q：{faq.get('q', '')}\n"))
                segs.append(("body", f"A：{faq.get('a', '')}\n"))
        else:
            segs.append(("h1", "相关蓝屏代码\n"))
            for rel in entry.get("related", []):
                segs.append(("bullet", f"· {rel.get('code', '')}　{rel.get('name', '')}\n"))
            segs.append(("h1", "条目信息\n"))
            segs.append(("mono", f"来源页面：{entry.get('detail_url', '')}\n"))
        self.text.write(segs, clear=True, scroll=False)


class RepairBench(tk.Frame):
    """修复台：环境确认 + 步骤清单 + 实时日志。"""

    def __init__(self, master, *, asset_dir: Path, entry: dict | None, on_close, on_run,
                 on_preview, on_rescan, on_auto_backup, on_toggle_step, on_save_log,
                 on_one_click):
        super().__init__(master, bg=T.bg)
        self._asset_dir = asset_dir
        self._entry = entry
        self._on_close = on_close
        self._on_run = on_run
        self._on_preview = on_preview
        self._on_rescan = on_rescan
        self._on_auto_backup = on_auto_backup
        self._on_toggle_step = on_toggle_step
        self._on_save_log = on_save_log
        self._on_one_click = on_one_click
        self._steps: list[str] = []
        self._selected: dict[str, bool] = {}
        self._log_lines: list[tuple[str, str]] = []

        self._build()
        self.apply_plan(engine.recommend_plan(entry), engine.PLANS[engine.recommend_plan(entry)]["steps"])

    # -- 构建 ---------------------------------------------------------------
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = tk.Frame(self, bg=T.surface, height=64)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        tk.Label(header, text="修复台", bg=T.surface, fg=T.text, font=ui(15, "bold")).pack(side="left", padx=22)
        self.header_code = tk.Label(header, text="", bg=T.surface, fg=T.info, font=mono(12))
        self.header_code.pack(side="left", padx=(6, 0))
        AnimatedButton(header, text="关闭修复台", command=self._on_close, variant="ghost", font=ui(11),
                       height=32, padx=14).pack(side="right", padx=20)

        body = tk.Frame(self, bg=T.bg)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=0, minsize=520)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        left = tk.Frame(body, bg=T.bg)
        left.grid(row=0, column=0, sticky="nsew", padx=(20, 12), pady=16)
        right = tk.Frame(body, bg=T.bg)
        right.grid(row=0, column=1, sticky="nsew", padx=(0, 20), pady=16)

        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(2, weight=1)
        self._build_environment(left)
        self._build_plan(left)
        self._build_steps(left)
        self._build_log(right)
        self._build_footer()

    def _build_environment(self, parent: tk.Frame) -> None:
        card = Card(parent, bg=T.surface)
        card.grid(row=0, column=0, sticky="ew")
        tk.Label(card, text="环境与目标", bg=T.surface, fg=T.text, font=ui(12, "bold")).pack(anchor="w", padx=16, pady=(14, 8))
        grid = tk.Frame(card, bg=T.surface)
        grid.pack(fill="x", padx=16, pady=(0, 10))
        grid.grid_columnconfigure(1, weight=1)
        grid.grid_columnconfigure(3, weight=1)

        self.var_system = tk.StringVar()
        self.var_firmware = tk.StringVar(value="AUTO")
        self.var_efi = tk.StringVar()
        self.var_backup = tk.StringVar()

        tk.Label(grid, text="系统盘", bg=T.surface, fg=T.text_dim, font=ui(10)).grid(row=0, column=0, sticky="w", pady=4)
        self.cmb_system = ttk.Combobox(grid, textvariable=self.var_system, width=9, font=ui(10))
        self.cmb_system.grid(row=0, column=1, sticky="w", padx=(6, 0), pady=4)
        tk.Label(grid, text="固件", bg=T.surface, fg=T.text_dim, font=ui(10)).grid(row=0, column=2, sticky="w", padx=(14, 0), pady=4)
        self.cmb_firmware = ttk.Combobox(grid, textvariable=self.var_firmware, width=7, font=ui(10), state="readonly")
        self.cmb_firmware.grid(row=0, column=3, sticky="w", padx=(6, 0), pady=4)
        tk.Label(grid, text="EFI", bg=T.surface, fg=T.text_dim, font=ui(10)).grid(row=0, column=4, sticky="w", padx=(14, 0), pady=4)
        self.cmb_efi = ttk.Combobox(grid, textvariable=self.var_efi, width=8, font=ui(10))
        self.cmb_efi.grid(row=0, column=5, sticky="w", padx=(6, 0), pady=4)

        tk.Label(grid, text="备份目录", bg=T.surface, fg=T.text_dim, font=ui(10)).grid(row=1, column=0, sticky="w", pady=4)
        self.entry_backup = tk.Entry(grid, textvariable=self.var_backup, bg=T.surface_alt, fg=T.text,
                                     insertbackground=T.primary, relief="flat", bd=0, font=mono(9))
        self.entry_backup.grid(row=1, column=1, columnspan=4, sticky="ew", padx=(8, 0), pady=4,
                               ipady=6, ipadx=4)
        AnimatedButton(grid, text="自动", command=self._on_auto_backup, variant="ghost", font=ui(10),
                       height=30, padx=12).grid(row=1, column=5, sticky="w", padx=(8, 0), pady=4)

        actions = tk.Frame(card, bg=T.surface)
        actions.pack(fill="x", padx=16, pady=(0, 12))
        grid.grid_columnconfigure(1, weight=1)
        AnimatedButton(actions, text="重新扫描环境", command=self._on_rescan, variant="ghost",
                       font=ui(10), height=30, padx=12).pack(side="left")
        self.env_label = tk.Label(card, text="等待扫描…", bg=T.surface, fg=T.text_faint, font=ui(9),
                                  anchor="w", justify="left", wraplength=460)
        self.env_label.pack(fill="x", padx=16, pady=(0, 14))

    def _build_plan(self, parent: tk.Frame) -> None:
        card = Card(parent, bg=T.surface)
        card.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.plan_title = tk.Label(card, text="推荐方案", bg=T.surface, fg=T.primary, font=ui(12, "bold"), anchor="w")
        self.plan_title.pack(fill="x", padx=16, pady=(14, 2))
        self.plan_note = tk.Label(card, text="", bg=T.surface, fg=T.text_dim, font=ui(10), anchor="w",
                                  justify="left", wraplength=460)
        self.plan_note.pack(fill="x", padx=16, pady=(0, 14))

    def _build_steps(self, parent: tk.Frame) -> None:
        card = Card(parent, bg=T.surface)
        card.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        tk.Label(card, text="执行项目（单击切换勾选）", bg=T.surface, fg=T.text, font=ui(12, "bold")).pack(
            anchor="w", padx=16, pady=(14, 6))
        wrap = tk.Frame(card, bg=T.surface)
        wrap.pack(fill="both", expand=True, padx=10, pady=(0, 12))
        self.step_list = RowList(wrap, row_height=46, draw_row=self._draw_step,
                                 on_activate=self._activate_step, bg=T.surface)
        self.step_list.pack(fill="both", expand=True)

    def _draw_step(self, canvas, row, x, y, w, h, state) -> None:
        bg = T.elevated if state["hover"] else T.surface
        canvas.create_rectangle(x, y, x + w, y + h, fill=bg, outline="")
        checked = row["checked"]
        cx, cy = x + 22, y + h / 2
        if checked:
            round_rect(canvas, cx - 8, cy - 8, cx + 8, cy + 8, 5, fill=T.primary, outline=T.primary)
            canvas.create_text(cx, cy, text="✓", font=ui(11, "bold"), fill="#0b1020")
        else:
            round_rect(canvas, cx - 8, cy - 8, cx + 8, cy + 8, 5, fill=T.surface_alt, outline=T.border)
        canvas.create_text(x + 42, y + 15, text=row["title"], font=ui(11, "bold"), fill=T.text, anchor="w")
        risk_color = {"low": T.success, "medium": T.warning, "high": T.danger}.get(row["risk"], T.idle)
        canvas.create_text(x + w - 14, y + 15, text=f"{engine.RISK_TEXT.get(row['risk'], '')}风险",
                           font=ui(9), fill=risk_color, anchor="e")
        detail = row["detail"]
        if row.get("note"):
            detail = f"{detail}　（{row['note']}）"
        canvas.create_text(x + 42, y + 33, text=detail, font=ui(9), fill=T.text_faint, anchor="w")

    def _activate_step(self, index: int, row: dict) -> None:
        self._on_toggle_step(row["id"])

    # -- 日志 ---------------------------------------------------------------
    def _build_log(self, parent: tk.Frame) -> None:
        card = Card(parent, bg=T.surface)
        card.pack(fill="both", expand=True)
        top = tk.Frame(card, bg=T.surface)
        top.pack(fill="x", padx=16, pady=(14, 8))
        self.mascot = Mascot(top, self._asset_dir, mode="action", height=220)
        self.mascot.pack(side="left")
        status = tk.Frame(top, bg=T.surface)
        status.pack(side="left", fill="both", expand=True, padx=(6, 0))
        self.status_title = tk.Label(status, text="待命", bg=T.surface, fg=T.text, font=ui(13, "bold"), anchor="w")
        self.status_title.pack(fill="x")
        self.status_detail = tk.Label(status, text="确认系统盘与备份目录后即可开始。",
                                      bg=T.surface, fg=T.text_dim, font=ui(10), anchor="w",
                                      justify="left", wraplength=360)
        self.status_detail.pack(fill="x", pady=(6, 0))

        self.log = RichText(card, bg="#060a16", fg="#c9d6f5", font=mono(10))
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.log.write([("lvl_skip", "等待执行。每条命令、返回码与结果都会实时打印在这里。\n")], scroll=False)

    def _build_footer(self) -> None:
        footer = tk.Frame(self, bg=T.surface, height=62)
        footer.grid(row=2, column=0, sticky="ew")
        footer.grid_propagate(False)
        self.var_dry = tk.BooleanVar(value=False)
        ttk.Checkbutton(footer, text="演练模式（只显示命令，不执行）", variable=self.var_dry,
                        style="Dark.TCheckbutton").pack(side="left", padx=(22, 0))
        AnimatedButton(footer, text="保存日志", command=self._on_save_log, variant="ghost", font=ui(11),
                       height=36, padx=14).pack(side="right", padx=(22, 0))
        self.btn_run = AnimatedButton(footer, text="执行勾选项目", command=self._on_run, variant="primary",
                                      font=ui(11, "bold"), height=36, padx=18)
        self.btn_run.pack(side="right")
        AnimatedButton(footer, text="命令预览", command=self._on_preview, variant="ghost", font=ui(11),
                       height=36, padx=14).pack(side="right", padx=(0, 8))
        AnimatedButton(footer, text="一键修复蓝屏与引导", command=self._on_one_click, variant="primary",
                       font=ui(11, "bold"), height=36, padx=18).pack(side="left", padx=(22, 0))

    # -- 数据 ---------------------------------------------------------------
    def apply_plan(self, plan_id: str, step_ids: list[str]) -> None:
        plan = engine.PLANS.get(plan_id, engine.PLANS["GUIDED_ONLY"])
        self.plan_title.configure(text=plan["name"])
        self.plan_note.configure(text=plan["note"])
        self._steps = [s for s in step_ids if s in engine.STEPS]
        self._selected = {s: not engine.STEPS[s].optional for s in self._steps}
        self.refresh_steps()

    def refresh_steps(self, notes: dict[str, str] | None = None) -> None:
        rows = []
        for sid in self._steps:
            step = engine.STEPS[sid]
            rows.append({
                "id": sid,
                "title": step.title,
                "risk": step.risk,
                "detail": step.detail,
                "checked": self._selected.get(sid, False),
                "note": (notes or {}).get(sid, ""),
            })
        self.step_list.set_rows(rows)

    def selected_ids(self) -> list[str]:
        return [s for s in self._steps if self._selected.get(s)]

    def toggle_step(self, sid: str) -> None:
        self._selected[sid] = not self._selected.get(sid, False)
        self.refresh_steps()

    def set_context(self, ctx: engine.Context) -> None:
        self.var_system.set(ctx.system_drive)
        self.var_firmware.set(ctx.firmware)
        self.var_efi.set(ctx.efi_drive)
        self.var_backup.set(ctx.backup_dir)

    def set_env_text(self, text: str, color: str = T.text_faint) -> None:
        self.env_label.configure(text=text, fg=color)

    def set_status(self, title: str, detail: str, mascot_mode: str = "action", bubble: str = "") -> None:
        self.status_title.configure(text=title)
        self.status_detail.configure(text=detail)
        self.mascot.set_mode(mascot_mode, bubble)

    def append_log(self, level: str, message: str) -> None:
        tag = {"ok": "lvl_ok", "warn": "lvl_warn", "error": "lvl_error", "cmd": "lvl_cmd",
               "out": "lvl_out", "skip": "lvl_skip"}.get(level, "lvl_out")
        self.log.write([(tag, f"{message}\n")], scroll=True)

    def set_running(self, running: bool) -> None:
        self.btn_run.configure(state="disabled" if running else "normal")
