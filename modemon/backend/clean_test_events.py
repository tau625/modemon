#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清理自测事件。"""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent / "db" / "modemon.db"
con = sqlite3.connect(str(DB))
n = con.execute("DELETE FROM chat_run_events WHERE title IN ('自测审计','自测')").rowcount
con.commit()
print("已清理自测事件: %d" % n)
con.close()
