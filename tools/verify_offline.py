#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离线与依赖自检：确认运行期代码不发起网络请求，且数据/素材随包内置。

用法：python tools/verify_offline.py [项目根目录]
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

RUNTIME_MODULES = [
    "main.py",
    "repair_engine.py",
    "app/theme.py",
    "app/widgets.py",
    "app/views.py",
    "app/__init__.py",
]
NET_MODULES = {
    "urllib", "urllib2", "http", "http.client", "requests", "socket", "ssl",
    "ftplib", "telnetlib", "smtplib", "xmlrpc", "aiohttp", "httpx", "websockets",
    "urllib.request", "urllib.parse",
}
OFFLINE_BUILD_ONLY = {"scraper.py"}


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    problems: list[str] = []
    checked = 0

    for rel in RUNTIME_MODULES:
        path = root / rel
        if not path.exists():
            problems.append(f"缺少运行期模块：{rel}")
            continue
        checked += 1
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in NET_MODULES or alias.name in NET_MODULES:
                        problems.append(f"{rel} 导入了网络模块 {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.split(".")[0] in NET_MODULES or module in NET_MODULES:
                    problems.append(f"{rel} 导入了网络模块 {module}")

    for rel in OFFLINE_BUILD_ONLY:
        path = root / rel
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        uses_network = any(
            (isinstance(n, ast.Import) and any(a.name.split(".")[0] in NET_MODULES for a in n.names))
            or (isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] in NET_MODULES)
            for n in ast.walk(tree)
        )
        print(f"[构建期工具] {rel} 使用网络：{'是' if uses_network else '否'}（不打包进运行期）")

    data_path = root / "bsod_data.json"
    if not data_path.exists():
        problems.append("缺少 bsod_data.json")
    else:
        data = json.loads(data_path.read_text(encoding="utf-8"))
        print(f"[内置数据] 条目数 {data.get('count')}，快照 {data.get('scraped_at')}")
        if not data.get("entries"):
            problems.append("内置数据为空")

    assets = root / "app" / "assets"
    required = [
        "mascot_idle_48.png", "mascot_idle_56.png", "mascot_idle_200.png", "mascot_idle_260.png",
        "mascot_action_220.png", "mascot_action_300.png", "app_icon.png", "app_icon.ico",
    ]
    for name in required:
        if not (assets / name).exists():
            problems.append(f"缺少素材 {name}")
    print(f"[内置素材] {assets} 共 {len(list(assets.glob('*.png')))} 个 PNG")

    print(f"[运行期模块] 检查 {checked} 个，未发现网络依赖" if not problems else "")
    if problems:
        print("[失败]")
        for item in problems:
            print("  -", item)
        return 1
    print("[通过] 运行期零网络依赖，数据与素材均随包内置")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
