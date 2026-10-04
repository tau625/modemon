#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清理僵尸工作流（供流水线前重置）。"""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent / "db" / "modemon.db"
con = sqlite3.connect(str(DB))
n = con.execute("UPDATE workflows SET status='failed' WHERE status IN ('running','paused')").rowcount
con.commit()
print("已清理僵尸工作流: %d" % n)
for st in ("running", "paused", "failed", "completed", "pending"):
    c = con.execute("SELECT COUNT(*) FROM workflows WHERE status=?", (st,)).fetchone()[0]
    if c:
        print("  %-11s %d" % (st, c))
con.close()
