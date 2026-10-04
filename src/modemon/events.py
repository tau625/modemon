"""事件总线：所有进度都走这里，既打屏也落 JSONL，未来可直接接 WebSocket 推送。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from rich.console import Console

ICONS = {
    "run_start": "🚀",
    "stage_start": "▶",
    "stage_done": "✔",
    "llm_call": "🤖",
    "llm_wait": "⏳",
    "artifact": "📄",
    "exec": "⚙",
    "review": "🔍",
    "revise": "✎",
    "checkpoint": "⏸",
    "warn": "⚠",
    "error": "✖",
    "cost": "💰",
    "run_done": "🏁",
}


class EventBus:
    def __init__(
        self,
        events_file: Path | None = None,
        console: Console | None = None,
        verbose: bool = True,
    ) -> None:
        self.events_file = events_file
        self.console = console or Console()
        self.verbose = verbose
        self._subscribers: list[Callable[[dict[str, Any]], None]] = []
        self.events: list[dict[str, Any]] = []

    def subscribe(self, fn: Callable[[dict[str, Any]], None]) -> None:
        self._subscribers.append(fn)

    def emit(self, kind: str, message: str = "", **data: Any) -> dict[str, Any]:
        event = {"ts": time.time(), "kind": kind, "message": message, **data}
        self.events.append(event)

        if self.events_file is not None:
            try:
                self.events_file.parent.mkdir(parents=True, exist_ok=True)
                with self.events_file.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(event, ensure_ascii=False) + "\n")
            except OSError:
                pass  # 事件日志写不了不应中断主流程

        if self.verbose:
            icon = ICONS.get(kind, "·")
            color = {"error": "red", "warn": "yellow", "run_done": "green"}.get(kind, "cyan")
            text = f"{icon} {message}" if message else f"{icon} {kind}"
            extra = data.get("detail")
            if extra:
                text += f" [dim]{extra}[/dim]"
            self.console.print(f"[{color}]{text}[/{color}]")

        for fn in self._subscribers:
            try:
                fn(event)
            except Exception:  # 订阅者异常不影响主流程
                pass
        return event
