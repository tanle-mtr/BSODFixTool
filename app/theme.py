#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""设计令牌与字体解析。

令牌全部来自产品证据推导（诊断控制台 / 离线 PE 工具），
不含 Fantasy Mouse 参考构图的纸纹、胶带、粗描边等风格要素。
"""

from __future__ import annotations

import ctypes
import tkinter.font as tkfont
from dataclasses import dataclass


class T:
    """颜色与尺寸令牌。"""

    # 表面分层
    bg = "#0b1020"
    surface = "#101830"
    surface_alt = "#16203c"
    elevated = "#1a2444"
    border = "#25325a"
    border_soft = "#1c2748"

    # 文本
    text = "#e9eefb"
    text_dim = "#9fadd0"
    text_faint = "#8a99bd"

    # 语义色
    primary = "#5b8cff"
    primary_hover = "#4a7cf6"
    primary_active = "#3b68dd"
    success = "#34d399"
    warning = "#fbbf24"
    danger = "#f87171"
    info = "#38bdf8"
    idle = "#64748b"

    # 形状与动效
    radius = 12
    radius_sm = 8
    row_height = 46
    appbar_height = 76
    left_width = 404
    motion_ms = 150


@dataclass
class FontSet:
    base: str
    mono: str
    has_cjk: bool
    families: tuple[str, ...]

    def make(self, size: int, weight: str = "normal") -> tuple[str, int, str]:
        return (self.base, size, weight)

    def mono_make(self, size: int, weight: str = "normal") -> tuple[str, int, str]:
        return (self.mono, size, weight)


CJK_CANDIDATES = (
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "微软雅黑",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "PingFang SC",
    "SimHei",
    "黑体",
    "SimSun",
    "宋体",
    "DengXian",
    "等线",
)
LATIN_CANDIDATES = ("Segoe UI", "Tahoma", "Verdana", "Arial", "Helvetica")
MONO_CANDIDATES = ("Cascadia Mono", "Consolas", "Lucida Console", "Courier New", "DejaVu Sans Mono")


def resolve_fonts(root) -> FontSet:
    families = tuple(sorted(set(tkfont.families(root))))
    known = set(families)
    cjk = next((name for name in CJK_CANDIDATES if name in known), None)
    latin = next((name for name in LATIN_CANDIDATES if name in known), None)
    mono = next((name for name in MONO_CANDIDATES if name in known), "Courier New")
    base = cjk or latin or "TkDefaultFont"
    return FontSet(base=base, mono=mono, has_cjk=cjk is not None, families=families)


_FONTS: FontSet | None = None


def init_fonts(root) -> FontSet:
    """在应用启动时探测可用字族（含 WinPE 常见的中文字体缺失场景）。"""
    global _FONTS
    _FONTS = resolve_fonts(root)
    return _FONTS


def current_fonts() -> FontSet | None:
    return _FONTS


def ui(size: int = 11, weight: str = "normal") -> tuple[str, int, str]:
    return (_FONTS.base, size, weight) if _FONTS else ("Segoe UI", size, weight)


def mono(size: int = 11, weight: str = "normal") -> tuple[str, int, str]:
    return (_FONTS.mono, size, weight) if _FONTS else ("Consolas", size, weight)


def reduced_motion() -> bool:
    """读取系统的“减少动态效果”设置，供动效降级使用。"""
    try:
        enabled = ctypes.c_int()
        ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)
        return enabled.value == 0
    except Exception:  # noqa: BLE001
        return False


def severity_color(text: str) -> str:
    """把站点给出的严重度文案映射成语义色。"""
    value = (text or "").strip()
    if not value:
        return T.idle
    if value.startswith("高") or "进不了系统" in value:
        return T.danger
    if value.startswith("中"):
        return T.warning
    if value.startswith("低"):
        return T.info
    return T.idle
