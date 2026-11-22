#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证图标：EXE 文件图标 + 运行中窗口标题栏/任务栏图标。

用 ctypes 直接读 PE 资源与窗口 WM_GETICON，再转成 PNG 供肉眼核对。
"""

from __future__ import annotations

import ctypes
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "dist" / "BSODFixTool.exe"
OUT = ROOT.parent

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32

WM_GETICON = 0x007F
ICON_BIG = 1
ICON_SMALL = 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD), ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP), ("hbmColor", wintypes.HBITMAP),
    ]


def hicon_to_png(hicon, path: Path) -> tuple[int, int] | None:
    if not hicon:
        return None
    info = ICONINFO()
    if not user32.GetIconInfo(hicon, ctypes.byref(info)):
        return None
    hbm = info.hbmColor or info.hbmMask
    if not hbm:
        return None
    width = gdi32.GetObjectW(hbm, 0, None)
    height = gdi32.GetObjectW(hbm, 0, None)
    header = BITMAPINFOHEADER()
    header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    header.biWidth = width
    header.biHeight = -height  # 负数表示自上而下
    header.biPlanes = 1
    header.biBitCount = 32
    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(hbm, 0, height, buffer, ctypes.byref(header), 0)
    img = Image.frombuffer("RGBA", (width, height), buffer, "raw", "BGRA", 0, 1)
    img.save(path)
    user32.DestroyIcon(hicon)
    return width, height


def extract_exe_icon() -> None:
    large = wintypes.HICON()
    small = wintypes.HICON()
    count = shell32.ExtractIconExW(str(EXE), 0, ctypes.byref(large), ctypes.byref(small), 1)
    print(f"[EXE] ExtractIconEx 返回 {count} 个图标")
    size = hicon_to_png(large, OUT / "exe_icon_large.png")
    print(f"[EXE] 大图标 {size} -> exe_icon_large.png")
    size = hicon_to_png(small, OUT / "exe_icon_small.png")
    print(f"[EXE] 小图标 {size} -> exe_icon_small.png")


def check_window_icon() -> None:
    proc = subprocess.Popen([str(EXE)])
    hwnd = None
    for _ in range(60):
        hwnd = user32.FindWindowW(None, "蓝屏代码查询与修复工具 v2.0")
        if hwnd:
            break
        time.sleep(0.3)
    if not hwnd:
        print("[窗口] 未找到主窗口")
        proc.terminate()
        return
    time.sleep(1.2)
    for label, kind in (("大", ICON_BIG), ("小", ICON_SMALL)):
        hicon = user32.SendMessageW(hwnd, WM_GETICON, kind, 0)
        size = hicon_to_png(hicon, OUT / f"window_icon_{label}.png")
        print(f"[窗口] {label}图标 WM_GETICON -> {size}")
    if user32.GetClassLongPtrW(hwnd, -14):
        hicon = user32.GetClassLongPtrW(hwnd, -14)
        size = hicon_to_png(hicon, OUT / "window_icon_class.png")
        print(f"[窗口] 类图标 -> {size}")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


if __name__ == "__main__":
    extract_exe_icon()
    check_window_icon()
