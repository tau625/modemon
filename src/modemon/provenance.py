"""数值溯源门禁：论文里出现的每个数字，是否能在**真实执行结果**中找到出处。

动机：AI 写论文最大的可信度风险是"数字凭空生成"。本模块把论文中的数值与
`results/` 下的真实产出（执行汇总、JSON/CSV 结果）以及赛题原文做交叉核对，
把找不到出处的数字列出来给人复核。
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# 这些 LaTeX 结构里的数字是排版参数，不是论文结论数据
STRIP_PATTERNS = [
    re.compile(r"%[^\n]*"),                                   # 注释
    re.compile(r"\\includegraphics\s*\[[^\]]*\]"),             # 图片尺寸
    re.compile(r"\\includegraphics\s*\{[^}]*\}"),              # 图片路径
    re.compile(r"\\(?:label|ref|eqref|cite|citep|citet|nocite|input|include)\s*\{[^}]*\}"),
    re.compile(r"\\(?:usepackage|documentclass|geometry|setlength|hspace|vspace|fontsize|rule|"
               r"begin|end|pagestyle|setcounter|cline|hline|scalebox|resizebox)\s*(?:\[[^\]]*\])?\{[^}]*\}"),
    re.compile(r"\\[a-zA-Z@]+\*?"),                           # 残留的命令名
]

NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
CSV_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")

# 门禁自己写出的报告不能当作"证据"，否则会形成自证循环
META_RESULT_FILES = {
    "provenance_check.json",
    "compliance_check.json",
    "compile_summary.json",
    "agent_notes.json",
}


@dataclass
class NumberHit:
    value: float
    raw: str
    context: str


@dataclass
class ProvenanceReport:
    total: int = 0
    matched: int = 0
    unmatched: list[dict[str, Any]] = field(default_factory=list)
    evidence_count: int = 0
    sources: list[str] = field(default_factory=list)
    tolerance: float = 0.01

    @property
    def ratio(self) -> float:
        return (self.matched / self.total) if self.total else 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "matched": self.matched,
            "ratio": round(self.ratio, 4),
            "evidence_count": self.evidence_count,
            "sources": self.sources,
            "tolerance": self.tolerance,
            "unmatched": self.unmatched,
        }


def _strip_latex_noise(text: str) -> str:
    for pattern in STRIP_PATTERNS:
        text = pattern.sub(" ", text)
    return text


def collect_paper_numbers(text: str) -> list[NumberHit]:
    """抽取论文正文中的数值（已剔除排版参数与引用编号）。"""
    cleaned = _strip_latex_noise(text)
    hits: list[NumberHit] = []
    for match in NUMBER_RE.finditer(cleaned):
        raw = match.group(0)
        value = float(raw)
        # 过滤：个位数整数（多为章节号/列表号）、纯 0
        if "." not in raw and abs(value) < 10:
            continue
        if value == 0:
            continue
        start = max(0, match.start() - 40)
        end = min(len(cleaned), match.end() + 40)
        context = " ".join(cleaned[start:end].split())
        hits.append(NumberHit(value=value, raw=raw, context=context))
    return hits


def _numbers_from_json(data: Any, out: list[float]) -> None:
    if isinstance(data, bool):
        return
    if isinstance(data, (int, float)):
        out.append(float(data))
    elif isinstance(data, dict):
        for value in data.values():
            _numbers_from_json(value, out)
    elif isinstance(data, list):
        for value in data:
            _numbers_from_json(value, out)
    elif isinstance(data, str):
        for token in NUMBER_RE.findall(data):
            out.append(float(token))


def collect_evidence_numbers(run_root: Path) -> tuple[list[float], list[str]]:
    """收集"真实来源"的数值：执行汇总、结果文件、以及赛题原文。"""
    run_root = Path(run_root)
    numbers: list[float] = []
    sources: list[str] = []

    seen_files: set[Path] = set()
    for pattern in ("results/execution_*.json", "results/*.json", "results/*.csv"):
        for path in sorted(run_root.glob(pattern)):
            if path.name in META_RESULT_FILES:
                continue  # 门禁自身产物，不能作为证据
            if path in seen_files:
                continue  # 多个 glob 模式会重叠，去重
            seen_files.add(path)
            try:
                if path.suffix == ".csv":
                    with path.open(encoding="utf-8", newline="") as fh:
                        for row in csv.reader(fh):
                            for cell in row:
                                cell = cell.strip()
                                if CSV_NUM_RE.match(cell):
                                    numbers.append(float(cell))
                else:
                    _numbers_from_json(json.loads(path.read_text(encoding="utf-8")), numbers)
                sources.append(path.relative_to(run_root).as_posix())
            except (OSError, json.JSONDecodeError, csv.Error):
                continue

    # 赛题原文里的数据也是合法出处
    problem = run_root / "artifacts" / "00_problem.md"
    if problem.exists():
        for token in NUMBER_RE.findall(problem.read_text(encoding="utf-8", errors="replace")):
            numbers.append(float(token))
        sources.append("artifacts/00_problem.md")

    return numbers, sources


def _is_match(value: float, evidence: Iterable[float], tolerance: float) -> bool:
    for candidate in evidence:
        if abs(candidate - value) <= max(tolerance * abs(candidate), 1e-9):
            return True
        # 论文常四舍五入：按论文的小数位数比较
        raw = f"{value}"
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        try:
            if abs(round(candidate, decimals) - value) < 1e-9:
                return True
        except (TypeError, ValueError):
            continue
    return False


def check_provenance(run_root: Path, *, tolerance: float = 0.01, paper_files: list[Path] | None = None) -> ProvenanceReport:
    """核对论文数值与真实结果的对应关系。"""
    run_root = Path(run_root)
    paper_dir = run_root / "paper"
    files = paper_files or [
        p for p in sorted(list(paper_dir.rglob("*.tex")) + list((run_root / "artifacts").glob("*.md")))
        if p.exists() and p.name != "00_problem.md"
    ]

    evidence, sources = collect_evidence_numbers(run_root)
    report = ProvenanceReport(evidence_count=len(evidence), sources=sources, tolerance=tolerance)

    seen: set[str] = set()
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for hit in collect_paper_numbers(text):
            key = f"{hit.raw}@{path.name}"
            if key in seen:
                continue
            seen.add(key)
            report.total += 1
            if _is_match(hit.value, evidence, tolerance):
                report.matched += 1
            else:
                report.unmatched.append(
                    {
                        "value": hit.raw,
                        "file": path.relative_to(run_root).as_posix(),
                        "context": hit.context,
                    }
                )
    return report
