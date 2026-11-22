#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主链路自测：查询 → 详情 → 修复台 → 一键修复（演练模式）。

演练模式只打印命令，不会修改系统。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import main as appmain  # noqa: E402


def check(label: str, condition: bool, detail: str = "") -> None:
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        raise SystemExit(1)


def main() -> int:
    app = appmain.App()
    app.withdraw()
    app.update()

    deadline = time.time() + 20
    while not app.ctx.system_drive and time.time() < deadline:
        app.update()
        time.sleep(0.1)
    app.update()
    check("环境扫描完成", bool(app.ctx.system_drive), f"系统盘 {app.ctx.system_drive} / 固件 {app.ctx.firmware}")

    check("内置数据加载", len(app.entries) == 73, f"{len(app.entries)} 条")
    check("默认选中首条", app.current is not None and app.current["code"] == "0x0000000A")

    app.browser.var_query.set("0x0000007B")
    app.update()
    check("代码搜索", app.current["code"] == "0x0000007B", app.current["name"])

    app.browser.var_query.set("MEMORY_MANAGEMENT")
    app.update()
    check("名称搜索", app.current["name"] == "MEMORY_MANAGEMENT", app.current["code"])

    app.browser.var_query.set("")
    app.update()
    app.browser._on_chip("存储与文件系统")
    app.update()
    check("分类筛选", all(e["category"] == "存储与文件系统" for e in app._matched),
          f"{len(app._matched)} 条")

    app._select_code("0x0000007B")
    app.update()
    app.detail._set_tab(1)
    app.update()
    check("详情标签切换", "排查步骤" in app.detail.text.content())
    app.detail._set_tab(0)
    app.update()
    check("原因分析内容", "常见原因" in app.detail.text.content())

    app._open_bench()
    app.update()
    check("修复台打开", app._bench is not None and len(app._bench._steps) > 0,
          f"{len(app._bench._steps)} 个步骤")
    check("推荐方案匹配", app._bench.plan_title.cget("text") == "引导与磁盘一键修复",
          app._bench.plan_title.cget("text"))

    app._open_bench_one_click()
    app.update()
    check("一键修复方案", len(app._bench._steps) == 11, f"{len(app._bench._steps)} 步")

    app._bench.var_dry.set(True)
    app._run_one_click()
    deadline = time.time() + 25
    while app.running and time.time() < deadline:
        app.update()
        time.sleep(0.05)
    app.update()
    log = app._bench.log.content()
    check("演练执行完成", "[演练]" in log, f"{len(log.splitlines())} 行日志")
    check("演练不改动系统", "[OK]" not in log and "命令退出码" not in log)
    check("日志包含引导命令", "bcdboot" in log and "bootrec" in log)

    binding = app.bind("<Control-f>")
    app._focus_search()
    check("快捷键聚焦搜索框", "_focus_search" in binding and app.focus_get() is not None,
          f"binding={'ok' if '_focus_search' in binding else 'missing'}")

    app.destroy()
    print("\n全部主链路自测通过（全程未修改系统）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
