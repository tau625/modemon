"""工作流编排：执行步骤、落库、广播、检查点暂停与恢复。

状态机
------
    workflow.status : pending -> running -> paused -> running -> completed
                                        \-> failed
    step.status     : pending -> running -> waiting_checkpoint -> completed
                                        \-> failed / skipped

**检查点语义**（与蓝方一致）
--------------------------
`enable_checkpoints=1` 时，凡 `has_checkpoint=True` 的步骤完成后**不立即前进**，
而是写入一条 `checkpoints` 记录、把步骤置为 `waiting_checkpoint`、工作流置为 `paused`，
等用户 resolve 后才继续。关闭检查点则一路连续执行。

**持久化原则**
-------------
执行过程中每个事件**先落库、再广播**。WS 断线不影响状态完整性；
前端重连后用 REST 全量拉取即可还原过程卡片。
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from . import agent_runtime as ar
from . import broadcast as bc
from . import run_events as re_mod
from . import step_runner as sr
from . import workflow_engine as we

log = logging.getLogger("modemon.workflow")

Broadcaster = Callable[[str, dict, Optional[str]], Awaitable[int]]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


@dataclass
class StepExecutionReport:
    ok: bool
    workflow_id: str
    skill_name: str
    run_id: str
    message_id: int
    status: str                     # completed | waiting_checkpoint | failed
    checkpoint_id: Optional[int] = None
    cost_usd: Optional[float] = None
    duration_s: float = 0.0
    error_code: str = ""
    error: str = ""
    event_count: int = 0
    persisted_events: int = 0
    degraded: list[str] = field(default_factory=list)
    gates: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "ok": self.ok, "workflow_id": self.workflow_id,
            "skill_name": self.skill_name, "run_id": self.run_id,
            "message_id": self.message_id, "status": self.status,
            "checkpoint_id": self.checkpoint_id, "cost_usd": self.cost_usd,
            "duration_s": self.duration_s, "error_code": self.error_code,
            "error": self.error, "event_count": self.event_count,
            "persisted_events": self.persisted_events,
            "degraded": self.degraded, "gates": self.gates,
        }


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _get_step(con: sqlite3.Connection, wf_id: str, skill: str) -> sqlite3.Row:
    row = con.execute(
        "SELECT * FROM workflow_steps WHERE workflow_id=? AND skill_name=?",
        (wf_id, skill),
    ).fetchone()
    if row is None:
        raise ValueError(f"工作流 {wf_id} 没有步骤 {skill}")
    return row


def _set_step(
    con: sqlite3.Connection,
    wf_id: str,
    skill: str,
    *,
    status: Optional[str] = None,
    model_used: Optional[str] = None,
    error: Optional[str] = None,
    started: bool = False,
    completed: bool = False,
) -> None:
    sets, args = [], []
    if status is not None:
        sets.append("status=?"); args.append(status)
    if model_used is not None:
        sets.append("model_used=?"); args.append(model_used)
    if error is not None:
        sets.append("error_message=?"); args.append(error)
    if started:
        sets.append("started_at=?"); args.append(_now())
    if completed:
        sets.append("completed_at=?"); args.append(_now())
    if not sets:
        return
    args += [wf_id, skill]
    con.execute(f"UPDATE workflow_steps SET {', '.join(sets)} WHERE workflow_id=? AND skill_name=?", args)
    con.commit()


def _set_workflow(con: sqlite3.Connection, wf_id: str, **fields: Any) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    con.execute(f"UPDATE workflows SET {sets}, updated_at=? WHERE id=?",
                (*fields.values(), _now(), wf_id))
    con.commit()


def next_pending_step(con: sqlite3.Connection, wf_id: str) -> Optional[dict[str, Any]]:
    """按 step_order 取下一个可执行步骤。

    `waiting_checkpoint` 与 `skipped` 都会被视为"阻塞/已过"，
    因此**必须先把检查点解决掉**，流水线才会前进。
    """
    row = con.execute(
        "SELECT skill_name, display_name, step_order, status FROM workflow_steps"
        " WHERE workflow_id=? AND status IN ('pending')"
        " ORDER BY step_order LIMIT 1",
        (wf_id,),
    ).fetchone()
    return dict(row) if row else None


def first_blocking_step(con: sqlite3.Connection, wf_id: str) -> Optional[dict[str, Any]]:
    """返回当前阻塞流水线的步骤（waiting_checkpoint 优先）。"""
    row = con.execute(
        "SELECT skill_name, display_name, step_order, status FROM workflow_steps"
        " WHERE workflow_id=? AND status IN ('running','waiting_checkpoint')"
        " ORDER BY CASE status WHEN 'waiting_checkpoint' THEN 0 ELSE 1 END, step_order LIMIT 1",
        (wf_id,),
    ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# 执行单个步骤
# ---------------------------------------------------------------------------


#: 产出数值结果后需要做**诚信审计**的步骤。
#: 审计对象是 `figures/all_results.json`（数据真相源）与代码的一致性。
POST_AUDIT_SKILLS: frozenset[str] = frozenset({
    "comp-code", "comp-stats-code", "code", "experiment-run",
    # `comp_stats`（统计建模大赛）序列的第 2 步——流B 新增时按步骤级
    # select 保留了 `comp-stats-code`，但那一步的**默认**技能名是
    # `comp-data-analysis`。漏掉它会让统计流的 `all_results.json` 诚信审计不触发。
    "comp-data-analysis",
})

#: 后台审计任务的强引用（防 GC 中途回收）
_AUDIT_TASKS: set[asyncio.Task[Any]] = set()

#: 产出了 FigureSpec 后需要**引擎渲染**的步骤。
#:
#: ⚠️ 只改提示词是不够的：实测发现 agent 写了 `architecture.spec.json`
#: 却**没人去渲染它**，于是 `architecture.png` 根本不存在——
#: 而 agent 同时手写了 `latex_includes.tex`，把"没渲染"这件事**掩盖**了。
#: 所以必须在步骤之后由引擎把 spec 变成真正的图。
POST_FIGURE_SKILLS: frozenset[str] = frozenset({
    "paper-figure-drawio", "comp-arch-figure", "figure",
})

#: 图表渲染任务的强引用
_FIGURE_TASKS: set[asyncio.Task[Any]] = set()

#: 产出论文后需要做**引用审计**的步骤（ARIS `citation-audit`，MIT License）。
#:
#: ⚠️ **不要在这里另抄一份 skill 名单**——常量真源在
#: `services/citation_audit.py::CITATION_AUDIT_SKILLS`。抄两份必然漂移。
try:
    from .citation_audit import CITATION_AUDIT_SKILLS
except Exception:                    # 模块缺失时静默不触发，不炸主流程
    CITATION_AUDIT_SKILLS = frozenset()

#: 引用审计任务的强引用（防 GC 中途回收）
_CITATION_TASKS: set[asyncio.Task[Any]] = set()


def _persist_custom_event(*, workflow_id: str, kind: str, payload: dict,
                          title: str = "", detail: str = "") -> None:
    """把自定义事件写入 `chat_run_events`。

    ⚠️ **必须写库，不能只广播**。实测发现 `push` 是**纯广播**函数：

        push = broadcaster or (lambda t, p, w: bc.hub.publish(t, p, workflow_id=w))

    它只发 WebSocket，不落库。于是 `result_audit` / `figure_render`
    这类自定义事件广播出去就没了——事后**查不到**，违反
    "历史一律走 run-events 端点" 的设计原则（实测踩过）。

    `map_event` 只认标准 EventKind，所以自定义事件走直接插入。
    """
    try:
        from . import run_events as re2

        con = _open_conn(None)
        try:
            row = con.execute(
                "SELECT id FROM chat_messages WHERE session_id=?"
                " ORDER BY id DESC LIMIT 1", (workflow_id,)).fetchone()
            message_id = row["id"] if row else 0
            ev = re2.sanitize_custom_evidence(dict(payload))
            con.execute(
                "INSERT OR IGNORE INTO chat_run_events"
                " (event_id, workflow_id, message_id, run_id, sequence, kind, state,"
                "  title, safe_detail, public_artifact_path, started_at, completed_at,"
                "  evidence_json)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, workflow_id, message_id,
                 re2.new_run_id(), 1, kind,
                 "completed" if payload.get("ok", True) else "failed",
                 title or kind,
                 re2.redact(detail)[:re2.MAX_SAFE_DETAIL], None,
                 _now(), _now(), json.dumps(ev, ensure_ascii=False)),
            )
            con.commit()
        finally:
            con.close()
    except Exception as exc:
        log.warning("persist custom event failed: %s", exc)


async def _run_post_step_figures(*, workflow_id: str, skill_name: str,
                                 workspace: Path, push) -> None:
    """后台把 FigureSpec 渲染成 SVG/PNG 并登记进 `latex_includes.tex`。

    非阻塞；渲染失败只推事件，**不影响步骤状态**。
    用 `merge=True` 追加而非覆盖——保留 agent 手写的那份登记。
    """
    try:
        from . import figure_pipeline as fp

        rep = await asyncio.to_thread(fp.build_figures, workspace, merge=True)
        payload = {
            "workflow_id": workflow_id, "triggered_by": skill_name,
            "ok": rep.ok, "rendered": rep.rendered,
            "skipped": rep.skipped, "errors": rep.errors,
            "includes_tex": str(rep.includes_tex) if rep.includes_tex else None,
        }
        _persist_custom_event(
            workflow_id=workflow_id, kind="figure_render", payload=payload,
            title="FigureSpec 渲染：%d 张" % len(rep.rendered),
            detail="; ".join(rep.errors[:3]) or
                   "; ".join(str(x.get("png")) for x in rep.rendered[:3]))
        await push("figure_render", payload, workflow_id)
    except Exception as exc:
        try:
            await push("figure_render", {
                "workflow_id": workflow_id, "triggered_by": skill_name,
                "ok": False, "errors": ["渲染未执行：%s" % exc],
            }, workflow_id)
        except Exception:
            pass


async def _run_post_step_audit(*, workflow_id: str, skill_name: str,
                               workspace: Path, push) -> None:
    """后台跑一次**独立的**结果诚信审计（ARIS experiment-audit，MIT）。

    任何失败都记为 `skipped`，**绝不影响步骤状态**——
    审计是加分项，不是硬门槛（与 vision 自检同一取舍）。
    """
    try:
        from . import result_audit as ra

        result_file = "figures/all_results.json"
        r = await asyncio.to_thread(
            ra.audit_workspace, workspace, result_file=result_file)

        payload = {
            "workflow_id": workflow_id,
            "triggered_by": skill_name,
            "skill_used": r.skill_used,
            "verdict": r.verdict,
            "ok": r.ok,
            "issues": r.issues,
            "notes": r.notes,
            "upstream": {"repo": ra.UPSTREAM_REPO,
                         "license": ra.UPSTREAM_LICENSE},
        }
        # 先写库（可事后查询），再广播（实时）
        _persist_custom_event(
            workflow_id=workflow_id, kind="result_audit", payload=payload,
            title="结果诚信审计：%s" % r.verdict,
            detail="; ".join(r.issues[:3]) or "; ".join(str(n) for n in r.notes[:3]))
        await push("result_audit", payload, workflow_id)
    except Exception as exc:  # 审计出任何问题都不能拖垮主流程
        # ⚠️ 异常分支也要**写库**：只 push 的话事后查不到，
        #    就变成"审计静默消失"——实测踩过这个缺口。
        payload = {
            "workflow_id": workflow_id, "triggered_by": skill_name,
            "verdict": "skipped", "ok": True,
            "notes": ["审计未执行：%s" % exc],
        }
        _persist_custom_event(
            workflow_id=workflow_id, kind="result_audit", payload=payload,
            title="结果诚信审计：未执行", detail=str(exc)[:200])
        try:
            await push("result_audit", payload, workflow_id)
        except Exception:
            pass


async def _run_post_step_citation_audit(*, workflow_id: str, skill_name: str,
                                        workspace: Path, push) -> None:
    """后台跑一次**独立的**引用审计（ARIS `citation-audit`，MIT License）。

    与 `_run_post_step_audit` 同构：失败一律降级 `skipped`，**不影响步骤状态**；
    异常分支也必须**写库**（否则审计静默消失）。
    """
    kind = "citation_audit"
    try:
        from . import citation_audit as ca

        kind = ca.CITATION_AUDIT_EVENT_KIND
        r = await asyncio.to_thread(ca.audit_paper, workspace)
        payload = {
            "workflow_id": workflow_id, "triggered_by": skill_name,
            "skill_used": r.skill_used, "verdict": r.verdict,
            "top_verdict": r.top_verdict, "ok": r.ok,
            "issues": r.issues, "notes": r.notes, "targets": r.targets,
            "upstream": {"repo": ca.UPSTREAM_REPO, "license": ca.UPSTREAM_LICENSE},
        }
        _persist_custom_event(
            workflow_id=workflow_id, kind=kind, payload=payload,
            title="引用审计：%s" % r.verdict,
            detail="; ".join(r.issues[:3]) or "; ".join(str(n) for n in r.notes[:3]))
        await push(kind, payload, workflow_id)
    except Exception as exc:
        payload = {
            "workflow_id": workflow_id, "triggered_by": skill_name,
            "verdict": "skipped", "ok": True,
            "notes": ["引用审计未执行：%s" % exc],
        }
        _persist_custom_event(
            workflow_id=workflow_id, kind=kind, payload=payload,
            title="引用审计：未执行", detail=str(exc)[:200])
        try:
            await push(kind, payload, workflow_id)
        except Exception:
            pass


def _spawn_post_step_hooks(*, workflow_id: str, skill_name: str,
                           workspace: Path, push) -> None:
    """步骤成功后派生后台钩子（审计 + 图表渲染）。

    ⚠️ **必须在两条路径上都调用**：有检查点的步骤会提前 `return report`，
    而 `comp-code`（需要审计的那个）**恰好有检查点**——
    实测中审计钩子因此从未执行，而 `figure_render` 正常（那个步骤没检查点），
    表现为"一个生效一个不生效"，很难一眼看出来。
    """
    if not Path(workspace).is_dir():
        log.info("post-step hooks skipped: workspace missing %s", workspace)
        return

    log.info("post-step hooks: skill=%s wf=%s", skill_name, workflow_id[:12])

    if skill_name in POST_AUDIT_SKILLS:
        t = asyncio.create_task(_run_post_step_audit(
            workflow_id=workflow_id, skill_name=skill_name,
            workspace=Path(workspace), push=push))
        _AUDIT_TASKS.add(t)                      # 防 GC
        t.add_done_callback(_AUDIT_TASKS.discard)
        log.info("audit task spawned for %s", skill_name)

    if skill_name in POST_FIGURE_SKILLS:
        t2 = asyncio.create_task(_run_post_step_figures(
            workflow_id=workflow_id, skill_name=skill_name,
            workspace=Path(workspace), push=push))
        _FIGURE_TASKS.add(t2)
        t2.add_done_callback(_FIGURE_TASKS.discard)
        log.info("figure task spawned for %s", skill_name)

    if skill_name in CITATION_AUDIT_SKILLS:
        t3 = asyncio.create_task(_run_post_step_citation_audit(
            workflow_id=workflow_id, skill_name=skill_name,
            workspace=Path(workspace), push=push))
        _CITATION_TASKS.add(t3)                  # 防 GC
        t3.add_done_callback(_CITATION_TASKS.discard)
        log.info("citation audit task spawned for %s", skill_name)


async def execute_step(
    con: sqlite3.Connection,
    *,
    workflow_id: str,
    skill_name: str,
    workspace: Path,
    template: str = "comp_zh",
    language: str = "zh",
    runtime: Optional[str] = None,
    model: Optional[str] = None,
    effort: Optional[str] = None,
    max_budget_usd: Optional[float] = 1.0,
    strict: bool = False,
    allowed_tools: Optional[tuple[str, ...]] = None,
    permission_mode: Optional[str] = "acceptEdits",
    extra_prompt: str = "",
    message_id: Optional[int] = None,
    broadcaster: Optional[Broadcaster] = None,
) -> StepExecutionReport:
    """执行一个步骤：落库 + 广播 + 检查点。

    ⚠️ **必须由后台任务调用，不要在 HTTP 请求里直接 await。**
    实测教训：客户端在长步骤中途断开会让该协程被取消，
    于是步骤永远停在 `running`，变成僵尸状态（既没完成也没失败）。
    用 `start_step_run()` 启动后台任务，请求立即返回。
    """
    wf = con.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
    if wf is None:
        raise ValueError(f"工作流不存在: {workflow_id}")

    snap = _get_step(con, workflow_id, skill_name)
    run_id = re_mod.new_run_id()
    store = re_mod.RunEventStore(con, workspace=Path(workspace))
    if message_id is None:
        message_id = _ensure_task_message(con, workflow_id, skill_name)

    _set_step(con, workflow_id, skill_name, status="running", started=True, error="")
    _set_workflow(con, workflow_id, status="running", current_step=skill_name)

    push = broadcaster or (lambda t, p, w: bc.hub.publish(t, p, workflow_id=w))
    await push("step_started", {
        "skill_name": skill_name, "run_id": run_id, "message_id": message_id,
    }, workflow_id)

    request = sr.StepRunRequest(
        workflow_id=workflow_id, skill_name=skill_name, workspace=Path(workspace),
        template=template, language=language, runtime=runtime, model=model,
        effort=effort, max_budget_usd=max_budget_usd, strict=strict,
        allowed_tools=allowed_tools, extra_prompt=extra_prompt,
        permission_mode=permission_mode,
    )

    outcome: Optional[sr.StepRunOutcome] = None
    seq = 0
    persisted = 0
    interrupted: Optional[BaseException] = None
    try:
        async for item in sr.run_step(request):
            if isinstance(item, sr.StepRunOutcome):
                outcome = item
                continue
            rec = store.append(workflow_id=workflow_id, message_id=message_id,
                               run_id=run_id, sequence=seq, event=item)
            if rec is not None:
                persisted += 1
                await push("run_event", {
                    "message_id": message_id, "run_id": run_id,
                    "event": {
                        "sequence": rec.sequence, "kind": rec.kind, "state": rec.state,
                        "title": rec.title, "safe_detail": rec.safe_detail,
                        "public_artifact_path": rec.public_artifact_path,
                        "started_at": rec.started_at,
                    },
                }, workflow_id)
            seq += 1
    except asyncio.CancelledError as exc:
        # 被取消（进程退出 / 上层取消）——**必须留下痕迹**，
        # 否则步骤会永远停在 running，心跳修复也无从判断。
        interrupted = exc
    except BaseException as exc:  # noqa: BLE001
        interrupted = exc

    if interrupted is not None or outcome is None:
        reason = f"执行被中断: {type(interrupted).__name__ if interrupted else '无结果'}"
        _set_step(con, workflow_id, skill_name, status="failed",
                  error=reason, completed=True)
        _set_workflow(con, workflow_id, status="failed")
        con.execute("UPDATE chat_messages SET status='interrupted', error_message=?,"
                    " completed_at=? WHERE id=?", (reason, _now(), message_id))
        con.commit()
        await push("step_failed", {"skill_name": skill_name, "run_id": run_id,
                                   "error_code": "INTERRUPTED", "error": reason},
                   workflow_id)
        if interrupted is not None and not isinstance(interrupted, asyncio.CancelledError):
            raise interrupted
        raise asyncio.CancelledError() if interrupted else RuntimeError(reason)

    report = StepExecutionReport(
        ok=outcome.ok, workflow_id=workflow_id, skill_name=skill_name, run_id=run_id,
        message_id=message_id, status="completed" if outcome.ok else "failed",
        cost_usd=outcome.cost_usd, duration_s=outcome.duration_s,
        error_code=outcome.error_code, error=outcome.error,
        event_count=outcome.event_count, persisted_events=persisted,
        degraded=list(outcome.degraded), gates=list(outcome.gates),
    )

    if not outcome.ok:
        _set_step(con, workflow_id, skill_name, status="failed",
                  error=(outcome.error or outcome.error_code)[:500], completed=True)
        _set_workflow(con, workflow_id, status="failed")
        con.execute(
            "UPDATE chat_messages SET status='failed', error_message=?, completed_at=?"
            " WHERE id=?", ((outcome.error or outcome.error_code)[:500], _now(), message_id))
        con.commit()
        await push("step_failed", report.summary(), workflow_id)
        return report

    # ---- 检查点 ----
    step = _get_step(con, workflow_id, skill_name)
    if bool(wf["enable_checkpoints"]) and bool(step["has_checkpoint"]):
        cp_id = _create_checkpoint(con, workflow_id, skill_name,
                                   step["checkpoint_type"] or "approve",
                                   {"outputs": json.loads(step["output_files"] or "[]"),
                                    "run_id": run_id})
        _set_step(con, workflow_id, skill_name, status="waiting_checkpoint")
        _set_workflow(con, workflow_id, status="paused")
        con.execute("UPDATE chat_messages SET status='waiting_checkpoint' WHERE id=?", (message_id,))
        con.commit()
        report.status = "waiting_checkpoint"
        report.checkpoint_id = cp_id
        await push("checkpoint_created", {
            "checkpoint_id": cp_id, "skill_name": skill_name,
            "checkpoint_type": step["checkpoint_type"] or "approve",
            "message_id": message_id,
        }, workflow_id)
        # ★ 钩子必须在**这里**也调用——本分支会提前 return，
        #   而 comp-code（需审计）恰好走这条路径（有检查点）。
        _spawn_post_step_hooks(workflow_id=workflow_id, skill_name=skill_name,
                               workspace=Path(workspace), push=push)
        return report

    _set_step(con, workflow_id, skill_name, status="completed", completed=True,
              model_used=outcome.model_used)
    con.execute("UPDATE chat_messages SET status='done', completed_at=? WHERE id=?",
                (_now(), message_id))
    con.commit()
    _sync_stage_receipt(con, workflow_id, skill_name)
    await push("step_completed", report.summary(), workflow_id)

    # ★ 后台钩子：结果诚信审计（ARIS `experiment-audit`）+ 图表渲染
    #   （ARIS `figure-spec`），两者都是 MIT License。
    #   非阻塞 fire-and-forget；失败一律降级，**不影响步骤状态**。
    _spawn_post_step_hooks(workflow_id=workflow_id, skill_name=skill_name,
                           workspace=Path(workspace), push=push)

    # ⚠️ 必须 await：漏掉会让"全部步骤完成"的判定永远不执行，
    #    工作流停在 running。实测由 RuntimeWarning 暴露：
    #    "coroutine '_advance_or_finish' was never awaited"
    await _advance_or_finish(con, workflow_id, push)
    return report


def _ensure_task_message(con: sqlite3.Connection, wf_id: str, skill: str) -> int:
    """为本次执行准备一条 chat_messages 记录（过程卡片挂靠它）。

    `content` 是 NOT NULL：这里存"执行 <skill>"这一事实描述，
    不把模型输出写进去（输出在产物文件里，且可能含未审内容）。
    """
    cur = con.execute(
        "INSERT INTO chat_messages (session_id, role, content, skill_name, status,"
        " item_kind, operation_kind, execution_scope, started_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (wf_id, "assistant", f"执行 {skill}", skill, "running",
         "task", "run_step", "full", _now()),
    )
    con.commit()
    return int(cur.lastrowid)


def _sync_stage_receipt(con: sqlite3.Connection, wf_id: str, skill: str) -> None:
    """步骤成功完成后写入阶段验收回执。

    注意：**只记录事实**，不做"推断式验收"——
    蓝方明确写了 "Never inferred from the number of focused task receipts"。
    这里的语义是「引擎确认该步骤产出已通过质量门」，
    与「用户在对话里显式 accept」是两件事，因此用 `engine:` 前缀区分来源。
    """
    con.execute(
        "INSERT INTO chat_stage_receipts (workflow_id, skill_name, snapshot, evidence_json)"
        " VALUES (?,?,?,?) ON CONFLICT(workflow_id, skill_name) DO UPDATE SET"
        " snapshot=excluded.snapshot, evidence_json=excluded.evidence_json,"
        " accepted_at=CURRENT_TIMESTAMP",
        (wf_id, skill, "engine:quality_gates_passed",
         json.dumps({"source": "workflow_engine"}, ensure_ascii=False)),
    )
    con.commit()


# ---------------------------------------------------------------------------
# 检查点
# ---------------------------------------------------------------------------


def _create_checkpoint(
    con: sqlite3.Connection, wf_id: str, skill: str, ctype: str, data: dict[str, Any]
) -> int:
    cur = con.execute(
        "INSERT INTO checkpoints (workflow_id, step_name, checkpoint_type, data, status)"
        " VALUES (?,?,?,?, 'pending')",
        (wf_id, skill, ctype, json.dumps(data, ensure_ascii=False)),
    )
    con.commit()
    return int(cur.lastrowid)


def pending_checkpoint(con: sqlite3.Connection, wf_id: str) -> Optional[dict[str, Any]]:
    row = con.execute(
        "SELECT * FROM checkpoints WHERE workflow_id=? AND status='pending'"
        " ORDER BY id LIMIT 1", (wf_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "checkpoint_id": row["id"], "workflow_id": row["workflow_id"],
        "step_name": row["step_name"], "checkpoint_type": row["checkpoint_type"],
        "data": json.loads(row["data"] or "{}"), "status": row["status"],
        "created_at": row["created_at"],
        "remaining_seconds": _checkpoint_remaining(row),
    }


def _checkpoint_remaining(row: sqlite3.Row) -> int:
    """剩余等待秒数——前端据此判断后端是否为旧版逻辑（契约字段）。"""
    timeout = we.inactivity_timeout(row["step_name"])
    try:
        created = row["created_at"]
        t = time.mktime(time.strptime(created[:19], "%Y-%m-%dT%H:%M:%S"))
        age = max(0, int(time.time() - t))
    except Exception:
        age = 0
    return max(0, timeout - age)


async def resolve_checkpoint(
    con: sqlite3.Connection,
    *,
    workflow_id: str,
    action: str,
    checkpoint_id: Optional[int] = None,
    data: Optional[dict[str, Any]] = None,
    broadcaster: Optional[Broadcaster] = None,
) -> dict[str, Any]:
    """解决检查点并决定是否继续。

    - `approve`：步骤置 completed，工作流恢复 running，自动推进下一步
    - `stop`：步骤置 completed，工作流保持 paused（用户主动停在检查点）
    - `feedback` / `select`：记录回复，同样推进（反馈内容由上层注入下一次提示）
    """
    if action not in ("approve", "select", "feedback", "stop"):
        raise ValueError(f"非法检查点动作: {action}")

    if checkpoint_id:
        row = con.execute("SELECT * FROM checkpoints WHERE id=? AND workflow_id=?",
                          (checkpoint_id, workflow_id)).fetchone()
    else:
        row = con.execute(
            "SELECT * FROM checkpoints WHERE workflow_id=? AND status='pending'"
            " ORDER BY id LIMIT 1", (workflow_id,)).fetchone()
    if row is None:
        raise LookupError("没有待处理的检查点")

    con.execute(
        "UPDATE checkpoints SET status='resolved', response=?, resolved_at=? WHERE id=?",
        (json.dumps({"action": action, "data": data or {}}, ensure_ascii=False), _now(), row["id"]),
    )
    con.commit()

    push = broadcaster or (lambda t, p, w: bc.hub.publish(t, p, workflow_id=w))
    await push("checkpoint_resolved", {
        "checkpoint_id": row["id"], "action": action, "step_name": row["step_name"],
    }, workflow_id)

    if action != "stop":
        _set_step(con, workflow_id, row["step_name"], status="completed", completed=True)
        _set_workflow(con, workflow_id, status="running")
        await _advance_or_finish(con, workflow_id, push)
    else:
        _set_step(con, workflow_id, row["step_name"], status="completed", completed=True)
        _set_workflow(con, workflow_id, status="paused")

    return {
        "ok": True, "checkpoint_id": row["id"], "action": action,
        "step_name": row["step_name"],
        "workflow_status": con.execute("SELECT status FROM workflows WHERE id=?",
                                       (workflow_id,)).fetchone()["status"],
    }


async def _advance_or_finish(
    con: sqlite3.Connection, wf_id: str, push: Broadcaster
) -> Optional[dict[str, Any]]:
    """检查是否所有步骤都已完成；是则把工作流置为 completed。"""
    remaining = con.execute(
        "SELECT COUNT(*) c FROM workflow_steps WHERE workflow_id=?"
        " AND status NOT IN ('completed','skipped')", (wf_id,),
    ).fetchone()["c"]
    if remaining == 0:
        _set_workflow(con, wf_id, status="completed", current_step=None)
        await push("workflow_completed", {"workflow_id": wf_id}, wf_id)
        return {"workflow_status": "completed"}
    _set_workflow(con, wf_id, status="running")
    return None


# ---------------------------------------------------------------------------
# 连续执行（到检查点为止）
# ---------------------------------------------------------------------------


async def run_until_blocked(
    con: sqlite3.Connection,
    *,
    workflow_id: str,
    workspace: Path,
    max_steps: int = 10,
    **step_kwargs: Any,
) -> list[StepExecutionReport]:
    """连续执行直到：完成 / 失败 / 遇到检查点暂停 / 达到步数上限。

    这是"半自动"模式：开启检查点时会自然地停在每个需要人工确认的步骤。
    """
    reports: list[StepExecutionReport] = []
    for _ in range(max_steps):
        wf = con.execute("SELECT status FROM workflows WHERE id=?", (workflow_id,)).fetchone()
        if wf is None or wf["status"] in ("completed", "failed"):
            break
        blocking = first_blocking_step(con, workflow_id)
        if blocking and blocking["status"] == "waiting_checkpoint":
            break
        nxt = next_pending_step(con, workflow_id)
        if nxt is None:
            await _advance_or_finish(con, workflow_id,
                                     lambda t, p, w: bc.hub.publish(t, p, workflow_id=w))
            break
        rep = await execute_step(con, workflow_id=workflow_id,
                                 skill_name=nxt["skill_name"], workspace=workspace,
                                 **step_kwargs)
        reports.append(rep)
        if not rep.ok or rep.status == "waiting_checkpoint":
            break
    return reports


# ---------------------------------------------------------------------------
# 后台任务注册表
# ---------------------------------------------------------------------------
# 为什么必须后台化：实测中，客户端在长步骤中途断开，
# FastAPI 会取消该请求协程，导致步骤永久停在 running（僵尸态）。
# 长任务的执行周期**不应绑定在 HTTP 请求的生命周期上**。
#
# 蓝方对此有同类机制（`_register_workflow_task` + 心跳修复：
# "定期检查：如果数据库里工作流是 running 但没有对应的 task，自动修复"）。

_RUN_TASKS: dict[str, asyncio.Task[Any]] = {}


def active_runs() -> dict[str, str]:
    """当前在跑的后台任务：{工作流 id: 技能名}。"""
    return {k: (t.get_name() or "") for k, t in _RUN_TASKS.items() if not t.done()}


def is_running(workflow_id: str) -> bool:
    t = _RUN_TASKS.get(workflow_id)
    return t is not None and not t.done()


def start_step_run(
    *,
    workflow_id: str,
    skill_name: str,
    db_path: Optional[Path] = None,
    **kwargs: Any,
) -> str:
    """在后台启动一次步骤执行，**立即返回 run_id**。

    后台任务使用**独立的数据库连接**：SQLite 连接不可跨线程/跨任务共享，
    且这样即使请求侧的连接被关闭也不影响执行。
    """
    if is_running(workflow_id):
        raise RuntimeError(f"工作流 {workflow_id} 已有步骤在运行")
    run_id = re_mod.new_run_id()

    async def _runner() -> None:
        con = _open_conn(db_path)
        try:
            await execute_step(con, workflow_id=workflow_id, skill_name=skill_name, **kwargs)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("step run failed: %s", exc)
        finally:
            con.close()
            _RUN_TASKS.pop(workflow_id, None)

    task = asyncio.create_task(_runner(), name=f"{workflow_id}:{skill_name}")
    _RUN_TASKS[workflow_id] = task
    return run_id


def start_batch_run(
    *,
    workflow_id: str,
    workspace: Path,
    max_steps: int = 10,
    db_path: Optional[Path] = None,
    **kwargs: Any,
) -> str:
    """后台启动"连续执行到检查点"，立即返回 run_id。

    与 `start_step_run` 同理：批量执行可能持续数分钟，
    不能绑定在 HTTP 请求上。
    """
    if is_running(workflow_id):
        raise RuntimeError(f"工作流 {workflow_id} 已有任务在运行")

    async def _runner() -> None:
        con = _open_conn(db_path)
        try:
            await run_until_blocked(con, workflow_id=workflow_id,
                                    workspace=workspace, max_steps=max_steps, **kwargs)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("batch run failed: %s", exc)
        finally:
            con.close()
            _RUN_TASKS.pop(workflow_id, None)

    task = asyncio.create_task(_runner(), name=f"{workflow_id}:batch")
    _RUN_TASKS[workflow_id] = task
    return re_mod.new_run_id()


def _open_conn(db_path: Optional[Path]) -> sqlite3.Connection:
    """打开独立连接。默认复用 main.DB_PATH。"""
    if db_path is None:
        try:
            import main as app_module  # 延迟导入，避免循环

            db_path = app_module.DB_PATH
        except Exception:
            db_path = Path(__file__).resolve().parents[1] / "db" / "modemon.db"
    con = sqlite3.connect(str(db_path), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def repair_orphans(con: sqlite3.Connection, workflow_id: Optional[str] = None) -> dict[str, Any]:
    """修复僵尸状态：库里是 running、但没有对应后台任务的步骤/工作流。

    对应蓝方的心跳自愈机制。**不猜测"大概跑完了"**——
    一律标记为 `failed` 并写明原因，让用户重新执行，
    避免把未验证的中间态当成成功。
    """
    wf_rows = con.execute(
        "SELECT id, current_step FROM workflows WHERE status='running'"
        + (" AND id=?" if workflow_id else ""),
        ((workflow_id,) if workflow_id else ()),
    ).fetchall()

    repaired: list[dict[str, Any]] = []
    for wf in wf_rows:
        wid = wf["id"]
        if is_running(wid):
            continue
        steps = con.execute(
            "SELECT skill_name FROM workflow_steps WHERE workflow_id=? AND status='running'",
            (wid,),
        ).fetchall()
        for s in steps:
            con.execute(
                "UPDATE workflow_steps SET status='failed', completed_at=?,"
                " error_message=? WHERE workflow_id=? AND skill_name=?",
                (_now(), "执行进程中断（无对应后台任务），已标记为失败；请重新执行该步骤",
                 wid, s["skill_name"]),
            )
            repaired.append({"workflow_id": wid, "skill_name": s["skill_name"],
                             "action": "step_running->failed"})
        con.execute("UPDATE workflows SET status='failed', updated_at=? WHERE id=?",
                    (_now(), wid))
        repaired.append({"workflow_id": wid, "action": "workflow_running->failed"})
    con.commit()
    return {"repaired": repaired, "count": len(repaired),
            "active_runs": list(active_runs())}


__all__ = [
    "StepExecutionReport", "execute_step", "resolve_checkpoint", "run_until_blocked",
    "next_pending_step", "first_blocking_step", "pending_checkpoint",
    "start_step_run", "start_batch_run", "active_runs", "is_running", "repair_orphans",
]
