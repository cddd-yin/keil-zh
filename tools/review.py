#!/usr/bin/env python3
"""把 resources.json 中的英文界面文本导出为便于人工审校的清单。

用法：python tools/review.py {strings|menus|dialogs|dialogclasses|count}
输出：build/report_<模式>.txt（count 直接打印到屏幕）
"""
from __future__ import annotations
import json
import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
BUILD = BASE / "build"
data = json.loads((BUILD / "resources.json").read_text(encoding="utf-8"))
en = data["languages"]["1033"]
ja = data["languages"].get("1041", {})

CLASS_NAME = {128: "Button", 129: "Edit", 130: "Static", 131: "ListBox", 132: "ComboBox", 133: "ScrollBar", 134: "GroupBox"}


def cls_label(cls):
    if cls[0] == "ordinal":
        return CLASS_NAME.get(cls[1], f"ord:{cls[1]}")
    if cls[0] == "string":
        return f"str:{cls[1]}"
    return "none"


def walk_menus(items, depth=0):
    out = []
    for i, item in enumerate(items):
        out.append(f"{'    ' * depth}{i}: {item.get('text')!r}  flags={item.get('flags')} id={item.get('id')}")
        out += walk_menus(item.get("children", []), depth + 1)
    return out


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "count"
    lines: list[str] = []

    if what == "strings":
        ja_st = ja.get("string_table", {})
        for sid, text in sorted(en["string_table"].items(), key=lambda kv: int(kv[0])):
            mark = "J" if ja_st.get(sid) else " "
            lines.append(f"[{mark}] {sid}\t{text}")
    elif what == "menus":
        for name, menu in sorted(en["menus"].items(), key=lambda kv: int(kv[0])):
            lines.append(f"===== MENU {name} ({menu.get('kind')}) =====")
            lines += walk_menus(menu.get("items", []))
    elif what == "dialogs":
        for name, dlg in sorted(en["dialogs"].items(), key=lambda kv: int(kv[0])):
            if "error" in dlg:
                lines.append(f"===== DIALOG {name} ERROR {dlg['error']}")
                continue
            lines.append(f"===== DIALOG {name} kind={dlg['kind']} title={dlg['title']!r}")
            for it in dlg.get("items", []):
                title = it["title"]
                text = title[1] if title[0] == "string" else ""
                lines.append(f"   cls={cls_label(it['class']):12s} id={it['id']:>6} text={text!r}")
    elif what == "dialogclasses":
        counter = Counter()
        uniq = {}
        for dlg in en["dialogs"].values():
            if "error" in dlg:
                continue
            for it in dlg.get("items", []):
                if it["title"][0] == "string":
                    lab = cls_label(it["class"])
                    counter[lab] += 1
                    if it["title"][1]:
                        uniq.setdefault(lab, set()).add(it["title"][1])
        for lab, n in counter.most_common():
            print(f"{lab:12s} items={n:5d} unique_texts={len(uniq.get(lab, ())) }")
        return 0
    elif what == "count":
        n_menu_items = 0
        for menu in en["menus"].values():
            n_menu_items += len([x for x in walk_menus(menu.get("items", [])) if "text='" in x or ': \'\'' not in x])
        n_dlg_text = 0
        uniq_dlg = set()
        for dlg in en["dialogs"].values():
            if "error" in dlg:
                continue
            if dlg["title"][0] == "string" and dlg["title"][1]:
                n_dlg_text += 1
            for it in dlg.get("items", []):
                if it["title"][0] == "string" and it["title"][1]:
                    n_dlg_text += 1
                    uniq_dlg.add((cls_label(it["class"]), it["title"][1]))
        print(f"english strings: {len(en['string_table'])}")
        print(f"english menus: {len(en['menus'])}")
        print(f"english dialogs: {len(en['dialogs'])}, texts: {n_dlg_text}, unique(cls,text): {len(uniq_dlg)}")
        return 0

    BUILD.mkdir(exist_ok=True)
    (BUILD / f"report_{what}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written build/report_{what}.txt  ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
