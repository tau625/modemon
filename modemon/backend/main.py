"""modemon backend —— FastAPI 应用入口。

运行：
    python -m uvicorn main:app --host 127.0.0.1 --port 8770

本骨架实现的是**主线**：模板解析、工作流 CRUD、检查点、对话工作台的最小闭环、
设置与模型预设、以及国赛 AI 使用申报门禁。

刻意**未**实现（与 modemon 当前阶段不匹配，见 docs/SPEC-PROVENANCE.md）：
账号体系、计费钱包、加密 Skill capsule、CLI 网关代理。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from models import schemas as S
from routers import editor as editor_router
from routers import ws as ws_router
from services import run_events as re_mod
from services import step_runner as sr
from services import workflow_engine as we
from services import workflow_service as wfs

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "db" / "modemon.db"
SCHEMA_PATH = ROOT / "db" / "schema.sql"
FRONTEND_DIR = ROOT.parent / "frontend"


# ---------------------------------------------------------------------------
# 运行参数（全部可用环境变量覆盖，便于部署时不动代码）
# ---------------------------------------------------------------------------

LOG_DIR = ROOT / "logs"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


# 僵尸回收阈值：**超过该时长无事件推进**的 running 工作流判为僵尸。
# 取 45 分钟的理由（不是拍脑袋）：实测最长的单步 `comp-paper-zh` 为 24.5 分钟
# （reports/26 §4.2），期间可能**一个事件都不落**，阈值必须显著大于它，
# 否则会把正常的长写作步骤误杀。45 分钟 ≈ 1.8×实测上界。
STALE_RUNNING_MINUTES = _env_int("MODEMON_STALE_RUNNING_MINUTES", 45)
# 定期心跳间隔（reports/28 §3.1 建议 5 分钟）。
REAP_INTERVAL_SECONDS = _env_int("MODEMON_REAP_INTERVAL_SECONDS", 300)
# 日志保留天数。按天轮转，文件名 `modemon.log.<YYYY-MM-DD>.log`。
LOG_BACKUP_DAYS = _env_int("MODEMON_LOG_BACKUP_DAYS", 14)

log = logging.getLogger("modemon.app")


# ---------------------------------------------------------------------------
# 日志归集
# ---------------------------------------------------------------------------
# 为什么必须落盘：服务以 background job 运行，wrapper 一退 stdout 就没了；
# 而 `services/workflow_service.py` 里的 `log = getLogger("modemon.workflow")`
# **从来没有 handler**，它打的 `log.info`（钩子派发 / 审计派生）长期不可见——
# 排查"审计没触发"时正是被这一点误导过一次。
#
# 为什么 handler 装在**根 logger**、而不是给 `modemon.workflow` 单独挂一个：
# 子 logger 的记录会向根传播。两边都挂同一个 handler 会让每条记录落盘两次；
# 只挂根 + 把 `modemon` 树显式设为 INFO = 一份日志、全覆盖。


def setup_logging(*, log_dir: Optional[Path] = None) -> Path:
    """配置「文件 + 控制台」双 handler，返回日志文件路径。可重复调用（幂等）。"""
    target_dir = Path(log_dir) if log_dir is not None else LOG_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / "modemon.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    for lg in ("modemon", "modemon.workflow", "modemon.app"):
        logging.getLogger(lg).setLevel(logging.INFO)

    already = any(getattr(h, "_modemon_log_path", None) == str(path)
                  for h in root.handlers)
    if not already:
        fh = TimedRotatingFileHandler(
            path, when="midnight", interval=1, backupCount=LOG_BACKUP_DAYS,
            encoding="utf-8", delay=False,
        )
        fh.suffix = "%Y-%m-%d.log"
        fh.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
        fh.setLevel(logging.INFO)
        fh._modemon_log_path = str(path)  # type: ignore[attr-defined]
        root.addHandler(fh)

        # 控制台只作辅助（后台 job 会丢，落盘才算数）
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
        sh.setLevel(logging.INFO)
        root.addHandler(sh)

    log.info("日志已落盘: %s （按天轮转，保留 %d 天）", path, LOG_BACKUP_DAYS)
    return path


# ---------------------------------------------------------------------------
# 僵尸工作流回收
# ---------------------------------------------------------------------------
# 背景（reports/26 §4.1）：DB 长期滞留 `running`，实测一次排查中**9 个僵尸并发**
# 与真实运行争抢 agent 进程，导致误判"审计没触发"。
#
# 判定口径（刻意保守，两类分开处理）：
#   A. 库里 running + **无对应后台任务** → 僵尸，标 failed。
#      （启动时用既有的 `wfs.repair_orphans()`；定期用同一函数，**不改它**）
#   B. 库里 running + **有活任务**，但**超过阈值无事件推进** → **只告警不动手**。
#      不猜"大概跑完了"：它可能只是长步骤里长时间无事件，杀掉会造成真实数据丢失。
#   C. 库里**非** running、却有 `running` 步骤 → 遗留（步骤只能随工作流在跑），标 failed。
#      `repair_orphans()` 只扫 status='running' 的工作流，**扫不到这一类**；
#      实测库里就躺着一条（workflow 27dc89fb… / comp-code）。修它需要改
#      services（不在本流写作用域），故在此独立兜住并已上报。


def _parse_ts(raw: Any) -> Optional[datetime]:
    """容错解析时间戳。库里混着 `_now()` 的 ISO 串与 SQLite 的 `CURRENT_TIMESTAMP`
    （空格分隔、无时区），直接用字符串比大小时序会错，必须逐个解析。"""
    if raw in (None, ""):
        return None
    s = str(raw).strip().replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def last_activity(con: sqlite3.Connection, wf_id: str) -> Optional[datetime]:
    """工作流最后一次「有推进」的时间：取各来源的最大值。

    任一时间戳解析不了 → 返回 None（调用方按"活动未知"处理，**不回收**）——
    宁可漏杀，不可误杀。
    """
    srcs: list[Any] = []
    for row in con.execute(
        "SELECT COALESCE(completed_at, started_at) ts FROM chat_run_events WHERE workflow_id=?",
        (wf_id,),
    ).fetchall():
        srcs.append(row["ts"])
    for row in con.execute(
        "SELECT COALESCE(completed_at, started_at, NULL) ts FROM workflow_steps WHERE workflow_id=?",
        (wf_id,),
    ).fetchall():
        srcs.append(row["ts"])
    for row in con.execute(
        "SELECT last_progress_at, started_at, created_at FROM chat_messages WHERE session_id=?",
        (wf_id,),
    ).fetchall():
        srcs.extend([row["last_progress_at"], row["started_at"], row["created_at"]])
    row = con.execute(
        "SELECT updated_at, created_at FROM workflows WHERE id=?", (wf_id,)).fetchone()
    if row is not None:
        srcs.extend([row["updated_at"], row["created_at"]])

    parsed = [dt for dt in (_parse_ts(s) for s in srcs) if dt is not None]
    if not parsed:
        return None
    # 只有**全部**来源都可解析时才敢下结论；否则活动时间不可信。
    if any(s not in (None, "") and _parse_ts(s) is None for s in srcs):
        return None
    return max(parsed)


def reap_orphan_steps(con: sqlite3.Connection) -> list[dict[str, Any]]:
    """扫 C 类遗留：工作流不在 running，却有 `running` 步骤。

    ⚠️ 有活任务的工作流一律跳过：`execute_step` 里「步骤置 running」与
    「工作流置 running」是**两条语句**（services/workflow_service.py:440-441），
    定期扫描若恰好插在中间，就会把刚启动的正常步骤判成遗留。
    """
    rows = con.execute(
        "SELECT s.workflow_id, s.skill_name FROM workflow_steps s"
        " JOIN workflows w ON w.id = s.workflow_id"
        " WHERE s.status='running' AND w.status <> 'running'"
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        if wfs.is_running(r["workflow_id"]):
            continue
        con.execute(
            "UPDATE workflow_steps SET status='failed', completed_at=?, error_message=?"
            " WHERE workflow_id=? AND skill_name=? AND status='running'",
            (_now(), "工作流已不在运行，该步骤为遗留 running（无推进进程）；已标记为失败",
             r["workflow_id"], r["skill_name"]),
        )
        out.append({"workflow_id": r["workflow_id"], "skill_name": r["skill_name"],
                    "action": "orphan_step_running->failed"})
    if out:
        con.commit()
    return out


def reap_stale_workflows(
    con: sqlite3.Connection, *, stale_minutes: Optional[int] = None
) -> dict[str, Any]:
    """回收「超过阈值无事件推进」的 running 工作流（A + B 类）。"""
    threshold = STALE_RUNNING_MINUTES if stale_minutes is None else int(stale_minutes)
    now = datetime.now(timezone.utc)

    repaired: list[dict[str, Any]] = []
    stale_active: list[dict[str, Any]] = []
    unknown: list[str] = []

    for wf in con.execute(
        "SELECT id, current_step, created_at, updated_at FROM workflows WHERE status='running'"
    ).fetchall():
        wid = wf["id"]
        last = last_activity(con, wid)
        if last is None:
            unknown.append(wid)
            continue
        age_min = (now - last).total_seconds() / 60.0
        if age_min < threshold:
            continue

        detail = {"workflow_id": wid, "current_step": wf["current_step"],
                  "idle_minutes": round(age_min, 1)}

        if wfs.is_running(wid):
            # B 类：有活任务。只告警——不猜"大概跑完了"。
            stale_active.append(detail)
            log.warning("running 工作流长时间无推进（有活任务，不回收）: %s idle=%.1fmin step=%s",
                        wid[:12], age_min, wf["current_step"])
            continue

        # A 类：无后台任务 = 僵尸。
        for s in con.execute(
            "SELECT skill_name FROM workflow_steps WHERE workflow_id=? AND status='running'",
            (wid,),
        ).fetchall():
            con.execute(
                "UPDATE workflow_steps SET status='failed', completed_at=?, error_message=?"
                " WHERE workflow_id=? AND skill_name=?",
                (_now(),
                 "超过 %d 分钟无事件推进（无对应后台任务），判为僵尸并标记失败；请重新执行"
                 % threshold, wid, s["skill_name"]),
            )
            repaired.append({**detail, "skill_name": s["skill_name"],
                             "action": "stale_step_running->failed"})
        con.execute("UPDATE workflows SET status='failed', updated_at=? WHERE id=?",
                    (_now(), wid))
        repaired.append({**detail, "action": "stale_workflow_running->failed"})
        log.info("回收僵尸工作流: %s idle=%.1fmin step=%s", wid[:12], age_min,
                 wf["current_step"])

    if repaired:
        con.commit()
    if unknown:
        # 时间戳坏的库不猜——列出来让人工看一眼，而不是静默留在 running。
        log.warning("活动时间不可解析、暂不回收（需人工核查）: %s",
                    [w[:12] for w in unknown])
    return {"stale_minutes": threshold, "repaired": repaired,
            "stale_active": stale_active, "unknown_activity": unknown}


def run_startup_maintenance() -> dict[str, Any]:
    """启动自愈：僵尸工作流 + 遗留步骤。**任何异常都不允许拖垮启动。**"""
    result: dict[str, Any] = {"ok": True}
    con = get_db()
    try:
        # 一、既有函数（**只调不改**）：把所有「running 且无后台任务」的工作流置 failed。
        #    刚启动的进程必然没有任何后台任务，所以这一步等价于"重启后清空僵尸"。
        orphans = wfs.repair_orphans(con)
        result["repair_orphans"] = orphans
        # 二、`repair_orphans` 扫不到的遗留步骤（详见 reap_orphan_steps 注释）。
        orphan_steps = reap_orphan_steps(con)
        result["orphan_steps"] = orphan_steps
        result["reaped_workflows"] = len(orphans.get("repaired", []))
        result["reaped_steps"] = len(orphan_steps)
        log.info("启动自愈完成: 工作流回收=%d 遗留步骤回收=%d",
                 result["reaped_workflows"], result["reaped_steps"])
    except Exception:  # noqa: BLE001 —— 自愈失败也要能起服务
        result["ok"] = False
        log.exception("启动自愈失败（不影响服务启动）")
    finally:
        con.close()
    return result


async def _reap_loop() -> None:
    """定期心跳回收。间隔 `MODEMON_REAP_INTERVAL_SECONDS`（默认 300s）。"""
    while True:
        await asyncio.sleep(REAP_INTERVAL_SECONDS)
        try:
            con = get_db()
            try:
                res = reap_stale_workflows(con)
                orphan_steps = reap_orphan_steps(con)
            finally:
                con.close()
            if res["repaired"] or res["stale_active"] or orphan_steps:
                log.info("定期回收: 回收=%d 活任务但停滞=%d 遗留步骤=%d 判定阈值=%dmin",
                         len(res["repaired"]), len(res["stale_active"]),
                         len(orphan_steps), res["stale_minutes"])
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("定期回收失败（下一轮重试）")


# ---------------------------------------------------------------------------
# 数据库
# ---------------------------------------------------------------------------


def get_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = get_db()
    try:
        con.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        con.commit()
    finally:
        con.close()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    init_db()
    # 启动自愈：上一次进程留下的 running 全是僵尸（新进程没有任何后台任务）。
    run_startup_maintenance()
    reaper = asyncio.create_task(_reap_loop(), name="modemon-zombie-reaper")
    try:
        yield
    finally:
        reaper.cancel()
        with suppress(asyncio.CancelledError):
            await reaper
        log.info("服务已停止，日志: %s", LOG_DIR / "modemon.log")


app = FastAPI(
    title="modemon",
    version="0.1.0",
    description="数学建模竞赛智能体（骨架）",
    lifespan=lifespan,
)

# WebSocket：实时推送运行事件与检查点通知（WS 只是通知，状态以 REST 为准）
app.include_router(ws_router.router)

# 编辑器域：/api/editor/{wf_id}/*（文件读写 + 编译产物 + 编辑器元信息）
app.include_router(editor_router.router)


# ---------------------------------------------------------------------------
# 错误契约
# ---------------------------------------------------------------------------
# 前端需同时兼容 `{detail: "str"}` 与 `{detail: {message, code}}` 两种形态。


class ModemonError(Exception):
    def __init__(self, message: str, *, code: str = "", status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


@app.exception_handler(ModemonError)
async def _modemon_error_handler(_req: Request, exc: ModemonError) -> JSONResponse:
    detail: Any = {"message": exc.message, "code": exc.code} if exc.code else exc.message
    return JSONResponse(status_code=exc.status, content={"detail": detail})


@app.exception_handler(HTTPException)
async def _http_error_handler(_req: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict):
        return JSONResponse(status_code=exc.status_code, content={"detail": detail})
    return JSONResponse(status_code=exc.status_code, content={"detail": str(detail)})


# ---------------------------------------------------------------------------
# 依赖
# ---------------------------------------------------------------------------


def db_dep() -> sqlite3.Connection:
    con = get_db()
    try:
        yield con
    finally:
        con.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# 健康检查与模板
# ---------------------------------------------------------------------------


@app.get("/api/health", response_model=S.OkResponse)
def health() -> S.OkResponse:
    return S.OkResponse()


@app.get("/api/templates")
def list_templates() -> dict[str, Any]:
    """列出可用模板及其步骤数。

    ⚠️ 数据源是**模板注册表**（35 个值），不是 `S.TemplateType` 枚举。
    实测缺陷：原先循环枚举 → 只列出 9 个，而注册表有 35 个，
    于是 22 个竞赛模板**经 API 完全不可达**（`POST /api/workflows`
    会被 pydantic 拦成 422）。改走注册表后一处改动即全量生效，
    也避免了"枚举与注册表两份真相源"的漂移。
    """
    out = []
    for value in we.registry.values():
        tmpl = we.resolve_template(value)
        limit, mode = we.resolve_page_rule(value)
        out.append(
            {
                "template": value,
                "display_name": tmpl.display_name,
                "step_count": len(tmpl.sub_steps),
                "page_advisory": limit,
                "page_rule_mode": mode,
                "requires_ai_disclosure": we.registry.requires_ai_disclosure(value),
            }
        )
    return {"templates": out}


@app.get("/api/templates/{template}/resolve-steps")
def resolve_steps(template: str, docx_mode: bool = False) -> dict[str, Any]:
    """把模板解析为步骤列表——步骤的唯一真相源。

    创建工作流与运行时都调用它，以保证「模板步骤」与「数据库步骤」一一对应。
    """
    # 校验也走注册表（而不是 `S.TemplateType(...)` 枚举）——
    # 否则新模板会被枚举挡住，报成"未知模板"。
    if not we.registry.is_known(template):
        raise ModemonError(f"未知模板: {template}", code="UNKNOWN_TEMPLATE", status=404)
    tmpl = we.resolve_template(template, docx_mode=docx_mode)
    limit, mode = we.resolve_page_rule(template)
    return {
        "template": template,
        "display_name": tmpl.display_name,
        "page_advisory": limit,
        "page_rule_mode": mode,
        "steps": [
            {
                "skill_name": s.skill_name,
                "display_name": s.display_name,
                "output_files": list(s.output_files),
                "primary_output": s.primary_output,
                "has_checkpoint": s.has_checkpoint,
                "checkpoint_type": s.checkpoint_type,
                "min_size": we.min_size_for(s.skill_name),
                "inactivity_timeout": we.inactivity_timeout(s.skill_name),
                "required_companions": list(we.required_companions_for(s.skill_name)),
            }
            for s in tmpl.sub_steps
        ],
    }


# ---------------------------------------------------------------------------
# 工作流
# ---------------------------------------------------------------------------


@app.post("/api/workflows", response_model=S.WorkflowInfo, status_code=201)
def create_workflow(body: S.WorkflowCreate, con: sqlite3.Connection = Depends(db_dep)) -> S.WorkflowInfo:
    tmpl = we.resolve_template(body.template)
    wf_id = uuid.uuid4().hex
    created = _now()

    con.execute(
        "INSERT INTO workflows (id, template, title, params, status, enable_checkpoints, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (wf_id, body.template, body.title, json.dumps(body.params, ensure_ascii=False),
         S.WorkflowStatus.PENDING.value, int(body.enable_checkpoints), created, created),
    )
    for i, s in enumerate(tmpl.sub_steps):
        con.execute(
            "INSERT INTO workflow_steps"
            " (workflow_id, skill_name, display_name, step_order, status, has_checkpoint, checkpoint_type, output_files)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (wf_id, s.skill_name, s.display_name, i, S.StepStatus.PENDING.value,
             int(s.has_checkpoint), s.checkpoint_type,
             json.dumps(list(s.output_files), ensure_ascii=False)),
        )
    con.commit()

    limit, _ = we.resolve_page_rule(body.template)
    return S.WorkflowInfo(
        id=wf_id, template=body.template, title=body.title, params=body.params,
        status=S.WorkflowStatus.PENDING, current_step=None,
        steps=_load_steps(con, wf_id), created_at=created, updated_at=created,
        page_advisory=limit,
    )


def _load_steps(con: sqlite3.Connection, wf_id: str) -> list[S.StepInfo]:
    rows = con.execute(
        "SELECT skill_name, display_name, step_order, status, has_checkpoint,"
        " checkpoint_type, output_files, started_at, completed_at, error_message"
        " FROM workflow_steps WHERE workflow_id=? ORDER BY step_order",
        (wf_id,),
    ).fetchall()
    return [
        S.StepInfo(
            skill_name=r["skill_name"], display_name=r["display_name"],
            step_order=r["step_order"], status=S.StepStatus(r["status"]),
            has_checkpoint=bool(r["has_checkpoint"]), checkpoint_type=r["checkpoint_type"],
            output_files=_loads(r["output_files"], []),
            started_at=r["started_at"], completed_at=r["completed_at"],
            error_message=r["error_message"],
        )
        for r in rows
    ]


def _get_workflow(con: sqlite3.Connection, wf_id: str) -> sqlite3.Row:
    row = con.execute("SELECT * FROM workflows WHERE id=?", (wf_id,)).fetchone()
    if row is None:
        raise ModemonError(f"工作流不存在: {wf_id}", code="WORKFLOW_NOT_FOUND", status=404)
    return row


@app.get("/api/workflows", response_model=list[S.WorkflowInfo])
def list_workflows(con: sqlite3.Connection = Depends(db_dep)) -> list[S.WorkflowInfo]:
    out = []
    for r in con.execute("SELECT * FROM workflows ORDER BY created_at DESC").fetchall():
        limit, _ = we.resolve_page_rule(r["template"])
        out.append(
            S.WorkflowInfo(
                # template 直传字符串：改用注册表后，库里可能存着枚举之外的
                # 新模板值（35 个中的任意一个），再走 S.TemplateType() 会抛 ValueError。
                id=r["id"], template=r["template"], title=r["title"],
                params=_loads(r["params"], {}), status=S.WorkflowStatus(r["status"]),
                current_step=r["current_step"], steps=_load_steps(con, r["id"]),
                created_at=r["created_at"], updated_at=r["updated_at"],
                page_advisory=limit,
            )
        )
    return out


@app.get("/api/workflows/{wf_id}", response_model=S.WorkflowInfo)
def get_workflow(wf_id: str, con: sqlite3.Connection = Depends(db_dep)) -> S.WorkflowInfo:
    r = _get_workflow(con, wf_id)
    limit, _ = we.resolve_page_rule(r["template"])
    return S.WorkflowInfo(
        id=r["id"], template=r["template"], title=r["title"],
        params=_loads(r["params"], {}), status=S.WorkflowStatus(r["status"]),
        current_step=r["current_step"], steps=_load_steps(con, wf_id),
        created_at=r["created_at"], updated_at=r["updated_at"], page_advisory=limit,
    )


@app.delete("/api/workflows/{wf_id}", response_model=S.OkResponse)
def delete_workflow(wf_id: str, con: sqlite3.Connection = Depends(db_dep)) -> S.OkResponse:
    _get_workflow(con, wf_id)
    con.execute("DELETE FROM workflows WHERE id=?", (wf_id,))
    con.commit()
    return S.OkResponse()


# ---------------------------------------------------------------------------
# 检查点
# ---------------------------------------------------------------------------


@app.get("/api/workflows/{wf_id}/checkpoints/current", response_model=Optional[S.CheckpointView])
def current_checkpoint(wf_id: str, con: sqlite3.Connection = Depends(db_dep)) -> Optional[S.CheckpointView]:
    """返回当前待处理检查点。

    `remaining_seconds` 是**契约字段**：前端据此判断后端是否为旧版逻辑。
    """
    _get_workflow(con, wf_id)
    cp = wfs.pending_checkpoint(con, wf_id)
    if cp is None:
        return None
    return S.CheckpointView(
        checkpoint_id=str(cp["checkpoint_id"]), workflow_id=wf_id,
        step_name=cp["step_name"], checkpoint_type=cp["checkpoint_type"],
        data=cp["data"], status=cp["status"],
        remaining_seconds=cp["remaining_seconds"],
    )


@app.post("/api/workflows/{wf_id}/checkpoints/resolve", response_model=S.CheckpointView)
async def resolve_checkpoint(
    wf_id: str,
    body: S.CheckpointResponse,
    con: sqlite3.Connection = Depends(db_dep),
) -> S.CheckpointView:
    """解决检查点并决定是否继续。

    - `approve` / `select` / `feedback` → 标记步骤完成并**继续推进**
    - `stop` → 标记步骤完成但**保持暂停**（用户主动停在检查点）

    契约要求：成功时返回体必须含 `status: 'resolved'`，
    否则前端会判定后端仍是旧版逻辑。
    """
    _get_workflow(con, wf_id)
    try:
        result = await wfs.resolve_checkpoint(
            con, workflow_id=wf_id, action=body.action,
            checkpoint_id=int(body.checkpoint_id) if body.checkpoint_id else None,
            data=body.data,
        )
    except LookupError as exc:
        raise ModemonError(str(exc), code="NO_PENDING_CHECKPOINT", status=404) from None
    except ValueError as exc:
        raise ModemonError(str(exc), code="INVALID_CHECKPOINT_ACTION", status=422) from None

    row = con.execute("SELECT * FROM checkpoints WHERE id=?",
                      (result["checkpoint_id"],)).fetchone()
    return S.CheckpointView(
        checkpoint_id=str(row["id"]), workflow_id=wf_id,
        step_name=row["step_name"], checkpoint_type=row["checkpoint_type"],
        data=_loads(row["data"], {}), status="resolved", remaining_seconds=None,
    )


# ---------------------------------------------------------------------------
# 对话工作台（最小闭环）
# ---------------------------------------------------------------------------


@app.post("/api/workflows/{wf_id}/chat/say", status_code=202)
def chat_say(
    wf_id: str,
    body: S.SayIn,
    con: sqlite3.Connection = Depends(db_dep),
) -> dict[str, Any]:
    """用户发言。

    `turn_id` 为**幂等键**：同一 turn_id 重复提交直接返回既有结果，
    避免网络重试把同一句话重复喂给主会话。
    """
    _get_workflow(con, wf_id)
    if body.turn_id:
        dup = con.execute(
            "SELECT id FROM chat_messages WHERE client_turn_id=? AND session_id=?",
            (body.turn_id, wf_id),
        ).fetchone()
        if dup:
            return {"ok": True, "message_id": dup["id"], "deduplicated": True}

    cur = con.execute(
        "INSERT INTO chat_messages (session_id, role, content, client_turn_id, turn_id, status, item_kind)"
        " VALUES (?,?,?,?,?,?,?)",
        (wf_id, "user", body.text, body.turn_id, body.turn_id, "done", "user_message"),
    )
    con.commit()
    return {"ok": True, "message_id": cur.lastrowid, "deduplicated": False}


@app.post("/api/internal/chat/propose", status_code=201)
def chat_propose(
    body: S.ProposeIn,
    con: sqlite3.Connection = Depends(db_dep),
) -> dict[str, Any]:
    """MCP 子进程回调产生执行提议。

    MCP 是独立进程，无法共享进程内状态，因此当前轮次约束（`execution_scope`
    / `focus_target`）由后端从 `chat_sessions` 读取并**硬性**约束提议，
    而不是信任调用方传入的值——否则「仅对话」模式可能被扩成完整步骤执行。
    """
    sess = con.execute(
        "SELECT active_turn_mode, active_focus_target FROM chat_sessions WHERE workflow_id=?",
        (body.workflow_id,),
    ).fetchone()

    scope = body.execution_scope
    focus = body.focus_target
    if sess is not None:
        if sess["active_turn_mode"] == "conversation":
            raise ModemonError(
                "当前轮次为「仅对话」模式，不允许产生执行提议",
                code="PROPOSE_BLOCKED_BY_TURN_MODE", status=409,
            )
        if sess["active_focus_target"]:
            scope = "focused"
            focus = sess["active_focus_target"]

    cur = con.execute(
        "INSERT INTO chat_messages (session_id, role, content, skill_name, instruction, status,"
        " item_kind, execution_scope, focus_target, operation_kind, confirmed_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,NULL)",
        # content 是 NOT NULL：提议卡片的可见正文取 raw_text，
        # 缺省回退到 instruction（整理后的执行要点）。
        (body.session_id, "assistant", body.raw_text or body.instruction,
         body.skill, body.instruction, "proposed",
         "task", scope, focus, body.operation_kind or "run_step"),
    )
    con.commit()
    return {"ok": True, "message_id": cur.lastrowid, "execution_scope": scope, "focus_target": focus}


@app.post("/api/workflows/{wf_id}/chat/messages/{msg_id}/confirm")
def confirm_message(
    wf_id: str,
    msg_id: int,
    body: S.ProposalEditIn = Body(...),
    con: sqlite3.Connection = Depends(db_dep),
) -> dict[str, Any]:
    """确认执行——**后端硬闸**。

    两道校验都必须在后端做（前端隐藏按钮挡不住双击、重发、直调接口）：
    1. `confirmed_at` 是否为空（是否仍停在提议卡片）
    2. `revision` 是否与库中一致（CAS，防并发跑旧指令）
    """
    row = con.execute(
        "SELECT * FROM chat_messages WHERE id=? AND session_id=?", (msg_id, wf_id)
    ).fetchone()
    if row is None:
        raise ModemonError("提议不存在", code="PROPOSAL_NOT_FOUND", status=404)
    if row["status"] != "proposed":
        raise ModemonError(
            f"提议状态为 {row['status']}，不可确认", code="PROPOSAL_NOT_PENDING", status=409
        )
    if int(row["proposal_revision"]) != int(body.revision):
        raise ModemonError(
            "提议已被修改，请刷新后重试（revision 不匹配）",
            code="REVISION_CONFLICT", status=409,
        )

    con.execute(
        "UPDATE chat_messages SET instruction=?, execution_scope=?, focus_target=?,"
        " model_preset_id=?, effort=?, confirmed_at=?, status='queued',"
        " proposal_revision=proposal_revision+1 WHERE id=?",
        (body.instruction, body.execution_scope or row["execution_scope"],
         body.focus_target if body.focus_target is not None else row["focus_target"],
         body.model_preset_id, body.effort, _now(), msg_id),
    )
    con.commit()
    return {"ok": True, "message_id": msg_id, "status": "queued"}


# ---------------------------------------------------------------------------
# 执行：单步 / 连续（到检查点为止）/ 运行事件回放
# ---------------------------------------------------------------------------


@app.get("/api/runtimes")
def list_runtimes() -> dict[str, Any]:
    """列出可用的 agent 运行时及其**如实声明的能力**。

    前端据此提示用户"当前运行时做不到什么"，而不是让约束静默失效。
    """
    from services import agent_runtime as ar  # 局部导入，避免无谓的启动开销

    return {"runtimes": ar.describe_all(),
            "default_priority": list(ar.DEFAULT_PRIORITY)}


@app.post("/api/workflows/{wf_id}/steps/{skill_name}/run", status_code=202)
async def run_one_step(
    wf_id: str,
    skill_name: str,
    workspace: str = Query(..., description="工作区绝对路径"),
    runtime: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    effort: Optional[str] = Query(None),
    template: str = Query("comp_zh"),
    max_budget_usd: float = Query(1.0),
    strict: bool = Query(False),
    extra_prompt: str = Query(""),
    permission_mode: Optional[str] = Query(
        None, description="权限模式；求解类步骤需 bypassPermissions 才能执行解释器"),
    con: sqlite3.Connection = Depends(db_dep),
) -> dict[str, Any]:
    """启动单步执行（**后台任务**），立即返回 202 + run_id。

    为什么不是同步等待：实测中客户端在长步骤中途断开会让协程被取消，
    步骤永久停在 `running`。执行周期不应绑定在 HTTP 请求上。
    进度通过 WebSocket 实时推送，权威状态用 REST 查询。
    """
    wf = _get_workflow(con, wf_id)
    if wfs.is_running(wf_id):
        raise ModemonError("该工作流已有步骤在运行", code="ALREADY_RUNNING", status=409)
    row = con.execute(
        "SELECT skill_name FROM workflow_steps WHERE workflow_id=? AND skill_name=?",
        (wf_id, skill_name)).fetchone()
    if row is None:
        raise ModemonError(f"工作流 {wf_id} 没有步骤 {skill_name}",
                           code="STEP_NOT_FOUND", status=404)
    run_id = wfs.start_step_run(
        workflow_id=wf_id, skill_name=skill_name, workspace=Path(workspace),
        template=template or wf["template"], runtime=runtime, model=model,
        effort=effort, max_budget_usd=max_budget_usd, strict=strict,
        extra_prompt=extra_prompt,
        permission_mode=permission_mode or "acceptEdits",
    )
    return {"ok": True, "accepted": True, "run_id": run_id,
            "workflow_id": wf_id, "skill_name": skill_name,
            "note": "执行已后台化；请通过 WebSocket 或 REST 查询进度"}


@app.get("/api/runs")
def list_active_runs() -> dict[str, Any]:
    """当前在跑的后台任务。"""
    return {"active": wfs.active_runs()}


@app.post("/api/workflows/{wf_id}/repair")
def repair_workflow(wf_id: str, con: sqlite3.Connection = Depends(db_dep)) -> dict[str, Any]:
    """修复僵尸状态：库里 running 但没有对应后台任务。

    对应蓝方的心跳自愈机制。**不猜测"大概跑完了"**——
    一律标记为失败并说明原因，避免把未验证的中间态当成成功。
    """
    _get_workflow(con, wf_id)
    res = wfs.repair_orphans(con, wf_id)
    log.info("/repair 手动回收: wf=%s repaired=%d active_runs=%s",
             wf_id[:12], res.get("count", 0), res.get("active_runs"))
    return res


@app.post("/api/workflows/{wf_id}/run", status_code=202)
async def run_workflow_until_blocked(
    wf_id: str,
    workspace: str = Query(...),
    runtime: Optional[str] = Query(None),
    max_steps: int = Query(5, ge=1, le=20),
    max_budget_usd: float = Query(1.0),
    extra_prompt: str = Query(""),
    con: sqlite3.Connection = Depends(db_dep),
) -> dict[str, Any]:
    """后台启动连续执行，直到完成 / 失败 / **遇到检查点暂停** / 达到步数上限。

    与单步执行同理：返回 202，进度由 WebSocket 推送，
    权威状态用 `GET /api/workflows/{id}` 查询。
    """
    wf = _get_workflow(con, wf_id)
    if wfs.is_running(wf_id):
        raise ModemonError("该工作流已有任务在运行", code="ALREADY_RUNNING", status=409)
    run_id = wfs.start_batch_run(
        workflow_id=wf_id, workspace=Path(workspace), max_steps=max_steps,
        runtime=runtime, template=wf["template"], max_budget_usd=max_budget_usd,
        extra_prompt=extra_prompt,
    )
    return {"ok": True, "accepted": True, "run_id": run_id, "workflow_id": wf_id,
            "max_steps": max_steps,
            "note": "已后台启动；请通过 WebSocket 或 REST 查询进度"}


@app.get("/api/workflows/{wf_id}/run-events")
def list_run_events(
    wf_id: str,
    message_id: Optional[int] = Query(None),
    all_messages: bool = Query(False, description="返回该工作流全部步骤的事件（诊断用）"),
    limit: int = Query(500, ge=1, le=5000),
    con: sqlite3.Connection = Depends(db_dep),
) -> dict[str, Any]:
    """回放运行事件（已脱敏）。

    这是 WS 断线后重建过程卡片的**权威数据源**——
    WS 只负责实时，历史一律走这里。

    `all_messages=true` 时返回**该工作流所有步骤**的事件。
    实测需要：默认只返回最近一条 task 的事件，
    多步流水线出问题时早期步骤的失败原因就查不到了。
    """
    _get_workflow(con, wf_id)
    store = re_mod.RunEventStore(con)

    if all_messages:
        rows = con.execute(
            "SELECT event_id, run_id, sequence, kind, state, title, safe_detail,"
            " public_artifact_path, started_at, completed_at, evidence_json, message_id"
            " FROM chat_run_events WHERE workflow_id=?"
            " ORDER BY message_id, sequence LIMIT ?",
            (wf_id, limit),
        ).fetchall()
        events = []
        for r in rows:
            events.append({
                "event_id": r["event_id"], "run_id": r["run_id"],
                "message_id": r["message_id"],
                "sequence": r["sequence"], "kind": r["kind"], "state": r["state"],
                "title": r["title"], "safe_detail": r["safe_detail"],
                "public_artifact_path": r["public_artifact_path"],
                "started_at": r["started_at"], "completed_at": r["completed_at"],
                "evidence": json.loads(r["evidence_json"] or "{}"),
            })
        return {"workflow_id": wf_id, "message_id": None, "events": events,
                "count": len(events), "all_messages": True}

    if message_id is None:
        row = con.execute(
            "SELECT id FROM chat_messages WHERE session_id=? AND item_kind='task'"
            " ORDER BY id DESC LIMIT 1", (wf_id,)).fetchone()
        message_id = row["id"] if row else None
    events = store.list_for_message(message_id, limit=limit) if message_id else []
    return {"workflow_id": wf_id, "message_id": message_id, "events": events,
            "count": len(events), "all_messages": False}


# ---------------------------------------------------------------------------
# 成文链：排版规格 / 论文装配 / 去 AI 味 / LaTeX / DOCX
# ---------------------------------------------------------------------------


@app.get("/api/tex-runtime")
def tex_runtime_status() -> dict[str, Any]:
    """TeX 运行时状态（对应用户可见的三态）。

    如实报告 `ready | fresh | missing`——随包 TeXLive 往往是**未初始化的 MiKTeX**，
    直接编译会要求先完成 setup。这与蓝方 `latex:get-status` 的语义一致。
    """
    from services import tex_runtime as tx

    return tx.resolve_tex_runtime().as_dict()


@app.get("/api/typography/{template}")
def typography_for(template: str) -> dict[str, Any]:
    """返回该模板实际使用的排版规格（供前端展示与校对）。"""
    from services import typography as ty

    p = ty.resolve_profile(template)
    return {
        "name": p.name, "source": p.source, "style": p.as_dict(),
        "page_limit": ty.PAGE_LIMIT.get(template),
        "chars_per_page_zh": ty.CHARS_PER_PAGE_ZH,
        "chars_per_page_en": ty.CHARS_PER_PAGE_EN,
        "warnings": p.warnings,
    }


def _workspace_snapshot(ws: Path) -> dict[str, Any]:
    """导出失败时的现场快照。

    为什么必须记：上一轮导出报过 **HTTP 500 且事后无法定位**（reports/26 §4.3）——
    根因就是当时**什么现场都没留下**。这里把决定成败的那几个事实一次记全：
    文件是否存在、大小、mtime、**可读/可写**（Windows 上 `PermissionError [Errno 13]`
    是真实存在的 500 路径，见下方测试 `test_export_survives_readonly_tex`）。
    """
    snap: dict[str, Any] = {"exists": ws.is_dir()}
    try:
        paper = ws / "paper"
        snap["paper_dir"] = paper.is_dir()
        snap["figures_dir"] = (ws / "figures").is_dir()
        files: list[dict[str, Any]] = []
        for sub in (paper, ws / "figures"):
            if sub.is_dir():
                for p in sorted(sub.rglob("*")):
                    if p.is_file():
                        st = p.stat()
                        files.append({
                            "path": str(p.relative_to(ws)),
                            "bytes": st.st_size,
                            "mtime": datetime.fromtimestamp(
                                st.st_mtime, timezone.utc).isoformat(),
                            "readable": os.access(p, os.R_OK),
                            "writable": os.access(p, os.W_OK),
                        })
        snap["file_count"] = len(files)
        snap["files"] = files[:50]
        sections = paper / "sections"
        snap["sections"] = (sorted(p.name for p in sections.glob("*.md"))
                            if sections.is_dir() else [])
        res = ws / "figures" / "all_results.json"
        snap["all_results"] = ({
            "bytes": res.stat().st_size, "writable": os.access(res, os.W_OK),
        } if res.is_file() else None)
        main_md = paper / "main.md"
        snap["main_md"] = main_md.is_file()
    except Exception as exc:  # noqa: BLE001 —— 快照自己失败也不能再抛
        snap["snapshot_error"] = repr(exc)
    return snap


@app.post("/api/paper/export")
def export_paper(body: S.PaperExportBody) -> dict[str, Any]:
    """装配论文并导出。

    ★ **表格由程序从 `all_results.json` 生成，不经过模型**——
    模型誊抄数字会出错，而论文里的数字错了就是硬伤。

    ★ 失败一律转成**结构化错误 + 诊断编号**，并落盘 workspace 快照与 traceback：
    `reports/26 §4.3` 那次 500 之所以至今查不动，就是因为当时没有任何现场记录。
    """
    from services import docx_export as dx
    from services import latex_export as lx

    ws = Path(body.workspace)
    if not ws.is_dir():
        raise ModemonError(f"工作区不存在: {ws}", code="WORKSPACE_NOT_FOUND", status=404)

    diag_id = uuid.uuid4().hex[:12]
    try:
        out: dict[str, Any] = {"workspace": str(ws), "template": body.template,
                               "results": {}}

        if "latex" in body.formats:
            r = lx.export_latex(ws, template=body.template, language=body.language,
                                title=body.title, abstract=body.abstract,
                                keywords=body.keywords, compile_pdf=body.compile_pdf)
            out["results"]["latex"] = r.as_dict()

        if "docx" in body.formats:
            out["results"]["docx"] = dx.export_docx(
                ws, template=body.template, title=body.title,
                abstract=body.abstract, keywords=body.keywords)

        out["ok"] = bool(out["results"]) and all(
            v.get("ok") for v in out["results"].values())
        return out
    except Exception as exc:
        log.exception(
            "论文导出失败 diag=%s workspace=%s formats=%s compile_pdf=%s\n"
            "workspace 快照: %s",
            diag_id, ws, body.formats, body.compile_pdf,
            json.dumps(_workspace_snapshot(ws), ensure_ascii=False))
        raise ModemonError(
            f"论文导出失败：{type(exc).__name__}: {exc}"
            f"（诊断编号 {diag_id}，详见 {LOG_DIR / 'modemon.log'}）",
            code="PAPER_EXPORT_FAILED", status=500,
        ) from exc


@app.get("/api/paper/lint")
def lint_paper_endpoint(
    workspace: str = Query(..., description="工作区绝对路径"),
    template: str = Query("comp_cumcm"),
) -> dict[str, Any]:
    """对工作区论文做去 AI 味检查（含图题规则）。

    可机械判定的部分在执行后强制检查——**写在提示里不等于一定做到**。
    """
    from services import deai_lint as dl
    from services import paper_build as pb

    ws = Path(workspace)
    if not ws.is_dir():
        raise ModemonError(f"工作区不存在: {ws}", code="WORKSPACE_NOT_FOUND", status=404)
    doc, notes = pb.build_paper(ws, template=template)
    manifest = pb.parse_figure_manifest(ws)
    rep = dl.lint_paper(ws, sections=[s.body for s in doc.sections],
                        manifest_captions=[m.name for m in manifest])
    result = rep.as_dict()
    result["notes"] = notes
    return result


# ---------------------------------------------------------------------------
# 设置与模型预设
# ---------------------------------------------------------------------------


@app.get("/api/settings")
def get_settings(con: sqlite3.Connection = Depends(db_dep)) -> dict[str, Any]:
    rows = con.execute("SELECT key, value FROM settings").fetchall()
    return {"settings": {r["key"]: r["value"] for r in rows}}


@app.put("/api/settings", response_model=S.OkResponse)
def put_settings(body: S.SettingsUpdate, con: sqlite3.Connection = Depends(db_dep)) -> S.OkResponse:
    for k, v in body.settings.items():
        con.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?,?,?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (k, v, _now()),
        )
    con.commit()
    return S.OkResponse()


@app.get("/api/settings/presets", response_model=list[S.PresetView])
def list_presets(con: sqlite3.Connection = Depends(db_dep)) -> list[S.PresetView]:
    """列出模型预设。**绝不回传 api_key**，只回传是否已配置。"""
    rows = con.execute("SELECT * FROM model_presets ORDER BY created_at").fetchall()
    return [
        S.PresetView(
            id=r["id"], name=r["name"], model_id=r["model_id"],
            provider_id=r["provider_id"], context_mode=r["context_mode"],
            has_api_key=bool(r["api_key"]),
        )
        for r in rows
    ]


@app.post("/api/settings/presets", response_model=S.PresetView, status_code=201)
def create_preset(body: S.PresetBody, con: sqlite3.Connection = Depends(db_dep)) -> S.PresetView:
    pid = uuid.uuid4().hex
    con.execute(
        "INSERT INTO model_presets (id, name, model_id, api_key, context_mode) VALUES (?,?,?,?,?)",
        (pid, body.name, body.model_id, body.api_key, body.context_mode),
    )
    con.commit()
    return S.PresetView(
        id=pid, name=body.name, model_id=body.model_id,
        context_mode=body.context_mode, has_api_key=bool(body.api_key),
    )


# ---------------------------------------------------------------------------
# 国赛 AI 使用申报门禁
# ---------------------------------------------------------------------------


def _requires_disclosure(con: sqlite3.Connection, wf_id: str) -> bool:
    row = con.execute("SELECT template FROM workflows WHERE id=?", (wf_id,)).fetchone()
    return row is not None and row["template"] == S.TemplateType.COMP_CUMCM.value


@app.get("/api/workflows/{wf_id}/ai-disclosure", response_model=S.AiDisclosure)
def get_disclosure(wf_id: str, con: sqlite3.Connection = Depends(db_dep)) -> S.AiDisclosure:
    _get_workflow(con, wf_id)
    row = con.execute("SELECT * FROM ai_disclosures WHERE workflow_id=?", (wf_id,)).fetchone()
    if row is None:
        return S.AiDisclosure()
    return S.AiDisclosure(
        records=[S.ToolUseRecord(**r) for r in _loads(row["records_json"], [])],
        verified_by_team=bool(row["verified_by_team"]),
    )


@app.put("/api/workflows/{wf_id}/ai-disclosure", response_model=S.AiDisclosure)
def put_disclosure(
    wf_id: str, body: S.AiDisclosure, con: sqlite3.Connection = Depends(db_dep)
) -> S.AiDisclosure:
    """保存 AI 使用记录。

    国赛要求申报 1–5 条真实记录。这里在**保存时**校验条目数，
    在**开始成文步骤时**校验是否已核验（见 `start_workflow`）。
    """
    _get_workflow(con, wf_id)
    if body.records and not (1 <= len(body.records) <= 5):
        raise ModemonError(
            "国赛 AI 使用记录须为 1–5 条", code="AI_DISCLOSURE_COUNT_INVALID", status=422
        )
    con.execute(
        "INSERT INTO ai_disclosures (workflow_id, records_json, verified_by_team, verified_at, updated_at)"
        " VALUES (?,?,?,?,?) ON CONFLICT(workflow_id) DO UPDATE SET"
        " records_json=excluded.records_json, verified_by_team=excluded.verified_by_team,"
        " verified_at=excluded.verified_at, updated_at=excluded.updated_at",
        (wf_id, json.dumps([r.model_dump() for r in body.records], ensure_ascii=False),
         int(body.verified_by_team), _now() if body.verified_by_team else None, _now()),
    )
    con.commit()
    return body


@app.post("/api/workflows/{wf_id}/start", response_model=S.OkResponse)
def start_workflow(wf_id: str, con: sqlite3.Connection = Depends(db_dep)) -> S.OkResponse:
    """启动工作流。

    **国赛门禁**：`comp_cumcm` 模板必须已填写 AI 使用记录并完成参赛队核验，
    否则拒绝启动。这道闸在后端，前端隐藏按钮挡不住直调接口。
    """
    row = _get_workflow(con, wf_id)
    if row["template"] == S.TemplateType.COMP_CUMCM.value:
        d = con.execute("SELECT * FROM ai_disclosures WHERE workflow_id=?", (wf_id,)).fetchone()
        if d is None or not _loads(d["records_json"], []):
            raise ModemonError(
                "国赛（CUMCM）要求申报 AI 使用情况：请先填写 1–5 条 AI 工具使用记录",
                code="AI_DISCLOSURE_REQUIRED", status=409,
            )
        if not d["verified_by_team"]:
            raise ModemonError(
                "AI 使用记录尚未经参赛队人工核验确认",
                code="AI_DISCLOSURE_NOT_VERIFIED", status=409,
            )
    if row["status"] == S.WorkflowStatus.RUNNING.value:
        raise ModemonError("工作流已在运行", code="ALREADY_RUNNING", status=409)

    con.execute(
        "UPDATE workflows SET status=?, updated_at=? WHERE id=?",
        (S.WorkflowStatus.RUNNING.value, _now(), wf_id),
    )
    con.commit()
    return S.OkResponse()


@app.get("/api/workflows/{wf_id}/workspace/health")
def workspace_health(
    wf_id: str,
    workspace: str = Query(..., description="工作区绝对路径"),
    con: sqlite3.Connection = Depends(db_dep),
) -> dict[str, Any]:
    """对当前步骤跑质量门，返回结构化结果。

    响应区分 `ok` / `unavailable`，避免把「检查器不可用」当成「产出不合格」。
    """
    wf = _get_workflow(con, wf_id)
    ws = Path(workspace)
    steps = _load_steps(con, wf_id)
    results = []
    for s in steps:
        if s.status != S.StepStatus.RUNNING:
            continue
        primary = we.check_primary_output(ws, s.skill_name)
        comps = we.check_step_companions(ws, s.skill_name)
        pages, chars = we.check_paper_body_pages(ws, language="zh")
        results.append(
            {
                "skill_name": s.skill_name,
                "primary_output_ok": primary.ok,
                "primary_output_reason": primary.reason,
                "companions_ok": comps.ok,
                "missing_companions": list(comps.missing),
                "body_chars": chars,
                "body_pages_estimate": pages,
                "unavailable": False,
            }
        )
    return {"workflow_id": wf_id, "template": wf["template"], "steps": results}


if __name__ == "__main__":
    import uvicorn  # noqa: PLC0415

    uvicorn.run(app, host="127.0.0.1", port=8770)


# ---------------------------------------------------------------------------
# 前端（无构建步骤：原生 HTML + ES module，由后端同源托管）
# ---------------------------------------------------------------------------
# 刻意不引入打包工具：骨架阶段用单文件前端即可形成闭环，
# 也让"后端同源托管"这一部署形态从第一天就被验证。

if FRONTEND_DIR.is_dir():
    @app.get("/")
    def _index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
