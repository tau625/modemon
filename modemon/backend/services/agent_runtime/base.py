"""Agent 运行时抽象层。

为什么需要这一层
----------------
蓝方产品**硬绑定 Claude Code CLI**，后果在其源码注释里写得很清楚：

    【为什么要 audit()】黑名单是穷举的，CLI 升级加了新工具就会【无声漏进来】。
    那些工具能发飞书消息、能调外部 LLM、能读写文件，【全在我们的闸外面】。

一旦运行时不可替换，所有安全与配额约束就只能**寄生在它的参数上**，
厂商改语义（例如 `--allowedTools` 其实不是白名单）就会静默失效。

本层把运行时变成**可插拔组件**，并且要求每个适配器**如实声明自己的能力**：

- 声明支持某能力 → 直接使用；
- 声明不支持 → 由上层选择**降级策略**，并把降级事实记录到 `RunResult.degraded`。

绝不静默假设某个开关存在——那是蓝方踩过的坑。
"""

from __future__ import annotations

import abc
import dataclasses
import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Iterable, Optional


class RuntimeUnavailable(Exception):
    """运行时可执行文件不存在或不可用。"""


class CapabilityError(Exception):
    """请求的能力该运行时不具备，且上层未提供降级策略。"""

    def __init__(self, capability: str, runtime: str) -> None:
        super().__init__(f"运行时 {runtime!r} 不支持能力 {capability!r}")
        self.capability = capability
        self.runtime = runtime


class EventKind(str, enum.Enum):
    STARTED = "started"
    PROGRESS = "progress"      # 阶段性进展（可展示）
    LOG = "log"                # 原始日志（可能不入库）
    TOOL = "tool"              # 工具调用
    RESULT = "result"          # 最终结果
    ERROR = "error"
    HEARTBEAT = "heartbeat"    # 保活，证明未静默


@dataclass(frozen=True)
class Capabilities:
    """运行时的能力声明。**由适配器如实填写，不做乐观假设。**"""

    name: str
    #: 能否流式输出事件
    streaming: bool = False
    #: 能否按 session id 恢复会话
    session_resume: bool = False
    #: 支持的思考强度档位（空 = 不支持该概念）
    effort_levels: tuple[str, ...] = ()
    #: 能否指定模型
    model_selection: bool = False
    #: 是否能限定可用工具白名单
    tool_allowlist: bool = False
    #: 是否能屏蔽指定工具
    tool_denylist: bool = False
    #: **能否硬性钉住 MCP 配置、忽略环境中的其它 MCP 配置来源**
    mcp_pinning: bool = False
    #: 能否限制花费
    budget_limit: bool = False
    #: 能否要求结构化输出
    structured_output: bool = False
    #: 能否追加可访问目录
    extra_dirs: bool = False
    #: 能否跳过工作区里的自动发现（CLAUDE.md / hooks / 插件）
    skip_ambient_config: bool = False
    #: 支持的权限模式档位（空 = 该运行时不区分权限模式）
    #: 实测教训：Claude Code 在 `-p` 非交互模式下**默认拒绝文件写入**，
    #: 必须显式给 `acceptEdits`，否则 agent 干完活却落不了盘。
    permission_modes: tuple[str, ...] = ()
    #: 运行时自身能否在某模型过载/额度耗尽时自动回退到备用模型
    #: （Claude Code 的 `--fallback-model`）。不具备时由上层做模型链重试。
    model_fallback: bool = False

    def as_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclass
class RunSpec:
    """一次运行的完整输入。**与运行时无关的中立描述。**"""

    prompt: str
    workspace: Path

    system_prompt: Optional[str] = None
    model: Optional[str] = None
    effort: Optional[str] = None

    #: 允许的工具。None = 不限制（由运行时默认）
    allowed_tools: Optional[tuple[str, ...]] = None
    #: 禁止的工具
    disallowed_tools: tuple[str, ...] = ()

    #: 显式指定的 MCP 配置；配合 isolate_mcp 使用
    mcp_config: Optional[Path] = None
    #: **要求忽略工作区/用户环境中的 MCP 配置来源**
    isolate_mcp: bool = True
    #: 跳过 CLAUDE.md / hooks / 插件等环境自动发现
    skip_ambient_config: bool = True

    resume_session_id: Optional[str] = None
    add_dirs: tuple[Path, ...] = ()
    max_budget_usd: Optional[float] = None
    output_json_schema: Optional[str] = None

    #: 权限模式。**非交互场景通常必须显式设置**，否则写文件会被拒。
    #: Claude Code 取值：default | acceptEdits | plan | bypassPermissions | dontAsk | auto
    permission_mode: Optional[str] = "acceptEdits"

    #: 备用模型。额度耗尽/过载时使用。
    #: Claude Code 会经 `--fallback-model` 在**同一次调用内**自动切换；
    #: 不支持该能力的运行时，由上层做「模型链」重试。
    fallback_model: Optional[str] = None

    #: 额度耗尽/过载时的模型链（上层重试用）。可含多个。
    model_chain: tuple[str, ...] = ()

    #: 整次运行的硬上限
    timeout_s: int = 3600
    #: 静默（无任何事件）上限——只约束静默，不限制可见工作总时长
    inactivity_timeout_s: int = 900

    env: dict[str, str] = field(default_factory=dict)


@dataclass
class RunEvent:
    kind: EventKind
    text: str = ""
    data: dict = field(default_factory=dict)


@dataclass
class RunResult:
    ok: bool
    final_text: str = ""
    session_id: Optional[str] = None
    cost_usd: Optional[float] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    duration_s: float = 0.0
    exit_code: Optional[int] = None
    error_code: str = ""
    error: str = ""

    #: **降级事实**：请求了但运行时无法满足、且已被上层策略补偿的能力。
    #: 必须如实记录——这正是蓝方缺失的「对账」意识。
    degraded: list[str] = field(default_factory=list)

    #: 运行期间产生的可展示事件（由调用方决定是否持久化）
    events: list[RunEvent] = field(default_factory=list)


class AgentRuntime(abc.ABC):
    """Agent 运行时适配器基类。"""

    @property
    @abc.abstractmethod
    def capabilities(self) -> Capabilities: ...

    @abc.abstractmethod
    def is_available(self) -> bool:
        """该运行时在本机是否可用（可执行文件存在等）。"""

    @abc.abstractmethod
    def build_command(self, spec: RunSpec) -> list[str]:
        """把中立的 RunSpec 翻译成本运行时的命令行。

        独立出来便于**测试与审计**：无需真正执行即可检查参数是否正确、
        以及哪些请求的能力被降级。
        """

    @abc.abstractmethod
    async def run(self, spec: RunSpec) -> AsyncIterator[RunEvent]:
        """执行并流式产出事件。**最后一个事件必须是 result 或 error。**"""

    # -- 辅助 ---------------------------------------------------------------

    def negotiate(self, spec: RunSpec) -> list[str]:
        """返回**因运行时能力不足而降级**的项（不抛错，供上层决策）。

        上层可据此拒绝执行（严格模式）或接受降级（宽松模式），
        无论哪种，`degraded` 都会被如实记录。
        """
        caps = self.capabilities
        degraded: list[str] = []
        if spec.isolate_mcp and not caps.mcp_pinning:
            degraded.append("mcp_isolation")
        if spec.allowed_tools and not caps.tool_allowlist:
            degraded.append("tool_allowlist")
        if spec.disallowed_tools and not caps.tool_denylist:
            degraded.append("tool_denylist")
        if spec.effort and spec.effort not in caps.effort_levels:
            degraded.append("effort:%s" % spec.effort)
        if spec.model and not caps.model_selection:
            degraded.append("model_selection")
        if spec.resume_session_id and not caps.session_resume:
            degraded.append("session_resume")
        if spec.max_budget_usd is not None and not caps.budget_limit:
            degraded.append("budget_limit")
        if spec.output_json_schema and not caps.structured_output:
            degraded.append("structured_output")
        if spec.add_dirs and not caps.extra_dirs:
            degraded.append("extra_dirs")
        if spec.skip_ambient_config and not caps.skip_ambient_config:
            degraded.append("skip_ambient_config")
        if spec.permission_mode and caps.permission_modes \
                and spec.permission_mode not in caps.permission_modes:
            degraded.append("permission_mode:%s" % spec.permission_mode)
        return degraded

    def describe(self) -> dict[str, object]:
        return {"runtime": self.capabilities.name,
                "available": self.is_available(),
                "capabilities": self.capabilities.as_dict()}


def summarize(events: Iterable[RunEvent]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in events:
        counts[e.kind.value] = counts.get(e.kind.value, 0) + 1
    return counts


__all__ = [
    "AgentRuntime", "Capabilities", "RunSpec", "RunEvent", "RunResult", "EventKind",
    "RuntimeUnavailable", "CapabilityError", "summarize",
]
