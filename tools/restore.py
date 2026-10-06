#!/usr/bin/env python3
"""还原 Keil µVision 为官方英文版。

处理两种情况：
  1) 原地汉化（UV4.exe 被改写）：若存在 UV4.exe.bak，则用它恢复；
  2) 非破坏式汉化（生成的 UV4_zh-CN.exe）：直接删除该副本。
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
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
    restored = 0
    if backup.is_file():
        shutil.copy2(backup, target)
        backup.unlink()
        restored += 1
        print("已从 UV4.exe.bak 恢复原版 UV4.exe（并删除备份）。")

    copy = target.with_name("UV4_zh-CN.exe")
    if copy.is_file():
        try:
            copy.unlink()
            print("已删除中文副本 UV4_zh-CN.exe。")
        except OSError as exc:
            if copy.with_suffix(".exe.bak").exists():
                pass
            print(f"警告：无法删除 {copy}（可能仍在运行）：{exc}")

    if not restored and not copy.is_file():
        print("没有发现汉化痕迹（原版 UV4.exe 未被修改）。")
    print("完成。若中文副本曾运行，请关闭后再确认。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
