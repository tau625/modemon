#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""成文链真实验证：LaTeX 导出 + 编译出 PDF。

造一个仿真工作区（正文/数据真相源/图表/参考文献），跑完整导出链路，
产出真实 PDF 并校验页数预算。
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

from services import deai_lint as dl  # noqa: E402
from services import latex_export as lx  # noqa: E402
from services import paper_build as pb  # noqa: E402
from services import tex_runtime as tx  # noqa: E402
from services import typography as ty  # noqa: E402

OUT = Path(r"E:\02_Installers\DailyApps\Modex-MH-Agent-RE\reports\21-typesetting-chain.md")

SECTIONS = {
    "01_problem.md": """## 问题重述

某物流公司拥有 3 个仓库与 4 个配送点，单位运价矩阵已知，
需要在满足各配送点需求的前提下最小化总运输成本。

## 问题分析

该问题属于经典的运输问题，可建模为线性规划。
决策变量为各仓库到各配送点的运量，目标函数为总运价，约束为供需平衡。
""",
    "02_model.md": """## 模型假设

- 各仓库供给量已知且固定
- 运输成本与运量严格成正比，无固定成本
- 不考虑运输时间与损耗

## 模型建立

设 $x_{ij}$ 表示从仓库 $i$ 运往配送点 $j$ 的运量，
$c_{ij}$ 为单位运价。则模型为

$$\\min \\sum_{i=1}^{3}\\sum_{j=1}^{4} c_{ij} x_{ij}$$

约束条件为各仓库供给上限与各配送点需求下限。
""",
    "03_solution.md": """## 求解结果

采用线性规划求解器求得最优调运方案，最优总成本见表 1。

**求解环境**：Python 3.11 + 线性规划求解器，迭代次数与耗时见结果表。

## 灵敏度分析

当单位运价整体上浮 10% 时，最优调运方案保持不变，
说明该方案对运价扰动具有稳定性。
""",
}


def build_workspace(root: Path) -> Path:
    ws = root / "ws"
    (ws / "paper" / "sections").mkdir(parents=True)
    (ws / "figures").mkdir(parents=True)

    for name, text in SECTIONS.items():
        (ws / "paper" / "sections" / name).write_text(text, encoding="utf-8")

    # ★ 数据真相源：表格只能由它生成
    (ws / "figures" / "all_results.json").write_text(json.dumps({
        "objective_value": 1234.0,
        "status": "optimal",
        "solver": "HiGHS",
        "iterations": 7,
        "time_s": 0.03125,
        "gap": 0.0,
        "scenarios": [
            {"case": "基准", "objective": 1234.0, "time_s": 0.031},
            {"case": "运价+10%", "objective": 1357.4, "time_s": 0.028},
            {"case": "需求+5%", "objective": 1295.7, "time_s": 0.033},
        ],
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    # 图表（按命名约定）
    (ws / "figures" / "fig_result.png").write_bytes(
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 200)
    (ws / "figures" / "tikz_arch.drawio").write_text("<mxfile/>", encoding="utf-8")
    (ws / "figures" / "FIGURE_MANIFEST.md").write_text(
        "# 图表清单\n\n**结果与讨论**\n\n- fig_result\n\n**模型架构**\n\n- tikz_arch\n",
        encoding="utf-8")

    # 参考文献
    (ws / "paper" / "references.md").write_text(
        "1. 姜启源. 数学模型（第五版）. 高等教育出版社, 2018.\n"
        "2. Dantzig G B. Linear Programming and Extensions. Princeton, 1963.\n",
        encoding="utf-8")
    return ws


def main() -> int:
    print("=" * 74)
    print("成文链真实验证：LaTeX 导出 + 编译")
    print("=" * 74)

    # 0) TeX 运行时
    rt = tx.resolve_tex_runtime()
    print("TeX 运行时  :", rt.state, "|", rt.note)
    print("xelatex     :", rt.xelatex)
    print("随包安装器  :", rt.installer_available)
    print()

    with tempfile.TemporaryDirectory(prefix="modemon-paper-") as td:
        ws = build_workspace(Path(td))
        print("工作区      :", ws)

        # 1) 排版规格
        prof = ty.resolve_profile("comp_cumcm")
        print("排版规格    :", prof.name, "(source=%s)" % prof.source)
        print("  字体      :", prof.fonts)
        print("  正文      :", f"{prof.body['font_size_pt']}pt / {prof.body['line_spacing']}倍 / "
                              f"首行缩进 {prof.body['first_line_indent_chars']} 字符")
        print("  页边距    :", f"{prof.page['margin_top_cm']}cm")
        print()

        # 2) 装配论文
        doc, notes = pb.build_paper(ws, template="comp_cumcm", language="zh",
                                    title="基于线性规划的运输成本优化模型",
                                    abstract="本文针对运输成本最小化问题建立线性规划模型，"
                                             "求得最优调运方案与最小总成本，并进行了灵敏度分析。",
                                    keywords=["运输问题", "线性规划", "灵敏度分析"])
        print("装配结果：")
        print("  章节      :", len(doc.sections))
        print("  **表格（程序生成）**:", len(doc.tables))
        for t in doc.tables:
            print("     -", t.name, f"{len(t.rows)} 行 x {len(t.headers)} 列", "|", t.caption)
        print("  图        :", len(doc.figures), [f.path.split('/')[-1] for f in doc.figures])
        print("  参考文献  :", len(doc.references))
        for n in notes:
            print("  note      :", n)
        print()

        # 表格内容（证明来自数据文件而非模型）
        if doc.tables:
            print("结果表内容（取自 all_results.json）：")
            for row in doc.tables[0].rows:
                print("    ", row)
            print()

        # 3) 去 AI 味检查（故意留一处违规，验证能抓到）
        (ws / "paper" / "sections" / "04_draft.md").write_text(
            "## 讨论\n\n**结论：** 模型有效。\n\n作为一个AI，我认为该方案合理。\n",
            encoding="utf-8")
        doc2, _ = pb.build_paper(ws, template="comp_cumcm", language="zh")
        rep = dl.lint_paper(ws, sections=[s.body for s in doc2.sections],
                            manifest_captions=["结果图"])
        print("去 AI 味检查：")
        print("  ok        :", rep.ok, "| errors:", len(rep.errors), "| warns:", len(rep.warnings))
        for i in rep.issues:
            print(f"    [{i.severity}] {i.rule}: {i.message[:70]}")
        print()

        # 4) 导出 + 编译
        t0 = time.monotonic()
        res = lx.export_latex(
            ws, template="comp_cumcm", language="zh",
            title="基于线性规划的运输成本优化模型",
            abstract="本文针对运输成本最小化问题建立线性规划模型，求得最优调运方案与最小总成本。",
            keywords=["运输问题", "线性规划", "灵敏度分析"],
            compile_pdf=True)
        dt = time.monotonic() - t0

        print("导出结果 (%.1fs)：" % dt)
        print("  ok        :", res.ok)
        print("  tex       :", res.tex)
        print("  pdf       :", res.pdf)
        print("  pages     :", res.pages)
        print("  budget    :", json.dumps(res.budget, ensure_ascii=False) if res.budget else None)
        if res.compile_error:
            print("  compile_error:", res.compile_error)
        for n in res.notes:
            print("  note      :", n)
        print()

        pdf_size = Path(res.pdf).stat().st_size if res.pdf else 0
        tex_size = Path(res.tex).stat().st_size if res.tex else 0
        print("产物大小： tex=%d 字节  pdf=%d 字节" % (tex_size, pdf_size))
        print()

        # 5) DOCX 导出（同一份论文模型 + 同一套规格）
        from services import docx_export as dx
        dres = dx.export_docx(ws, template="comp_cumcm",
                              title="基于线性规划的运输成本优化模型",
                              abstract="本文针对运输成本最小化问题建立线性规划模型。",
                              keywords=["运输问题", "线性规划", "灵敏度分析"])
        print("DOCX 导出：")
        print("  ok      :", dres["ok"])
        print("  docx    :", dres["docx"])
        print("  bytes   :", dres["bytes"])
        print("  表格    :", dres["tables"], "| 图:", dres["figures"], "| 参考文献:", dres["references"])

        # 5) 落盘留档
        lines = [
            "# 成文链真实验证：LaTeX 导出与编译",
            "",
            "> 由 `paper_chain_check.py` 生成。数据源为仿真工作区，**不代表真实竞赛结果**。",
            "",
            "## TeX 运行时",
            "",
            "```json",
            json.dumps(rt.as_dict(), ensure_ascii=False, indent=1),
            "```",
            "",
            "> **实测约束**：随包 TeXLive 是**未初始化的 MiKTeX**，直接编译会报",
            "> `fresh TeX installation / Please finish the setup`。",
            "> 这印证了蓝方启动日志的「检查工具可用性（不等待 LaTeX 在线安装）」",
            "> 以及其 `latex:get-status` / `latex:install` 两个 IPC 的存在。",
            "> 本次验证**复用系统已装的 TeXLive**，未改动目标安装目录。",
            "",
            "## 排版规格（恢复真值）",
            "",
            f"- 规格名：`{prof.name}`（来源 `{prof.source}`）",
            f"- 字体：{prof.fonts}",
            f"- 正文：{prof.body['font_size_pt']}pt / {prof.body['line_spacing']} 倍行距 / "
            f"首行缩进 {prof.body['first_line_indent_chars']} 字符",
            f"- 页边距：{prof.page['margin_top_cm']}cm（四边）",
            f"- 标题：一至四级 {prof.headings['level1_pt']}/{prof.headings['level2_pt']}/"
            f"{prof.headings['level3_pt']}/{prof.headings['level4_pt']}pt，加粗，一级居中",
            f"- 三线表：{prof.table['top_border_pt']}-{prof.table['header_border_pt']}-"
            f"{prof.table['bottom_border_pt']}pt，表内 {prof.table['font_size_pt']}pt",
            f"- 图宽上限：{prof.image['max_width_cm']}cm",
            f"- 参考文献：悬挂缩进 {prof.references['hanging_indent_cm']}cm，"
            f"{prof.references['font_size_pt']}pt",
            "",
            "## 程序化表格（★ 绝不经过模型）",
            "",
            f"从 `figures/all_results.json` 生成 **{len(doc.tables)}** 张表：",
            "",
        ]
        for t in doc.tables:
            lines += [f"### `TABLE_{t.name}.md`（{len(t.rows)} 行）", "", "```markdown",
                      t.to_markdown()[:1500], "```", ""]
        lines += [
            "> 设计要点（来自蓝方验证过的做法）：**表格不做模型誊抄**，",
            "> 一律由程序从数据真相源生成——模型誊抄数字会出错，而论文里的数字错了就是硬伤。",
            "",
            "### 生成的 LaTeX 表（节选）",
            "",
            "```latex",
            (doc.tables[0].to_latex() if doc.tables else "")[:1200],
            "```",
            "",
            "## 去 AI 味检查",
            "",
            f"- 通过：**{rep.ok}**（errors {len(rep.errors)} / warns {len(rep.warnings)}）",
            "",
            "| 规则 | 级别 | 说明 |",
            "|---|---|---|",
        ]
        for i in rep.issues:
            lines.append(f"| `{i.rule}` | {i.severity} | {i.message[:90]} |")
        lines += [
            "",
            "> 检出样例是**故意植入**的：`**结论：**`（冒号写在加粗标记内，",
            "> 复现材料标注这是「最高频痕迹」）与「作为一个AI」自指表达。",
            "",
            "## 导出与编译结果",
            "",
            "| 项 | 值 |",
            "|---|---|",
            f"| 导出成功 | **{res.ok}** |",
            f"| `.tex` | `{res.tex}`（{tex_size} 字节） |",
            f"| `.pdf` | `{res.pdf}`（{pdf_size} 字节） |",
            f"| **实测页数** | **{res.pages}** |",
            f"| 页数预算（advisory） | {json.dumps(res.budget, ensure_ascii=False)} |",
            f"| 编译错误 | `{res.compile_error or '无'}` |",
            f"| 耗时 | {dt:.1f}s |",
            "",
            "## DOCX 导出（同一论文模型，同一排版规格）",
            "",
            "| 项 | 值 |",
            "|---|---|",
            f"| 导出成功 | **{dres['ok']}** |",
            f"| 文件 | `{dres['docx']}`（{dres['bytes']} 字节） |",
            f"| 表格 / 图 / 参考文献 | {dres['tables']} / {dres['figures']} / {dres['references']} |",
            "",
            "### 中文 Word 的三个坑（已处理，并由测试回读验证）",
            "",
            "1. **东亚字体必须单独设 `w:eastAsia`**——只设 `run.font.name` 只作用于西文。",
            "2. **首行缩进要按「字符」而非磅**——用 `w:firstLineChars`（1/100 字符单位），",
            "   才能随字号自适应；写死磅值在改字号后会错位。",
            "3. **三线表靠边框控制**——上/下粗 1.5pt、表头下细 0.75pt、中间无线。",
            "",
            "## 编译日志尾部",
            "",
            "```",
            (res.log_tail or "(无)")[:2500],
            "```",
            "",
            "## 生成的 .tex（节选）",
            "",
            "```latex",
            (Path(res.tex).read_text(encoding="utf-8")[:3000] if res.tex else ""),
            "```",
            "",
        ]
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text("\n".join(lines), encoding="utf-8")
        print()
        print("报告已写入:", OUT)

        return 0 if res.ok and res.pdf else 1


if __name__ == "__main__":
    raise SystemExit(main())
