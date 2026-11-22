#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蓝屏修复引擎：环境识别、卷扫描、命令预览与安全执行。

重要：本模块只调用 Windows 自带的 chkdsk / sfc / dism / bcdboot / bootrec /
bcdedit / diskpart 等工具，不做格式化、分区删除等高危操作。所有引导修改前
会先备份 BCD 与注册表配置单元；是否执行由 GUI 明确确认。
"""

from __future__ import annotations

import copy
import ctypes
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

Logger = Callable[[str, str], None]  # (level, message)

RISK_TEXT = {"low": "低", "medium": "中", "high": "高"}


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #
@dataclass
class Volume:
    number: str
    letter: str
    label: str
    fs: str
    size: str
    status: str
    info: str = ""

    @property
    def text(self) -> str:
        letter = self.letter or "无盘符"
        return f"卷{self.number}  {letter:<5} {self.fs:<6} {self.size:<9} {self.label} {self.info}".rstrip()


@dataclass
class Context:
    system_drive: str = ""
    efi_drive: str = ""
    firmware: str = "AUTO"          # AUTO / UEFI / BIOS
    backup_dir: str = ""
    dry_run: bool = False
    winpe: bool = False
    efi_volume_number: str = ""
    assigned_efi_letter: str = ""
    volumes: list[Volume] = field(default_factory=list)


@dataclass
class StepResult:
    id: str
    title: str
    status: str                      # ok / skipped / failed
    message: str
    output: str = ""


@dataclass
class Step:
    id: str
    title: str
    detail: str
    risk: str = "low"
    needs_system: bool = True
    needs_efi: bool = False
    firmware: str = ""               # 空表示不限；否则仅 UEFI/BIOS
    optional: bool = False
    action: str = "cmd"              # cmd / backup_bcd / backup_registry / assign_efi / remove_efi
    timeout: int = 1800
    stdin: str = ""
    fallback: str = ""
    command: Callable[[Context], list[str]] = field(default=lambda ctx: [])

    def preview(self, ctx: Context) -> list[str]:
        try:
            return self.command(ctx)
        except Exception as exc:  # noqa: BLE001
            return [f"# 无法生成命令：{exc}"]


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def drive(path: str) -> str:
    """返回 C:\\ 形式。"""
    path = (path or "").strip().rstrip("\\/")
    return path + "\\" if path else ""


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:  # noqa: BLE001
        return False


def detect_winpe() -> bool:
    markers = [
        r"X:\Windows\System32\winpeshl.exe",
        r"X:\Windows\System32\startnet.cmd",
        r"X:\Windows\System32\winpe.dll",
    ]
    root = os.environ.get("SystemRoot", "").upper()
    return root.startswith("X:\\") or any(os.path.exists(p) for p in markers)


def _run_capture(args: list[str], timeout: int = 60) -> str:
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="cp936",
        errors="replace",
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
    )
    return proc.stdout or ""


def _parse_volume_line(line: str) -> Volume | None:
    stripped = line.strip()
    if not re.match(r"^(卷|Volume)\s+\d+", stripped, re.I):
        return None
    parts = re.split(r"\s{2,}", stripped)
    if len(parts) < 4:
        return None
    rest = parts[2:]
    fs_idx = -1
    for i, token in enumerate(rest):
        if re.fullmatch(r"(NTFS|FAT32|FAT|exFAT|ReFS)", token, re.I):
            fs_idx = i
            break
    if fs_idx < 0:
        return None
    fs = rest[fs_idx].upper()
    letter = ""
    label_tokens = rest[:fs_idx]
    if label_tokens and re.fullmatch(r"[A-Z]", label_tokens[0], re.I):
        letter = label_tokens[0].upper()
        label_tokens = label_tokens[1:]
    label = " ".join(label_tokens).strip()
    after = rest[fs_idx + 1:]
    type_ = after[0].strip() if len(after) > 0 else ""
    size = after[1].strip() if len(after) > 1 else ""
    status = after[2].strip() if len(after) > 2 else ""
    info = " ".join(after[3:]).strip() if len(after) > 3 else ""
    return Volume(
        number=parts[1],
        letter=letter,
        label=label,
        fs=fs,
        size=size,
        status=status,
        info=info,
    )


def scan_volumes(logger: Logger | None = None) -> list[Volume]:
    """用 diskpart 只读列出卷；失败时回退到盘符探测。"""
    defsay = logger or (lambda *_: None)
    try:
        script = Path(tempfile.gettempdir()) / f"bsodfix_listvol_{os.getpid()}.txt"
        script.write_text("list volume\nexit\n", encoding="ascii")
        out = _run_capture(["diskpart", "/s", str(script)])
        vols = [v for line in out.splitlines() if (v := _parse_volume_line(line))]
        if vols:
            return vols
        defsay("warn", "diskpart 未返回可解析的卷列表，已切换到盘符探测。")
    except Exception as exc:  # noqa: BLE001
        defsay("warn", f"diskpart 不可用（{exc}），已切换到盘符探测。")

    vols: list[Volume] = []
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZAB":
        p = f"{letter}:\\"
        if os.path.exists(p):
            try:
                fs = "NTFS" if os.path.exists(os.path.join(p, "$MFT")) else "UNKNOWN"
            except Exception:  # noqa: BLE001
                fs = "UNKNOWN"
            vols.append(Volume(number="?", letter=letter, label="", fs=fs, size="", status=""))
    return vols


def find_windows_drives(volumes: Iterable[Volume]) -> list[str]:
    result: list[str] = []
    for vol in volumes:
        if not vol.letter:
            continue
        marker = os.path.join(f"{vol.letter}:\\", "Windows", "System32", "config", "SYSTEM")
        if os.path.exists(marker):
            result.append(vol.letter + ":")
    # 兜底：diskpart 没列出来时逐个盘符探测
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZAB":
        drive_ = letter + ":"
        if drive_ in result:
            continue
        marker = os.path.join(drive_ + "\\", "Windows", "System32", "config", "SYSTEM")
        if os.path.exists(marker):
            result.append(drive_)
    return result


def _size_to_mb(size: str) -> float:
    m = re.search(r"([\d.]+)\s*(GB|MB|KB|B)", size or "", re.I)
    if not m:
        return 0.0
    value = float(m.group(1))
    unit = m.group(2).upper()
    return {"GB": value * 1024, "MB": value, "KB": value / 1024, "B": value / 1048576}[unit]


def find_efi_volume(volumes: Iterable[Volume]) -> Volume | None:
    candidates = []
    for vol in volumes:
        info = (vol.info or "").lower()
        size_mb = _size_to_mb(vol.size)
        if "efi" in info or ("fat" in vol.fs.lower() and 0 < size_mb <= 1024):
            candidates.append(vol)
    if not candidates:
        return None
    # 优先有盘符的、信息里明确写 EFI 的
    candidates.sort(key=lambda v: (not bool(v.letter), "efi" not in (v.info or "").lower()))
    return candidates[0]


def detect_firmware(ctx: Context, volumes: Iterable[Volume]) -> str:
    env_fw = (os.environ.get("firmware_type") or "").strip().upper()
    if env_fw in {"UEFI", "BIOS"}:
        return env_fw
    if ctx.efi_drive and os.path.exists(os.path.join(drive(ctx.efi_drive), "EFI", "Microsoft", "Boot", "bootmgfw.efi")):
        return "UEFI"
    if find_efi_volume(volumes):
        return "UEFI"
    if ctx.system_drive and os.path.exists(os.path.join(drive(ctx.system_drive), "Boot", "BCD")):
        return "BIOS"
    return "AUTO"


def pick_free_letter() -> str:
    for letter in "SYWZFO":
        if not os.path.exists(letter + ":\\"):
            return letter + ":"
    return ""


def make_backup_dir(ctx: Context) -> str:
    base = drive(ctx.system_drive) if ctx.system_drive else os.getcwd()
    if not os.access(base, os.W_OK):
        base = os.getcwd()
    path = Path(base) / "BSODFixBackups" / datetime.now().strftime("%Y%m%d-%H%M%S")
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def bcd_file(ctx: Context) -> Path:
    if ctx.firmware == "UEFI" and ctx.efi_drive:
        return Path(drive(ctx.efi_drive)) / "EFI" / "Microsoft" / "Boot" / "BCD"
    return Path(drive(ctx.system_drive)) / "Boot" / "BCD"


def _split_command(text: str) -> list[str]:
    tokens = shlex.split(text, posix=False)
    cleaned: list[str] = []
    for token in tokens:
        if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
            token = token[1:-1]
        cleaned.append(token)
    return cleaned


def run_command(cmd: list[str], logger: Logger, *, timeout: int = 1800, stdin: str = "") -> tuple[int, str]:
    exe = cmd[0]
    if not shutil.which(exe) and not os.path.exists(exe):
        raise FileNotFoundError(f"找不到命令：{exe}（当前环境可能不是 PE/WinRE）")
    logger("cmd", "> " + " ".join(f'"{a}"' if " " in a else a for a in cmd))
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE if stdin else subprocess.DEVNULL,
        text=True,
        encoding="cp936",
        errors="replace",
        bufsize=1,
        creationflags=CREATE_NO_WINDOW,
    )
    if stdin and proc.stdin:
        try:
            proc.stdin.write(stdin)
            proc.stdin.flush()
        finally:
            proc.stdin.close()
    lines: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip("\r\n")
        if line:
            lines.append(line)
            logger("out", line)
    try:
        rc = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        raise RuntimeError(f"命令超时（{timeout} 秒）：{exe}")
    if rc != 0:
        logger("warn", f"命令返回非零退出码：{rc}")
    return rc, "\n".join(lines)


# --------------------------------------------------------------------------- #
# 修复步骤定义
# --------------------------------------------------------------------------- #
def _backup_root(ctx: Context) -> str:
    return drive(ctx.backup_dir) if ctx.backup_dir else "<备份目录>\\"


def _backup_bcd_cmd(ctx: Context) -> list[str]:
    return [f"复制 {bcd_file(ctx)} -> {_backup_root(ctx)}BCD-backup"]


def _backup_registry_cmd(ctx: Context) -> list[str]:
    src = Path(drive(ctx.system_drive)) / "Windows" / "System32" / "config"
    return [f"复制 {src}\\SYSTEM|SOFTWARE|SAM|SECURITY|DEFAULT -> {_backup_root(ctx)}Registry"]


def _assign_efi_cmd(ctx: Context) -> list[str]:
    letter = ctx.assigned_efi_letter or pick_free_letter()
    return [f"diskpart: select volume {ctx.efi_volume_number} -> assign letter={letter}"]


def _remove_efi_cmd(ctx: Context) -> list[str]:
    return [f"diskpart: select volume {ctx.efi_volume_number} -> remove letter={ctx.assigned_efi_letter}"]


STEPS: dict[str, Step] = {
    "backup_bcd": Step(
        id="backup_bcd",
        title="备份引导配置 BCD",
        detail="修改引导前先复制现有 BCD，可回退。",
        risk="low",
        action="backup_bcd",
        command=_backup_bcd_cmd,
    ),
    "backup_registry": Step(
        id="backup_registry",
        title="备份注册表配置单元",
        detail="复制 SYSTEM/SOFTWARE/SAM/SECURITY/DEFAULT，适合 0xC0000218 一类故障。",
        risk="low",
        action="backup_registry",
        optional=True,
        command=_backup_registry_cmd,
    ),
    "chkdsk": Step(
        id="chkdsk",
        title="检查并修复文件系统",
        detail="chkdsk /f，修复逻辑错误；PE 下可直接执行。",
        risk="medium",
        command=lambda ctx: [f"chkdsk {drive(ctx.system_drive)} /f"],
    ),
    "chkdsk_deep": Step(
        id="chkdsk_deep",
        title="深度磁盘检查（慢）",
        detail="chkdsk /f /r，扫描坏扇区，耗时可能很长。",
        risk="medium",
        optional=True,
        timeout=7200,
        command=lambda ctx: [f"chkdsk {drive(ctx.system_drive)} /f /r"],
    ),
    "sfc_offline": Step(
        id="sfc_offline",
        title="离线系统文件检查",
        detail="sfc /scannow /offbootdir /offwindir，修复被替换的系统文件。",
        risk="low",
        command=lambda ctx: [
            f"sfc /scannow /offbootdir={drive(ctx.system_drive)} /offwindir={drive(ctx.system_drive)}Windows"
        ],
    ),
    "dism_restore": Step(
        id="dism_restore",
        title="DISM 组件存储修复",
        detail="离线 /RestoreHealth；可能需要网络或 Windows 安装介质。",
        risk="low",
        optional=True,
        timeout=3600,
        command=lambda ctx: [f"dism /image:{drive(ctx.system_drive)}Windows /cleanup-image /restorehealth"],
    ),
    "assign_efi": Step(
        id="assign_efi",
        title="为 EFI 分区临时分配盘符",
        detail="仅在 UEFI 且 EFI 分区无盘符时执行；修复结束后自动移除。",
        risk="medium",
        needs_efi=False,
        firmware="UEFI",
        action="assign_efi",
        command=_assign_efi_cmd,
    ),
    "bcdboot_uefi": Step(
        id="bcdboot_uefi",
        title="重建 UEFI 引导文件",
        detail="bcdboot 向 EFI 系统分区写入 bootmgfw.efi 与 BCD。",
        risk="medium",
        needs_efi=True,
        firmware="UEFI",
        fallback="bootrec_rebuild",
        command=lambda ctx: [f"bcdboot {drive(ctx.system_drive)}Windows /s {drive(ctx.efi_drive)} /f UEFI"],
    ),
    "bcdboot_bios": Step(
        id="bcdboot_bios",
        title="重建传统 BIOS 引导",
        detail="bcdboot 向系统分区写入 bootmgr 与 BCD。",
        risk="medium",
        firmware="BIOS",
        fallback="bootrec_rebuild",
        command=lambda ctx: [f"bcdboot {drive(ctx.system_drive)}Windows /s {drive(ctx.system_drive)} /f BIOS"],
    ),
    "bootrec_fixmbr": Step(
        id="bootrec_fixmbr",
        title="修复主引导记录 MBR",
        detail="bootrec /fixmbr，仅传统 BIOS 需要。",
        risk="medium",
        firmware="BIOS",
        command=lambda ctx: ["bootrec /fixmbr"],
    ),
    "bootrec_fixboot": Step(
        id="bootrec_fixboot",
        title="修复分区引导扇区",
        detail="bootrec /fixboot，仅传统 BIOS 需要。",
        risk="medium",
        firmware="BIOS",
        command=lambda ctx: ["bootrec /fixboot"],
        fallback="bootsect",
    ),
    "bootrec_rebuild": Step(
        id="bootrec_rebuild",
        title="扫描并重建 BCD",
        detail="bootrec /rebuildbcd，自动回答 Y 添加找到的 Windows。",
        risk="medium",
        firmware="BIOS",
        stdin="Y\n",
        command=lambda ctx: ["bootrec /rebuildbcd"],
    ),
    "bootsect": Step(
        id="bootsect",
        title="重写引导扇区（备用）",
        detail="bootsect /nt60 sys /mbr，bootrec /fixboot 失败时使用。",
        risk="high",
        firmware="BIOS",
        command=lambda ctx: [f"bootsect /nt60 {drive(ctx.system_drive)} /mbr"],
    ),
    "remove_efi": Step(
        id="remove_efi",
        title="移除 EFI 临时盘符",
        detail="恢复 EFI 分区原本无盘符的状态。",
        risk="low",
        action="remove_efi",
        firmware="UEFI",
        needs_efi=False,
        command=_remove_efi_cmd,
    ),
}

PLANS: dict[str, dict] = {
    "ONE_CLICK": {
        "name": "一键修复蓝屏与引导",
        "note": "备份 → 文件系统 → 系统文件 → 引导重建（UEFI / BIOS 自动适配），缺命令自动跳过。",
        "steps": [
            "backup_registry", "backup_bcd", "chkdsk", "assign_efi",
            "bcdboot_uefi", "bcdboot_bios", "bootrec_fixmbr", "bootrec_fixboot",
            "bootrec_rebuild", "sfc_offline", "remove_efi",
        ],
    },
    "BOOT_RESCUE": {
        "name": "引导与磁盘一键修复",
        "note": "适合进不了系统、0x7B/0xED、BCD 损坏、更新后无法启动。",
        "steps": [
            "backup_bcd", "chkdsk", "assign_efi", "bcdboot_uefi", "bcdboot_bios",
            "bootrec_fixmbr", "bootrec_fixboot", "bootrec_rebuild", "remove_efi",
        ],
    },
    "SYSTEM_REPAIR": {
        "name": "系统文件与磁盘修复",
        "note": "适合驱动/系统文件损坏类蓝屏；不会自动卸载驱动或删文件。",
        "steps": ["backup_bcd", "chkdsk", "sfc_offline", "dism_restore"],
    },
    "REGISTRY_RESCUE": {
        "name": "注册表故障修复",
        "note": "适合 0xC0000218 / 0xC000021A；先备份配置单元，再修系统文件。",
        "steps": ["backup_registry", "backup_bcd", "chkdsk", "sfc_offline", "dism_restore"],
    },
    "FULL_RESCUE": {
        "name": "全面修复（引导 + 系统文件）",
        "note": "步骤最多、耗时最长；建议先备份重要数据再执行。",
        "steps": [
            "backup_registry", "backup_bcd", "chkdsk", "assign_efi",
            "bcdboot_uefi", "bcdboot_bios", "bootrec_fixmbr", "bootrec_fixboot",
            "bootrec_rebuild", "sfc_offline", "dism_restore", "remove_efi",
        ],
    },
    "GUIDED_ONLY": {
        "name": "仅生成排查指引（不自动修复）",
        "note": "内存/硬件/显卡类蓝屏通常无法靠命令修复，请按页面步骤检查硬件或驱动。",
        "steps": [],
    },
}

BOOT_CODES = {
    "0x00000023", "0x00000024", "0x00000051", "0x0000007A", "0x0000007B",
    "0x000000ED", "0x000000F5", "0x00000154", "0x000001C7",
    "0xC0000218", "0xC000021A", "0xC0000221",
}


def recommend_plan(entry: dict | None) -> str:
    if not entry:
        return "GUIDED_ONLY"
    code = (entry.get("code") or "").upper()
    blob = " ".join(
        [
            entry.get("name", ""),
            entry.get("summary", ""),
            " ".join(c.get("title", "") + c.get("desc", "") for c in entry.get("causes", [])),
            " ".join(s.get("title", "") + s.get("desc", "") for s in entry.get("steps", [])),
        ]
    )
    if code in {"0XC0000218", "0XC000021A"} or "注册表" in blob:
        return "REGISTRY_RESCUE"
    if code in {c.upper() for c in BOOT_CODES} or any(
        k in blob for k in ("引导", "BCD", "启动盘", "无法启动", "文件系统", "分区表")
    ):
        return "BOOT_RESCUE"
    if any(k in blob for k in ("系统文件", "驱动", "IRQL", "补丁", "更新")):
        return "SYSTEM_REPAIR"
    return "GUIDED_ONLY"


def applicable(ctx: Context, step: Step) -> tuple[bool, str]:
    if step.needs_system and not ctx.system_drive:
        return False, "未选择系统盘"
    if step.needs_efi and not ctx.efi_drive:
        return False, "未识别到 EFI 分区盘符"
    if step.firmware and ctx.firmware not in ("AUTO", step.firmware):
        return False, f"仅适用于 {step.firmware}"
    if step.id == "assign_efi" and (ctx.efi_drive or not ctx.efi_volume_number):
        return False, "EFI 分区已有盘符或未识别到 EFI 分区"
    if step.id == "remove_efi" and not ctx.assigned_efi_letter:
        return False, "本次未分配临时盘符"
    return True, ""


# --------------------------------------------------------------------------- #
# 特殊动作
# --------------------------------------------------------------------------- #
def _copy_one(src: Path, dst_dir: Path, logger: Logger) -> bool:
    if not src.exists():
        logger("warn", f"跳过备份（文件不存在）：{src}")
        return False
    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
        target = dst_dir / src.name
        shutil.copy2(src, target)
        logger("ok", f"已备份：{target}")
        return True
    except Exception as exc:  # noqa: BLE001
        logger("error", f"备份失败：{src} -> {exc}")
        return False


def _do_backup_bcd(ctx: Context, logger: Logger) -> StepResult:
    src = bcd_file(ctx)
    dst = Path(drive(ctx.backup_dir))
    ok = _copy_one(src, dst, logger)
    # 再备份另一处常见位置，避免固件判断偏差
    other = (
        Path(drive(ctx.system_drive)) / "Boot" / "BCD"
        if ctx.firmware == "UEFI"
        else Path(drive(ctx.efi_drive)) / "EFI" / "Microsoft" / "Boot" / "BCD"
        if ctx.efi_drive
        else None
    )
    if other and other != src:
        ok = _copy_one(other, dst / "BCD-alt", logger) or ok
    return StepResult("backup_bcd", "备份引导配置 BCD", "ok" if ok else "skipped",
                      "已备份 BCD" if ok else "未找到可备份的 BCD 文件")


def _do_backup_registry(ctx: Context, logger: Logger) -> StepResult:
    src = Path(drive(ctx.system_drive)) / "Windows" / "System32" / "config"
    dst = Path(drive(ctx.backup_dir)) / "Registry"
    names = ["SYSTEM", "SOFTWARE", "SAM", "SECURITY", "DEFAULT"]
    count = sum(_copy_one(src / n, dst, logger) for n in names)
    return StepResult("backup_registry", "备份注册表配置单元", "ok" if count else "skipped",
                      f"已备份 {count}/{len(names)} 个配置单元")


def _diskpart_script(lines: list[str], logger: Logger) -> int:
    script = Path(tempfile.gettempdir()) / f"bsodfix_{os.getpid()}.txt"
    script.write_text("\n".join(lines + ["exit"]), encoding="ascii")
    rc, _ = run_command(["diskpart", "/s", str(script)], logger, timeout=120)
    return rc


def _do_assign_efi(ctx: Context, logger: Logger) -> StepResult:
    letter = ctx.assigned_efi_letter or pick_free_letter()
    if not letter:
        return StepResult("assign_efi", "分配 EFI 临时盘符", "failed", "没有可用的临时盘符")
    rc = _diskpart_script(
        [f"select volume {ctx.efi_volume_number}", f"assign letter={letter[:-1]}"], logger
    )
    if rc != 0:
        return StepResult("assign_efi", "分配 EFI 临时盘符", "failed", "diskpart 分配失败")
    ctx.efi_drive = letter
    ctx.assigned_efi_letter = letter
    return StepResult("assign_efi", "分配 EFI 临时盘符", "ok", f"EFI 分区已临时映射为 {letter}")


def _do_remove_efi(ctx: Context, logger: Logger) -> StepResult:
    if not ctx.assigned_efi_letter:
        return StepResult("remove_efi", "移除 EFI 临时盘符", "skipped", "本次未分配")
    rc = _diskpart_script(
        [f"select volume {ctx.efi_volume_number}", f"remove letter={ctx.assigned_efi_letter[:-1]}"], logger
    )
    if rc != 0:
        return StepResult("remove_efi", "移除 EFI 临时盘符", "failed", "diskpart 移除失败，可手动移除")
    ctx.efi_drive = ""
    ctx.assigned_efi_letter = ""
    return StepResult("remove_efi", "移除 EFI 临时盘符", "ok", "已移除临时盘符")


# --------------------------------------------------------------------------- #
# 执行器
# --------------------------------------------------------------------------- #
def preview_plan(ctx: Context, step_ids: Iterable[str]) -> list[str]:
    lines: list[str] = []
    sim = copy.copy(ctx)
    for sid in step_ids:
        step = STEPS.get(sid)
        if not step:
            continue
        ok, reason = applicable(sim, step)
        lines.append(f"\n## {step.title} [{RISK_TEXT.get(step.risk, step.risk)}风险]")
        if not ok:
            lines.append(f"# 跳过：{reason}")
            continue
        if step.id == "assign_efi" and sim.efi_volume_number and not sim.efi_drive:
            letter = pick_free_letter()
            sim.efi_drive = letter
            sim.assigned_efi_letter = letter
        for cmd in step.preview(sim):
            lines.append(cmd if cmd.startswith("#") else "> " + cmd)
        if step.id == "remove_efi" and sim.assigned_efi_letter:
            sim.efi_drive = ""
            sim.assigned_efi_letter = ""
    return lines


def _execute_one(step_id: str, ctx: Context, logger: Logger, depth: int = 0) -> StepResult:
    step = STEPS.get(step_id)
    if not step:
        return StepResult(step_id, step_id, "failed", "未知步骤")
    ok, reason = applicable(ctx, step)
    if not ok:
        logger("skip", f"[跳过] {step.title}：{reason}")
        return StepResult(step_id, step.title, "skipped", reason)

    if ctx.dry_run:
        logger("info", f"[演练] {step.title}")
        if step.id == "assign_efi" and ctx.efi_volume_number and not ctx.efi_drive:
            letter = pick_free_letter()
            ctx.efi_drive = letter
            ctx.assigned_efi_letter = letter
            logger("cmd", f"  diskpart: assign letter={letter}（模拟）")
        for cmd in step.preview(ctx):
            logger("cmd", "  " + cmd)
        if step.id == "remove_efi" and ctx.assigned_efi_letter:
            ctx.efi_drive = ""
            ctx.assigned_efi_letter = ""
        return StepResult(step_id, step.title, "skipped", "演练模式，未实际执行")

    logger("info", f"▶ {step.title}")
    output = ""
    try:
        if step.action == "backup_bcd":
            result = _do_backup_bcd(ctx, logger)
        elif step.action == "backup_registry":
            result = _do_backup_registry(ctx, logger)
        elif step.action == "assign_efi":
            result = _do_assign_efi(ctx, logger)
        elif step.action == "remove_efi":
            result = _do_remove_efi(ctx, logger)
        else:
            rc_total = 0
            unavailable: list[str] = []
            for cmd in step.preview(ctx):
                if cmd.startswith("#"):
                    continue
                args = _split_command(cmd)
                if not args:
                    continue
                if not shutil.which(args[0]) and not os.path.exists(args[0]):
                    unavailable.append(args[0])
                    continue
                rc, out = run_command(args, logger, timeout=step.timeout, stdin=step.stdin)
                rc_total += rc
                output += out + "\n"
            if unavailable:
                msg = f"当前环境缺少命令：{', '.join(sorted(set(unavailable)))}；请在 PE/WinRE 中运行"
                logger("skip", f"[跳过] {step.title}：{msg}")
                result = StepResult(step_id, step.title, "skipped", msg)
                level, symbol = "warn", "-"
                logger(level, f"{symbol} {step.title}：{result.message}")
                return result
            if rc_total != 0:
                if step.fallback and depth < 2:
                    logger("warn", f"{step.title} 失败，尝试备用方案：{STEPS[step.fallback].title}")
                    fb = _execute_one(step.fallback, ctx, logger, depth + 1)
                    if fb.status == "ok":
                        return StepResult(step_id, step.title, "ok", f"主方案失败，备用方案成功：{fb.message}", output)
                    return StepResult(step_id, step.title, "failed", f"主方案与备用方案均失败：{fb.message}", output)
                return StepResult(step_id, step.title, "failed", f"命令退出码合计 {rc_total}", output)
            result = StepResult(step_id, step.title, "ok", "完成")
    except Exception as exc:  # noqa: BLE001
        logger("error", f"{step.title} 异常：{exc}")
        result = StepResult(step_id, step.title, "failed", str(exc))

    level = "ok" if result.status == "ok" else "warn" if result.status == "skipped" else "error"
    symbol = {"ok": "✔", "warn": "-", "error": "✘"}[level]
    logger(level, f"{symbol} {step.title}：{result.message}")
    return result


def execute_steps(ctx: Context, step_ids: Iterable[str], logger: Logger) -> list[StepResult]:
    if not ctx.backup_dir and not ctx.dry_run:
        ctx.backup_dir = make_backup_dir(ctx)
        logger("info", f"备份目录：{ctx.backup_dir}")
    results: list[StepResult] = []
    for sid in step_ids:
        results.append(_execute_one(sid, ctx, logger))
    return results


def format_report(ctx: Context, results: list[StepResult], entry: dict | None = None) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "蓝屏修复报告",
        "=" * 40,
        f"时间：{now}",
        f"代码：{(entry or {}).get('code', '-')} {(entry or {}).get('name', '')}",
        f"系统盘：{ctx.system_drive or '-'}",
        f"固件：{ctx.firmware}",
        f"EFI 分区：{ctx.efi_drive or '-'}",
        f"环境：{'WinPE/WinRE' if ctx.winpe else '完整 Windows'}",
        f"模式：{'演练' if ctx.dry_run else '实际执行'}",
        f"备份：{ctx.backup_dir or '-'}",
        "",
    ]
    for r in results:
        lines.append(f"[{r.status.upper():7}] {r.title} - {r.message}")
    lines += ["", "提示：修复后请重启并观察；若仍蓝屏，请结合页面中的原因分析检查硬件/驱动。"]
    return "\n".join(lines)


def prerequisites(ctx: Context) -> list[str]:
    warnings: list[str] = []
    if not is_admin():
        warnings.append("当前不是管理员权限，修复命令可能失败。")
    if not ctx.system_drive:
        warnings.append("未识别到 Windows 系统盘，请手动选择。")
    if ctx.firmware == "AUTO":
        warnings.append("固件模式未确定，默认会尝试 UEFI/BIOS 两套命令中的适用项。")
    if ctx.firmware == "UEFI" and not ctx.efi_drive and not ctx.efi_volume_number:
        warnings.append("UEFI 环境未找到 EFI 系统分区，bcdboot 可能无法执行。")
    if not ctx.winpe:
        warnings.append("bootrec 通常只在 PE/WinRE 中存在；在完整 Windows 中相关步骤会被跳过。")
    warnings.append("若系统盘启用 BitLocker，请先解锁或暂停保护，否则离线修复可能无法读取文件。")
    return warnings
