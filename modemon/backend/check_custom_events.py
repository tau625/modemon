#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查 figure_render / result_audit 两类自定义事件是否落库。"""
import json
import sqlite3
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
DB = BACKEND / "db" / "modemon.db"


def main() -> int:
    wid = sys.argv[1] if len(sys.argv) > 1 else ""
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row

    q = ("SELECT kind,state,title,safe_detail,evidence_json,started_at"
         " FROM chat_run_events WHERE kind IN ('result_audit','figure_render')")
    args: tuple = ()
    if wid:
        q += " AND workflow_id=?"
        args = (wid,)
    q += " ORDER BY rowid DESC LIMIT 10"

    rows = con.execute(q, args).fetchall()
    print("=== 自定义事件（result_audit / figure_render）===")
    if not rows:
        print("  （无）")
    for r in rows:
        ev = json.loads(r["evidence_json"] or "{}")
        print("  [%s] %s @%s state=%s"
              % (r["kind"], (r["title"] or "")[:40],
                 (r["started_at"] or "")[-8:], r["state"]))
        if r["kind"] == "figure_render":
            for it in (ev.get("rendered") or [])[:3]:
                print("      -> %s  png=%s" % (it.get("spec"), it.get("png")))
            for e in (ev.get("errors") or [])[:3]:
                print("      err:", str(e)[:100])
        else:
            print("      verdict=%s ok=%s triggered_by=%s"
                  % (ev.get("verdict"), ev.get("ok"), ev.get("triggered_by")))
            for n in (ev.get("notes") or [])[:3]:
                print("      note :", str(n)[:100])
            for i in (ev.get("issues") or [])[:4]:
                print("      issue:", str(i)[:110])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
