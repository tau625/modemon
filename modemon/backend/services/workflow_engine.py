"""modemon workflow engine — 数模竞赛流水线编排。

来源与边界
----------
本模块的**契约与数据**（步骤序列、展示名、产出文件名、阈值、超时、页码规则）
来自对 Modex-MH-Agent `services.workflow_engine` 的**内省与纯访问器求值**，
是真值而非推测。详见 `docs/SPEC-PROVENANCE.md`。

**算法实现为本项目自行编写**——逆向只恢复了签名、docstring 与数据，
函数体（Cython 编译为原生机器码）不可恢复。

设计取向与蓝方的三点差异
------------------------
1. **响应模型显式声明**：蓝方路由大量返回裸 dict；本项目一律用 Pydantic 模型。
2. **页数上限为 advisory**：与蓝方一致——只对用户可见，不作生成/压缩门控。
3. **检查器不可用与真实缺陷必须区分**：布尔门无法表达，故用结构化结果。

模板解析：查注册表，不查 `if/elif` 链
------------------------------------
30 个产品面模板的**数据**在 `services.template_registry`（22 竞赛 + 5 学术 +
1 资产 + 2 软著/专利），**编排**在本模块的 `SEQUENCE_BUILDERS`。
22 个竞赛模板只由 3 套编排支撑（`comp_zh` / `comp_en` / `comp_stats`），
**华为杯是 `comp_zh` 上的步骤级变体**，不是第 4 套 DAG（§3.6）。

解析规则：
- 未知 value **绝不抛异常**：回退到通用中文序列并置 `degraded=True`；
- 非字符串输入（`None` / `enum` / `int`）经 `template_registry.coerce_value` 归一化，
  同样不抛异常；
- `docx_mode` 只改「论文主产物后缀」，不改步骤序列。

单步超时：两套语义，别混用
--------------------------
- `inactivity_timeout()`：**蓝方恢复真值**（静默无输出上限，成文 2700 / 创作 5400 秒）；
- `tiered_inactivity_timeout()`：本项目脚本的**单步总预算分级**
  （写作类 40 分钟 / 分析类 15 分钟，见 §5.3 与 `run_full_pipeline.py --step-deadline-min`）。

两者是不同的旋钮：前者约束「多久没输出算卡死」，后者约束「这一步最多给多久」。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence

try:  # 正常路径：作为 `services` 包的一部分导入
    from . import template_registry as registry
except ImportError:  # pragma: no cover - 允许脚本以顶层模块方式直跑
    import template_registry as registry  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# 数据结构
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


class CheckpointType(str, Enum):
    APPROVE = "approve"
    IDEA_SELECT = "idea_select"
    FEEDBACK = "feedback"
    ASSETS_RESOLVE = "assets_resolve"


class TemplateType(str, Enum):
    """竞赛与学术模板。`comp_*` 为数学建模竞赛族。"""

    COMP_CUMCM = "comp_cumcm"
    COMP_HUAWEI = "comp_huawei"
    COMP_MCM = "comp_mcm"
    COMP_APMCM = "comp_apmcm"
    COMP_MATHORCUP = "comp_mathorcup"
    COMP_ZH = "comp_zh"
    COMP_EN = "comp_en"
    COURSE_PAPER = "course_paper"
    THESIS_PROPOSAL = "thesis_proposal"


@dataclass(frozen=True)
class StepDef:
    """单个步骤的契约。

    前 6 个字段与蓝方 `StepDef` 完全一致（内省真值）。
    后 5 个字段是本项目加的**变体/可选性元数据**——它们不改变蓝方契约，
    只让「步骤级 select」（华为杯）与「可合法跳过」（AUTO-RECOVER / from_assets）
    有地方可表达，从而避免复制 DAG。
    """

    skill_name: str
    display_name: str
    output_files: tuple[str, ...]
    primary_output: Optional[str] = None
    has_checkpoint: bool = False
    checkpoint_type: Optional[str] = None
    #: 变体标记（如 `huawei`）。非默认变体时由 `STEP_VARIANTS` 替换而来
    variant: Optional[str] = None
    #: 该步替换了哪一步（步骤级 select 的「来源」）
    select_from: Optional[str] = None
    #: 签名模板包路径。华为杯写作步骤用它，缺失时 fail-closed（§3.6）
    template_bundle: Optional[str] = None
    #: True = 模板包缺失时**不得**静默降级为通用文档
    fail_closed: bool = False
    #: True = 该步可合法跳过（AUTO-RECOVER 白名单 / from_assets 资产跳过）
    optional: bool = False


@dataclass(frozen=True)
class TemplateDef:
    """模板 = 一条流水线。

    `sub_steps` 是**步骤的唯一真相源**：创建工作流与运行时都由它派生步骤列表，
    以保证「模板步骤」与「数据库步骤」逐一对应，避免 step_index 错位
    导致 expected_outputs 张冠李戴（这正是蓝方 docstring 强调的点）。
    """

    pipeline_skill: str
    display_name: str
    sub_steps: tuple[StepDef, ...]
    #: 注册表原值（与 `pipeline_skill` 的 `pipeline-` 前缀部分一致，便于调用方直取）
    template_value: str = ""
    #: 中文名（天府杯 / 国赛 (CUMCM) …）
    label: str = ""
    lang: str = "zh"
    pages: Optional[int] = None
    stars: int = 0
    group: str = ""
    sequence: str = ""
    variant: Optional[str] = None
    #: True = 该 value 不在注册表里，已回退到通用序列
    degraded: bool = False
    degraded_reason: str = ""

    @property
    def skill_names(self) -> tuple[str, ...]:
        return tuple(s.skill_name for s in self.sub_steps)

    @property
    def step_count(self) -> int:
        return len(self.sub_steps)


# ---------------------------------------------------------------------------
# 步骤模板（分段构造：中文与英文共用前 6 步）
# ---------------------------------------------------------------------------

_COMMON_HEAD_STEPS: tuple[StepDef, ...] = (
    StepDef(
        skill_name="comp-prob-analysis",
        display_name="Problem Analysis",
        output_files=("PROBLEM_ANALYSIS.md",),
        primary_output="PROBLEM_ANALYSIS.md",
        has_checkpoint=True,
        checkpoint_type="approve",
    ),
    StepDef(
        skill_name="comp-modeling",
        display_name="Modeling & Solution",
        output_files=("MODELING_REPORT.md",),
        primary_output="MODELING_REPORT.md",
        has_checkpoint=True,
        checkpoint_type="feedback",
    ),
    StepDef(
        skill_name="comp-code",
        display_name="Programming",
        output_files=("code/main.py", "RESULTS.md"),
        primary_output="RESULTS.md",
        has_checkpoint=True,
        checkpoint_type="approve",
    ),
    StepDef(
        skill_name="paper-figure",
        display_name="Figure Generation",
        output_files=("figures/latex_includes.tex",),
        primary_output="figures/",
    ),
    StepDef(
        skill_name="paper-figure-drawio",
        display_name="Flow & Architecture Diagrams",
        output_files=("figures/latex_includes.tex",),
        primary_output="figures/",
    ),
    StepDef(
        skill_name="comp-review",
        display_name="Logic Adversarial Review",
        output_files=("COMP_REVIEW.md",),
        primary_output="COMP_REVIEW.md",
    ),
)

#: 中文展示名（与英文步骤一一对应）
_ZH_DISPLAY = {
    "comp-prob-analysis": "赛题分析",
    "comp-modeling": "建模求解",
    "comp-code": "编程实现",
    "paper-figure": "图表生成",
    "paper-figure-drawio": "流程与架构图绘制",
    "comp-review": "逻辑对抗复核",
    "comp-paper-zh": "竞赛论文撰写",
    "comp-compile-zh": "编译与合规检查",
    # 统计建模（唯一编排例外）的两步
    "comp-topic-plan": "选题规划",
    "comp-data-analysis": "数据采集与分析",
    "comp-stats-code": "数据采集与分析",
}


def _localize(steps: Iterable[StepDef]) -> tuple[StepDef, ...]:
    """把英文展示名替换为中文，其余字段不变。"""
    out = []
    for s in steps:
        out.append(
            StepDef(
                skill_name=s.skill_name,
                display_name=_ZH_DISPLAY.get(s.skill_name, s.display_name),
                output_files=s.output_files,
                primary_output=s.primary_output,
                has_checkpoint=s.has_checkpoint,
                checkpoint_type=s.checkpoint_type,
            )
        )
    return tuple(out)


def comp_en_steps() -> tuple[StepDef, ...]:
    """英文竞赛（美赛等）通用步骤列表。"""
    return _COMMON_HEAD_STEPS + (
        StepDef(
            skill_name="comp-paper-en",
            display_name="Paper Writing (English)",
            output_files=("paper/main.tex",),
            primary_output="paper/main.tex",
            has_checkpoint=True,
            checkpoint_type="approve",
        ),
        StepDef(
            skill_name="comp-compile-en",
            display_name="Compile & Compliance Check",
            output_files=("paper/main.pdf",),
            primary_output="paper/main.pdf",
        ),
    )


def comp_zh_steps(
    first_skill: str = "comp-prob-analysis",
    paper_skill: str = "comp-paper-zh",
    *,
    variant: Optional[str] = None,
) -> tuple[StepDef, ...]:
    """中文竞赛（国赛等）通用步骤列表。

    绝大多数中文赛事共用同一写作契约；**华为杯是刻意的例外**——
    它有独立的研究生级机制与求解深度技能，因此调用方通过 `paper_skill`
    或 `variant` 选择它，而**无需复制一份 DAG**。

    Args:
        first_skill: 起始技能，便于从中间插入赛事特有步骤。
        paper_skill: 论文撰写技能；华为杯传入其专属技能名。
        variant: 步骤级变体键（见 `STEP_VARIANTS`）。`"huawei"` 只替换
            「建模求解」与「论文撰写」两步的技能/契约，**步骤数不变**。
    """
    head = _localize(_COMMON_HEAD_STEPS)
    if first_skill != "comp-prob-analysis":
        idx = next((i for i, s in enumerate(head) if s.skill_name == first_skill), 0)
        head = head[idx:]
    tail_skill = "comp-compile-zh"
    # 论文技能名后缀决定编译技能名：comp-paper-zh -> comp-compile-zh
    if paper_skill != "comp-paper-zh":
        tail_skill = paper_skill.replace("paper", "compile")
    tail = _localize(
        (
            StepDef(
                skill_name=paper_skill,
                display_name="Paper Writing",
                output_files=("paper/main.tex",),
                primary_output="paper/main.tex",
                has_checkpoint=True,
                checkpoint_type="approve",
            ),
            StepDef(
                skill_name=tail_skill,
                display_name="Compile & Compliance Check",
                output_files=("paper/main.pdf",),
                primary_output="paper/main.pdf",
            ),
        )
    )
    return apply_step_variant(head + tail, variant)


def comp_stats_steps(
    *,
    code_skill: str = "comp-data-analysis",
    paper_skill: str = "comp-paper-zh",
) -> tuple[StepDef, ...]:
    """统计建模大赛（`comp_stats`）——**唯一的编排例外**（5 步）。

    蓝方原文（§3.2 `【直接提取】`）：

    > `选题规划 → 数据采集分析 → 图表 → 论文 → 编译`

    与通用中文序列的差异集中在**前半段**：统计建模重「选题立项 + 数据采集」，
    因此没有独立的「建模求解」步，且**首步是选题规划**（人工可确认的检查点）。

    Args:
        code_skill: 数据采集/分析步的技能名。取值见 `STATS_CODE_SKILLS`：
            - `comp-data-analysis`（默认，任务建议命名）
            - `comp-stats-code`（下游 `workflow_service.POST_AUDIT_SKILLS` 已识别，
              选它即可让统计流也走 `all_results.json` 的诚信审计）
        paper_skill: 论文撰写技能名（默认与中文竞赛一致）。
    """
    if code_skill not in STATS_CODE_SKILLS:
        code_skill = STATS_CODE_SKILLS[0]
    tail_skill = (
        "comp-compile-zh" if paper_skill == "comp-paper-zh"
        else paper_skill.replace("paper", "compile")
    )
    return _localize((
        StepDef(
            skill_name="comp-topic-plan",
            display_name="Topic Planning",
            output_files=("TOPIC_PLAN.md",),
            primary_output="TOPIC_PLAN.md",
            has_checkpoint=True,
            checkpoint_type="approve",
        ),
        StepDef(
            skill_name=code_skill,
            display_name="Data Collection & Analysis",
            output_files=("code/main.py", "RESULTS.md"),
            primary_output="RESULTS.md",
            has_checkpoint=True,
            checkpoint_type="feedback",
        ),
        StepDef(
            skill_name="paper-figure",
            display_name="Figure Generation",
            output_files=("figures/latex_includes.tex",),
            primary_output="figures/",
        ),
        StepDef(
            skill_name=paper_skill,
            display_name="Paper Writing",
            output_files=("paper/main.tex",),
            primary_output="paper/main.tex",
            has_checkpoint=True,
            checkpoint_type="approve",
        ),
        StepDef(
            skill_name=tail_skill,
            display_name="Compile & Compliance Check",
            output_files=("paper/main.pdf",),
            primary_output="paper/main.pdf",
        ),
    ))


# ---------------------------------------------------------------------------
# 变体：步骤级 select（华为杯）
# ---------------------------------------------------------------------------

#: 统计建模「数据采集分析」步的可用技能名。
#: `comp-stats-code` 已被本项目下游（`POST_AUDIT_SKILLS` / `step_runner` 分段交付）
#: 识别为「产数值结果、需诚信审计」的代码步。
STATS_CODE_SKILLS: tuple[str, ...] = ("comp-data-analysis", "comp-stats-code")

#: 步骤级变体表。键为变体名，值为 `skill_name → 替换后的 StepDef`。
#:
#: ⚠️ **设计约束（§3.6 原文）**：*Huawei Cup is the deliberate exception: it has
#: its own graduate-level mechanism and solver-depth Skill, so callers can select
#: it **without duplicating the DAG**.*
#: 所以这里**只做步骤替换**，绝不新增/删除步骤——`comp_huawei` 的步骤数与
#: `comp_cumcm` 完全一致（8 步），差异全部落在两个步骤上：
#:   - 建模求解：研究生级求解深度（同一技能，靠 select 元数据标记分层机制）；
#:   - 论文撰写：换成 `comp-paper-huawei`，绑定**签名模板包**
#:     `comp-paper-zh/templates/huawei`，且缺失时 fail-closed（不得静默降级为通用 ctexart）。
STEP_VARIANTS: dict[str, dict[str, StepDef]] = {
    "huawei": {
        "comp-modeling": StepDef(
            skill_name="comp-modeling",
            display_name="建模求解（研究生级求解深度）",
            output_files=("MODELING_REPORT.md",),
            primary_output="MODELING_REPORT.md",
            has_checkpoint=True,
            checkpoint_type="feedback",
            variant="huawei",
            select_from="comp-modeling",
        ),
        "comp-paper-zh": StepDef(
            skill_name="comp-paper-huawei",
            display_name="华为杯论文撰写",
            output_files=("paper/main.tex",),
            primary_output="paper/main.tex",
            has_checkpoint=True,
            checkpoint_type="approve",
            variant="huawei",
            select_from="comp-paper-zh",
            template_bundle="comp-paper-zh/templates/huawei",
            fail_closed=True,
        ),
    },
}


def apply_step_variant(
    steps: Iterable[StepDef],
    variant: Optional[str],
) -> tuple[StepDef, ...]:
    """按变体表做**步骤级替换**；步骤数与顺序不变。"""
    out = tuple(steps)
    if not variant:
        return out
    table = STEP_VARIANTS.get(variant)
    if not table:
        return out
    return tuple(table.get(s.skill_name, s) for s in out)


# ---------------------------------------------------------------------------
# 学术 / 资产 / ip 族的步骤编排
# ---------------------------------------------------------------------------

#: `paper_writing` 卡片内的分支（§3.7 原文 `paper_type`）→ 撰写步技能名。
#: `paper_writing_zh` / `nature_writing` 两个标识符来自前端判定谓词
#: （`[... "paper_writing", "paper_writing_zh", "nature_writing"].includes(e)`），
#: 属【直接提取】；`course_paper` / `course_report` / `competition` 分支复用同族模板名。
ACADEMIC_BRANCH_SKILLS: dict[str, str] = {
    "academic_zh": "paper-writing",
    "academic_en": "paper-writing-en",
    "nature": "nature-writing",
    "competition": "comp-paper-zh",
    "course": "course-paper-writing",
    "course_report": "course-report-writing",
}
DEFAULT_ACADEMIC_BRANCH = "academic_zh"

_ACADEMIC_TAIL: tuple[StepDef, ...] = (
    StepDef(
        skill_name="docx-precheck",
        display_name="成稿合规预检",
        output_files=("DOCX_PRECHECK.md",),
        primary_output="DOCX_PRECHECK.md",
    ),
    StepDef(
        skill_name="docx-export",
        display_name="Word 导出",
        output_files=("paper/main.docx",),
        primary_output="paper/main.docx",
    ),
)


def academic_steps(branch: str = DEFAULT_ACADEMIC_BRANCH) -> tuple[StepDef, ...]:
    """`paper_writing` 学术卡片：规划 → 分析 → 图表 → 撰写 → 预检 → 导出。

    撰写步的技能名由**分支**（`paper_type`）决定——这是卡片内切换的实现方式，
    与华为杯同源的「步骤级 select」思路，而不是为每个分支复制一套序列。
    """
    write_skill = ACADEMIC_BRANCH_SKILLS.get(branch, ACADEMIC_BRANCH_SKILLS[DEFAULT_ACADEMIC_BRANCH])
    return (
        StepDef(
            skill_name="paper-plan",
            display_name="选题与大纲规划",
            output_files=("PAPER_PLAN.md",),
            primary_output="PAPER_PLAN.md",
            has_checkpoint=True,
            checkpoint_type="approve",
        ),
        StepDef(
            skill_name="paper-analysis",
            display_name="数据分析与结果整理",
            output_files=("ANALYSIS.md",),
            primary_output="ANALYSIS.md",
            optional=True,
        ),
        StepDef(
            skill_name="paper-figure",
            display_name="图表生成",
            output_files=("figures/latex_includes.tex",),
            primary_output="figures/",
            optional=True,
        ),
        StepDef(
            skill_name=write_skill,
            display_name="论文撰写",
            output_files=("paper/main.md",),
            primary_output="paper/main.md",
            has_checkpoint=True,
            checkpoint_type="approve",
        ),
        *_ACADEMIC_TAIL,
    )


def thesis_proposal_steps() -> tuple[StepDef, ...]:
    """开题报告：文献调研 → 开题撰写 → 技术路线 → Word导出（§3.7）。"""
    return (
        StepDef(
            skill_name="literature-search",
            display_name="文献调研",
            output_files=("LITERATURE.md",),
            primary_output="LITERATURE.md",
            has_checkpoint=True,
            checkpoint_type="approve",
        ),
        StepDef(
            skill_name="proposal-writing",
            display_name="开题撰写",
            output_files=("paper/main.md",),
            primary_output="paper/main.md",
            has_checkpoint=True,
            checkpoint_type="approve",
        ),
        StepDef(
            skill_name="tech-roadmap",
            display_name="技术路线",
            output_files=("TECH_ROADMAP.md",),
            primary_output="TECH_ROADMAP.md",
            optional=True,
        ),
        _ACADEMIC_TAIL[1],
    )


def literature_review_steps() -> tuple[StepDef, ...]:
    """文献综述：检索 → **真实性验证** → 主题聚类 → 综述撰写 → Word导出（§3.7）。

    「真实性验证」是独立步骤而非提示词要求——文献造假必须被单独拦一道。
    """
    return (
        StepDef(
            skill_name="literature-search",
            display_name="文献检索",
            output_files=("LITERATURE.md",),
            primary_output="LITERATURE.md",
        ),
        StepDef(
            skill_name="citation-verify",
            display_name="文献真实性验证",
            output_files=("CITATION_AUDIT.md",),
            primary_output="CITATION_AUDIT.md",
        ),
        StepDef(
            skill_name="topic-cluster",
            display_name="主题聚类",
            output_files=("TOPIC_CLUSTERS.md",),
            primary_output="TOPIC_CLUSTERS.md",
        ),
        StepDef(
            skill_name="survey-writing",
            display_name="综述撰写",
            output_files=("paper/main.md",),
            primary_output="paper/main.md",
            has_checkpoint=True,
            checkpoint_type="approve",
        ),
        _ACADEMIC_TAIL[1],
    )


def course_paper_steps() -> tuple[StepDef, ...]:
    """课程论文：大纲规划 → [可选]数据分析+图表 → 撰写嵌入图 → 审查 → Word导出（§3.7）。"""
    return (
        StepDef(
            skill_name="paper-plan",
            display_name="大纲规划",
            output_files=("PAPER_PLAN.md",),
            primary_output="PAPER_PLAN.md",
        ),
        StepDef(
            skill_name="paper-analysis",
            display_name="数据分析与图表",
            output_files=("figures/latex_includes.tex",),
            primary_output="figures/",
            optional=True,
        ),
        StepDef(
            skill_name="paper-writing",
            display_name="撰写（嵌入图）",
            output_files=("paper/main.md",),
            primary_output="paper/main.md",
        ),
        StepDef(
            skill_name="paper-review",
            display_name="成稿审查",
            output_files=("PAPER_REVIEW.md",),
            primary_output="PAPER_REVIEW.md",
        ),
        _ACADEMIC_TAIL[1],
    )


def course_report_steps() -> tuple[StepDef, ...]:
    """课程报告：事实提取+大纲 → [可选]数据图表 → [可选]架构图 → 撰写 → 审查 → 导出（§3.7）。"""
    return (
        StepDef(
            skill_name="paper-plan",
            display_name="事实提取与大纲",
            output_files=("PAPER_PLAN.md",),
            primary_output="PAPER_PLAN.md",
        ),
        StepDef(
            skill_name="paper-analysis",
            display_name="数据分析与图表",
            output_files=("figures/latex_includes.tex",),
            primary_output="figures/",
            optional=True,
        ),
        StepDef(
            skill_name="paper-figure-drawio",
            display_name="架构图绘制",
            output_files=("figures/latex_includes.tex",),
            primary_output="figures/",
            optional=True,
        ),
        StepDef(
            skill_name="paper-writing",
            display_name="撰写（嵌入图）",
            output_files=("paper/main.md",),
            primary_output="paper/main.md",
        ),
        StepDef(
            skill_name="paper-review",
            display_name="成稿审查",
            output_files=("PAPER_REVIEW.md",),
            primary_output="PAPER_REVIEW.md",
        ),
        _ACADEMIC_TAIL[1],
    )


#: `paper_from_assets` 的资产跳过规则（§6.2 docstring 原文）。
#: 键 = 步骤技能名，值 = 「在什么条件下跳过」。
#: 动机是**不重跑覆盖用户已有产出**，而不是省时间。
ASSET_SKIP_RULES: dict[str, str] = {
    "paper-analysis": "用户已传 code + results 时跳过（不要重跑覆盖）",
    "paper-figure": "用户已传 figures 且 `missing_assets` 未标识缺图时跳过",
    "paper-figure-drawio": "`figures/` 下已有 `fig_roadmap.*` 或 `missing_assets` 未提及 roadmap 时跳过",
}


def from_assets_steps() -> tuple[StepDef, ...]:
    """从已有资料写论文：资产盘点 → 缺什么补什么 → 成文（§3.4 + AUTO-RECOVER 白名单）。"""
    return (
        StepDef(
            skill_name="assets-inventory",
            display_name="资产盘点",
            output_files=("_assets_index.json",),
            primary_output="_assets_index.json",
            has_checkpoint=True,
            checkpoint_type="assets_resolve",
        ),
        StepDef(
            skill_name="paper-plan",
            display_name="论文规划",
            output_files=("PAPER_PLAN.md",),
            primary_output="PAPER_PLAN.md",
        ),
        StepDef(
            skill_name="paper-analysis",
            display_name="代码与结果整理",
            output_files=("ANALYSIS.md",),
            primary_output="ANALYSIS.md",
            optional="paper-analysis" in ASSET_SKIP_RULES,
        ),
        StepDef(
            skill_name="paper-figure",
            display_name="数据图生成",
            output_files=("figures/latex_includes.tex",),
            primary_output="figures/",
            optional="paper-figure" in ASSET_SKIP_RULES,
        ),
        StepDef(
            skill_name="paper-figure-drawio",
            display_name="架构图绘制",
            output_files=("figures/latex_includes.tex",),
            primary_output="figures/",
            optional="paper-figure-drawio" in ASSET_SKIP_RULES,
        ),
        StepDef(
            skill_name="paper-writing",
            display_name="论文撰写",
            output_files=("paper/main.md",),
            primary_output="paper/main.md",
            has_checkpoint=True,
            checkpoint_type="approve",
        ),
        _ACADEMIC_TAIL[1],
    )


def copyright_material_steps() -> tuple[StepDef, ...]:
    """软著申请资料（§3.8）：业务理解 → 合成示例源码 → 申请表 → 操作手册 → Word/TXT。"""
    return (
        StepDef(
            skill_name="copyright-understanding",
            display_name="业务理解",
            output_files=("software_overview.md",),
            primary_output="software_overview.md",
        ),
        StepDef(
            skill_name="copyright-source",
            display_name="合成示例源码",
            output_files=("code/main.py",),
            primary_output="code/main.py",
        ),
        StepDef(
            skill_name="copyright-form",
            display_name="申请表",
            output_files=("copyright_application.md",),
            primary_output="copyright_application.md",
        ),
        StepDef(
            skill_name="copyright-manual",
            display_name="操作手册",
            output_files=("user_manual.md",),
            primary_output="user_manual.md",
            has_checkpoint=True,
            checkpoint_type="approve",
        ),
        _ACADEMIC_TAIL[1],
    )


def patent_disclosure_steps() -> tuple[StepDef, ...]:
    """专利交底书（§3.8）：背景 → 技术方案(含 mermaid) → 保护点 → 渲染图示导出 Word。"""
    return (
        StepDef(
            skill_name="patent-background",
            display_name="背景技术",
            output_files=("patent_background.md",),
            primary_output="patent_background.md",
        ),
        StepDef(
            skill_name="patent-solution",
            display_name="技术方案（含 mermaid 框图/流程图）",
            output_files=("patent_solution.md", "figures/latex_includes.tex"),
            primary_output="patent_solution.md",
            has_checkpoint=True,
            checkpoint_type="approve",
        ),
        StepDef(
            skill_name="patent-claims",
            display_name="保护点",
            output_files=("patent_claims.md",),
            primary_output="patent_claims.md",
        ),
        _ACADEMIC_TAIL[1],
    )


#: 编排键 → 构造器。22 个竞赛模板只用到前 3 个。
SEQUENCE_BUILDERS: dict[str, Callable[[], tuple[StepDef, ...]]] = {
    registry.SEQ_COMP_ZH: comp_zh_steps,
    registry.SEQ_COMP_EN: comp_en_steps,
    registry.SEQ_COMP_STATS: comp_stats_steps,
    registry.SEQ_ACADEMIC: academic_steps,
    registry.SEQ_THESIS_PROPOSAL: thesis_proposal_steps,
    registry.SEQ_LITERATURE_REVIEW: literature_review_steps,
    registry.SEQ_COURSE_PAPER: course_paper_steps,
    registry.SEQ_COURSE_REPORT: course_report_steps,
    registry.SEQ_FROM_ASSETS: from_assets_steps,
    registry.SEQ_COPYRIGHT: copyright_material_steps,
    registry.SEQ_PATENT: patent_disclosure_steps,
}


def build_sequence(key: str, *, branch: Optional[str] = None) -> tuple[StepDef, ...]:
    """按编排键构造步骤链；未知键回退到通用中文序列。"""
    builder = SEQUENCE_BUILDERS.get(key)
    if builder is None:
        return comp_zh_steps()
    if key == registry.SEQ_ACADEMIC:
        return academic_steps(branch or DEFAULT_ACADEMIC_BRANCH)
    return builder()


def _build_skill_primary_index() -> dict[str, str]:
    """技能名 → 声明的主产物（覆盖全部编排 + 全部变体）。

    为什么需要：`check_primary_output` 原来只在 `comp_zh_steps()` / `comp_en_steps()`
    里找步骤，于是**华为杯与学术/资产/ip 族的技能全部查不到**，
    静默返回「该步骤无主产物约束」——门控形同虚设。
    """
    index: dict[str, str] = {}
    for key in registry.SEQUENCES:
        try:
            steps = build_sequence(key)
        except Exception:  # noqa: BLE001 - 单个编排坏了不该拖垮索引
            continue
        for s in steps:
            if s.primary_output:
                index.setdefault(s.skill_name, s.primary_output)
    for table in STEP_VARIANTS.values():
        for s in table.values():
            if s.primary_output:
                index.setdefault(s.skill_name, s.primary_output)
    return index


#: 全部技能（含变体）的主产物索引
_SKILL_PRIMARY_OUTPUT: dict[str, str] = _build_skill_primary_index()


# ---------------------------------------------------------------------------
# 每步契约（阈值全部来自内省真值）
# ---------------------------------------------------------------------------

#: 主产物最低字节阈值；低于此值判定步骤未真实产出
MIN_SIZE_FOR: dict[str, int] = {
    "comp-prob-analysis": 1500,
    "comp-modeling": 2000,
    "comp-code": 1000,
    "paper-figure": 500,
    "paper-figure-drawio": 500,
    "comp-review": 40,
    "comp-paper-zh": 10000,
    "comp-paper-en": 10000,
    "comp-compile-zh": 30000,
    "comp-compile-en": 30000,
    # --- 以下为**本项目衍生值**（非蓝方恢复真值），只补有明确同档参照的步骤 ---
    # 选题规划：与 comp-prob-analysis 同档（题目分析的产物体量相近）
    "comp-topic-plan": 1500,
    # 数据采集分析：与 comp-code 同档（同一主产物 RESULTS.md）
    "comp-data-analysis": 1000,
    "comp-stats-code": 1000,
    # 学术/资产/ip 族的上表未列技能一律走 DEFAULT_MIN_SIZE：
    # 它们的成稿质量由 docx 链路与视觉门负责，这里不编造阈值。
}
DEFAULT_MIN_SIZE = 100

#: 必须同时存在的二级文件。仅「编程实现」有强约束——
#: 它必须同时产出入口代码与机器可读的原始结果，
#: 后者是防幻觉机制的数据锚点（数值必须从它读取，而非由模型誊抄）。
REQUIRED_COMPANIONS: dict[str, tuple[str, ...]] = {
    "comp-code": ("code/main.py", "figures/all_results.json"),
    # 统计建模的「数据采集分析」步与 comp-code 是同一契约：
    # 只要它产数值结论，就必须留下机器可读的原始结果，否则审计无从下手。
    "comp-data-analysis": ("code/main.py", "figures/all_results.json"),
    "comp-stats-code": ("code/main.py", "figures/all_results.json"),
}
MIN_COMPANION_BYTES = 50

#: 静默（无输出）超时秒数。只约束静默时长，不限制可见工作总时长。
INACTIVITY_TIMEOUT: dict[str, int] = {
    "comp-prob-analysis": 5400,
    "comp-modeling": 5400,
    "comp-code": 5400,
    "paper-figure": 5400,
    "paper-figure-drawio": 5400,
    "comp-review": 5400,
    "comp-paper-zh": 2700,
    "comp-paper-en": 2700,
    "comp-compile-zh": 2700,
    "comp-compile-en": 2700,
    # --- 本项目衍生值：统计建模前两步属「创作型」（分析/求解）档 ---
    "comp-topic-plan": 5400,
    "comp-data-analysis": 5400,
    "comp-stats-code": 5400,
}
DEFAULT_INACTIVITY_TIMEOUT = 5400

#: 终稿页数参考值。全部为 advisory——只对用户可见，
#: **绝不**作为生成 / 扩展 / 压缩的门控（蓝方 docstring 明确的设计意图）。
#:
#: 由注册表派生：22 个竞赛模板的页数与 §3.2 表格逐行一致，
#: 学术/资产/ip 族无参考值（`None`）。
PAGE_LIMIT: dict[str, Optional[int]] = {s.value: s.pages for s in registry.ALL_TEMPLATES}
PAGE_RULE_MODE = "advisory_max"

#: 正文字符预算（内省真值）。用于页数的保守预检。
CHARS_PER_PAGE_ZH = 800
CHARS_PER_PAGE_EN = 2200


# ---------------------------------------------------------------------------
# 单步超时分级（蓝方 `_step_inactivity_timeout` 的分档语义）
# ---------------------------------------------------------------------------
#
# 为什么必须分级：实测踩过「一刀切的上限误杀合法长步」——
# `run_full_pipeline.py:183` 记录 comp-code 跑了 25 分钟被脚本判超时并 break，
# 但那一步其实还在正常推进；写作类步骤实测**单次生成需要 24.5 分钟**，
# 与脚本默认的 25 分钟上限只差 30 秒，边界完全不可用。
#
# 与 `INACTIVITY_TIMEOUT` 的区别（**两个旋钮，别混用**）：
#   - `inactivity_timeout()`：静默（无输出）上限，取自蓝方恢复真值（2700 / 5400）；
#   - `tiered_inactivity_timeout()`：**单步总预算**按步骤类型分级。

#: 写作类 40 分钟。与 `run_full_pipeline.py --step-deadline-min`（默认 40）一致。
WRITE_STEP_TIMEOUT = 2400
#: 分析类 15 分钟。与 `agent_runtime.RunSpec.inactivity_timeout_s` 默认值一致。
ANALYSIS_STEP_TIMEOUT = 900
#: 计算/图表类 30 分钟。
COMPUTE_STEP_TIMEOUT = 1800
#: 编译/导出类 15 分钟（工具型步骤，卡住要早发现）。
COMPILE_STEP_TIMEOUT = 900
#: 未知技能取**最长档**：宁可多等，也不要因为没登记就掐断合法工作。
UNKNOWN_STEP_TIMEOUT = WRITE_STEP_TIMEOUT

STEP_TIMEOUT_TIERS: dict[str, int] = {
    "writing": WRITE_STEP_TIMEOUT,
    "analysis": ANALYSIS_STEP_TIMEOUT,
    "compute": COMPUTE_STEP_TIMEOUT,
    "compile": COMPILE_STEP_TIMEOUT,
    "default": UNKNOWN_STEP_TIMEOUT,
}
DEFAULT_STEP_TIER = "default"

#: 精确归类（优先于前缀规则）。
STEP_TIER_BY_SKILL: dict[str, str] = {
    # 写作类
    "comp-paper-zh": "writing",
    "comp-paper-en": "writing",
    "comp-paper-huawei": "writing",
    "paper-writing": "writing",
    "paper-writing-en": "writing",
    "nature-writing": "writing",
    "proposal-writing": "writing",
    "survey-writing": "writing",
    "patent-solution": "writing",
    "patent-claims": "writing",
    # 分析类
    "comp-prob-analysis": "analysis",
    "comp-modeling": "analysis",
    "comp-review": "analysis",
    "comp-topic-plan": "analysis",
    "paper-plan": "analysis",
    "paper-review": "analysis",
    "assets-inventory": "analysis",
    "literature-search": "analysis",
    "citation-verify": "analysis",
    "topic-cluster": "analysis",
    "tech-roadmap": "analysis",
    "patent-background": "analysis",
    "copyright-understanding": "analysis",
    # 计算/图表类
    "comp-code": "compute",
    "comp-data-analysis": "compute",
    "comp-stats-code": "compute",
    "paper-analysis": "compute",
    "paper-figure": "compute",
    "paper-figure-drawio": "compute",
    "comp-arch-figure": "compute",
    "copyright-source": "compute",
    "copyright-form": "compute",
    "copyright-manual": "compute",
    # 编译/导出类
    "comp-compile-zh": "compile",
    "comp-compile-en": "compile",
    "docx-precheck": "compile",
    "docx-export": "compile",
}

#: 前缀兜底规则（按序匹配，先命中者生效）——为**未逐一登记**的技能名分层。
_TIER_PREFIX_RULES: tuple[tuple[str, str], ...] = (
    ("comp-compile", "compile"),
    ("docx-", "compile"),
    ("comp-paper", "writing"),
    ("comp-prob-analysis", "analysis"),
    ("comp-modeling", "analysis"),
    ("comp-review", "analysis"),
    ("comp-topic-plan", "analysis"),
    ("comp-code", "compute"),
    ("comp-data-analysis", "compute"),
    ("comp-stats-code", "compute"),
    ("comp-arch-figure", "compute"),
    ("paper-plan", "analysis"),
    ("paper-figure", "compute"),
    ("paper-analysis", "compute"),
    ("paper-review", "analysis"),
    ("paper-writing", "writing"),
    ("nature-writing", "writing"),
    ("literature-", "analysis"),
    ("copyright-", "compute"),
    ("patent-", "writing"),
)


def timeout_tier(skill_name: object) -> str:
    """把技能名归入超时档位：writing / analysis / compute / compile / default。

    未知技能返回 ``"default"``（**最长档**），不抛异常——
    分级只影响等待时长，任何情况下都不该因为「名字没登记」而打断步骤。
    """
    if not isinstance(skill_name, str):
        raw = getattr(skill_name, "value", None)
        skill_name = raw if isinstance(raw, str) else ""
    skill = skill_name.strip().lower()
    if not skill:
        return DEFAULT_STEP_TIER
    tier = STEP_TIER_BY_SKILL.get(skill)
    if tier:
        return tier
    for prefix, mapped in _TIER_PREFIX_RULES:
        if skill.startswith(prefix):
            return mapped
    return DEFAULT_STEP_TIER


def tiered_inactivity_timeout(skill_name: object) -> int:
    """单步**总预算**（秒），按 `timeout_tier` 分级。

    用途：脚本的单步 deadline、`RunSpec.timeout_s`。
    不变量：``tiered_inactivity_timeout(s) <= inactivity_timeout(s)``——
    总预算不应超过「静默上限」这一更宽松的真值（否则分级失去意义）。
    """
    return STEP_TIMEOUT_TIERS.get(timeout_tier(skill_name), UNKNOWN_STEP_TIMEOUT)


#: 约定常量
AI_DISCLOSURE_PDF_NAME = "AI工具使用详情.pdf"
CORE_FAILURE = "[CORE_ARTIFACT] "
ADVISORY_REPAIR_PREFIX = "[OPTIONAL_OPTIMIZATION]"
COMPACT_INDEX_MAX_CHARS = 6000
#: FIGURE_MANIFEST 条目形如 `- fig_xxx` / `- tikz_xxx`
MANIFEST_ITEM_RE = r"^[ \t]*-[ \t]+(fig_[A-Za-z0-9_]+|tikz_[A-Za-z0-9_]+)"
#: 图表文件名约定（内省真值：fig_* 为数据图，tikz_* 为架构图）
_FIGURE_NAME_RE = re.compile(r"^(fig_|tikz_)")
_FIGURE_EXTS = {".png", ".pdf", ".svg", ".drawio"}


# ---------------------------------------------------------------------------
# 质量门
# ---------------------------------------------------------------------------


@dataclass
class GateResult:
    """门控结果。

    与蓝方的布尔返回值相比，这里显式区分**失败原因类别**：
    `unavailable`（检查器不可用，不能据此判论文有错）与真实缺陷必须分开，
    否则会把「工具坏了」误判成「产出不合格」并触发无意义的修复循环。
    """

    ok: bool
    reason: str = ""
    unavailable: bool = False
    missing: Sequence[str] = field(default_factory=tuple)


class StepCheckPendingError(Exception):
    """检查器不可用或未就绪；不可据此判定步骤失败。"""

    def __init__(self, reason: str, *, unavailable: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.unavailable = unavailable


def min_size_for(skill_name: str) -> int:
    return MIN_SIZE_FOR.get(skill_name, DEFAULT_MIN_SIZE)


def inactivity_timeout(skill_name: str, *, tiered: bool = False) -> int:
    """静默（无输出）超时；``tiered=True`` 时改用单步总预算分级。

    ⚠️ 默认路径保持蓝方恢复真值不变（调用方 `workflow_service` / `step_runner`
    依赖它）。要按步骤类型放宽/收紧，请显式走 `tiered_inactivity_timeout()`。
    """
    if tiered:
        return tiered_inactivity_timeout(skill_name)
    return INACTIVITY_TIMEOUT.get(skill_name, DEFAULT_INACTIVITY_TIMEOUT)


def required_companions_for(skill_name: str) -> tuple[str, ...]:
    return REQUIRED_COMPANIONS.get(skill_name, ())


def resolve_page_rule(template: object) -> tuple[Optional[int], str]:
    """返回 (页数参考值, 模式)。模式恒为 advisory_max。

    页数来自注册表（§3.2 表格逐行照录）。未知 value → ``None``：
    没有参考值，也**绝不**阻断（§3.5）。
    """
    return registry.pages_for(template), PAGE_RULE_MODE


#: 未知模板的降级序列：通用中文竞赛序列。
FALLBACK_SEQUENCE = registry.SEQ_COMP_ZH


def _docx_target(path: str) -> str:
    """Word 模式下的产物替换规则。

    - ``paper/main.tex`` → ``paper/main.md``：正文改由 Markdown 装配
      （引擎 `build_paper` 只认 `paper/sections/*.md` / `paper/main.md`）；
    - ``paper/main.pdf`` → ``paper/main.docx``：Word 链路的成稿是 .docx，**不是**
      .pdf 也不是 .md。旧实现把编译步的主产物也改写成 `paper/main.md`，
      导致「成稿步骤的契约变成正文文件」——这是本次修掉的一处逻辑错配。
    """
    if not path.startswith("paper/main."):
        return path
    if path.endswith(".tex"):
        return path[: -len(".tex")] + ".md"
    if path.endswith(".pdf"):
        return path[: -len(".pdf")] + ".docx"
    return path


def _to_docx(steps: Iterable[StepDef]) -> tuple[StepDef, ...]:
    """Word 模式：论文主产物走 Markdown/Word 链路，其余字段不变。"""
    out: list[StepDef] = []
    for s in steps:
        out.append(
            StepDef(
                skill_name=s.skill_name,
                display_name=s.display_name,
                output_files=tuple(_docx_target(f) for f in s.output_files),
                primary_output=_docx_target(s.primary_output) if s.primary_output else s.primary_output,
                has_checkpoint=s.has_checkpoint,
                checkpoint_type=s.checkpoint_type,
                variant=s.variant,
                select_from=s.select_from,
                template_bundle=s.template_bundle,
                fail_closed=s.fail_closed,
                optional=s.optional,
            )
        )
    return tuple(out)


def resolve_template(
    template: object,
    *,
    docx_mode: bool = False,
    huawei: bool = False,
    branch: Optional[str] = None,
) -> TemplateDef:
    """把模板名解析为一条完整流水线。

    这是**步骤的唯一来源**：数据库步骤行由它派生，
    绝不从别处单独维护一份，避免 step_index 错位。

    解析契约（**任何输入都不抛异常**）：

    1. 输入先经 `template_registry.coerce_value` 归一化——``str``、
       ``enum.Enum``（如 `TemplateType`）、带空白/大小写差异的字符串都接受；
    2. 命中注册表 → 用该条目的 ``sequence`` 构造步骤链，并带上
       ``label / lang / pages / stars / group``；
    3. **未命中 → 回退通用中文序列 + ``degraded=True``**（记录原因），不崩；
    4. ``comp_huawei``（或显式 ``huawei=True``）→ 步骤级变体，**步骤数不变**；
    5. ``docx_mode`` 只把论文主产物后缀从 ``.tex`` 换成 ``.md``，不改步骤序列。
    """
    value = registry.coerce_value(template)
    spec = registry.get(value) if value else None
    degraded = spec is None
    reason = ""
    if degraded:
        shown = str(template) if template is not None else "None"
        reason = f"未知模板 {shown!r}（归一化后 {value!r}），已回退通用中文竞赛序列"

    sequence = spec.sequence if spec else FALLBACK_SEQUENCE
    variant = spec.variant if spec else None
    if huawei:
        variant = "huawei"

    if sequence == registry.SEQ_COMP_ZH and variant == "huawei":
        # 华为杯：**复用** comp_zh 序列，只在步骤级替换两处契约
        steps = comp_zh_steps(variant="huawei")
    else:
        steps = build_sequence(sequence, branch=branch)

    if docx_mode:
        steps = _to_docx(steps)

    name = value or ""
    return TemplateDef(
        pipeline_skill=f"pipeline-{name or 'unknown'}",
        display_name=name,
        sub_steps=steps,
        template_value=name,
        label=spec.label if spec else "",
        lang=spec.lang if spec else "zh",
        pages=spec.pages if spec else None,
        stars=spec.stars if spec else 0,
        group=spec.group if spec else registry.GROUP_GENERIC,
        sequence=sequence,
        variant=variant,
        degraded=degraded,
        degraded_reason=reason,
    )


def check_step_companions(workspace: Path, skill_name: str) -> GateResult:
    """校验必填二级文件：存在且 > 50 字节（防空文件占位）。"""
    required = required_companions_for(skill_name)
    if not required:
        return GateResult(ok=True)
    missing: list[str] = []
    for rel in required:
        p = workspace / rel
        if not p.is_file():
            missing.append(rel)
            continue
        try:
            if p.stat().st_size <= MIN_COMPANION_BYTES:
                missing.append(f"{rel} (仅 {p.stat().st_size} 字节, 疑似空文件占位)")
        except OSError:
            missing.append(f"{rel} (无法读取)")
    if missing:
        return GateResult(ok=False, reason="二级文件不齐全", missing=tuple(missing))
    return GateResult(ok=True)


# ---------------------------------------------------------------------------
# 正文来源解析（与 `paper_build.build_paper` 的三段式**逐条对齐**）
# ---------------------------------------------------------------------------

#: 约定格式：正文分节目录。agent 写 `paper/sections/NN_章节名.md`，
#: 由引擎按文件名（两位数字前缀）装配成 `main.tex`。
PAPER_SECTIONS_DIR = "paper/sections"

#: 「论文撰写」步骤。它们的产物是**正文**，而正文有三种合法承载形态，
#: 因此不能用「某个具体文件是否存在」来判主产物。
PAPER_STEP_SKILLS: frozenset[str] = frozenset({
    "comp-paper-zh", "comp-paper-en", "comp-paper-huawei", "paper-writing",
})


def _count_section_files(sec_dir: Path) -> tuple[int, int]:
    """统计 `paper/sections/` 下的分节正文：返回 (字符数, 文件数)。

    字符数取**各分节 strip 后的长度之和**（不注入装配用的空行分隔符）——
    门控的算术要一眼可验：`Σ len(section)`。
    """
    total = 0
    files = 0
    for p in sorted(sec_dir.iterdir()):
        if not p.is_file() or p.suffix.lower() not in (".md", ".markdown", ".tex"):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if not text:
            continue
        total += len(text)
        files += 1
    return total, files


def paper_body_chars(workspace: Path) -> tuple[int, str]:
    """按**引擎与 agent 的格式约定**读正文，返回 ``(字符数, 来源)``。

    来源取值与 `paper_build.PaperDoc.body_source` **同名**，避免两套词汇：

    ============== ==========================================================
    ``sections``    ``paper/sections/*.md``（或 ``*.tex``），按文件名排序 —— 约定格式
    ``main_md``     ``paper/main.md``（读到「## 附录」之前）—— 兼容旧路径
    ``prebuilt_tex`` agent **直出**的成品 ``paper/main.tex``（无引擎生成标记）
                    —— 走「只编译不重建」，正文按该文件计数
    ``none``        三者都没有
    ============== ==========================================================

    ⚠️ 这里必须与 `paper_build.build_paper` 的三段式一致：否则会出现
    「agent 照约定写 `paper/sections/*.md`，却被门控判成没产出」的**两边打架**——
    步骤会被无意义地打回返修。
    """
    ws = Path(workspace)

    # 1) 约定格式：paper/sections/*.md|*.tex
    sec_dir = ws / PAPER_SECTIONS_DIR
    if sec_dir.is_dir():
        chars, _files = _count_section_files(sec_dir)
        if chars:
            return chars, "sections"

    # 2) 兼容路径：paper/main.md（「## 附录」之前为正文）
    main_md = ws / "paper" / "main.md"
    if main_md.is_file():
        try:
            body = main_md.read_text(encoding="utf-8", errors="replace").split("## 附录")[0].strip()
        except OSError:
            body = ""
        if body:
            return len(body), "main_md"

    # 3) agent 直出的成品 paper/main.tex —— 判据与 paper_build 完全一致：
    #    无引擎生成标记 + 自洽可编译（有 \documentclass 与 document 环境）。
    #    引擎自己的产物**不算正文来源**：那是上一次运行的残留，
    #    认它会让「正文被删空」的现场骗过门控。
    main_tex = ws / "paper" / "main.tex"
    if main_tex.is_file():
        try:
            text = main_tex.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        if text.strip():
            body_len = 0
            try:  # 单一真相源：直接复用 paper_build 的判定与正文抽取
                from .paper_build import detect_prebuilt_tex, extract_tex_body

                if detect_prebuilt_tex(ws) is not None:
                    body_len = len(extract_tex_body(text).strip())
            except Exception:  # noqa: BLE001 - 退化为本地结构判据
                if "\\documentclass" in text and "\\begin{document}" in text:
                    body_len = len(text.strip())
            if body_len:
                return body_len, "prebuilt_tex"

    return 0, "none"


def check_primary_output(
    workspace: Path,
    skill_name: str,
    *,
    primary_output: Optional[str] = None,
) -> GateResult:
    """校验主产物存在且达到该技能的最小字节阈值。

    「论文撰写」类步骤（`PAPER_STEP_SKILLS`）走**正文三分支**判定：
    `paper/sections/*.md` 的**总字符数** 与 `paper/main.md`、agent 直出的
    `paper/main.tex` 任一达标即算通过（阈值仍是 `min_size_for(skill)`）。
    其余步骤仍按声明的主产物文件判定。
    """
    if skill_name in PAPER_STEP_SKILLS:
        chars, source = paper_body_chars(workspace)
        threshold = min_size_for(skill_name)
        if source == "none" or not chars:
            return GateResult(
                ok=False,
                reason=(
                    "正文缺失: 未找到 paper/sections/*.md、paper/main.md，"
                    "也没有 agent 直出的 paper/main.tex"
                ),
            )
        if chars < threshold:
            return GateResult(
                ok=False,
                reason=f"正文过小: {source} 共 {chars} 字符 < 阈值 {threshold}（疑似未真实产出）",
            )
        return GateResult(ok=True, reason=f"正文来源 {source}（{chars} 字符）")

    step = next(
        (s for s in comp_zh_steps() + comp_en_steps() if s.skill_name == skill_name),
        None,
    )
    rel = primary_output or (step.primary_output if step else None)
    if not rel:
        # 追加查找：华为杯/学术/资产/ip 族的技能不在上面两条序列里
        rel = _SKILL_PRIMARY_OUTPUT.get(skill_name)
    if not rel:
        return GateResult(ok=True, reason="该步骤无主产物约束")

    target = workspace / rel
    threshold = min_size_for(skill_name)

    if rel.endswith("/"):
        # 目录型主产物（如 figures/）：不能只看「目录里有东西」，
        # 必须存在符合命名约定的图表文件（fig_* / tikz_*），
        # 否则 figures/ 里放一个无关文件就能骗过健康检查。
        if not target.is_dir():
            return GateResult(ok=False, reason=f"主产物目录不存在: {rel}")
        figured = [
            f for f in target.rglob("*")
            if f.is_file()
            and _FIGURE_NAME_RE.match(f.name)
            and f.suffix.lower() in _FIGURE_EXTS
        ]
        if not figured:
            return GateResult(
                ok=False,
                reason=f"主产物目录内无符合约定的图表文件（需 fig_* 或 tikz_*）: {rel}",
            )
        return GateResult(ok=True)

    if not target.is_file():
        return GateResult(ok=False, reason=f"主产物缺失: {rel}")
    size = target.stat().st_size
    if size < threshold:
        return GateResult(
            ok=False,
            reason=f"主产物过小: {rel} {size}B < 阈值 {threshold}B（疑似未真实产出）",
        )
    return GateResult(ok=True)


def check_paper_body_pages(
    workspace: Path,
    *,
    language: str = "zh",
) -> tuple[int, int]:
    """正文页数保守预检。

    正文来源优先级（与 `paper_build.build_paper` 一致，见 `paper_body_chars`）：
      1. `paper/sections/*.md`（或 `*.tex`）总字符数 —— **约定格式**
      2. `paper/main.md` 中「## 附录」之前的部分 —— 兼容旧路径
      3. agent 直出的成品 `paper/main.tex` —— 只编译不重建，正文按它计数

    Returns:
        (估算页数, 正文字符数)。页数仅为**建议值**，不作门控。
    """
    chars, _source = paper_body_chars(workspace)
    per_page = CHARS_PER_PAGE_ZH if language == "zh" else CHARS_PER_PAGE_EN
    return (chars // per_page if per_page else 0), chars


def classify_failure(exc: BaseException) -> str:
    """把异常归类为蓝方定义的三态之一。

    - `unavailable`：检查器不可用 —— 不能据此判产出有错
    - `interrupted`：修复未结束
    - `defect`：真实缺陷
    """
    if isinstance(exc, StepCheckPendingError):
        return "unavailable" if exc.unavailable else "interrupted"
    return "defect"


__all__ = [
    "StepDef",
    "TemplateDef",
    "StepStatus",
    "WorkflowStatus",
    "CheckpointType",
    "TemplateType",
    "GateResult",
    "StepCheckPendingError",
    "registry",
    "comp_zh_steps",
    "comp_en_steps",
    "comp_stats_steps",
    "academic_steps",
    "thesis_proposal_steps",
    "literature_review_steps",
    "course_paper_steps",
    "course_report_steps",
    "from_assets_steps",
    "copyright_material_steps",
    "patent_disclosure_steps",
    "build_sequence",
    "SEQUENCE_BUILDERS",
    "FALLBACK_SEQUENCE",
    "STEP_VARIANTS",
    "apply_step_variant",
    "ACADEMIC_BRANCH_SKILLS",
    "STATS_CODE_SKILLS",
    "ASSET_SKIP_RULES",
    "PAPER_SECTIONS_DIR",
    "PAPER_STEP_SKILLS",
    "paper_body_chars",
    "resolve_template",
    "resolve_page_rule",
    "timeout_tier",
    "tiered_inactivity_timeout",
    "STEP_TIMEOUT_TIERS",
    "STEP_TIER_BY_SKILL",
    "WRITE_STEP_TIMEOUT",
    "ANALYSIS_STEP_TIMEOUT",
    "COMPUTE_STEP_TIMEOUT",
    "COMPILE_STEP_TIMEOUT",
    "min_size_for",
    "inactivity_timeout",
    "required_companions_for",
    "check_step_companions",
    "check_primary_output",
    "check_paper_body_pages",
    "classify_failure",
    "MIN_SIZE_FOR",
    "INACTIVITY_TIMEOUT",
    "REQUIRED_COMPANIONS",
    "PAGE_LIMIT",
    "AI_DISCLOSURE_PDF_NAME",
    "CORE_FAILURE",
    "ADVISORY_REPAIR_PREFIX",
    "COMPACT_INDEX_MAX_CHARS",
    "MANIFEST_ITEM_RE",
    "CHARS_PER_PAGE_ZH",
    "CHARS_PER_PAGE_EN",
]
