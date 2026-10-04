"""人机协同闭环集成测试：WebSocket + 检查点暂停/恢复 + 事件落库与脱敏。

用 Echo 运行时跑完整链路（确定性、不发真实模型请求）：
  建工作流 -> WS 订阅 -> 执行步骤 -> 事件落库并广播 -> 检查点暂停
  -> 人工批准 -> 恢复推进 -> 完成

同时验证**脱敏**：凭据与私有路径绝不入库。
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import main as app_module  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from services import run_events as re_mod  # noqa: E402

PASS = 0
FAIL = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  %s" % name)
    else:
        FAIL += 1
        FAILURES.append(name)
        print("  FAIL  %s  %s" % (name, detail))


def new_client() -> TestClient:
    td = tempfile.mkdtemp(prefix="modemon-collab-")
    app_module.DB_PATH = Path(td) / "modemon.db"
    app_module.init_db()
    return TestClient(app_module.app)


def new_ws() -> Path:
    return Path(tempfile.mkdtemp(prefix="modemon-ws-"))


def mk_workflow(c: TestClient, *, checkpoints: bool = True) -> str:
    r = c.post("/api/workflows", json={
        "template": "comp_cumcm", "title": "闭环测试",
        "enable_checkpoints": checkpoints,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def emit_for(skill: str) -> dict:
    """按步骤给出能满足质量门的产物。"""
    return {
        "comp-prob-analysis": {"PROBLEM_ANALYSIS.md": "分" * 1600},
        "comp-modeling": {"MODELING_REPORT.md": "模" * 2100},
        "comp-code": {
            "RESULTS.md": "r" * 1100,
            "code/main.py": "print('x')\n" * 20,
            "figures/all_results.json": '{"v": 1}\n' * 6,
        },
    }.get(skill, {})


def _qs(d: dict) -> str:
    from urllib.parse import urlencode
    return urlencode(d)


def _poll_step_done(c: TestClient, wf_id: str, skill: str, timeout: float = 30.0) -> dict:
    """轮询直到步骤离开 running（后台任务完成后状态会变）。"""
    import time as _t
    deadline = _t.monotonic() + timeout
    last = None
    while _t.monotonic() < deadline:
        w = c.get(f"/api/workflows/{wf_id}").json()
        st = next((s for s in w["steps"] if s["skill_name"] == skill), None)
        last = st
        if st and st["status"] != "running":
            return {"workflow": w, "step": st}
        _t.sleep(0.15)
    raise TimeoutError(f"步骤 {skill} 超时未完成，最后状态: {last}")


def _poll_batch_idle(c: TestClient, wf_id: str, timeout: float = 60.0) -> dict:
    """轮询直到没有任务在跑（/api/runs 为空）。"""
    import time as _t
    deadline = _t.monotonic() + timeout
    while _t.monotonic() < deadline:
        runs = c.get("/api/runs").json()["active"]
        if wf_id not in runs:
            return c.get(f"/api/workflows/{wf_id}").json()
        _t.sleep(0.15)
    raise TimeoutError("批量执行超时")


class _EchoPatch:
    """在后台任务存活期间保持 EchoRuntime.run 打补丁。

    注意：不能"POST 之后立刻还原补丁"——步骤已被后台化，
    还原发生在任务完成之前会导致真实调用。
    """

    def __init__(self, emit_for_skill):
        self.emit_for_skill = emit_for_skill
        self._orig = None

    def __enter__(self):
        from services import agent_runtime as ar
        self._orig = ar.EchoRuntime.run

        async def patched(runtime_self, spec):
            skill = "comp-code"
            for s in ("comp-prob-analysis", "comp-modeling", "comp-code",
                      "comp-review", "comp-paper-zh"):
                if s in spec.prompt:
                    skill = s
                    break
            spec.env.update({"ECHO_EMIT": json.dumps(self.emit_for_skill(skill),
                                                     ensure_ascii=False)})
            async for e in self._orig(runtime_self, spec):
                yield e

        ar.EchoRuntime.run = patched
        return self

    def __exit__(self, *exc):
        from services import agent_runtime as ar
        ar.EchoRuntime.run = self._orig
        return False


def run_step_background(c: TestClient, wf_id: str, skill: str, ws_dir: Path) -> dict:
    """POST 单步执行（202），轮询至完成，返回步骤视图。"""
    r = c.post(f"/api/workflows/{wf_id}/steps/{skill}/run?"
               + _qs({"workspace": str(ws_dir), "runtime": "echo",
                      "max_budget_usd": "0.1"}))
    assert r.status_code == 202, r.text
    return _poll_step_done(c, wf_id, skill)


# ---------------------------------------------------------------------------


def test_websocket_hello_and_snapshot() -> None:
    print("\n[1] WebSocket 连接与状态快照")
    c = new_client()
    wf_id = mk_workflow(c)

    with c.websocket_connect(f"/ws/{wf_id}") as ws:
        msg = json.loads(ws.receive_text())
        check("连接后收到 hello", msg["type"] == "hello", str(msg)[:120])
        check("hello 带工作流快照", msg.get("workflow", {}).get("id") == wf_id)
        check("快照含 8 个步骤", len(msg.get("steps", [])) == 8, str(len(msg.get("steps", []))))
        check("快照含待处理检查点字段", "pending_checkpoint" in msg)
        check("初始无待处理检查点", msg["pending_checkpoint"] is None)

        ws.send_text("ping")
        check("ping -> pong（纯文本心跳）", ws.receive_text() == "pong")

    with c.websocket_connect("/ws/deadbeef") as ws:
        msg = json.loads(ws.receive_text())
        check("不存在的工作流 -> hello 带 error",
              msg.get("error") == "workflow_not_found", str(msg)[:120])


def test_checkpoint_pause_and_resume() -> None:
    print("\n[2] 检查点暂停 → 人工批准 → 恢复推进")
    c = new_client()
    wf_id = mk_workflow(c, checkpoints=True)
    ws_dir = new_ws()

    seen: list[dict] = []
    with c.websocket_connect(f"/ws/{wf_id}") as ws:
        json.loads(ws.receive_text())  # hello

        with _EchoPatch(emit_for):
            r = c.post(f"/api/workflows/{wf_id}/steps/comp-prob-analysis/run?"
                       + _qs({"workspace": str(ws_dir), "runtime": "echo",
                              "max_budget_usd": "0.1"}))
            check("POST 单步执行 = 202（后台化）", r.status_code == 202, r.text[:200])
            check("202 返回 run_id", bool(r.json().get("run_id")), r.text[:200])
            res = _poll_step_done(c, wf_id, "comp-prob-analysis")

        step = res["step"]
        check("步骤状态 = waiting_checkpoint", step["status"] == "waiting_checkpoint", str(step))
        check("工作流状态 = paused", res["workflow"]["status"] == "paused",
              res["workflow"]["status"])

        # 收集 WS 期间推来的消息
        import time as _t
        deadline = _t.monotonic() + 6
        while _t.monotonic() < deadline and len(seen) < 12:
            try:
                ws.receive_text()
            except Exception:
                break
            break

    # 用 REST 回放验证事件确实落库（不依赖 WS）
    ev = c.get(f"/api/workflows/{wf_id}/run-events").json()
    check("事件已落库（WS 之外仍有权威来源）", ev["count"] > 0, str(ev["count"]))
    check("落库事件含 progress", any(e["kind"] == "progress" for e in ev["events"]))

    cp = c.get(f"/api/workflows/{wf_id}/checkpoints/current").json()
    check("current 返回检查点", cp is not None and cp["status"] == "pending", str(cp))
    check("**含 remaining_seconds（契约字段）**",
          cp is not None and cp["remaining_seconds"] is not None, str(cp))

    r = c.post(f"/api/workflows/{wf_id}/checkpoints/resolve",
               json={"action": "approve", "data": {"note": "ok"}})
    check("resolve = 200", r.status_code == 200, r.text[:200])
    check("**回包 status = resolved**", r.json()["status"] == "resolved", str(r.json()))

    w2 = c.get(f"/api/workflows/{wf_id}").json()
    st2 = {s["skill_name"]: s["status"] for s in w2["steps"]}
    check("批准后步骤 = completed", st2["comp-prob-analysis"] == "completed", str(st2))
    check("批准后工作流恢复 running", w2["status"] == "running", w2["status"])

    cp2 = c.get(f"/api/workflows/{wf_id}/checkpoints/current").json()
    check("检查点已清空", cp2 is None)

    r = c.post(f"/api/workflows/{wf_id}/checkpoints/resolve", json={"action": "approve"})
    check("再次 resolve -> 404", r.status_code == 404)


def test_checkpoint_stop_keeps_paused() -> None:
    print("\n[3] 检查点选择「停在此处」应保持暂停")
    c = new_client()
    wf_id = mk_workflow(c, checkpoints=True)
    ws_dir = new_ws()
    with _EchoPatch(emit_for):
        run_step_background(c, wf_id, "comp-prob-analysis", ws_dir)

    r = c.post(f"/api/workflows/{wf_id}/checkpoints/resolve", json={"action": "stop"})
    check("stop 动作接受", r.status_code == 200, r.text[:200])
    w = c.get(f"/api/workflows/{wf_id}").json()
    check("stop 后步骤完成但工作流仍 paused",
          w["status"] == "paused"
          and next(s for s in w["steps"] if s["skill_name"] == "comp-prob-analysis")["status"] == "completed",
          str(w["status"]))


def test_no_checkpoint_mode_runs_through() -> None:
    print("\n[4] 关闭检查点：连续执行（后台化）")
    c = new_client()
    wf_id = mk_workflow(c, checkpoints=False)
    ws_dir = new_ws()

    with _EchoPatch(emit_for):
        r = c.post(f"/api/workflows/{wf_id}/run?"
                   + _qs({"workspace": str(ws_dir), "runtime": "echo",
                          "max_steps": "3", "max_budget_usd": "0.1"}))
        check("批量执行 = 202（后台化）", r.status_code == 202, r.text[:200])
        w = _poll_batch_idle(c, wf_id)

    done = [s for s in w["steps"] if s["status"] == "completed"]
    check("3 个步骤已完成", len(done) == 3, str(len(done)))
    check("工作流仍在 running（还有后续步骤）", w["status"] == "running", w["status"])
    check("无检查点阻塞",
          c.get(f"/api/workflows/{wf_id}/checkpoints/current").json() is None)

    runs = c.get("/api/runs").json()["active"]
    check("后台任务已清空", wf_id not in runs, str(runs))


def test_orphan_repair() -> None:
    print("\n[4b] 僵尸状态修复（对应蓝方心跳自愈）")
    c = new_client()
    wf_id = mk_workflow(c, checkpoints=False)

    # 人为制造僵尸：库里 running，但没有后台任务
    con = app_module.get_db()
    try:
        con.execute("UPDATE workflows SET status='running' WHERE id=?", (wf_id,))
        con.execute("UPDATE workflow_steps SET status='running' WHERE workflow_id=?"
                    " AND skill_name='comp-prob-analysis'", (wf_id,))
        con.commit()
    finally:
        con.close()

    r = c.post(f"/api/workflows/{wf_id}/repair")
    check("repair = 200", r.status_code == 200, r.text[:200])
    body = r.json()
    check("报告修复项", body["count"] >= 2, str(body))

    w = c.get(f"/api/workflows/{wf_id}").json()
    check("工作流被标记为 failed（不猜测已完成）", w["status"] == "failed", w["status"])
    st = next(s for s in w["steps"] if s["skill_name"] == "comp-prob-analysis")
    check("僵尸步骤标记为 failed", st["status"] == "failed", st["status"])
    check("写明原因", "中断" in (st["error_message"] or ""), str(st["error_message"]))


def test_run_events_persistence_and_replay() -> None:
    print("\n[5] 运行事件落库与回放")
    c = new_client()
    wf_id = mk_workflow(c, checkpoints=True)
    ws_dir = new_ws()
    with _EchoPatch(emit_for):
        run_step_background(c, wf_id, "comp-prob-analysis", ws_dir)

    r = c.get(f"/api/workflows/{wf_id}/run-events")
    check("run-events = 200", r.status_code == 200, r.text[:200])
    body = r.json()
    check("返回事件列表", body["count"] > 0, str(body["count"]))
    kinds = {e["kind"] for e in body["events"]}
    check("含 progress 事件", "progress" in kinds, str(kinds))
    check("**不含 log 事件（原始日志不落库）**", "log" not in kinds, str(kinds))
    check("事件按 sequence 有序",
          [e["sequence"] for e in body["events"]] == sorted(e["sequence"] for e in body["events"]))
    check("含 run_id 便于溯源", all(e.get("run_id") for e in body["events"]))

    arts = [e.get("public_artifact_path") for e in body["events"] if e.get("public_artifact_path")]
    check("记录了公开产物路径", any(a and "PROBLEM_ANALYSIS" in a for a in arts), str(arts))


def test_redaction() -> None:
    print("\n[6] 脱敏：凭据与私有路径绝不入库")
    ws = Path(r"C:\Users\someone\private-workspace")

    s1 = re_mod.redact("Using key sk-abcdef1234567890XYZ to call the API", ws)
    check("凭据被抹除", "sk-abcdef" not in s1 and "«redacted»" in s1, s1)

    s2 = re_mod.redact("read C:\\Users\\someone\\private-workspace\\a\\b\\c.md", ws)
    check("工作区内绝对路径 -> 相对路径", "a/b/c.md" in s2 and "someone" not in s2, s2)

    s3 = re_mod.redact("read C:\\Windows\\System32\\config\\SAM", ws)
    check("工作区外路径 -> 仅保留文件名", "«path:SAM»" in s3, s3)

    s4 = re_mod.redact("Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig", ws)
    check("Bearer 令牌被抹除", "eyJhbGci" not in s4, s4)

    s5 = re_mod.redact("token " + "a" * 40, ws)
    check("长 hex/字母数字串被抹除", "a" * 40 not in s5, s5)

    # 白名单：工具输入不落库
    ev = {
        "input": "SECRET PROMPT",
        "command": "curl -H 'Authorization: Bearer xxx'",
        "thinking": "model internal reasoning",
        "api_key": "sk-whatever",
        "tool_name": "Write",
        "bytes": 1234,
        "phase": "compiling",
    }
    clean = re_mod.sanitize_evidence(ev, ws)
    for bad in ("input", "command", "thinking", "api_key"):
        check("字段 %s 不入库" % bad, bad not in clean, str(clean))
    check("允许的字段保留", clean.get("tool_name") == "Write" and clean.get("bytes") == 1234,
          str(clean))


def test_map_event_filters() -> None:
    print("\n[7] 事件映射：日志与思考不落库")
    from services import agent_runtime as ar

    log_ev = ar.RunEvent(ar.EventKind.LOG, text="raw log line")
    check("LOG 事件不生成记录", re_mod.map_event(log_ev, run_id="r", sequence=0) is None)

    hb_ev = ar.RunEvent(ar.EventKind.HEARTBEAT, text="hb")
    check("HEARTBEAT 不生成记录", re_mod.map_event(hb_ev, run_id="r", sequence=1) is None)

    r_ev = ar.RunEvent(ar.EventKind.RESULT, text="done",
                       data={"session_id": "s", "cost_usd": 0.01, "prompt": "SECRET",
                             "tokens_in": 100, "tokens_out": 20})
    rec = re_mod.map_event(r_ev, run_id="r", sequence=2, workspace=Path("C:/ws"))
    check("RESULT 生成记录", rec is not None and rec.state == "completed")
    check("RESULT 的敏感字段被剔除",
          "prompt" not in rec.evidence, str(rec.evidence))
    check("度量字段保留（cost/tokens）",
          rec.evidence.get("cost_usd") == 0.01
          and rec.evidence.get("tokens_in") == 100
          and rec.evidence.get("tokens_out") == 20, str(rec.evidence))
    check("**session_id 不入事件表**（属 chat_sessions 专用列）",
          "session_id" not in rec.evidence, str(rec.evidence))

    e_ev = ar.RunEvent(ar.EventKind.ERROR, text="boom", data={"code": "TIMEOUT"})
    rec2 = re_mod.map_event(e_ev, run_id="r", sequence=3)
    check("ERROR 映射为 failed", rec2.state == "failed" and rec2.evidence.get("code") == "TIMEOUT")


def test_runtimes_endpoint() -> None:
    print("\n[8] 运行时能力对前端可见")
    c = new_client()
    r = c.get("/api/runtimes")
    check("/api/runtimes = 200", r.status_code == 200)
    body = r.json()
    names = [x["runtime"] for x in body["runtimes"]]
    check("列出 claude-code", "claude-code" in names, str(names))
    check("列出 deepseek-harness", "deepseek-harness" in names, str(names))
    cc = next(x for x in body["runtimes"] if x["runtime"] == "claude-code")
    check("**能力如实暴露给前端**",
          cc["capabilities"]["mcp_pinning"] is True
          and cc["capabilities"]["permission_modes"], str(cc["capabilities"]))
    dsh = next(x for x in body["runtimes"] if x["runtime"] == "deepseek-harness")
    check("DSH 的能力缺失也如实暴露",
          dsh["capabilities"]["mcp_pinning"] is False, str(dsh["capabilities"]))


def test_frontend_served() -> None:
    print("\n[9] 前端由后端同源托管")
    c = new_client()
    r = c.get("/")
    if r.status_code == 404:
        check("前端目录缺失 -> 跳过（仅当 frontend/ 存在时托管）", True)
        return
    check("/ = 200", r.status_code == 200)
    check("返回 HTML", "<!doctype html" in r.text.lower())
    r2 = c.get("/static/app.js")
    check("/static/app.js = 200", r2.status_code == 200, str(r2.status_code))
    check("app.js 含 WS 连接逻辑", "WebSocket" in r2.text)
    check("app.js 体现「WS 只通知」原则",
          "WS 只" in r2.text or "只用于实时通知" in r2.text or "状态一律以 REST" in r2.text,
          "未找到注释")


def main() -> int:
    print("=" * 74)
    print("modemon 人机协同闭环集成测试")
    print("=" * 74)
    test_websocket_hello_and_snapshot()
    test_checkpoint_pause_and_resume()
    test_checkpoint_stop_keeps_paused()
    test_no_checkpoint_mode_runs_through()
    test_orphan_repair()
    test_run_events_persistence_and_replay()
    test_redaction()
    test_map_event_filters()
    test_runtimes_endpoint()
    test_frontend_served()
    print("\n" + "=" * 74)
    print("PASS %d / FAIL %d" % (PASS, FAIL))
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print("  -", f)
    print("=" * 74)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
