"""WebSocket 路由：实时推送运行事件与检查点通知。

契约（与前端约定一致）
--------------------
连接：`ws://127.0.0.1:<port>/ws/{workflow_id}`

信封：`{"type": "<事件类型>", "workflow_id": "<id>", ...}`

客户端 → 服务端：
  - 文本 `ping`  → 服务端回 `pong`（纯文本，与蓝方一致）

服务端 → 客户端（type）：
  - `hello`               连接确认，含当前工作流状态快照
  - `step_started`        步骤开始
  - `run_event`           运行事件（已脱敏、已落库）
  - `step_completed`      步骤完成
  - `step_failed`         步骤失败
  - `checkpoint_created`  需要人工确认
  - `checkpoint_resolved` 检查点已处理
  - `workflow_completed`  工作流完成

**WS 只是通知**：前端断线重连后应通过 REST 重新拉取状态，
不得依赖 WS 补发历史事件。
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services import broadcast as bc
from services import workflow_service as wfs

log = logging.getLogger("modemon.ws")

router = APIRouter()

#: 心跳间隔（秒）——纯文本 ping/pong，与蓝方一致
HEARTBEAT_S = 10


@router.websocket("/ws/{workflow_id}")
async def ws_endpoint(websocket: WebSocket, workflow_id: str) -> None:
    await websocket.accept()
    sub = await bc.hub.subscribe(websocket, [workflow_id])

    # 连接即给一份状态快照，前端无需立刻再发一次 REST 请求
    try:
        snapshot = _snapshot(websocket.app, workflow_id)
    except Exception:  # 快照失败不应导致连接失败
        snapshot = {}
    await websocket.send_text(json.dumps(
        {"type": "hello", "workflow_id": workflow_id, **snapshot},
        ensure_ascii=False, default=str))

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_S)
            try:
                await websocket.send_text(json.dumps(
                    {"type": "heartbeat", "workflow_id": workflow_id}))
            except Exception:
                return

    hb = asyncio.create_task(heartbeat())
    try:
        while True:
            msg = await websocket.receive_text()
            text = (msg or "").strip()
            if text == "ping":
                await websocket.send_text("pong")
            elif text.startswith("{"):
                # 预留：客户端可通过 WS 发指令；当前一律要求走 REST，
                # 避免两套写路径造成状态分叉。
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    payload = {}
                await websocket.send_text(json.dumps({
                    "type": "notice",
                    "workflow_id": workflow_id,
                    "message": "写操作请走 REST 接口；WS 仅用于接收通知",
                    "echo_type": payload.get("type"),
                }, ensure_ascii=False))
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # 客户端异常断开
        log.debug("ws closed: %s", exc)
    finally:
        hb.cancel()
        await bc.hub.unsubscribe(sub)


def _snapshot(app, workflow_id: str) -> dict:
    """读取当前工作流状态，供 `hello` 携带。"""
    import main as app_module  # 延迟导入避免循环

    con = app_module.get_db()
    try:
        wf = con.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
        if wf is None:
            return {"error": "workflow_not_found"}
        steps = [
            dict(r) for r in con.execute(
                "SELECT skill_name, display_name, step_order, status, has_checkpoint,"
                " checkpoint_type, model_used, error_message, started_at, completed_at"
                " FROM workflow_steps WHERE workflow_id=? ORDER BY step_order",
                (workflow_id,)).fetchall()
        ]
        return {
            "workflow": {
                "id": wf["id"], "title": wf["title"], "template": wf["template"],
                "status": wf["status"], "current_step": wf["current_step"],
                "enable_checkpoints": bool(wf["enable_checkpoints"]),
            },
            "steps": steps,
            "pending_checkpoint": wfs.pending_checkpoint(con, workflow_id),
        }
    finally:
        con.close()
