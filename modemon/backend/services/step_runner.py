"""步骤执行器：把「运行时 + 工作区 + 质量门」接成一条可执行的步骤。

执行序
------
1. **工作区守卫**——先消除环境注入面（`.mcp.json` 等），再谈执行。
2. **能力协商**——问运行时"你能做到哪些"，不能做到的记入 `degraded`，
   并在**严格模式**下直接拒绝（宁可不跑，也不在无约束下跑）。
3. **构建提示**——步骤契约 + 工作区上下文，带字符预算。
4. **流式执行**——产出事件；静默超时只约束"无声"时长。
5. **质量门**——主产物阈值、二级文件；结果**结构化**，
   区分「产出不合格」与「检查器不可用」。

设计要点
--------
蓝方把所有约束寄生在 CLI 参数上，一旦厂商改语义就静默失效。
本执行器把约束分成三层，任一层失效都不会让其余层一起沉默：

    运行时能力（参数级） < 工作区守卫（文件级） < 质量门（产物级）
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Optional

from . import agent_runtime as ar
from . import tool_env as te
from . import workflow_engine as we
from . import workspace_guard as wg


@dataclass
class StepRunRequest:
    """一次步骤执行的请求。"""

    workflow_id: str
    skill_name: str
    workspace: Path

    #: 赛事/模板名，用于解析页数参考值
    template: str = "comp_zh"
    #: 论文语言，决定字符/页预算
    language: str = "zh"

    #: 运行时偏好；None = 自动选择
    runtime: Optional[str] = None
    model: Optional[str] = None
    effort: Optional[str] = None
    resume_session_id: Optional[str] = None

    #: 工具约束（运行时能力允许时生效）
    allowed_tools: Optional[tuple[str, ...]] = None
    disallowed_tools: tuple[str, ...] = ()

    #: 模型链（额度耗尽时依次回退）；空 = 用 DEFAULT_MODEL_CHAIN
    model_chain: tuple[str, ...] = ()

    #: 权限模式。非交互场景必须能写文件，故默认 acceptEdits
    permission_mode: Optional[str] = "acceptEdits"

    max_budget_usd: Optional[float] = 1.0
    #: 严格模式：请求的能力若无法满足则拒绝执行
    strict: bool = True

    extra_prompt: str = ""


@dataclass
class StepRunOutcome:
    ok: bool
    skill_name: str
    runtime: str = ""
    final_text: str = ""
    session_id: Optional[str] = None
    cost_usd: Optional[float] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    duration_s: float = 0.0
    #: 本步**实际生效**的模型快照（落 `workflow_steps.model_used`）
    model_used: Optional[str] = None

    error_code: str = ""
    error: str = ""

    #: 能力降级事实（如 `mcp_isolation`、`effort:xhigh`）
    degraded: list[str] = field(default_factory=list)
    #: 工作区守卫的处置结果
    guard: dict[str, object] = field(default_factory=dict)
    #: 子进程工具环境准备结果（PATH 注入了什么、缺了什么）
    tool_env: dict[str, object] = field(default_factory=dict)
    #: 质量门结果
    gates: list[dict[str, object]] = field(default_factory=list)
    #: 是否因检查器不可用而无法判定（**不可当作失败**）
    inconclusive: bool = False

    event_count: int = 0

    def summary(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "skill_name": self.skill_name,
            "runtime": self.runtime,
            "cost_usd": self.cost_usd,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "duration_s": self.duration_s,
            "model_used": self.model_used,
            "error_code": self.error_code,
            "error": self.error,
            "degraded": list(self.degraded),
            "guard": self.guard,
            "tool_env": self.tool_env,
            "gates": self.gates,
            "inconclusive": self.inconclusive,
            "event_count": self.event_count,
        }


#: 缺了这些能力就不能安全执行（严格模式下拒绝）
CRITICAL_IF_REQUESTED: dict[str, str] = {
    "mcp_isolation": "无法钉住 MCP 配置，工作区可能存在能力注入面",
    "tool_allowlist": "无法限定工具集合，agent 可能调用未授权工具",
}

#: 默认模型链。
#:
#: 额度耗尽/过载时按顺序回退。Claude Code 会经 `--fallback-model` 在**同一次调用内**
#: 自动切换；若整条链都不可用，则由上层循环换下一个模型重试。
#:
#: ⚠️ 必须用 **API 模型 ID**，不是界面显示名。
#: 实测教训：曾把界面上的「MiMo-V2.6-Pro」直接当模型 ID 传进去，
#: 导致全部步骤秒失败 —— `API Error: 400 Unsupported model MiMo-V2.6-Pro`。
#: 真实 ID 是小写的 `mimo-v2.6-pro[1M]` / `mimo-v2.6-flash[1M]`。
#:
#: 可用环境变量 `MODEMON_MODEL_CHAIN` 覆盖（逗号分隔），
#: 以免把某一台机器的服务商配置硬编码进来。
DEFAULT_MODEL_CHAIN: tuple[str, ...] = tuple(
    m.strip() for m in os.environ.get(
        "MODEMON_MODEL_CHAIN",
        "mimo-v2.6-pro[1M],mimo-v2.6-flash[1M]",
    ).split(",") if m.strip()
)

#: 这些错误码表示"换个模型 / 再试一次可能就好了"，值得重试。
#:
#: ⚠️ `INACTIVITY_TIMEOUT` 必须在列：
#: 实测根因是**模型网关停止响应**——agent 发出请求后 600 秒毫无返回
#: （事件序列是 `Read → tool_result`，之后 600s 纯静默）。这既不是子进程挂起，
#: 也不是脚本错误，重试/换模型通常就能过。漏掉这个码会把步骤直接判死。
RETRYABLE_CODES = frozenset({
    "QUOTA_OR_OVERLOAD", "MAX_BUDGET_USD", "NONZERO_EXIT", "INACTIVITY_TIMEOUT",
})

#: 判定"网关无响应"的静默阈值（秒）。
#:
#: 不能太短：合法的长工具调用（如一万次蒙特卡洛、LaTeX 编译）本身就有间隙；
#: 不能太长：早期用 2700s，一个卡住的步骤要等 45 分钟才被发现，
#: 期间整条流水线完全停滞。
#: 实测合法间隙最大约 96s，取 300s 既能容忍又能快速重试。
INACTIVITY_TIMEOUT_S = 300

#: 质量门失败后最多返修几轮。
#:
#: 为什么需要它：实测中 agent 会漏掉约定的产物（例如 `comp-code` 少写
#: `figures/all_results.json`），若直接判步骤失败，整条流水线就断了。
#: 蓝方的 `recover_checked_step`（max_repairs=3 / max_local_rechecks=2 /
#: max_advisory_repairs=1）正是为解决这类问题而存在。
MAX_REPAIRS = 3


#: 最多整体重跑几轮（在模型链之外，针对网关抖动的额外容忍）
MAX_ATTEMPTS = 3


def build_repair_note(failures: list[dict[str, object]]) -> str:
    """把门控失败翻译成**给 agent 的返修指令**。"""
    lines = [
        "",
        "## ⚠️ 上一次没有通过产物检查，请立即补正",
        "",
        "上一次执行**未产出**或**未达标**的内容：",
        "",
    ]
    for f in failures:
        gate = f.get("gate", "")
        reason = str(f.get("reason") or "")
        if gate == "primary_output":
            lines.append(f"- **主产物不合格**：{reason}")
        elif gate == "required_companions":
            miss = f.get("missing") or []
            lines.append(f"- **缺少必需的二级文件**：{reason}")
            for m in miss:  # type: ignore[union-attr]
                lines.append(f"  - `{m}`")
        else:
            lines.append(f"- {gate}：{reason}")
    lines += [
        "",
        "**请只做一件事：把上面列出的文件补出来。**",
        "不要再做探索或额外分析，不要重新做已经完成的部分。",
        "",
    ]
    return "\n".join(lines)


#: 论文撰写类技能——需要一个**产物格式约定**（分节 Markdown，由引擎装配）。
#:
#: 实测背景（P0 根因之一）：`build_paper` 只认 `paper/sections/*.md` /
#: `paper/main.md`，而 agent 直接写 `paper/main.tex`（27,538 B 的成品）。
#: 两边没有约定 → 引擎读到 `body_chars=0`、产出 2 页桩 PDF，并在导出时
#: 覆盖 agent 的成品。让引擎"认 `.tex`"只是治标（见 `paper_build` 的
#: `prebuilt_tex` 路径），**把约定写进提示**才是治本。
PAPER_WRITING_SKILLS = (
    "comp-paper-zh", "comp-paper-en", "comp-paper-huawei", "comp-stats-paper",
)


def build_step_prompt(
    request: StepRunRequest,
    *,
    step: Optional[we.StepDef] = None,
    context_excerpt: str = "",
) -> str:
    """把步骤契约捏成给 agent 的提示。

    明确列出：要产出什么、主产物是什么、最低体量要求、二级文件、
    以及（advisory 的）页数参考。**页数只作为建议呈现，不作硬约束。**
    """
    skill = request.skill_name
    if step is None:
        step = next(
            (s for s in we.comp_zh_steps() + we.comp_en_steps() if s.skill_name == skill),
            None,
        )
    lines = [f"# 任务：{step.display_name if step else skill}", ""]
    lines.append(f"当前步骤技能：`{skill}`")
    lines.append("")
    # ★ 范围纪律：实测中 agent 会跑偏——在"赛题分析"步骤里去解题、反复跑命令，
    #   400 秒烧掉 $1.36 却一个产物都没写出来。必须**显式限定范围**。
    lines += [
        "## 范围（严格遵守）",
        "",
        f"**本步骤只做一件事：产出上面列出的文件。**",
        "",
        "- 不要提前执行后续步骤的工作（例如本步是分析就不要解题、不要写代码）；",
        "- 不要为了「先摸清情况」反复运行命令；读必要的文件即可，**尽早开始写产物**；",
        "- 完成后立即结束，不要继续做可选的优化或补充探索。",
        "",
    ]
    # ★ 对图表类步骤额外设一个**打磨上界**。    #   实测：agent 会自己「编译→渲染→看图→改→再编译」，
    #   这在质量上是对的（相当于视觉自检），但**没有上界**——
    #   paper-figure-drawio 因此跑了 11 分钟仍未收尾并被判静默超时。
    #   给它 2 轮，既保留质量又封顶时间。
    # ★ 对"写代码"的步骤要求**分小段交付**。
    #
    #   实测依据：网关在**长单轮生成**上会卡死——失败都发生在
    #   `Read → tool_result` 之后（即 agent 正要一次性吐出大段代码的时刻），
    #   而短轮次的 Read/Bash 都正常。分小段能把单轮长度压下来，
    #   从源头降低触发概率（重试是兜底，这里是治因）。
    if skill in ("comp-code", "code", "comp-stats-code"):
        lines += [
            "### 代码要分小段交付（重要）",
            "",
            "**不要一次性写出整个脚本**。请拆成多个小步骤，每次只写一小段，",
            "每段写完就停下来确认，再继续下一段。例如：",
            "",
            "1. 先写文件头与数据读取（约 20 行）；",
            "2. 再写求解部分（约 30 行）；",
            "3. 再写结果导出（约 20 行）。",
            "",
            "这样做的原因：单次生成过长会导致执行中断，分段写既安全也便于逐步验证。",
            "",
        ]

    # ★ 流程/架构图**不要手写 TikZ**，改写 FigureSpec JSON。
    #
    #   实测教训：让 agent 手写 TikZ 会陷入「编译→渲染→看图→改」的
    #   无上界循环（每次 20–40 秒），是 paper-figure-drawio 反复卡死的根源。
    #   FigureSpec 是**确定性**的：同一份 JSON → 同一份 SVG，没有迭代。
    #   而且写 JSON 比写 TikZ 容易得多——agent 只需表达**语义**，
    #   渲染交给引擎（ARIS figure-spec，MIT）。
    if skill in ("paper-figure-drawio", "figure", "comp-arch-figure"):
        lines += [
            "### 流程/架构图：写 FigureSpec JSON，不要写 TikZ（重要）",
            "",
            "**不要手写 TikZ 或 LaTeX 图形代码**——请写**声明式的 FigureSpec JSON**，",
            "由引擎确定性渲染成 SVG/PNG。这样不需要反复编译试错。",
            "",
            "**必须产出**：`figures/architecture.spec.json`",
            "",
            "格式要点：",
            "",
            "```json",
            "{",
            '  "title": "求解流程与系统架构",',
            '  "canvas": {"width": 720, "height": 320},',
            '  "style": {"font_family": "SimHei, sans-serif", "font_size": 14,',
            '            "bg_color": "#FFFFFF",',
            '            "palette": ["#4477AA", "#EE6677", "#228833"]},',
            '  "nodes": [',
            '    {"id": "a", "label": "输入层", "sublabel": "问题数据",',
            '     "x": 120, "y": 160, "width": 130, "height": 76,',
            '     "shape": "rounded"}',
            "  ],",
            '  "edges": [',
            '    {"from": "a", "to": "b", "label": "传递", "arrow": "right"}',
            "  ]",
            "}",
            "```",
            "",
            "- `node.id` 必须唯一；`label` 支持 `\\n` 换行；",
            "- `x`/`y` 是**中心坐标**；`shape` 可选 rounded/rect/circle/ellipse/diamond；",
            "- `edges[].from` / `to` 必须指向存在的 `node.id`；",
            "- **`title` 会作为图注**，请写完整的中文描述（不要用英文缩写或文件名）。",
            "",
            "写完 JSON 即可结束——**渲染由引擎负责，你不需要也不应该自己编译图形**。",
            "",
        ]

    if skill in ("paper-figure", "paper-figure-drawio"):
        lines += [
            "### 图表的打磨上界（重要）",
            "",
            "允许你「编译 → 渲染 → 看图 → 修正」来保证图形质量，",
            "但**最多 2 轮**。第 2 轮之后无论是否还有可改进之处，",
            "都要立即结束并把文件留在工作区。",
            "",
            "不要在图形细节上无限迭代；先保证文件产出，再谈美观。",
            "",
        ]
    # ★ **论文产物格式约定**：正文写成 `paper/sections/*.md`，由引擎装配。
    #
    #   实测证据：agent 产出 27,538 B 的 `paper/main.tex`，而引擎只认
    #   Markdown 分节 → 导出读到 `body_chars=0`，产出 2 页桩 PDF 并覆盖成品。
    #   约定必须**显式写进提示**：写在文档里不等于 agent 会遵守。
    if skill in PAPER_WRITING_SKILLS:
        lines += [
            "### 论文产物格式约定（强制）",
            "",
            "**正文一律写成 Markdown 分节文件**，放在 `paper/sections/` 下，"
            "文件名前缀用两位数字控制装配顺序：",
            "",
            "- `paper/sections/01_问题重述.md`",
            "- `paper/sections/02_问题分析.md`",
            "- `paper/sections/03_模型假设与符号说明.md`",
            "- …（每个章节一个文件，直到结论、模型评价与参考文献）",
            "",
            "每个文件以 `## 章节标题` 开头（`###` 表示二级小节）。",
            "",
            "**为什么必须这样**：正文由**引擎装配**——引擎读取 "
            "`paper/sections/*.md` 后统一生成 `paper/main.tex`、`paper/main.docx`、"
            "`paper/main.pdf`。若你直接手写完整的 `paper/main.tex`，"
            "引擎会读不到正文（`body_chars = 0`），只能产出 2 页的桩 PDF。",
            "",
            "- **不要**手写完整的 `paper/main.tex`（本步主产物由引擎装配生成）；",
            "- **不要**把整篇论文塞进单个文件（引擎按文件名排序装配）；",
            "- 表格由引擎从 `figures/all_results.json` **程序化生成**，正文里用 "
            "`@ref(tab:results)` 这类引用即可，**不要誊抄数字表**"
            "（数字必须可追溯到数据文件，誊抄必出错）；",
            "- 若你确实选择直出成品 `.tex`，请**只写到** `paper/main.tex`："
            "引擎会走「**只编译不重建**」路径，不会覆盖你的文件。",
            "",
        ]

    # ★ 必须给出**绝对工作区路径**：实测中若只给相对文件名，
    #   agent 会自行猜测绝对路径（曾去读 `\Users\...\dev\MODELING_REPORT.md`），
    #   导致权限被拒、白跑一轮。
    lines += [
        "## 工作区",
        "",
        f"工作目录：`{Path(request.workspace).resolve()}`",
        "",
        "**所有产出文件都必须写在这个目录下**，并使用相对路径引用已有文件；",
        "不要臆测其它绝对路径。",
        "",
    ]

    if step:
        lines += ["## 必须产出", ""]
        for f in step.output_files:
            lines.append(f"- `{f}`")
        lines.append("")
        if step.primary_output:
            lines += [
                f"## 主产物", "",
                f"`{step.primary_output}`",
                "",
                f"最低体量要求：**{we.min_size_for(skill)} 字节**"
                "（低于此值将被判定为未真实产出）。",
                "",
            ]
    companions = we.required_companions_for(skill)
    if companions:
        lines += ["## 必须同时存在（二级文件）", ""]
        for c in companions:
            lines.append(f"- `{c}`（且需 > {we.MIN_COMPANION_BYTES} 字节，防占位）")
        lines += [
            "",
            "> `figures/all_results.json` 是**数据真相源**：",
            "> 论文中的任何数值都必须从它读取，**不得凭记忆或推断书写**。",
            "",
        ]

    limit, mode = we.resolve_page_rule(request.template)
    if limit:
        lines += [
            "## 篇幅参考（建议值，非硬性）", "",
            f"终稿页数参考：**{limit} 页**（中文约 {we.CHARS_PER_PAGE_ZH} 字/页，"
            f"英文约 {we.CHARS_PER_PAGE_EN} 字/页）。",
            "",
            "该值仅供你把握篇幅，**不会**作为生成、扩写或压缩的门控。",
            "",
        ]

    if context_excerpt:
        lines += ["## 工作区已有内容", "", context_excerpt[:2000], ""]

    if request.extra_prompt:
        lines += ["## 补充要求", "", request.extra_prompt, ""]

    return "\n".join(lines)


def summarize_workspace(workspace: Path, *, budget_chars: int = 3000) -> str:
    """生成工作区现状摘要，供**显式注入提示**。

    为什么要显式注入，而不是写 `CLAUDE.md` 让 agent 自动读取：
    我们为安全开了 `--bare`（跳过 CLAUDE.md 自动发现，防工作区文件注入提示），
    代价就是 agent 看不到工作区。因此必须**把上下文写进提示**，
    在保留安全性的同时补回上下文能力。

    摘要内容按字符预算裁剪，并优先保留关键类型文件（md/tex/bib/json/csv）。
    """
    ws = Path(workspace)
    if not ws.is_dir():
        return ""
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", ".cache"}
    key_exts = {".md", ".tex", ".bib", ".json", ".csv", ".py", ".txt", ".yml", ".yaml"}

    files: list[tuple[str, int]] = []
    for p in sorted(ws.rglob("*")):
        rel = p.relative_to(ws)
        if any(part in skip_dirs for part in rel.parts):
            continue
        if p.is_file() and len(rel.parts) <= 4:
            try:
                files.append((rel.as_posix(), p.stat().st_size))
            except OSError:
                continue

    if not files:
        return "（工作区为空）"

    lines = [f"共 {len(files)} 个文件：", ""]
    key = [f for f in files if Path(f[0]).suffix.lower() in key_exts]
    other = [f for f in files if f not in key]
    for name, size in key[:60]:
        lines.append(f"- `{name}`（{size} 字节）")
    if other:
        lines.append(f"- …另有 {len(other)} 个非关键文件")
    lines.append("")

    # 关键文件的内容摘要（只截取少量）
    picked = 0
    for name, size in key:
        if picked >= 4 or size > 200_000:
            continue
        if Path(name).suffix.lower() not in {".md", ".json", ".txt", ".tex", ".csv"}:
            continue
        try:
            text = (ws / name).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        excerpt = text[:600].strip()
        if not excerpt:
            continue
        lines += [f"### `{name}` 开头片段", "", "```", excerpt, "```", ""]
        picked += 1

    out = "\n".join(lines)
    if len(out) > budget_chars:
        out = out[:budget_chars] + "\n\n…（工作区摘要已按预算截断）"
    return out


async def run_step(
    request: StepRunRequest,
) -> AsyncIterator[ar.RunEvent | StepRunOutcome]:
    """执行一个步骤。

    异步生成器：先流式产出 `RunEvent`，**最后一个产出一定是 `StepRunOutcome`**。
    """
    outcome = StepRunOutcome(ok=False, skill_name=request.skill_name)
    started = time.monotonic()

    # ---- 1. 工作区守卫（先于一切） ----
    guard = wg.guard_workspace(request.workspace, isolate=True)
    outcome.guard = guard.summary()
    yield ar.RunEvent(ar.EventKind.PROGRESS,
                      text=f"工作区守卫：发现 {len(guard.findings)} 项，隔离 {len(guard.quarantined)} 项",
                      data=outcome.guard)
    if guard.blocked:
        outcome.error_code = "WORKSPACE_GUARD_BLOCKED"
        outcome.error = "工作区存在可注入配置且未被隔离，拒绝执行"
        outcome.duration_s = round(time.monotonic() - started, 3)
        yield outcome
        return

    # ---- 2. 选择运行时并协商能力 ----
    try:
        rt = ar.resolve_runtime(request.runtime)
    except ar.RuntimeUnavailable as exc:
        outcome.error_code = "RUNTIME_UNAVAILABLE"
        outcome.error = str(exc)
        outcome.duration_s = round(time.monotonic() - started, 3)
        yield outcome
        return
    outcome.runtime = rt.capabilities.name

    # ★ 为子进程准备工具环境（PATH 等）。
    #   agent 看不到我们进程内解析的路径；若不注入，
    #   第 8 步「编译论文」会因为找不到 xelatex 直接失败。
    #   整轮复用同一份环境。
    env, env_rep = te.prepare_child_env()
    _PASS_ENV_PREFIXES = ("MIKTEX", "TEXMF", "LATEXMK", "PYTHON", "GIT_", "DSH")
    _PASS_ENV_EXACT = {"PATH", "PAGER", "NO_COLOR"}
    child_env = {
        k: v for k, v in env.items()
        if k in _PASS_ENV_EXACT or k.startswith(_PASS_ENV_PREFIXES)
    }
    outcome.tool_env = env_rep.as_dict()
    missing_tools = [k for k, v in env_rep.found.items() if not v]
    if missing_tools:
        outcome.degraded.append("missing_tools:" + ",".join(missing_tools))

    ws_path = Path(request.workspace)
    base_prompt = build_step_prompt(
        request, context_excerpt=summarize_workspace(ws_path))

    # ---- 模型链：额度耗尽/过载时依次回退 ----
    chain: list[str] = []
    if request.model:
        chain.append(request.model)
    for m in (request.model_chain or DEFAULT_MODEL_CHAIN):
        if m and m not in chain:
            chain.append(m)
    if not chain:
        chain = [""]                     # 空串 = 用运行时默认模型

    repair_round = 0
    repair_note = ""
    total_attempts = 0
    while True:
        model_idx = 0
        while True:
            model = chain[model_idx] if model_idx < len(chain) else ""
            fallback = chain[model_idx + 1] if model_idx + 1 < len(chain) else None

            spec = ar.RunSpec(
                prompt=base_prompt + repair_note,
                workspace=ws_path,
                model=model or None,
                fallback_model=fallback,
                effort=request.effort,
                allowed_tools=request.allowed_tools,
                disallowed_tools=request.disallowed_tools,
                isolate_mcp=True,
                skip_ambient_config=True,
                resume_session_id=request.resume_session_id,
                max_budget_usd=request.max_budget_usd,
                timeout_s=we.inactivity_timeout(request.skill_name),
                # ★ 静默超时要**短于**整步超时，否则卡住的步骤无法自愈。
                #   实测：comp-code 在 62 条事件后静默 8 分钟以上，
                #   而 2700s 的静默上限意味着要等 45 分钟才会被判定超时——
                #   期间流水线完全停滞。这里收敛到 10 分钟，
                #   让"卡住"能被及时发现并由返修/重试路径接管。
                inactivity_timeout_s=min(
                    we.inactivity_timeout(request.skill_name), INACTIVITY_TIMEOUT_S),
                permission_mode=request.permission_mode,
            )
            spec.env.update(child_env)

            degraded = rt.negotiate(spec)
            outcome.degraded = [d for d in outcome.degraded if ":" in d] + list(degraded)
            if "mcp_isolation" in degraded and not guard.quarantined:
                degraded = [d for d in degraded if d != "mcp_isolation"]
                outcome.degraded = [d for d in outcome.degraded if d != "mcp_isolation"]
            elif "mcp_isolation" in degraded and guard.quarantined:
                outcome.degraded.append("mcp_isolation:compensated_by_workspace_guard")

            if request.strict:
                blocking = [d for d in degraded if d.split(":")[0] in CRITICAL_IF_REQUESTED]
                if blocking:
                    outcome.error_code = "CAPABILITY_MISSING"
                    outcome.error = "；".join(
                        CRITICAL_IF_REQUESTED[d.split(":")[0]] for d in blocking)
                    outcome.duration_s = round(time.monotonic() - started, 3)
                    yield outcome
                    return

            yield ar.RunEvent(
                ar.EventKind.STARTED,
                text=f"运行时 {outcome.runtime} 执行 {request.skill_name}"
                     + (f"（模型 {model}）" if model else "")
                     + (f"｜返修第 {repair_round} 轮" if repair_round else ""),
                data={"runtime": rt.capabilities.name, "model": model,
                      "fallback_model": fallback, "repair_round": repair_round},
            )

            # ---- 执行 ----
            outcome.error_code = ""
            outcome.error = ""
            final_text = ""
            async for ev in rt.run(spec):
                outcome.event_count += 1
                if ev.kind is ar.EventKind.RESULT:
                    final_text = ev.text or final_text
                    outcome.session_id = ev.data.get("session_id") or outcome.session_id
                    if ev.data.get("cost_usd") is not None:
                        outcome.cost_usd = ev.data["cost_usd"]
                    outcome.tokens_in = ev.data.get("tokens_in")
                    outcome.tokens_out = ev.data.get("tokens_out")
                    outcome.model_used = ev.data.get("actual_model") or spec.model
                    denials = ev.data.get("permission_denials") or []
                    if denials:
                        outcome.degraded.append("permission_denied:%d" % len(denials))
                    if ev.data.get("fallback"):
                        outcome.degraded.append("final_text_fallback:%s" % ev.data["fallback"])
                elif ev.kind is ar.EventKind.ERROR:
                    outcome.error_code = ev.data.get("code", "RUNTIME_ERROR")
                    outcome.error = ev.text
                yield ev

            # 可重试错误 → 换下一个模型；链尾则整体再跑一轮。
            #
            # 为什么链尾也要重试：`INACTIVITY_TIMEOUT` 是**网关抖动**，
            # 同一模型隔一会儿往往就好了（实测同一配置一次 327s 成功、
            # 另一次 600s 纯静默）。只在"有下一个模型"时才重试的话，
            # 抖动就会被误判成永久失败。
            if outcome.error_code in RETRYABLE_CODES and (
                    model_idx + 1 < len(chain) or total_attempts < MAX_ATTEMPTS):
                if model_idx + 1 < len(chain):
                    nxt = chain[model_idx + 1]
                    outcome.degraded.append("model_retry:%s->%s(%s)"
                                            % (model or "default", nxt,
                                               outcome.error_code))
                    model_idx += 1
                else:
                    outcome.degraded.append("full_retry:%s(%s)"
                                            % (model or "default",
                                               outcome.error_code))
                    model_idx = 0
                total_attempts += 1
                continue
            break

        outcome.final_text = final_text
        outcome.duration_s = round(time.monotonic() - started, 3)

        if outcome.error_code:
            outcome.ok = False
            yield outcome
            return

        # ---- 质量门 ----
        primary = we.check_primary_output(ws_path, request.skill_name)
        comps = we.check_step_companions(ws_path, request.skill_name)
        pages, chars = we.check_paper_body_pages(ws_path, language=request.language)

        outcome.gates = [
            {"gate": "primary_output", "ok": primary.ok, "reason": primary.reason},
            {"gate": "required_companions", "ok": comps.ok,
             "reason": comps.reason, "missing": list(comps.missing)},
            {"gate": "body_pages_advisory", "ok": True,
             "pages_estimate": pages, "body_chars": chars,
             "note": "advisory only（不作门控）"},
        ]
        failures = [g for g in outcome.gates[:2] if not g["ok"]]

        if not failures:
            outcome.ok = True
            outcome.error_code = ""
            outcome.error = ""
            yield outcome
            return

        # ---- 返修：把失败原因变成下一轮的明确指令 ----
        if repair_round >= MAX_REPAIRS:
            outcome.ok = False
            outcome.error_code = "QUALITY_GATE_FAILED"
            outcome.error = ("质量门未通过（已返修 %d 轮）：" % repair_round
                             + ", ".join(str(g["gate"]) for g in failures))
            yield outcome
            return

        repair_round += 1
        repair_note = build_repair_note(failures)
        outcome.degraded.append("repair_round:%d" % repair_round)
        yield ar.RunEvent(
            ar.EventKind.PROGRESS,
            text=f"质量门未通过，发起第 {repair_round} 轮返修："
                 + ", ".join(str(g["gate"]) for g in failures),
            data={"repair_round": repair_round, "failures": failures},
        )


async def run_step_blocking(request: StepRunRequest) -> tuple[StepRunOutcome, list[ar.RunEvent]]:
    """同步风格的便捷封装：返回 (结果, 事件列表)。"""
    events: list[ar.RunEvent] = []
    outcome: Optional[StepRunOutcome] = None
    async for item in run_step(request):
        if isinstance(item, StepRunOutcome):
            outcome = item
        else:
            events.append(item)
    assert outcome is not None
    return outcome, events


__all__ = [
    "StepRunRequest", "StepRunOutcome", "run_step", "run_step_blocking",
    "build_step_prompt", "build_repair_note", "summarize_workspace",
    "CRITICAL_IF_REQUESTED", "DEFAULT_MODEL_CHAIN", "RETRYABLE_CODES", "MAX_REPAIRS",
    "INACTIVITY_TIMEOUT_S", "MAX_ATTEMPTS", "PAPER_WRITING_SKILLS",
]
