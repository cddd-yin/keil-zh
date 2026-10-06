#!/usr/bin/env python3
"""从一对兼容的 PE 文件导出“纯文本”翻译词典（维护者工具）。

用途：当你手头有一个已经汉化好的 UV4.exe（donor）时，可以用它与官方原版对比，
自动导出 {资源身份 + 英文原文 SHA-256 + 中文译文} 的词典（format_version=2），
**不嵌入任何二进制字节**，只保存界面文本。

用法：
  python tools\\export_translation_catalog.py <原版 UV4.exe> <汉化版.exe> <输出.json>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from build_patch import file_version, sha256, text_sha256  # noqa: E402
from pe_resources import (  # noqa: E402
    RT_DIALOG,
    RT_MENU,
    RT_STRING,
    parse_string_block,
    read_resources,
)
from resource_formats import (  # noqa: E402
    dialog_skeleton,
    menu_skeleton,
    parse_dialog,
    parse_menu,
)

ENGLISH_US = 1033


def index_resources(path: Path) -> dict[tuple[object, object, int], dict[str, object]]:
    return {
        (item["type"], item["name"], int(item["lang"])): item
        for item in read_resources(path)
    }


def menu_differences(
    original: dict[str, object], translated: dict[str, object]
) -> dict[str, dict[str, str]]:
    if menu_skeleton(original) != menu_skeleton(translated):
        raise ValueError("Menu structures differ")
    result: dict[str, dict[str, str]] = {}

    def walk(left, right, prefix: tuple[int, ...] = ()) -> None:
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            path = prefix + (index,)
            left_text = str(left_item["text"])
            right_text = str(right_item["text"])
            if left_text != right_text:
                if not right_text:
                    continue
                result["/".join(map(str, path))] = {
                    "source_sha256": text_sha256(left_text),
                    "translation": right_text,
                }
            walk(left_item["children"], right_item["children"], path)

    walk(original["items"], translated["items"])
    return result


def dialog_differences(
    original: dict[str, object], translated: dict[str, object]
) -> dict[str, dict[str, str]]:
    if dialog_skeleton(original) != dialog_skeleton(translated):
        raise ValueError("Dialog structures differ")
    result: dict[str, dict[str, str]] = {}

    def record(key: str, left: tuple, right: tuple) -> None:
        if left[0] != "string" or right[0] != "string" or left[1] == right[1]:
            return
        if not right[1]:
            return
        result[key] = {
            "source_sha256": text_sha256(str(left[1])),
            "translation": str(right[1]),
        }

    record("title", original["title"], translated["title"])
    for index, (left_item, right_item) in enumerate(
        zip(original["items"], translated["items"])
    ):
        record(f"item:{index}", left_item["title"], right_item["title"])
    return result


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser()
    parser.add_argument("original", type=Path)
    parser.add_argument("patched", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    original = args.original.resolve()
    patched = args.patched.resolve()
    output = args.output.resolve()

    left = index_resources(original)
    right = index_resources(patched)
    strings: dict[str, dict[str, str]] = {}
    menus: dict[str, dict[str, dict[str, str]]] = {}
    dialogs: dict[str, dict[str, dict[str, str]]] = {}
    string_blocks: set[int] = set()

    for key, original_item in left.items():
        resource_type, resource_name, language = key
        if language != ENGLISH_US or key not in right:
            continue
        patched_item = right[key]
        if resource_type == RT_STRING and isinstance(resource_name, int):
            original_values = parse_string_block(resource_name, original_item["data"])
            patched_values = parse_string_block(resource_name, patched_item["data"])
            for string_id in sorted(original_values.keys() & patched_values.keys()):
                translated = patched_values[string_id]
                if original_values[string_id] != translated:
                    if not translated:
                        continue
                    strings[str(string_id)] = {
                        "source_sha256": text_sha256(original_values[string_id]),
                        "translation": translated,
                    }
                    string_blocks.add(resource_name)
        elif resource_type == RT_MENU and isinstance(resource_name, int):
            changes = menu_differences(
                parse_menu(original_item["data"]), parse_menu(patched_item["data"])
            )
            if changes:
                menus[str(resource_name)] = changes
        elif resource_type == RT_DIALOG and isinstance(resource_name, int):
            changes = dialog_differences(
                parse_dialog(original_item["data"]), parse_dialog(patched_item["data"])
            )
            if changes:
                dialogs[str(resource_name)] = changes

    version = ".".join(map(str, file_version(original)))
    catalog = {
        "format_version": 2,
        "language": ENGLISH_US,
        "target": {
            "product": "Arm Keil µVision",
            "version": version,
            "sha256": sha256(original),
            "note": "由 export_translation_catalog.py 从原版/汉化版对照导出。",
        },
        "translations": {
            "string_table": strings,
            "menus": menus,
            "dialogs": dialogs,
        },
        "stats": {
            "string_resources": len(string_blocks),
            "strings": len(strings),
            "menu_resources": len(menus),
            "menu_items": sum(len(items) for items in menus.values()),
            "dialog_resources": len(dialogs),
            "dialog_texts": sum(len(items) for items in dialogs.values()),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(json.dumps(catalog["stats"], ensure_ascii=False, indent=2))
    print(f"已写出：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
