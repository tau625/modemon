#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract the full implementation spec of services.workflow_engine.

Two levels:
  A. Static spec  -- classes/methods/functions with type-annotated signatures + docstrings
  B. Live probing -- call zero-argument, side-effect-free-looking functions to recover
     actual DATA (e.g. the Chinese/English competition step lists), which annotations
     alone cannot give.

Writes reports/14-workflow-engine-spec.md
"""
import json
import os

RE = r"E:\02_Installers\DailyApps\Modex-MH-Agent-RE"
SPEC = os.path.join(RE, "reports", "12-backend-spec.json")
OUT = os.path.join(RE, "reports", "14-workflow-engine-spec.md")
MOD = "services.workflow_engine"

# name fragments that suggest a pure, zero-arg data accessor worth calling
SAFE_CALL = ("_steps", "_list", "_templates", "_names", "_defaults")


def main():
    spec = json.load(open(SPEC, encoding="utf-8"))
    w = spec.get(MOD)
    if not w or "error" in w:
        raise SystemExit("no spec for %s" % MOD)

    L = []
    L.append("# `services.workflow_engine` 实现规格")
    L.append("")
    L.append("> 产品主线模块（Cython 编译前 **3.1 MB**，后端最大）。")
    L.append("> 规格由内省恢复：**签名与 docstring 是真实的，函数体不可恢复**。")
    L.append("")
    L.append("## 模块 docstring")
    L.append("")
    L.append("```")
    L.append((w.get("doc") or "(空)").strip())
    L.append("```")
    L.append("")

    # ---- module level constants ----
    if w.get("consts"):
        L.append("## 模块级常量（%d）" % len(w["consts"]))
        L.append("")
        L.append("| 名称 | 值 |")
        L.append("|---|---|")
        for c in w["consts"]:
            v = c["value"].replace("|", "\\|")
            L.append("| `%s` | `%s` |" % (c["name"], v[:220]))
        L.append("")

    # ---- exceptions ----
    errs = w.get("errors") or []
    if errs:
        L.append("## 异常类型（%d）" % len(errs))
        L.append("")
        for c in errs:
            L.append("### `%s`" % c["name"])
            L.append("")
            if c.get("bases"):
                L.append("- 基类：%s" % ", ".join("`%s`" % b for b in c["bases"]))
            if c.get("sig"):
                L.append("- 构造签名：`%s`" % c["sig"])
            if c.get("doc"):
                L.append("")
                L.append("```")
                L.append(c["doc"].strip()[:900])
                L.append("```")
            L.append("")

    # ---- classes ----
    L.append("## 类（%d）" % len(w["classes"]))
    L.append("")
    for c in w["classes"]:
        L.append("### `%s`" % c["name"])
        L.append("")
        if c.get("bases"):
            L.append("- 基类：%s" % ", ".join("`%s`" % b for b in c["bases"]))
        if c.get("sig"):
            L.append("- 构造签名：`%s`" % c["sig"])
        if c.get("fields"):
            L.append("- **字段**：")
            L.append("")
            L.append("  | 字段 | 类型 | 默认值 |")
            L.append("  |---|---|---|")
            for f in c["fields"]:
                L.append("  | `%s` | `%s` | `%s` |" % (f["name"], f["type"][:70], f["default"][:50]))
        if c.get("doc"):
            L.append("")
            L.append("```")
            L.append(c["doc"].strip()[:1200])
            L.append("```")
        if c["methods"]:
            L.append("")
            L.append("- **方法（%d）**：" % len(c["methods"]))
            L.append("")
            for m in c["methods"]:
                L.append("  - `%s%s`" % (m["name"], m["sig"]))
                if m["doc"].strip():
                    for line in m["doc"].strip().splitlines():
                        L.append("    > %s" % line.strip())
        L.append("")

    # ---- module functions, grouped ----
    fns = w["functions"]
    L.append("## 模块级函数（%d）" % len(fns))
    L.append("")
    withdoc = [f for f in fns if f["doc"].strip()]
    nodoc = [f for f in fns if not f["doc"].strip()]
    L.append("- 有 docstring：**%d**；仅有签名：%d" % (len(withdoc), len(nodoc)))
    L.append("")
    L.append("### 有行为描述的（按名称排序）")
    L.append("")
    for f in sorted(withdoc, key=lambda x: x["name"]):
        L.append("#### `%s%s`" % (f["name"], f["sig"]))
        L.append("")
        L.append("```")
        L.append(f["doc"].strip()[:1600])
        L.append("```")
        L.append("")
    L.append("### 仅有签名（%d）" % len(nodoc))
    L.append("")
    L.append("```python")
    for f in sorted(nodoc, key=lambda x: x["name"]):
        L.append("%s%s" % (f["name"], f["sig"]))
    L.append("```")
    L.append("")

    # ---- callable candidates ----
    cands = [f for f in fns if "(" in f["sig"] and f["sig"].count("(") == 1
             and f["sig"].strip().endswith(")")]
    L.append("## 可安全试探调用的零参函数（候选 %d）" % len(cands))
    L.append("")
    for f in sorted(cands, key=lambda x: x["name"]):
        L.append("- `%s%s`" % (f["name"], f["sig"]))
    L.append("")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")

    print("classes   :", len(w["classes"]))
    print("methods   :", sum(len(c["methods"]) for c in w["classes"]))
    print("functions :", len(fns), "(with doc: %d)" % len(withdoc))
    print("consts    :", len(w.get("consts") or []))
    print("errors    :", len(errs))
    print("zero-arg callable candidates:", len(cands))
    print("written ->", OUT)


if __name__ == "__main__":
    main()
