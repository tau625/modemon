"""模板注册表 —— 蓝方 30 个产品面模板 + 5 个兼容值。

为什么是「注册表」而不是「22 套 DAG」
------------------------------------
`reports/04-methodology.md` §3.2 给出 22 个竞赛模板的
``value / label / 赛期 / lang / pages / stars``，而 §3.3 证明它们**只由 3 套编排支撑**：

================== ============================================================== ======
``sequence``        步骤链                                                          模板数
================== ============================================================== ======
``comp_zh``         赛题分析 → 建模 → 编程 → 图表 → 流程架构图 → 复核 → 论文 → 编译    18
``comp_en``         Analysis → … → Compile（英文同名双轨）                             4
``comp_stats``      选题规划 → 数据采集分析 → 图表 → 论文 → 编译                        1
================== ============================================================== ======

**`comp_stats` 是唯一编排例外**（§3.2 原文 `【直接提取】`）。

**华为杯不是第 4 套编排**：§3.6 的引擎 docstring 原文说明它是 ``comp_zh`` 上的
步骤级选择（*Huawei Cup is the deliberate exception: it has its own graduate-level
mechanism and solver-depth Skill, so callers can select it without duplicating the
DAG.*）。因此 ``comp_huawei.sequence`` 仍是 ``comp_zh``，只带 ``variant="huawei"``，
由 ``workflow_engine.STEP_VARIANTS`` 在步骤级替换。

证据
----
- 22 行竞赛表：`reports/04-methodology.md` §3.2 `【直接提取】`（前端构建产物注册表数组）
- 学术 5 个：§3.7；``ip`` 2 个：§3.8；``paper_from_assets``：§3.4
- **交叉印证（本次新增）**：`pyc_dump/backend__models__schemas.dis.txt` 里
  反汇编出的原始 ``TemplateType`` 枚举成员与 §3.2 的 22 个 ``comp_*`` **逐一吻合**，
  另含前端产品面未列出的 ``full_pipeline`` / ``humanities_paper`` / ``grad_project``
  三个成员 —— 本模块把它们登记为**兼容值**（``EXTRA_TEMPLATES``），
  以保证「任何调用方传进来的历史值都解析得开、且不降级」。

本模块只放**数据**，不放 ``StepDef``：步骤构造在 `workflow_engine` 里，
避免 ``workflow_engine → template_registry → workflow_engine`` 的循环依赖。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

# ---------------------------------------------------------------------------
# 分组（前端顶部页签 = 互斥产品面，§3.1）
# ---------------------------------------------------------------------------

GROUP_COMPETITION = "competition"
GROUP_ACADEMIC = "academic"
GROUP_FROM_ASSETS = "from_assets"
GROUP_IP = "ip"
#: 兼容值：不在产品页签里，但历史/后端枚举可达
GROUP_GENERIC = "generic"

GROUPS: tuple[str, ...] = (
    GROUP_COMPETITION,
    GROUP_ACADEMIC,
    GROUP_FROM_ASSETS,
    GROUP_IP,
    GROUP_GENERIC,
)

# ---------------------------------------------------------------------------
# 编排键（= 步骤链的唯一真相源，见 `workflow_engine.SEQUENCE_BUILDERS`）
# ---------------------------------------------------------------------------

SEQ_COMP_ZH = "comp_zh"
SEQ_COMP_EN = "comp_en"
SEQ_COMP_STATS = "comp_stats"
SEQ_ACADEMIC = "academic"
SEQ_THESIS_PROPOSAL = "thesis_proposal"
SEQ_LITERATURE_REVIEW = "literature_review"
SEQ_COURSE_PAPER = "course_paper"
SEQ_COURSE_REPORT = "course_report"
SEQ_FROM_ASSETS = "from_assets"
SEQ_COPYRIGHT = "copyright_material"
SEQ_PATENT = "patent_disclosure"

SEQUENCES: tuple[str, ...] = (
    SEQ_COMP_ZH,
    SEQ_COMP_EN,
    SEQ_COMP_STATS,
    SEQ_ACADEMIC,
    SEQ_THESIS_PROPOSAL,
    SEQ_LITERATURE_REVIEW,
    SEQ_COURSE_PAPER,
    SEQ_COURSE_REPORT,
    SEQ_FROM_ASSETS,
    SEQ_COPYRIGHT,
    SEQ_PATENT,
)

#: 22 个竞赛模板共用这 3 套编排 —— 这是本模块最重要的结构事实。
COMPETITION_SEQUENCES: tuple[str, ...] = (SEQ_COMP_ZH, SEQ_COMP_EN, SEQ_COMP_STATS)


@dataclass(frozen=True, slots=True)
class TemplateSpec:
    """一个模板的注册表条目。

    字段与前端注册表 ``{value, icon, label, desc, time, lang, pages, stars, group}``
    一一对应，并补上本项目自用的 ``sequence`` / ``variant`` / ``branches``。
    """

    value: str
    label: str
    #: 赛期：`3月` / `4-5月` / `7-9月`；非季节性模板为空串
    month: str
    lang: str
    #: 页数参考值。**仅 advisory**（§3.5：绝不作生成/扩展/压缩门控）；None = 无参考值
    pages: Optional[int]
    #: 推荐星级。竞赛模板为 0-5（§3.2）；非竞赛模板无此语义，恒为 0
    stars: int
    group: str
    #: 编排键，取值见 `SEQUENCES`
    sequence: str
    #: 原文 `desc`（前端紧凑步骤表达）
    desc: str = ""
    #: 原文 `time`
    est_time: str = ""
    #: 步骤级变体键（如 `huawei`），由 `workflow_engine.STEP_VARIANTS` 解释
    variant: Optional[str] = None
    #: 卡片内可切换的分支（§3.7 `paper_type`）
    branches: tuple[str, ...] = ()
    #: 国赛 2025+ 的 AI 使用申报硬闸（§3.9）
    requires_ai_disclosure: bool = False
    #: 证据强度备注（哪些字段是【直接提取】，哪些是【推断】）
    note: str = ""


# ---------------------------------------------------------------------------
# 22 个竞赛模板（reports/04-methodology.md §3.2，逐行照录）
# ---------------------------------------------------------------------------

_COMPETITION: tuple[TemplateSpec, ...] = (
    TemplateSpec("comp_tianfu", "天府杯", "3月", "zh", 30, 4, GROUP_COMPETITION, SEQ_COMP_ZH),
    TemplateSpec("comp_certcup", "认证杯", "4-5月", "zh", 35, 3, GROUP_COMPETITION, SEQ_COMP_ZH),
    TemplateSpec("comp_mathorcup", "MathorCup", "4月", "zh", 30, 4, GROUP_COMPETITION, SEQ_COMP_ZH),
    TemplateSpec("comp_teddy", "泰迪杯", "4月", "zh", 40, 3, GROUP_COMPETITION, SEQ_COMP_ZH),
    TemplateSpec("comp_huadong", "华东杯", "4-5月", "zh", 30, 2, GROUP_COMPETITION, SEQ_COMP_ZH),
    TemplateSpec("comp_huazhong", "华中杯", "4-5月", "zh", 30, 2, GROUP_COMPETITION, SEQ_COMP_ZH),
    TemplateSpec("comp_wuyi", "五一杯", "5月", "zh", 30, 3, GROUP_COMPETITION, SEQ_COMP_ZH),
    TemplateSpec("comp_zhongqing", "中青杯", "5月", "zh", 30, 3, GROUP_COMPETITION, SEQ_COMP_ZH),
    TemplateSpec("comp_yangtze", "长三角", "5月", "zh", 30, 2, GROUP_COMPETITION, SEQ_COMP_ZH),
    # ★ 唯一编排例外：重数据采集，5 步
    TemplateSpec("comp_stats", "统计建模大赛", "5月", "zh", 30, 3, GROUP_COMPETITION, SEQ_COMP_STATS),
    TemplateSpec("comp_shuwei", "数维杯", "5月", "zh", 30, 3, GROUP_COMPETITION, SEQ_COMP_ZH),
    TemplateSpec("comp_diangong", "电工杯", "5-6月", "zh", 30, 4, GROUP_COMPETITION, SEQ_COMP_ZH),
    TemplateSpec("comp_liaoning", "辽宁省/东三省", "6月", "zh", 30, 2, GROUP_COMPETITION, SEQ_COMP_ZH),
    TemplateSpec("comp_apmcm_zh", "亚太赛中文 (APMCM)", "6月", "zh", 25, 3, GROUP_COMPETITION, SEQ_COMP_ZH),
    TemplateSpec("comp_shenzhen", "深圳杯", "7-9月", "zh", 30, 4, GROUP_COMPETITION, SEQ_COMP_ZH),
    TemplateSpec("comp_huashu", "华数杯", "8月", "zh", 30, 3, GROUP_COMPETITION, SEQ_COMP_ZH),
    TemplateSpec(
        "comp_cumcm", "国赛 (CUMCM)", "9月", "zh", 30, 5, GROUP_COMPETITION, SEQ_COMP_ZH,
        requires_ai_disclosure=True,
        note="前端对 comp_cumcm 有单独特判：AI 使用记录必须 1-5 条且限定国产工具（§3.9）",
    ),
    TemplateSpec(
        "comp_huawei", "华为杯", "9月", "zh", 50, 5, GROUP_COMPETITION, SEQ_COMP_ZH,
        variant="huawei",
        note="研究生赛；唯一「机制不同」的竞赛，用步骤级 select 而非复制 DAG（§3.6）",
    ),
    TemplateSpec("comp_mcm", "美赛 (MCM/ICM)", "2月", "en", 25, 5, GROUP_COMPETITION, SEQ_COMP_EN),
    TemplateSpec("comp_shuwei_en", "数维杯国际赛", "11月", "en", 25, 3, GROUP_COMPETITION, SEQ_COMP_EN),
    TemplateSpec("comp_apmcm", "亚太 (APMCM)", "11月", "en", 25, 3, GROUP_COMPETITION, SEQ_COMP_EN),
    TemplateSpec("comp_certcup_en", "小美赛 (认证杯国际)", "12月", "en", 25, 3, GROUP_COMPETITION, SEQ_COMP_EN),
)

# ---------------------------------------------------------------------------
# 5 个学术写作模板（§3.7 `【直接提取】` 前端变量 Oe）
# ---------------------------------------------------------------------------

_ACADEMIC: tuple[TemplateSpec, ...] = (
    TemplateSpec(
        "paper_writing", "论文写作", "", "zh", None, 0, GROUP_ACADEMIC, SEQ_ACADEMIC,
        desc="通用学术 / Nature 顶刊 / 人文社科 — 卡片内切换分支，各有专属规划与撰写 skill",
        est_time="~30-120 分钟",
        branches=("academic_zh", "academic_en", "competition", "course", "course_report", "nature"),
        note="humanities_paper 不是独立模板，是本卡片内的一个分支（§3.7 注）",
    ),
    TemplateSpec(
        "thesis_proposal", "开题报告", "", "zh", None, 0, GROUP_ACADEMIC, SEQ_THESIS_PROPOSAL,
        desc="文献调研 → 开题撰写 → 技术路线 → Word导出", est_time="~30-60 分钟",
    ),
    TemplateSpec(
        "literature_review", "文献综述", "", "zh", None, 0, GROUP_ACADEMIC, SEQ_LITERATURE_REVIEW,
        desc="文献检索 → 真实性验证 → 主题聚类 → 综述撰写 → Word导出", est_time="~30-60 分钟",
    ),
    TemplateSpec(
        "course_paper", "课程论文", "", "zh", None, 0, GROUP_ACADEMIC, SEQ_COURSE_PAPER,
        desc="大纲规划 → [可选: 数据分析+图表] → 撰写嵌入图 → 审查 → Word导出",
        est_time="~25-50 分钟",
    ),
    TemplateSpec(
        "course_report", "课程报告", "", "zh", None, 0, GROUP_ACADEMIC, SEQ_COURSE_REPORT,
        desc="事实提取+大纲 → [可选: 数据分析+图表] → [可选: 架构图] → 撰写嵌入图 → 审查 → Word导出",
        est_time="~25-50 分钟",
    ),
)

# ---------------------------------------------------------------------------
# from_assets 1 个（§3.4）+ ip 2 个（§3.8）
# ---------------------------------------------------------------------------

_ASSET_AND_IP: tuple[TemplateSpec, ...] = (
    TemplateSpec(
        "paper_from_assets", "从已有资料写论文", "", "zh", None, 0, GROUP_FROM_ASSETS, SEQ_FROM_ASSETS,
        desc="已有代码/数据/图/结果 → 智能盘点资产 → 缺什么自动补什么 → 生成完整论文",
        est_time="~30-60 分钟",
    ),
    TemplateSpec(
        "copyright_material", "生成软著申请资料", "", "zh", None, 0, GROUP_IP, SEQ_COPYRIGHT,
        desc="一句话描述软件 → AI 撰写业务理解/合成示例源码/申请表/操作手册 → 正式 Word/TXT",
    ),
    TemplateSpec(
        "patent_disclosure", "生成专利交底书", "", "zh", None, 0, GROUP_IP, SEQ_PATENT,
        desc="一句话描述技术 → AI 撰写背景/技术方案(含 mermaid 框图流程图)/保护点 → 渲染图示导出 Word",
    ),
)

# ---------------------------------------------------------------------------
# 兼容值（原始 TemplateType 枚举里有、产品页签里没有）
# ---------------------------------------------------------------------------

_EXTRA: tuple[TemplateSpec, ...] = (
    TemplateSpec(
        "comp_zh", "中文竞赛（通用）", "", "zh", None, 0, GROUP_GENERIC, SEQ_COMP_ZH,
        note="通用中文竞赛序列；`comp_*` 未收录值的历史兜底名",
    ),
    TemplateSpec(
        "comp_en", "英文竞赛（通用）", "", "en", None, 0, GROUP_GENERIC, SEQ_COMP_EN,
        note="通用英文竞赛序列",
    ),
    TemplateSpec(
        "full_pipeline", "全流程科研", "", "zh", None, 0, GROUP_GENERIC, SEQ_ACADEMIC,
        note="原始枚举成员（schemas.dis.txt:32）；步骤链未恢复，暂按学术序列承载【推断】",
    ),
    TemplateSpec(
        "humanities_paper", "人文社科论文", "", "zh", None, 0, GROUP_GENERIC, SEQ_ACADEMIC,
        note="原始枚举成员（schemas.dis.txt:62）；前端已并入 paper_writing 分支（§3.7 注）",
    ),
    TemplateSpec(
        "grad_project", "研究生项目", "", "zh", None, 0, GROUP_GENERIC, SEQ_ACADEMIC,
        note="原始枚举成员（schemas.dis.txt:66）；步骤链未恢复，暂按学术序列承载【推断】",
    ),
)

#: 30 个产品面模板：22 竞赛 + 5 学术 + 1 资产 + 2 软著/专利（§3.11 的「内置模板共 30 个」）
TEMPLATES: tuple[TemplateSpec, ...] = _COMPETITION + _ACADEMIC + _ASSET_AND_IP

#: 5 个兼容值
EXTRA_TEMPLATES: tuple[TemplateSpec, ...] = _EXTRA

#: 全部可解析值（35）
ALL_TEMPLATES: tuple[TemplateSpec, ...] = TEMPLATES + EXTRA_TEMPLATES

#: value → spec
TEMPLATE_INDEX: dict[str, TemplateSpec] = {s.value: s for s in ALL_TEMPLATES}

#: 三个产品面的模板数（§3.1）
GROUP_COUNTS: dict[str, int] = {
    GROUP_COMPETITION: 22,
    GROUP_ACADEMIC: 5,
    GROUP_FROM_ASSETS: 1,
    GROUP_IP: 2,
    GROUP_GENERIC: 5,
}


# ---------------------------------------------------------------------------
# 查询 API
# ---------------------------------------------------------------------------


def coerce_value(raw: object) -> Optional[str]:
    """把任意输入归一化成注册表 ``value``。

    为什么需要它：调用方可能传 ``str``、``enum.Enum``（如 ``TemplateType``）、
    ``None``，或带空白/大小写差异的字符串。**本函数绝不抛异常**——
    未知名一律返回 ``None``，由调用方决定降级策略。

    这也是 ``resolve_template("comp_tianfu")`` 一类崩溃的根因修复点：
    旧实现直接 ``template.startswith(...)``，遇到 ``None`` / 枚举 / 非字符串
    就是 ``AttributeError`` / ``TypeError``。
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        val = raw
    else:
        inner = getattr(raw, "value", None)
        if isinstance(inner, str):
            val = inner
        elif isinstance(raw, (int, float, bool)) or raw is Ellipsis:
            return None
        else:
            try:
                val = str(raw)
            except Exception:  # pragma: no cover - 极端对象
                return None
    val = val.strip().lower()
    return val or None


def get(raw: object) -> Optional[TemplateSpec]:
    """按 value（或其等价输入）取条目；未知返回 ``None``。"""
    value = coerce_value(raw)
    if value is None:
        return None
    return TEMPLATE_INDEX.get(value)


def is_known(raw: object) -> bool:
    return get(raw) is not None


def values(group: Optional[str] = None) -> tuple[str, ...]:
    """全部可解析 value（可按产品面过滤）。"""
    if group is None:
        return tuple(s.value for s in ALL_TEMPLATES)
    return tuple(s.value for s in ALL_TEMPLATES if s.group == group)


def specs(group: Optional[str] = None) -> tuple[TemplateSpec, ...]:
    if group is None:
        return ALL_TEMPLATES
    return tuple(s for s in ALL_TEMPLATES if s.group == group)


def pages_for(raw: object) -> Optional[int]:
    """页数参考值。未知 value → ``None``（页数只提示、不阻断，§3.5）。"""
    spec = get(raw)
    return spec.pages if spec else None


def requires_ai_disclosure(raw: object) -> bool:
    """国赛硬闸（§3.9）。"""
    spec = get(raw)
    return bool(spec and spec.requires_ai_disclosure)


def iter_competition() -> Iterable[TemplateSpec]:
    return (s for s in ALL_TEMPLATES if s.group == GROUP_COMPETITION)


def validate_registry() -> list[str]:
    """自检注册表数据的自洽性，返回问题清单（空 = 通过）。

    这是给测试用的**显式校验**，不在 import 时抛错——
    引擎可以在数据有问题时仍然加载并提供降级行为。
    """
    problems: list[str] = []

    seen: set[str] = set()
    for spec in ALL_TEMPLATES:
        if spec.value in seen:
            problems.append(f"重复 value: {spec.value}")
        seen.add(spec.value)
        if spec.group not in GROUPS:
            problems.append(f"{spec.value}: 未知 group {spec.group}")
        if spec.sequence not in SEQUENCES:
            problems.append(f"{spec.value}: 未知 sequence {spec.sequence}")
        if spec.lang not in ("zh", "en"):
            problems.append(f"{spec.value}: lang 必须为 zh/en，got {spec.lang}")
        if spec.value != spec.value.strip().lower():
            problems.append(f"{spec.value}: value 必须为小写去空白形式")
        if spec.pages is not None and not (5 <= spec.pages <= 200):
            problems.append(f"{spec.value}: pages 异常 {spec.pages}")
        if not (0 <= spec.stars <= 5):
            problems.append(f"{spec.value}: stars 越界 {spec.stars}")
        if spec.group == GROUP_COMPETITION and spec.sequence not in COMPETITION_SEQUENCES:
            problems.append(f"{spec.value}: 竞赛模板必须用 {COMPETITION_SEQUENCES} 之一")
        if spec.group != GROUP_COMPETITION and (spec.stars or spec.month):
            problems.append(f"{spec.value}: 非竞赛模板不应带星级/赛期")

    comp = specs(GROUP_COMPETITION)
    if len(comp) != 22:
        problems.append(f"竞赛模板数应为 22，got {len(comp)}")
    if len(TEMPLATES) != 30:
        problems.append(f"产品面模板数应为 30，got {len(TEMPLATES)}")
    if sum(s.pages is not None for s in comp) != 22:
        problems.append("22 个竞赛模板都必须有页数参考值")
    if len({s.sequence for s in comp}) != 3:
        problems.append("竞赛模板应只由 3 套编排支撑")
    if sum(1 for s in comp if s.sequence == SEQ_COMP_STATS) != 1:
        problems.append("comp_stats 必须是唯一编排例外")
    if not requires_ai_disclosure("comp_cumcm"):
        problems.append("comp_cumcm 必须带 AI 申报硬闸标记")
    if get("comp_huawei").variant != "huawei":  # type: ignore[union-attr]
        problems.append("comp_huawei 必须带 huawei 变体标记")
    if get("comp_huawei").pages != 50:  # type: ignore[union-attr]
        problems.append("comp_huawei 页数必须是 50")
    return problems


__all__ = [
    "TemplateSpec",
    "TEMPLATES",
    "EXTRA_TEMPLATES",
    "ALL_TEMPLATES",
    "TEMPLATE_INDEX",
    "GROUP_COUNTS",
    "GROUPS",
    "SEQUENCES",
    "COMPETITION_SEQUENCES",
    "GROUP_COMPETITION",
    "GROUP_ACADEMIC",
    "GROUP_FROM_ASSETS",
    "GROUP_IP",
    "GROUP_GENERIC",
    "SEQ_COMP_ZH",
    "SEQ_COMP_EN",
    "SEQ_COMP_STATS",
    "SEQ_ACADEMIC",
    "SEQ_THESIS_PROPOSAL",
    "SEQ_LITERATURE_REVIEW",
    "SEQ_COURSE_PAPER",
    "SEQ_COURSE_REPORT",
    "SEQ_FROM_ASSETS",
    "SEQ_COPYRIGHT",
    "SEQ_PATENT",
    "coerce_value",
    "get",
    "is_known",
    "values",
    "specs",
    "pages_for",
    "requires_ai_disclosure",
    "iter_competition",
    "validate_registry",
]
