"""版面与图表装配回归测试。

针对"看渲染结果才发现"的缺陷，把它们转成可执行断言：

  1. 清单解析：**表格格式**的 FIGURE_MANIFEST 要能读出中文图注
  2. 表格规模：元数据不进论文表，行数有上限（否则一张表撑爆两页）
  3. 标签归一：`Z0` 要能查到中文标签（大小写不敏感）
  4. 非浮动排版：文末浮动体区块用 \\captionof，避免标题落单/空白页
  5. 版面校验器自身：图页不应被误判为"空白页"
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from services import latex_export as lx  # noqa: E402
from services import paper_build as pb  # noqa: E402
from services import typography as ty  # noqa: E402

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
        print("  FAIL  %s  %s" % (name, detail[:160]))


TABLE_MANIFEST = """# 图表清单（FIGURE MANIFEST）

## 流程与架构图

| 文件名 | 中文标题 | 数据来源 | 说明 |
|--------|----------|----------|------|
| `fig_transport_plan.png` | 情景1 最优调运方案 X*（吨） | `scenario1_basic.X` | 热力图 |
| `tikz_solution_pipeline.tex` | 求解流程与系统架构 | 结构示意 | 三层架构 |

## 传统列表格式

- fig_legacy
"""


def test_manifest_table_format() -> None:
    print("\n[1] FIGURE_MANIFEST 表格格式解析（中文图注不得丢失）")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "figures").mkdir()
        (ws / "figures" / "FIGURE_MANIFEST.md").write_text(TABLE_MANIFEST, encoding="utf-8")
        ents = pb.parse_figure_manifest(ws)
        by_name = {e.name: e for e in ents}

        check("表格行被识别", "fig_transport_plan" in by_name, str(list(by_name)))
        check("**中文图注被读出**",
              by_name.get("fig_transport_plan") and
              by_name["fig_transport_plan"].caption == "情景1 最优调运方案 X*（吨）",
              str(by_name.get("fig_transport_plan")))
        check("tikz 行也被识别", "tikz_solution_pipeline" in by_name)
        check("列表式仍然兼容", "fig_legacy" in by_name, str(list(by_name)))
        check("表头行不产生条目", all(not e.name.startswith("文件名") for e in ents))


def test_result_table_content() -> None:
    print("\n[2] 结果表内容（元数据不进论文表，行数有上限）")
    data = {
        "meta": {"title": "内部标题", "generated_by": "code/main.py",
                 "python": "3.11.9", "platform": "win"},
        "data": {"supply": [1, 2, 3], "demand": [1, 2]},
        "scenario1_basic": {"Z0": 775.0, "simplex_iterations": 3},
        "scenario2": {"shortage_gap_tons": 7.5, "penalty_p": 100.0},
        **{f"noise_field_{i}": float(i) for i in range(40)},
    }
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "figures"
        p.mkdir()
        (p / "all_results.json").write_text(
            __import__("json").dumps(data, ensure_ascii=False), encoding="utf-8")
        src = pb.load_results(Path(td))
        t = pb.build_result_table(src)

        check("结果表非空", t is not None)
        if not t:
            return
        body = "\n".join(r[0] + "=" + r[1] for r in t.rows)
        check("**meta 元数据被剔除**", "内部标题" not in body and "code/main.py" not in body,
              body[:120])
        check("**data 输入数据不进结果表**", "supply" not in body, body[:120])
        check("**行数有上限**", len(t.rows) <= pb.MAX_TABLE_ROWS + 1,
              "rows=%d" % len(t.rows))
        check("**关键结果字段保留**", "775" in body and "7.5" in body, body[:200])

        # 标签归一：Z0 应显示为中文
        labels = [r[0] for r in t.rows]
        check("**Z0 显示为中文标签（大小写不敏感）**",
              any("最优总成本" in l for l in labels), str(labels[:8]))
        check("没有原始 key 直接出现在标签里",
              not any("." in l and l.startswith("scenario") for l in labels),
              str(labels[:8]))


def test_non_float_rendering() -> None:
    print("\n[3] 文末浮动体区块用非浮动排版")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "figures").mkdir()
        (ws / "figures" / "all_results.json").write_text(
            '{"scenario1": {"Z0": 775, "iterations": 2}}', encoding="utf-8")
        (ws / "figures" / "t1.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)

        src = pb.load_results(ws)
        t = pb.build_result_table(src)
        fig = pb.FigureRef(path="figures/t1.png", latex_name="t1", kind="data",
                           caption="测试图")
        tab_inline = t.to_inline_latex()
        fig_inline = fig.to_inline_latex(base_prefix="../")

        check("**表用 captionof 而非浮动环境**",
              "\\captionof{table}" in tab_inline and "\\begin{table}" not in tab_inline,
              tab_inline[:120])
        check("**图用 captionof 而非浮动环境**",
              "\\captionof{figure}" in fig_inline and "\\begin{figure}" not in fig_inline,
              fig_inline[:120])
        check("图路径仍带前缀", "{../figures/t1.png}" in fig_inline, fig_inline)
        check("保留了浮动变体（供正文内插图使用）",
              "\\begin{figure}" in fig.to_latex(base_prefix="../"))

        # 端到端：导出的正文不应出现落单标题
        doc = pb.PaperDoc(title="t", abstract="a", keywords=["k"],
                          sections=[], figures=[fig], tables=[t])
        src_tex = lx.build_document(doc, ty.resolve_profile("comp_cumcm"),
                                    figure_base="../")
        check("正文包含 captionof", "\\captionof{" in src_tex)
        check("标题与表在同一大块（表紧随标题）",
              src_tex.index("\\section*{结果数据表}") <
              src_tex.index("\\captionof{table}"), src_tex[-400:])


def test_figure_height_bound() -> None:
    print("\n[4] 图的高度上限（防止顶穿正文区）")
    fig = pb.FigureRef(path="figures/a.png", latex_name="a", kind="data",
                       caption="c")
    out = fig.to_latex(base_prefix="../")
    check("**includegraphics 有高度上限**", "height=" in out and "keepaspectratio" in out,
          out[:160])
    check("默认使用 [htbp] 正常浮动", "\\begin{figure}[htbp]" in out, out[:80])


def test_prompt_shaping_per_step() -> None:
    print("\n[5] 提示按步骤差异化塑形（不依赖脆弱措辞）")
    from services import step_runner as sr

    def mk(skill: str) -> "sr.StepRunRequest":
        return sr.StepRunRequest(workflow_id="w", skill_name=skill,
                                 workspace=Path("."), language="zh")

    base = sr.build_step_prompt(mk("comp-prob-analysis"))
    code_p = sr.build_step_prompt(mk("comp-code"))
    fig_p = sr.build_step_prompt(mk("paper-figure"))
    fig2_p = sr.build_step_prompt(mk("paper-figure-drawio"))

    # 断言"差异"而不是某个具体措辞——措辞会改，塑形行为不该改。
    check("**代码步骤被额外塑形**（要求分段交付）", code_p != base and len(code_p) > len(base),
          "code=%d base=%d" % (len(code_p), len(base)))
    check("**图表步骤被额外塑形**（限制润色轮次）", fig_p != base and len(fig_p) > len(base),
          "fig=%d base=%d" % (len(fig_p), len(base)))
    check("drawio 步骤同样被塑形", fig2_p != base and len(fig2_p) > len(base),
          "fig2=%d base=%d" % (len(fig2_p), len(base)))
    check("分析步骤不带图表约束", "图形" not in base and "润色" not in base,
          base[:120])
    check("分析步骤不带分段要求", "分小段" not in base, base[:120])
    check("代码步骤不带图表约束", "图形" not in code_p, code_p[:120])


def main() -> int:
    print("=" * 74)
    print("modemon 版面与图表装配回归测试")
    print("=" * 74)
    test_manifest_table_format()
    test_result_table_content()
    test_non_float_rendering()
    test_figure_height_bound()
    test_prompt_shaping_per_step()
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
