"""modemon API 数据模型。

与 Modex 的差异（刻意的改进）
-----------------------------
蓝方后端**基本不声明响应模型**（内省真值：`response_model` 分布为
None=148 / dict=55 / list=2），直接返回裸 dict。本项目**一律显式声明**：

- 前端可生成类型、契约自文档化、联调成本显著下降；
- 出现字段改名时，编译期/校验期即暴露，而非运行时静默。
代价是需要维护模型，但相对收益很小。

请求体模型的**字段名与枚举取值与蓝方一致**（来自内省真值），
以保证行为等价；仅补充了响应侧模型。

来源：reports/18-api-contract.md、18-api-contract.json
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# 枚举（取值来自内省真值）
# ---------------------------------------------------------------------------


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_CHECKPOINT = "waiting_checkpoint"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class TemplateType(str, Enum):
    """**兼容用的历史枚举**——不是模板的真相源。

    ⚠️ 真相源是 `services/template_registry.py`（35 个值：22 竞赛 + 5 学术
    + 1 资产 + 2 软著/专利 + 5 兼容值）。这里**刻意不再扩充成员**：
    再抄一份名单必然与注册表漂移，而实测已经踩过——枚举只有 9 个成员时，
    22 个竞赛模板经 API **完全不可达**（pydantic 拦成 422）。

    校验统一走 `template_registry.is_known()`；本类仅为向后兼容保留。
    """

    COMP_CUMCM = "comp_cumcm"
    COMP_HUAWEI = "comp_huawei"
    COMP_MCM = "comp_mcm"
    COMP_APMCM = "comp_apmcm"
    COMP_MATHORCUP = "comp_mathorcup"
    COMP_ZH = "comp_zh"
    COMP_EN = "comp_en"
    COURSE_PAPER = "course_paper"
    THESIS_PROPOSAL = "thesis_proposal"


def _validate_template(value: str) -> str:
    """用**注册表**校验模板名（不是枚举）。

    延迟导入避免与 services 层成环；注册表是纯数据模块，无副作用。
    """
    try:
        from services import template_registry as _tr

        if not _tr.is_known(value):
            raise ValueError(f"未知模板: {value}")
    except ImportError:              # services 不可用时放行，不在 schema 层硬拦
        pass
    return value


#: 四个智能体角色（内省真值：ModelDiscoveryBody.agent）
AgentRole = Literal["executor", "reviewer", "editor_ai", "gpt_image"]
#: 交互模式（内省真值：SayIn.mode / ChatConfigIn.interaction_mode）
InteractionMode = Literal["auto", "conversation", "focused", "full"]
#: 执行范围（内省真值：ProposeIn.execution_scope）
ExecutionScope = Literal["full", "focused"]
#: 操作类型（内省真值：ProposeIn.operation_kind）
OperationKind = Literal["run_step", "focused_run", "research", "patch", "validate"]
#: 检查点动作（内省真值：CheckpointResponse.action）
CheckpointAction = Literal["approve", "select", "feedback", "stop"]
#: 上下文窗口档位（内省真值：PresetBody.context_mode）
ContextMode = Literal["auto", "200k", "1m"]


# ---------------------------------------------------------------------------
# 工作流
# ---------------------------------------------------------------------------


class WorkflowCreate(BaseModel):
    """POST /api/workflows —— 请求体（字段与内省真值一致）。

    `template` 用**注册表**校验（而非 `TemplateType` 枚举），
    这样 35 个模板全部可达，且只有一份真相源。非法值仍会被
    pydantic 拦成 **422**（保持原有契约）。
    """

    template: str
    title: str
    params: dict[str, Any] = Field(default_factory=dict)
    enable_checkpoints: bool = False

    _check_template = field_validator("template")(_validate_template)


class StepInfo(BaseModel):
    """单个步骤的公开视图。

    对应蓝方 `models.schemas.StepInfo`（10 个字段，内省真值）。
    """

    skill_name: str
    display_name: str
    step_order: int
    status: StepStatus = StepStatus.PENDING
    has_checkpoint: bool = False
    checkpoint_type: Optional[str] = None
    output_files: list[str] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class WorkflowInfo(BaseModel):
    """工作流公开视图（对应蓝方 `WorkflowInfo`，9 个字段）。"""

    id: str
    template: str
    title: str
    params: dict[str, Any] = Field(default_factory=dict)
    status: WorkflowStatus = WorkflowStatus.PENDING
    current_step: Optional[str] = None
    steps: list[StepInfo] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    #: 相对蓝方新增：把 advisory 页数参考值直接暴露给前端
    page_advisory: Optional[int] = None


# ---------------------------------------------------------------------------
# 检查点
# ---------------------------------------------------------------------------


class CheckpointData(BaseModel):
    """检查点内容（对应蓝方 `CheckpointData`，3 个字段）。"""

    checkpoint_type: str
    step_name: str
    data: dict[str, Any] = Field(default_factory=dict)


class CheckpointResponse(BaseModel):
    """POST /api/workflows/{wf}/checkpoints/resolve —— 请求体。

    `action` 的 4 个取值来自内省真值。
    """

    action: CheckpointAction
    checkpoint_id: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)


class CheckpointView(BaseModel):
    """检查点公开视图。

    `remaining_seconds` 是**契约要求字段**：前端据此判定后端是否为旧版逻辑。
    """

    checkpoint_id: str
    workflow_id: str
    step_name: str
    checkpoint_type: str
    data: dict[str, Any] = Field(default_factory=dict)
    status: Literal["pending", "resolved"] = "pending"
    remaining_seconds: Optional[int] = None


# ---------------------------------------------------------------------------
# 对话工作台
# ---------------------------------------------------------------------------


class SayIn(BaseModel):
    """POST /api/workflows/{wf}/chat/say —— 用户发言。

    `turn_id` 为**幂等键**：网络重试时不能把同一句话重复喂给主会话。
    """

    text: str
    turn_id: Optional[str] = None
    mode: Optional[InteractionMode] = None
    focus_target: Optional[str] = None


class ProposalEditIn(BaseModel):
    """PATCH .../chat/messages/{msg}/proposal —— 编辑提议。

    `revision` 为 **CAS 乐观并发**字段：防止「保存编辑」与「确认执行」并发跑旧指令。
    """

    instruction: str
    revision: int
    execution_scope: Optional[ExecutionScope] = None
    focus_target: Optional[str] = None
    model_preset_id: Optional[str] = None
    effort: Optional[str] = None
    target_paths: Optional[list[str]] = None
    target_sections: Optional[dict[str, list[str]]] = None


class ProposeIn(BaseModel):
    """POST /api/internal/chat/propose —— MCP 子进程回调产生提议。"""

    session_id: str
    workflow_id: str
    skill: str
    instruction: str = ""
    raw_text: str = ""
    execution_scope: ExecutionScope = "full"
    focus_target: str = ""
    operation_kind: Optional[OperationKind] = None
    target_paths: list[str] = Field(default_factory=list)
    target_sections: dict[str, list[str]] = Field(default_factory=dict)
    input_paths: list[str] = Field(default_factory=list)


class DecisionIn(BaseModel):
    """POST .../chat/decisions —— 记录决策（含被否决的方案）。"""

    topic: str
    choice: str
    rejected: str = ""
    evidence: str = ""


class ForkChoiceIn(BaseModel):
    """POST .../chat/forks/{fork}/choose —— 分叉选择。

    `expected_revision` 为乐观并发校验。
    """

    choice: Optional[str] = None
    skip: bool = False
    action: Optional[Literal["select", "accept_recommendation", "defer", "reopen"]] = None
    expected_revision: Optional[int] = None
    expected_choice_label: Optional[str] = None


class ChatConfigIn(BaseModel):
    """PATCH .../chat/config —— 对话配置。"""

    interaction_mode: InteractionMode
    model_preset_id: Optional[str] = None
    effort: Optional[str] = None


class StageAcceptIn(BaseModel):
    """POST .../chat/stages/{skill}/accept —— 阶段验收。

    验收必须**显式落库**，绝不从聚焦任务的回执数量推断。
    """

    snapshot: str


# ---------------------------------------------------------------------------
# 设置与账号
# ---------------------------------------------------------------------------


class SettingsUpdate(BaseModel):
    """PUT /api/settings —— 批量更新设置。"""

    settings: dict[str, str]


class DataDirUpdate(BaseModel):
    """PUT /api/settings/data-dir —— 切换数据目录。"""

    path: str


# ---------------------------------------------------------------------------
# 成文（排版 / 导出）
# ---------------------------------------------------------------------------


class PaperExportBody(BaseModel):
    """成文导出请求。

    `formats` 支持 `latex`（可编译 PDF）与 `docx`，**共用同一份论文模型与排版规格**。
    """

    workspace: str
    template: str = "comp_cumcm"
    language: str = "zh"
    title: str = ""
    abstract: str = ""
    keywords: list[str] = Field(default_factory=list)
    formats: list[str] = Field(default_factory=lambda: ["latex", "docx"])
    compile_pdf: bool = True


class PresetBody(BaseModel):
    """POST /api/settings/presets —— 模型预设。

    `context_mode` 的 3 个档位来自内省真值。
    """

    name: str
    model_id: str
    api_key: str = ""
    context_mode: Optional[ContextMode] = None


class PresetView(BaseModel):
    """模型预设公开视图（**不回传 api_key**）。"""

    id: str
    name: str
    model_id: str
    provider_id: str = ""
    context_mode: Optional[ContextMode] = None
    has_api_key: bool = False


class ModelDiscoveryBody(BaseModel):
    """POST /api/settings/models/discover —— 探测可用模型。"""

    agent: Optional[AgentRole] = None


# ---------------------------------------------------------------------------
# 编辑器
# ---------------------------------------------------------------------------


class AiAgentRequest(BaseModel):
    """POST /api/editor/{wf}/ai-agent —— 编辑器 AI（走 SSE 流）。"""

    message: str
    current_file: str = ""
    compile_log: str = ""
    request_id: Optional[str] = None
    auto_export: bool = False
    auto_repair: bool = False
    allowed_paths: Optional[list[str]] = None
    permission_mode: Literal["project", "intent"] = "project"


class ToolUseRecord(BaseModel):
    """国赛 AI 使用记录（强制申报项）。

    对应内置模板 `comp_cumcm` 的门禁：必须填写 1–5 条真实记录
    并完成参赛队人工核验确认，否则不放行。
    """

    order: int = Field(ge=1, le=5)
    tool_name: str
    purpose: str
    prompt_excerpt: str = ""
    output_used: str = ""


class AiDisclosure(BaseModel):
    """AI 使用申报。导出文件名由引擎常量给定：`AI工具使用详情.pdf`。"""

    records: list[ToolUseRecord] = Field(default_factory=list)
    verified_by_team: bool = False


# ---------------------------------------------------------------------------
# 通用
# ---------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    """统一错误体。

    契约（内省真值）：前端需同时兼容 `{detail: "字符串"}` 与
    `{detail: {message, code}}` 两种形态，故这里用 union。
    """

    message: str
    code: str = ""


class ErrorResponse(BaseModel):
    detail: str | ErrorDetail


class OkResponse(BaseModel):
    ok: bool = True


__all__ = [
    "StepStatus", "WorkflowStatus", "TemplateType",
    "AgentRole", "InteractionMode", "ExecutionScope", "OperationKind",
    "CheckpointAction", "ContextMode",
    "WorkflowCreate", "StepInfo", "WorkflowInfo",
    "CheckpointData", "CheckpointResponse", "CheckpointView",
    "SayIn", "ProposalEditIn", "ProposeIn", "DecisionIn", "ForkChoiceIn",
    "ChatConfigIn", "StageAcceptIn",
    "SettingsUpdate", "DataDirUpdate", "PresetBody", "PresetView", "ModelDiscoveryBody",
    "AiAgentRequest", "ToolUseRecord", "AiDisclosure", "PaperExportBody",
    "ErrorDetail", "ErrorResponse", "OkResponse",
]
