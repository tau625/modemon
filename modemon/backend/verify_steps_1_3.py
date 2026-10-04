#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""聚焦验证：只跑前 3 步，确认审计钩子触发并落库。

用法：python verify_steps_1_3.py [--audit-timeout 600]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

B = "http://127.0.0.1:8770"
DB = BACKEND / "db" / "modemon.db"

PROBLEM = """2026 年全国大学生数学建模竞赛 A 题（模拟）

某物流公司运营 3 个配送中心（DC1/DC2/DC3）与 4 个需求点（R1–R4）。
供应量为 DC1=35、DC2=25、DC3=30（吨）；需求量为 R1=20、R2=25、R3=20、R4=25（吨）。
单位运价矩阵（元/吨）：

        R1   R2   R3   R4
DC1      8   12   10   14
DC2     11    7   13    9
DC3     12   10    6   11

请建立数学模型，求总运输成本最小的调运方案，并回答：
（1）最优调运方案与最小总成本；
（2）若 DC2 供应量下降 30%，最优成本如何变化；
（3）该方案对运价波动的稳定性分析。
"""

HINTS = {
    "comp-prob-analysis": "把赛题原文中的数据逐条抄录进分析文件。",
    "comp-modeling": "建立线性规划模型，写入 MODELING_REPORT.md。",
    "comp-code": "用 Python 求解，**必须**把结果写入 `figures/all_results.json`。",
}


def http(method, path, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(B + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=3)
    ap.add_argument("--wait-audit-s", type=int, default=900)
    a = ap.parse_args()

    import tempfile
    ws = Path(tempfile.mkdtemp(prefix="modemon-focus-")) / "ws"
    (ws / "user_data").mkdir(parents=True)
    (ws / "user_data" / "problem.txt").write_text(PROBLEM, encoding="utf-8")

    wf = http("POST", "/api/workflows", {
        "template": "comp_cumcm", "title": "聚焦验证(前3步)",
        "enable_checkpoints": True})
    wid = wf["id"]
    steps = [s["skill_name"] for s in wf["steps"]][: a.steps]
    print("工作区: %s" % ws)
    print("工作流: %s" % wid)
    print("步骤: %s\n" % steps)

    for skill in steps:
        q = urllib.parse.urlencode({
            "workspace": str(ws), "max_budget_usd": 5.0,
            "extra_prompt": HINTS.get(skill, ""),
            "permission_mode": "bypassPermissions"})
        t0 = time.monotonic()
        try:
            http("POST", f"/api/workflows/{wid}/steps/{skill}/run?{q}", None, 60)
        except urllib.error.HTTPError as e:
            print("  启动 %s 失败: %s" % (skill, e))
            continue
        status = "running"
        while time.monotonic() - t0 < 1800:
            cur = http("GET", f"/api/workflows/{wid}")
            sv = next((x for x in cur["steps"] if x["skill_name"] == skill), {})
            status = sv.get("status", "?")
            if status != "running":
                break
            time.sleep(6)
        print("  %-22s %-18s %.0fs" % (skill, status, time.monotonic() - t0))
        if status == "waiting_checkpoint":
            cp = http("GET", f"/api/workflows/{wid}/checkpoints/current")
            http("POST", f"/api/workflows/{wid}/checkpoints/resolve",
                 {"action": "approve", "checkpoint_id": (cp or {}).get("checkpoint_id"),
                  "data": {"note": "focus verify"}})

    # 等审计落库
    print("\n等审计事件落库（最多 %d 秒）…" % a.wait_audit_s)
    t0 = time.monotonic()
    found = []
    while time.monotonic() - t0 < a.wait_audit_s:
        con = sqlite3.connect(str(DB))
        con.row_factory = sqlite3.Row
        found = con.execute(
            "SELECT kind, title, evidence_json FROM chat_run_events"
            " WHERE workflow_id=? AND kind IN ('result_audit','figure_render')",
            (wid,)).fetchall()
        con.close()
        if found:
            break
        print("  …%.1f 分钟" % ((time.monotonic() - t0) / 60))
        time.sleep(20)

    print("\n=== 落库事件：%d 条 ===" % len(found))
    for r in found:
        ev = json.loads(r["evidence_json"] or "{}")
        print("  [%s] %s" % (r["kind"], (r["title"] or "")[:50]))
        print("      verdict=%s issues=%d notes=%d"
              % (ev.get("verdict"), len(ev.get("issues") or []),
                 len(ev.get("notes") or [])))
        for n in (ev.get("notes") or [])[:2]:
            print("      note:", str(n)[:100])

    print("\n%s" % ("PASS result_audit 已落库" if any(
        r["kind"] == "result_audit" for r in found) else
        "FAIL result_audit 未落库"))
    return 0 if any(r["kind"] == "result_audit" for r in found) else 1


if __name__ == "__main__":
    raise SystemExit(main())
