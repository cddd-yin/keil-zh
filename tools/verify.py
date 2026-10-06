#!/usr/bin/env python3
"""校验工具：PE 段对比 + 菜单/对话框可无损解析。

用法：
  python tools\\verify.py <汉化后.exe>
      检查菜单/对话框资源能否“解析 -> 重新序列化”逐字节还原。

  python tools\\verify.py <原版.exe> <汉化后.exe>
      在上面基础上，再逐段比较两个文件：
      `.text/.rdata/.data` 必须完全相同，只允许 `.rsrc` 变化。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from winres import (  # noqa: E402
    RT_DIALOG,
    RT_MENU,
    parse_dialog,
    parse_menu,
    read_resources,
    serialize_dialog,
    serialize_menu,
)


def sections(path: Path) -> dict[str, dict[str, object]]:
    """返回 {段名: {size, sha256}}。"""
    data = path.read_bytes()
    if data[:2] != b"MZ":
        raise ValueError(f"Not a PE file: {path}")
    pe_offset = struct.unpack_from("<L", data, 0x3C)[0]
    if data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise ValueError(f"PE signature not found: {path}")
    section_count = struct.unpack_from("<H", data, pe_offset + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe_offset + 20)[0]
    table = pe_offset + 24 + optional_size
    result: dict[str, dict[str, object]] = {}
    for index in range(section_count):
        offset = table + index * 40
        name = data[offset : offset + 8].split(b"\0", 1)[0].decode("ascii")
        raw_size, raw_offset = struct.unpack_from("<LL", data, offset + 16)
        payload = data[raw_offset : raw_offset + raw_size]
        result[name] = {
            "size": raw_size,
            "sha256": hashlib.sha256(payload).hexdigest().upper(),
        }
    return result


def compare_sections(before_path: Path, after_path: Path) -> dict[str, object]:
    """只允许资源段变化，代码/数据段必须逐字节一致。"""
    before = sections(before_path)
    after = sections(after_path)
    names = sorted(before.keys() | after.keys())
    identical = {name: before.get(name) == after.get(name) for name in names}
    code_ok = all(
        identical.get(name, False)
        for name in (".text", ".rdata", ".data")
        if name in identical
    )
    return {
        "code_sections_identical": code_ok,
        "resource_section_changed": not identical.get(".rsrc", True),
        "changed_sections": [name for name in names if not identical[name]],
    }


def check_formats(path: Path) -> dict[str, object]:
    """菜单/对话框往返解析校验。"""
    stats: dict[str, object] = {
        "path": str(path),
        "menu": {"total": 0, "exact": 0, "mismatch": [], "errors": []},
        "dialog": {"total": 0, "exact": 0, "mismatch": [], "errors": []},
    }
    for resource in read_resources(path):
        if resource["type"] == RT_MENU:
            bucket, parser, serializer = stats["menu"], parse_menu, serialize_menu
        elif resource["type"] == RT_DIALOG:
            bucket, parser, serializer = stats["dialog"], parse_dialog, serialize_dialog
        else:
            continue
        bucket["total"] += 1
        label = f"{resource['name']}:{resource['lang']}"
        try:
            rebuilt = serializer(parser(resource["data"]))
            if rebuilt == resource["data"]:
                bucket["exact"] += 1
            else:
                bucket["mismatch"].append(
                    {
                        "resource": label,
                        "original": len(resource["data"]),
                        "rebuilt": len(rebuilt),
                    }
                )
        except Exception as error:  # noqa: BLE001
            bucket["errors"].append({"resource": label, "error": str(error)})
    return stats


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) not in (2, 3):
        print(__doc__)
        return 1

    report: dict[str, object] = {}
    if len(sys.argv) == 3:
        before = Path(sys.argv[1]).resolve()
        after = Path(sys.argv[2]).resolve()
        report["sections"] = compare_sections(before, after)
        report["formats"] = check_formats(after)
    else:
        report["formats"] = check_formats(Path(sys.argv[1]).resolve())

    print(json.dumps(report, ensure_ascii=False, indent=2))
    ok = True
    if "sections" in report:
        ok = ok and bool(report["sections"]["code_sections_identical"])
        ok = ok and bool(report["sections"]["resource_section_changed"])
    for bucket in ("menu", "dialog"):
        formats = report["formats"][bucket]
        ok = ok and not formats["mismatch"] and not formats["errors"]
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
