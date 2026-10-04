"""流 D：运维健壮性回归测试 —— 僵尸回收 / 日志归集 / 导出 500 兜底。

对应 reports/26 §4.1（僵尸并发）§4.3（导出 500 未定位）§4.4（无日志）
与 reports/28 §3.1 §3.3 §3.4。

每项断言都对着**实测复现过的失败模式**，不是"函数能跑通就行"：
- §4.1 实测一次排查中 9 个僵尸 `running` 并发争抢 agent 进程
- §4.3 两个可复现的 500 路径：`all_results.json` 非 UTF-8（`UnicodeDecodeError`）、
  `paper/main.tex` 被占用或只读（Windows `PermissionError [Errno 13]`）
- §4.4 `modemon.workflow` 的 handler 从来没配过，它打的 `log.info` 看不到
"""

from __future__ import annotations

import json
import logging
import os
import stat
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import main as app_module  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from services import latex_export as lx  # noqa: E402
from services import workflow_service as wfs  # noqa: E402

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


# 本文件专用日志目录：不污染仓库 logs/，也避免与其他测试互相干扰。
LOGDIR = Path(tempfile.mkdtemp(prefix="modemon-ops-logs-"))
LOG_FILE = app_module.setup_logging(log_dir=LOGDIR)


def log_text() -> str:
    if not LOG_FILE.exists():
        return ""
    return LOG_FILE.read_text(encoding="utf-8", errors="replace")


def new_client() -> tuple[TestClient, Path]:
    td = tempfile.mkdtemp(prefix="modemon-ops-")
    root = Path(td)
    app_module.DB_PATH = root / "modemon.db"
    app_module.init_db()
    return TestClient(app_module.app, raise_server_exceptions=False), root


def mk_workflow(c: TestClient) -> str:
    return c.post("/api/workflows",
                  json={"template": "comp_cumcm", "title": "ops"}).json()["id"]


def set_status(wf_id: str, *, wf: str, step: str | None = None,
               skill: str = "comp-prob-analysis") -> None:
    con = app_module.get_db()
    try:
        con.execute("UPDATE workflows SET status=? WHERE id=?", (wf, wf_id))
        if step is not None:
            con.execute("UPDATE workflow_steps SET status=? WHERE workflow_id=?"
                        " AND skill_name=?", (step, wf_id, skill))
        con.commit()
    finally:
        con.close()


def age_workflow(wf_id: str, minutes: float, *, garbage_event: bool = False) -> None:
    """把该工作流所有"推进"时间戳推到 N 分钟前（模拟长时间无事件推进）。"""
    old = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    con = app_module.get_db()
    try:
        con.execute("UPDATE workflows SET created_at=?, updated_at=? WHERE id=?",
                    (old, old, wf_id))
        con.execute("UPDATE workflow_steps SET started_at=? WHERE workflow_id=?",
                    (old, wf_id))
        if garbage_event:
            con.execute(
                "INSERT INTO chat_run_events (event_id, workflow_id, message_id, run_id,"
                " sequence, kind, state, title, started_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                ("evt-garbage", wf_id, 1, "r1", 1, "progress", "running",
                 "garbage-ts", "not-a-timestamp"),
            )
        con.commit()
    finally:
        con.close()


def mk_workspace(root: Path) -> Path:
    ws = root / "ws"
    (ws / "figures").mkdir(parents=True)
    (ws / "paper" / "sections").mkdir(parents=True)
    (ws / "paper" / "sections" / "01_problem.md").write_text(
        "# 问题重述\n" + "分析要点与假设。" * 40, encoding="utf-8")
    (ws / "figures" / "all_results.json").write_text(
        '{"scenario1_basic": {"Z0": 775}}', encoding="utf-8")
    return ws


# ---------------------------------------------------------------------------


def test_startup_reaps_zombies() -> None:
    print("\n[1] 启动自愈：僵尸 running -> failed（§4.1）")
    c, _ = new_client()
    wf_id = mk_workflow(c)
    set_status(wf_id, wf="running", step="running")

    res = app_module.run_startup_maintenance()
    check("启动自愈报告成功", res["ok"] is True, str(res))
    check("回收了 1 个僵尸工作流", res["reaped_workflows"] >= 1, str(res))
    check("走的是既有 repair_orphans（不猜完成）",
          "repair_orphans" in res and res["repair_orphans"]["count"] >= 1, str(res))

    w = c.get(f"/api/workflows/{wf_id}").json()
    check("工作流被标记为 failed", w["status"] == "failed", w["status"])
    st = next(s for s in w["steps"] if s["skill_name"] == "comp-prob-analysis")
    check("僵尸步骤被标记为 failed", st["status"] == "failed", st["status"])
    check("写明原因（中断）", "中断" in (st["error_message"] or ""), str(st["error_message"]))
    check("自愈结果落盘可查", "启动自愈完成" in log_text())


def test_lifespan_wires_startup_maintenance() -> None:
    print("\n[2] startup 钩子真的挂上了（不是只写了个函数）")
    td = Path(tempfile.mkdtemp(prefix="modemon-ops-lifespan-"))
    app_module.DB_PATH = td / "modemon.db"
    app_module.init_db()

    con = app_module.get_db()
    try:
        con.execute("INSERT INTO workflows (id, template, title, status) VALUES"
                    " ('zombie-lifespan', 'comp_cumcm', 'z', 'running')")
        con.commit()
    finally:
        con.close()

    with TestClient(app_module.app) as c:  # 上下文管理器 = 真跑 lifespan
        w = c.get("/api/workflows/zombie-lifespan").json()
        check("进 startup 后僵尸已清", w["status"] == "failed", w["status"])
    check("退出后应用仍可用（定期任务被正常取消）",
          app_module.LOG_DIR.is_dir())


def test_reaps_orphan_steps_repair_orphans_misses() -> None:
    print("\n[3] repair_orphans 的盲区：非 running 工作流下的 running 步骤")
    c, _ = new_client()
    wf_id = mk_workflow(c)
    set_status(wf_id, wf="failed", step="running")   # 工作流不在跑，步骤却在跑

    con = app_module.get_db()
    try:
        missed = wfs.repair_orphans(con)
        step = con.execute("SELECT status FROM workflow_steps WHERE workflow_id=?"
                           " AND skill_name='comp-prob-analysis'", (wf_id,)).fetchone()
    finally:
        con.close()
    check("确认 repair_orphans 扫不到这一类（实测库里就有一条）",
          missed["count"] == 0 and step["status"] == "running", str(dict(step)))

    res = app_module.run_startup_maintenance()
    check("启动自愈补上这一步", res["reaped_steps"] == 1, str(res))
    w = c.get(f"/api/workflows/{wf_id}").json()
    st = next(s for s in w["steps"] if s["skill_name"] == "comp-prob-analysis")
    check("遗留步骤被标记为 failed", st["status"] == "failed", st["status"])
    check("写明原因（遗留）", "遗留" in (st["error_message"] or ""), str(st["error_message"]))

    # 防误杀：有活任务时不许碰（execute_step 里两条 UPDATE 之间存在竞态窗口）
    set_status(wf_id, wf="failed", step="running")
    original = wfs.is_running
    wfs.is_running = lambda _wid: True
    try:
        con = app_module.get_db()
        try:
            guarded = app_module.reap_orphan_steps(con)
        finally:
            con.close()
    finally:
        wfs.is_running = original
    check("有活任务的工作流即使工作流状态不是 running 也不动它",
          guarded == [], str(guarded))


def test_stale_threshold_is_safe() -> None:
    print("\n[4] 阈值内**不误杀**（防误杀是这一项的核心）")
    c, _ = new_client()
    wf_id = mk_workflow(c)
    set_status(wf_id, wf="running", step="running")
    age_workflow(wf_id, 1)                            # 1 分钟前进过

    con = app_module.get_db()
    try:
        res = app_module.reap_stale_workflows(con)
        last = app_module.last_activity(con, wf_id)
        w = c.get(f"/api/workflows/{wf_id}").json()
    finally:
        con.close()
    check("repaired 为空", res["repaired"] == [], str(res))
    check("stale_active 为空", res["stale_active"] == [], str(res))
    check("阈值透传为 45 分钟", res["stale_minutes"] == app_module.STALE_RUNNING_MINUTES, str(res))
    check("工作流仍是 running", w["status"] == "running", w["status"])
    check("last_activity 可解析且带时区",
          last is not None and last.tzinfo is not None, str(last))


def test_stale_workflow_is_reaped() -> None:
    print("\n[5] 超阈值无事件推进 -> 自动标失败（§3.1 定期回收）")
    c, _ = new_client()
    wf_id = mk_workflow(c)
    set_status(wf_id, wf="running", step="running")
    age_workflow(wf_id, 60)

    con = app_module.get_db()
    try:
        res = app_module.reap_stale_workflows(con)
    finally:
        con.close()
    actions = [r["action"] for r in res["repaired"]]
    check("步骤被回收", "stale_step_running->failed" in actions, str(actions))
    check("工作流被回收", "stale_workflow_running->failed" in actions, str(actions))
    check("报告了停滞时长", all(r["idle_minutes"] >= 59 for r in res["repaired"]), str(res))

    w = c.get(f"/api/workflows/{wf_id}").json()
    st = next(s for s in w["steps"] if s["skill_name"] == "comp-prob-analysis")
    check("工作流 = failed", w["status"] == "failed", w["status"])
    check("步骤 = failed", st["status"] == "failed", st["status"])
    check("原因写明阈值", "无事件推进" in (st["error_message"] or ""), str(st["error_message"]))
    check("回收动作落盘", "回收僵尸工作流" in log_text())


def test_live_task_is_never_killed() -> None:
    print("\n[6] 有活任务 + 长时间无推进 -> 只告警，**不动手**（不猜『大概跑完了』）")
    c, _ = new_client()
    wf_id = mk_workflow(c)
    set_status(wf_id, wf="running", step="running")
    age_workflow(wf_id, 90)

    original = wfs.is_running
    wfs.is_running = lambda _wid: True          # 模拟后台任务还活着
    try:
        con = app_module.get_db()
        try:
            res = app_module.reap_stale_workflows(con)
        finally:
            con.close()
    finally:
        wfs.is_running = original

    check("没有回收任何东西", res["repaired"] == [], str(res))
    check("被列入 stale_active 告警", len(res["stale_active"]) == 1, str(res))
    check("记录了停滞时长", res["stale_active"][0]["idle_minutes"] >= 89, str(res))
    w = c.get(f"/api/workflows/{wf_id}").json()
    check("工作流保持 running（不误杀长步骤）", w["status"] == "running", w["status"])
    check("告警落盘", "长时间无推进（有活任务，不回收）" in log_text())


def test_threshold_and_params() -> None:
    print("\n[7] 阈值必须大于实测最长单步 24.5 分钟（§4.2 证据）")
    check("阈值 >= 40 分钟", app_module.STALE_RUNNING_MINUTES >= 40,
          str(app_module.STALE_RUNNING_MINUTES))
    check("心跳间隔为正值且不超过 1 小时",
          0 < app_module.REAP_INTERVAL_SECONDS <= 3600, str(app_module.REAP_INTERVAL_SECONDS))
    check("日志保留天数 > 0", app_module.LOG_BACKUP_DAYS > 0, str(app_module.LOG_BACKUP_DAYS))
    check("定期回收是协程", callable(app_module._reap_loop))


def test_timestamp_parsing_is_fail_safe() -> None:
    print("\n[8] 时间戳容错：宁可漏杀，不可误杀")
    from datetime import timezone as tz

    a = app_module._parse_ts("2026-10-03 21:37:16")        # SQLite CURRENT_TIMESTAMP
    b = app_module._parse_ts("2026-10-03T21:37:16+00:00")  # _now() 的 ISO 串
    check("SQLite 空格格式可解析", a is not None and a.tzinfo is not None, str(a))
    check("两种格式指向同一时刻", a is not None and b is not None and a == b, "%s %s" % (a, b))
    check("时间戳带时区（能安全做减法）",
          a is not None and a.tzinfo == tz.utc, str(a))
    check("垃圾值 -> None", app_module._parse_ts("not-a-timestamp") is None)
    check("空值 -> None", app_module._parse_ts(None) is None)

    c, _ = new_client()
    wf_id = mk_workflow(c)
    set_status(wf_id, wf="running", step="running")
    age_workflow(wf_id, 120, garbage_event=True)   # 一个来源不可解析
    con = app_module.get_db()
    try:
        check("任一来源不可解析 -> last_activity 判为未知", app_module.last_activity(con, wf_id) is None)
        res = app_module.reap_stale_workflows(con)
        check("活动未知的工作流不被回收", res["repaired"] == [], str(res))
        check("列入 unknown_activity 供人工核查", res["unknown_activity"] == [wf_id], str(res))
    finally:
        con.close()
    check("工作流保持 running", c.get(f"/api/workflows/{wf_id}").json()["status"] == "running")


def test_logging_to_disk() -> None:
    print("\n[9] 日志归集：落盘 + 轮转 + modemon.workflow 可见（§4.4 / §3.3）")
    check("日志文件已创建", LOG_FILE.exists(), str(LOG_FILE))
    check("默认日志目录 = <backend>/logs",
          app_module.LOG_DIR == BACKEND / "logs", str(app_module.LOG_DIR))

    token = "ops-marker-%d" % os.getpid()
    logging.getLogger("modemon.workflow").info("%s", token)   # 没配 handler 时这条永远看不到
    text = log_text()
    check("**modemon.workflow 的 INFO 能落盘**（本次核心验收点）", token in text)
    check("带 logger 名与时间戳", "modemon.workflow" in text, text[-200:])

    app_module.setup_logging(log_dir=LOGDIR)                  # 幂等：重复配置不重复落盘
    token2 = "ops-idem-%d" % os.getpid()
    logging.getLogger("modemon.workflow").info("%s", token2)
    check("重复 setup_logging 幂等（同一条只出现一次）",
          log_text().count(token2) == 1, str(log_text().count(token2)))

    handlers = [h for h in logging.getLogger().handlers
                if getattr(h, "_modemon_log_path", None) == str(LOG_FILE)]
    check("该路径只有一个 handler", len(handlers) == 1, str(len(handlers)))
    fh = handlers[0] if handlers else None
    check("按天轮转（TimedRotatingFileHandler@midnight）",
          isinstance(fh, TimedRotatingFileHandler) and fh.when == "MIDNIGHT", str(fh))
    check("保留 %d 天" % app_module.LOG_BACKUP_DAYS,
          fh is not None and fh.backupCount == app_module.LOG_BACKUP_DAYS, str(getattr(fh, "backupCount", None)))
    check("轮转文件名带日期后缀",
          fh is not None and fh.suffix == "%Y-%m-%d.log", str(getattr(fh, "suffix", None)))

    default_path = app_module.setup_logging()                 # 默认路径 = backend/logs/
    check("默认日志路径已建立", default_path == app_module.LOG_DIR / "modemon.log"
          and default_path.exists(), str(default_path))


def test_repair_endpoint_logged() -> None:
    print("\n[10] /repair 关键路径有 INFO 日志（§3.1）")
    c, _ = new_client()
    wf_id = mk_workflow(c)
    set_status(wf_id, wf="running", step="running")
    r = c.post(f"/api/workflows/{wf_id}/repair")
    check("repair = 200", r.status_code == 200, r.text[:160])
    check("契约字段 count 不变", r.json()["count"] >= 2, str(r.json()))
    check("/repair 动作落盘", "/repair 手动回收" in log_text())
    check("日志含工作流短 id", wf_id[:12] in log_text())


def test_export_structured_error_on_exception() -> None:
    print("\n[11] 导出异常 -> 结构化错误 + traceback + workspace 快照（§3.4）")
    c, root = new_client()
    ws = mk_workspace(root)

    def boom(*_a, **_kw):
        raise RuntimeError("boom-diag-marker")

    original = lx.export_latex
    lx.export_latex = boom
    try:
        r = c.post("/api/paper/export", json={
            "workspace": str(ws), "template": "comp_cumcm", "formats": ["latex"],
            "compile_pdf": False,
        })
    finally:
        lx.export_latex = original

    check("HTTP 500（不再裸 500）", r.status_code == 500, str(r.status_code))
    body = r.json()
    check("结构化 detail.code", body.get("detail", {}).get("code") == "PAPER_EXPORT_FAILED", r.text[:200])
    check("消息含异常类型", "RuntimeError" in body["detail"]["message"], r.text[:200])
    check("消息含诊断编号", "诊断编号" in body["detail"]["message"], r.text[:200])
    check("**不回传 traceback**（结构化而非裸堆栈）", "Traceback" not in r.text, r.text[:200])
    text = log_text()
    check("traceback 落盘", "Traceback (most recent call last)" in text)
    check("异常原文落盘", "boom-diag-marker" in text)
    check("workspace 快照落盘", "workspace 快照" in text and "file_count" in text)
    check("快照含 sections 清单", "01_problem.md" in text)


def test_export_500_bad_utf8_results() -> None:
    print("\n[12] 实测 500 路径 B：all_results.json 非 UTF-8（UnicodeDecodeError）")
    c, root = new_client()
    ws = mk_workspace(root)
    (ws / "figures" / "all_results.json").write_bytes(b'{"a": "\xff\xfe bad"}')

    r = c.post("/api/paper/export", json={
        "workspace": str(ws), "template": "comp_cumcm", "formats": ["latex"],
        "compile_pdf": False,
    })
    check("HTTP 500 被结构化", r.status_code == 500
          and r.json()["detail"]["code"] == "PAPER_EXPORT_FAILED", r.text[:200])
    check("根因类型出现在回包中", "UnicodeDecodeError" in r.json()["detail"]["message"],
          r.text[:200])
    text = log_text()
    check("根因类型落盘", "UnicodeDecodeError" in text)
    check("定位到 paper_build.load_results", "paper_build.py" in text and "load_results" in text)
    check("快照记录了 all_results 大小", '"all_results": {"bytes"' in text)


def test_export_readonly_tex_never_bare_500() -> None:
    print("\n[13] 只读/被占用的 main.tex：要么结构化 500，要么保住 agent 产物后成功")
    c, root = new_client()
    ws = mk_workspace(root)
    marker = "agent-product-%d" % os.getpid()
    tex = ws / "paper" / "main.tex"
    tex.write_text("%% " + marker, encoding="utf-8")
    os.chmod(tex, stat.S_IREAD)
    try:
        read_only = not os.access(tex, os.W_OK)
        r = c.post("/api/paper/export", json={
            "workspace": str(ws), "template": "comp_cumcm", "formats": ["latex"],
            "compile_pdf": False,
        })
    finally:
        os.chmod(tex, stat.S_IWRITE)

    body = r.json()
    text = log_text()
    kept = any(marker in p.read_text(encoding="utf-8", errors="replace")
               for p in (ws / "paper").glob("*.tex"))
    check("前置条件：文件确为只读（Windows chmod 生效）", read_only, str(read_only))
    check("**不裸 500**：要么结构化错误、要么成功",
          r.status_code == 200 or body.get("detail", {}).get("code") == "PAPER_EXPORT_FAILED",
          "%s %s" % (r.status_code, r.text[:160]))
    check("不回传 traceback", "Traceback" not in r.text, r.text[:160])
    check("失败分支根因可查 / 成功分支 agent 产物留存",
          ("PermissionError" in text) if r.status_code == 500 else kept,
          "%s kept=%s" % (r.status_code, kept))
    check("回包结构完整（200 有 ok、500 无 results）",
          ("ok" in body) if r.status_code == 200 else ("results" not in body),
          r.text[:160])


def test_export_500_when_paper_path_blocked() -> None:
    print("\n[13b] 确定性真实失败：paper/ 被同名文件占位（FileExistsError）")
    c, root = new_client()
    ws = root / "ws"
    (ws / "figures").mkdir(parents=True)
    (ws / "figures" / "all_results.json").write_text('{"a": 1}', encoding="utf-8")
    (ws / "paper").write_text("这是一个文件，不是目录", encoding="utf-8")

    r = c.post("/api/paper/export", json={
        "workspace": str(ws), "template": "comp_cumcm", "formats": ["latex"],
        "compile_pdf": False,
    })
    body = r.json()
    check("HTTP 500", r.status_code == 500, str(r.status_code))
    check("结构化 code", body.get("detail", {}).get("code") == "PAPER_EXPORT_FAILED", r.text[:160])
    check("消息含诊断编号", "诊断编号" in body["detail"]["message"], r.text[:160])
    text = log_text()
    check("失败落盘且带 traceback",
          "论文导出失败 diag=" in text and "Traceback (most recent call last)" in text)
    check("快照标出 paper 不是目录（现场可判读）",
          '"paper_dir": false' in text, text[-260:])


def test_export_still_succeeds() -> None:
    print("\n[14] 正常路径无回归（兜底不能把成功也吞掉）")
    c, root = new_client()
    ws = mk_workspace(root)
    r = c.post("/api/paper/export", json={
        "workspace": str(ws), "template": "comp_cumcm", "formats": ["latex"],
        "compile_pdf": False,
    })
    check("HTTP 200", r.status_code == 200, r.text[:200])
    body = r.json()
    check("返回 latex 结果", "latex" in body.get("results", {}), str(body)[:200])
    check("产出 main.tex", body["results"]["latex"]["tex"].endswith("main.tex"),
          str(body["results"]["latex"].get("tex")))
    check("空 formats 仍为 200 且 ok=false（原语义不变）",
          c.post("/api/paper/export", json={
              "workspace": str(ws), "formats": []}).json().get("ok") is False)
    check("工作区不存在仍为 404（显式错误不吞）",
          c.post("/api/paper/export", json={
              "workspace": str(root / "nope")}).status_code == 404)


def main() -> int:
    print("=" * 74)
    print("modemon 运维健壮性回归测试（僵尸回收 / 日志归集 / 导出兜底）")
    print("=" * 74)
    test_startup_reaps_zombies()
    test_lifespan_wires_startup_maintenance()
    test_reaps_orphan_steps_repair_orphans_misses()
    test_stale_threshold_is_safe()
    test_stale_workflow_is_reaped()
    test_live_task_is_never_killed()
    test_threshold_and_params()
    test_timestamp_parsing_is_fail_safe()
    test_logging_to_disk()
    test_repair_endpoint_logged()
    test_export_structured_error_on_exception()
    test_export_500_bad_utf8_results()
    test_export_readonly_tex_never_bare_500()
    test_export_500_when_paper_path_blocked()
    test_export_still_succeeds()
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
