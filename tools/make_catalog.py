#!/usr/bin/env python3
"""从翻译源文件与官方 UV4.exe 生成带原文指纹的词典 translations/zh_CN.json。

工作方式（与参考项目 player4086/keil-uv5-zh-cn-patch 一致）：

1. 合并 translations/src/*.json（平铺的 {英文原文: 简体中文}）为一张全局表；
2. 扫描官方 UV4.exe 中语言 1033 的字符串表 / 菜单 / 对话框，
   把每一条可翻译文本与全局表对照；
3. 对命中且通过安全校验（格式符 / 快捷键 / 助记符 / 换行）的条目，
   记录 **资源身份 + 英文原文 SHA-256 + 译文**；未命中或校验不通过的保持英文；
4. 输出 format_version=2 的词典，供 build_patch.py 使用。

用法：
  python tools\\make_catalog.py                       # 自动定位 UV4.exe
  python tools\\make_catalog.py --target "<...>\\UV4.exe"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from build_patch import file_version, find_target, sha256, text_sha256  # noqa: E402
from pe_resources import (  # noqa: E402
    RT_DIALOG,
    RT_MENU,
    RT_STRING,
    parse_string_block,
    read_resources,
)
from resource_formats import iter_menu_items, parse_dialog, parse_menu  # noqa: E402


SRC = ROOT / "translations" / "src"
OUT = ROOT / "translations" / "zh_CN.json"
BUILD = ROOT / "build"
ENGLISH_US = 1033

# %% / %1..%9 / %Ts / printf 风格格式符
SPEC_RE = re.compile(r"%%|%[0-9]|%Ts|%[-+ #0]*[0-9*]*(?:\.[0-9*]+)?[hlL]*[diouxXeEfgGcsp]")


def spec_tokens(text: str) -> list[str]:
    return sorted(SPEC_RE.findall(text))


def validate(source: str, translation: str, kind: str) -> str | None:
    """返回错误说明；None 表示通过。"""
    if spec_tokens(source) != spec_tokens(translation):
        return f"格式符不一致 {spec_tokens(source)} -> {spec_tokens(translation)}"
    if source.count("\t") != translation.count("\t"):
        return "制表符(快捷键)数量不一致"
    if "\t" in source and source.rsplit("\t", 1)[-1] != translation.rsplit("\t", 1)[-1]:
        return f"快捷键后缀被改动：{source.rsplit(chr(9), 1)[-1]!r}"
    if kind == "string_table" and source.count("\n") != translation.count("\n"):
        return "换行数量不一致"
    if source.count("&") != translation.count("&"):
        return f"助记符 & 数量不一致（{source.count('&')} -> {translation.count('&')}）"
    return None


def load_parts() -> tuple[dict[str, str], list[str]]:
    texts: dict[str, str] = {}
    problems: list[str] = []
    origin: dict[str, str] = {}
    for path in sorted(SRC.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            problems.append(f"{path.name}: 顶层必须是对象")
            continue
        for key, value in data.items():
            if not isinstance(value, str) or not value:
                problems.append(f"{path.name}: 译文为空 -> {key!r}")
                continue
            if key in texts and texts[key] != value:
                problems.append(
                    f"冲突：{key!r}\n    {origin[key]} => {texts[key]!r}\n"
                    f"    {path.name} => {value!r}"
                )
                continue
            texts[key] = value
            origin[key] = path.name
    return texts, problems


def entry(source: str, translation: str) -> dict[str, str]:
    return {"source_sha256": text_sha256(source), "translation": translation}


def build_catalog(target: Path) -> tuple[dict, list[str]]:
    texts, problems = load_parts()
    ignored: list[str] = []

    def translate(source: str, kind: str, label: str) -> str | None:
        if not source:
            return None
        translation = texts.get(source)
        if translation is None or translation == source:
            return None
        problem = validate(source, translation, kind)
        if problem:
            ignored.append(f"[{kind} {label}] {problem} | {source!r} -> {translation!r}")
            return None
        return translation

    string_table: dict[str, dict[str, str]] = {}
    menus: dict[str, dict[str, dict[str, str]]] = {}
    dialogs: dict[str, dict[str, dict[str, str]]] = {}
    string_blocks: set[int] = set()
    stats = Counter()

    for item in read_resources(target):
        if int(item["lang"]) != ENGLISH_US:
            continue
        rtype, name, data = item["type"], item["name"], item["data"]
        if not isinstance(name, int):
            continue

        if rtype == RT_STRING:
            values = parse_string_block(name, data)
            for sid, source in sorted(values.items()):
                translation = translate(source, "string_table", f"string {sid}")
                if translation is not None:
                    string_table[str(sid)] = entry(source, translation)
                    string_blocks.add(name)
                    stats["strings"] += 1

        elif rtype == RT_MENU:
            menu = parse_menu(data)
            entries: dict[str, dict[str, str]] = {}
            for path, node in iter_menu_items(menu["items"]):
                source = str(node.get("text") or "")
                translation = translate(source, "menus", f"menu {name}:{path}")
                if translation is not None:
                    entries[path] = entry(source, translation)
            if entries:
                menus[str(name)] = entries
                stats["menu_resources"] += 1
                stats["menu_items"] += len(entries)

        elif rtype == RT_DIALOG:
            dialog = parse_dialog(data)
            entries = {}
            if dialog["title"][0] == "string":
                source = str(dialog["title"][1])
                translation = translate(source, "dialogs", f"dialog {name}:title")
                if translation is not None:
                    entries["title"] = entry(source, translation)
            for index, node in enumerate(dialog["items"]):
                if node["title"][0] != "string":
                    continue
                source = str(node["title"][1])
                translation = translate(source, "dialogs", f"dialog {name}:item:{index}")
                if translation is not None:
                    entries[f"item:{index}"] = entry(source, translation)
            if entries:
                dialogs[str(name)] = entries
                stats["dialog_resources"] += 1
                stats["dialog_texts"] += len(entries)

    version = ".".join(map(str, file_version(target)))
    catalog = {
        "format_version": 2,
        "language": ENGLISH_US,
        "target": {
            "product": "Arm Keil µVision",
            "version": version,
            "sha256": sha256(target),
            "note": (
                "资源身份 + 英文原文 SHA-256 双重匹配；未命中项保持英文。"
                "在其它 µVision 5.x 上走兼容模式（默认需 ≥70% 命中）。"
            ),
        },
        "translations": {
            "string_table": dict(sorted(string_table.items(), key=lambda kv: int(kv[0]))),
            "menus": {key: menus[key] for key in sorted(menus, key=int)},
            "dialogs": {key: dialogs[key] for key in sorted(dialogs, key=int)},
        },
        "stats": {
            "string_resources": len(string_blocks),
            "strings": stats["strings"],
            "menu_resources": stats["menu_resources"],
            "menu_items": stats["menu_items"],
            "dialog_resources": stats["dialog_resources"],
            "dialog_texts": stats["dialog_texts"],
            "total_entries": (
                stats["strings"] + stats["menu_items"] + stats["dialog_texts"]
            ),
            "source_texts": len(texts),
        },
        "problems": ignored,
    }
    return catalog, problems


def write_coverage(catalog: dict) -> None:
    stats = catalog["stats"]
    BUILD.mkdir(exist_ok=True)
    (BUILD / "coverage.txt").write_text(
        "\n".join(
            (
                f"词典条目：{stats['total_entries']}",
                f"字符串表：{stats['strings']} 条 / {stats['string_resources']} 组",
                f"菜单：{stats['menu_items']} 项 / {stats['menu_resources']} 组",
                f"对话框：{stats['dialog_texts']} 处 / {stats['dialog_resources']} 个",
                f"源词典条目：{stats['source_texts']}",
                f"目标版本：{catalog['target']['version']}",
                f"目标 SHA-256：{catalog['target']['sha256']}",
            )
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="生成带原文指纹的 Keil 词典")
    parser.add_argument("--target", type=Path, help="官方 UV4.exe 路径（省略则自动查找）")
    parser.add_argument("--output", default=OUT, type=Path)
    args = parser.parse_args()

    target = args.target.resolve() if args.target is not None else find_target()
    if target is None or not target.is_file():
        raise SystemExit("找不到官方 UV4.exe；请用 --target 手动指定。")

    catalog, problems = build_catalog(target)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    BUILD.mkdir(exist_ok=True)
    write_coverage(catalog)

    stats = catalog["stats"]
    print(f"目标：{target}")
    print(f"版本：{catalog['target']['version']}")
    print(f"SHA-256：{catalog['target']['sha256']}")
    print(f"字符串表：{stats['strings']} 条")
    print(f"菜单：{stats['menu_items']} 项 / {stats['menu_resources']} 组")
    print(f"对话框：{stats['dialog_texts']} 处 / {stats['dialog_resources']} 个")
    print(f"合计：{stats['total_entries']} 条（源文件共 {stats['source_texts']} 条）")
    print(f"已写出：{args.output}")
    if problems:
        print(f"\n!!! 发现 {len(problems)} 个源词典问题：")
        for item in problems[:40]:
            print("  -", item)
        return 1
    if catalog["problems"]:
        print(f"\n注意：{len(catalog['problems'])} 条译文未通过校验（已跳过，保持英文）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
