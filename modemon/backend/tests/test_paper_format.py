"""论文格式约定 + 表格标签歧义 + 列名本地化 回归测试（流 C）。

针对**真实跑完的工作区**里抓到的三处缺陷，把它们转成可执行断言：

  1. **表格标签歧义**：导出的「求解结果」表出现 4 行都叫「总成本」
     （`scenario1_basic.Z0` / `scenario2.Z0` / `cost_change_summary.Z0`
     折叠成同一标签）——`_label_for` 只取叶子，丢了分组信息。
  2. **记录表列名未本地化**：表头是 `name`，行是 `x11/x12/x21…`
     （3×4 运输问题），应可读为 `DC1→R1`。
  3. **引擎/agent 论文格式错配**：`build_paper` 只认 `paper/sections/*.md`
     或 `paper/main.md`，而 agent 直写 `paper/main.tex`；两边无约定导致
     引擎读到 `body_chars=0`，把 27.5 KB 的成品论文报成空正文。

`REAL_RESULTS` 是那份真实 `figures/all_results.json` 的**逐字结构复刻**
（数值原样保留），用例直接以它为输入，而不是另造一份"好看"的数据。
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from services import paper_build as pb  # noqa: E402
from services import step_runner as sr  # noqa: E402

PASS = 0
FAIL = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  %s" % name)
    else:
        FAIL += 1
        FAILURES.append(name)
        print("  FAIL  %s  %s" % (name, detail[:200]))


# ---------------------------------------------------------------------------
# 真实坏样本：那次跑完的工作区里的 all_results.json
# ---------------------------------------------------------------------------

REAL_RESULTS: dict = {
    "problem": "2026 CUMCM A (simulated): 3 DCs -> 4 demand points transportation LP",
    "data": {
        "supply": [35.0, 25.0, 30.0],
        "demand": [20.0, 25.0, 20.0, 25.0],
        "unit_cost": [[8.0, 12.0, 10.0, 14.0], [11.0, 7.0, 13.0, 9.0],
                      [12.0, 10.0, 6.0, 11.0]],
    },
    "optimal_objective": 775.0,
    # ↓ 记录表（index=0）的来源：实测表头 `name`、行 `x11/x12/...`
    "variables": [
        {"name": "x11", "value": 20.0}, {"name": "x12", "value": 15.0},
        {"name": "x13", "value": 0.0}, {"name": "x14", "value": 0.0},
        {"name": "x21", "value": 0.0}, {"name": "x22", "value": 10.0},
        {"name": "x23", "value": 0.0}, {"name": "x24", "value": 15.0},
        {"name": "x31", "value": -0.0}, {"name": "x32", "value": 0.0},
        {"name": "x33", "value": 20.0}, {"name": "x34", "value": 10.0},
    ],
    "optimal_plan_matrix_t0": [[20.0, 15.0, 0.0, 0.0], [0.0, 10.0, 0.0, 15.0],
                              [-0.0, 0.0, 20.0, 10.0]],
    "optimal_family": {
        "param": "t in [0,15]",
        "formula": "x11=20, x12=15-t, x14=t, x22=10+t, x24=15-t, x33=20, x34=10",
        "cost_always": 775.0,
        "samples": [{"t": 0.0, "Z": 775.0, "feasible": True},
                    {"t": 15.0, "Z": 775.0, "feasible": True}],
    },
    # ↓ 「4 行都叫总成本」的元凶：4 个不同分组下同名叶子 total_cost
    "scenarios": {
        "S1_baseline": {"desc": "原问题最优调运", "total_cost": 775.0,
                        "delta_vs_base": 0.0, "delta_pct": 0.0},
        "S2A_shortage_p20": {"desc": "DC2-30%, 口径A 缺货+惩罚 p=20",
                             "total_cost": 857.5, "Z_trans": 707.5,
                             "shortage_total_t": 7.5,
                             "delta_vs_base": 82.5, "delta_pct": 10.65},
        "S2A_trans_only": {"desc": "DC2-30%, 口径A 仅运输成本项",
                           "total_cost": 707.5,
                           "delta_vs_base": -67.5, "delta_pct": -8.71},
        "S2B_ext_1p5x": {"desc": "DC2-30%, 口径B 外部应急运力(1.5×销地最低价)",
                         "total_cost": 801.25,
                         "delta_vs_base": 26.25, "delta_pct": 3.39},
    },
    "scenario2": {
        "supply2": [35.0, 17.5, 30.0],
        "gap_t": 7.5,
        "caliber_A": {"Z_trans": 707.5, "Z_by_p": {"20": 857.5, "50": 1082.5},
                      "shortage": [0.0, 0.0, 0.0, 7.5]},
        "caliber_B": {"unit_ext_price": [12.0, 10.5, 9.0, 13.5], "Z": 801.25,
                      "ext_by_R": [0.0, 7.5, 0.0, 0.0]},
        "marginal_DC2": {"slope_yuan_per_ton": 9.0,
                         "samples": [{"s2": 10.0, "Z_trans": 640.0},
                                     {"s2": 17.5, "Z_trans": 707.5}]},
    },
    "scenario3": {
        "global_scale": [{"lambda": 0.9, "Z": 697.5}, {"lambda": 1.0, "Z": 775.0}],
        "worst_single_up": 16.0,
        "worst_single_down": -21.0,
        "monte_carlo": {"B": 20000, "seed": 20261003, "mean": 765.57,
                        "std": 17.92, "p5": 736.14, "p50": 765.37, "p95": 795.21},
    },
    "iterations": {"scenario1_lpit": 6, "scenario2_caliberA_nit": 12},
    "timing_sec": {"scenario1": 0.0027, "monte_carlo": 20.2466, "total": 20.2611},
}

#: 与 `_label_for` 同名叶子冲突直接相关的四个 key
COLLIDING_KEYS = (
    "scenarios.S1_baseline.total_cost",
    "scenarios.S2A_shortage_p20.total_cost",
    "scenarios.S2A_trans_only.total_cost",
    "scenarios.S2B_ext_1p5x.total_cost",
)

#: 原始下标键（不允许原样出现在论文表里的形态）
RAW_INDEX_RE = re.compile(r"\bx\d{2}\b")


def real_workspace(root: Path) -> Path:
    """造一个与真实工作区**同构**的工作区（含那份 all_results.json）。"""
    ws = root / "ws"
    (ws / "figures").mkdir(parents=True)
    (ws / "figures" / "all_results.json").write_text(
        json.dumps(REAL_RESULTS, ensure_ascii=False, indent=2), encoding="utf-8")
    return ws


AGENT_TEX_TEMPLATE = r"""\documentclass[12pt,a4paper]{ctexart}
\usepackage{amsmath,amssymb,graphicx,booktabs,caption}
\title{基于线性规划的运输成本优化模型}
\author{参赛队}
\date{\today}
\begin{document}
\maketitle
\begin{abstract}
本文针对 3 个配送中心与 4 个需求点之间的运输成本最小化问题建立线性规划模型，
求得最优调运方案与最小总成本，并对供应中断与运价扰动做了灵敏度分析。
\end{abstract}
\keywords{运输问题；线性规划；灵敏度分析}
%(body)s
\section{结论}
模型给出确定性的最优调运方案，总成本 775 元，且该最优解不唯一。
\end{document}
"""


def agent_tex(note: str = "") -> str:
    """agent 在 `comp-paper-zh` 步骤里直出的成品 `.tex`（约 29 KB）。

    体量对齐实测：那次 agent 写出的是 **27,538 B** 的完整论文，
    而引擎的桩只有 1,845 B——本用例必须落在"成品"那一档才有意义。
    """
    para = ("本文以总成本最小为目标，将配送中心的供应量与需求点的需求量写成约束，"
            "并用单纯形法求解。对偶变量给出了各需求点增加一单位需求时的边际成本，"
            "从而支撑后续的应急调度决策，也为灵敏度分析提供了定价解释。")
    body = "\n".join(
        f"\\section{{章节 {i}}}\n" + (para * 10) for i in range(1, 10))
    return (note + AGENT_TEX_TEMPLATE % {"body": body})


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------


def test_real_result_table_unique_labels() -> None:
    """★ 真实坏样本回归：同一张表内标签必须唯一。"""
    print("\n[1] 真实坏样本：结果表标签唯一（原来 4 行都叫「总成本」）")
    with tempfile.TemporaryDirectory() as td:
        ws = real_workspace(Path(td))
        src = pb.load_results(ws)
        t = pb.build_result_table(src)
        check("结果表生成成功", t is not None)

        dups = pb.table_label_duplicates(t)
        check("**同一张表内没有重复标签**", dups == [], str(dups))

        labels = [r[0] for r in t.rows]
        cost_rows = [l for l in labels if l.endswith("总成本")]
        # 真实数据里共 5 行「总成本」：4 个 `scenarios.*.total_cost`
        # + 1 个 `scenario2.caliber_B.Z`（数值 801.25 与 S2B 确实相等，
        #   所以**只能靠标签**区分——这正是缺陷的核心）。
        check("**「总成本」行共 5 行**", len(cost_rows) == 5, str(cost_rows))
        check("**它们两两不同**", len(set(cost_rows)) == 5, str(cost_rows))
        check("**每一行都带分组语义（不只是「总成本」）**",
              all(len(l) > len("总成本") for l in cost_rows), str(cost_rows))
        for key, marker in (("S1_baseline", "原问题基准"),
                            ("S2A_shortage_p20", "缺货惩罚"),
                            ("S2A_trans_only", "仅运输成本"),
                            ("S2B_ext_1p5x", "外部应急运力")):
            check(f"标签含场景语义 `{marker}`",
                  any(marker in l for l in cost_rows), str(cost_rows))

        # 直接对"元凶"的 4 个 key 断言：一一对应且互不相同
        colliding = [k for k in src.scalars if k.endswith(".total_cost")]
        check("**数据里确有 4 个同名叶子 `total_cost`**",
              len(colliding) == 4, str(colliding))
        check("采集到的冲突 key 与预期一致",
              set(colliding) == set(COLLIDING_KEYS), str(colliding))
        col_labels = [pb._label_for(k) for k in colliding]
        check("**4 个 `total_cost` 的标签互不相同**",
              len(set(col_labels)) == 4, str(col_labels))
        check("**它们都带分组限定**",
              all(len(l) > len("总成本") for l in col_labels), str(col_labels))

        # 同一数值出现在两个场景里也不混淆
        check("数值相同的两行（801.25）标签不同",
              len({"情景 S2B 外部应急运力 总成本", "情景2 口径B 总成本"}
                  & set(cost_rows)) == 2, str(cost_rows))

        # 原始 key 不得原样进论文
        check("**没有标签是原始叶子名**",
              not any(l in ("total_cost", "z", "z0") for l in labels), str(labels[:6]))
        check("**没有标签带原始分组路径**",
              not any("." in l for l in labels), str(labels[:6]))


def test_label_for_group_semantics() -> None:
    """`_label_for` 必须保留分组语义（验收点）。"""
    print("\n[2] `_label_for`：分组语义 + 大小写不敏感")
    l1 = pb._label_for("scenario1_basic.Z0")
    check("**scenario1_basic.Z0 含分组「情景1」**", "情景1" in l1, l1)
    check("**scenario1_basic.Z0 仍是「最优总成本」**", "最优总成本" in l1, l1)
    check("**它不再等于裸「最优总成本」**", l1 != "最优总成本", l1)

    l2 = pb._label_for("scenario2_penalty_sensitivity.penalty_p")
    check("**罚系数场景字段带「罚系数」前缀**", "罚系数" in l2, l2)

    check("三个 Z0 场景标签互不相同",
          len({pb._label_for("scenario1_basic.Z0"), pb._label_for("scenario2.Z0"),
               pb._label_for("cost_change_summary.Z0")}) == 3,
          str([pb._label_for(k) for k in
               ("scenario1_basic.Z0", "scenario2.Z0", "cost_change_summary.Z0")]))

    check("查表大小写不敏感",
          pb._label_for("Scenario1_Basic.Z0") == l1,
          f"{pb._label_for('Scenario1_Basic.Z0')} != {l1}")
    check("**顶层叶子不加前缀（旧行为保持不变）**",
          pb._label_for("objective_value") == "目标值"
          and pb._label_for("iterations") == "迭代次数",
          f"{pb._label_for('objective_value')} / {pb._label_for('iterations')}")
    check("未登记的分组也保留分组信息（不退化回裸叶子）",
          pb._label_for("scenario9_weird.Z0").startswith("情景9"), 
          pb._label_for("scenario9_weird.Z0"))


def test_unique_labels_safety_net() -> None:
    """去重安全网：前缀映射撞车时也必须给出不同标签。"""
    print("\n[3] 标签唯一性安全网（`unique_labels` 三级兜底）")
    got = pb.unique_labels(["scenario1_basic.Z0", "scenario1.Z0"])
    check("两个同前缀 key 得到不同标签",
          got["scenario1_basic.Z0"] != got["scenario1.Z0"], str(got))
    check("**都仍含分组「情景1」（不丢语义）**",
          all("情景1" in v for v in got.values()), str(got))
    check("去重兜底用原始路径限定",
          "scenario1" in got["scenario1.Z0"], str(got))

    many = pb.unique_labels(["a.Z0"] * 1 + ["a.Z0", "b.Z0", "c.Z0"])
    check("多 key 映射不产生重复标签", len(set(many.values())) == 3, str(many))

    dup_table = pb.TableSpec(name="t", caption="c", headers=["指标", "数值"],
                             rows=[["总成本", "1"], ["总成本", "2"], ["均值", "3"]])
    check("**自检函数能报出重复标签**",
          pb.table_label_duplicates(dup_table) == ["总成本"],
          str(pb.table_label_duplicates(dup_table)))


def test_record_table_localization() -> None:
    """记录表：列名与下标键都要本地化（验收点）。"""
    print("\n[4] 记录表列名本地化（`name` / `x11` 不得进论文）")
    with tempfile.TemporaryDirectory() as td:
        ws = real_workspace(Path(td))
        src = pb.load_results(ws)
        r = pb.build_record_table(src)
        check("记录表生成成功", r is not None)
        if not r:
            return

        check("**表头不再是原始键 `name`**", "name" not in r.headers, str(r.headers))
        check("**表头被识别为「变量」列**", r.headers[0] == "变量", str(r.headers))
        check("列名已本地化（无下划线原始键）",
              not any("_" in h for h in r.headers), str(r.headers))

        flat = " ".join(" ".join(row) for row in r.rows)
        check("**没有任何单元格原样输出 `x11` 这类下标键**",
              not RAW_INDEX_RE.search(flat), flat[:160])
        first_col = [row[0] for row in r.rows]
        check("**`x11` 变成 `DC1→R1`**", first_col[0] == "DC1→R1", str(first_col[:4]))
        check("**`x34` 变成 `DC3→R4`**", first_col[-1] == "DC3→R4", str(first_col[-2:]))
        check("12 行全在（3×4 运输问题）", len(first_col) == 12, str(len(first_col)))

    # 非矩阵键不受影响：普通记录表的列名照旧走 FIELD_LABELS
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "figures").mkdir(parents=True)
        (ws / "figures" / "all_results.json").write_text(json.dumps(
            {"cases": [{"case": "基准", "obj": 1234.0}]}, ensure_ascii=False),
            encoding="utf-8")
        r2 = pb.build_record_table(pb.load_results(ws))
        check("普通记录表列名仍用登记标签",
              r2 is not None and "算例" in r2.headers, str(r2.headers if r2 else None))
        check("非下标键的值不被改写",
              r2 is not None and r2.rows[0][0] == "基准", str(r2.rows if r2 else None))


def test_value_label_units() -> None:
    """`_value_label` 的映射规则与边界。"""
    print("\n[5] `_value_label` 映射规则")
    check("x11 -> DC1→R1", pb._value_label("x11") == "DC1→R1", pb._value_label("x11"))
    check("x_1_10 -> DC1→R10（多位数需分隔符）",
          pb._value_label("x_1_10") == "DC1→R10", pb._value_label("x_1_10"))
    check("c21 -> DC2→R1 单位运价",
          pb._value_label("c21") == "DC2→R1 单位运价", pb._value_label("c21"))
    check("未知前缀也不原样输出下标键",
          "x11" not in pb._value_label("a11"), pb._value_label("a11"))
    check("**含分隔符的歧义键不做猜测**（`x1011` 保持原样）",
          pb._value_label("x1011") == "x1011", pb._value_label("x1011"))
    check("普通数值/文本不受影响",
          pb._value_label(0.5) == "0.5" and pb._value_label("基准") == "基准"
          and pb._value_label(None) == "—",
          f"{pb._value_label(0.5)} / {pb._value_label('基准')} / {pb._value_label(None)}")
    check("中文标签不会被误判为下标键", not pb._is_indexed_key("供应下降（吨）"))


def test_paper_format_sections_first() -> None:
    """约定格式：`paper/sections/*.md` → `body_source=sections`。"""
    print("\n[6] 格式约定：正文写 `paper/sections/*.md`（引擎装配）")
    with tempfile.TemporaryDirectory() as td:
        ws = real_workspace(Path(td))
        (ws / "paper" / "sections").mkdir(parents=True)
        (ws / "paper" / "sections" / "01_问题重述.md").write_text(
            "## 问题重述\n\n某物流公司有 3 个仓库。\n", encoding="utf-8")
        (ws / "paper" / "sections" / "02_模型建立.md").write_text(
            "## 模型建立\n\n设 $x_{ij}$ 为运量。\n", encoding="utf-8")

        doc, notes = pb.build_paper(ws, template="comp_cumcm", title="运输模型")
        check("**body_source 标为 sections**", doc.body_source == "sections",
              doc.body_source)
        check("**分节被装配成 2 个章节**", len(doc.sections) == 2,
              str([s.title for s in doc.sections]))
        check("notes 说明正文来源", any("paper/sections/" in n for n in notes),
              str(notes))
        check("不走预编译路径", not doc.is_prebuilt and doc.prebuilt_tex == "")


def test_paper_format_prebuilt_tex() -> None:
    """agent 直出成品 `.tex` → 只编译不重建（P0 的引擎侧收口）。"""
    print("\n[7] 格式约定：agent 直出 `paper/main.tex` → 只编译不重建")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "paper").mkdir(parents=True)
        (ws / "figures").mkdir(parents=True)
        target = ws / "paper" / "main.tex"
        target.write_text(agent_tex(), encoding="utf-8")
        before = sha256(target)
        size = target.stat().st_size
        check("样张确实是成品级 `.tex`（> 20 KB）", size > 20_000, str(size))

        doc, notes = pb.build_paper(ws, template="comp_cumcm", title="运输模型")
        check("**body_source 标为 prebuilt_tex**",
              doc.body_source == "prebuilt_tex", doc.body_source)
        check("**doc 记录预编译文件路径**",
              doc.prebuilt_tex == "paper/main.tex" and doc.is_prebuilt,
              f"{doc.prebuilt_tex} / {doc.is_prebuilt}")
        check("**正文按 `.tex` 计数，不再报「空正文」**",
              len(doc.body_text) > 8_000, str(len(doc.body_text)))
        check("抽出的正文不含导言区",
              "\\documentclass" not in doc.body_text, doc.body_text[:80])
        check("**notes 显式声明只编译不重建**",
              any("只编译不重建" in n for n in notes), str(notes))
        check("**不再出现「未找到正文」**",
              not any("未找到正文" in n for n in notes), str(notes))
        check("**原文件未被改写（内容 hash 一致）**", sha256(target) == before)
        check("页数预算按真实正文计算（> 0 页）",
              doc.budget().estimated_pages > 0, str(doc.budget().as_dict()))

    # 优先级：main.md 仍高于预编译 .tex（兼容路径不被新路径抢走）
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "paper").mkdir(parents=True)
        (ws / "paper" / "main.tex").write_text(agent_tex(), encoding="utf-8")
        (ws / "paper" / "main.md").write_text(
            "## 问题重述\n\n正文从这里来。\n", encoding="utf-8")
        doc2, _ = pb.build_paper(ws, template="comp_cumcm")
        check("main.md 优先于预编译 .tex（旧路径不被抢）",
              doc2.body_source == "main_md" and len(doc2.sections) == 1,
              f"{doc2.body_source} / {len(doc2.sections)}")


def test_engine_generated_tex_is_not_prebuilt() -> None:
    """引擎自己的产物（带生成标记）不算 agent 成品，可安全重建。"""
    print("\n[8] 带引擎标记的 `main.tex`：不当作成品，空正文被如实暴露")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "paper").mkdir(parents=True)
        (ws / "paper" / "main.tex").write_text(
            "% modemon:generated-latex-export\n"
            "\\documentclass[12pt,a4paper]{ctexart}\n\\begin{document}\n"
            "\\section*{结果数据表}\n\\end{document}\n", encoding="utf-8")

        check("**detect_prebuilt_tex 判定为 None**",
              pb.detect_prebuilt_tex(ws) is None,
              str(pb.detect_prebuilt_tex(ws)))
        doc, notes = pb.build_paper(ws, template="comp_cumcm")
        check("body_source 为 none", doc.body_source == "none", doc.body_source)
        check("**notes 明确「未找到正文」**",
              any("未找到正文" in n for n in notes), str(notes))
        check("**空正文不被伪装成有正文（下游据此降级）**",
              doc.body_text == "" and len(doc.sections) == 0,
              repr(doc.body_text[:40]))

    # 半成品：只有标题与表格桩、没有 documentclass → 也不算成品
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "paper").mkdir(parents=True)
        (ws / "paper" / "main.tex").write_text(
            "\\section*{结果数据表}\n\\captionof{table}{求解结果}\n", encoding="utf-8")
        check("缺 documentclass 的桩文件不算成品",
              pb.detect_prebuilt_tex(ws) is None)
        _, notes2 = pb.build_paper(ws, template="comp_cumcm")
        check("**并给出可诊断的原因**（不是静默的空正文）",
              any("不是自洽可编译" in n for n in notes2), str(notes2))


def test_step_prompt_declares_convention() -> None:
    """`comp-paper-zh` / `comp-paper-en` 的提示必须写明约定（验收点）。"""
    print("\n[9] 步骤提示：明确要求写 `paper/sections/`")
    def mk(skill: str) -> "sr.StepRunRequest":
        return sr.StepRunRequest(workflow_id="w", skill_name=skill,
                                 workspace=Path("."), language="zh")

    zh = sr.build_step_prompt(mk("comp-paper-zh"))
    en = sr.build_step_prompt(mk("comp-paper-en"))
    code = sr.build_step_prompt(mk("comp-code"))
    analysis = sr.build_step_prompt(mk("comp-prob-analysis"))

    check("**zh 提示要求写入 `paper/sections/`**", "paper/sections/" in zh)
    check("**zh 提示说明由引擎装配**", "引擎装配" in zh, zh[:200])
    check("提示给出具体文件示例", "paper/sections/01_问题重述.md" in zh)
    check("**en 提示同样写入约定**", "paper/sections/" in en)
    check("提示写明直出 .tex 时的兜底路径（只编译不重建）",
          "只编译不重建" in zh and "paper/main.tex" in zh)
    check("提示仍保留「必须产出」区块（不覆盖步骤契约）", "## 必须产出" in zh, zh[:120])
    check("**非论文步骤不带该约定**（不越界塑形）",
          "paper/sections/" not in code and "paper/sections/" not in analysis,
          code[:120])
    check("论文步骤提示比分析步骤更长（差异化塑形）", len(zh) > len(analysis),
          "%d vs %d" % (len(zh), len(analysis)))
    check("`paper-writing` 族技能名已登记",
          "comp-paper-zh" in sr.PAPER_WRITING_SKILLS)


def test_end_to_end_contract() -> None:
    """端到端：真实坏样本工作区按约定改写后，引擎能读到正文与干净的表。"""
    print("\n[10] 端到端：约定生效后的装配结果")
    with tempfile.TemporaryDirectory() as td:
        ws = real_workspace(Path(td))
        (ws / "paper" / "sections").mkdir(parents=True)
        (ws / "paper" / "sections" / "01_问题重述.md").write_text(
            "## 问题重述\n\n" + "某物流公司有 3 个配送中心。\n" * 40, encoding="utf-8")

        doc, notes = pb.build_paper(ws, template="comp_cumcm")
        check("正文来源为约定目录", doc.body_source == "sections", str(notes))
        check("正文非空（不会再出现 body_chars=0）", len(doc.body_text) > 100,
              str(len(doc.body_text)))
        check("结果表无重复标签",
              all(pb.table_label_duplicates(t) == [] for t in doc.tables),
              str([pb.table_label_duplicates(t) for t in doc.tables]))
        check("记录表已本地化（无 `name` / `x11`）",
              all("name" not in t.headers for t in doc.tables)
              and not RAW_INDEX_RE.search(
                  " ".join(c for t in doc.tables for row in t.rows for c in row)),
              str([t.headers for t in doc.tables]))

        written = pb.write_table_files(ws, doc.tables)
        md = "\n".join(p.read_text(encoding="utf-8") for p in written)
        check("落盘的 TABLE_*.md 也不含原始下标键",
              not RAW_INDEX_RE.search(md), md[:120])
        rows_total_cost = re.findall(r"^\| (.*?总成本) \|", md, re.M)
        check("**落盘表里「总成本」行两两不同**",
              len(rows_total_cost) >= 4
              and len(rows_total_cost) == len(set(rows_total_cost)),
              str(rows_total_cost))
        check("Markdown 表头结构正确", "| 指标 | 数值 |" in md, md[:120])


def main() -> int:
    print("=" * 74)
    print("modemon 论文格式约定 / 标签唯一性 / 列名本地化回归测试")
    print("=" * 74)
    test_real_result_table_unique_labels()
    test_label_for_group_semantics()
    test_unique_labels_safety_net()
    test_record_table_localization()
    test_value_label_units()
    test_paper_format_sections_first()
    test_paper_format_prebuilt_tex()
    test_engine_generated_tex_is_not_prebuilt()
    test_step_prompt_declares_convention()
    test_end_to_end_contract()
    print("\n" + "=" * 74)
    print("PASS %d / FAIL %d" % (PASS, FAIL))
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print("  -", f)
    print("=" * 74)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
