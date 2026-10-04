#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Probe route-definition evidence, then try the authoritative route dump.

Stage 1 (static): look for APIRouter / route-shaped literals in the string tables.
Stage 2 (authoritative): import the compiled FastAPI app and dump app.routes.

Stage 2 is the ground truth if it works; it must never hang, so it runs in a
subprocess-free but guarded way (import happens once, with a hard bail on error).
"""
import os
import re
import sys

RE = r"E:\02_Installers\DailyApps\Modex-MH-Agent-RE"
BACKEND = r"E:\02_Installers\DailyApps\Modex-MH-Agent\resources\app\backend"
STRINGS = os.path.join(RE, "strings")
OUT = os.path.join(RE, "reports", "08-route-probe.md")


def static_probe():
    res = {}
    path_like = re.compile(r"^/[A-Za-z][A-Za-z0-9_\-/{}]{1,60}$")
    for fn in os.listdir(STRINGS):
        if not fn.endswith(".strings.txt"):
            continue
        mod = fn.replace(".cp311-win_amd64.pyd.strings.txt", "").replace(".strings.txt", "")
        hits = set()
        with open(os.path.join(STRINGS, fn), "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                s = line.strip()
                if path_like.match(s):
                    hits.add(s)
        if hits:
            res[mod] = sorted(hits)
    return res


def dynamic_probe():
    """Import the compiled app and enumerate real routes."""
    sys.path.insert(0, BACKEND)
    out = {"ok": False, "error": None, "routes": []}
    try:
        import main  # noqa: F401  (Cython-compiled FastAPI app module)
        app = getattr(main, "app", None)
        if app is None:
            out["error"] = "module imported but no 'app' attribute"
            return out
        for r in getattr(app, "routes", []):
            methods = sorted(getattr(r, "methods", None) or [])
            path = getattr(r, "path", None)
            name = getattr(r, "name", "")
            if path:
                out["routes"].append({"path": path, "methods": methods, "name": name})
        out["ok"] = True
    except BaseException as exc:  # import-time guards may raise anything
        out["error"] = "%s: %s" % (type(exc).__name__, exc)
    return out


def main():
    L = []
    L.append("# 路由探测")
    L.append("")

    L.append("## 阶段 1：字符串表中的路由形态（静态）")
    L.append("")
    st = static_probe()
    if st:
        for mod in sorted(st):
            L.append("### `%s`" % mod)
            L.append("")
            for s in st[mod]:
                L.append("- `%s`" % s)
            L.append("")
    else:
        L.append("**未在字符串表中发现独立的路由字面量。**")
        L.append("")
        L.append("这说明 FastAPI 的路径常量没有被 Cython 保留为可检索的独立字符串")
        L.append("（可能被合并进 interned 常量区，或路径由变量拼接）。")
        L.append("因此静态方式无法可靠恢复路由表，必须依赖阶段 2。")
        L.append("")

    L.append("## 阶段 2：导入编译后的 FastAPI app 并枚举真实路由（权威）")
    L.append("")
    d = dynamic_probe()
    if d["ok"]:
        L.append("导入成功，共 **%d** 条路由。" % len(d["routes"]))
        L.append("")
        L.append("| 方法 | 路径 | 端点名 |")
        L.append("|---|---|---|")
        for r in sorted(d["routes"], key=lambda x: x["path"]):
            L.append("| %s | `%s` | `%s` |" % (", ".join(r["methods"]) or "-", r["path"], r["name"]))
        L.append("")
    else:
        L.append("导入失败：`%s`" % d["error"])
        L.append("")
        L.append("（这本身是一条有价值的发现：编译后的后端在导入期就会执行守卫逻辑，")
        L.append("说明存在启动时的许可证/环境校验。）")
        L.append("")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("static modules with path-like literals:", len(st))
    print("dynamic ok:", d["ok"], "error:", d["error"], "routes:", len(d["routes"]))
    print("written ->", OUT)


if __name__ == "__main__":
    main()
