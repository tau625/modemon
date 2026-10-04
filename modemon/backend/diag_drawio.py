#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诊断 paper-figure-drawio 步骤为何静默超时。"""
import json
import sqlite3
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
DB = BACKEND / "db" / "modemon.db"
WS = Path(r"C:\Users\SAKE\AppData\Local\Temp\modemon-full-il7v2iiu\ws")


def main() -> int:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row

    print("=== paper-figure-drawio 的全部事件 ===")
    rows = con.execute(
        "SELECT e.sequence,e.kind,e.title,e.safe_detail,e.started_at,e.evidence_json"
        " FROM chat_run_events e JOIN chat_messages m ON m.id=e.message_id"
        " WHERE m.skill_name='paper-figure-drawio' ORDER BY e.sequence"
    ).fetchall()
    for r in rows:
        ev = json.loads(r["evidence_json"] or "{}")
        print("  %2d %-8s %-26s %-46s %s"
              % (r["sequence"], r["kind"], (r["title"] or "")[:26],
                 (r["safe_detail"] or "")[:46], ev.get("code") or ""))
    print("  合计 %d 条" % len(rows))

    print("\n=== 对比：paper-figure（第 4 步，成功）的事件 ===")
    rows2 = con.execute(
        "SELECT e.sequence,e.kind,e.title,e.safe_detail FROM chat_run_events e"
        " JOIN chat_messages m ON m.id=e.message_id"
        " WHERE m.skill_name='paper-figure' ORDER BY e.sequence"
    ).fetchall()
    for r in rows2:
        print("  %2d %-8s %-26s %s"
              % (r["sequence"], r["kind"], (r["title"] or "")[:26],
                 (r["safe_detail"] or "")[:60]))

    print("\n=== 工作区 figures/ 现状 ===")
    fig = WS / "figures"
    if fig.is_dir():
        for p in sorted(fig.iterdir()):
            print("  %9d B  %s" % (p.stat().st_size if p.is_file() else -1, p.name))

    mf = fig / "FIGURE_MANIFEST.md"
    if mf.is_file():
        print("\n=== FIGURE_MANIFEST.md（前 40 行）===")
        for i, line in enumerate(mf.read_text(encoding="utf-8",
                                              errors="replace").splitlines()[:40], 1):
            print("  %2d| %s" % (i, line))

    inc = fig / "latex_includes.tex"
    if inc.is_file():
        print("\n=== latex_includes.tex（前 25 行）===")
        for i, line in enumerate(inc.read_text(encoding="utf-8",
                                               errors="replace").splitlines()[:25], 1):
            print("  %2d| %s" % (i, line))

    print("\n=== draw.io 是否在 PATH / 是否存在 ===")
    for p in (r"E:\02_Installers\DailyApps\Modex-MH-Agent\runtime\draw.io\draw.io.exe",):
        print("  %s -> %s" % (p, "存在" if Path(p).is_file() else "不存在"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
