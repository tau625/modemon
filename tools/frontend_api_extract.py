#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recover the HTTP/WS API surface from the minified frontend bundle.

The compiled backend refuses out-of-band import (runtime guard), and FastAPI
route literals were not preserved in the Cython string table -- so the frontend,
which must call every endpoint, is the authoritative remaining source.

Deterministic: pure regex over the bundle, no LLM, cannot overflow context.

Writes reports/09-frontend-api-surface.md
"""
import os
import re
from collections import defaultdict

DIST = r"E:\02_Installers\DailyApps\Modex-MH-Agent\resources\app\dist\assets"
OUT = r"E:\02_Installers\DailyApps\Modex-MH-Agent-RE\reports\09-frontend-api-surface.md"

# quoted literals that look like API paths
STR_RE = re.compile(r"""['"`](/[A-Za-z0-9_\-./{}$:\[\]]{2,120})['"`]""")
# template literals with interpolation, e.g. `/api/chat/${id}/run`
TPL_RE = re.compile(r"`(/[A-Za-z0-9_\-./{}$:\[\]()]{2,140})`")
# absolute external endpoints
URL_RE = re.compile(r"""['"`](https?://[A-Za-z0-9_\-.:/@?=&%#]{4,160})['"`]""")
# websocket constructor sites
WS_RE = re.compile(r"""(?:WebSocket|ws://|wss://)[^'"`]{0,40}['"`]([^'"`]{2,140})['"`]""")
# react-router style path definitions are usually plain strings; capture common nouns
ROUTE_HINT = re.compile(r"""['"`](/(?:workflows?|chat|editor|artifacts?|settings|account|dashboard|library|latex|checkpoints?|new)[A-Za-z0-9_\-/:{}.]*)['"`]""")

SKIP_PREFIX = ("/assets/", "/logo", "/favicon", "/icons", "/static/", "/node_modules")


def scan():
    api = defaultdict(set)
    ws = defaultdict(set)
    ext = defaultdict(set)
    router = defaultdict(set)
    if not os.path.isdir(DIST):
        return api, ws, ext, router
    for fn in sorted(os.listdir(DIST)):
        if not fn.endswith(".js"):
            continue
        p = os.path.join(DIST, fn)
        with open(p, "r", encoding="utf-8", errors="replace") as fh:
            txt = fh.read()
        for rx in (STR_RE, TPL_RE):
            for m in rx.finditer(txt):
                s = m.group(1)
                if s.startswith(SKIP_PREFIX):
                    continue
                if s.startswith("/api/") or s.startswith("/ws/") or s.startswith("/v1/"):
                    (api if not s.startswith("/ws/") else ws)[fn].add(s)
                elif ROUTE_HINT.match(s):
                    router[fn].add(s)
        for m in URL_RE.finditer(txt):
            u = m.group(1)
            if not any(d in u for d in ("w3.org", "schema.org", "example.com", "localhost")):
                ext[fn].add(u)
        for m in WS_RE.finditer(txt):
            v = m.group(1)
            if "ws" in v.lower() or v.startswith("/"):
                ws[fn].add(v)
    return api, ws, ext, router


def main():
    api, ws, ext, router = scan()
    all_api = sorted({s for v in api.values() for s in v})
    all_ws = sorted({s for v in ws.values() for s in v})
    all_ext = sorted({s for v in ext.values() for s in v})
    all_router = sorted({s for v in router.values() for s in v})

    L = []
    L.append("# 前端 bundle 提取的 API 面（确定性脚本产出）")
    L.append("")
    L.append("来源：`resources/app/dist/assets/*.js`（Vite minified，无 sourcemap）。")
    L.append("")
    L.append("> **为什么用前端而不是后端**：编译后的后端在 import 期即触发守卫")
    L.append("> （`RuntimeInspectionUnavailable: 完整性验证或运行时约束未通过，未执行任何能力`），")
    L.append("> 带外导入被拒绝；且 FastAPI 路由字面量未被 Cython 保留为可检索常量。")
    L.append("> 前端必须调用每一个端点，因此它是当前最可靠的路由来源。")
    L.append("")

    L.append("## A. 后端 API 路径（%d 条）" % len(all_api))
    L.append("")
    groups = defaultdict(list)
    for s in all_api:
        parts = [x for x in s.split("/") if x]
        key = parts[1] if len(parts) > 1 else s
        groups[key].append(s)
    L.append("| 资源域 | 条数 | 路径 |")
    L.append("|---|---|---|")
    for k in sorted(groups):
        ps = sorted(set(groups[k]))
        shown = "<br>".join("`%s`" % x for x in ps[:16])
        if len(ps) > 16:
            shown += "<br>…（共 %d）" % len(ps)
        L.append("| `%s` | %d | %s |" % (k, len(ps), shown))
    L.append("")

    L.append("## B. WebSocket / 实时通道（%d 条）" % len(all_ws))
    L.append("")
    for s in all_ws:
        L.append("- `%s`" % s)
    L.append("")

    L.append("## C. 前端路由路径（%d 条，React Router 线索）" % len(all_router))
    L.append("")
    for s in all_router:
        L.append("- `%s`" % s)
    L.append("")

    L.append("## D. 外部端点（%d 条）" % len(all_ext))
    L.append("")
    for s in all_ext:
        L.append("- `%s`" % s)
    L.append("")

    L.append("## E. 各 chunk 的 API 调用密度")
    L.append("")
    L.append("| chunk | API 路径数 |")
    L.append("|---|---|")
    for fn in sorted(api, key=lambda f: -len(api[f])):
        L.append("| `%s` | %d |" % (fn, len(api[fn])))
    L.append("")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")

    flat = os.path.join(os.path.dirname(OUT), "_api-paths.txt")
    with open(flat, "w", encoding="utf-8") as fh:
        fh.write("\n".join(all_api) + "\n")

    print("api paths: %d" % len(all_api))
    print("ws: %d ; router: %d ; external: %d" % (len(all_ws), len(all_router), len(all_ext)))
    print("written ->", OUT)


if __name__ == "__main__":
    main()
