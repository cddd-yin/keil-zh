#!/usr/bin/env python3
"""还原 Keil µVision 为官方英文版。

默认的“原地汉化”会改写 UV4.exe，并在旁边保留原版备份 UV4.exe.bak；
本脚本把备份复制回 UV4.exe（随后删除备份），并顺手清理旧式的
UV4_zh-CN.exe 中文副本。还原后，桌面快捷方式启动的就是英文原版。
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from build_patch import find_target  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    target = find_target()
    if target is None:
        print("未能自动找到 Keil 安装位置，请手动删除 UV4_zh-CN.exe 或从 UV4.exe.bak 恢复。")
        return 1
    print("Keil 安装目录：", target.parent)

    backup = target.with_name(target.name + ".bak")
    restored = False
    if backup.is_file():
        shutil.copy2(backup, target)
        backup.unlink()
        restored = True
        print("已从 UV4.exe.bak 恢复原版 UV4.exe（并删除备份）。")

    removed = False
    for name in ("UV4_zh-CN.exe", "UV4_CN.exe"):
        copy = target.with_name(name)
        if copy.is_file():
            try:
                copy.unlink()
                removed = True
                print(f"已删除中文副本 {name}。")
            except OSError as exc:
                print(f"警告：无法删除 {copy}（可能仍在运行）：{exc}")

    if not restored and not removed:
        print("没有发现汉化痕迹（原版 UV4.exe 未被修改）。")
    print("完成。若中文副本曾运行，请关闭后再确认。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
