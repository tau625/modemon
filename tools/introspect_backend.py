#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Introspect every importable backend module to recover a real specification.

Key discovery: only the top-level `main` module is blocked by the runtime guard
(it runs the integrity check at import). Leaf modules import fine, and Cython
preserves module/class/function docstrings -- which for this codebase are
detailed design documents.

Runs one subprocess per batch so a single bad module cannot kill the sweep.
Writes reports/12-backend-spec-recovered.md + 12-backend-spec.json
"""
import json
import os
import subprocess
import sys

BACKEND = r"E:\02_Installers\DailyApps\Modex-MH-Agent\resources\app\backend"
PY = r"E:\02_Installers\DailyApps\Modex-MH-Agent\runtime\python\python.exe"
RE = r"E:\02_Installers\DailyApps\Modex-MH-Agent-RE"
OUT_MD = os.path.join(RE, "reports", "12-backend-spec-recovered.md")
OUT_JSON = os.path.join(RE, "reports", "12-backend-spec.json")

WORKER = r'''
import json, os, sys, inspect, dataclasses
sys.path.insert(0, r"{backend}")
mods = {mods!r}

ROUTINE_TYPES = ("function", "cython_function_or_method", "builtin_function_or_method",
                 "method_descriptor", "method", "wrapper_descriptor", "classmethod",
                 "staticmethod", "functools.partial")
SKIP_TYPES = ("module", "str", "bytes", "int", "float", "bool", "NoneType", "list",
              "dict", "tuple", "set", "frozenset", "type", "Pattern", "ContextVar")


def sig_of(o):
    try:
        return str(inspect.signature(o))
    except Exception:
        return ""


def doc_of(o):
    try:
        return (inspect.getdoc(o) or "")[:1500]
    except Exception:
        return ""


res = {{}}
for name in mods:
    try:
        m = __import__(name, fromlist=["*"])
    except BaseException as e:
        res[name] = {{"error": "%s: %s" % (type(e).__name__, str(e)[:200])}}
        continue
    entry = {{"doc": (inspect.getdoc(m) or "")[:6000], "classes": [], "functions": [],
              "consts": [], "errors": []}}
    for n, o in sorted(vars(m).items()):
        if n.startswith("__") or n.startswith("_pyx"):
            continue
        tn = type(o).__name__
        try:
            if inspect.isclass(o):
                bases = []
                try:
                    bases = [b.__name__ for b in o.__bases__]
                except Exception:
                    pass
                is_exc = False
                try:
                    is_exc = issubclass(o, BaseException)
                except Exception:
                    pass
                c = {{"name": n, "doc": doc_of(o), "sig": sig_of(o), "bases": bases,
                      "is_exception": is_exc, "fields": [], "methods": []}}
                if dataclasses.is_dataclass(o):
                    try:
                        for f in dataclasses.fields(o):
                            c["fields"].append({{"name": f.name, "type": str(f.type),
                                                 "default": repr(f.default)[:80]}})
                    except Exception:
                        pass
                for mn, mo in sorted(vars(o).items()):
                    if mn.startswith("__") and mn not in ("__init__", "__call__"):
                        continue
                    if type(mo).__name__ in ROUTINE_TYPES or inspect.isroutine(mo):
                        c["methods"].append({{"name": mn, "sig": sig_of(mo), "doc": doc_of(mo)}})
                (entry["errors"] if is_exc else entry["classes"]).append(c)
            elif tn in ROUTINE_TYPES or (callable(o) and tn not in SKIP_TYPES):
                if getattr(o, "__module__", name) in (name, None, "builtins") or tn == "cython_function_or_method":
                    entry["functions"].append({{"name": n, "sig": sig_of(o), "doc": doc_of(o)}})
            elif isinstance(o, (str, int, float, bool, tuple, frozenset, set, bytes)) and not n.startswith("_"):
                s = repr(o)
                if 0 < len(s) <= 400:
                    entry["consts"].append({{"name": n, "value": s}})
            elif tn == "Pattern":
                entry["consts"].append({{"name": n, "value": "re:" + getattr(o, "pattern", "")[:200]}})
        except Exception:
            continue
    res[name] = entry
sys.stdout.write(json.dumps(res, ensure_ascii=False))
'''


def list_modules():
    mods = []
    for dp, _d, fns in os.walk(BACKEND):
        rel = os.path.relpath(dp, BACKEND)
        for fn in fns:
            if fn.endswith(".cp311-win_amd64.pyd"):
                base = fn.split(".")[0]
                mod = base if rel == "." else rel.replace(os.sep, ".") + "." + base
                mods.append(mod)
            elif fn.endswith(".pyc") and not fn.startswith("__"):
                base = fn[:-4]
                mod = base if rel == "." else rel.replace(os.sep, ".") + "." + base
                mods.append(mod)
    return sorted(set(mods))


def main():
    mods = list_modules()
    print("modules discovered:", len(mods))
    results = {}
    BATCH = 12
    for i in range(0, len(mods), BATCH):
        batch = mods[i:i + BATCH]
        src = WORKER.format(backend=BACKEND, mods=batch)
        try:
            p = subprocess.run([PY, "-c", src], capture_output=True, timeout=180,
                               cwd=BACKEND)
            out = p.stdout.decode("utf-8", "replace").strip()
            if out.startswith("{"):
                results.update(json.loads(out))
            else:
                for m in batch:
                    results[m] = {"error": "batch failed: " + (p.stderr.decode("utf-8", "replace")[-200:])}
        except subprocess.TimeoutExpired:
            for m in batch:
                results[m] = {"error": "timeout"}
        print("  batch %d/%d done" % (i // BATCH + 1, (len(mods) + BATCH - 1) // BATCH))

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=1)

    ok = [m for m, v in results.items() if "error" not in v]
    failed = {m: v["error"] for m, v in results.items() if "error" in v}
    n_doc = sum(1 for m in ok if results[m]["doc"].strip())
    n_cls = sum(len(results[m]["classes"]) for m in ok)
    n_exc = sum(len(results[m].get("errors", [])) for m in ok)
    n_fld = sum(len(c.get("fields", [])) for m in ok for c in results[m]["classes"])
    n_mth = sum(len(c["methods"]) for m in ok for c in results[m]["classes"])
    n_fun = sum(len(results[m]["functions"]) for m in ok)
    n_sig = sum(1 for m in ok for f in results[m]["functions"] if f["sig"])
    n_sig += sum(1 for m in ok for c in results[m]["classes"] for x in c["methods"] if x["sig"])
    n_fdoc = sum(1 for m in ok for f in results[m]["functions"] if f["doc"].strip())
    n_cdoc = sum(1 for m in ok for c in results[m]["classes"] for x in c["methods"] if x["doc"].strip())
    n_cst = sum(len(results[m]["consts"]) for m in ok)
    doc_chars = sum(len(results[m]["doc"]) for m in ok)

    L = []
    L.append("# 后端规格恢复（内省法）")
    L.append("")
    L.append("## 关键突破")
    L.append("")
    L.append("**运行期守卫只拦截顶层 `main` 模块**（它在导入时执行完整性校验）。")
    L.append("**叶子模块可以正常导入**，且 Cython 完整保留了大量可内省对象。")
    L.append("")
    L.append("| 可内省对象 | 是否可用 |")
    L.append("|---|---|")
    L.append("| 模块 docstring | ✅ 且本项目的 docstring **就是设计文档** |")
    L.append("| 类名 / 基类 / 是否异常类 | ✅ |")
    L.append("| **方法名与函数签名**（含**类型标注**） | ✅ 见下方样例 |")
    L.append("| dataclass **字段名/类型/默认值** | ✅ |")
    L.append("| 异常类的 **`code` 默认值**（错误码常量） | ✅ |")
    L.append("| 模块级常量 / 正则 / 集合 | ✅ |")
    L.append("| **函数体实现** | ❌ 仍是原生机器码 |")
    L.append("")
    L.append("⇒ 这把「照符号表猜测重写」提升为「**照接口规格复现**」。")
    L.append("")
    L.append("## 恢复统计")
    L.append("")
    L.append("| 指标 | 数量 |")
    L.append("|---|---|")
    L.append("| 尝试导入的模块 | %d |" % len(mods))
    L.append("| 成功导入 | **%d** |" % len(ok))
    L.append("| 失败（守卫/依赖/副作用） | %d |" % len(failed))
    L.append("| 有 docstring 的模块 | **%d**（共 %s 字符） |" % (n_doc, format(doc_chars, ",")))
    L.append("| 恢复出的**类** | **%d** |" % n_cls)
    L.append("| 恢复出的**异常类**（含错误码） | **%d** |" % n_exc)
    L.append("| 恢复出的 **dataclass 字段** | **%d** |" % n_fld)
    L.append("| 恢复出的**类方法** | **%d** |" % n_mth)
    L.append("| 恢复出的**模块级函数** | **%d** |" % n_fun)
    L.append("| 其中有**可用签名**的 | **%d** |" % n_sig)
    L.append("| 有 docstring 的函数 | %d |" % n_fdoc)
    L.append("| 有 docstring 的方法 | %d |" % n_cdoc)
    L.append("| 恢复出的模块级常量 | %d |" % n_cst)
    L.append("")
    if failed:
        L.append("## 导入失败的模块（%d）" % len(failed))
        L.append("")
        for m, e in sorted(failed.items())[:30]:
            L.append("- `%s` — %s" % (m, e))
        L.append("")
    L.append("## 样例：模块 docstring（本项目 docstring 即设计文档）")
    L.append("")
    shown = 0
    for m in sorted(ok):
        d = results[m]["doc"].strip()
        if len(d) < 80:
            continue
        L.append("### `%s`" % m)
        L.append("")
        L.append("```")
        L.append(d[:1500])
        L.append("```")
        L.append("")
        shown += 1
        if shown >= 12:
            break

    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")

    print("\nimported OK : %d / %d" % (len(ok), len(mods)))
    print("classes     : %d" % n_cls)
    print("methods     : %d" % n_mth)
    print("functions   : %d" % n_fun)
    print("with sigs   : %d" % n_sig)
    print("written ->", OUT_MD)


if __name__ == "__main__":
    main()
