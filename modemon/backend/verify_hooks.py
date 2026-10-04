#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""隔离验证后置钩子：直接调用 `_spawn_post_step_hooks` 并等审计完成。

这是**精准验证**：之前 `comp-code` 有检查点，`execute_step` 提前 return，
钩子从未执行。本脚本绕过 `execute_step` 的路径问题，直接验证钩子本身
能派生任务、能写库。
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

from services import workflow_service as wfs  # noqa: E402

DB = BACKEND / "db" / "modemon.db"
WS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    r"C:\Users\SAKE\AppData\Local\Temp\modemon-full-40zrklrh\ws")
WID = sys.argv[2] if len(sys.argv) > 2 else "verify-hook-wf"


async def main() -> int:
    pushed: list[tuple] = []

    async def push(kind, payload, workflow_id):
        pushed.append((kind, payload))
        print("  [push] %s ok=%s" % (kind, payload.get("ok")))

    print("工作区: %s" % WS)
    print("工作流: %s" % WID)
    print("派生钩子（comp-code → 审计；paper-figure-drawio → 渲染）…")

    wfs._spawn_post_step_hooks(workflow_id=WID, skill_name="comp-code",
                               workspace=WS, push=push)
    wfs._spawn_post_step_hooks(workflow_id=WID, skill_name="paper-figure-drawio",
                               workspace=WS, push=push)

    tasks = list(wfs._AUDIT_TASKS) + list(wfs._FIGURE_TASKS)
    print("派生任务数: %d" % len(tasks))

    t0 = time.monotonic()
    deadline = t0 + 1500          # 最多等 25 分钟
    while time.monotonic() < deadline:
        if all(t.done() for t in tasks):
            break
        await asyncio.sleep(15)
        done = sum(1 for t in tasks if t.done())
        print("  …%d/%d 完成（%.1f 分钟）" % (done, len(tasks),
                                            (time.monotonic() - t0) / 60))

    for t in tasks:
        if t.done() and t.exception():
            print("  任务异常: %r" % t.exception())

    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT kind, state, title, evidence_json FROM chat_run_events"
        " WHERE workflow_id=? AND kind IN ('result_audit','figure_render')",
        (WID,)).fetchall()
    print("\n=== 落库的自定义事件：%d 条 ===" % len(rows))
    for r in rows:
        ev = json.loads(r["evidence_json"] or "{}")
        print("  [%s] state=%s %s" % (r["kind"], r["state"],
                                      (r["title"] or "")[:44]))
        if r["kind"] == "result_audit":
            print("      verdict=%s" % ev.get("verdict"))
            for n in (ev.get("notes") or [])[:3]:
                print("      note :", str(n)[:100])
            for i in (ev.get("issues") or [])[:4]:
                print("      issue:", str(i)[:110])
        else:
            for it in (ev.get("rendered") or [])[:4]:
                print("      -> %s png=%s" % (it.get("spec"), it.get("png")))
    con.close()

    ok = len(rows) >= 1
    print("\n%s" % ("PASS 自定义事件已落库" if ok else "FAIL 没有事件落库"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
