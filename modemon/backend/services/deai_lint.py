"""去 AI 味检查（de-AI lint）。

规则来源
--------
规则与判据来自对 Modex-MH-Agent `services/prompts/academic_docx_traps.md` 与
`docx_write_markdown.md` 的恢复。蓝方把这些约束写进了提示词，让模型"尽量遵守"；
本项目把其中**可机械判定**的部分做成 lint，**在执行后强制检查**——
因为"写在提示里"不等于"一定做到"。

已恢复并实现的规则
------------------
1. 图题 ≤ 15 个汉字
2. 图题内禁用公式（`$...$` / `\\(...\\)` / `\\begin{...}`）
3. 标签与内容之间用空格而非冒号（"空格替冒号"）
4. **`**标签：**` 的冒号必须写在 `**` 外** ——复现材料标注这是"最高频痕迹"
5. 正文不得出现"作为一个 AI / 作为语言模型"等自指表达
6. 不得出现占位符残留（TODO / XXX / 待补充 / 括号占位）

最后两条是通用论文卫生，不属于蓝方原始规则，但同一类问题的漏网之鱼。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Literal

Severity = Literal["error", "warn", "info"]

#: 图题汉字上限（恢复真值）
MAX_CAPTION_HANZI = 15

_HANZI_RE = re.compile(r"[\u4e00-\u9fff]")
_MATH_RE = re.compile(r"\$[^$]+\$|\\\(.*?\\\)|\\begin\{(equation|align|gather)")
#: `**标签：**` —— 冒号被困在星号内（最高频痕迹）
_BOLD_COLON_INSIDE_RE = re.compile(r"\*\*[^*\n]{1,20}[：:]\*\*")
#: `**标签**:` 或 `**标签：** ` 的合规写法
_LABEL_OK_RE = re.compile(r"\*\*[^*\n]{1,20}\*\*\s*[：:]")
_SELF_REF_RE = re.compile(
    r"(作为一个?\s*(AI|人工智能|语言模型|大模型))|(As an AI)|(作为语言模型)")
_PLACEHOLDER_RE = re.compile(
    r"(TODO|FIXME|XXX+|待补充|待填写|此处略|【\s*】|\(\s*待\s*\)|\{\{.*?\}\})")
_COLON_AS_SEP_RE = re.compile(r"[\u4e00-\u9fff]{2,10}：")


@dataclass
class LintIssue:
    rule: str
    severity: Severity
    message: str
    line: int = 0
    excerpt: str = ""

    def as_dict(self) -> dict:
        return {"rule": self.rule, "severity": self.severity, "message": self.message,
                "line": self.line, "excerpt": self.excerpt}


@dataclass
class LintReport:
    issues: list[LintIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[LintIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[LintIssue]:
        return [i for i in self.issues if i.severity == "warn"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "error_count": len(self.errors),
            "warn_count": len(self.warnings),
            "by_rule": _count_by_rule(self.issues),
            "issues": [i.as_dict() for i in self.issues],
        }


def _count_by_rule(issues: Iterable[LintIssue]) -> dict[str, int]:
    out: dict[str, int] = {}
    for i in issues:
        out[i.rule] = out.get(i.rule, 0) + 1
    return out


# ---------------------------------------------------------------------------
# 单条规则
# ---------------------------------------------------------------------------


def check_caption(text: str, *, line: int = 0) -> list[LintIssue]:
    """图题规则：≤15 汉字、禁公式。"""
    out: list[LintIssue] = []
    hanzi = len(_HANZI_RE.findall(text))
    if hanzi > MAX_CAPTION_HANZI:
        out.append(LintIssue(
            "caption_too_long", "warn",
            f"图题 {hanzi} 个汉字，超过上限 {MAX_CAPTION_HANZI}",
            line, text[:80]))
    if _MATH_RE.search(text):
        out.append(LintIssue(
            "caption_has_math", "error",
            "图题内禁止出现公式（公式应放在正文，图题只作说明）",
            line, text[:80]))
    return out


def check_bold_label_colon(text: str, *, line: int = 0) -> list[LintIssue]:
    """`**标签：**` 的冒号必须写在 `**` 外（最高频 AI 痕迹）。"""
    out: list[LintIssue] = []
    for m in _BOLD_COLON_INSIDE_RE.finditer(text):
        frag = m.group(0)
        # 已经是 `**标签：** 内容` 这种（后面紧跟空格+内容）也算问题，
        # 规范写法是 `**标签**：内容`
        fixed = frag.replace("：", "").replace(":", "")
        out.append(LintIssue(
            "bold_colon_inside", "error",
            f"冒号写在了加粗标记内：`{frag}` → 应改为 `{fixed}**：`",
            line, text[max(0, m.start() - 10):m.end() + 20]))
    return out


def check_self_reference(text: str, *, line: int = 0) -> list[LintIssue]:
    out = []
    for m in _SELF_REF_RE.finditer(text):
        out.append(LintIssue("self_reference", "error",
                             "正文出现自指表达（AI/语言模型），论文中不应出现",
                             line, text[max(0, m.start() - 15):m.end() + 15]))
    return out


def check_placeholders(text: str, *, line: int = 0) -> list[LintIssue]:
    out = []
    for m in _PLACEHOLDER_RE.finditer(text):
        out.append(LintIssue("placeholder_left", "error",
                             f"残留占位符：`{m.group(0)}`", line,
                             text[max(0, m.start() - 15):m.end() + 15]))
    return out


#: 硬编码的图表编号引用，如「见表 1」「如图2所示」
_HARDCODED_REF_RE = re.compile(r"(见|如|参见|详见|见下|见上)?\s*(表|图)\s*(\d+)\s*[，。、）)]?")


def check_hardcoded_refs(text: str, *, line: int = 0) -> list[LintIssue]:
    """「硬编码图表编号」：正文写死「表 1 / 图 2」会在表格增减后**错位**。

    实测缺陷：正文写「各项指标见表 1，不同算例见表 2」，而 LaTeX 自动编号
    后实际是表 2、表 3（前面还有一张符号说明表占了表 1），视觉自检判
    「交叉引用编号整体错位」。

    正确写法是 `@ref(tab:xxx)`（由 `md_inline_to_tex` 转成 `\\ref`）。
    """
    out = []
    kind = {"表": "tab", "图": "fig"}
    for m in _HARDCODED_REF_RE.finditer(text):
        out.append(LintIssue(
            "hardcoded_ref", "warn",
            f"硬编码的图表编号「{m.group(2)} {m.group(3)}」"
            f"——表格增减后会错位，请改用 @ref({kind.get(m.group(2), 'tab')}:xxx)",
            line=line,
        ))
    return out


def check_colon_separator(text: str, *, line: int = 0) -> list[LintIssue]:
    """「空格替冒号」：并非一律禁止，只在**紧随加粗标签**时提示。"""
    out = []
    for m in _BOLD_COLON_INSIDE_RE.finditer(text):
        continue
    # 形如 `**标签**：内容` 是合规的；只有 `**标签：**` 才是问题（上一条规则覆盖）
    return out


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------


def lint_text(text: str, *, check_captions: bool = False) -> LintReport:
    """检查一段文本。

    Args:
        check_captions: True 时把整段视为图题（用于 `figures/FIGURE_MANIFEST.md`）。
    """
    rep = LintReport()
    if check_captions:
        rep.issues.extend(check_caption(text))
    for n, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        rep.issues.extend(check_bold_label_colon(line, line=n))
        rep.issues.extend(check_self_reference(line, line=n))
        rep.issues.extend(check_placeholders(line, line=n))
        rep.issues.extend(check_hardcoded_refs(line, line=n))
    return rep


def lint_paper(workspace, *, sections: Iterable[str] = (),
               manifest_captions: Iterable[str] = ()) -> LintReport:
    """检查整篇论文：正文 + 图题。"""
    rep = LintReport()
    for text in sections:
        rep.issues.extend(lint_text(text).issues)
    for cap in manifest_captions:
        rep.issues.extend(check_caption(cap))
    return rep


__all__ = [
    "LintIssue", "LintReport", "MAX_CAPTION_HANZI",
    "check_caption", "check_bold_label_colon", "check_self_reference",
    "check_placeholders", "lint_text", "lint_paper",
]
