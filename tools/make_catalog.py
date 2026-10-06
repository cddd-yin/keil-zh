#!/usr/bin/env python3
"""把 translations/src/*.json 合并为 translations/zh_CN.json，并统计覆盖率。

src 目录下每个 *.json 都是一个 { "英文原文": "简体中文" } 的平铺对象；
合并时若同一英文原文出现不同译文将报错（避免错翻/冲突）。

覆盖率统计基于 build/resources.json（由 tools/extract.py 生成），
列出尚未翻译的界面文本，便于持续补全。
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "translations" / "src"
OUT = ROOT / "translations" / "zh_CN.json"
BUILD = ROOT / "build"


def load_parts() -> tuple[dict, list[str]]:
    texts: dict[str, str] = {}
    problems: list[str] = []
    origin: dict[str, str] = {}
    for path in sorted(SRC.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, value in data.items():
            if not isinstance(value, str) or not value:
                problems.append(f"{path.name}: 译文为空 -> {key!r}")
                continue
            if key in texts and texts[key] != value:
                problems.append(f"冲突：{key!r}\n    {origin[key]} => {texts[key]!r}\n    {path.name} => {value!r}")
                continue
            texts[key] = value
            origin[key] = path.name
    return texts, problems


def collect_sources() -> dict[str, set[str]]:
    """返回 {英文原文: {来源种类}}。"""
    if not (BUILD / "resources.json").exists():
        return {}
    data = json.loads((BUILD / "resources.json").read_text(encoding="utf-8"))
    en = data["languages"]["1033"]
    sources: dict[str, set[str]] = {}

    def add(text: str, where: str) -> None:
        if text:
            sources.setdefault(text, set()).add(where)

    for text in en["string_table"].values():
        add(text, "字符串表")
    for menu in en["menus"].values():
        def walk(items):
            for it in items:
                add(it.get("text") or "", "菜单")
                walk(it.get("children", []))
        if "items" in menu:
            walk(menu["items"])
    for dlg in en["dialogs"].values():
        if "error" in dlg:
            continue
        if dlg["title"][0] == "string":
            add(dlg["title"][1], "对话框")
        for it in dlg["items"]:
            if it["title"][0] == "string":
                add(it["title"][1], "对话框")
    return sources


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    SRC.mkdir(parents=True, exist_ok=True)
    texts, problems = load_parts()

    catalog = {
        "format_version": 1,
        "language": 1033,
        "target": {
            "product": "Arm Keil µVision",
            "tested": "5.40.0.0",
            "note": "面向 µVision 5.x；按原文精确匹配，未命中项保持英文。",
        },
        "texts": dict(sorted(texts.items())),
        "keep": json.loads((SRC / "_keep.json").read_text(encoding="utf-8")) if (SRC / "_keep.json").exists() else [],
        "overrides": json.loads((SRC / "_overrides.json").read_text(encoding="utf-8")) if (SRC / "_overrides.json").exists() else {},
    }
    OUT.write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    sources = collect_sources()
    covered = set(texts) & set(sources)
    missing = set(sources) - set(texts)
    # 忽略明显非 UI 的短/技术串，便于阅读
    def looks_technical(t: str) -> bool:
        if not t.strip():
            return True
        if t.strip() in {"...", "Static", "OK"}:  # 仍需翻译的除外
            return t.strip() != "OK"
        return False

    txt = []
    txt.append(f"词典条目：{len(texts)}")
    txt.append(f"覆盖到界面文本：{len(covered)} / {len(sources)}（{len(covered)/max(1,len(sources)):.1%}）")
    txt.append(f"未覆盖：{len(missing)}")
    txt.append("")
    txt.append("=== 未覆盖清单（按来源）===")
    by_kind = Counter()
    for text in sorted(missing):
        kinds = ",".join(sorted(sources[text]))
        by_kind[kinds] += 1
        txt.append(f"[{kinds}] {text!r}")
    (BUILD / "coverage.txt").write_text("\n".join(txt) + "\n", encoding="utf-8")

    print(txt[0]); print(txt[1]); print(txt[2])
    print("按来源统计未覆盖：", dict(by_kind))
    if problems:
        print("\n!!! 发现 %d 个问题：" % len(problems))
        for p in problems[:40]:
            print("  -", p)
        return 1
    print("\n已写出", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
