"""图表样式：让生成的数据图**能正确显示中文**。

要解决的问题（实测发现）
------------------------
用 matplotlib 默认配置画图，中文会变成方框（tofu）：

    UserWarning: Glyph 38656 (\N{CJK UNIFIED IDEOGRAPH-9700}) missing from font(s) DejaVu Sans.

matplotlib 默认字体是 DejaVu Sans，**不含 CJK 字形**。一张坐标轴全是 `□□` 的图，
在中文论文里完全不可用。

**这是测试永远查不出来的缺陷**——编译成功、文件存在、尺寸正常，
只有把渲染结果**看一眼**才会发现。因此本模块负责把这件事在源头做对。

另外 `unicode_minus` 也要关闭，否则负号会显示成方框。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

#: 可用的中文字体（按优先级）——Windows 常见可用字体
CJK_FONT_CANDIDATES = ("SimHei", "Microsoft YaHei", "SimSun", "Noto Sans CJK SC",
                       "Source Han Sans SC", "WenQuanYi Micro Hei")

#: 论文常用配色（科研绘图惯例；此处为保守可读的默认值）
DEFAULT_PALETTE = ["#4477AA", "#EE6677", "#228833", "#CCBB44", "#66CCEE", "#AA3377"]

#: 版式预设
STYLE_PRESETS: dict[str, dict[str, Any]] = {
    # 论文正文插图：小字号、细线、无边框，适合双栏/单栏嵌入
    "paper": {
        "figure.dpi": 140, "savefig.dpi": 200, "font.size": 9,
        "axes.titlesize": 10, "axes.labelsize": 9, "legend.fontsize": 8,
        "xtick.labelsize": 8, "ytick.labelsize": 8,
        "axes.linewidth": 0.8, "lines.linewidth": 1.4,
        "axes.grid": True, "grid.alpha": 0.3, "grid.linewidth": 0.5,
        "axes.spines.top": False, "axes.spines.right": False,
        "figure.autolayout": True,
    },
    # 汇报/幻灯片：大字号
    "presentation": {
        "figure.dpi": 150, "savefig.dpi": 200, "font.size": 14,
        "axes.titlesize": 16, "axes.labelsize": 14, "legend.fontsize": 12,
        "axes.linewidth": 1.2, "lines.linewidth": 2.2,
        "axes.grid": True, "grid.alpha": 0.3,
    },
}


@dataclass
class FigureStyleReport:
    applied: bool = False
    cjk_font: Optional[str] = None
    available_cjk: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied, "cjk_font": self.cjk_font,
            "available_cjk": self.available_cjk, "warnings": self.warnings,
        }


def list_available_cjk() -> list[str]:
    """列出本机 matplotlib 能用的中文字体。"""
    try:
        from matplotlib import font_manager  # type: ignore
    except Exception:
        return []
    names = {f.name for f in font_manager.fontManager.ttflist}
    return [c for c in CJK_FONT_CANDIDATES if c in names]


def apply_cjk_style(
    *,
    preset: str = "paper",
    font: Optional[str] = None,
    palette: Optional[list[str]] = None,
    strict: bool = False,
) -> FigureStyleReport:
    """为 matplotlib 配置中文字体与论文风格。

    Args:
        preset: `paper` | `presentation`
        font: 指定字体；None 时按候选列表自动挑一个可用的。
        palette: 配色列表；None 时用默认。
        strict: True 时若找不到中文字体则抛错（避免悄悄产出方框图）。

    Returns:
        FigureStyleReport，`applied=False` 表示未成功配置（调用方应据此告警）。
    """
    rep = FigureStyleReport()
    try:
        import matplotlib  # type: ignore
        matplotlib.use("Agg", force=True)
        from matplotlib import rcParams  # type: ignore
    except Exception as exc:
        rep.warnings.append(f"matplotlib 不可用: {exc}")
        return rep

    rep.available_cjk = list_available_cjk()
    chosen = font if font and font in rep.available_cjk else (
        rep.available_cjk[0] if rep.available_cjk else None)

    if chosen is None:
        msg = ("未找到可用的中文字体；图表中的中文将显示为方框。"
               f"候选：{', '.join(CJK_FONT_CANDIDATES)}")
        rep.warnings.append(msg)
        if strict:
            raise RuntimeError(msg)
    else:
        rep.cjk_font = chosen

    # 1) 风格预设
    for k, v in STYLE_PRESETS.get(preset, STYLE_PRESETS["paper"]).items():
        rcParams[k] = v

    # 2) ★ 中文字体族
    if chosen:
        rcParams["font.family"] = "sans-serif"
        rcParams["font.sans-serif"] = [chosen, "DejaVu Sans"]

    # 3) ★ 负号：默认的 U+2212 在很多字体里缺失，会显示成方框
    rcParams["axes.unicode_minus"] = False

    # 4) 配色
    from matplotlib import cycler  # type: ignore
    rcParams["axes.prop_cycle"] = cycler(color=palette or DEFAULT_PALETTE)

    rep.applied = True
    return rep


def new_figure(width_in: float = 5.0, height_in: float = 3.0):
    """建一个符合论文尺寸的 figure（需先调用 `apply_cjk_style`）。"""
    import matplotlib.pyplot as plt  # type: ignore

    fig, ax = plt.subplots(figsize=(width_in, height_in))
    return fig, ax


def save_figure(fig, path: Path, *, tight: bool = True, dpi: Optional[int] = None) -> Path:
    """保存图表，并**校验文件中确实嵌入了中文字形**。

    这里做一次轻量自检：若标题/标签含中文但渲染时缺字形，
    matplotlib 会发出 Glyph missing 警告。我们用 warnings 捕获它，
    避免产出"看起来成功、实际是方框"的图。
    """
    import warnings

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        if tight:
            try:
                fig.tight_layout()
            except Exception:
                pass
        fig.savefig(str(p), dpi=dpi, bbox_inches="tight")
    missing = [str(w.message) for w in caught if "missing from font" in str(w.message)]
    if missing:
        raise RuntimeError(
            "图表中的中文缺字形，会渲染成方框："
            + "; ".join(missing[:3])
            + "——请先调用 apply_cjk_style() 配置中文字体"
        )
    return p


__all__ = [
    "FigureStyleReport", "apply_cjk_style", "list_available_cjk",
    "new_figure", "save_figure", "CJK_FONT_CANDIDATES",
    "DEFAULT_PALETTE", "STYLE_PRESETS",
]
