#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成「中文缺字形」的前后对比图，用于说明为什么必须做视觉校验。"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

OUT = Path(r"E:\02_Installers\DailyApps\Modex-MH-Agent-RE\reports\assets")

LABELS = ["基准", "运价+10%", "需求+5%"]
VALUES = [1234.0, 1357.4, 1295.7]


def render(path: Path, *, cjk: bool) -> None:
    import matplotlib
    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    from matplotlib import rcParams

    if cjk:
        from services import figure_style as fs
        fs.apply_cjk_style(preset="paper")
    else:
        # 还原"默认配置"：DejaVu Sans 不含 CJK 字形
        rcParams["font.family"] = "sans-serif"
        rcParams["font.sans-serif"] = ["DejaVu Sans"]
        rcParams["axes.unicode_minus"] = True
        rcParams["font.size"] = 9

    fig, ax = plt.subplots(figsize=(4.6, 2.9))
    ax.bar(LABELS, VALUES, color="#4477AA")
    ax.set_ylabel("总成本（元）")
    ax.set_title("不同算例的运输成本对比")
    for i, v in enumerate(VALUES):
        ax.text(i, v + 8, f"{v:.1f}", ha="center", fontsize=8)
    ax.grid(True, axis="y", alpha=0.3)
    try:
        fig.tight_layout()
    except Exception:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(path), dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    render(OUT / "tofu-before.png", cjk=False)
    print("before ->", OUT / "tofu-before.png")
    render(OUT / "cjk-after.png", cjk=True)
    print("after  ->", OUT / "cjk-after.png")
