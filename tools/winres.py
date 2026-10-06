#!/usr/bin/env python3
"""Win32 PE 资源读写 + 界面格式解析（仅标准库，仅 Windows）。

* 读取/写回：Windows 官方资源 API（LoadLibraryEx / EnumResource* / UpdateResource），
  不执行目标程序；
* 字符串表（RT_STRING）、菜单（RT_MENU）、对话框（RT_DIALOG）的解析与序列化。

本模块是 Keil µVision 汉化补丁的分析层。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import struct
from pathlib import Path

if not hasattr(ctypes, "WinDLL"):
    raise SystemExit("winres 只能在 Windows 上运行。")

RT_MENU = 4
RT_DIALOG = 5
RT_STRING = 6

LOAD_LIBRARY_AS_DATAFILE = 0x00000002
LOAD_LIBRARY_AS_IMAGE_RESOURCE = 0x00000020

MF_POPUP = 0x0010
MF_END = 0x0080
MENUEX_POPUP = 0x0001
MENUEX_END = 0x0080
DS_SETFONT = 0x00000040

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

kernel32.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD]
kernel32.LoadLibraryExW.restype = wintypes.HMODULE
kernel32.FreeLibrary.argtypes = [wintypes.HMODULE]
kernel32.FreeLibrary.restype = wintypes.BOOL

ENUMRESTYPEPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMODULE, ctypes.c_void_p, ctypes.c_ssize_t
)
ENUMRESNAMEPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMODULE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ssize_t
)
ENUMRESLANGPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL,
    wintypes.HMODULE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.WORD,
    ctypes.c_ssize_t,
)

kernel32.EnumResourceTypesW.argtypes = [wintypes.HMODULE, ENUMRESTYPEPROC, ctypes.c_ssize_t]
kernel32.EnumResourceTypesW.restype = wintypes.BOOL
kernel32.EnumResourceNamesW.argtypes = [
    wintypes.HMODULE,
    ctypes.c_void_p,
    ENUMRESNAMEPROC,
    ctypes.c_ssize_t,
]
kernel32.EnumResourceNamesW.restype = wintypes.BOOL
kernel32.EnumResourceLanguagesW.argtypes = [
    wintypes.HMODULE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ENUMRESLANGPROC,
    ctypes.c_ssize_t,
]
kernel32.EnumResourceLanguagesW.restype = wintypes.BOOL

kernel32.FindResourceExW.argtypes = [
    wintypes.HMODULE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.WORD,
]
kernel32.FindResourceExW.restype = wintypes.HRSRC
kernel32.LoadResource.argtypes = [wintypes.HMODULE, wintypes.HRSRC]
kernel32.LoadResource.restype = wintypes.HGLOBAL
kernel32.SizeofResource.argtypes = [wintypes.HMODULE, wintypes.HRSRC]
kernel32.SizeofResource.restype = wintypes.DWORD
kernel32.LockResource.argtypes = [wintypes.HGLOBAL]
kernel32.LockResource.restype = ctypes.c_void_p
kernel32.BeginUpdateResourceW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
kernel32.BeginUpdateResourceW.restype = wintypes.HANDLE
kernel32.UpdateResourceW.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.WORD,
    ctypes.c_void_p,
    wintypes.DWORD,
]
kernel32.UpdateResourceW.restype = wintypes.BOOL
kernel32.EndUpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.BOOL]
kernel32.EndUpdateResourceW.restype = wintypes.BOOL


class ResourceError(RuntimeError):
    pass


class ResourceFormatError(ValueError):
    pass


def _raise(label: str) -> None:
    code = ctypes.get_last_error()
    raise ResourceError(f"{label} 失败：{ctypes.FormatError(code)}（错误码 {code}）")


def _decode_identifier(pointer: int | None) -> int | str:
    value = int(pointer or 0)
    if value <= 0xFFFF:
        return value
    return ctypes.wstring_at(value)


class _Ident:
    """把 int / str 资源标识安全地转换为 Win32 API 需要的指针。"""

    def __init__(self, value: int | str):
        self.value = value
        self._storage = None

    def __enter__(self) -> ctypes.c_void_p:
        if isinstance(self.value, int):
            return ctypes.c_void_p(self.value)
        self._storage = ctypes.c_wchar_p(self.value)
        return ctypes.cast(self._storage, ctypes.c_void_p)

    def __exit__(self, *_: object) -> None:
        self._storage = None


def read_resources(path: str | Path) -> list[dict]:
    """读取 PE 文件全部资源，返回按 (type,name,lang) 排序的列表。"""
    module = kernel32.LoadLibraryExW(
        str(path), None, LOAD_LIBRARY_AS_DATAFILE | LOAD_LIBRARY_AS_IMAGE_RESOURCE
    )
    if not module:
        _raise(f"LoadLibraryExW({path})")

    out: list[dict] = []
    refs: list[object] = []

    def on_type(hmod, type_ptr, _lp):
        rtype = _decode_identifier(type_ptr)

        def on_name(_h, _t, name_ptr, _l):
            rname = _decode_identifier(name_ptr)

            def on_lang(__h, __t, __n, lang, __l):
                with _Ident(rtype) as t, _Ident(rname) as n:
                    hrsrc = kernel32.FindResourceExW(module, t, n, lang)
                    if not hrsrc:
                        _raise("FindResourceExW")
                    size = int(kernel32.SizeofResource(module, hrsrc))
                    hglobal = kernel32.LoadResource(module, hrsrc)
                    if not hglobal:
                        _raise("LoadResource")
                    ptr = kernel32.LockResource(hglobal)
                    if not ptr and size:
                        _raise("LockResource")
                    data = ctypes.string_at(ptr, size) if size else b""
                out.append(
                    {"type": rtype, "name": rname, "lang": int(lang), "size": size, "data": data}
                )
                return True

            cb = ENUMRESLANGPROC(on_lang)
            refs.append(cb)
            with _Ident(rtype) as t, _Ident(rname) as n:
                if not kernel32.EnumResourceLanguagesW(module, t, n, cb, 0):
                    _raise("EnumResourceLanguagesW")
            return True

        cb = ENUMRESNAMEPROC(on_name)
        refs.append(cb)
        with _Ident(rtype) as t:
            if not kernel32.EnumResourceNamesW(module, t, cb, 0):
                _raise("EnumResourceNamesW")
        return True

    cb = ENUMRESTYPEPROC(on_type)
    refs.append(cb)
    try:
        if not kernel32.EnumResourceTypesW(module, cb, 0):
            _raise("EnumResourceTypesW")
    finally:
        kernel32.FreeLibrary(module)
    out.sort(key=lambda item: (str(item["type"]), str(item["name"]), int(item["lang"])))
    return out


def update_resources(path: str | Path, updates: list[dict]) -> None:
    """把一批 {type,name,lang,data} 写回 PE 文件（就地）。任一条失败则整体放弃。"""
    handle = kernel32.BeginUpdateResourceW(str(path), False)
    if not handle:
        _raise(f"BeginUpdateResourceW({path})")
    discard = True
    try:
        for item in updates:
            data = bytes(item["data"])
            buf = ctypes.create_string_buffer(data) if data else None
            ptr = ctypes.cast(buf, ctypes.c_void_p) if buf is not None else None
            with _Ident(item["type"]) as t, _Ident(item["name"]) as n:
                if not kernel32.UpdateResourceW(
                    handle, t, n, int(item["lang"]), ptr, len(data)
                ):
                    _raise(f"UpdateResourceW({item['type']},{item['name']},{item['lang']})")
        discard = False
    finally:
        if not kernel32.EndUpdateResourceW(handle, discard):
            _raise("EndUpdateResourceW")


# --------------------------------------------------------------------------
# 字符串表（RT_STRING）
# --------------------------------------------------------------------------
def parse_string_block(name: int, data: bytes) -> dict[int, str]:
    """解析一个字符串块（16 条），返回 {字符串ID: 文本}。"""
    result: dict[int, str] = {}
    offset = 0
    base = (name - 1) * 16
    for index in range(16):
        if offset + 2 > len(data):
            break
        length = struct.unpack_from("<H", data, offset)[0]
        offset += 2
        byte_len = length * 2
        if offset + byte_len > len(data):
            break
        result[base + index] = data[offset : offset + byte_len].decode(
            "utf-16le", errors="replace"
        )
        offset += byte_len
    return result


def build_string_block(name: int, values: dict[int, str]) -> bytes:
    """按 16 条一块的格式重新打包字符串表。"""
    out = bytearray()
    base = (name - 1) * 16
    for index in range(16):
        encoded = values.get(base + index, "").encode("utf-16le")
        length = len(encoded) // 2
        if length > 0xFFFF:
            raise ResourceError(f"字符串 {base + index} 过长")
        out.extend(struct.pack("<H", length))
        out.extend(encoded)
    return bytes(out)


# --------------------------------------------------------------------------
# 通用小工具 + 菜单（RT_MENU）
# --------------------------------------------------------------------------
def _need(data: bytes, offset: int, size: int) -> None:
    if offset < 0 or offset + size > len(data):
        raise ResourceFormatError(
            f"资源在 {len(data)} 字节处结束，却要在 {offset} 处读取 {size} 字节"
        )


def _align(value: int, boundary: int) -> int:
    return (value + boundary - 1) & ~(boundary - 1)


def _pad(buf: bytearray, boundary: int) -> None:
    while len(buf) % boundary:
        buf.append(0)


def _u16(data: bytes, offset: int) -> tuple[int, int]:
    _need(data, offset, 2)
    return struct.unpack_from("<H", data, offset)[0], offset + 2


def _utf16z(data: bytes, offset: int) -> tuple[str, int]:
    start = offset
    while True:
        value, offset = _u16(data, offset)
        if value == 0:
            return data[start : offset - 2].decode("utf-16le", errors="strict"), offset


def _write_utf16z(buf: bytearray, text: str) -> None:
    buf.extend(text.encode("utf-16le"))
    buf.extend(b"\x00\x00")


def parse_menu(data: bytes) -> dict:
    _need(data, 0, 4)
    version, offset = struct.unpack_from("<HH", data, 0)
    first = 4 + offset
    if first > len(data):
        raise ResourceFormatError("菜单头指针越界")

    def standard(pos: int) -> tuple[list[dict], int]:
        items: list[dict] = []
        while True:
            flags, pos = _u16(data, pos)
            is_popup = bool(flags & MF_POPUP)
            item_id = None
            if not is_popup:
                item_id, pos = _u16(data, pos)
            text, pos = _utf16z(data, pos)
            children: list[dict] = []
            if is_popup:
                children, pos = standard(pos)
            items.append({"flags": flags, "id": item_id, "text": text, "children": children})
            if flags & MF_END:
                return items, pos

    def extended(pos: int) -> tuple[list[dict], int]:
        items: list[dict] = []
        while True:
            pos = _align(pos, 4)
            _need(data, pos, 14)
            item_type, state, item_id = struct.unpack_from("<LLL", data, pos)
            pos += 12
            flags, pos = _u16(data, pos)
            text, pos = _utf16z(data, pos)
            pos = _align(pos, 4)
            help_id = None
            children: list[dict] = []
            if flags & MENUEX_POPUP:
                _need(data, pos, 4)
                help_id = struct.unpack_from("<L", data, pos)[0]
                pos += 4
                children, pos = extended(pos)
            items.append(
                {
                    "type": item_type,
                    "state": state,
                    "id": item_id,
                    "flags": flags,
                    "help_id": help_id,
                    "text": text,
                    "children": children,
                }
            )
            if flags & MENUEX_END:
                return items, pos

    if version == 0:
        items, end = standard(first)
        kind = "standard"
    elif version == 1:
        items, end = extended(first)
        kind = "extended"
    else:
        raise ResourceFormatError(f"不支持的菜单模板版本 {version}")
    return {"kind": kind, "prefix": data[:first], "items": items, "tail": data[end:]}


def serialize_menu(menu: dict) -> bytes:
    out = bytearray(menu["prefix"])

    def write_standard(items: list[dict]) -> None:
        for item in items:
            out.extend(struct.pack("<H", item["flags"]))
            if not (item["flags"] & MF_POPUP):
                out.extend(struct.pack("<H", item["id"] or 0))
            _write_utf16z(out, item["text"])
            if item["flags"] & MF_POPUP:
                write_standard(item["children"])

    def write_extended(items: list[dict]) -> None:
        for item in items:
            _pad(out, 4)
            out.extend(
                struct.pack("<LLLH", item["type"], item["state"], item["id"] or 0, item["flags"])
            )
            _write_utf16z(out, item["text"])
            _pad(out, 4)
            if item["flags"] & MENUEX_POPUP:
                out.extend(struct.pack("<L", item["help_id"] or 0))
                write_extended(item["children"])

    if menu["kind"] == "standard":
        write_standard(menu["items"])
    else:
        write_extended(menu["items"])
    out.extend(menu["tail"])
    return bytes(out)


def iter_menu_items(items: list[dict], prefix: str = ""):
    """遍历菜单节点，产出 (索引路径, 节点)，路径形如 "0/3/1"。"""
    for index, item in enumerate(items):
        path = f"{prefix}{index}"
        yield path, item
        yield from iter_menu_items(item["children"], path + "/")


# --------------------------------------------------------------------------
# 对话框（RT_DIALOG）
# --------------------------------------------------------------------------
def _read_spec(data: bytes, offset: int) -> tuple[tuple[str, object], int]:
    first, nxt = _u16(data, offset)
    if first == 0:
        return ("none", 0), nxt
    if first == 0xFFFF:
        ordinal, nxt = _u16(data, nxt)
        return ("ordinal", ordinal), nxt
    text, nxt = _utf16z(data, offset)
    return ("string", text), nxt


def _write_spec(buf: bytearray, value: tuple[str, object]) -> None:
    kind, payload = value
    if kind == "none":
        buf.extend(struct.pack("<H", 0))
    elif kind == "ordinal":
        buf.extend(struct.pack("<HH", 0xFFFF, int(payload)))
    elif kind == "string":
        _write_utf16z(buf, str(payload))
    else:
        raise ResourceFormatError(f"未知的可变字段类型 {kind}")


def parse_dialog(data: bytes) -> dict:
    _need(data, 0, 4)
    is_extended = struct.unpack_from("<H", data, 2)[0] == 0xFFFF
    pos = 0
    if is_extended:
        _need(data, 0, 26)
        fixed = struct.unpack_from("<HHLLLHhhhh", data, 0)
        pos = 26
        style = fixed[4]
        item_count = fixed[5]
        kind = "extended"
    else:
        _need(data, 0, 18)
        fixed = struct.unpack_from("<LLHhhhh", data, 0)
        pos = 18
        style = fixed[0]
        item_count = fixed[2]
        kind = "standard"

    menu, pos = _read_spec(data, pos)
    window_class, pos = _read_spec(data, pos)
    title, pos = _read_spec(data, pos)
    font = None
    if style & DS_SETFONT:
        if is_extended:
            _need(data, pos, 6)
            point_size, weight = struct.unpack_from("<HH", data, pos)
            italic = data[pos + 4]
            charset = data[pos + 5]
            pos += 6
            typeface, pos = _utf16z(data, pos)
            font = [point_size, weight, italic, charset, typeface]
        else:
            point_size, pos = _u16(data, pos)
            typeface, pos = _utf16z(data, pos)
            font = [point_size, typeface]

    items: list[dict] = []
    for _ in range(item_count):
        pos = _align(pos, 4)
        if is_extended:
            _need(data, pos, 24)
            item_fixed = list(struct.unpack_from("<LLLhhhhL", data, pos))
            pos += 24
            item_id = item_fixed[-1]
        else:
            _need(data, pos, 18)
            item_fixed = list(struct.unpack_from("<LLhhhhH", data, pos))
            pos += 18
            item_id = item_fixed[-1]
        item_class, pos = _read_spec(data, pos)
        item_title, pos = _read_spec(data, pos)
        extra_size, pos = _u16(data, pos)
        if extra_size:
            payload_size = extra_size - 2
            if payload_size < 0:
                raise ResourceFormatError("对话框创建数据大小非法")
            _need(data, pos, payload_size)
            extra_payload = data[pos : pos + payload_size]
            pos += payload_size
        else:
            extra_payload = b""
        items.append(
            {
                "fixed": item_fixed,
                "id": item_id,
                "class": item_class,
                "title": item_title,
                "extra_size": extra_size,
                "extra_payload": extra_payload,
            }
        )
    return {
        "kind": kind,
        "fixed": list(fixed),
        "menu": menu,
        "class": window_class,
        "title": title,
        "font": font,
        "items": items,
        "tail": data[pos:],
    }


def serialize_dialog(dlg: dict) -> bytes:
    out = bytearray()
    if dlg["kind"] == "extended":
        out.extend(struct.pack("<HHLLLHhhhh", *dlg["fixed"]))
    else:
        out.extend(struct.pack("<LLHhhhh", *dlg["fixed"]))
    _write_spec(out, dlg["menu"])
    _write_spec(out, dlg["class"])
    _write_spec(out, dlg["title"])
    if dlg["font"] is not None:
        if dlg["kind"] == "extended":
            point_size, weight, italic, charset, typeface = dlg["font"]
            out.extend(struct.pack("<HHBB", point_size, weight, italic, charset))
            _write_utf16z(out, typeface)
        else:
            point_size, typeface = dlg["font"]
            out.extend(struct.pack("<H", point_size))
            _write_utf16z(out, typeface)
    for item in dlg["items"]:
        _pad(out, 4)
        if dlg["kind"] == "extended":
            out.extend(struct.pack("<LLLhhhhL", *item["fixed"]))
        else:
            out.extend(struct.pack("<LLhhhhH", *item["fixed"]))
        _write_spec(out, item["class"])
        _write_spec(out, item["title"])
        out.extend(struct.pack("<H", item["extra_size"]))
        out.extend(item["extra_payload"])
    out.extend(dlg["tail"])
    return bytes(out)
