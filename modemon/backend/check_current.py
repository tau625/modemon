#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查当前流水线状态 + 两个钩子是否落库。"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND = Path(__file__).resolve().parent
DB = BACKEND / "db" / "modemon.db"

con = sqlite3.connect(str(DB))
con.row_factory = sqlite3.Row

print("=== 最近 3 个工作流 ===")
rows = con.execute(
    "SELECT id, title, status, created_at FROM workflows"
    " ORDER BY rowid DESC LIMIT 3").fetchall()
for r in rows:
    print("  %s  %-22s %-12s %s" % (r["id"][:12], (r["title"] or "")[:22],
                                   r["status"], r["created_at"]))

# 优先用命令行指定的 workflow_id（有多个同名工作流，容易查错）
target = sys.argv[1] if len(sys.argv) > 1 else ""
wid = target if target else (rows[0]["id"] if rows else "")
print("\n=== 步骤状态（最新工作流 %s）===" % wid[:12])
for r in con.execute(
        "SELECT skill_name, status, error_message, started_at, completed_at"
        " FROM workflow_steps WHERE workflow_id=? ORDER BY step_order", (wid,)):
    mark = {"completed": "[x]", "running": "[>]", "pending": "[ ]",
            "failed": "[!]", "waiting_checkpoint": "[P]"}.get(r["status"], "[?]")
    print("  %s %-24s %-10s %s" % (mark, r["skill_name"], r["status"],
                                  (r["error_message"] or "")[:70]))

print("\n=== 自定义钩子事件（result_audit / figure_render）===")
ev_rows = con.execute(
    "SELECT workflow_id, kind, state, title, safe_detail, evidence_json, started_at"
    " FROM chat_run_events WHERE kind IN ('result_audit','figure_render')"
    " ORDER BY rowid DESC LIMIT 8").fetchall()
if not ev_rows:
    print("  ✗ 全库无自定义事件")
for r in ev_rows:
    ev = json.loads(r["evidence_json"] or "{}")
    print("\n  [%s] wf=%s @ %s" % (r["kind"], r["workflow_id"][:10], r["started_at"]))
    print("     title:", (r["title"] or "")[:60])
    print("     detail:", (r["safe_detail"] or "")[:80])
    print("     evidence:", json.dumps(ev, ensure_ascii=False)[:300])
    if ev == {}:
        print("     ✗ 载荷被剥空")
    if r["kind"] == "result_audit":
        print("     verdict =", ev.get("verdict"))
    if r["kind"] == "figure_render":
        for it in (ev.get("rendered") or [])[:3]:
            print("     rendered:", it.get("spec"), "->", it.get("png") or it.get("svg"))

print("\n=== 工作区产物（最新）===")
import glob
ws_dirs = sorted(glob.glob(r"C:\Users\SAKE\AppData\Local\Temp\modemon-full-*\ws"),
                 key=lambda p: Path(p).stat().st_mtime, reverse=True)
if ws_dirs:
    ws = Path(ws_dirs[0])
    print(" ", ws)
    for p in sorted(ws.rglob("*")):
        if p.is_file():
            print("   %8d B  %s" % (p.stat().st_size, p.relative_to(ws).as_posix()))

con.close()
