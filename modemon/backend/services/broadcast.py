"""WebSocket 广播管理器。

设计原则（与蓝方一致）
--------------------
**WebSocket 只是通知，状态永远以数据库为准。**

蓝方在 schema 注释里写得很明确：

    WS 只是通知，断线/重启后仍应完整显示。
    提议卡片的派生信息也要落库；WS 只是通知。

因此本模块只负责"把已落库的事实推出去"，**不承担状态**。
前端刷新或重连时，一律通过 REST 重新拉取完整状态，
WS 只用于让界面实时跟上。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import WebSocket

log = logging.getLogger("modemon.ws")


@dataclass(eq=False)   # eq=False 保留默认的身份哈希——订阅者要放进 set()
class Subscriber:
    ws: WebSocket
    channels: set[str] = field(default_factory=set)


class BroadcastHub:
    """按频道（workflow_id）分组的广播中心。

    每个订阅者还有一个 `__all__` 频道用于接收全局事件（如后台任务完成）。
    """

    def __init__(self) -> None:
        self._subs: dict[str, set[Subscriber]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, ws: WebSocket, channels: list[str]) -> Subscriber:
        sub = Subscriber(ws=ws, channels=set(channels) | {"__all__"})
        async with self._lock:
            for ch in sub.channels:
                self._subs[ch].add(sub)
        return sub

    async def unsubscribe(self, sub: Subscriber) -> None:
        async with self._lock:
            for ch in sub.channels:
                self._subs[ch].discard(sub)
            for ch in list(self._subs):
                if not self._subs[ch]:
                    del self._subs[ch]

    def subscriber_count(self, channel: Optional[str] = None) -> int:
        if channel is None:
            return len({id(s) for subs in self._subs.values() for s in subs})
        return len(self._subs.get(channel, ()))

    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        workflow_id: Optional[str] = None,
    ) -> int:
        """广播一条消息。

        信封格式与前端约定一致：`{type, workflow_id, ...}`。
        返回成功投递数（失败者会被摘除，不阻塞其它订阅者）。
        """
        msg = {"type": event_type}
        if workflow_id:
            msg["workflow_id"] = workflow_id
        msg.update(payload)
        text = json.dumps(msg, ensure_ascii=False, default=str)

        async with self._lock:
            targets = set(self._subs.get(workflow_id or "", ())) | set(self._subs.get("__all__", ()))

        dead: list[Subscriber] = []
        sent = 0
        for sub in targets:
            try:
                await sub.ws.send_text(text)
                sent += 1
            except Exception:
                dead.append(sub)
        for sub in dead:
            await self.unsubscribe(sub)
        return sent


#: 进程级单例。生产环境若多进程需换成 Redis 等外部广播。
hub = BroadcastHub()


__all__ = ["BroadcastHub", "Subscriber", "hub"]
