#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""流水线进度诊断：查状态、事件、花费，并判断步骤是否仍在推进。"""
import json
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
DB = BACKEND / "db" / "modemon.db"
B = "http://127.0.0.1:8770"

WID = sys.argv[1] if len(sys.argv) > 1 else ""


def get(p, t=30):
    return json.loads(urllib.request.urlopen(B + p, timeout=t).read())


def main() -> int:
    if not WID:
        ws = get("/api/workflows")
        if not ws:
            print("无工作流")
            return 1
        wid = ws[0]["id"]
    else:
        wid = WID

    w = get("/api/workflows/" + wid)
    print("工作流 %s | %s | %s" % (wid[:12], w["title"], w["status"]))
    for i, s in enumerate(w["steps"], 1):
        mark = {"completed": "[x]", "running": "[>]", "pending": "[ ]",
                "failed": "[!]", "waiting_checkpoint": "[P]"}.get(s["status"], "[?]")
        print("  %s %d. %-22s %-18s %s"
              % (mark, i, s["skill_name"], s["status"],
                 (s.get("error_message") or "")[:70]))
    print("在跑:", get("/api/runs")["active"])

    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row

    def count():
        return con.execute(
            "SELECT COUNT(*) c FROM chat_run_events WHERE workflow_id=?", (wid,)
        ).fetchone()["c"]

    n1 = count()
    print("\n事件数: %d（等 40 秒判断是否仍在推进）" % n1)
    time.sleep(40)
    n2 = count()
    print("40 秒后: %d -> %s" % (n2, "仍在推进" if n2 > n1 else "**已停止推进**"))

    print("\n=== 各 run 汇总 ===")
    rows = con.execute(
        "SELECT m.skill_name, e.run_id, COUNT(*) n FROM chat_run_events e"
        " JOIN chat_messages m ON m.id = e.message_id"
        " WHERE e.workflow_id=? GROUP BY e.run_id ORDER BY m.id", (wid,)
    ).fetchall()
    total = 0.0
    for r in rows:
        last = con.execute(
            "SELECT kind,state,evidence_json FROM chat_run_events"
            " WHERE run_id=? ORDER BY sequence DESC LIMIT 1", (r["run_id"],)
        ).fetchone()
        ev = json.loads(last["evidence_json"] or "{}")
        c = ev.get("cost_usd")
        if isinstance(c, (int, float)):
            total += float(c)
        print("  %-22s n=%-4d last=%-7s cost=%-8s code=%-18s model=%s"
              % (r["skill_name"], r["n"], last["kind"], c,
                 ev.get("code") or "-", ev.get("actual_model") or "-"))
    print("累计花费: $%.4f" % total)

    print("\n=== 最近 5 条事件 ===")
    for r in con.execute(
        "SELECT kind,title,safe_detail,started_at FROM chat_run_events"
        " WHERE workflow_id=? ORDER BY rowid DESC LIMIT 5", (wid,)
    ):
        print("  %-8s %-30s %-50s %s"
              % (r["kind"], (r["title"] or "")[:30],
                 (r["safe_detail"] or "")[:50], r["started_at"]))

    ws_dir = None
    for d in Path(r"C:\Users\SAKE\AppData\Local\Temp").glob("modemon-full-*"):
        if ws_dir is None or d.stat().st_mtime > ws_dir.stat().st_mtime:
            ws_dir = d
    if ws_dir:
        print("\n=== 工作区 %s ===" % ws_dir)
        files = sorted((p for p in ws_dir.rglob("*") if p.is_file()),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files[:12]:
            print("  %9d B  %s  %s" % (p.stat().st_size,
                                       time.strftime("%H:%M:%S",
                                                     time.localtime(p.stat().st_mtime)),
                                       p.relative_to(ws_dir).as_posix()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
