#!/usr/bin/env python3
"""校验补丁只改动了资源段（.rsrc），代码段与数据段与官方原版逐字节一致。

用法：
  python tools\\verify_sections.py "<原版 UV4.exe>" "<UV4_zh-CN.exe>"
"""

from __future__ import annotations

import hashlib
import struct
import sys
from pathlib import Path


def sections(path: Path) -> dict[str, tuple[int, bytes]]:
    data = path.read_bytes()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    count = struct.unpack_from("<H", data, pe + 6)[0]
    opt = struct.unpack_from("<H", data, pe + 20)[0]
    base = pe + 24 + opt
    result: dict[str, tuple[int, bytes]] = {}
    for index in range(count):
        off = base + index * 40
        name = data[off:off + 8].rstrip(b"\x00").decode("ascii", "replace")
        v_size, v_addr, raw_size, raw_ptr = struct.unpack_from("<IIII", data, off + 8)
        result[name] = (raw_size, data[raw_ptr:raw_ptr + raw_size])
    return result


def file_version(path: Path) -> str:
    import ctypes
    from ctypes import wintypes

    version = ctypes.WinDLL("version", use_last_error=True)
    version.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p]
    version.GetFileVersionInfoSizeW.restype = ctypes.c_uint32
    version.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    version.GetFileVersionInfoW.restype = ctypes.c_int
    version.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint32)]
    version.VerQueryValueW.restype = ctypes.c_int

    size = version.GetFileVersionInfoSizeW(str(path), None)
    buf = ctypes.create_string_buffer(size)
    version.GetFileVersionInfoW(str(path), 0, size, buf)
    ptr = ctypes.c_void_p()
    length = ctypes.c_uint32()
    version.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(length))

    class Fixed(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint32) for n in (
            "sig", "ver", "fms", "fls", "pms", "pls", "ffm", "ff", "fos", "ftype", "fsub",
            "fms2", "fls2")]

    fixed = ctypes.cast(ptr, ctypes.POINTER(Fixed)).contents
    return f"{fixed.fms >> 16}.{fixed.fms & 0xFFFF}.{fixed.fls >> 16}.{fixed.fls & 0xFFFF}"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    original, patched = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    a, b = sections(original), sections(patched)

    print(f"原版：{original}  ({file_version(original)})")
    print(f"补丁：{patched}  ({file_version(patched)})")
    print()
    changed, same, missing = [], 0, []
    for name in a:
        if name not in b:
            missing.append(name)
            continue
        if a[name][1] == b[name][1]:
            same += 1
        else:
            changed.append(name)
    for name in b:
        if name not in a:
            changed.append(name + " (新增)")

    print(f"逐字节相同的段（{same}）：" + ", ".join(n for n in a if n in b and a[n][1] == b[n][1]))
    print(f"发生变化的段：{', '.join(changed) if changed else '无'}")
    if missing:
        print("补丁中缺失的段：" + ", ".join(missing))

    code_ok = all(
        a[n][1] == b.get(n, (0, b""))[1] for n in (".text", ".rdata", ".data") if n in a
    )
    rsrc_changed = ".rsrc" in changed
    print()
    print("代码/数据段保持一致：", "是" if code_ok else "否")
    print("资源段已改变：", "是" if rsrc_changed else "否")
    ok = code_ok and rsrc_changed and not missing
    print("结论：", "通过（仅界面资源被修改）" if ok else "异常，请检查")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
