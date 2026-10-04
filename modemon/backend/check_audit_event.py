#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证 result_audit 事件是否落库。用法：python check_audit_event.py <workflow_id>"""
import json
import sqlite3
import sys
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
DB = BACKEND / "db" / "modemon.db"
B = "http://127.0.0.1:8770"


def main() -> int:
    wid = sys.argv[1] if len(sys.argv) > 1 else ""

    def get(p, t=30):
        return json.loads(urllib.request.urlopen(B + p, timeout=t).read())

    if not wid:
        ws = get("/api/workflows")
        wid = ws[0]["id"] if ws else ""

    w = get("/api/workflows/" + wid)
    print("工作流 %s | %s" % (wid[:12], w["status"]))
    for i, s in enumerate(w["steps"], 1):
        m = {"completed": "[x]", "running": "[>]", "pending": "[ ]",
             "failed": "[!]", "waiting_checkpoint": "[P]"}.get(s["status"], "[?]")
        print("  %s %d. %-22s %-18s %s"
              % (m, i, s["skill_name"], s["status"],
                 (s.get("error_message") or "")[:60]))

    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row

    print("\n=== result_audit 事件 ===")
    rows = con.execute(
        "SELECT kind,title,safe_detail,evidence_json,started_at"
        " FROM chat_run_events WHERE workflow_id=? AND kind='result_audit'",
        (wid,)).fetchall()
    if not rows:
        print("  （尚无——审计在后台跑，通常需 10–20 分钟；"
              "若步骤 3 刚结束请稍后再查）")
    for r in rows:
        ev = json.loads(r["evidence_json"] or "{}")
        print("  @%s verdict=%s ok=%s triggered_by=%s"
              % ((r["started_at"] or "")[-8:], ev.get("verdict"), ev.get("ok"),
                 ev.get("triggered_by")))
        for n in (ev.get("notes") or [])[:4]:
            print("     note :", str(n)[:110])
        for i in (ev.get("issues") or [])[:5]:
            print("     issue:", str(i)[:120])

    print("\n=== 各 run 汇总 ===")
    for r in con.execute(
        "SELECT m.skill_name, e.run_id, COUNT(*) n FROM chat_run_events e"
        " JOIN chat_messages m ON m.id = e.message_id"
        " WHERE e.workflow_id=? GROUP BY e.run_id ORDER BY m.id", (wid,)
    ):
        last = con.execute(
            "SELECT kind, evidence_json FROM chat_run_events"
            " WHERE run_id=? ORDER BY sequence DESC LIMIT 1", (r["run_id"],)
        ).fetchone()
        ev = json.loads(last["evidence_json"] or "{}")
        print("  %-22s n=%-4d last=%-9s cost=%s"
              % (r["skill_name"], r["n"], last["kind"], ev.get("cost_usd")))

    print("\n=== 工作区产物 ===")
    for d in sorted(Path(r"C:\Users\SAKE\AppData\Local\Temp").glob("modemon-full-*"),
                    key=lambda p: p.stat().st_mtime, reverse=True)[:1]:
        wsd = d / "ws"
        if wsd.is_dir():
            print("  %s" % wsd)
            for p in sorted(x for x in wsd.rglob("*") if x.is_file()):
                print("    %9d B  %s" % (p.stat().st_size, p.relative_to(wsd).as_posix()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
