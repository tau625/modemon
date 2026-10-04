#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quantify how much of the backend is actually recoverable.

Answers: for each of the 172 compiled modules, how many function-level symbols and
how many docstrings survived Cython compilation? That bounds how much of a
reimplementation can be driven by recovered spec vs. pure guesswork.

Writes reports/11-recoverability.md
"""
import os
import re
from collections import defaultdict

RE = r"E:\02_Installers\DailyApps\Modex-MH-Agent-RE"
STRINGS = os.path.join(RE, "strings")
OUT = os.path.join(RE, "reports", "11-recoverability.md")
MANIFEST = os.path.join(RE, "reports", "build-inputs-paths.txt")

QUAL = re.compile(r"^([a-z_][a-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)$")
# docstring-ish: sentence-like, has spaces/punctuation, not a symbol or path
SYMISH = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def is_docstring(s):
    if SYMISH.match(s):
        return False
    if s.startswith(("/", "\\", "http", "D:", "E:")):
        return False
    if len(s) < 12:
        return False
    # must contain a space and read like prose (or CJK)
    if " " not in s and not any("\u4e00" <= c <= "\u9fff" for c in s):
        return False
    return True


# CPython/Cython interpreter boilerplate pollutes the string table heavily.
# Anything matching these is runtime furniture, not Modex application knowledge.
BOILER = re.compile(
    r"(coroutine|async generator|traceback|BaseException|__dict__ slot|metaclass|"
    r"shared cython type|positional argument|keyword argument|PyObject|"
    r"already been imported|Re-initialisation|DOS mode|%\.200s|%\.30s|%U|%S\b|"
    r"unhashable|not subscriptable|not iterable|must be a|should have returned|"
    r"Interpreter change|join\(\) result|descriptor|buffer|memoryview)",
    re.I,
)


def is_app_text(s):
    """Genuine Modex-side text: Chinese, or English mentioning app domain terms."""
    if any("\u4e00" <= c <= "\u9fff" for c in s):
        return True  # CJK cannot be interpreter boilerplate
    if BOILER.search(s):
        return False
    return bool(re.search(
        r"(skill|workflow|artifact|paper|editor|chat|checkpoint|workspace|docx|latex|"
        r"capsule|license|account|wallet|figure|prompt|template|proxy|integrity|"
        r"manifest|update|render|token|model)",
        s, re.I))


def main():
    per_mod_syms = defaultdict(set)
    per_mod_docs = defaultdict(set)
    boilerplate = defaultdict(set)

    for fn in os.listdir(STRINGS):
        if not fn.endswith(".strings.txt"):
            continue
        mod = fn.replace(".cp311-win_amd64.pyd.strings.txt", "").replace(".strings.txt", "")
        with open(os.path.join(STRINGS, fn), "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                s = line.strip()
                m = QUAL.match(s)
                if m:
                    name = m.group(2)
                    if not name.startswith("__pyx"):  # drop Cython internals
                        per_mod_syms[mod].add(name)
                elif is_docstring(s):
                    if is_app_text(s):
                        per_mod_docs[mod].add(s)
                    else:
                        boilerplate[mod].add(s)
        # CJK docstrings live in the separate high-precision dump
    cjk = os.path.join(RE, "reports", "cjk-strings-from-pyd.md")
    if os.path.exists(cjk):
        cur = None
        with open(cjk, "r", encoding="utf-8") as fh:
            for line in fh:
                hm = re.match(r"^## (\S+)\.cp311-win_amd64\.pyd", line)
                if hm:
                    cur = hm.group(1)
                    continue
                if line.startswith("- ") and cur:
                    per_mod_docs[cur].add(line[2:].strip())

    # manifest: how many backend source files exist
    backend_files = []
    with open(MANIFEST, "r", encoding="utf-8") as fh:
        for line in fh:
            if "  " not in line:
                continue
            p = line.split("  ", 1)[1].strip()
            if p.startswith("web/backend/") and p.endswith(".py"):
                backend_files.append(p)

    mods = sorted(set(per_mod_syms) | set(per_mod_docs) | set(boilerplate))
    tot_syms = sum(len(v) for v in per_mod_syms.values())
    tot_docs = sum(len(v) for v in per_mod_docs.values())
    tot_boiler = sum(len(v) for v in boilerplate.values())

    L = []
    L.append("# 后端可复现性量化评估")
    L.append("")
    L.append("**问题**：Modex 的后端（176 个源文件 / 172 个 Cython `.pyd`）能被复现到什么程度？")
    L.append("")
    L.append("**方法**：Cython 编译后，**函数名（qualname）与 docstring 会保留在字符串表中**，")
    L.append("而**函数体逻辑不会**。因此可复现性 ≈ 我们能恢复多少「接口规格」，")
    L.append("再加上多少「行为描述」。下面逐模块量化。")
    L.append("")
    L.append("## 总览")
    L.append("")
    L.append("| 指标 | 值 |")
    L.append("|---|---|")
    L.append("| 后端源文件（构建清单口径） | **%d** |" % len(backend_files))
    L.append("| 编译模块（.pyd/.pyc） | **%d** |" % len(mods))
    L.append("| 恢复出的**函数级符号**（已剔除 `__pyx_*` 内部名） | **%d** |" % tot_syms)
    L.append("| 恢复出的**业务语义文本**（docstring/日志/错误信息/策略注释） | **%d** |" % tot_docs)
    L.append("| 已识别并剔除的**解释器样板串**（噪声，非产品知识） | %d |" % tot_boiler)
    L.append("")
    L.append("> ⚠️ 初版脚本把 %d 条" % (tot_docs + tot_boiler))
    L.append("> 全部计为产品知识，其中绝大多数实为 CPython/Cython 运行时错误消息")
    L.append("> （如 `can't send non-None value to a just-started coroutine`）。")
    L.append("> 现已剔除。**保留这条修正记录**，以免高估可复现性。")
    L.append("")
    L.append("> ⚠️ 关键：**函数体实现（算法、SQL、状态转移）零恢复**。")
    L.append("> 符号与文本只能界定「有什么函数、大致干什么」，不能给出「怎么做的」。")
    L.append("")
    L.append("## 逐模块恢复度（按符号数排序，前 45）")
    L.append("")
    L.append("| 模块 | 函数符号 | 行为描述 | 相对恢复度 |")
    L.append("|---|---|---|---|")
    for mod in sorted(mods, key=lambda m: -len(per_mod_syms[m]))[:45]:
        ns, nd = len(per_mod_syms[mod]), len(per_mod_docs[mod])
        if ns >= 40 and nd >= 15:
            verdict = "**高**（接口清晰）"
        elif ns >= 15 or nd >= 10:
            verdict = "中"
        elif ns or nd:
            verdict = "低"
        else:
            verdict = "**几乎无**"
        L.append("| `%s` | %d | %d | %s |" % (mod, ns, nd, verdict))
    L.append("")
    weak = [m for m in mods if len(per_mod_syms[m]) == 0 and len(per_mod_docs[m]) == 0]
    L.append("## 恢复度为「几乎无」的模块（%d 个）" % len(weak))
    L.append("")
    L.append("这些模块只恢复了模块名与 `__pyx_*` 内部符号，**没有任何语义信息**：")
    L.append("")
    for m in weak[:40]:
        L.append("- `%s`" % m)
    if len(weak) > 40:
        L.append("- …（其余 %d 个）" % (len(weak) - 40))
    L.append("")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")

    print("backend .py files: %d" % len(backend_files))
    print("modules analysed : %d" % len(mods))
    print("function symbols : %d" % tot_syms)
    print("behaviour texts  : %d" % tot_docs)
    print("weak modules     : %d" % len(weak))
    print("written ->", OUT)


if __name__ == "__main__":
    main()
