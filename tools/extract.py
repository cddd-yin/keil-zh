#!/usr/bin/env python3
"""导出 UV4.exe 中的界面资源，生成可供翻译/比对的结构化 JSON。

用法：
  python tools\\extract.py <UV4.exe> [输出目录]

输出（默认写入 build/）：
  resources.json  —— 全部语言下的字符串表 / 菜单 / 对话框文本
  summary.txt     —— 各语言、各类型的资源统计
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from pe_resources import (  # noqa: E402
    RT_DIALOG,
    RT_MENU,
    RT_STRING,
    parse_string_block,
    read_resources,
)
from resource_formats import parse_dialog, parse_menu  # noqa: E402

LANG_NAME = {1033: "en-US", 2057: "en-GB", 1041: "ja-JP", 2052: "zh-CN"}

_DROP_KEYS = {"prefix", "tail", "extra_payload"}


def _clean(obj):
    """去掉二进制字段，得到可直接序列化为 JSON 的纯文本结构。"""
    if isinstance(obj, dict):
        return {key: _clean(value) for key, value in obj.items() if key not in _DROP_KEYS}
    if isinstance(obj, (list, tuple)):
        return [_clean(value) for value in obj]
    if isinstance(obj, bytes):
        return f"<{len(obj)} bytes>"
    return obj


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    target = Path(sys.argv[1]).resolve()
    out_dir = (
        Path(sys.argv[2]).resolve()
        if len(sys.argv) > 2
        else Path(__file__).resolve().parent.parent / "build"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    resources = read_resources(target)
    payload: dict = {"target": str(target), "languages": {}}
    counts: Counter = Counter()
    lang_counts: Counter = Counter()

    for item in resources:
        counts[str(item["type"])] += 1
        lang_counts[int(item["lang"])] += 1

    for item in resources:
        lang = int(item["lang"])
        bucket = payload["languages"].setdefault(
            str(lang),
            {"name": LANG_NAME.get(lang, f"lang-{lang}"), "string_table": {}, "menus": {}, "dialogs": {}},
        )
        rtype, rname = item["type"], item["name"]
        if rtype == RT_STRING and isinstance(rname, int):
            for sid, text in parse_string_block(rname, item["data"]).items():
                if text:
                    bucket["string_table"][str(sid)] = text
        elif rtype == RT_MENU and isinstance(rname, int):
            try:
                bucket["menus"][str(rname)] = parse_menu(item["data"])
            except Exception as exc:  # noqa: BLE001
                bucket["menus"][str(rname)] = {"error": str(exc)}
        elif rtype == RT_DIALOG and isinstance(rname, int):
            try:
                bucket["dialogs"][str(rname)] = parse_dialog(item["data"])
            except Exception as exc:  # noqa: BLE001
                bucket["dialogs"][str(rname)] = {"error": str(exc)}

    (out_dir / "resources.json").write_text(
        json.dumps(_clean(payload), ensure_ascii=False, indent=1), encoding="utf-8"
    )

    lines = [f"目标：{target}", f"资源总数：{len(resources)}", "", "按类型："]
    for key, value in sorted(
        counts.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 9999
    ):
        lines.append(f"  type {key}: {value}")
    lines.append("")
    lines.append("按语言：")
    for key in sorted(lang_counts):
        lines.append(f"  {key} ({LANG_NAME.get(key, '?')}): {lang_counts[key]}")
    lines.append("")
    for lang_key, bucket in sorted(payload["languages"].items(), key=lambda kv: int(kv[0])):
        lines.append(
            f"{lang_key} {bucket['name']}: 字符串 {len(bucket['string_table'])} / "
            f"菜单 {len(bucket['menus'])} / 对话框 {len(bucket['dialogs'])}"
        )
    text = "\n".join(lines) + "\n"
    (out_dir / "summary.txt").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
