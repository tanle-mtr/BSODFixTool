#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 Fantasy Mouse UI 插件的已授权素材派生本项目使用的鼠鼠状态素材与软件图标。

只做「背景去除 / 裁切 / 缩放 / 合成底板」，不重绘角色解剖结构。
用法：python tools/derive_assets.py <插件根目录> [输出目录]
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

PLUGIN_ASSETS = Path("assets/visual-grounding")
BG_KEY = (255, 0, 255, 255)


def strip_background(src: Path) -> Image.Image:
    img = Image.open(src).convert("RGBA")
    work = img.copy()
    w, h = work.size
    for corner in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        px = work.getpixel(corner)
        if px[:3] == BG_KEY[:3]:
            continue
        ImageDraw.floodfill(work, corner, BG_KEY, thresh=42)
    px = work.load()
    out = img.load()
    for y in range(h):
        for x in range(w):
            if px[x, y][:3] == BG_KEY[:3]:
                out[x, y] = (0, 0, 0, 0)
    bbox = img.getbbox()
    return img.crop(bbox) if bbox else img


def fit_height(img: Image.Image, height: int) -> Image.Image:
    ratio = height / img.height
    return img.resize((max(1, int(img.width * ratio)), height), Image.LANCZOS)


def rounded_badge(size: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    badge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    grad = Image.new("RGBA", (size, size))
    draw = ImageDraw.Draw(grad)
    for y in range(size):
        t = y / max(1, size - 1)
        color = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,)
        draw.line([(0, y), (size, y)], fill=color)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=255)
    badge.paste(grad, (0, 0), mask)
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse([size * 0.08, size * 0.02, size * 0.92, size * 0.72], fill=(120, 140, 255, 46))
    glow = glow.filter(ImageFilter.GaussianBlur(size * 0.10))
    badge.alpha_composite(glow)
    return badge


def build_icon(mascot: Image.Image, size: int = 1024) -> Image.Image:
    badge = rounded_badge(size, (79, 70, 229), (13, 18, 32))
    ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    rdraw = ImageDraw.Draw(ring)
    rdraw.ellipse(
        [size * 0.10, size * 0.10, size * 0.90, size * 0.90],
        outline=(165, 180, 252, 70),
        width=max(2, size // 220),
    )
    rdraw.ellipse(
        [size * 0.20, size * 0.20, size * 0.80, size * 0.80],
        outline=(165, 180, 252, 40),
        width=max(2, size // 300),
    )
    badge.alpha_composite(ring)
    char = fit_height(mascot, int(size * 0.70))
    x = (size - char.width) // 2
    y = int(size * 0.145)
    badge.alpha_composite(char, (x, y))
    edge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(edge).rounded_rectangle(
        [size * 0.045, size * 0.045, size * 0.955, size * 0.955],
        radius=int(size * 0.21),
        outline=(165, 180, 252, 130),
        width=max(2, size // 200),
    )
    badge.alpha_composite(edge)
    return badge


def main() -> None:
    plugin_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        r"C:\Users\Administrator\.workbuddy\skills\fantasy-mouse-ui"
    )
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent.parent / "app" / "assets"
    out_dir.mkdir(parents=True, exist_ok=True)

    idle_src = plugin_root / PLUGIN_ASSETS / "canonical-protagonist.png"
    action_src = plugin_root / PLUGIN_ASSETS / "processing-action-hands.png"

    idle = fit_height(strip_background(idle_src), 640)
    idle.save(out_dir / "mascot_idle.png")
    print("idle", idle.size)
    for height in (48, 56, 200, 260):
        fit_height(idle, height).save(out_dir / f"mascot_idle_{height}.png")

    action = fit_height(strip_background(action_src), 640)
    action.save(out_dir / "mascot_action.png")
    print("action", action.size)
    for height in (220, 300):
        fit_height(action, height).save(out_dir / f"mascot_action_{height}.png")

    icon = build_icon(idle)
    icon.save(out_dir / "app_icon.png")
    icon.resize((256, 256), Image.LANCZOS).save(
        out_dir / "app_icon.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print("icon", icon.size, "ico written")


if __name__ == "__main__":
    main()
