#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打包发布件：单文件 EXE + 文档 + 图标 + 截图 + 设计档案 + 可编辑源码。"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

def _force_utf8_stdout() -> None:
    """CI 控制台默认是 cp1252，强制 UTF-8 输出，避免中文日志直接崩掉。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


_force_utf8_stdout()

BASE = Path(__file__).resolve().parent.parent
ROOT = BASE.parent
RELEASE = ROOT / "BSODFixTool_v2.0_发布版"
ZIP = ROOT / "BSODFixTool_v2.0.zip"


def copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> None:
    if RELEASE.exists():
        shutil.rmtree(RELEASE)
    RELEASE.mkdir(parents=True)

    copy(BASE / "dist" / "BSODFixTool.exe", RELEASE / "BSODFixTool.exe")
    copy(BASE / "README.md", RELEASE / "README.md")
    copy(BASE / "run_pe.cmd", RELEASE / "run_pe.cmd")
    copy(BASE / "app" / "assets" / "app_icon.png", RELEASE / "app_icon.png")
    copy(BASE / "app" / "assets" / "app_icon.ico", RELEASE / "app_icon.ico")

    shots = RELEASE / "界面截图"
    copy(ROOT / "ui_v2_exe.png", shots / "主界面.png")
    copy(ROOT / "ui_v2_bench.png", shots / "修复台.png")

    design = RELEASE / "design"
    for name in ("workflow-brief.json", "mouse-ui-project.json", "design-notes.md", "qa-comparison.png"):
        copy(BASE / "design" / name, design / name)

    src = RELEASE / "source"
    copy(BASE / "main.py", src / "main.py")
    copy(BASE / "repair_engine.py", src / "repair_engine.py")
    copy(BASE / "scraper.py", src / "scraper.py")
    copy(BASE / "bsod_data.json", src / "bsod_data.json")
    copy(BASE / "build.bat", src / "build.bat")
    shutil.copytree(BASE / "app", src / "app",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(BASE / "tools", src / "tools",
                    ignore=shutil.ignore_patterns("__pycache__"))

    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(RELEASE.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(RELEASE.parent))

    with zipfile.ZipFile(ZIP) as z:
        assert z.testzip() is None
        print(f"发布包文件数 {len(z.namelist())}")
    print(f"EXE {round((RELEASE / 'BSODFixTool.exe').stat().st_size / 1024 / 1024, 1)} MB")
    print(f"ZIP {ZIP} {round(ZIP.stat().st_size / 1024 / 1024, 1)} MB")


if __name__ == "__main__":
    main()
