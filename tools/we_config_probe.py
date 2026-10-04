#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parameterized probing of workflow_engine's pure data accessors.

Once skill names are known (from _comp_en_steps / _comp_zh_steps), a family of
pure accessors can be evaluated to recover REAL configuration data: per-skill
minimum output sizes, required companion files, inactivity timeouts, template
dependencies, and the Chinese competition step list.

Only explicitly whitelisted, side-effect-free accessors are called.
Writes reports/16-workflow-engine-config.md
"""
import json
import os
import subprocess

BACKEND = r"E:\02_Installers\DailyApps\Modex-MH-Agent\resources\app\backend"
PY = r"E:\02_Installers\DailyApps\Modex-MH-Agent\runtime\python\python.exe"
RE = r"E:\02_Installers\DailyApps\Modex-MH-Agent-RE"
OUT = os.path.join(RE, "reports", "16-workflow-engine-config.md")

PROBE = '''
import json, sys, io, contextlib
sys.path.insert(0, BACKEND_PATH)
m = __import__("services.workflow_engine", fromlist=["*"])
res = {}

def call(label, fn, *a, **kw):
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            r = fn(*a, **kw)
        try:
            json.dumps(r, default=repr)
            v = r
        except Exception:
            v = repr(r)
        res[label] = {"ok": True, "value": v}
    except BaseException as e:
        res[label] = {"ok": False, "error": "%s: %s" % (type(e).__name__, str(e)[:200])}

call("_comp_zh_steps()", m._comp_zh_steps)

skills = set()
for listfn in ("_comp_en_steps", "_comp_zh_steps"):
    try:
        for s in getattr(m, listfn)():
            n = getattr(s, "skill_name", None)
            if n:
                skills.add(n)
    except BaseException:
        pass
res["_skills_discovered"] = {"ok": True, "value": sorted(skills)}

for s in sorted(skills):
    call("_min_size_for(%r)" % s, m._min_size_for, s)
    call("_required_companions_for(%r)" % s, m._required_companions_for, s)
    call("_step_inactivity_timeout(%r)" % s, m._step_inactivity_timeout, s)
    call("_skill_template_dependencies(%r)" % s, lambda x: list(m._skill_template_dependencies(x)), s)
    call("_compute_health_blocks(%r)" % s, m._compute_health_blocks, s, True)

for t in ("comp_cumcm", "comp_huawei", "comp_mcm", "comp_apmcm", "comp_mathorcup",
          "comp_zh", "comp_en", "course_paper", "thesis_proposal"):
    call("_resolve_competition_page_rule(%r)" % t, m._resolve_competition_page_rule, t, None)

for s in sorted(skills)[:6]:
    call("_resolve_step_effort(%r)" % s, m._resolve_step_effort, {}, s)

sys.stdout.write(json.dumps(res, ensure_ascii=False, default=repr))
'''

STRIP = "'\""


def main():
    src = PROBE.replace("BACKEND_PATH", repr(BACKEND))
    err = ""
    try:
        p = subprocess.run([PY, "-c", src], capture_output=True, timeout=300, cwd=BACKEND)
        out = p.stdout.decode("utf-8", "replace").strip()
        res = json.loads(out) if out.startswith("{") else {}
        err = p.stderr.decode("utf-8", "replace")[-400:]
    except subprocess.TimeoutExpired:
        res, err = {}, "timeout"

    ok = {k: v for k, v in res.items() if v.get("ok")}
    bad = {k: v for k, v in res.items() if not v.get("ok")}

    L = []
    L.append("# `services.workflow_engine` 配置数据恢复（参数化探测）")
    L.append("")
    L.append("**原理**：`_comp_zh_steps(first_skill='comp-prob-analysis', paper_skill='comp-paper-zh')`")
    L.append("的默认参数可见，等价零参可调；一旦拿到技能名，一整族**纯访问器**即可求值。")
    L.append("")
    L.append("**只调用白名单内的无副作用访问器**（未调用任何写文件 / 启动进程 / 网络函数）。")
    L.append("")
    L.append("| 结果 | 数量 |")
    L.append("|---|---|")
    L.append("| 成功调用 | **%d** |" % len(ok))
    L.append("| 失败调用 | %d |" % len(bad))
    L.append("")

    sk = ok.get("_skills_discovered", {}).get("value") or []
    if sk:
        L.append("## 发现的技能名（%d）" % len(sk))
        L.append("")
        L.append(", ".join("`%s`" % s for s in sk))
        L.append("")

    zh = ok.get("_comp_zh_steps()")
    if zh:
        L.append("## ★ 中文竞赛步骤列表 `_comp_zh_steps()`")
        L.append("")
        L.append("```")
        L.append(str(zh["value"])[:6000])
        L.append("```")
        L.append("")

    L.append("## 逐技能配置数据")
    L.append("")
    for key in ("_min_size_for", "_required_companions_for", "_step_inactivity_timeout",
                "_skill_template_dependencies", "_compute_health_blocks"):
        rows = {k: v["value"] for k, v in ok.items() if k.startswith(key + "(")}
        if not rows:
            continue
        L.append("### `%s`" % key)
        L.append("")
        L.append("| skill | 值 |")
        L.append("|---|---|")
        for k in sorted(rows):
            name = k[k.index("(") + 1:].strip(STRIP)
            val = json.dumps(rows[k], ensure_ascii=False, default=repr)
            L.append("| `%s` | `%s` |" % (name, val[:220]))
        L.append("")

    pr = {k: v["value"] for k, v in ok.items() if k.startswith("_resolve_competition_page_rule")}
    if pr:
        L.append("## 竞赛页码规则 `_resolve_competition_page_rule`")
        L.append("")
        L.append("| template | 返回值 |")
        L.append("|---|---|")
        for k in sorted(pr):
            t = k[k.index("(") + 1:k.rindex(")")].strip(STRIP)
            L.append("| `%s` | `%s` |" % (t, json.dumps(pr[k], ensure_ascii=False, default=repr)[:260]))
        L.append("")

    ef = {k: v["value"] for k, v in ok.items() if k.startswith("_resolve_step_effort")}
    if ef:
        L.append("## 默认思考强度 `_resolve_step_effort({}, skill)`")
        L.append("")
        for k in sorted(ef):
            s = k[k.index("(") + 1:k.rindex(")")].strip(STRIP)
            L.append("- `%s` → `%s`" % (s, ef[k]))
        L.append("")

    if bad:
        L.append("## 调用失败")
        L.append("")
        for k in sorted(bad):
            L.append("- `%s` — %s" % (k, bad[k]["error"]))
        L.append("")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")

    print("OK %d / %d" % (len(ok), len(res)))
    if zh:
        print("  _comp_zh_steps() ->", str(zh["value"])[:500])
    print("  skills discovered:", len(sk))
    if err.strip():
        print("stderr tail:", err[:300])
    print("written ->", OUT)


if __name__ == "__main__":
    main()
