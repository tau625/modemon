#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic surface extraction -- no LLM involved, cannot overflow context.

Extracts, from already-collected artefacts:
  A. HTTP route table     <- strings/_merged_strings.txt + per-module .strings.txt
  B. IPC channel table    <- asar/*.js  (Electron ipcMain/ipcRenderer)
  C. Backend module map   <- qualname symbol table (module -> top-level functions)
  D. WebSocket / event type names
  E. Chinese-string index <- reports/cjk-strings-from-pyd.md

Writes reports/07-surface-extract.md
"""
import os
import re
from collections import defaultdict

RE = r"E:\02_Installers\DailyApps\Modex-MH-Agent-RE"
STRINGS = os.path.join(RE, "strings")
ASAR = os.path.join(RE, "asar")
OUT = os.path.join(RE, "reports", "07-surface-extract.md")

ROUTE_RE = re.compile(r"/api/[A-Za-z0-9_{}\-/\.]*")
WS_RE = re.compile(r"/ws/[A-Za-z0-9_{}\-/\.]*")
QUALNAME_RE = re.compile(r"^([a-z_][a-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)$")

# Electron IPC channels
IPC_RE = re.compile(
    r"""ipc(?:Main|Renderer)\s*\.\s*(?:handle|on|once|invoke|send|sendSync)\s*\(\s*['"]([^'"]+)['"]"""
)
IPC_RE2 = re.compile(r"""channel\s*[:=]\s*['"]([a-z][a-z0-9:\-_.]{2,60})['"]""")


def read_text(path, limit=None):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read(limit) if limit else fh.read()


def routes():
    """Route paths keyed by the module whose string table contained them."""
    per_module = defaultdict(set)
    merged = os.path.join(STRINGS, "_merged_strings.txt")
    for line in read_text(merged).splitlines():
        for m in ROUTE_RE.finditer(line):
            per_module["(merged)"].add(m.group())
    for fn in os.listdir(STRINGS):
        if not fn.endswith(".strings.txt"):
            continue
        mod = fn.replace(".cp311-win_amd64.pyd.strings.txt", "").replace(".strings.txt", "")
        for line in read_text(os.path.join(STRINGS, fn)).splitlines():
            for m in ROUTE_RE.finditer(line):
                per_module[mod].add(m.group())
    return per_module


def ws_channels():
    found = set()
    for fn in ("_merged_strings.txt",):
        for line in read_text(os.path.join(STRINGS, fn)).splitlines():
            for m in WS_RE.finditer(line):
                found.add(m.group())
            if re.search(r"(websocket|ws_)", line, re.I) and "/" in line and len(line) < 120:
                if line.strip().startswith("/"):
                    found.add(line.strip())
    return found


def ipc():
    per_file = defaultdict(set)
    if not os.path.isdir(ASAR):
        return per_file
    for dp, _d, fns in os.walk(ASAR):
        for fn in fns:
            if not fn.endswith(".js"):
                continue
            p = os.path.join(dp, fn)
            if os.path.getsize(p) > 2_000_000:
                continue
            txt = read_text(p)
            rel = os.path.relpath(p, ASAR)
            for rx in (IPC_RE, IPC_RE2):
                for m in rx.finditer(txt):
                    per_file[rel].add(m.group(1))
    return per_file


def module_map():
    """module -> set of qualnames, from the merged symbol table."""
    mods = defaultdict(set)
    for line in read_text(os.path.join(STRINGS, "_merged_strings.txt")).splitlines():
        line = line.strip()
        m = QUALNAME_RE.match(line)
        if m:
            mods[m.group(1)].add(line)
    return mods


def main():
    rts = routes()
    ipcs = ipc()
    mods = module_map()
    wss = ws_channels()

    all_routes = sorted({r for s in rts.values() for r in s})
    all_ipc = sorted({c for s in ipcs.values() for c in s})

    L = []
    L.append("# 确定性表面提取（脚本产出，非人工推断）")
    L.append("")
    L.append("本文件由 `tools/extract_surface.py` 从已采集的字符串表与 asar 源码直接生成，")
    L.append("**不含任何人工推断**，可视为原始证据索引。")
    L.append("")

    L.append("## A. HTTP 路由")
    L.append("")
    L.append("共提取到 **%d** 条 `/api/...` 路径。" % len(all_routes))
    L.append("")
    # group by first two path segments
    groups = defaultdict(list)
    for r in all_routes:
        parts = [p for p in r.split("/") if p]
        key = "/".join(parts[:2]) if len(parts) >= 2 else r
        groups[key].append(r)
    L.append("| 路由族 | 条数 | 路径 |")
    L.append("|---|---|---|")
    for k in sorted(groups):
        paths = sorted(set(groups[k]))
        shown = "<br>".join("`%s`" % p for p in paths[:14])
        if len(paths) > 14:
            shown += "<br>…（共 %d 条）" % len(paths)
        L.append("| `/%s` | %d | %s |" % (k, len(paths), shown))
    L.append("")
    L.append("### 按所属模块（含这些路由字符串的 .pyd）")
    L.append("")
    L.append("| 模块 | 路由数 |")
    L.append("|---|---|")
    for mod in sorted(rts):
        n = len({r for r in rts[mod]})
        if n:
            L.append("| `%s` | %d |" % (mod, n))
    L.append("")

    L.append("## B. WebSocket / 事件通道")
    L.append("")
    if wss:
        for w in sorted(wss):
            L.append("- `%s`" % w)
    else:
        L.append("未提取到 `/ws/...` 形式的字面量（通道可能由常量拼接或在前端定义）。")
    L.append("")

    L.append("## C. Electron IPC 通道")
    L.append("")
    L.append("共 **%d** 个通道名。" % len(all_ipc))
    L.append("")
    if all_ipc:
        L.append("| 通道 | 出现在 |")
        L.append("|---|---|")
        inv = defaultdict(list)
        for f, chans in ipcs.items():
            for c in chans:
                inv[c].append(f)
        for c in all_ipc:
            L.append("| `%s` | %s |" % (c, ", ".join("`%s`" % f for f in sorted(inv[c]))))
    else:
        L.append("未匹配到 `ipcMain.* / ipcRenderer.*` 形式（可能使用了封装或常量表）。")
    L.append("")

    L.append("## D. 后端模块符号表规模（qualname 计数）")
    L.append("")
    L.append("从字符串表恢复的 `模块.限定名` 符号，可反映每个模块的公开面大小。")
    L.append("")
    L.append("| 模块 | 符号数 | 顶层函数样例 |")
    L.append("|---|---|---|")
    for mod in sorted(mods, key=lambda m: -len(mods[m]))[:60]:
        names = sorted({q.split(".", 1)[1] for q in mods[mod]})
        top = [n for n in names if n.islower() or n.startswith("_")]
        L.append("| `%s` | %d | %s |" % (mod, len(mods[mod]), ", ".join("`%s`" % n for n in top[:6])))
    L.append("")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")

    print("routes: %d unique (%d modules)" % (len(all_routes), len([m for m in rts if rts[m]])))
    print("ipc channels: %d across %d files" % (len(all_ipc), len(ipcs)))
    print("ws literals: %d" % len(wss))
    print("modules with qualnames: %d" % len(mods))
    print("written ->", OUT)


if __name__ == "__main__":
    main()
