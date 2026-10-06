#!/usr/bin/env python3
"""Keil µVision 简体中文资源补丁生成器。

读取用户合法安装的 UV4.exe，把界面文本（字符串表 / 菜单 / 对话框）替换为
词典中的简体中文，生成一个**独立的中文副本**（默认 UV4_zh-CN.exe），不覆盖原版。

只用 Windows 标准资源 API 修改界面资源，不改编译器、调试器、Pack、工程或许可逻辑。

用法：
  python tools\\build_patch.py --target "<...>\\UV4\\UV4.exe" --dry-run
  python tools\\build_patch.py --target "<...>\\UV4\\UV4.exe"
  python tools\\build_patch.py --target "<...>\\UV4\\UV4.exe" --in-place   # 原地替换（自动 .bak 备份）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from winres import (  # noqa: E402
    RT_DIALOG, RT_MENU, RT_STRING,
    build_string_block, parse_dialog, parse_menu, parse_string_block,
    read_resources, serialize_dialog, serialize_menu, update_resources,
)

ROOT = TOOLS.parent
DEFAULT_CATALOG = ROOT / "translations" / "zh_CN.json"
DEFAULT_LANG = 1033

# %% / %1..%9 / %Ts / printf 风格格式符
SPEC_RE = re.compile(r"%%|%[0-9]|%Ts|%[-+ #0]*[0-9*]*(?:\.[0-9*]+)?[hlL]*[diouxXeEfgGcsp]")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def spec_tokens(text: str) -> list[str]:
    return sorted(SPEC_RE.findall(text))


def validate(source: str, translation: str, kind: str = "string_table") -> str | None:
    """返回错误说明；None 表示通过。"""
    if spec_tokens(source) != spec_tokens(translation):
        return f"格式符不一致 {spec_tokens(source)} -> {spec_tokens(translation)}"
    if source.count("\t") != translation.count("\t"):
        return "制表符(快捷键)数量不一致"
    if "\t" in source and source.rsplit("\t", 1)[-1] != translation.rsplit("\t", 1)[-1]:
        return f"快捷键后缀被改动：{source.rsplit(chr(9),1)[-1]!r}"
    # 字符串表里的「提示\n标题」两段式必须保持两段；菜单/对话框允许中文更紧凑（行数更少）
    if kind == "string_table" and source.count("\n") != translation.count("\n"):
        return "换行数量不一致"
    if source.count("&") != translation.count("&"):
        return f"助记符 & 数量不一致（{source.count('&')} -> {translation.count('&')}）"
    return None


class Catalog:
    def __init__(self, data: dict):
        self.texts: dict[str, str] = data.get("texts", {})
        self.keep: set[str] = set(data.get("keep", []))
        self.overrides: dict[str, dict] = data.get("overrides", {})

    def lookup(self, kind: str, resource: int, key: str, source: str) -> str | None:
        table = self.overrides.get(kind, {}).get(str(resource))
        if table is not None and key in table:
            return table[key]          # 允许显式 null（此处保持原文）
        if source in self.keep:
            return None
        return self.texts.get(source)


def load_catalog(path: Path) -> Catalog:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format_version") != 1:
        raise SystemExit("词典格式不受支持（需要 format_version=1）")
    return Catalog(data)


def iter_menu_items(items, prefix=""):
    for index, item in enumerate(items):
        path = f"{prefix}{index}"
        yield path, item
        yield from iter_menu_items(item["children"], path + "/")


def plan(target: Path, catalog: Catalog, lang: int):
    updates: list[dict] = []
    report = {
        "string_table": {"resources": 0, "matched": 0, "total": 0},
        "menus": {"resources": 0, "matched": 0, "total": 0},
        "dialogs": {"resources": 0, "matched": 0, "total": 0},
        "problems": [],
    }
    used: set[str] = set()

    def translate(kind: str, resource_id: int, key: str, source: str) -> str | None:
        report[kind]["total"] += 1
        value = catalog.lookup(kind, resource_id, key, source)
        if value is None or value == source:
            return None
        err = validate(source, value, kind)
        if err:
            report["problems"].append(f"[{kind} {resource_id} {key}] {err} | {source!r} -> {value!r}")
            return None
        report[kind]["matched"] += 1
        used.add(source)
        return value

    for item in read_resources(str(target)):
        if int(item["lang"]) != lang:
            continue
        rtype, name, data = item["type"], item["name"], item["data"]

        if rtype == RT_STRING and isinstance(name, int):
            values = parse_string_block(name, data)
            changed = False
            for sid in sorted(values):
                source = values[sid]
                if not source:
                    continue
                value = translate("string_table", sid, "", source)
                if value is not None:
                    values[sid] = value
                    changed = True
            if changed:
                updates.append({"type": rtype, "name": name, "lang": lang,
                                "data": build_string_block(name, values)})
                report["string_table"]["resources"] += 1

        elif rtype == RT_MENU and isinstance(name, int):
            try:
                menu = parse_menu(data)
            except Exception as exc:  # noqa: BLE001
                report["problems"].append(f"[menu {name}] 解析失败：{exc}")
                continue
            changed = False
            for path, node in iter_menu_items(menu["items"]):
                source = node.get("text") or ""
                if not source:
                    continue
                value = translate("menus", name, path, source)
                if value is not None:
                    node["text"] = value
                    changed = True
            if changed:
                updates.append({"type": rtype, "name": name, "lang": lang,
                                "data": serialize_menu(menu)})
                report["menus"]["resources"] += 1

        elif rtype == RT_DIALOG and isinstance(name, int):
            try:
                dlg = parse_dialog(data)
            except Exception as exc:  # noqa: BLE001
                report["problems"].append(f"[dialog {name}] 解析失败：{exc}")
                continue
            changed = False
            if dlg["title"][0] == "string" and dlg["title"][1]:
                value = translate("dialogs", name, "title", dlg["title"][1])
                if value is not None:
                    dlg["title"] = ["string", value]
                    changed = True
            for node in dlg["items"]:
                if node["title"][0] != "string" or not node["title"][1]:
                    continue
                value = translate("dialogs", name, f"item:{node['id']}", node["title"][1])
                if value is not None:
                    node["title"] = ["string", value]
                    changed = True
            if changed:
                updates.append({"type": rtype, "name": name, "lang": lang,
                                "data": serialize_dialog(dlg)})
                report["dialogs"]["resources"] += 1

    matched = sum(report[k]["matched"] for k in ("string_table", "menus", "dialogs"))
    report["catalog_entries"] = len(catalog.texts)
    report["applied_texts"] = matched
    report["unused_catalog_entries"] = len(set(catalog.texts) - used)
    return updates, report


def find_target() -> Path | None:
    """自动定位官方 UV4.exe：先查注册表（各 Keil 产品），再查常见安装路径与开始菜单快捷方式。"""
    import winreg

    candidates: list[Path] = []
    products = ("MDK", "C51", "C251", "C166", "MDK-ARM", "ARM")
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY, 0):
            for product in products:
                for prefix in (r"SOFTWARE\Keil\Products", r"SOFTWARE\WOW6432Node\Keil\Products"):
                    try:
                        with winreg.OpenKey(hive, prefix + "\\" + product, 0, winreg.KEY_READ | view) as key:
                            base, _ = winreg.QueryValueEx(key, "Path")
                    except OSError:
                        continue
                    candidates.append(Path(base).parent / "UV4" / "UV4.exe")
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    for extra in (
        local / "Keil_v5" / "UV4" / "UV4.exe",
        local / "Keil_v5" / "UV4" / "UV4.exe",
        Path(r"C:\Keil_v5\UV4\UV4.exe"),
        Path(r"C:\Keil\UV4\UV4.exe"),
        Path(r"C:\Keil\C51\UV4\UV4.exe"),
        Path(r"D:\Keil_v5\UV4\UV4.exe"),
    ):
        candidates.append(extra)
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="生成 Keil µVision 简体中文副本")
    parser.add_argument("--target", type=Path, help="官方 UV4.exe 路径（省略则自动查找）")
    parser.add_argument("--catalog", default=DEFAULT_CATALOG, type=Path)
    parser.add_argument("--output", type=Path, help="输出路径（默认原版旁 UV4_zh-CN.exe）")
    parser.add_argument("--report", default=ROOT / "build" / "patch-report.json", type=Path)
    parser.add_argument("--lang", default=DEFAULT_LANG, type=int, help="目标资源语言（默认 1033）")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写文件")
    parser.add_argument("--in-place", action="store_true", help="原地替换原版（自动 .bak 备份）")
    args = parser.parse_args()

    target = args.target.resolve() if args.target else find_target()
    if target is None:
        raise SystemExit("未能自动找到 UV4.exe，请用 --target \"<...>\\UV4\\UV4.exe\" 手动指定。")
    if not target.is_file():
        raise SystemExit(f"找不到目标文件：{target}")
    output = args.output.resolve() if args.output else target.with_name("UV4_zh-CN.exe")
    if not args.in_place and output == target:
        raise SystemExit("输出不能覆盖原版；如需原地替换请加 --in-place")

    catalog = load_catalog(args.catalog.resolve())
    updates, report = plan(target, catalog, args.lang)
    report.update({
        "target": str(target),
        "target_sha256": sha256(target),
        "language": args.lang,
        "catalog": str(args.catalog.resolve()),
        "resource_updates": len(updates),
        "output": str(output),
        "dry_run": bool(args.dry_run),
        "in_place": bool(args.in_place),
    })

    if not args.dry_run and updates:
        if args.in_place:
            backup = target.with_name(target.name + ".bak")
            if not backup.exists():
                shutil.copy2(target, backup)
            write_target = target
        else:
            write_target = output
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, write_target)
        update_resources(str(write_target), updates)
        report["output_sha256"] = sha256(write_target)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["problems"]:
        print(f"\n注意：{len(report['problems'])} 条译文未通过校验（已跳过，保持英文）。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
