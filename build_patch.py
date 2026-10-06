#!/usr/bin/env python3
"""让 Keil µVision 5.x 直接显示简体中文（默认**原地汉化**原版 UV4.exe）。

核心目标：**双击桌面上的 Keil 图标就是中文**，不需要另开别的 exe。

* 默认行为：就地改写官方 `UV4.exe` 的界面资源；首次改写前自动备份
  `UV4.exe.bak`（原版），随时可用 `tools\\restore.py` 一键还原；
* 只改资源段 `.rsrc`：`.text / .rdata / .data` 与备份原版逐字节一致，
  写入前会自动校验，校验不过立即放弃；
* 词典按 **资源身份 + 英文原文 SHA-256** 双重匹配（参照 GitHub 项目
  player4086/keil-uv5-zh-cn-patch 的"原文指纹"方案），只有完全对得上的
  条目才会被替换，其余一律保持英文；
* 完整验证过的版本按文件 SHA-256 精确识别，其它 µVision 5.x 走保守的
  "兼容模式"，并要求匹配率达到阈值（默认 70%）才允许写入。

附加选项：`--copy` 只生成旁边的 `UV4_zh-CN.exe`、完全不动原版（非破坏式）。

本项目的词典同时覆盖 **字符串表 / 菜单 / 对话框**。
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent
TOOLS_DIR = ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from winres import (  # noqa: E402
    RT_DIALOG,
    RT_MENU,
    RT_STRING,
    build_string_block,
    parse_dialog,
    parse_menu,
    parse_string_block,
    read_resources,
    serialize_dialog,
    serialize_menu,
    update_resources,
)
from verify import compare_sections  # noqa: E402

ENGLISH_US = 1033
DEFAULT_CATALOG = ROOT / "translations" / "zh_CN.json"
DEFAULT_MIN_COVERAGE = 0.70


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-16le")).hexdigest().upper()


class VSFixedFileInfo(ctypes.Structure):
    _fields_ = [
        ("signature", ctypes.c_uint32),
        ("structure_version", ctypes.c_uint32),
        ("file_version_ms", ctypes.c_uint32),
        ("file_version_ls", ctypes.c_uint32),
        ("product_version_ms", ctypes.c_uint32),
        ("product_version_ls", ctypes.c_uint32),
        ("file_flags_mask", ctypes.c_uint32),
        ("file_flags", ctypes.c_uint32),
        ("file_os", ctypes.c_uint32),
        ("file_type", ctypes.c_uint32),
        ("file_subtype", ctypes.c_uint32),
        ("file_date_ms", ctypes.c_uint32),
        ("file_date_ls", ctypes.c_uint32),
    ]


def file_version(path: Path) -> tuple[int, int, int, int]:
    if os.name != "nt":
        raise SystemExit("This patcher requires Windows.")
    version = ctypes.WinDLL("version", use_last_error=True)
    version.GetFileVersionInfoSizeW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p]
    version.GetFileVersionInfoSizeW.restype = ctypes.c_uint32
    version.GetFileVersionInfoW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    version.GetFileVersionInfoW.restype = ctypes.c_int
    version.VerQueryValueW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    version.VerQueryValueW.restype = ctypes.c_int

    size = version.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        raise SystemExit(f"No Windows version information found in: {path}")
    buffer = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(str(path), 0, size, buffer):
        raise ctypes.WinError(ctypes.get_last_error())
    pointer = ctypes.c_void_p()
    length = ctypes.c_uint32()
    if not version.VerQueryValueW(buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)):
        raise ctypes.WinError(ctypes.get_last_error())
    fixed = ctypes.cast(pointer, ctypes.POINTER(VSFixedFileInfo)).contents
    if fixed.signature != 0xFEEF04BD:
        raise SystemExit(f"Invalid Windows version resource in: {path}")
    return (
        fixed.file_version_ms >> 16,
        fixed.file_version_ms & 0xFFFF,
        fixed.file_version_ls >> 16,
        fixed.file_version_ls & 0xFFFF,
    )


def find_target() -> Path | None:
    """在注册表与常见安装路径中自动查找官方 UV4.exe。"""
    candidates: list[Path] = []
    try:
        import winreg
    except ImportError:  # 非 Windows（仅用于静态检查）
        winreg = None
    if winreg is not None:
        products = ("MDK", "C51", "C251", "C166", "MDK-ARM", "ARM")
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY, 0):
                for product in products:
                    for prefix in (
                        r"SOFTWARE\Keil\Products",
                        r"SOFTWARE\WOW6432Node\Keil\Products",
                    ):
                        try:
                            with winreg.OpenKey(
                                hive, prefix + "\\" + product, 0, winreg.KEY_READ | view
                            ) as key:
                                base, _ = winreg.QueryValueEx(key, "Path")
                        except OSError:
                            continue
                        candidates.append(Path(base).parent / "UV4" / "UV4.exe")
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates.extend(
        (
            local / "Keil_v5" / "UV4" / "UV4.exe",
            Path(r"C:\Keil_v5\UV4\UV4.exe"),
            Path(r"C:\Keil\UV4\UV4.exe"),
            Path(r"C:\Keil\C51\UV4\UV4.exe"),
            Path(r"D:\Keil_v5\UV4\UV4.exe"),
        )
    )
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def load_catalog(path: Path) -> dict[str, object]:
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Cannot read translation catalog {path}: {error}") from error
    if catalog.get("format_version") != 2:
        raise SystemExit("Unsupported translation catalog format; expected version 2.")
    if int(catalog.get("language", -1)) != ENGLISH_US:
        raise SystemExit("Translation catalog language does not match the target resources.")
    translations = catalog.get("translations")
    if not isinstance(translations, dict):
        raise SystemExit("Translation catalog has no translations object.")
    if not isinstance(translations.get("string_table"), dict) or not isinstance(
        translations.get("menus"), dict
    ):
        raise SystemExit("Translation catalog string_table or menus section is invalid.")
    if not isinstance(translations.get("dialogs", {}), dict):
        raise SystemExit("Translation catalog dialogs section is invalid.")
    return catalog


def translation_pair(entry: object, label: str) -> tuple[str, str]:
    if not isinstance(entry, dict):
        raise SystemExit(f"Invalid catalog entry: {label}")
    source = entry.get("source_sha256")
    translation = entry.get("translation")
    if (
        not isinstance(source, str)
        or len(source) != 64
        or any(character not in "0123456789ABCDEFabcdef" for character in source)
        or not isinstance(translation, str)
        or not translation
    ):
        raise SystemExit(f"Invalid source hash or translation in catalog entry: {label}")
    return source.upper(), translation


def menu_item_at_path(menu: dict[str, object], path: str) -> dict[str, object] | None:
    try:
        indexes = [int(value) for value in path.split("/")]
    except ValueError:
        return None
    items = menu["items"]
    item: dict[str, object] | None = None
    for index in indexes:
        if index < 0 or index >= len(items):
            return None
        item = items[index]
        items = item["children"]
    return item


def dialog_item_slot(dialog: dict[str, object], key: str) -> tuple[str, int] | None:
    """把词典键解析为 (kind, index)；title 用 ("title", 0)，控件用 ("item", 索引)。"""
    if key == "title":
        return ("title", 0)
    if key.startswith("item:"):
        try:
            index = int(key[5:])
        except ValueError:
            return None
        if 0 <= index < len(dialog["items"]):
            return ("item", index)
    return None


def read_dialog_text(dialog: dict[str, object], slot: tuple[str, int]) -> str | None:
    kind, index = slot
    if kind == "title":
        target = dialog["title"]
        return target[1] if target[0] == "string" else None
    item = dialog["items"][index]
    return item["title"][1] if item["title"][0] == "string" else None


def write_dialog_text(dialog: dict[str, object], slot: tuple[str, int], text: str) -> bool:
    kind, index = slot
    if kind == "title":
        dialog["title"] = ("string", text)
        return True
    item = dialog["items"][index]
    if item["title"][0] != "string":
        return False
    item["title"] = ("string", text)
    return True


def plan_updates(
    target: Path, catalog: dict[str, object]
) -> tuple[list[dict[str, object]], dict[str, object]]:
    translations = catalog["translations"]
    string_catalog = translations["string_table"]
    menu_catalog = translations["menus"]
    dialog_catalog = translations.get("dialogs", {})
    try:
        catalog_strings: dict[int, object] = {
            int(key): value for key, value in string_catalog.items()
        }
        catalog_menus: dict[int, dict[str, object]] = {}
        for key, value in menu_catalog.items():
            if not isinstance(value, dict):
                raise ValueError(key)
            catalog_menus[int(key)] = value
        catalog_dialogs: dict[int, dict[str, object]] = {}
        for key, value in dialog_catalog.items():
            if not isinstance(value, dict):
                raise ValueError(key)
            catalog_dialogs[int(key)] = value
    except (TypeError, ValueError) as error:
        raise SystemExit(f"Translation catalog contains an invalid resource ID: {error}")

    matched_strings: set[int] = set()
    matched_menus: set[tuple[int, str]] = set()
    matched_dialogs: set[tuple[int, str]] = set()
    updates: list[dict[str, object]] = []
    report: dict[str, object] = {
        "target": str(target),
        "language": ENGLISH_US,
        "string_table": {"resources": 0, "texts": 0},
        "menus": {"resources": 0, "texts": 0},
        "dialogs": {"resources": 0, "texts": 0},
    }

    for target_item in read_resources(target):
        if int(target_item["lang"]) != ENGLISH_US:
            continue
        resource_name = target_item["name"]

        if target_item["type"] == RT_STRING and isinstance(resource_name, int):
            target_values = parse_string_block(resource_name, target_item["data"])
            changed = 0
            for string_id, current_text in target_values.items():
                entry = catalog_strings.get(string_id)
                if entry is None:
                    continue
                source_hash, translation = translation_pair(entry, f"string {string_id}")
                if text_sha256(current_text) != source_hash:
                    continue
                target_values[string_id] = translation
                matched_strings.add(string_id)
                changed += 1
            if changed:
                updates.append(
                    {
                        "type": RT_STRING,
                        "name": resource_name,
                        "lang": ENGLISH_US,
                        "data": build_string_block(resource_name, target_values),
                    }
                )
                report["string_table"]["resources"] += 1
                report["string_table"]["texts"] += changed

        elif target_item["type"] == RT_MENU and isinstance(resource_name, int):
            entries = catalog_menus.get(resource_name)
            if entries is None:
                continue
            target_menu = parse_menu(target_item["data"])
            changed = 0
            for path, entry in entries.items():
                source_hash, translation = translation_pair(
                    entry, f"menu {resource_name}:{path}"
                )
                item = menu_item_at_path(target_menu, path)
                if item is None or text_sha256(str(item["text"])) != source_hash:
                    continue
                item["text"] = translation
                matched_menus.add((resource_name, path))
                changed += 1
            if changed:
                updates.append(
                    {
                        "type": RT_MENU,
                        "name": resource_name,
                        "lang": ENGLISH_US,
                        "data": serialize_menu(target_menu),
                    }
                )
                report["menus"]["resources"] += 1
                report["menus"]["texts"] += changed

        elif target_item["type"] == RT_DIALOG and isinstance(resource_name, int):
            entries = catalog_dialogs.get(resource_name)
            if entries is None:
                continue
            target_dialog = parse_dialog(target_item["data"])
            changed = 0
            for key, entry in entries.items():
                slot = dialog_item_slot(target_dialog, key)
                if slot is None:
                    continue
                current_text = read_dialog_text(target_dialog, slot)
                if current_text is None:
                    continue
                source_hash, translation = translation_pair(
                    entry, f"dialog {resource_name}:{key}"
                )
                if text_sha256(current_text) != source_hash:
                    continue
                if write_dialog_text(target_dialog, slot, translation):
                    matched_dialogs.add((resource_name, key))
                    changed += 1
            if changed:
                updates.append(
                    {
                        "type": RT_DIALOG,
                        "name": resource_name,
                        "lang": ENGLISH_US,
                        "data": serialize_dialog(target_dialog),
                    }
                )
                report["dialogs"]["resources"] += 1
                report["dialogs"]["texts"] += changed

    menu_keys = {
        (resource_id, path)
        for resource_id, entries in catalog_menus.items()
        for path in entries
    }
    dialog_keys = {
        (resource_id, key)
        for resource_id, entries in catalog_dialogs.items()
        for key in entries
    }
    total = len(catalog_strings) + len(menu_keys) + len(dialog_keys)
    matched = len(matched_strings) + len(matched_menus) + len(matched_dialogs)
    report["resource_updates"] = len(updates)
    report["coverage"] = {
        "matched": matched,
        "total": total,
        "ratio": round(matched / total, 6) if total else 0.0,
        "matched_strings": len(matched_strings),
        "total_strings": len(catalog_strings),
        "unmatched_string_ids": sorted(set(catalog_strings) - matched_strings),
        "matched_menu_items": len(matched_menus),
        "total_menu_items": len(menu_keys),
        "unmatched_menu_items": [
            f"{resource_id}:{path}" for resource_id, path in sorted(menu_keys - matched_menus)
        ],
        "matched_dialog_texts": len(matched_dialogs),
        "total_dialog_texts": len(dialog_keys),
        "unmatched_dialog_texts": [
            f"{resource_id}:{key}"
            for resource_id, key in sorted(dialog_keys - matched_dialogs)
        ],
    }
    return updates, report


def restore(target: Path) -> int:
    """从 UV4.exe.bak 还原原版，并清理旧式中文副本。"""
    backup = target.with_name(target.name + ".bak")
    restored = False
    if backup.is_file():
        shutil.copy2(backup, target)
        backup.unlink()
        restored = True
        print(f"已从 {backup.name} 还原原版 {target.name}（并删除备份）。")
    removed = False
    for name in ("UV4_zh-CN.exe", "UV4_CN.exe"):
        copy = target.with_name(name)
        if copy.is_file():
            try:
                copy.unlink()
                removed = True
                print(f"已删除中文副本 {name}。")
            except OSError as error:
                print(f"警告：无法删除 {copy}（可能仍在运行）：{error}")
    if not restored and not removed:
        print("没有发现汉化痕迹（UV4.exe.bak 不存在，也没有中文副本）。")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(
        description=(
            "Make Keil uVision 5.x display Simplified Chinese. By default the "
            "installed UV4.exe is patched in place (an original UV4.exe.bak is "
            "created first), so the normal desktop shortcut starts the Chinese UI."
        )
    )
    parser.add_argument(
        "--target",
        type=Path,
        help="path to an official uVision 5.x UV4.exe (default: auto-detect)",
    )
    parser.add_argument(
        "--catalog",
        default=DEFAULT_CATALOG,
        type=Path,
        help="translation catalog (default: bundled Simplified Chinese catalog)",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="write UV4_zh-CN.exe beside the original instead of patching it in place",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="explicit output path (implies a non-destructive copy)",
    )
    parser.add_argument(
        "--report",
        default=ROOT / "patch-report.json",
        type=Path,
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=DEFAULT_MIN_COVERAGE,
        help="minimum source-text match ratio for untested uVision 5.x builds",
    )
    parser.add_argument(
        "--exact-only",
        action="store_true",
        help="accept only the fully tested executable hash",
    )
    parser.add_argument(
        "--restore",
        action="store_true",
        help="restore the original English UV4.exe from UV4.exe.bak and exit",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    target = args.target.resolve() if args.target is not None else find_target()
    if target is None:
        raise SystemExit(
            "Could not locate UV4.exe automatically; pass --target \"<...>\\UV4\\UV4.exe\"."
        )
    if args.restore:
        print(f"Keil 安装目录：{target.parent}")
        return restore(target)
    if not target.is_file():
        raise SystemExit(f"Target file does not exist: {target}")

    backup = target.with_name(target.name + ".bak")
    in_place = not args.copy and args.output is None
    output = (
        target
        if in_place
        else (
            args.output.resolve()
            if args.output is not None
            else target.with_name("UV4_zh-CN.exe")
        )
    )
    if not in_place and output == target:
        raise SystemExit("Explicit output path equals the original; drop --output to patch in place.")

    catalog_path = args.catalog.resolve()
    report_path = args.report.resolve()
    if not 0.0 <= args.min_coverage <= 1.0:
        raise SystemExit("--min-coverage must be between 0.0 and 1.0.")

    # 原地汉化时以“备份原版”为源，保证每次都是对着英文原版做指纹匹配。
    source = backup if backup.is_file() else target

    version = file_version(source)
    if version[0] != 5:
        raise SystemExit(
            f"Unsupported file version {'.'.join(map(str, version))}; "
            "only uVision 5.x is accepted. No file was changed."
        )
    source_hash = sha256(source)
    catalog = load_catalog(catalog_path)
    catalog_target = catalog.get("target")
    if not isinstance(catalog_target, dict) or not isinstance(
        catalog_target.get("sha256"), str
    ):
        raise SystemExit("Translation catalog target metadata is invalid.")
    tested_hash = str(catalog_target["sha256"]).upper()
    exact_target = source_hash == tested_hash

    updates, report = plan_updates(source, catalog)
    coverage = float(report["coverage"]["ratio"])
    accepted = exact_target or (
        not args.exact_only and coverage >= args.min_coverage
    )
    compatibility = "exact-tested" if exact_target else "compatible-source-match"
    report["target_version"] = ".".join(map(str, version))
    report["target"] = str(target)
    report["target_sha256"] = sha256(target)
    report["source"] = str(source)
    report["source_sha256"] = source_hash
    report["mode"] = "in-place" if in_place else "copy"
    report["backup"] = str(backup) if (in_place or backup.is_file()) else None
    report["catalog"] = str(catalog_path)
    report["catalog_sha256"] = sha256(catalog_path)
    report["compatibility"] = {
        "mode": compatibility,
        "fully_tested": exact_target,
        "minimum_coverage": args.min_coverage,
        "exact_only": bool(args.exact_only),
        "accepted": accepted,
    }
    report["output"] = str(output)
    report["dry_run"] = bool(args.dry_run)

    if accepted and not args.dry_run:
        if in_place and not backup.is_file():
            shutil.copy2(target, backup)
            report["backup_created"] = True
            source = backup
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + ".building")
        if temporary.exists():
            temporary.unlink()
        try:
            shutil.copy2(source, temporary)
            update_resources(temporary, updates)
            verification = compare_sections(source, temporary)
            report["verification"] = verification
            if not verification["code_sections_identical"]:
                raise SystemExit(
                    "安全校验未通过：代码/数据段发生变化，已放弃写入，目标文件保持原样。"
                )
            os.replace(temporary, output)
        except OSError as error:
            raise SystemExit(
                "无法写入目标文件：\n"
                f"  {output}\n"
                f"原因：{error}\n"
                "请先完全退出正在运行的 Keil / µVision，再重新执行。"
                + ("" if in_place else "\n原版 UV4.exe 未被修改。")
            ) from error
        finally:
            if temporary.exists():
                temporary.unlink()
        report["output_sha256"] = sha256(output)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not accepted:
        print(
            "Compatibility check failed: source-text coverage is below the "
            "required threshold, or --exact-only rejected this build. "
            "No file was changed.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
