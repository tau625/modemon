"""端到端回归测试：**只有真跑才能发现的缺陷**。

这些用例全部来自一次完整流水线运行（`reports/30-e2e-regression.md`）。
在写下它们之前，**1355 项测试全绿**，而这些缺陷一个都没被覆盖到。

⚠️ 本文件的用例价值在于：它们**不能靠 mock 或静态检查发现**——
必须真的渲染一张图、真的编译一份文档、真的去看渲染结果。
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from services import figure_pipeline as fp  # noqa: E402
from services import latex_export as lx  # noqa: E402
from services import paper_build as pb  # noqa: E402
from services import tex_runtime as tx  # noqa: E402
from services import typography as ty  # noqa: E402

PASS = 0
FAIL = 0
FAILURES: list[str] = []

_PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
_SVG = (b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" '
        b'width="100" height="50"></svg>')


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  %s" % name)
    else:
        FAIL += 1
        FAILURES.append(name)
        print("  FAIL  %s  %s" % (name, detail[:160]))


SPEC = {
    "title": "求解流程与系统架构",
    "canvas": {"width": 400, "height": 200},
    "style": {"font_family": "SimHei", "font_size": 13, "bg_color": "#FFFFFF",
              "palette": ["#4477AA"]},
    "nodes": [{"id": "a", "label": "甲", "x": 100, "y": 100, "width": 80,
               "height": 50, "shape": "rounded"},
              {"id": "b", "label": "乙", "x": 300, "y": 100, "width": 80,
               "height": 50, "shape": "rounded"}],
    "edges": [{"from": "a", "to": "b", "label": "连", "arrow": "right"}],
}


def test_svg_not_includable() -> None:
    """缺陷 4.1：SVG 被当插图 → 整份论文编译失败。

    真跑报错原文：
        ! LaTeX Error: Cannot determine size of graphic in
            ../figures/tikz_architecture.svg (no BoundingBox).
    根因：FigureSpec 同时产出 `X.png` 与 `X.svg`，**stem 相同**都被
    `FIGURE_RE` 命中，而 `\\includegraphics` 不支持 SVG。
    """
    print("\n[1] ★ 缺陷 4.1：SVG 不得进入 LaTeX 插图")
    check("LATEX_FIGURE_EXTS 不含 svg/drawio",
          ".svg" not in pb.LATEX_FIGURE_EXTS and ".drawio" not in pb.LATEX_FIGURE_EXTS,
          str(pb.LATEX_FIGURE_EXTS))
    check("LATEX_FIGURE_EXTS 含光栅格式",
          {".png", ".jpg", ".jpeg", ".pdf"} <= set(pb.LATEX_FIGURE_EXTS))

    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "figures").mkdir()
        # 同一张图的两个格式（真实场景：FigureSpec 渲染链同时产出）
        (ws / "figures" / "tikz_architecture.png").write_bytes(_PNG)
        (ws / "figures" / "tikz_architecture.svg").write_bytes(_SVG)
        (ws / "figures" / "fig_a.png").write_bytes(_PNG)
        (ws / "figures" / "only_svg.svg").write_bytes(_SVG)   # 纯 SVG，无孪生

        doc, _ = pb.build_paper(ws, template="comp_cumcm", title="t")
        paths = [f.path for f in doc.figures]
        check("**不含任何 .svg**", not any(p.endswith(".svg") for p in paths), str(paths))
        check("纯 SVG（无光栅孪生）被跳过",
              not any("only_svg" in p for p in paths), str(paths))
        check("**同 stem 只保留一张（优先 png）**",
              sum(1 for p in paths if "tikz_architecture" in p) == 1, str(paths))
        check("光栅图正常保留", any("fig_a.png" in p for p in paths), str(paths))

        # 端到端：生成的 .tex 里不得出现 .svg
        prof = ty.resolve_profile("comp_cumcm")
        src = lx.build_document(doc, prof, figure_base="../")
        check("**生成的 .tex 里无 .svg**", ".svg" not in src, src[-300:])


def test_duplicate_spec_dedup() -> None:
    """缺陷 4.2：同一份 spec 两个名字 → 重复 `\\label`。

    实测：`architecture.spec.json` 与 `tikz_architecture.spec.json`
    **逐字节相同**（SHA256 一致）。
    """
    print("\n[2] ★ 缺陷 4.2：内容相同的 FigureSpec 只渲染一次")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "figures").mkdir()
        payload = json.dumps(SPEC, ensure_ascii=False)
        (ws / "figures" / "architecture.spec.json").write_text(payload, encoding="utf-8")
        (ws / "figures" / "tikz_architecture.spec.json").write_text(payload, encoding="utf-8")
        # 再来一份**内容不同**的，必须保留
        other = dict(SPEC)
        other["title"] = "另一张图"
        (ws / "figures" / "flow.spec.json").write_text(
            json.dumps(other, ensure_ascii=False), encoding="utf-8")

        found = fp.find_specs(ws)
        names = sorted(p.name for p in found)
        check("**内容相同的去重为 1 份**", len([n for n in names if "architecture" in n]) == 1,
              str(names))
        check("内容不同的全部保留", "flow.spec.json" in names, str(names))
        check("保留名字最短的（通常是'正名'）",
              "architecture.spec.json" in names, str(names))

        rep = fp.build_figures(ws)
        labels = [f.get("caption") for f in rep.rendered]
        check("渲染结果无重复", len(rep.rendered) == len(set(labels)), str(labels))


def test_forward_reference_needs_two_passes() -> None:
    """缺陷 4.3：前向引用未解析 → PDF 里出现 `??`。

    `\\ref` 在文档前部、`\\label` 在后部时，**必须编译两遍**才能解析。
    实测规则：只跑一遍 → `LaTeX Warning: Reference '...' undefined` → 渲染成 `??`。
    """
    print("\n[3] ★ 缺陷 4.3：前向引用必须两遍编译才解析")
    rt = tx.resolve_tex_runtime()
    if not rt.ready:
        print("      (TeX 不可用，跳过)")
        check("TeX 不可用时如实报告", rt.state in ("fresh", "missing"), rt.state)
        return

    # 契约：默认必须是 2 遍
    import inspect
    sig = inspect.signature(tx.compile_tex)
    check("**compile_tex 默认 runs=2**", sig.parameters["runs"].default == 2,
          str(sig.parameters["runs"].default))

    # 行为：前向引用的文档，两遍编译后 PDF 里不应有 `??`
    src = (
        "\\documentclass{article}\n"
        "\\usepackage{xeCJK}\n"
        "\\begin{document}\n"
        "见第~\\ref{sec:late}~节。\n"          # ← 前向引用
        "\\newpage\n"
        "\\section{后置章节}\\label{sec:late}\n"
        "正文。\n"
        "\\end{document}\n"
    )
    import fitz

    def pdf_text(path: str) -> str:
        d = fitz.open(path)
        try:
            return "".join(d[i].get_text() for i in range(d.page_count))
        finally:
            d.close()          # ⚠️ 不关会占住文件，TemporaryDirectory 清理时 PermissionError

    # --- 两遍编译：前向引用应已解析 ---
    with tempfile.TemporaryDirectory() as td:
        tex = Path(td) / "fwd.tex"
        tex.write_text(src, encoding="utf-8")
        r2 = tx.compile_tex(tex, runtime=rt, runs=2)
        check("两遍编译成功", r2.ok, r2.error)
        if r2.pdf and Path(r2.pdf).is_file():
            t2 = pdf_text(r2.pdf)
            check("**两遍编译后 PDF 里无 `??`**", "??" not in t2,
                  t2[:120].replace("\n", " "))

    # --- 一遍编译：**必须用全新目录** ---
    #   ⚠️ 实测踩过：在同一目录先跑两遍再跑一遍，`.aux` 已被填好，
    #   单遍也会"解析成功"，对照用例就失效了。
    with tempfile.TemporaryDirectory() as td:
        tex = Path(td) / "fwd.tex"
        tex.write_text(src, encoding="utf-8")
        r1 = tx.compile_tex(tex, runtime=rt, runs=1)
        if r1.pdf and Path(r1.pdf).is_file():
            t1 = pdf_text(r1.pdf)
            check("对照：全新目录下一遍编译确实留下 `??`（证明用例有效）",
                  "??" in t1, t1[:120].replace("\n", " "))


def test_no_title_only_page() -> None:
    """缺陷 4.4：标题独占一页。

    实测：agent 把摘要写成**分节**（`00_摘要.md`）→ `doc.abstract` 为空
    → 无条件 `\\newpage` 让第 1 页只剩标题（版面校验报「近乎空白页」）。
    """
    print("\n[4] ★ 缺陷 4.4：无摘要时标题不得独占一页")
    prof = ty.resolve_profile("comp_cumcm")

    # 有摘要 → 摘要后断页（保持原行为）
    with tempfile.TemporaryDirectory() as td:
        doc = pb.PaperDoc(title="标题", abstract="摘要正文。", keywords=["关键词"],
                          sections=[pb.Section(level=1, title="第一章", body="正文。")])
        src = lx.build_document(doc, prof)
        check("有摘要时保留 `\\newpage`", r"\newpage" in src, src[:400])

    # 无摘要 → 不断页，让首个分节接在标题下
    with tempfile.TemporaryDirectory() as td:
        doc = pb.PaperDoc(title="标题", abstract="", keywords=[],
                          sections=[pb.Section(level=1, title="摘要", body="正文。")])
        src = lx.build_document(doc, prof)
        head = src.split(r"\begin{document}")[-1]
        check("**无摘要时标题后不断页**", r"\newpage" not in head.split("\\section")[0],
              head[:300])


def test_layout_verifier_catches_double_question() -> None:
    """缺陷 4.5：**校验器自己漏报** `??`。

    真跑时校验器报「无未解析交叉引用」，而 PDF 里明明有 `??`——
    因为它查的是 `???`（三个问号），而 LaTeX 的未解析占位是 **`??`（两个）**。

    ⚠️ 这条比单个缺陷更危险：**校验器的 bug 会让后续所有检查失真**。
    """
    print("\n[5] ★ 缺陷 4.5：版面校验器必须能抓 `??`")
    import re
    src = (BACKEND / "verify_layout.py").read_text(encoding="utf-8")
    check("匹配规则覆盖两个问号", r"\?\?" in src, "未见 \\?\\? 规则")
    check("不再只查三个问号",
          not re.search(r're\.findall\(r"\\\?\\\?\\\?"', src),
          "仍在只查 ???")
    check("失败时打印上下文（便于定位）", "snippet" in src or "上下文" in src)

    # 行为验证：拿一份含 `??` 的 PDF 喂给它
    rt = tx.resolve_tex_runtime()
    if not rt.ready:
        print("      (TeX 不可用，跳过行为验证)")
        return
    src_tex = (
        "\\documentclass{article}\n\\usepackage{xeCJK}\n"
        "\\begin{document}\n见~\\ref{sec:nope}~节。\\end{document}\n"
    )
    with tempfile.TemporaryDirectory() as td:
        tex = Path(td) / "bad.tex"
        tex.write_text(src_tex, encoding="utf-8")
        r = tx.compile_tex(tex, runtime=rt, runs=1)   # 一遍 → 前向引用必未解析
        if not (r.pdf and Path(r.pdf).is_file()):
            print("      (未产出 PDF，跳过)")
            return
        import importlib.util
        spec = importlib.util.spec_from_file_location("vl", BACKEND / "verify_layout.py")
        vl = importlib.util.module_from_spec(spec)          # type: ignore[arg-type]
        spec.loader.exec_module(vl)                         # type: ignore[union-attr]
        code = vl.check(Path(r.pdf))
        check("**校验器对 `??` 判失败**（返回非 0）", code != 0, "code=%s" % code)


def main() -> int:
    print("=" * 74)
    print("端到端回归测试（★ 全部来自一次真实流水线运行）")
    print("=" * 74)
    test_svg_not_includable()
    test_duplicate_spec_dedup()
    test_forward_reference_needs_two_passes()
    test_no_title_only_page()
    test_layout_verifier_catches_double_question()
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
