"""确定性测试替身运行时。

用途：让上层编排逻辑（工作流引擎、质量门、降级策略）能在**无网络、无模型**的
条件下被完整测试。它也是「能力协商」的对照物——刻意只声明很少的能力，
用以验证降级路径确实被触发并如实记录。
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import AsyncIterator

from .base import (
    AgentRuntime,
    Capabilities,
    EventKind,
    RunEvent,
    RunSpec,
)


class EchoRuntime(AgentRuntime):
    """把 prompt 回显出来，并按 `emit` 参数写入指定文件。

    参数（写在 `RunSpec.env` 里，便于测试注入）：
      - `ECHO_EMIT`      : JSON 字符串 `{"相对路径": "要写入的内容"}`
      - `ECHO_FAIL`      : 非空则模拟失败并置该错误码
      - `ECHO_SILENT_S`  : 静默秒数（用于验证静默超时）
      - `ECHO_EVENTS`    : 事件条数
    """

    @property
    def capabilities(self) -> Capabilities:
        # 刻意保持"弱能力"，用于验证降级路径
        return Capabilities(
            name="echo",
            streaming=True,
            session_resume=True,
            effort_levels=(),
            model_selection=False,
            tool_allowlist=False,
            tool_denylist=False,
            mcp_pinning=False,
            budget_limit=False,
            structured_output=False,
            extra_dirs=False,
            skip_ambient_config=False,
        )

    def is_available(self) -> bool:
        return True

    def build_command(self, spec: RunSpec) -> list[str]:
        return ["echo", spec.prompt]

    async def run(self, spec: RunSpec) -> AsyncIterator[RunEvent]:
        started = time.monotonic()
        yield RunEvent(EventKind.STARTED, text="echo runtime started",
                       data={"workspace": str(spec.workspace)})

        silent = float(spec.env.get("ECHO_SILENT_S", "0") or 0)
        if silent:
            await asyncio.sleep(silent)

        fail = spec.env.get("ECHO_FAIL", "")
        if fail:
            yield RunEvent(EventKind.ERROR, text="simulated failure",
                           data={"code": fail})
            return

        emit_raw = spec.env.get("ECHO_EMIT", "")
        if emit_raw:
            try:
                emit = json.loads(emit_raw)
            except json.JSONDecodeError:
                emit = {}
            for rel, content in emit.items():
                p = Path(spec.workspace) / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
                yield RunEvent(EventKind.PROGRESS, text=f"wrote {rel}",
                               data={"path": rel, "bytes": len(content)})

        n = int(spec.env.get("ECHO_EVENTS", "2") or 2)
        for i in range(n):
            yield RunEvent(EventKind.LOG, text=f"step {i + 1}/{n}")

        yield RunEvent(
            EventKind.RESULT,
            text=f"[echo] {spec.prompt[:200]}",
            data={
                "session_id": spec.resume_session_id or "echo-session",
                "cost_usd": 0.0,
                "tokens_in": len(spec.prompt.split()),
                "tokens_out": 1,
                "duration_s": round(time.monotonic() - started, 4),
            },
        )
