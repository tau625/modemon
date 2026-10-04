#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出结果全量落盘，便于审查。"""
import json
import sys
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
B = "http://127.0.0.1:8770"
OUT = BACKEND.parent.parent / "reports" / "_export-probe.json"


def find_ws() -> Path:
    base = Path.home() / "AppData" / "Local" / "Temp"
    ok = [d / "ws" for d in base.glob("modemon-full-*")
          if (d / "ws" / "figures" / "all_results.json").is_file()]
    ok.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return ok[0]


def main() -> int:
    ws = find_ws()
    print("工作区: %s" % ws)
    body = {"workspace": str(ws), "template": "comp_cumcm",
            "title": "测试导出", "formats": ["latex", "docx"], "compile_pdf": True}
    req = urllib.request.Request(
        B + "/api/paper/export", data=json.dumps(body).encode(),
        method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        d = json.loads(r.read().decode())

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")

    res = d.get("results", {})
    for fmt, info in res.items():
        print("\n--- %s ---" % fmt)
        for k, v in info.items():
            if k in ("log_tail", "tables"):
                continue
            print("  %-16s %s" % (k, str(v)[:120]))
        tail = (info.get("log_tail") or "")
        warns = [ln for ln in tail.splitlines()
                 if "Warning" in ln or "Error" in ln or "Overfull" in ln]
        print("  日志告警 %d 条：" % len(warns))
        for w in warns[:8]:
            print("     ", w[:110])

    print("\n--- 图表/表格 ---")
    print("  tables:", len(d.get("tables") or []))
    print("  figures:", len(d.get("figures") or []))
    print("  notes:", json.dumps(d.get("notes"), ensure_ascii=False)[:400])
    print("\n完整结果 -> %s" % OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
