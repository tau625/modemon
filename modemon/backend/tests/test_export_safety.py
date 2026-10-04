"""导出安全回归测试（P0 数据丢失防护 + 排版打磨）。

依据：`reports/26-project-review-gaps.md` §1/§2 与 `reports/28-gap-closure-plan.md`
§0.1 / §0.2 / §4。这些缺陷都是「跑一次真实导出 / 看一眼渲染结果」才发现的，
单元测试当时全绿——所以在这里把它们固化成**可执行断言**：

  1. 预置 agent 版 `paper/main.tex` → 导出 → 原文件仍在、新文件另名（P0）
  2. 引擎自己的产物仍可覆盖（幂等，不留 `.agent` 垃圾文件）
  3. 已归档的 agent 版不会被二次导出冲掉（编号递增）
  4. 空正文导出 → `ok is False` + 明确 error，且**不产出桩 PDF**（P0）
  5. agent 直出成品 `paper/main.tex` → 原文一字不丢（只编译不重建，P0）
  6. preamble 里 `\\usepackage{caption}` 恰好 1 次（曾重复引入）
  7. `\\captionof` 位于 `center` 环境内（曾裸放正文触发宏包警告）
  8. 表题仍在表格上方、图题仍在图片下方（包装不得改变中文论文惯例）
  9. 表题 / 图题的字重设置一致（视觉自检报过「字重不一致」）
 10. 参考文献编号渲染为 `[1][2][3]`（而非裸小数字 / 上标）
"""

from __future__ import annotations

import re
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

#: agent 直写的论文里的一句**唯一标记**——用来证明它（没）被导出覆盖。
AGENT_MARK = "AGENT-OWNED-PAPER-DO-NOT-CLOBBER"

AGENT_TEX = (
    "\\documentclass{ctexart}\n"
    "\\begin{document}\n"
    "\\section{问题重述}\n"
    + (f"{AGENT_MARK} 这是 agent 在 comp-paper-zh 步骤里直写的完整论文正文。\n" * 20)
    + "\\end{document}\n"
)


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  %s" % name)
    else:
        FAIL += 1
        FAILURES.append(name)
        print("  FAIL  %s  %s" % (name, detail[:160]))


def make_ws(root: Path, *, with_sections: bool = True,
            with_agent_tex: bool = False) -> Path:
    """造一个最小工作区。

    `with_sections=True` 给出引擎认得的正文（`paper/sections/*.md`），
    此时 `body_chars > 0`，导出会正常推进到落盘。
    """
    ws = Path(root)
    (ws / "paper").mkdir(parents=True, exist_ok=True)
    if with_sections:
        sec = ws / "paper" / "sections"
        sec.mkdir(parents=True, exist_ok=True)
        (sec / "01-restate.md").write_text(
            "## 问题重述\n\n本文研究 3×4 运输问题，建立线性规划模型并给出调运方案。\n\n"
            "## 模型建立\n\n目标为总运输成本最小，约束为供需平衡。\n",
            encoding="utf-8")
    if with_agent_tex:
        (ws / "paper" / "main.tex").write_text(AGENT_TEX, encoding="utf-8")
    return ws


def inside_center(tex: str, needle: str) -> bool:
    """`needle` 是否落在某个 `center` 环境内。

    按出现顺序把 `\\begin{center}` 与**紧随其后**的 `\\end{center}` 配成区间，
    再判断 needle 的位置是否落在任一区间内。不依赖具体排版细节。
    题目要求的正是这一条：`\\captionof` 必须在环境内。
    """
    spans: list[tuple[int, int]] = []
    i = 0
    while True:
        b = tex.find(r"\begin{center}", i)
        if b < 0:
            break
        e = tex.find(r"\end{center}", b)
        if e < 0:
            break
        spans.append((b, e))
        i = e + 1
    pos = tex.find(needle)
    return pos >= 0 and any(b < pos < e for b, e in spans)


def make_doc() -> pb.PaperDoc:
    return pb.PaperDoc(
        title="运输成本优化模型",
        abstract="本文建立线性规划模型求解运输问题。",
        keywords=["运输问题", "线性规划"],
        sections=[pb.Section(level=1, title="问题重述", body="正文内容，见表。")],
        tables=[pb.TableSpec(name="results", caption="求解结果",
                             headers=["指标", "数值"],
                             rows=[["目标值", "1234"], ["迭代次数", "7"]])],
        figures=[pb.FigureRef(path="figures/fig_a.png", latex_name="a",
                              kind="data", caption="求解流程示意")],
        references=["张三. 运输问题研究[J]. 运筹学学报, 2024.",
                    "李四. 线性规划[M]. 高等教育出版社, 2023."],
    )


# ---------------------------------------------------------------------------
# 1. P0：导出不得覆盖 agent 产物
# ---------------------------------------------------------------------------


def test_agent_artifact_protected() -> None:
    print("\n[1] P0：导出不覆盖 agent 直写的 paper/main.tex")
    with tempfile.TemporaryDirectory() as td:
        ws = make_ws(td, with_sections=True, with_agent_tex=True)
        res = lx.export_latex(ws, compile_pdf=False)

        kept = ws / "paper" / "main.agent.tex"
        fresh = ws / "paper" / "main.tex"
        fresh_text = fresh.read_text(encoding="utf-8") if fresh.is_file() else ""

        check("导出正常完成（正文非空）", res.ok, str(res.as_dict()))
        check("**agent 版被改名保留，内容逐字未变**",
              kept.is_file() and kept.read_text(encoding="utf-8") == AGENT_TEX)
        check("新文件另名落盘 paper/main.tex", fresh.is_file())
        check("**agent 正文没有被写进 main.tex（未覆盖）**",
              AGENT_MARK not in fresh_text, fresh_text[:120])
        check("main.tex 是引擎产物（首行有生成标记）",
              lx.is_engine_generated(fresh_text),
              fresh_text.splitlines()[0] if fresh_text else "(空)")
        check("返回 notes 里说明了改名",
              any(("改名" in n and "main.agent.tex" in n) for n in (res.notes or [])),
              str(res.notes))


def test_engine_output_can_be_overwritten() -> None:
    print("\n[2] 引擎自己的产物可以被覆盖（幂等，不留垃圾文件）")
    with tempfile.TemporaryDirectory() as td:
        ws = make_ws(td, with_sections=True, with_agent_tex=False)
        r1 = lx.export_latex(ws, compile_pdf=False)
        r2 = lx.export_latex(ws, compile_pdf=False)

        check("首次导出成功", r1.ok, str(r1.as_dict()))
        check("二次导出成功", r2.ok, str(r2.as_dict()))
        check("**引擎产物不产生 .agent 归档**",
              not (ws / "paper" / "main.agent.tex").exists())
        check("二次导出未报「改名」",
              not any("改名" in n for n in (r2.notes or [])), str(r2.notes))


def test_archived_copy_not_clobbered() -> None:
    print("\n[3] 已归档的 agent 版不会被二次导出冲掉（编号递增）")
    with tempfile.TemporaryDirectory() as td:
        ws = make_ws(td, with_sections=True, with_agent_tex=True)
        (ws / "paper" / "main.agent.tex").write_text(
            "OLDER-ARCHIVED-AGENT-TEX", encoding="utf-8")

        res = lx.export_latex(ws, compile_pdf=False)

        arch = ws / "paper" / "main.agent.tex"
        arch2 = ws / "paper" / "main.agent.2.tex"
        check("导出成功", res.ok, str(res.as_dict()))
        check("**上一份归档逐字未动**",
              arch.read_text(encoding="utf-8") == "OLDER-ARCHIVED-AGENT-TEX")
        check("新的 agent 版另起编号 main.agent.2.tex",
              arch2.is_file() and arch2.read_text(encoding="utf-8") == AGENT_TEX)


# ---------------------------------------------------------------------------
# 2. P0：空正文导出不得报成功
# ---------------------------------------------------------------------------


def test_empty_body_is_not_success() -> None:
    print("\n[4] P0：空正文导出 → ok=False + 明确 error，且不产出桩 PDF")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "paper").mkdir(parents=True, exist_ok=True)
        # 即便调用方要求编译，也不该走到编译——空正文没有可编译的意义
        res = lx.export_latex(ws, compile_pdf=True)

        check("**ok is False**", res.ok is False, str(res.as_dict()))
        check("给出明确 error（含 body_chars=0）",
              bool(res.error) and "body_chars=0" in res.error, res.error)
        check("budget.body_chars == 0",
              bool(res.budget) and res.budget.get("body_chars") == 0,
              str(res.budget))
        check("**不产出桩 PDF**", res.pdf is None and res.pages is None,
              f"pdf={res.pdf} pages={res.pages}")
        check("notes 说明未编译 PDF",
              any("未编译" in n for n in (res.notes or [])), str(res.notes))
        check("as_dict 暴露 error 字段", res.as_dict().get("error") == res.error)


def test_prebuilt_agent_tex_is_not_rebuilt() -> None:
    print("\n[5] agent 直出成品 `paper/main.tex` → 只编译不重建（P0）")
    with tempfile.TemporaryDirectory() as td:
        ws = make_ws(td, with_sections=False, with_agent_tex=True)
        doc, _notes = pb.build_paper(ws)
        res = lx.export_latex(ws, compile_pdf=False)

        # ★ 对两种实现都必须成立的不变式：agent 的原始字节一个都不能少。
        survivors = [p for p in (ws / "paper").glob("main*.tex")
                     if p.read_text(encoding="utf-8") == AGENT_TEX]
        check("**agent 成品原文至少完整保留一份（P0：不得丢失）**",
              len(survivors) >= 1, str([p.name for p in survivors]))
        check("res.tex 指向 paper/main.tex",
              str(res.tex or "").replace("\\", "/").endswith("paper/main.tex"),
              str(res.tex))

        if doc.is_prebuilt:
            arch = ws / "paper" / "main.agent.tex"
            check("成品路径：不再误报「空正文」", res.ok is True and not res.error,
                  str(res.as_dict()))
            check("**成品路径：未重建、未改名、未写入**",
                  (ws / "paper" / "main.tex").read_text(encoding="utf-8") == AGENT_TEX
                  and not arch.exists())
            check("成品路径：notes 说明「只编译不重建」",
                  any("只编译不重建" in n for n in (res.notes or [])), str(res.notes))
            check("成品路径：不把成品当成引擎产物",
                  not lx.is_engine_generated(
                      (ws / "paper" / "main.tex").read_text(encoding="utf-8")))
        else:
            check("无成品检测时：空正文必须报失败",
                  res.ok is False and "body_chars=0" in res.error, str(res.as_dict()))


# ---------------------------------------------------------------------------
# 3. 排版打磨
# ---------------------------------------------------------------------------


def test_preamble_caption_package_once() -> None:
    print("\n[6] `\\usepackage{caption}` 在 preamble 中恰好 1 次（曾重复引入）")
    prof = ty.resolve_profile("comp_cumcm")
    pre = lx.build_preamble(prof)
    doc_tex = lx.build_document(make_doc(), prof, figure_base="../")

    n_pre = pre.count(r"\usepackage{caption}")
    n_doc = doc_tex.count(r"\usepackage{caption}")
    check("**preamble 中只出现 1 次**", n_pre == 1, f"count={n_pre}")
    check("整份 .tex 中也只出现 1 次", n_doc == 1, f"count={n_doc}")
    check("`\\captionsetup` 位于 caption 宏包之后",
          pre.index(r"\usepackage{caption}") < pre.index(r"\captionsetup"),
          pre[-400:])


def test_caption_of_inside_environment() -> None:
    print("\n[7] `\\captionof` 必须位于环境内（曾裸放正文触发宏包警告）")
    prof = ty.resolve_profile("comp_cumcm")
    tex = lx.build_document(make_doc(), prof, figure_base="../")

    check("**\\captionof{table} 在 center 环境内**",
          inside_center(tex, r"\captionof{table}"))
    check("**\\captionof{figure} 在 center 环境内**",
          inside_center(tex, r"\captionof{figure}"))
    check("表题仍在表格上方（中文论文惯例：表题在上）",
          tex.index(r"\captionof{table}") < tex.index(r"\begin{tabular}"),
          tex[:200])
    check("图题仍在图片下方（中文论文惯例：图题在下）",
          tex.index(r"\includegraphics") < tex.index(r"\captionof{figure}"),
          tex[-300:])

    # 块级 + 幂等：上游哪天在 paper_build 侧修好，这里不得重复包装
    t = make_doc().tables[0]
    wrapped = lx.caption_inside_environment(t.to_inline_latex())
    check("块级包装后题注在环境内", inside_center(wrapped, r"\captionof{table}"))
    check("**幂等：再包装一次结果不变**",
          lx.caption_inside_environment(wrapped) == wrapped, wrapped[:160])
    f = make_doc().figures[0]
    fwrapped = lx.caption_inside_environment(f.to_inline_latex(base_prefix="../"))
    check("图块包装后题注在环境内", inside_center(fwrapped, r"\captionof{figure}"))
    check("上游未改时包装确有作用（对照：裸块不在环境内）",
          not inside_center(f.to_inline_latex(base_prefix="../"),
                            r"\captionof{figure}"))


def test_caption_weights_unified() -> None:
    print("\n[8] 表题 / 图题字重设置一致（视觉自检：字重不一致）")
    pre = lx.build_preamble(ty.resolve_profile("comp_cumcm"))
    m_t = re.search(r"\\captionsetup\[table\]\{([^}]*)\}", pre)
    m_f = re.search(r"\\captionsetup\[figure\]\{([^}]*)\}", pre)

    check("存在 \\captionsetup[table]", m_t is not None, pre[-400:])
    check("存在 \\captionsetup[figure]", m_f is not None, pre[-400:])
    check("**两者选项完全一致（字重统一）**",
          bool(m_t and m_f) and m_t.group(1) == m_f.group(1),
          f"{m_t.group(1) if m_t else None} vs {m_f.group(1) if m_f else None}")
    check("统一设置了字号与标签间距",
          bool(m_t) and "font=" in m_t.group(1) and "labelsep=" in m_t.group(1),
          m_t.group(1) if m_t else "")


def test_reference_numbering_bracketed() -> None:
    print("\n[9] 参考文献编号为 `[1][2][3]`（而非裸小数字 / 上标）")
    prof = ty.resolve_profile("comp_cumcm")
    tex = lx.build_document(make_doc(), prof, figure_base="../")

    check("**编号渲染为 [1]**", r"\item[{[1]}]" in tex, tex[-500:])
    check("**编号渲染为 [2]**", r"\item[{[2]}]" in tex, tex[-500:])
    check("不再使用裸数字标签", r"\item[1]" not in tex and r"\item[2]" not in tex)
    check("不使用上标编号", r"\textsuperscript" not in tex)
    check("参考文献小节标题仍在", r"\section*{参考文献}" in tex)


def test_marker_semantics() -> None:
    print("\n[10] 生成标记的判定语义（首行、容忍 BOM）")
    pre = lx.build_preamble(ty.resolve_profile("comp_cumcm"))

    check("引擎 preamble 首行即生成标记",
          pre.splitlines()[0].strip() == lx.EXPORT_MARKER, pre.splitlines()[0])
    check("引擎产物被判为引擎生成", lx.is_engine_generated(pre))
    check("**无标记的 agent .tex 不被认作引擎产物**",
          not lx.is_engine_generated(AGENT_TEX))
    check("带 BOM 也能识别", lx.is_engine_generated("\ufeff" + lx.EXPORT_MARKER + "\nX"))
    check("空文本判为否", not lx.is_engine_generated(""))


def main() -> int:
    print("=" * 74)
    print("modemon 导出安全回归测试（P0 数据丢失防护 + 排版打磨）")
    print("=" * 74)
    test_agent_artifact_protected()
    test_engine_output_can_be_overwritten()
    test_archived_copy_not_clobbered()
    test_empty_body_is_not_success()
    test_prebuilt_agent_tex_is_not_rebuilt()
    test_preamble_caption_package_once()
    test_caption_of_inside_environment()
    test_caption_weights_unified()
    test_reference_numbering_bracketed()
    test_marker_semantics()
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
