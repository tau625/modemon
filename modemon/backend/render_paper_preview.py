#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成论文并把 PDF 渲染成图片，用于**人眼/模型视觉校验**。

测试只能证明"编译没报错"，证明不了"中文渲染正常、三线表正确、缩进生效"。
本脚本把结果渲染成图，供直接查看。
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

import fitz  # noqa: E402
from services import latex_export as lx  # noqa: E402

OUT = Path(r"E:\02_Installers\DailyApps\Modex-MH-Agent-RE\.papercheck")
TITLE = "基于线性规划的运输成本优化模型"
ABSTRACT = (
    "本文针对运输成本最小化问题建立线性规划模型，以各仓库到各配送点的运量为决策变量，"
    "以总运价为目标函数，在供需约束下求得最优调运方案与最小总成本 1234 元，"
    "并进一步做了运价与需求的灵敏度分析。结果表明该方案对运价扰动具有稳定性。"
)  # 中文约 110 字
KEYWORDS = ["运输问题", "线性规划", "灵敏度分析"]

SECTIONS = {
    "01_problem.md": """## 问题重述

某物流公司拥有 3 个仓库与 4 个配送点，单位运价矩阵已知，
需要在满足各配送点需求的前提下确定调运方案，使总运输成本最小。

## 问题分析

该问题属于经典的运输问题，其约束与目标均为线性，因此可建模为线性规划。
决策变量为各仓库到各配送点的运量，目标函数为总运价。
由于产销总量平衡，模型可行域非空且有界，最优解一定存在。
""",
    "02_model.md": """## 模型假设

- 各仓库的供给量已知且固定，不随时间变化
- 运输成本与运量严格成正比，不考虑固定成本与规模效应
- 不考虑运输时间、损耗与路径容量限制

## 符号说明

| 符号 | 含义 |
|---|---|
| $x_{ij}$ | 从仓库 $i$ 运往配送点 $j$ 的运量 |
| $c_{ij}$ | 仓库 $i$ 到配送点 $j$ 的单位运价 |
| $a_i$ | 仓库 $i$ 的供给上限 |
| $b_j$ | 配送点 $j$ 的需求下限 |

## 模型建立

以总运输成本最小为目标，建立如下线性规划模型：

$$\\min \\sum_{i=1}^{3}\\sum_{j=1}^{4} c_{ij} x_{ij}$$

约束条件包括供给上限约束、需求下限约束与非负约束。
该模型的系数矩阵为全幺模矩阵，因此其线性松弛的最优解即为整数最优解。
""",
    "03_solution.md": """## 求解结果

采用线性规划求解器求得最优调运方案，最优总成本为 1234 元，
具体各项指标见 @ref(tab:results)，不同算例的对比结果见 @ref(tab:record_table)。

从结果看，基准算例在 7 次迭代内收敛，求解耗时不足 0.04 秒，
说明该模型规模小、数值条件良好，适合在实际调度中快速求解。

## 灵敏度分析

当单位运价整体上浮 10% 时，最优调运方案的结构保持不变，
仅总成本按比例上升，说明该方案对运价扰动具有较好的稳定性。
当某配送点需求上浮 5% 时，调运量在邻近仓库之间重新分配，
总成本上升幅度小于需求增幅，体现出方案具备一定的弹性。
""",
}


def build_workspace(root: Path) -> Path:
    ws = root / "ws"
    (ws / "paper" / "sections").mkdir(parents=True)
    (ws / "figures").mkdir(parents=True)

    for name, text in SECTIONS.items():
        (ws / "paper" / "sections" / name).write_text(text, encoding="utf-8")

    (ws / "figures" / "all_results.json").write_text(json.dumps({
        "objective_value": 1234.0,
        "status": "optimal",
        "solver": "HiGHS",
        "iterations": 7,
        "time_s": 0.03125,
        "gap": 0.0,
        "scenarios": [
            {"算例": "基准", "目标值": 1234.0, "耗时_s": 0.031},
            {"算例": "运价+10%", "目标值": 1357.4, "耗时_s": 0.028},
            {"算例": "需求+5%", "目标值": 1295.7, "耗时_s": 0.033},
        ],
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    # 造一张真实的图——**必须配置中文字体**，否则轴标签会变成方框
    try:
        from services import figure_style as fs

        rep = fs.apply_cjk_style(preset="paper", strict=False)
        print("中文字体 :", rep.cjk_font or "(未找到，图会显示方框)")
        if rep.warnings:
            for w in rep.warnings:
                print("  warn:", w[:100])

        fig, ax = fs.new_figure(5.0, 3.0)
        xs = ["基准", "运价+10%", "需求+5%"]
        ys = [1234.0, 1357.4, 1295.7]
        ax.bar(xs, ys, color="#4477AA")
        ax.set_ylabel("总成本（元）")
        ax.set_title("不同算例的运输成本对比")
        for i, v in enumerate(ys):
            ax.text(i, v + 8, f"{v:.1f}", ha="center", fontsize=8)
        # save_figure 会自检是否缺字形，缺则抛错
        fs.save_figure(fig, ws / "figures" / "fig_scenarios.png")
        import matplotlib.pyplot as plt
        plt.close(fig)
        print("图表已生成（中文已校验）")
    except Exception as exc:
        print("图表生成失败:", exc)

    (ws / "figures" / "FIGURE_MANIFEST.md").write_text(
        "# 图表清单\n\n**结果与讨论**\n\n- fig_scenarios\n", encoding="utf-8")

    (ws / "paper" / "references.md").write_text(
        "1. 姜启源, 谢金星, 叶俊. 数学模型（第五版）. 高等教育出版社, 2018.\n"
        "2. Dantzig G B. Linear Programming and Extensions. Princeton University Press, 1963.\n"
        "3. 司守奎, 孙兆亮. 数学建模算法与应用（第二版）. 国防工业出版社, 2015.\n",
        encoding="utf-8")
    return ws


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    ws = build_workspace(OUT)

    r = lx.export_latex(ws, template="comp_cumcm", language="zh",
                        title=TITLE, abstract=ABSTRACT, keywords=KEYWORDS,
                        compile_pdf=True)
    print("ok     :", r.ok)
    print("pdf    :", r.pdf)
    print("pages  :", r.pages)
    print("budget :", json.dumps(r.budget, ensure_ascii=False))
    if r.compile_error:
        print("error  :", r.compile_error)
    if not r.pdf:
        return 1

    d = fitz.open(r.pdf)
    for i in range(min(3, d.page_count)):
        pix = d[i].get_pixmap(dpi=140)
        p = OUT / f"page{i + 1}.png"
        pix.save(str(p))
        print("rendered:", p.name, f"{pix.width}x{pix.height}")

    print("workdir:", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
