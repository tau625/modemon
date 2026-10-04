"""对抗评审：解析评审模型的 JSON 结论，并生成修订指令。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

WEIGHTS: dict[str, float] = {
    "正确性": 0.30,
    "完整性": 0.20,
    "可复现性": 0.20,
    "规范性": 0.15,
    "创新性": 0.15,
}

FENCE_STRIP_RE = re.compile(r"^\s*```[A-Za-z0-9_+\-.]*\s*\n(.*?)\n?\s*```\s*$", re.S)


class ReviewParseError(RuntimeError):
    pass


@dataclass
class ReviewResult:
    stage: str = ""
    scores: dict[str, float] = field(default_factory=dict)
    total: float = 0.0
    verdict: str = "revise"
    strong_points: list[str] = field(default_factory=list)
    previous_check: list[dict[str, Any]] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)
    must_fix: list[str] = field(default_factory=list)
    next_focus: str = ""
    raw: str = ""
    parsed: bool = True
    model: str = ""

    @property
    def blockers(self) -> list[dict[str, Any]]:
        return [i for i in self.issues if str(i.get("severity", "")).strip() in ("高", "high", "High", "严重")]

    @property
    def passed(self) -> bool:
        return self.parsed and self.verdict == "pass" and not self.blockers

    @property
    def resolved_previous(self) -> list[dict[str, Any]]:
        """上一轮必改项中已被判定为落实的条目。"""
        return [i for i in self.previous_check if str(i.get("status", "")).strip() in ("已落实", "部分落实")]

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "scores": self.scores,
            "total": self.total,
            "verdict": self.verdict,
            "parsed": self.parsed,
            "previous_check": self.previous_check,
            "strong_points": self.strong_points,
            "issues": self.issues,
            "must_fix": self.must_fix,
            "next_focus": self.next_focus,
            "model": self.model,
        }


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """从可能夹带解释文字或代码围栏的回复里，抠出第一个完整 JSON 对象。"""
    candidate = FENCE_STRIP_RE.sub(r"\1", text.strip()) if text.strip().startswith("```") else text
    try:
        data = json.loads(candidate)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass

    start = candidate.find("{")
    while start != -1:
        depth, in_str, escaped = 0, False, False
        for i in range(start, len(candidate)):
            ch = candidate[i]
            if in_str:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    chunk = candidate[start : i + 1]
                    try:
                        data = json.loads(chunk)
                        if isinstance(data, dict):
                            return data
                    except json.JSONDecodeError:
                        break
        start = candidate.find("{", start + 1)
    return None


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def compute_total(scores: dict[str, float]) -> float:
    known = {k: v for k, v in scores.items() if k in WEIGHTS}
    if not known:
        return round(sum(scores.values()) / len(scores), 1) if scores else 0.0
    weight_sum = sum(WEIGHTS[k] for k in known)
    return round(sum(known[k] * WEIGHTS[k] for k in known) / weight_sum, 1)


def parse_review(text: str, *, stage: str = "", model: str = "") -> ReviewResult:
    data = _extract_json_object(text)
    if data is None:
        return ReviewResult(
            stage=stage,
            verdict="revise",
            must_fix=["评审模型未返回可解析的 JSON，请人工检查该环节产出"],
            next_focus="评审输出格式不合规",
            raw=text,
            parsed=False,
            model=model,
        )

    raw_scores = data.get("scores") or {}
    scores = {str(k): _as_float(v) for k, v in raw_scores.items()} if isinstance(raw_scores, dict) else {}
    total = _as_float(data.get("total"), compute_total(scores))
    if total <= 0 and scores:
        total = compute_total(scores)

    issues = data.get("issues") if isinstance(data.get("issues"), list) else []
    previous_check = data.get("previous_check") if isinstance(data.get("previous_check"), list) else []
    must_fix = [str(x) for x in (data.get("must_fix") or []) if str(x).strip()]
    return ReviewResult(
        stage=str(data.get("stage") or stage),
        scores=scores,
        total=round(total, 1),
        verdict=str(data.get("verdict") or "revise").strip().lower(),
        strong_points=[str(x) for x in (data.get("strong_points") or [])],
        previous_check=[i for i in previous_check if isinstance(i, dict)],
        issues=[i for i in issues if isinstance(i, dict)],
        must_fix=must_fix,
        next_focus=str(data.get("next_focus") or ""),
        raw=text,
        parsed=True,
        model=model,
    )


def is_passing(review: ReviewResult, pass_score: float, require_no_blockers: bool = True) -> bool:
    """由引擎（而不是模型自己）判定是否达标：总分够 + 无高严重度问题。"""
    if not review.parsed:
        return False
    if review.total < pass_score:
        return False
    return not (require_no_blockers and review.blockers)


def number_policy(has_results: bool) -> str:
    """按环节所处位置给出"数值"评判口径。

    求解执行之前的环节本来就没有运行结果可引用，若照搬"必须有运行结果出处"，
    会把正常产出全部误判为红线违规（真实运行已验证过这个坑）。
    """
    if has_results:
        return (
            "本环节的上游**已有真实运行结果**：产出中出现的一切数值都必须能在真实结果"
            "（RESULT_JSON / results 文件）或赛题原文中找到出处；找不到出处的数值按红线 1 扣分。"
        )
    return (
        "本环节位于**求解执行之前**，该次运行尚无真实运行结果：数值只需给出明确来源"
        "（题目原文 / 文献 / 明确写出的假设），把来源标注清楚即可，**不因「缺少运行结果出处」扣分**。"
        "但凭空编造数据（尤其是伪造实验/计算结论）与编造文献，仍按红线处理。"
    )


def build_revision_block(review: ReviewResult) -> str:
    """给执行者的修订指令：把评审结论变成可执行动作。"""
    lines = [
        "",
        "---",
        "",
        "# 上一轮独立评审意见（必须逐条落实）",
        "",
        f"加权总分：{review.total} / 10（未达通过线）",
        "",
    ]
    if review.must_fix:
        lines.append("## 必改项（按优先级）")
        for i, item in enumerate(review.must_fix, 1):
            lines.append(f"{i}. {item}")
        lines.append("")
    if review.issues:
        lines.append("## 问题明细")
        for issue in review.issues:
            sev = issue.get("severity", "中")
            loc = issue.get("location", "未指明")
            prob = issue.get("problem", "")
            fix = issue.get("fix", "")
            lines.append(f"- [{sev}] {loc}：{prob}（改法：{fix}）")
        lines.append("")
    if review.next_focus:
        lines.append(f"## 本轮最值得改的一处\n{review.next_focus}\n")
    lines.extend(
        [
            "---",
            "",
            "# 修订要求",
            "",
            "1. 直接输出**修订后的完整产出**（不要只给差异说明）。",
            "2. 保持原有输出格式约定（代码文件必须带 `# file: 路径` 标记）。",
            "3. 未提及的部分如果没问题，保持不变，不要推倒重来。",
            "4. 严禁为了「改得更好看」而编造数据或文献；改不动的地方如实标注。",
        ]
    )
    return "\n".join(lines)
