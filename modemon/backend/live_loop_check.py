#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真实闭环验证：Claude Code + WebSocket + 检查点暂停/恢复。

流程：
  1. 建工作流（启用检查点）
  2. 连 WebSocket 订阅
  3. 用真实 Claude Code 跑第 1 步（comp-prob-analysis）
  4. 观察 WS 实时事件流
  5. 步骤完成后应停在检查点（waiting_checkpoint / paused）
  6. 人工 approve
  7. 验证恢复并推进

用法：python live_loop_check.py [--budget 0.40]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

import urllib.request

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

import websockets  # noqa: E402

BASE = "http://127.0.0.1:8770"
WS = "ws://127.0.0.1:8770"
OUT = Path(r"E:\02_Installers\DailyApps\Modex-MH-Agent-RE\reports\20-live-loop.md")


def http(method: str, path: str, body: dict | None = None, timeout: float = 30) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def wait_step_done(wf_id: str, skill: str, timeout: float = 420) -> dict:
    """轮询直到步骤离开 running。

    执行已**后台化**，所以这里要轮询而不是等长连接——
    这也正是修复"客户端断开导致僵尸 running"的方式。
    """
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        w = http("GET", f"/api/workflows/{wf_id}")
        st = next((s for s in w["steps"] if s["skill_name"] == skill), None)
        last = st
        if st and st["status"] != "running":
            return w
        time.sleep(1.0)
    raise TimeoutError(f"{skill} 超时，最后状态 {last}")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=0.40)
    args = ap.parse_args()

    print("=" * 74)
    print("真实闭环：Claude Code + WebSocket + 检查点")
    print("=" * 74)

    # 1) 建工作流
    wf = http("POST", "/api/workflows", {
        "template": "comp_cumcm", "title": "闭环验证",
        "enable_checkpoints": True,
    })
    wf_id = wf["id"]
    print("工作流:", wf_id, "步骤数:", len(wf["steps"]))

    # 2) 工作区：放一份赛题原文，让第 1 步有东西可分析
    ws_dir = Path(tempfile.mkdtemp(prefix="modemon-live-")) / "ws"
    ws_dir.mkdir(parents=True)
    (ws_dir / "user_data").mkdir()
    (ws_dir / "user_data" / "problem.txt").write_text(
        "某物流公司有 3 个仓库与 4 个配送点，单位运价矩阵给出，"
        "求最小运输成本的调运方案。请建立数学模型并说明假设。\n",
        encoding="utf-8",
    )
    print("工作区:", ws_dir)

    events: list[dict] = []
    checkpoint_seen = asyncio.Event()

    # 3) 连 WS
    async with websockets.connect(f"{WS}/ws/{wf_id}") as sock:
        hello = json.loads(await sock.recv())
        print("WS hello:", hello["type"], "步骤:", len(hello.get("steps", [])))
        print()

        async def pump() -> None:
            try:
                async for raw in sock:
                    if raw == "pong":
                        continue
                    m = json.loads(raw)
                    events.append(m)
                    t = m.get("type")
                    if t == "run_event":
                        e = m["event"]
                        print(f"  [ws run_event] {e['kind']:9} {e['title'][:50]}"
                              + (f" | {e.get('safe_detail','')[:50]}" if e.get("safe_detail") else ""))
                    elif t == "step_started":
                        print(f"  [ws] step_started      {m['skill_name']}")
                    elif t == "checkpoint_created":
                        print(f"  [ws] checkpoint_created {m['skill_name']} ({m['checkpoint_type']})")
                        checkpoint_seen.set()
                    elif t == "step_completed":
                        print(f"  [ws] step_completed    {m['skill_name']}")
                    elif t == "step_failed":
                        print(f"  [ws] step_failed       {m['skill_name']} {m.get('error','')[:60]}")
                    elif t == "heartbeat":
                        pass
                    else:
                        print(f"  [ws] {t}")
            except Exception as exc:
                print("  [ws] pump 结束:", type(exc).__name__)

        pump_task = asyncio.create_task(pump())

        # 4) 执行第 1 步（真实 Claude Code）—— 后台化，立即返回 202
        print("执行 comp-prob-analysis（真实 Claude Code，预算 %.2f USD）…" % args.budget)
        t0 = time.monotonic()
        q = (f"?workspace={urllib.parse.quote(str(ws_dir))}"
             f"&max_budget_usd={args.budget}")
        accepted = await asyncio.to_thread(
            http, "POST", f"/api/workflows/{wf_id}/steps/comp-prob-analysis/run{q}",
            None, 30)
        print("  POST -> 202, run_id=%s" % accepted.get("run_id", "")[:12])

        wfinal = await asyncio.to_thread(wait_step_done, wf_id, "comp-prob-analysis", 420)
        dt = time.monotonic() - t0
        step = next(s for s in wfinal["steps"] if s["skill_name"] == "comp-prob-analysis")
        rep = {
            "ok": step["status"] == "waiting_checkpoint",
            "status": step["status"],
            "error_code": step.get("error_message") or "",
            "gates": [],
        }
        print()
        print("-" * 74)
        print("步骤结果 (%.1fs)" % dt)
        print("-" * 74)
        print("  status            :", step["status"])
        print("  model_used        :", step.get("model_used"))
        print("  error_message     :", (step.get("error_message") or "")[:80])

        # 等 WS 把事件推完
        await asyncio.sleep(1.5)
        pump_task.cancel()

    # 5) 验证暂停状态
    print()
    w = http("GET", f"/api/workflows/{wf_id}")
    st = {s["skill_name"]: s["status"] for s in w["steps"]}
    print("工作流状态:", w["status"])
    print("第 1 步状态:", st.get("comp-prob-analysis"))
    cp = http("GET", f"/api/workflows/{wf_id}/checkpoints/current")
    print("待处理检查点:", json.dumps(cp, ensure_ascii=False) if cp else None)

    # 6) 批准
    resumed = None
    if cp:
        print()
        print("人工批准检查点…")
        r = http("POST", f"/api/workflows/{wf_id}/checkpoints/resolve",
                 {"action": "approve", "checkpoint_id": cp["checkpoint_id"],
                  "data": {"note": "人工确认赛题分析合格"}})
        print("resolve:", json.dumps(r, ensure_ascii=False))
        w2 = http("GET", f"/api/workflows/{wf_id}")
        st2 = {s["skill_name"]: s["status"] for s in w2["steps"]}
        print("批准后工作流状态:", w2["status"])
        print("批准后第 1 步状态:", st2.get("comp-prob-analysis"))
        resumed = (w2["status"], st2.get("comp-prob-analysis"))

    # 7) 事件回放（验证 WS 之外还有权威来源）
    ev = http("GET", f"/api/workflows/{wf_id}/run-events")
    print()
    print("事件回放: %d 条（kind 分布 %s）"
          % (ev["count"], json.dumps(_kinds(ev["events"]), ensure_ascii=False)))

    produced = ws_dir / "PROBLEM_ANALYSIS.md"
    size = produced.stat().st_size if produced.exists() else 0
    print("产物 PROBLEM_ANALYSIS.md:", produced.exists(), ("(%d 字节)" % size) if size else "")

    # 写报告
    lines = [
        "# 真实闭环验证：Claude Code + WebSocket + 检查点",
        "",
        "> 由 `live_loop_check.py` 生成。使用本机已配置的 Claude Code 端点。",
        "> **不记录任何凭据信息。**",
        "",
        "## 流程与结果",
        "",
        "| 环节 | 结果 |",
        "|---|---|",
        f"| 建工作流（启用检查点） | `{wf_id}`，{len(wf['steps'])} 步 |",
        f"| WS 连接 | ✅ 收到 `hello`，含 {len(hello.get('steps', []))} 步快照 |",
        f"| 执行 `comp-prob-analysis` | POST 返回 **202**（后台化），轮询至 `{step['status']}` |",
        f"| 步骤耗时 | {dt:.1f}s |",
        f"| 模型快照 | `{step.get('model_used') or '—'}` |",
        f"| **检查点暂停** | `{st.get('comp-prob-analysis')}`（工作流 `{w['status']}`） |",
        f"| 检查点 `remaining_seconds` | {cp.get('remaining_seconds') if cp else '—'} |",
        f"| **人工批准后** | 工作流 `{resumed[0] if resumed else '—'}`，步骤 `{resumed[1] if resumed else '—'}` |",
        f"| 事件回放条数 | {ev['count']} |",
        f"| 产物 | `PROBLEM_ANALYSIS.md` " + (f"（{size} 字节）" if size else "**未生成**"),
        "",
        "> **架构要点**：执行是**后台任务**，HTTP 只负责受理（202）。",
        "> 实测教训：若在请求里同步 await 长步骤，客户端中途断开会让协程被取消，",
        "> 步骤永久停在 `running` 变成僵尸。后台化 + 可查询的 run 状态解决了这一点，",
        "> 并配套 `POST /api/workflows/{id}/repair` 做僵尸自愈（对应蓝方的心跳修复）。",
        "",
        "## WebSocket 收到的消息类型",
        "",
        "```json",
        json.dumps(_types(events), ensure_ascii=False, indent=1),
        "```",
        "",
        "## 落库事件（脱敏后，供前端回放）",
        "",
        "| # | kind | state | title | safe_detail | artifact |",
        "|---|---|---|---|---|---|",
    ]
    for i, e in enumerate(ev["events"], 1):
        lines.append("| %d | `%s` | %s | %s | %s | %s |" % (
            i, e["kind"], e["state"], e["title"][:40].replace("|", "\\|"),
            (e["safe_detail"] or "")[:60].replace("|", "\\|"),
            e.get("public_artifact_path") or ""))
    lines += [
        "",
        "## 产物内容（前 1500 字）",
        "",
        "```markdown",
        produced.read_text(encoding="utf-8")[:1500] if produced.exists() else "(未生成)",
        "```",
        "",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print()
    print("报告已写入:", OUT)

    ok = bool(rep.get("ok")) and cp is not None and resumed and resumed[0] == "running"
    return 0 if ok else 1


def _kinds(events: list[dict]) -> dict:
    out: dict[str, int] = {}
    for e in events:
        out[e["kind"]] = out.get(e["kind"], 0) + 1
    return out


def _types(msgs: list[dict]) -> dict:
    out: dict[str, int] = {}
    for m in msgs:
        out[m.get("type", "?")] = out.get(m.get("type", "?"), 0) + 1
    return out


if __name__ == "__main__":
    import urllib.parse  # noqa: E402

    raise SystemExit(asyncio.run(main()))
