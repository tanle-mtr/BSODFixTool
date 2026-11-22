#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自绘控件库：动画按钮、胶囊、卡片、列表、滚动区、富文本、鼠鼠立绘。"""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import ttk

from .theme import T, mono, reduced_motion, ui


# --------------------------------------------------------------------------- #
# 基础绘制工具
# --------------------------------------------------------------------------- #
def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def mix(a: str, b: str, t: float) -> str:
    t = max(0.0, min(1.0, t))
    ca, cb = hex_rgb(a), hex_rgb(b)
    return "#%02x%02x%02x" % tuple(round(ca[i] + (cb[i] - ca[i]) * t) for i in range(3))


def parent_bg(widget: tk.Widget) -> str:
    for key in ("bg", "background"):
        try:
            return str(widget.cget(key))
        except tk.TclError:
            continue
    return T.bg


def fit_text(widget: tk.Widget, text: str, font, max_width: float) -> str:
    """按可用宽度截断文本并加省略号，避免长名称溢出裁切。"""
    if max_width <= 12:
        return text
    font_obj = tkfont.Font(root=widget, font=font)
    if font_obj.measure(text) <= max_width:
        return text
    ellipsis = "…"
    trimmed = text
    while trimmed and font_obj.measure(trimmed + ellipsis) > max_width:
        trimmed = trimmed[:-1]
    return (trimmed + ellipsis) if trimmed else ellipsis


def round_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, r: float, **kwargs) -> int:
    r = max(2, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class AnimatedButton(tk.Canvas):
    """自绘圆角按钮：悬停 / 按下 / 恢复全部为缓出过渡。"""

    VARIANTS = {
        "primary": {
            "normal": T.primary, "hover": T.primary_hover, "active": T.primary_active,
            "fg": "#ffffff", "fg_hover": "#ffffff",
            "border": T.primary_active, "border_hover": T.primary_active, "shadow": "#1b2550",
        },
        "ghost": {
            "normal": T.surface_alt, "hover": T.elevated, "active": "#202c52",
            "fg": T.text_dim, "fg_hover": T.text,
            "border": T.border, "border_hover": "#3a4a7d", "shadow": T.bg,
        },
        "quiet": {
            "normal": T.bg, "hover": T.surface_alt, "active": T.elevated,
            "fg": T.text_faint, "fg_hover": T.text_dim,
            "border": T.bg, "border_hover": T.border, "shadow": T.bg,
        },
        "danger": {
            "normal": T.danger, "hover": "#ef5f5f", "active": "#d94848",
            "fg": "#ffffff", "fg_hover": "#ffffff",
            "border": "#d94848", "border_hover": "#c24141", "shadow": "#3a1b25",
        },
    }

    def __init__(self, master, text: str = "", command=None, variant: str = "primary",
                 width: int | None = None, height: int = 38, font=None, padx: int = 18,
                 radius: int = T.radius, takefocus: int = 1, **kwargs):
        bg = parent_bg(master)
        super().__init__(master, height=height, highlightthickness=0, bd=0, bg=bg,
                         takefocus=takefocus, **kwargs)
        self._text = text
        self._command = command
        self._font_spec = font or ui(11, "bold")
        self._font = tkfont.Font(root=master, font=self._font_spec)
        self._padx = padx
        self._radius = radius
        self._state = "normal"
        self._inside = False
        self._pressed = False
        self._focused = False
        self._t = 0.0
        self._after: str | None = None
        self._palette = dict(self.VARIANTS.get(variant, self.VARIANTS["ghost"]))
        if width is None:
            width = max(84, int(self._font.measure(text) + padx * 2 + 12))
        tk.Canvas.configure(self, width=width, height=height)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<FocusIn>", self._on_focus)
        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<Key-space>", self._on_key)
        self.bind("<Key-Return>", self._on_key)
        self._draw()

    # -- 绘制 ---------------------------------------------------------------
    def _draw(self) -> None:
        self.delete("all")
        w = int(float(self.cget("width")))
        h = int(float(self.cget("height")))
        p = self._palette
        if self._state == "disabled":
            fill, fg, border, shadow = T.surface_alt, T.text_faint, T.border_soft, T.bg
            dy = 0
        else:
            target = p["active"] if self._pressed else p["hover"]
            fill = mix(p["normal"], target, self._t)
            fg = mix(p["fg"], p["fg_hover"], self._t)
            border = mix(p["border"], p["border_hover"], self._t)
            shadow = p["shadow"]
            dy = 1 if self._pressed else 0
        round_rect(self, 2, 3 + dy, w - 1, h - 1 + dy, self._radius, fill=shadow, outline="")
        round_rect(self, 1, 1 + dy, w - 2, h - 3 + dy, self._radius, fill=fill, outline=border, width=1)
        if self._focused and self._state != "disabled":
            round_rect(self, 3, 3 + dy, w - 3, h - 5 + dy, self._radius - 2,
                       outline=T.primary, width=1)
        self.create_text(w / 2, (h - 2) / 2 + dy, text=self._text, font=self._font, fill=fg)

    def _animate_to(self, target: float) -> None:
        if self._after:
            try:
                self.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None
        if self._state == "disabled" or reduced_motion() or abs(self._t - target) < 0.01:
            self._t = target
            self._draw()
            return
        start, delta, steps, interval = self._t, target - self._t, 9, 16
        counter = {"i": 0}

        def frame() -> None:
            counter["i"] += 1
            p = counter["i"] / steps
            eased = 1 - (1 - p) ** 3
            self._t = start + delta * eased
            self._draw()
            if counter["i"] < steps:
                self._after = self.after(interval, frame)
            else:
                self._after = None

        frame()

    # -- 事件 ---------------------------------------------------------------
    def _on_enter(self, _event=None) -> None:
        if self._state == "disabled":
            return
        self._inside = True
        self.configure(cursor="hand2")
        self._animate_to(1.0)

    def _on_leave(self, _event=None) -> None:
        self._inside = False
        self._pressed = False
        self.configure(cursor="")
        self._animate_to(0.0)

    def _on_press(self, _event=None) -> None:
        if self._state == "disabled":
            return
        self.focus_set()
        self._pressed = True
        self._draw()
        self._animate_to(1.0)

    def _on_release(self, _event=None) -> None:
        if self._state == "disabled":
            return
        was_pressed = self._pressed
        self._pressed = False
        self._animate_to(1.0 if self._inside else 0.0)
        if was_pressed and self._inside and self._command:
            self.after(50, self._command)

    def _on_focus(self, _event=None) -> None:
        self._focused = True
        self._draw()

    def _on_focus_out(self, _event=None) -> None:
        self._focused = False
        self._draw()

    def _on_key(self, _event=None) -> str:
        if self._state == "disabled":
            return "break"
        if self._command:
            self.after(10, self._command)
        return "break"

    # -- 配置 ---------------------------------------------------------------
    def configure(self, **kwargs) -> None:
        if "state" in kwargs:
            self._state = "disabled" if str(kwargs.pop("state")) == "disabled" else "normal"
            self.configure(cursor="" if self._state == "disabled" else ("hand2" if self._inside else ""))
        if "text" in kwargs:
            self._text = str(kwargs.pop("text"))
        if kwargs:
            tk.Canvas.configure(self, **kwargs)
        self._draw()

    def cget(self, key: str):
        if key == "state":
            return self._state
        return super().cget(key)


class Pill(tk.Canvas):
    """胶囊标签：状态徽章 / 可点选筛选项。"""

    def __init__(self, master, text: str = "", fg: str = T.text_dim, bg: str = T.surface_alt,
                 font=None, active: bool = False, command=None, height: int = 26, padx: int = 12):
        self._font_spec = font or ui(10)
        self._font = tkfont.Font(root=master, font=self._font_spec)
        width = int(self._font.measure(text) + padx * 2)
        super().__init__(master, width=width, height=height, highlightthickness=0, bd=0,
                         bg=parent_bg(master))
        self._text = text
        self._fg = fg
        self._bg = bg
        self._active = active
        self._command = command
        self._hover = False
        self._draw()
        if command:
            self.bind("<Enter>", self._on_enter)
            self.bind("<Leave>", self._on_leave)
            self.bind("<Button-1>", self._on_click)

    def _draw(self) -> None:
        self.delete("all")
        w = int(float(self.cget("width")))
        h = int(float(self.cget("height")))
        fill = mix(self._bg, T.primary, 0.28) if self._active else (
            mix(self._bg, T.primary, 0.16) if self._hover else self._bg)
        fg = T.text if (self._active or self._hover) else self._fg
        round_rect(self, 1, 1, w - 1, h - 1, h / 2, fill=fill,
                   outline=T.primary if self._active else T.border, width=1)
        self.create_text(w / 2, h / 2, text=self._text, font=self._font, fill=fg)

    def _on_enter(self, _event=None) -> None:
        self._hover = True
        self.configure(cursor="hand2")
        self._draw()

    def _on_leave(self, _event=None) -> None:
        self._hover = False
        self.configure(cursor="")
        self._draw()

    def _on_click(self, _event=None) -> None:
        if self._command:
            self._command()

    def set_active(self, active: bool) -> None:
        self._active = active
        self._draw()

    def set_fg(self, color: str) -> None:
        self._fg = color
        self._draw()

    def configure(self, **kwargs) -> None:
        if "text" in kwargs:
            self._text = str(kwargs.pop("text"))
            self.configure(width=int(self._font.measure(self._text) + 24))
        if "fg" in kwargs:
            self._fg = str(kwargs.pop("fg"))
        if kwargs:
            tk.Canvas.configure(self, **kwargs)
        self._draw()


class Card(tk.Frame):
    """带发丝描边的表面卡片。"""

    def __init__(self, master, bg: str = T.surface, border: str = T.border_soft, **kwargs):
        super().__init__(master, bg=bg, highlightthickness=1, highlightbackground=border,
                         highlightcolor=T.primary, bd=0, **kwargs)


class RowList(tk.Canvas):
    """自绘行列表：完全掌控行内排版，避免树控件的默认观感。"""

    def __init__(self, master, *, row_height: int = T.row_height, draw_row=None,
                 on_activate=None, bg: str = T.surface, **kwargs):
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, **kwargs)
        self._row_height = row_height
        self._draw_row = draw_row or (lambda *_: None)
        self._on_activate = on_activate
        self.rows: list = []
        self._hover_index = -1
        self._active_index = -1
        self.bind("<Configure>", lambda _e: self.redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda _e: self._set_hover(-1))
        self.bind("<Button-1>", self._on_click)
        self.bind("<MouseWheel>", self._on_wheel)

    def set_rows(self, rows: list) -> None:
        self.rows = rows
        self._hover_index = -1
        self.redraw()

    def set_active(self, index: int) -> None:
        self._active_index = index
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        width = max(240, self.winfo_width())
        y = 0
        for index, row in enumerate(self.rows):
            state = {
                "hover": index == self._hover_index,
                "active": index == self._active_index,
                "width": width,
                "height": self._row_height,
            }
            self._draw_row(self, row, 0, y, width, self._row_height, state)
            y += self._row_height
        self.configure(scrollregion=(0, 0, width, max(y, 1)))

    def _row_at(self, y: int) -> int:
        index = y // self._row_height
        return index if 0 <= index < len(self.rows) else -1

    def _set_hover(self, index: int) -> None:
        if index != self._hover_index:
            self._hover_index = index
            self.redraw()

    def _on_motion(self, event) -> None:
        self._set_hover(self._row_at(event.y))

    def _on_click(self, event) -> None:
        index = self._row_at(event.y)
        if index >= 0 and self._on_activate:
            self._active_index = index
            self.redraw()
            self._on_activate(index, self.rows[index])

    def _on_wheel(self, event) -> str:
        self.yview_scroll(-3 if event.delta > 0 else 3, "units")
        return "break"


class ScrollArea(tk.Frame):
    """纵向滚动容器，内含可自由布局的子框架。"""

    def __init__(self, master, bg: str = T.bg, **kwargs):
        super().__init__(master, bg=bg, **kwargs)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        # inner 是 canvas 的子窗口，事件会冒泡到 canvas，这里只绑定一次避免重复滚动
        self.canvas.bind("<MouseWheel>", self._on_wheel)

    def _on_inner(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)

    def _on_wheel(self, event) -> str:
        self.canvas.yview_scroll(-3 if event.delta > 0 else 3, "units")
        return "break"


class RichText(tk.Text):
    """带语义标签的深色富文本。"""

    def __init__(self, master, bg: str = T.surface, fg: str = T.text, font=None, **kwargs):
        super().__init__(master, bg=bg, fg=fg, font=font or ui(11), relief="flat",
                         bd=0, highlightthickness=1, highlightbackground=T.border_soft,
                         highlightcolor=T.primary, wrap="word", padx=16, pady=14,
                         spacing1=2, spacing3=3, **kwargs)
        self._configure_tags()

    def _configure_tags(self) -> None:
        cfg = {
            "display": {"font": ui(19, "bold"), "foreground": T.text, "spacing3": 6},
            "h1": {"font": ui(15, "bold"), "foreground": T.text, "spacing1": 12, "spacing3": 4},
            "h2": {"font": ui(12, "bold"), "foreground": T.primary, "spacing1": 12, "spacing3": 4},
            "body": {"foreground": T.text},
            "dim": {"foreground": T.text_dim},
            "faint": {"foreground": T.text_faint},
            "bullet": {"foreground": T.text, "lmargin1": 18, "lmargin2": 18, "spacing3": 4},
            "code": {"font": mono(11), "foreground": "#bcd2ff", "background": T.surface_alt},
            "ok": {"foreground": T.success},
            "warn": {"foreground": T.warning},
            "danger": {"foreground": T.danger, "font": ui(11, "bold")},
            "mono": {"font": mono(11), "foreground": T.text_dim},
            "lvl_ok": {"font": mono(10), "foreground": T.success},
            "lvl_warn": {"font": mono(10), "foreground": T.warning},
            "lvl_error": {"font": mono(10), "foreground": T.danger},
            "lvl_cmd": {"font": mono(10), "foreground": "#8ab4ff"},
            "lvl_out": {"font": mono(10), "foreground": T.text_dim},
            "lvl_skip": {"font": mono(10), "foreground": T.text_faint},
        }
        for tag, opts in cfg.items():
            self.tag_configure(tag, **opts)

    def write(self, segments: list[tuple[str, str]], *, clear: bool = False, scroll: bool = True) -> None:
        self.configure(state="normal")
        if clear:
            self.delete("1.0", "end")
        for tag, content in segments:
            self.insert("end", content, tag)
        self.configure(state="disabled")
        if scroll:
            self.see("end")

    def content(self) -> str:
        return self.get("1.0", "end-1c")


class Mascot(tk.Frame):
    """鼠鼠立绘：可切换 idle / action 资产，并可附带状态气泡。"""

    def __init__(self, master, asset_dir: Path, mode: str = "idle", height: int = 56,
                 bubble: str = "", fonts=None, bubble_font=None):
        super().__init__(master, bg=T.bg)
        self._asset_dir = asset_dir
        self._mode = mode
        self._image = None
        self._height = height
        self._bubble_text = bubble
        self._fonts = fonts
        self._bubble_font = bubble_font or ui(10)
        self.canvas = tk.Canvas(self, bg=T.bg, highlightthickness=0, bd=0)
        self.canvas.pack()
        self._render()

    def _asset(self) -> Path:
        if self._mode == "action":
            return self._asset_dir / ("mascot_action_300.png" if self._height >= 260 else "mascot_action_220.png")
        if self._height >= 200:
            return self._asset_dir / "mascot_idle_260.png"
        if self._height >= 120:
            return self._asset_dir / "mascot_idle_200.png"
        return self._asset_dir / ("mascot_idle_56.png" if self._height > 48 else "mascot_idle_48.png")

    def _render(self) -> None:
        self.canvas.delete("all")
        path = self._asset()
        try:
            photo = tk.PhotoImage(file=str(path))
        except tk.TclError:
            return
        self._image = photo
        w, h = photo.width(), photo.height()
        self.canvas.configure(width=w, height=h)
        self.canvas.create_image(0, 0, image=photo, anchor="nw")
        if self._bubble_text:
            self._draw_bubble(w, h)

    def _draw_bubble(self, w: int, h: int) -> None:
        text = self._bubble_text
        width = min(w + 120, 320)
        height = 54
        x0 = (w - width) / 2
        y0 = h - height - 2
        round_rect(self.canvas, x0, y0, x0 + width, y0 + height, 14, fill=T.elevated,
                   outline=T.border, width=1)
        self.canvas.create_text(x0 + width / 2, y0 + height / 2, text=text,
                                font=self._bubble_font, fill=T.text, width=width - 24,
                                justify="center")

    def set_mode(self, mode: str, bubble: str = "") -> None:
        self._mode = mode
        self._bubble_text = bubble
        self._render()

    def set_bubble(self, bubble: str) -> None:
        self._bubble_text = bubble
        self._render()
