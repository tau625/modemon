"""冒烟 + 真值回归测试。

关键点：`test_matches_recovered_truth` 断言本项目重建的流水线
与**从 Modex 内省恢复的真值**逐字段一致。
如果未来有人改动步骤定义，这个测试会失败并指出差异。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import workflow_engine as we  # noqa: E402

# ---------------------------------------------------------------------------
# 从 Modex 内省恢复的真值（勿改动：这是对照基线）
# 来源：reports/16-workflow-engine-config.md / 15-workflow-engine-probe.md
# ---------------------------------------------------------------------------

TRUTH_ZH = [
    ("comp-prob-analysis", "赛题分析", ["PROBLEM_ANALYSIS.md"], "PROBLEM_ANALYSIS.md", True, "approve"),
    ("comp-modeling", "建模求解", ["MODELING_REPORT.md"], "MODELING_REPORT.md", True, "feedback"),
    ("comp-code", "编程实现", ["code/main.py", "RESULTS.md"], "RESULTS.md", True, "approve"),
    ("paper-figure", "图表生成", ["figures/latex_includes.tex"], "figures/", False, None),
    ("paper-figure-drawio", "流程与架构图绘制", ["figures/latex_includes.tex"], "figures/", False, None),
    ("comp-review", "逻辑对抗复核", ["COMP_REVIEW.md"], "COMP_REVIEW.md", False, None),
    ("comp-paper-zh", "竞赛论文撰写", ["paper/main.tex"], "paper/main.tex", True, "approve"),
    ("comp-compile-zh", "编译与合规检查", ["paper/main.pdf"], "paper/main.pdf", False, None),
]

TRUTH_EN = [
    ("comp-prob-analysis", "Problem Analysis", ["PROBLEM_ANALYSIS.md"], "PROBLEM_ANALYSIS.md", True, "approve"),
    ("comp-modeling", "Modeling & Solution", ["MODELING_REPORT.md"], "MODELING_REPORT.md", True, "feedback"),
    ("comp-code", "Programming", ["code/main.py", "RESULTS.md"], "RESULTS.md", True, "approve"),
    ("paper-figure", "Figure Generation", ["figures/latex_includes.tex"], "figures/", False, None),
    ("paper-figure-drawio", "Flow & Architecture Diagrams", ["figures/latex_includes.tex"], "figures/", False, None),
    ("comp-review", "Logic Adversarial Review", ["COMP_REVIEW.md"], "COMP_REVIEW.md", False, None),
    ("comp-paper-en", "Paper Writing (English)", ["paper/main.tex"], "paper/main.tex", True, "approve"),
    ("comp-compile-en", "Compile & Compliance Check", ["paper/main.pdf"], "paper/main.pdf", False, None),
]

TRUTH_MIN_SIZE = {
    "comp-prob-analysis": 1500, "comp-modeling": 2000, "comp-code": 1000,
    "paper-figure": 500, "paper-figure-drawio": 500, "comp-review": 40,
    "comp-paper-zh": 10000, "comp-paper-en": 10000,
    "comp-compile-zh": 30000, "comp-compile-en": 30000,
}

TRUTH_TIMEOUT = {
    "comp-prob-analysis": 5400, "comp-modeling": 5400, "comp-code": 5400,
    "paper-figure": 5400, "paper-figure-drawio": 5400, "comp-review": 5400,
    "comp-paper-zh": 2700, "comp-paper-en": 2700,
    "comp-compile-zh": 2700, "comp-compile-en": 2700,
}

TRUTH_PAGE = {
    "comp_cumcm": 30, "comp_huawei": 50, "comp_mcm": 25,
    "comp_apmcm": 25, "comp_mathorcup": 30,
    "comp_zh": None, "comp_en": None, "course_paper": None, "thesis_proposal": None,
}

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  %s" % name)
    else:
        FAIL += 1
        print("  FAIL  %s  %s" % (name, detail))


def as_rows(steps) -> list[tuple]:
    return [
        (s.skill_name, s.display_name, list(s.output_files),
         s.primary_output, s.has_checkpoint, s.checkpoint_type)
        for s in steps
    ]


def test_matches_recovered_truth() -> None:
    print("\n[1] 与恢复真值逐字段比对")
    zh, en = we.comp_zh_steps(), we.comp_en_steps()

    check("国赛步骤数 = 8", len(zh) == 8, "got %d" % len(zh))
    for i, (got, want) in enumerate(zip(as_rows(zh), TRUTH_ZH)):
        check("国赛 step%d = %s" % (i + 1, want[0]), got == tuple(want), "\n      got  %s\n      want %s" % (got, want))

    check("美赛步骤数 = 8", len(en) == 8, "got %d" % len(en))
    for i, (got, want) in enumerate(zip(as_rows(en), TRUTH_EN)):
        check("美赛 step%d = %s" % (i + 1, want[0]), got == tuple(want), "\n      got  %s\n      want %s" % (got, want))

    check("中英文前 6 步技能名一致",
          zh[:6] and en[:6] and [s.skill_name for s in zh[:6]] == [s.skill_name for s in en[:6]])
    check("中英文仅在第 7/8 步分叉",
          [s.skill_name for s in zh[6:]] == ["comp-paper-zh", "comp-compile-zh"]
          and [s.skill_name for s in en[6:]] == ["comp-paper-en", "comp-compile-en"])


def test_thresholds() -> None:
    print("\n[2] 阈值 / 超时 / 页码")
    for skill, want in TRUTH_MIN_SIZE.items():
        check("min_size(%s) = %d" % (skill, want), we.min_size_for(skill) == want,
              "got %s" % we.min_size_for(skill))
    for skill, want in TRUTH_TIMEOUT.items():
        check("timeout(%s) = %d" % (skill, want), we.inactivity_timeout(skill) == want,
              "got %s" % we.inactivity_timeout(skill))
    for tmpl, want in TRUTH_PAGE.items():
        got, mode = we.resolve_page_rule(tmpl)
        check("page(%s) = %s" % (tmpl, want), got == want and mode == "advisory_max",
              "got %s/%s" % (got, mode))
    check("默认 min_size = 100", we.min_size_for("nonexistent") == 100)
    check("comp-code 有二级文件约束",
          we.required_companions_for("comp-code") == ("code/main.py", "figures/all_results.json"))
    check("其余技能无二级文件约束",
          all(we.required_companions_for(s) == () for s in TRUTH_MIN_SIZE if s != "comp-code"))


def test_gates() -> None:
    print("\n[3] 质量门实际行为")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)

        # 空工作区：主产物缺失
        r = we.check_primary_output(ws, "comp-modeling")
        check("空工作区判定主产物缺失", (not r.ok) and "缺失" in r.reason, r.reason)

        # 产出但过小 -> 判不合格
        (ws / "MODELING_REPORT.md").write_text("x" * 100, encoding="utf-8")
        r = we.check_primary_output(ws, "comp-modeling")
        check("产物 100B < 阈值 2000B -> 不合格", (not r.ok) and "过小" in r.reason, r.reason)

        # 达到阈值 -> 通过
        (ws / "MODELING_REPORT.md").write_text("y" * 2500, encoding="utf-8")
        r = we.check_primary_output(ws, "comp-modeling")
        check("产物 2500B >= 阈值 -> 通过", r.ok, r.reason)

        # comp-code 二级文件缺失
        r = we.check_step_companions(ws, "comp-code")
        check("comp-code 缺二级文件 -> 不合格", (not r.ok) and len(r.missing) == 2, str(r.missing))

        # 补齐但其中一个是空占位
        (ws / "code").mkdir()
        (ws / "figures").mkdir()
        (ws / "code" / "main.py").write_text("print(1)\n" * 10, encoding="utf-8")
        (ws / "figures" / "all_results.json").write_text("{}", encoding="utf-8")  # 2B, 疑似占位
        r = we.check_step_companions(ws, "comp-code")
        check("空占位文件被识别", (not r.ok) and any("空文件占位" in m for m in r.missing), str(r.missing))

        # 补齐到 >50B
        (ws / "figures" / "all_results.json").write_text('{"a": 1, "b": 2}\n' * 5, encoding="utf-8")
        r = we.check_step_companions(ws, "comp-code")
        check("comp-code 二级文件齐全 -> 通过", r.ok, r.reason)

        # 目录型主产物 —— 用独立工作区，避免受上面的 comp-code 用例影响
        with tempfile.TemporaryDirectory() as td2:
            w2 = Path(td2)
            r = we.check_primary_output(w2, "paper-figure")
            check("figures/ 不存在 -> 不合格", not r.ok, r.reason)

            (w2 / "figures").mkdir()
            r = we.check_primary_output(w2, "paper-figure")
            check("空 figures/ 目录 -> 不合格", not r.ok, r.reason)

            # 放一个无关文件不能骗过检查（必须符合 fig_* / tikz_* 约定）
            (w2 / "figures" / "notes.txt").write_text("hello", encoding="utf-8")
            r = we.check_primary_output(w2, "paper-figure")
            check("figures/ 只有无关文件 -> 仍不合格", not r.ok, r.reason)

            # 符合约定的数据图 -> 通过
            (w2 / "figures" / "fig_result.png").write_bytes(b"\x89PNG" + b"0" * 64)
            r = we.check_primary_output(w2, "paper-figure")
            check("figures/ 有 fig_*.png -> 通过", r.ok, r.reason)

        with tempfile.TemporaryDirectory() as td3:
            w3 = Path(td3)
            (w3 / "figures").mkdir()
            (w3 / "figures" / "tikz_arch.drawio").write_text("<mxfile/>", encoding="utf-8")
            r = we.check_primary_output(w3, "paper-figure-drawio")
            check("tikz_*.drawio 也被认作架构图 -> 通过", r.ok, r.reason)


def test_body_pages() -> None:
    print("\n[4] 正文页数预算")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "paper").mkdir()
        # 中文：800 字/页
        (ws / "paper" / "main.md").write_text("中" * 8000 + "\n## 附录\n" + "中" * 99999, encoding="utf-8")
        pages, chars = we.check_paper_body_pages(ws, language="zh")
        check("中文 8000 字 -> 10 页", pages == 10 and chars == 8000, "got %s pages / %s chars" % (pages, chars))
        check("附录之后不计入正文", chars == 8000, "chars=%d" % chars)
        # 英文：2200 字/页
        pages, chars = we.check_paper_body_pages(ws, language="en")
        check("英文 8000 字 -> 3 页", pages == 3, "got %s" % pages)
        # LaTeX 模式优先读 paper/sections/*.tex
        (ws / "paper" / "sections").mkdir()
        (ws / "paper" / "sections" / "01.tex").write_text("x" * 4400, encoding="utf-8")
        pages, chars = we.check_paper_body_pages(ws, language="en")
        check("LaTeX 模式读 sections/*.tex", chars == 4400 and pages == 2,
              "got %s pages / %s chars" % (pages, chars))


def test_template_resolution() -> None:
    print("\n[5] 模板解析与 docx 模式")
    t = we.resolve_template("comp_cumcm")
    check("comp_cumcm -> 中文流水线 8 步", len(t.sub_steps) == 8 and t.sub_steps[6].skill_name == "comp-paper-zh")
    t2 = we.resolve_template("comp_mcm")
    check("comp_mcm -> 英文流水线", t2.sub_steps[6].skill_name == "comp-paper-en")
    t3 = we.resolve_template("comp_huawei")
    check("comp_huawei -> 专属论文技能", t3.sub_steps[6].skill_name == "comp-paper-huawei",
          t3.sub_steps[6].skill_name)
    t4 = we.resolve_template("comp_cumcm", docx_mode=True)
    check("docx 模式把 paper/main.tex 改为 paper/main.md",
          t4.sub_steps[6].primary_output == "paper/main.md", str(t4.sub_steps[6].primary_output))
    check("同一模板两次解析结果一致（sub_steps 为唯一真相源）",
          t.skill_names == we.resolve_template("comp_cumcm").skill_names)


def test_failure_classification() -> None:
    print("\n[6] 失败三态分类")
    check("检查器不可用 -> unavailable",
          we.classify_failure(we.StepCheckPendingError("cli missing", unavailable=True)) == "unavailable")
    check("修复未结束 -> interrupted",
          we.classify_failure(we.StepCheckPendingError("still running")) == "interrupted")
    check("真实缺陷 -> defect", we.classify_failure(ValueError("bad output")) == "defect")


def main() -> int:
    print("=" * 72)
    print("modemon workflow_engine 冒烟 + 真值回归")
    print("=" * 72)
    test_matches_recovered_truth()
    test_thresholds()
    test_gates()
    test_body_pages()
    test_template_resolution()
    test_failure_classification()
    print("\n" + "=" * 72)
    print("PASS %d / FAIL %d" % (PASS, FAIL))
    print("=" * 72)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
