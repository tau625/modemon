"""Agent 运行时注册表与选择逻辑。

用 `resolve_runtime()` 按名字取适配器；用 `available_runtimes()` 列出本机可用项。
"""

from __future__ import annotations

from typing import Callable, Optional

from .base import (
    AgentRuntime,
    Capabilities,
    CapabilityError,
    EventKind,
    RunEvent,
    RunResult,
    RunSpec,
    RuntimeUnavailable,
    summarize,
)
from .claude_code import ClaudeCodeRuntime
from .deepseek_harness import DeepSeekHarnessRuntime
from .echo import EchoRuntime

_REGISTRY: dict[str, Callable[[], AgentRuntime]] = {
    "claude-code": ClaudeCodeRuntime,
    "claude": ClaudeCodeRuntime,
    "deepseek-harness": DeepSeekHarnessRuntime,
    "dsh": DeepSeekHarnessRuntime,
    "echo": EchoRuntime,
}

#: 默认优先级：越靠前越优先
DEFAULT_PRIORITY = ("claude-code", "deepseek-harness", "echo")


def register(name: str, factory: Callable[[], AgentRuntime]) -> None:
    """注册自定义运行时（例如接入其它 CLI agent）。"""
    _REGISTRY[name] = factory


def names() -> list[str]:
    return sorted(_REGISTRY)


def get(name: str) -> AgentRuntime:
    key = name.strip().lower()
    if key not in _REGISTRY:
        raise KeyError(
            f"未知运行时 {name!r}；可用: {', '.join(names())}"
        )
    return _REGISTRY[key]()


def available_runtimes() -> list[AgentRuntime]:
    out = []
    for n in DEFAULT_PRIORITY:
        try:
            rt = get(n)
        except KeyError:
            continue
        if rt.is_available():
            out.append(rt)
    return out


def resolve_runtime(preferred: Optional[str] = None) -> AgentRuntime:
    """选择运行时。

    Args:
        preferred: 指定的运行时名；为 None 时按默认优先级取第一个可用的。

    Raises:
        RuntimeUnavailable: 指定的运行时不可用，或没有任何可用运行时。
    """
    if preferred:
        rt = get(preferred)
        if not rt.is_available():
            raise RuntimeUnavailable(
                f"运行时 {preferred!r} 在本机不可用"
            )
        return rt
    avail = available_runtimes()
    if not avail:
        raise RuntimeUnavailable("本机没有任何可用的 agent 运行时")
    return avail[0]


def describe_all() -> list[dict[str, object]]:
    out = []
    for n in names():
        try:
            out.append(get(n).describe())
        except Exception as exc:  # 适配器自身出错不应影响列举
            out.append({"runtime": n, "error": str(exc)})
    return out


__all__ = [
    "AgentRuntime", "Capabilities", "CapabilityError", "EventKind",
    "RunEvent", "RunResult", "RunSpec", "RuntimeUnavailable", "summarize",
    "ClaudeCodeRuntime", "DeepSeekHarnessRuntime", "EchoRuntime",
    "register", "names", "get", "available_runtimes", "resolve_runtime", "describe_all",
    "DEFAULT_PRIORITY",
]
