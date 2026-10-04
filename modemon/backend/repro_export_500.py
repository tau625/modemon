#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复现论文导出的 500 并定位原因。"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

B = "http://127.0.0.1:8770"


def find_ws() -> Path:
    base = Path.home() / "AppData" / "Local" / "Temp"
    cands = [d / "ws" for d in base.glob("modemon-full-*")]
    ok = [p for p in cands if (p / "figures" / "all_results.json").is_file()]
    ok.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return ok[0] if ok else cands[0]


def main() -> int:
    ws = find_ws()
    print("工作区: %s" % ws)
    print("有 all_results.json:", (ws / "figures" / "all_results.json").is_file())

    body = {"workspace": str(ws), "template": "comp_cumcm",
            "title": "测试导出", "formats": ["latex", "docx"], "compile_pdf": True}
    req = urllib.request.Request(
        B + "/api/paper/export", data=json.dumps(body).encode(),
        method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            d = json.loads(r.read().decode())
        print("HTTP 200")
        print(json.dumps({k: v for k, v in d.items() if k != "tables"},
                         ensure_ascii=False, indent=1)[:700])
        return 0
    except urllib.error.HTTPError as e:
        print("HTTP %s" % e.code)
        print("body:", e.read().decode("utf-8", "replace")[:800])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
