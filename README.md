# 蓝屏代码查询与修复工具 v2.0

完全离线的 Windows 蓝屏查询 + 引导修复工具。内置 73 条蓝屏数据，单文件可执行，零外部依赖，可在 64 位 WinPE / WinRE U 盘中直接运行。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/tanle-mtr/BSODFixTool?label=release)](https://github.com/tanle-mtr/BSODFixTool/releases)
[![CI](https://github.com/tanle-mtr/BSODFixTool/actions/workflows/build.yml/badge.svg)](https://github.com/tanle-mtr/BSODFixTool/actions/workflows/build.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)

## 快速开始

**下载即用（推荐）**：到 [Releases](https://github.com/tanle-mtr/BSODFixTool/releases) 下载 `BSODFixTool_v2.0.zip`，解压后把 `BSODFixTool.exe` 放进 64 位 PE U 盘即可运行，无需安装任何运行库。

**从源码运行**：

```bash
git clone https://github.com/tanle-mtr/BSODFixTool.git
cd BSODFixTool
py -3.10 main.py
```

**自行打包**（需要 Python 3.10 + PyInstaller）：

```bash
build.bat          # Windows
python tools/derive_assets.py   # 如需重新派生鼠鼠素材与图标
python tools/verify_offline.py  # 离线与依赖自检
python tools/smoke_test.py       # 主链路自测（演练模式，不改系统）
```


## 界面（Fantasy Mouse UI · Strict 模式设计）

- 深色「诊断控制台」视觉体系：应用栏 + 左侧代码列表 + 右侧详情 + 全屏修复台。
- 鼠鼠角色参与：应用栏与详情卡使用默认交叠手形象；修复台切换为「安全帽 + 检修杆」动作形象（胸前 V/U 完全移除，只保留一双与道具真实接触的手）。
- 所有按钮为自绘圆角控件，悬停 / 按下 / 恢复均有缓出过渡动画，支持禁用态与键盘焦点环。
- 列表行悬停高亮、状态胶囊（环境 / 权限 / 固件 / 严重度）、等宽代码与命令终端。
- 支持 `Ctrl+F` 聚焦搜索、`Esc` 关闭修复台、Tab 键盘遍历。

## 功能

- 按代码 / 名称 / 分类 / 原因关键词检索 73 条蓝屏条目。
- 每个条目包含：概要、快速检查、参数含义、常见原因、排查步骤、风险提示、FAQ、相关代码。
- 修复中心按蓝屏类型推荐方案：
  - 引导与磁盘：`chkdsk` + BCD 备份 + `bcdboot` / `bootrec` 引导重建
  - 系统文件：`chkdsk` + 离线 `sfc` + `dism /RestoreHealth`
  - 注册表：先备份 `SYSTEM/SOFTWARE/SAM/SECURITY/DEFAULT`
  - 硬件 / 内存 / 显卡：只给排查指引，不做虚假的一键修复承诺
- **一键修复蓝屏与引导**：备份 → 文件系统 → 系统文件 → 引导重建（UEFI / BIOS 自动适配），缺命令自动跳过。
- 演练模式：只打印将要执行的命令，不修改系统。
- 执行日志实时输出，可保存；结束生成修复报告。
- 破坏性操作前二次确认，逐条列出命令与风险等级。

## 离线 / 零依赖 / PE

| 项目 | 说明 |
| --- | --- |
| 离线 | 运行期不发起任何网络请求（`tools/verify_offline.py` 静态扫描 6 个运行期模块，0 个网络依赖） |
| 零依赖 | 单文件 EXE 内置 Python 运行时、Tk、数据与素材，目标机无需安装任何运行库 |
| 数据 | `bsod_data.json` 73 条，随包内嵌 |
| PE | 仅使用 Windows 自带命令；自动识别 WinPE 与 UEFI/BIOS；缺 `bootrec` 等命令时自动跳过并写明原因；PE 缺中文字体时状态栏告警；窗口高度随屏幕自适应 |

### PE 使用

1. 把 `BSODFixTool.exe` 复制到 64 位 PE U 盘。
2. 从 U 盘启动进入 WinPE，运行该 exe。
3. 顶部「一键修复蓝屏与引导」→ 确认系统盘 / 固件 / 备份目录 → 执行。
4. 完成后重启并拔出 U 盘。

## 源码结构

```
main.py                应用入口、布局、修复台调度
app/theme.py           设计令牌与字体探测（含 PE 中文字体缺失处理）
app/widgets.py         自绘控件：动画按钮、胶囊、卡片、行列表、滚动区、富文本、鼠鼠立绘
app/views.py           三个视图：代码浏览器 / 代码详情 / 修复台
app/assets/            鼠鼠状态素材与软件图标（PNG + ICO）
repair_engine.py       环境识别、卷扫描、备份、命令执行与降级
scraper.py             构建期抓取脚本（联网，不打包进运行期）
tools/derive_assets.py 素材派生：背景去除 / 裁切 / 图标合成
tools/verify_offline.py 离线与依赖自检
tools/smoke_test.py     主链路自测（全程演练模式，不改系统）
design/                工作流简报、项目档案、设计推导与 QA 证据
build.bat              重新打包脚本（需要 Python 3.10 + PyInstaller）
```

## 重新构建

```
build.bat          # py -3.10 -m PyInstaller，生成 dist\BSODFixTool.exe
python tools/verify_offline.py
python tools/smoke_test.py
```

## 数据来源与免责声明

蓝屏条目抓取自 https://www.3z9w.com/bsod 及其代码库详情页，快照时间见 `bsod_data.json` 的 `scraped_at`。

界面中的鼠鼠形象由 Fantasy Mouse UI 插件素材派生（插件代码 MIT；素材源自网络梗图二次创作，原作者与原始授权未确认），仅用于本机工具界面。

任何系统修复都有风险：执行前请备份重要数据；引导修复会写入引导扇区；BitLocker 需先解锁；内存、硬盘、供电、主板等硬件故障无法靠命令修复。

## 许可证

代码以 **MIT** 许可证发布（见 [`LICENSE`](LICENSE)）。

仓库内同时包含**非本项目原创**的内容，其权利归属与 MIT 授权相互独立，请先阅读 [`NOTICE.md`](NOTICE.md)：

- `bsod_data.json`：来自 3z9w.com 的离线数据快照，内容权利属于来源站点，本项目仅附出处收录。
- `app/assets/*.png`：由 [Fantasy Mouse UI](https://github.com/LaoFeng-mouse/fantasy-mouse-ui) 素材派生的鼠鼠形象与应用图标，原始作者与授权未确认，不在 MIT 授权范围内。

## 贡献

欢迎提交 Issue 与 PR。改动请保持：

- 运行期**不得引入网络依赖**（`tools/verify_offline.py` 会扫描拦截）。
- 修复类改动必须保持「先备份、二次确认、可演练」三条底线。
- 界面改动请同步更新 `design/` 下的工作流简报与 QA 证据。

