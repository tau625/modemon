"""中文论文排版规格。

数据来源
--------
本模块内置的 `competition_zh` 规格，字段与数值**逐项来自对 Modex-MH-Agent
`tools/docx_style_profiles/competition_zh.json` 的恢复**（真值，非推测）：

    "profile_name": "数学建模竞赛中文论文样式（对标 cumcmthesis.cls）"
    A4 / 上下左右 2.5cm / SimHei+SimSun+Times New Roman+Consolas
    标题 15/14/12/11pt 加粗，一级居中 / 正文 12pt/1.5倍行距/首行缩进2字符
    标题 18pt 居中 SimHei / 三线表 1.5-0.75-1.5pt，表内 10.5pt
    参考文献 悬挂缩进 0.74cm，10.5pt，方括号编号 / 图宽上限 14cm
    代码 9pt/1.0 行距/底色 F5F5F5 / 摘要标签 14pt / 关键词标签 12pt SimHei

**它的自陈对标对象是公开的 `cumcmthesis.cls`**，因此这些数值可由公开来源反推，
不需要逆向——这一点很重要，它意味着复现该规格没有法律或技术障碍。

`covers/huawei.json` 同理对标 `gmcmthesis.cls`（华为杯），但其完整字段未全部恢复，
故华为杯当前复用竞赛通用规格，仅在页数上限（50 页）上区分。
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# 内置规格（恢复真值）
# ---------------------------------------------------------------------------

COMPETITION_ZH: dict[str, Any] = {
    "profile_name": "数学建模竞赛中文论文样式（对标 cumcmthesis.cls）",
    "page": {
        "size": "A4",
        "margin_top_cm": 2.5,
        "margin_bottom_cm": 2.5,
        "margin_left_cm": 2.5,
        "margin_right_cm": 2.5,
    },
    "fonts": {
        "chinese_heading": "SimHei",
        "chinese_body": "SimSun",
        "latin": "Times New Roman",
        "monospace": "Consolas",
    },
    "headings": {
        "level1_pt": 15,
        "level2_pt": 14,
        "level3_pt": 12,
        "level4_pt": 11,
        "bold": True,
        "level1_alignment": "center",
        "level2_alignment": "left",
        "level3_alignment": "left",
        "level1_page_break_before": False,
        "level2_page_break_before": False,
        "level3_page_break_before": False,
    },
    "body": {
        "font_size_pt": 12,
        "line_spacing": 1.5,
        "first_line_indent_chars": 2,
        "space_before_pt": 0,
        "space_after_pt": 0,
    },
    "title": {
        "font_size_pt": 18,
        "bold": True,
        "alignment": "center",
        "font_family": "SimHei",
        "line_spacing": 1.15,
        "space_before_pt": 12,
        "space_after_pt": 6,
    },
    "table": {
        "top_border_pt": 1.5,
        "header_border_pt": 0.75,
        "bottom_border_pt": 1.5,
        "font_size_pt": 10.5,
        "header_bold": True,
        "cell_alignment": "center",
    },
    "references": {
        "hanging_indent_cm": 0.74,
        "font_size_pt": 10.5,
        "numbering_style": "bracket",
    },
    "image": {"max_width_cm": 14, "alignment": "center"},
    "code_block": {
        "font_size_pt": 9,
        "line_spacing": 1.0,
        "background_color": "F5F5F5",
    },
    "abstract": {
        "label_size_pt": 14,
        "body_size_pt": 12,
        "label_bold": True,
        "label_alignment": "center",
    },
    "keywords": {"label_size_pt": 12, "label_bold": True, "font": "SimHei"},
}

#: 内置规格注册表
BUILTIN_PROFILES: dict[str, dict[str, Any]] = {
    "competition_zh": COMPETITION_ZH,
}

#: 模板 → 规格名（蓝方的 profile 选择逻辑）
TEMPLATE_PROFILE: dict[str, str] = {
    "comp_cumcm": "competition_zh",
    "comp_huawei": "competition_zh",   # 华为杯复用通用规格（其专属字段未全部恢复）
    "comp_mathorcup": "competition_zh",
    "comp_zh": "competition_zh",
    "comp_mcm": "competition_zh",      # 美赛走英文，但版面规格同源
    "comp_apmcm": "competition_zh",
    "comp_en": "competition_zh",
    "course_paper": "competition_zh",
    "thesis_proposal": "competition_zh",
}

#: 正文字符预算（恢复真值）：`_check_paper_body_pages` 的 docstring
CHARS_PER_PAGE_ZH = 800
CHARS_PER_PAGE_EN = 2200

#: 终稿页数参考（恢复真值，全部 advisory_max）
PAGE_LIMIT: dict[str, Optional[int]] = {
    "comp_cumcm": 30,
    "comp_huawei": 50,
    "comp_mcm": 25,
    "comp_apmcm": 25,
    "comp_mathorcup": 30,
}


@dataclass
class StyleProfile:
    """一份可直接驱动渲染的排版规格。"""

    name: str
    data: dict[str, Any]
    source: str = "builtin"
    #: 非致命偏差提示（例如某字体缺失）
    warnings: list[str] = field(default_factory=list)

    # -- 便捷读取 -----------------------------------------------------------

    @property
    def fonts(self) -> dict[str, str]:
        return self.data["fonts"]

    @property
    def body(self) -> dict[str, Any]:
        return self.data["body"]

    @property
    def headings(self) -> dict[str, Any]:
        return self.data["headings"]

    @property
    def title(self) -> dict[str, Any]:
        return self.data["title"]

    @property
    def table(self) -> dict[str, Any]:
        return self.data["table"]

    @property
    def image(self) -> dict[str, Any]:
        return self.data["image"]

    @property
    def page(self) -> dict[str, Any]:
        return self.data["page"]

    @property
    def references(self) -> dict[str, Any]:
        return self.data["references"]

    def heading_pt(self, level: int) -> float:
        key = f"level{max(1, min(4, level))}_pt"
        return float(self.headings.get(key, self.body["font_size_pt"] + 2))

    def as_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self.data)


def load_profile(
    name: str = "competition_zh",
    *,
    search_dirs: Optional[list[Path]] = None,
) -> StyleProfile:
    """加载排版规格。

    优先从外部目录读取同名 JSON（便于用户自定义）；
    找不到则回退内置恢复值。**外部文件不得静默覆盖关键字段**——
    缺字段会与内置规格合并，而不是整体替换。
    """
    for d in search_dirs or []:
        p = Path(d) / f"{name}.json"
        if p.is_file():
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                return StyleProfile(
                    name=name, data=copy.deepcopy(BUILTIN_PROFILES.get(name, COMPETITION_ZH)),
                    source="builtin", warnings=[f"外部规格解析失败，已回退内置: {exc}"])
            merged = copy.deepcopy(BUILTIN_PROFILES.get(name, COMPETITION_ZH))
            _deep_merge(merged, raw)
            return StyleProfile(name=name, data=merged, source=str(p))
    if name in BUILTIN_PROFILES:
        return StyleProfile(name=name, data=copy.deepcopy(BUILTIN_PROFILES[name]))
    return StyleProfile(name=name, data=copy.deepcopy(COMPETITION_ZH),
                        warnings=[f"未知规格 {name!r}，已回退 competition_zh"])


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def resolve_profile(template: str, **kw: Any) -> StyleProfile:
    """按模板解析规格。"""
    return load_profile(TEMPLATE_PROFILE.get(template, "competition_zh"), **kw)


# ---------------------------------------------------------------------------
# 篇幅预算（advisory）
# ---------------------------------------------------------------------------


@dataclass
class PageBudget:
    """页数预算结果。

    `limit` 为 None 表示该模板无页数上限。
    **该值只用于向用户展示与保守预检，绝不作为生成/扩写/压缩的门控**——
    这一点是蓝方 docstring 明确的设计意图，也是避免误杀合规论文的关键。
    """

    template: str
    limit: Optional[int]
    mode: str = "advisory_max"
    body_chars: int = 0
    language: str = "zh"
    estimated_pages: int = 0
    over_by: int = 0

    @property
    def over_limit(self) -> bool:
        return bool(self.limit) and self.estimated_pages > self.limit  # type: ignore[operator]

    def as_dict(self) -> dict[str, Any]:
        return {
            "template": self.template, "limit": self.limit, "mode": self.mode,
            "body_chars": self.body_chars, "language": self.language,
            "chars_per_page": CHARS_PER_PAGE_ZH if self.language == "zh" else CHARS_PER_PAGE_EN,
            "estimated_pages": self.estimated_pages,
            "over_limit": self.over_limit, "over_by": self.over_by,
            "advisory": True,
        }


def count_body_chars(text: str, *, language: str = "zh") -> int:
    """统计正文字符数。

    中文按**字符**计，英文按**词**计——英文 2200 词/页 vs 中文 800 字/页，
    两者口径不同，混用会严重误判页数。
    """
    if language == "zh":
        return len([c for c in text if not c.isspace()])
    return len(text.split())


def page_budget(
    template: str,
    body_text: str,
    *,
    language: str = "zh",
) -> PageBudget:
    """计算页数预算（advisory）。"""
    limit = PAGE_LIMIT.get(template)
    chars = count_body_chars(body_text, language=language)
    per_page = CHARS_PER_PAGE_ZH if language == "zh" else CHARS_PER_PAGE_EN
    pages = chars // per_page if per_page else 0
    return PageBudget(
        template=template, limit=limit, body_chars=chars, language=language,
        estimated_pages=pages,
        over_by=max(0, pages - limit) if limit else 0,
    )


__all__ = [
    "StyleProfile", "PageBudget", "COMPETITION_ZH", "BUILTIN_PROFILES",
    "TEMPLATE_PROFILE", "PAGE_LIMIT", "CHARS_PER_PAGE_ZH", "CHARS_PER_PAGE_EN",
    "load_profile", "resolve_profile", "page_budget", "count_body_chars",
]
