"""竞赛合规检查：论文是否满足竞赛的硬性要求。

覆盖：页数上限、必备章节、摘要、图片文件是否存在、图表是否被正文引用、
参考文献、LaTeX 占位符残留。这些都是"提交前必须过"的检查项。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PASS, WARN, FAIL = "pass", "warn", "fail"

INCLUDE_RE = re.compile(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")
PLACEHOLDER_PATTERNS = [
    ("待补充", re.compile(r"待补充|待填入|待填|需补充数据")),
    ("占位符", re.compile(r"占位|placeholder|PLACEHOLDER|XXX+|TODO|FIXME", re.I)),
    ("未替换模板句", re.compile(r"应填入|此处填写|填写真实|示例数值")),
]


@dataclass
class CheckItem:
    name: str
    status: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass
class ComplianceReport:
    items: list[CheckItem] = field(default_factory=list)
    page_count: int | None = None
    page_limit: int | None = None

    @property
    def failed(self) -> list[CheckItem]:
        return [i for i in self.items if i.status == FAIL]

    @property
    def warned(self) -> list[CheckItem]:
        return [i for i in self.items if i.status == WARN]

    @property
    def verdict(self) -> str:
        if self.failed:
            return FAIL
        return WARN if self.warned else PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "page_count": self.page_count,
            "page_limit": self.page_limit,
            "failed": len(self.failed),
            "warned": len(self.warned),
            "items": [i.to_dict() for i in self.items],
        }


def count_pdf_pages(pdf: Path) -> int | None:
    """统计 PDF 页数：优先用 pypdf，退化为按页对象估算。"""
    pdf = Path(pdf)
    if not pdf.exists():
        return None
    try:
        from pypdf import PdfReader  # 可选依赖

        return len(PdfReader(str(pdf)).pages)
    except Exception:  # noqa: BLE001 —— 没装 pypdf 就走估算
        pass
    try:
        data = pdf.read_bytes()
    except OSError:
        return None
    pages = len(re.findall(rb"/Type\s*/Page[^s]", data))
    return pages or None


def _paper_text(run_root: Path, patterns: tuple[str, ...] = ("paper/*.tex", "paper/**/*.tex")) -> tuple[str, list[Path]]:
    files: list[Path] = []
    for pattern in patterns:
        files.extend(sorted(run_root.glob(pattern)))
    files = [p for p in dict.fromkeys(files) if p.is_file()]
    text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in files)
    return text, files


def check_compliance(run_root: Path, competition: dict[str, Any] | None = None) -> ComplianceReport:
    run_root = Path(run_root)
    competition = competition or {}
    report = ComplianceReport()
    text, tex_files = _paper_text(run_root)

    if not tex_files:
        report.items.append(CheckItem("论文源文件", FAIL, "没有找到 paper/*.tex"))
        return report
    report.items.append(CheckItem("论文源文件", PASS, f"{len(tex_files)} 个 .tex 文件"))

    # 1) 文档完整性与篇幅：被截断的 LaTeX 往往缺 \end{document}，但依然能"编译"出半篇
    has_begin = bool(re.search(r"\\begin\{document\}", text))
    has_end = bool(re.search(r"\\end\{document\}", text))
    if has_begin and has_end:
        report.items.append(CheckItem("文档完整性", PASS, "起止标记齐全"))
    elif has_begin and not has_end:
        report.items.append(CheckItem("文档完整性", FAIL, "缺少 \\end{document}，疑似生成被截断"))
    else:
        report.items.append(CheckItem("文档完整性", FAIL, "缺少 \\begin{document}"))

    # 2) 必备章节
    required = list(competition.get("required_sections") or [])
    if required:
        missing = [s for s in required if s not in text]
        if missing:
            status = FAIL if len(missing) > max(2, len(required) // 3) else WARN
            report.items.append(CheckItem("必备章节", status, f"缺少 {len(missing)} 项：{'、'.join(missing)}"))
        else:
            report.items.append(CheckItem("必备章节", PASS, f"{len(required)} 项齐全"))

    # 2) 摘要
    if competition.get("abstract_first"):
        has_abstract = bool(re.search(r"摘要|abstract", text, re.I))
        report.items.append(
            CheckItem("摘要", PASS if has_abstract else FAIL, "已包含摘要" if has_abstract else "未找到摘要")
        )

    # 3) 页数：既要看上限，也要看下限（太短通常意味着内容不全或生成被截断）
    pdf = run_root / "paper" / "main.pdf"
    if not pdf.exists():
        candidates = sorted((run_root / "paper").glob("*.pdf"))
        pdf = candidates[0] if candidates else pdf
    limit = competition.get("page_limit")
    min_pages = int(competition.get("min_pages") or 0)
    report.page_limit = int(limit) if limit else None
    if pdf.exists():
        pages = count_pdf_pages(pdf)
        report.page_count = pages
        if pages is None:
            report.items.append(CheckItem("页数", WARN, "已生成 PDF 但无法统计页数"))
        elif report.page_limit and pages > report.page_limit:
            report.items.append(CheckItem("页数", FAIL, f"{pages} 页 > 上限 {report.page_limit} 页"))
        elif min_pages and pages < min_pages:
            status = FAIL if pages < min_pages / 2 else WARN
            report.items.append(
                CheckItem("页数", status,
                          f"只有 {pages} 页，该竞赛建议至少 {min_pages} 页（可能内容不全或生成被截断）")
            )
        elif report.page_limit:
            report.items.append(CheckItem("页数", PASS, f"{pages} 页 / 上限 {report.page_limit} 页"))
        else:
            report.items.append(CheckItem("页数", PASS, f"{pages} 页（该竞赛未设上限）"))
    else:
        report.items.append(CheckItem("页数", WARN, "还没有 PDF，无法统计页数（先执行 mma compile）"))

    # 4) 图片：既要引用存在，也要够数（竞赛论文缺图是硬伤）
    includes = INCLUDE_RE.findall(text)
    min_figures = int(competition.get("min_figures") or 0)
    available = sorted((run_root / "figures").glob("*.png")) if (run_root / "figures").exists() else []

    if includes:
        missing_files = []
        for rel in includes:
            target = (run_root / "paper" / rel.strip()).resolve()
            if not target.exists():
                target = (run_root / rel.strip()).resolve()
            if not target.exists():
                missing_files.append(rel.strip())
        if missing_files:
            report.items.append(CheckItem("图片文件", FAIL, f"{len(missing_files)} 个引用不存在：{', '.join(missing_files[:3])}"))
        elif min_figures and len(includes) < min_figures:
            report.items.append(
                CheckItem("图片数量", FAIL, f"只引用了 {len(includes)} 张图，该竞赛建议至少 {min_figures} 张")
            )
        else:
            detail = f"{len(includes)} 处引用全部存在"
            unused = [p.name for p in available if p.name not in text]
            if unused:
                detail += f"；figures/ 下还有 {len(unused)} 张图未被引用"
            report.items.append(CheckItem("图片文件", PASS, detail))
    else:
        status = FAIL if min_figures else WARN
        report.items.append(
            CheckItem(
                "图片文件",
                status,
                f"论文中没有插入任何图片" + (f"（该竞赛建议至少 {min_figures} 张）" if min_figures else ""),
            )
        )

    # 5) 图表是否被正文引用
    refs = len(re.findall(r"\\ref\{", text)) + len(re.findall(r"\\eqref\{", text))
    labels = len(re.findall(r"\\label\{", text))
    if labels and refs < labels // 2:
        report.items.append(CheckItem("图表引用", WARN, f"{labels} 个标签但只有 {refs} 处引用"))
    else:
        report.items.append(CheckItem("图表引用", PASS, f"标签 {labels} 个 / 引用 {refs} 处"))

    # 6) 参考文献
    bib = bool(re.search(r"\\bibitem|thebibliography|\\bibliography\{|\\addbibresource", text))
    report.items.append(CheckItem("参考文献", PASS if bib else FAIL, "已包含参考文献" if bib else "未找到参考文献环境"))

    # 7) 占位符残留
    leftovers: list[str] = []
    for label, pattern in PLACEHOLDER_PATTERNS:
        found = pattern.findall(text)
        if found:
            leftovers.append(f"{label}({len(found)})")
    if leftovers:
        report.items.append(CheckItem("占位符残留", FAIL, "、".join(leftovers)))
    else:
        report.items.append(CheckItem("占位符残留", PASS, "未发现未替换的占位内容"))

    return report
