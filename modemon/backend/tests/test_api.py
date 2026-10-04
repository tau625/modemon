"""modemon backend 集成测试 —— 真的把应用跑起来。

用 FastAPI TestClient 走完整 HTTP 栈（含 Pydantic 校验、依赖注入、错误处理），
覆盖主线闭环与三道后端硬闸。

每轮使用独立的临时数据库，测试之间互不污染。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import main as app_module  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

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


def new_client() -> tuple[TestClient, Path]:
    td = tempfile.mkdtemp(prefix="modemon-test-")
    root = Path(td)
    app_module.DB_PATH = root / "modemon.db"
    app_module.init_db()
    return TestClient(app_module.app), root


# ---------------------------------------------------------------------------


def test_health_and_templates() -> None:
    print("\n[1] 健康检查与模板")
    c, _ = new_client()
    r = c.get("/api/health")
    check("GET /api/health = 200", r.status_code == 200, str(r.status_code))

    r = c.get("/api/templates")
    check("GET /api/templates = 200", r.status_code == 200)
    tpls = {t["template"]: t for t in r.json()["templates"]}
    check("含 comp_cumcm", "comp_cumcm" in tpls)
    check("comp_cumcm 标记需要 AI 申报", tpls["comp_cumcm"]["requires_ai_disclosure"] is True)
    check("comp_mcm 不需要 AI 申报", tpls["comp_mcm"]["requires_ai_disclosure"] is False)
    check("comp_cumcm 页数参考 = 30", tpls["comp_cumcm"]["page_advisory"] == 30)
    check("comp_huawei 页数参考 = 50", tpls["comp_huawei"]["page_advisory"] == 50)

    r = c.get("/api/templates/comp_cumcm/resolve-steps")
    check("resolve-steps = 200", r.status_code == 200)
    body = r.json()
    steps = body["steps"]
    check("国赛 8 步", len(steps) == 8, str(len(steps)))
    check("第 1 步 = comp-prob-analysis / 赛题分析",
          steps[0]["skill_name"] == "comp-prob-analysis" and steps[0]["display_name"] == "赛题分析")
    check("第 3 步 comp-code 有二级文件约束",
          steps[2]["required_companions"] == ["code/main.py", "figures/all_results.json"])
    check("第 3 步 min_size = 1000", steps[2]["min_size"] == 1000)
    check("第 8 步 min_size = 30000", steps[7]["min_size"] == 30000)
    check("第 8 步 inactivity_timeout = 2700", steps[7]["inactivity_timeout"] == 2700)
    check("page_rule_mode = advisory_max", body["page_rule_mode"] == "advisory_max")

    r = c.get("/api/templates/comp_mcm/resolve-steps")
    check("美赛第 7 步 = comp-paper-en",
          r.json()["steps"][6]["skill_name"] == "comp-paper-en")

    r = c.get("/api/templates/not_a_template/resolve-steps")
    check("未知模板 -> 404", r.status_code == 404, str(r.status_code))
    # 契约：前端必须同时兼容 {detail: str} 与 {detail: {message, code}} 两种形态
    d = r.json().get("detail")
    check("错误体为 {detail: str} 或 {detail: {message, code}}",
          isinstance(d, str) or (isinstance(d, dict) and "message" in d), repr(d))


def test_workflow_crud() -> None:
    print("\n[2] 工作流 CRUD")
    c, _ = new_client()
    r = c.post("/api/workflows", json={"template": "comp_cumcm", "title": "2026 国赛 A 题"})
    check("POST /api/workflows = 201", r.status_code == 201, r.text[:200])
    wf = r.json()
    wf_id = wf["id"]
    check("返回 8 个步骤", len(wf["steps"]) == 8, str(len(wf["steps"])))
    check("状态 = pending", wf["status"] == "pending")
    check("page_advisory 透传 = 30", wf["page_advisory"] == 30)

    r = c.get("/api/workflows")
    check("列表含新建工作流", any(x["id"] == wf_id for x in r.json()))

    r = c.get(f"/api/workflows/{wf_id}")
    check("按 id 查询 OK", r.status_code == 200 and r.json()["id"] == wf_id)

    r = c.get("/api/workflows/deadbeef")
    check("不存在 -> 404 + 结构化错误",
          r.status_code == 404 and r.json()["detail"]["code"] == "WORKFLOW_NOT_FOUND")

    r = c.post("/api/workflows", json={"template": "comp_cumcm"})
    check("缺 title -> 422（Pydantic 校验生效）", r.status_code == 422)

    r = c.post("/api/workflows", json={"template": "bogus", "title": "x"})
    check("非法模板 -> 422", r.status_code == 422)


def test_ai_disclosure_gate() -> None:
    print("\n[3] 国赛 AI 使用申报门禁（后端硬闸）")
    c, _ = new_client()
    wf_id = c.post("/api/workflows", json={"template": "comp_cumcm", "title": "国赛"}).json()["id"]

    r = c.post(f"/api/workflows/{wf_id}/start")
    check("未申报 -> 拒绝启动 409", r.status_code == 409, r.text[:120])
    check("错误码 = AI_DISCLOSURE_REQUIRED",
          r.json()["detail"]["code"] == "AI_DISCLOSURE_REQUIRED")

    rec = {"order": 1, "tool_name": "ChatGPT", "purpose": "文献检索思路",
           "prompt_excerpt": "帮我列出……", "output_used": "仅用于头脑风暴"}
    r = c.put(f"/api/workflows/{wf_id}/ai-disclosure",
              json={"records": [rec], "verified_by_team": False})
    check("保存 1 条记录 = 200", r.status_code == 200, r.text[:150])

    r = c.post(f"/api/workflows/{wf_id}/start")
    check("已申报但未核验 -> 仍拒绝 409", r.status_code == 409)
    check("错误码 = AI_DISCLOSURE_NOT_VERIFIED",
          r.json()["detail"]["code"] == "AI_DISCLOSURE_NOT_VERIFIED")

    r = c.put(f"/api/workflows/{wf_id}/ai-disclosure",
              json={"records": [rec], "verified_by_team": True})
    check("标记已核验 = 200", r.status_code == 200)

    r = c.post(f"/api/workflows/{wf_id}/start")
    check("申报+核验齐备 -> 启动成功", r.status_code == 200, r.text[:150])

    r = c.post(f"/api/workflows/{wf_id}/start")
    check("重复启动 -> 409 ALREADY_RUNNING",
          r.status_code == 409 and r.json()["detail"]["code"] == "ALREADY_RUNNING")

    # 非国赛模板不受此闸约束
    wf2 = c.post("/api/workflows", json={"template": "comp_mcm", "title": "美赛"}).json()["id"]
    r = c.post(f"/api/workflows/{wf2}/start")
    check("美赛不触发 AI 申报闸 -> 可直接启动", r.status_code == 200, r.text[:120])

    # 记录条数校验
    r = c.put(f"/api/workflows/{wf_id}/ai-disclosure",
              json={"records": [rec] * 6, "verified_by_team": True})
    check("6 条记录 -> 422（上限 5）", r.status_code == 422, str(r.status_code))


def test_chat_workbench() -> None:
    print("\n[4] 对话工作台：幂等 / 硬闸 / CAS")
    c, root = new_client()
    wf_id = c.post("/api/workflows", json={"template": "comp_cumcm", "title": "t"}).json()["id"]

    # 幂等 turn_id
    r1 = c.post(f"/api/workflows/{wf_id}/chat/say", json={"text": "开始吧", "turn_id": "turn-1"})
    r2 = c.post(f"/api/workflows/{wf_id}/chat/say", json={"text": "开始吧", "turn_id": "turn-1"})
    check("同一 turn_id 重复提交 -> 去重", r2.json()["deduplicated"] is True)
    check("去重返回同一 message_id", r1.json()["message_id"] == r2.json()["message_id"])

    r3 = c.post(f"/api/workflows/{wf_id}/chat/say", json={"text": "换个说法", "turn_id": "turn-2"})
    check("不同 turn_id -> 不去重", r3.json()["deduplicated"] is False)

    # MCP 回调产生提议
    p = c.post("/api/internal/chat/propose", json={
        "session_id": wf_id, "workflow_id": wf_id, "skill": "comp-modeling",
        "instruction": "建立优化模型", "execution_scope": "full",
    })
    check("POST /api/internal/chat/propose = 201", p.status_code == 201, p.text[:200])
    msg_id = p.json()["message_id"]

    # CAS：revision 不匹配必须拒绝
    r = c.post(f"/api/workflows/{wf_id}/chat/messages/{msg_id}/confirm",
               json={"instruction": "建立优化模型（改）", "revision": 999})
    check("revision 不匹配 -> 409 REVISION_CONFLICT",
          r.status_code == 409 and r.json()["detail"]["code"] == "REVISION_CONFLICT",
          r.text[:160])

    # 正确 revision -> 通过
    r = c.post(f"/api/workflows/{wf_id}/chat/messages/{msg_id}/confirm",
               json={"instruction": "建立优化模型（改）", "revision": 1})
    check("revision 正确 -> 确认成功", r.status_code == 200 and r.json()["status"] == "queued",
          r.text[:160])

    # 二次确认必须被拒（状态已非 proposed）
    r = c.post(f"/api/workflows/{wf_id}/chat/messages/{msg_id}/confirm",
               json={"instruction": "再确认一次", "revision": 1})
    check("重复确认 -> 409 PROPOSAL_NOT_PENDING",
          r.status_code == 409 and r.json()["detail"]["code"] == "PROPOSAL_NOT_PENDING")

    # 不存在
    r = c.post(f"/api/workflows/{wf_id}/chat/messages/99999/confirm",
               json={"instruction": "x", "revision": 1})
    check("不存在的提议 -> 404", r.status_code == 404)


def test_conversation_mode_blocks_proposal() -> None:
    print("\n[5] 「仅对话」模式必须挡住执行提议")
    c, _ = new_client()
    wf_id = c.post("/api/workflows", json={"template": "comp_cumcm", "title": "t"}).json()["id"]
    con = app_module.get_db()
    try:
        con.execute(
            "INSERT INTO chat_sessions (id, workflow_id, active_turn_mode, active_focus_target)"
            " VALUES (?,?,?,?)", ("s1", wf_id, "conversation", None))
        con.commit()
    finally:
        con.close()

    r = c.post("/api/internal/chat/propose", json={
        "session_id": "s1", "workflow_id": wf_id, "skill": "comp-modeling", "instruction": "x",
    })
    check("仅对话模式下提议被拒 409",
          r.status_code == 409 and r.json()["detail"]["code"] == "PROPOSE_BLOCKED_BY_TURN_MODE",
          r.text[:160])

    # 聚焦模式下，后端应把 scope 收紧为 focused 并采用库中的 focus_target
    con = app_module.get_db()
    try:
        con.execute("UPDATE chat_sessions SET active_turn_mode='focused', active_focus_target='问题一'"
                    " WHERE id='s1'")
        con.commit()
    finally:
        con.close()
    r = c.post("/api/internal/chat/propose", json={
        "session_id": "s1", "workflow_id": wf_id, "skill": "comp-modeling",
        "instruction": "只做第一问", "execution_scope": "full",
    })
    check("聚焦模式强制 scope=focused（不信任调用方传值）",
          r.status_code == 201 and r.json()["execution_scope"] == "focused", r.text[:160])
    check("聚焦目标取自库中 active_focus_target",
          r.json()["focus_target"] == "问题一", str(r.json()))


def test_checkpoints() -> None:
    print("\n[6] 检查点契约")
    c, _ = new_client()
    wf_id = c.post("/api/workflows", json={"template": "comp_cumcm", "title": "t"}).json()["id"]

    r = c.get(f"/api/workflows/{wf_id}/checkpoints/current")
    check("无检查点 -> null", r.status_code == 200 and r.json() is None)

    con = app_module.get_db()
    try:
        con.execute(
            "INSERT INTO checkpoints (workflow_id, step_name, checkpoint_type, data)"
            " VALUES (?,?,?,?)", (wf_id, "comp-modeling", "feedback", '{"q": "确认模型?"}'))
        con.commit()
    finally:
        con.close()

    r = c.get(f"/api/workflows/{wf_id}/checkpoints/current")
    body = r.json()
    check("有检查点 -> 返回", r.status_code == 200 and body is not None)
    check("**含 remaining_seconds（前端据此判后端版本）**",
          "remaining_seconds" in body and body["remaining_seconds"] is not None, str(body))
    check("remaining_seconds 基于该步超时(5400)",
          body["remaining_seconds"] <= 5400, str(body["remaining_seconds"]))

    r = c.post(f"/api/workflows/{wf_id}/checkpoints/resolve", json={"action": "approve"})
    check("resolve = 200", r.status_code == 200, r.text[:160])
    check("**回包 status = resolved（契约字段）**", r.json()["status"] == "resolved", str(r.json()))

    r = c.get(f"/api/workflows/{wf_id}/checkpoints/current")
    check("已解决后 current -> null", r.json() is None)

    r = c.post(f"/api/workflows/{wf_id}/checkpoints/resolve", json={"action": "approve"})
    check("无待处理检查点 -> 404", r.status_code == 404)

    r = c.post(f"/api/workflows/{wf_id}/checkpoints/resolve", json={"action": "bogus"})
    check("非法 action -> 422（Literal 校验）", r.status_code == 422)


def test_settings_and_presets() -> None:
    print("\n[7] 设置与模型预设（密钥不外泄）")
    c, _ = new_client()

    r = c.put("/api/settings", json={"settings": {"theme": "dark", "data_dir": "D:/mh"}})
    check("PUT /api/settings = 200", r.status_code == 200)
    r = c.get("/api/settings")
    check("设置可读回", r.json()["settings"]["theme"] == "dark")

    r = c.post("/api/settings/presets", json={
        "name": "主模型", "model_id": "deepseek-chat", "api_key": "sk-secret-value",
        "context_mode": "200k",
    })
    check("创建预设 = 201", r.status_code == 201, r.text[:150])
    body = r.json()
    check("**响应不含 api_key**", "api_key" not in body, str(body))
    check("仅回传 has_api_key", body["has_api_key"] is True)
    check("context_mode 透传", body["context_mode"] == "200k")

    r = c.get("/api/settings/presets")
    check("**列表中也不含密钥**",
          all("api_key" not in p for p in r.json()), str(r.json()))

    r = c.post("/api/settings/presets", json={
        "name": "x", "model_id": "m", "context_mode": "512k"})
    check("非法 context_mode -> 422", r.status_code == 422)


def test_workspace_health() -> None:
    print("\n[8] 工作区质量门（结构化结果）")
    c, root = new_client()
    wf_id = c.post("/api/workflows", json={"template": "comp_cumcm", "title": "t"}).json()["id"]
    con = app_module.get_db()
    try:
        con.execute("UPDATE workflow_steps SET status='running' WHERE workflow_id=?"
                    " AND skill_name='comp-code'", (wf_id,))
        con.commit()
    finally:
        con.close()

    ws = root / "ws"
    (ws / "code").mkdir(parents=True)
    (ws / "figures").mkdir(parents=True)
    (ws / "code" / "main.py").write_text("print(1)\n" * 20, encoding="utf-8")
    (ws / "RESULTS.md").write_text("r" * 1500, encoding="utf-8")
    (ws / "figures" / "all_results.json").write_text("{}", encoding="utf-8")  # 空占位

    r = c.get(f"/api/workflows/{wf_id}/workspace/health", params={"workspace": str(ws)})
    check("health = 200", r.status_code == 200, r.text[:160])
    st = r.json()["steps"][0]
    check("主产物达标", st["primary_output_ok"] is True, str(st))
    check("二级文件空占位被识别", st["companions_ok"] is False, str(st))
    check("给出缺失原因", any("空文件占位" in m for m in st["missing_companions"]), str(st))
    check("含 unavailable 字段（区分检查器不可用）", "unavailable" in st)

    (ws / "figures" / "all_results.json").write_text('{"ok": true, "n": 42}\n' * 5, encoding="utf-8")
    r = c.get(f"/api/workflows/{wf_id}/workspace/health", params={"workspace": str(ws)})
    check("补齐后二级文件通过", r.json()["steps"][0]["companions_ok"] is True)


def main() -> int:
    print("=" * 74)
    print("modemon backend 集成测试（真跑 HTTP 栈）")
    print("=" * 74)
    test_health_and_templates()
    test_workflow_crud()
    test_ai_disclosure_gate()
    test_chat_workbench()
    test_conversation_mode_blocks_proposal()
    test_checkpoints()
    test_settings_and_presets()
    test_workspace_health()
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
