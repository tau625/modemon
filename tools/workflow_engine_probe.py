#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Probe zero-argument workflow_engine functions to recover actual DATA.

Signatures alone cannot tell you the Chinese/English competition step lists --
but if the accessor is a pure zero-arg function, calling it does. Runs in a
subprocess with a hard timeout; only functions with no required parameters and
data-accessor-looking names are attempted.

Writes reports/15-workflow-engine-probe.md
"""
import json
import os
import subprocess

BACKEND = r"E:\02_Installers\DailyApps\Modex-MH-Agent\resources\app\backend"
PY = r"E:\02_Installers\DailyApps\Modex-MH-Agent\runtime\python\python.exe"
RE = r"E:\02_Installers\DailyApps\Modex-MH-Agent-RE"
SPEC = os.path.join(RE, "reports", "12-backend-spec.json")
OUT = os.path.join(RE, "reports", "15-workflow-engine-probe.md")
MOD = "services.workflow_engine"

PROBE = r'''
import json, sys, io, contextlib, inspect
sys.path.insert(0, r"{backend}")
m = __import__("services.workflow_engine", fromlist=["*"])
names = {names!r}
out = {{}}
for n in names:
    fn = getattr(m, n, None)
    if fn is None:
        out[n] = {{"error": "missing"}}
        continue
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            r = fn()
        try:
            json.dumps(r)
            val = r
        except Exception:
            val = repr(r)
        out[n] = {{"ok": True, "type": type(r).__name__, "value": val,
                   "stdout": buf.getvalue()[:600]}}
    except BaseException as e:
        out[n] = {{"ok": False, "error": "%s: %s" % (type(e).__name__, str(e)[:200]),
                   "stdout": buf.getvalue()[:400]}}
sys.stdout.write(json.dumps(out, ensure_ascii=False, default=repr))
'''


def main():
    spec = json.load(open(SPEC, encoding="utf-8"))
    fns = spec[MOD]["functions"]

    # select: signature has no required parameter
    cands = []
    for f in fns:
        sig = f["sig"]
        if not sig.startswith("("):
            continue
        inner = sig[1:sig.rfind(")")]
        if inner.strip() == "":
            cands.append(f["name"])
    print("zero-arg functions:", len(cands))

    results = {}
    B = 12
    for i in range(0, len(cands), B):
        batch = cands[i:i + B]
        try:
            p = subprocess.run([PY, "-c", PROBE.format(backend=BACKEND, names=batch)],
                               capture_output=True, timeout=120, cwd=BACKEND)
            out = p.stdout.decode("utf-8", "replace").strip()
            results.update(json.loads(out) if out.startswith("{") else
                           {n: {"ok": False, "error": "batch fail"} for n in batch})
        except subprocess.TimeoutExpired:
            results.update({n: {"ok": False, "error": "timeout"} for n in batch})

    ok = {k: v for k, v in results.items() if v.get("ok")}
    bad = {k: v for k, v in results.items() if not v.get("ok")}

    L = []
    L.append("# `services.workflow_engine` 零参函数试探调用")
    L.append("")
    L.append("**目的**：签名只能说明「收什么返什么」，**不能给出数据内容**。")
    L.append("对无副作用的零参访问器直接调用，可恢复**真实数据**（例如竞赛步骤清单）。")
    L.append("")
    L.append("| 结果 | 数量 |")
    L.append("|---|---|")
    L.append("| 试探的零参函数 | %d |" % len(cands))
    L.append("| 成功返回 | **%d** |" % len(ok))
    L.append("| 抛错/超时 | %d |" % len(bad))
    L.append("")
    if ok:
        L.append("## ★ 成功恢复的真实数据")
        L.append("")
        for k in sorted(ok):
            v = ok[k]
            L.append("### `%s()` → `%s`" % (k, v.get("type")))
            L.append("")
            L.append("```json")
            s = json.dumps(v.get("value"), ensure_ascii=False, indent=1)
            L.append(s[:6000])
            L.append("```")
            L.append("")
    if bad:
        L.append("## 调用失败的（%d）" % len(bad))
        L.append("")
        for k in sorted(bad):
            L.append("- `%s()` — %s" % (k, bad[k].get("error")))
        L.append("")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")

    print("OK: %d / %d" % (len(ok), len(cands)))
    for k in sorted(ok):
        print("  OK  %-42s -> %s" % (k, ok[k].get("type")))
    for k in sorted(bad):
        print("  ERR %-42s %s" % (k, bad[k].get("error")))
    print("written ->", OUT)


if __name__ == "__main__":
    main()
