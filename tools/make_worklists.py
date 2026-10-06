#!/usr/bin/env python3
"""生成去重后的翻译工作清单（供人工翻译）。

输出：
  build/uniq_dialogs.txt   对话框控件文本（Button/Static/其它字符串类），按出现次数排序
  build/uniq_menus.txt     仅出现在菜单资源里的文本
  build/uniq_strings.txt   字符串表（id -> text）
"""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
BUILD = BASE / "build"
data = json.loads((BUILD / "resources.json").read_text(encoding="utf-8"))
en = data["languages"]["1033"]

CLASS_NAME = {128: "Button", 129: "Edit", 130: "Static", 131: "ListBox", 132: "ComboBox", 133: "ScrollBar", 134: "GroupBox"}


def cls_label(cls):
    if cls[0] == "ordinal":
        return CLASS_NAME.get(cls[1], f"ord{cls[1]}")
    if cls[0] == "string":
        return f"str:{cls[1]}"
    return "none"


# 字符串表
st_lines = []
for sid, text in sorted(en["string_table"].items(), key=lambda kv: int(kv[0])):
    st_lines.append(f"{sid}\t{text}")
(BUILD / "uniq_strings.txt").write_text("\n".join(st_lines) + "\n", encoding="utf-8")

# 菜单
menu_counter = Counter()
for name, menu in en["menus"].items():
    def walk(items):
        for it in items:
            t = it.get("text")
            if t:
                menu_counter[t] += 1
            walk(it.get("children", []))
    if "items" in menu:
        walk(menu["items"])
# 与字符串表重复的集合
st_set = set(en["string_table"].values())
menu_only = [(t, c) for t, c in menu_counter.most_common() if t not in st_set]
(BUILD / "uniq_menus.txt").write_text(
    "\n".join(f"{c}\t{t}" for t, c in menu_only) + "\n", encoding="utf-8")

# 对话框
dlg_counter = Counter()
dlg_class = {}
for name, dlg in en["dialogs"].items():
    if "error" in dlg:
        continue
    if dlg["title"][0] == "string" and dlg["title"][1]:
        key = ("<title>", dlg["title"][1])
        dlg_counter[dlg["title"][1]] += 1
        dlg_class.setdefault(dlg["title"][1], set()).add("<title>")
    for it in dlg["items"]:
        if it["title"][0] == "string" and it["title"][1]:
            t = it["title"][1]
            dlg_counter[t] += 1
            dlg_class.setdefault(t, set()).add(cls_label(it["class"]))
lines = []
for t, c in dlg_counter.most_common():
    classes = ",".join(sorted(dlg_class[t]))
    lines.append(f"{c}\t[{classes}]\t{t}")
(BUILD / "uniq_dialogs.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

print("uniq_strings:", len(st_lines))
print("menu_only:", len(menu_only))
print("uniq_dialogs:", len(dlg_counter))
