#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only inspection of the live Modex ARIS database (schema + row counts).

Opens with mode=ro URI so the application's database is never modified.
"""
import json
import os
import sqlite3
import sys

DB = r"C:\Users\SAKE\AppData\Roaming\ModexData\library-aJL7Wi\db\aris.db"


def main():
    uri = "file:%s?mode=ro" % DB.replace("\\", "/").replace("?", "%3f").replace("#", "%23")
    con = sqlite3.connect(uri, uri=True)
    cur = con.cursor()
    cur.execute("SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name")
    rows = cur.fetchall()

    out = []
    out.append("# 运行时数据库 aris.db 结构（只读检查）")
    out.append("")
    out.append("路径: `%s`" % DB)
    out.append("大小: %.1f KB" % (os.path.getsize(DB) / 1024.0))
    out.append("")

    tables = [r for r in rows if r[0] == "table"]
    indexes = [r for r in rows if r[0] == "index"]
    out.append("对象统计: table=%d index=%d" % (len(tables), len(indexes)))
    out.append("")
    out.append("## 表与行数")
    out.append("")
    out.append("| 表 | 行数 |")
    out.append("|---|---|")
    counts = {}
    for _t, name, _sql in tables:
        try:
            cur.execute('SELECT COUNT(*) FROM "%s"' % name)
            n = cur.fetchone()[0]
        except Exception as exc:
            n = "ERR:%s" % exc
        counts[name] = n
        out.append("| `%s` | %s |" % (name, n))
    out.append("")

    # columns per table
    out.append("## 各表字段")
    out.append("")
    for _t, name, _sql in tables:
        try:
            cur.execute('PRAGMA table_info("%s")' % name)
            cols = cur.fetchall()
        except Exception:
            continue
        out.append("### `%s`" % name)
        out.append("")
        out.append("| # | 列 | 类型 | 非空 | 默认 |")
        out.append("|---|---|---|---|---|")
        for c in cols:
            out.append("| %s | `%s` | %s | %s | %s |" % (c[0], c[1], c[2], "是" if c[3] else "", c[4] if c[4] is not None else ""))
        out.append("")

    # sample the most informative rows (workflows / steps / settings), truncating long text
    out.append("## 关键表样本数据")
    out.append("")
    for name, limit in (("workflows", 10), ("workflow_steps", 12), ("settings", 40), ("model_presets", 10)):
        if name not in counts or not isinstance(counts[name], int) or counts[name] == 0:
            continue
        try:
            cur.execute('SELECT * FROM "%s" LIMIT %d' % (name, limit))
            data = cur.fetchall()
            hdr = [d[0] for d in cur.description]
        except Exception as exc:
            out.append("- `%s`: %s" % (name, exc))
            continue
        out.append("### `%s` (前 %d 行)" % (name, limit))
        out.append("")
        for row in data:
            pairs = []
            for h, v in zip(hdr, row):
                s = "" if v is None else str(v)
                if len(s) > 220:
                    s = s[:220] + "…"
                pairs.append("%s=%s" % (h, s))
            out.append("- " + " | ".join(pairs))
        out.append("")

    idx = r"E:\02_Installers\DailyApps\Modex-MH-Agent-RE\reports\06-runtime-db.md"
    with open(idx, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print("\n".join(out[:60]))
    print("\n... written ->", idx)


if __name__ == "__main__":
    main()
