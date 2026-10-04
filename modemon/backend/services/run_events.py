"""运行事件的持久化与**脱敏**。

为什么必须先脱敏
----------------
蓝方在 schema 注释里写死了一条约束：

    执行剧场 V2：持久化的是结构化、脱敏、可验证的生命周期事件。
    原始 stream-json、命令、Skill 内容、密钥和私有目录**永不进入这张表**。

这条约束是对的，原因有三：
  1. 工具调用的 input 里可能带 API Key、私有文件路径、用户原话；
  2. 模型的 thinking 是过程草稿，落库等于把未审内容变成"事实记录"；
  3. 库里一旦有敏感数据，导出、备份、工单附件全都会把它带出去。

因此本模块采用**白名单 + 主动改写**，而不是"存了再想办法擦"。
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from . import agent_runtime as ar

# --- 脱敏规则 --------------------------------------------------------------

#: 形如 sk-xxx / tp-xxx / Bearer xxx / 32+ 位 hex 的凭据
_CREDENTIAL_RE = re.compile(
    r"(?i)\b(?:sk|tp|pk|ghp|gho|glpat|xoxb)-[A-Za-z0-9_\-]{8,}"
    r"|\bBearer\s+[A-Za-z0-9._\-]{8,}"
    r"|\b[A-Fa-f0-9]{32,}\b"
)

#: 绝对路径（Windows 盘符 / UNC / POSIX 常见根）
_ABS_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/][^\s'\"<>|]*)"          # C:\... or C:/...
    r"|(?:\\\\[^\s'\"<>|]+)"                     # \\server\share
    r"|(?<![\w.])/(?:home|Users|root|var|etc|opt|tmp)/[^\s'\"<>|]*"
)

#: 允许持久化的字段集合（白名单）
#:
#: 刻意**不含 `session_id`**：会话标识属于 `chat_sessions.cli_session_id` 专用列，
#: 混进事件表会让"哪次运行用了哪个会话"出现两个真相源。
#: 度量类字段（花费/token/退出码）是安全的，予以保留。
ALLOWED_EVENT_KEYS = frozenset({
    "phase", "state", "skill_name", "artifact", "bytes", "duration_s",
    "tool_name", "code", "count", "index", "total",
    "cost_usd", "tokens_in", "tokens_out", "exit_code",
})

#: 明确排除的字段（即使在白名单里也会被剔除）——会话标识只存专用列
EXCLUDED_EVENT_KEYS = frozenset({"session_id", "cli_session_id"})

#: 工具输入一律不落库——只保留工具名
NEVER_PERSIST = frozenset({
    "input", "command", "cmd", "prompt", "content", "thinking",
    "text", "api_key", "token", "secret", "env",
})

#: **自定义事件**（非 agent RunEvent）的字段白名单。
#:
#: ⚠️ 为什么需要单独一套：`ALLOWED_EVENT_KEYS` 是给 agent 运行时事件用的，
#: 而审计/渲染这类自定义事件的载荷字段完全不同。直接复用会把
#: `verdict` / `issues` / `rendered` 全部剥光——实测中事件确实落库了，
#: 但 `evidence_json` 成了 `{}`，等于**只留了个空壳**。
CUSTOM_EVENT_KEYS = frozenset({
    "workflow_id", "triggered_by", "skill_used", "verdict", "ok",
    "issues", "notes", "rendered", "skipped", "errors",
    "includes_tex", "upstream", "repo", "license",
    "spec", "png", "svg", "caption",
})

MAX_SAFE_DETAIL = 400


@dataclass
class RunEventRecord:
    event_id: str
    workflow_id: str
    message_id: int
    run_id: str
    sequence: int
    kind: str
    state: str
    title: str
    safe_detail: str = ""
    public_artifact_path: Optional[str] = None
    started_at: str = ""
    completed_at: Optional[str] = None
    evidence: dict[str, Any] = field(default_factory=dict)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def redact(text: str, workspace: Optional[Path] = None) -> str:
    """把一段文本改写为**可安全入库**的形式。

    - 凭据 → `«redacted»`
    - 工作区内的绝对路径 → 相对路径（相对路径是产物标识，本身安全）
    - 工作区外的绝对路径 → `«path»`
    - 截断到 `MAX_SAFE_DETAIL`
    """
    if not text:
        return ""

    def _path_sub(m: re.Match[str]) -> str:
        raw = m.group(0)
        if workspace:
            try:
                p = Path(raw)
                rel = p.resolve().relative_to(Path(workspace).resolve())
                return rel.as_posix()
            except (ValueError, OSError):
                pass
        # 保留文件名做定位线索，但不暴露目录
        name = Path(raw.rstrip("\\/")).name
        return f"«path:{name}»" if name else "«path»"

    out = _CREDENTIAL_RE.sub("«redacted»", text)
    out = _ABS_PATH_RE.sub(_path_sub, out)
    if len(out) > MAX_SAFE_DETAIL:
        out = out[:MAX_SAFE_DETAIL] + "…"
    return out


def sanitize_custom_evidence(data: dict[str, Any],
                             workspace: Optional[Path] = None) -> dict[str, Any]:
    """按**自定义事件**白名单过滤（审计 / 图表渲染等）。

    与 `sanitize_evidence` 的区别只在白名单不同：后者是给 agent 运行时
    事件用的，字段完全不同。直接复用会把自定义载荷剥成空壳。

    仍然保留原有的安全约束：`NEVER_PERSIST` 与 `EXCLUDED_EVENT_KEYS`
    一律剔除，字符串走 `redact`。
    """
    out: dict[str, Any] = {}
    for k, v in (data or {}).items():
        if k in NEVER_PERSIST or k in EXCLUDED_EVENT_KEYS or k not in CUSTOM_EVENT_KEYS:
            continue
        if isinstance(v, str):
            out[k] = redact(v, workspace)
        elif isinstance(v, (int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, (list, tuple)) and len(v) <= 50:
            items = []
            for x in v:
                if isinstance(x, dict):
                    items.append(sanitize_custom_evidence(x, workspace))
                elif isinstance(x, str):
                    items.append(redact(x, workspace))
                else:
                    items.append(x)
            out[k] = items
        elif isinstance(v, dict):
            out[k] = sanitize_custom_evidence(v, workspace)
    return out


def sanitize_evidence(data: dict[str, Any], workspace: Optional[Path] = None) -> dict[str, Any]:
    """按白名单过滤事件附加数据。"""
    out: dict[str, Any] = {}
    for k, v in (data or {}).items():
        if k in NEVER_PERSIST or k in EXCLUDED_EVENT_KEYS or k not in ALLOWED_EVENT_KEYS:
            continue
        if isinstance(v, str):
            out[k] = redact(v, workspace)
        elif isinstance(v, (int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, (list, tuple)) and len(v) <= 20:
            out[k] = [redact(str(x), workspace) if isinstance(x, str) else x for x in v]
        elif isinstance(v, dict):
            out[k] = sanitize_evidence(v, workspace)
    return out


def map_event(
    ev: ar.RunEvent,
    *,
    run_id: str,
    sequence: int,
    workspace: Optional[Path] = None,
) -> Optional[RunEventRecord]:
    """把运行时事件映射为可入库记录。

    返回 None 表示该事件**不该落库**（例如原始日志与 thinking）。
    """
    kind = ev.kind.value

    # 原始日志与思考过程不落库——它们是过程草稿，不是可验证事实
    if ev.kind is ar.EventKind.LOG:
        return None
    # STARTED 只作为阶段边界
    if ev.kind is ar.EventKind.HEARTBEAT:
        return None

    state_map = {
        ar.EventKind.STARTED: "running",
        ar.EventKind.PROGRESS: "running",
        ar.EventKind.TOOL: "running",
        ar.EventKind.RESULT: "completed",
        ar.EventKind.ERROR: "failed",
    }

    title = {
        ar.EventKind.STARTED: "开始执行",
        ar.EventKind.PROGRESS: "进展",
        ar.EventKind.TOOL: f"工具调用：{ev.text or '未知'}",
        ar.EventKind.RESULT: "执行完成",
        ar.EventKind.ERROR: "执行失败",
    }[ev.kind]

    evidence = sanitize_evidence(ev.data, workspace)
    public_artifact = None
    if ev.kind is ar.EventKind.PROGRESS:
        p = ev.data.get("path")
        if isinstance(p, str):
            public_artifact = redact(p, workspace)

    return RunEventRecord(
        event_id=uuid.uuid4().hex,
        workflow_id="",              # 由调用方填充
        message_id=0,
        run_id=run_id,
        sequence=sequence,
        kind=kind,
        state=state_map[ev.kind],
        title=title,
        safe_detail=redact(ev.text, workspace),
        public_artifact_path=public_artifact,
        started_at=_now(),
        evidence=evidence,
    )


class RunEventStore:
    """把运行事件写入 `chat_run_events`。"""

    def __init__(self, con: sqlite3.Connection, *, workspace: Optional[Path] = None) -> None:
        self.con = con
        self.workspace = workspace

    def append(
        self,
        *,
        workflow_id: str,
        message_id: int,
        run_id: str,
        sequence: int,
        event: ar.RunEvent,
    ) -> Optional[RunEventRecord]:
        rec = map_event(event, run_id=run_id, sequence=sequence, workspace=self.workspace)
        if rec is None:
            return None
        rec.workflow_id = workflow_id
        rec.message_id = message_id
        self.con.execute(
            "INSERT OR IGNORE INTO chat_run_events"
            " (event_id, workflow_id, message_id, run_id, sequence, kind, state,"
            "  title, safe_detail, public_artifact_path, started_at, completed_at, evidence_json)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rec.event_id, rec.workflow_id, rec.message_id, rec.run_id, rec.sequence,
             rec.kind, rec.state, rec.title, rec.safe_detail, rec.public_artifact_path,
             rec.started_at, rec.completed_at,
             __import__("json").dumps(rec.evidence, ensure_ascii=False)),
        )
        self.con.commit()
        return rec

    def list_for_message(self, message_id: int, *, limit: int = 500) -> list[dict[str, Any]]:
        """按序读取某条消息的全部事件（供前端刷新后重建过程卡片）。"""
        rows = self.con.execute(
            "SELECT event_id, run_id, sequence, kind, state, title, safe_detail,"
            " public_artifact_path, started_at, completed_at, evidence_json"
            " FROM chat_run_events WHERE message_id=? ORDER BY sequence LIMIT ?",
            (message_id, limit),
        ).fetchall()
        out = []
        for r in rows:
            out.append({
                "event_id": r["event_id"], "run_id": r["run_id"],
                "sequence": r["sequence"], "kind": r["kind"], "state": r["state"],
                "title": r["title"], "safe_detail": r["safe_detail"],
                "public_artifact_path": r["public_artifact_path"],
                "started_at": r["started_at"], "completed_at": r["completed_at"],
                "evidence": __import__("json").loads(r["evidence_json"] or "{}"),
            })
        return out


def new_run_id() -> str:
    return uuid.uuid4().hex


def fingerprint(paths: Iterable[Path]) -> str:
    """为一组产物算内容指纹，用于「上游是否被改动」的漂移检测。"""
    h = hashlib.sha256()
    for p in sorted(map(Path, paths)):
        try:
            st = p.stat()
        except OSError:
            h.update(f"{p.name}:missing".encode())
            continue
        h.update(f"{p.name}:{st.st_size}:{int(st.st_mtime)}".encode())
    return h.hexdigest()[:16]


__all__ = [
    "RunEventRecord", "RunEventStore", "redact", "sanitize_evidence", "map_event",
    "new_run_id", "fingerprint", "ALLOWED_EVENT_KEYS", "NEVER_PERSIST",
]
