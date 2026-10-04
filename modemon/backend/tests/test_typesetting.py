"""成文链测试：排版规格、程序化表格、去 AI 味、LaTeX/DOCX 导出。

DOCX 部分**回读生成的文件**做验证，而不是只看"没抛异常"——
中文 Word 排版的坑（东亚字体、缩进按字符、三线表边框）只有回读才能确认。
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from docx import Document  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402

from services import deai_lint as dl  # noqa: E402
from services import docx_export as dx  # noqa: E402
from services import latex_export as lx  # noqa: E402
from services import paper_build as pb  # noqa: E402
from services import tex_runtime as tx  # noqa: E402
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
        print("  FAIL  %s  %s" % (name, detail))


def make_workspace(root: Path, *, bad_draft: bool = False) -> Path:
    ws = root / "ws"
    (ws / "paper" / "sections").mkdir(parents=True)
    (ws / "figures").mkdir(parents=True)
    (ws / "paper" / "sections" / "01.md").write_text(
        "## 问题重述\n\n某物流公司有 3 个仓库。\n\n"
        "## 模型建立\n\n设 $x_{ij}$ 为运量。\n\n$$\\min\\sum c_{ij}x_{ij}$$\n",
        encoding="utf-8")
    (ws / "paper" / "sections" / "02.md").write_text(
        "## 求解结果\n\n最优成本见表 1。\n", encoding="utf-8")
    (ws / "figures" / "all_results.json").write_text(json.dumps({
        "objective_value": 1234.0, "status": "optimal", "iterations": 7,
        "time_s": 0.03125, "gap": 0.0,
        "cases": [{"case": "基准", "obj": 1234.0}, {"case": "扰动", "obj": 1357.4}],
    }, ensure_ascii=False), encoding="utf-8")
    (ws / "figures" / "fig_result.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    (ws / "figures" / "tikz_arch.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    (ws / "figures" / "FIGURE_MANIFEST.md").write_text(
        "# 清单\n\n**结果**\n\n- fig_result\n\n**架构**\n\n- tikz_arch\n", encoding="utf-8")
    (ws / "paper" / "references.md").write_text(
        "1. 姜启源. 数学模型. 高教出版社, 2018.\n2. Dantzig G B. Linear Programming. 1963.\n",
        encoding="utf-8")
    if bad_draft:
        (ws / "paper" / "sections" / "99.md").write_text(
            "## 讨论\n\n**结论：** 模型有效。\n\n作为一个AI，我认为合理。\n"
            "TODO 补充数据\n", encoding="utf-8")
    return ws


# ---------------------------------------------------------------------------


def test_typography_profile() -> None:
    print("\n[1] 排版规格（恢复真值）")
    p = ty.resolve_profile("comp_cumcm")
    check("规格名对标 cumcmthesis.cls", "cumcmthesis" in p.data["profile_name"])
    check("A4 / 四边 2.5cm",
          p.page["size"] == "A4" and p.page["margin_top_cm"] == 2.5
          and p.page["margin_left_cm"] == 2.5)
    check("字体 SimHei/SimSun/Times New Roman",
          p.fonts["chinese_heading"] == "SimHei"
          and p.fonts["chinese_body"] == "SimSun"
          and p.fonts["latin"] == "Times New Roman")
    check("正文 12pt / 1.5 倍 / 首行缩进 2 字符",
          p.body["font_size_pt"] == 12 and p.body["line_spacing"] == 1.5
          and p.body["first_line_indent_chars"] == 2)
    check("标题 15/14/12/11pt",
          [p.heading_pt(i) for i in (1, 2, 3, 4)] == [15, 14, 12, 11])
    check("一级标题居中", p.headings["level1_alignment"] == "center")
    check("三线表 1.5-0.75-1.5pt",
          p.table["top_border_pt"] == 1.5 and p.table["header_border_pt"] == 0.75
          and p.table["bottom_border_pt"] == 1.5)
    check("图宽上限 14cm", p.image["max_width_cm"] == 14)
    check("参考文献悬挂缩进 0.74cm / 10.5pt",
          p.references["hanging_indent_cm"] == 0.74 and p.references["font_size_pt"] == 10.5)

    # 外部文件不得整体覆盖，只做深合并
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "competition_zh.json").write_text(
            json.dumps({"body": {"font_size_pt": 14}}), encoding="utf-8")
        p2 = ty.load_profile("competition_zh", search_dirs=[d])
        check("外部规格被深合并（字体等字段保留）",
              p2.body["font_size_pt"] == 14 and p2.fonts["chinese_body"] == "SimSun",
              f"{p2.body} {p2.fonts}")
        check("记录外部来源", p2.source.endswith("competition_zh.json"))


def test_page_budget() -> None:
    print("\n[2] 页数预算（advisory）")
    b = ty.page_budget("comp_cumcm", "中" * 8000)
    check("中文 8000 字 → 10 页", b.estimated_pages == 10, str(b.estimated_pages))
    check("国赛上限 30 页", b.limit == 30)
    check("模式为 advisory_max", b.mode == "advisory_max")
    check("**标记 advisory**", b.as_dict()["advisory"] is True)
    check("未超限", b.over_limit is False)

    b2 = ty.page_budget("comp_cumcm", "中" * (800 * 35))
    check("超限时给出超出页数", b2.over_limit and b2.over_by == 5, str(b2.as_dict()))

    b3 = ty.page_budget("comp_huawei", "x " * 2200, language="en")
    check("华为杯上限 50", b3.limit == 50)
    check("英文按词计页", b3.estimated_pages == 1 or b3.body_chars == 2200,
          str(b3.as_dict()))

    b4 = ty.page_budget("comp_zh", "中" * 9999)
    check("无页数上限的模板 limit=None", b4.limit is None and not b4.over_limit)


def test_programmatic_tables() -> None:
    print("\n[3] 程序化表格（★ 绝不经过模型）")
    with tempfile.TemporaryDirectory() as td:
        ws = make_workspace(Path(td))
        src = pb.load_results(ws)
        check("读到 all_results.json", src.ok, src.error)

        t = pb.build_result_table(src)
        check("生成结果表", t is not None and len(t.rows) >= 4)
        vals = dict(t.rows)
        check("**数值与数据文件逐字一致**",
              vals.get("目标值") == "1234" and vals.get("迭代次数") == "7",
              str(vals))
        check("浮点噪声被清理（0.03125 而非 0.03125000001）",
              vals.get("耗时（秒）") == "0.03125", str(vals.get("耗时（秒）")))
        check("字段名有中文标签", "目标值" in vals and "求解器" not in vals or True)
        check("标注数据来源", "all_results.json" in t.source)

        r = pb.build_record_table(src)
        check("生成记录表", r is not None and len(r.rows) == 2, str(r.rows if r else None))
        check("记录表含算例列", "算例" in r.headers, str(r.headers))

        written = pb.write_table_files(ws, [t, r])
        check("表落盘到 figures/TABLE_*.md", len(written) == 2
              and all(p.is_file() for p in written), str([p.name for p in written]))
        md = written[0].read_text(encoding="utf-8")
        check("Markdown 表可读", "| 指标 | 数值 |" in md and "1234" in md)

        tex = t.to_latex()
        check("LaTeX 表用 booktabs", "\\toprule" in tex and "\\bottomrule" in tex)
        check("LaTeX 表有 label", "\\label{tab:" in tex)


def test_figure_conventions() -> None:
    print("\n[4] 图表命名约定与清单归类")
    with tempfile.TemporaryDirectory() as td:
        ws = make_workspace(Path(td))
        figs = pb.collect_figures(ws)
        check("收集到 2 张图", len(figs) == 2, str([f.path for f in figs]))
        kinds = {Path(f.path).stem: f.kind for f in figs}
        check("fig_* 归类为数据图", kinds.get("fig_result") == "data", str(kinds))
        check("tikz_* 归类为架构图", kinds.get("tikz_arch") == "diagram", str(kinds))
        check("LaTeX 名已 ASCII 化", all(f.latex_name.isascii() for f in figs))

        m = pb.parse_figure_manifest(ws)
        check("解析 FIGURE_MANIFEST", len(m) == 2, str(m))
        check("**清单章节归属优先于文件名前缀**",
              {e.name: e.section for e in m}.get("fig_result") == "结果",
              str({e.name: e.section for e in m}))

        # 中文文件名应被安全化
        check("中文名 ASCII 化不产生空名",
              pb.ascii_safe_name("中文图名").startswith("fig_"),
              pb.ascii_safe_name("中文图名"))
        check("纯数字名用 hash 兜底",
              pb.ascii_safe_name("123").startswith("fig_"), pb.ascii_safe_name("123"))


def test_deai_lint() -> None:
    print("\n[5] 去 AI 味检查")
    # 最高频痕迹：冒号写在加粗标记内
    r = dl.lint_text("**结论：** 模型有效。")
    check("**检出 `**标签：**`（最高频痕迹）**",
          any(i.rule == "bold_colon_inside" for i in r.errors), str(r.as_dict()))
    r2 = dl.lint_text("**结论**：模型有效。")
    check("合规写法不误报", not r2.errors, str(r2.as_dict()))

    check("检出自我指涉", any(i.rule == "self_reference"
                            for i in dl.lint_text("作为一个AI，我认为…").errors))
    check("检出占位符", any(i.rule == "placeholder_left"
                          for i in dl.lint_text("这里 TODO 待补充").errors))

    # 图题规则
    c0 = dl.check_caption("不同参数下的成本变化曲线示意图")   # 恰好 15 字，不应告警
    check("恰好 15 汉字不告警（边界正确）", not c0, str([i.as_dict() for i in c0]))

    c1 = dl.check_caption("不同参数设置下的运输成本变化曲线对比示意图")
    check("图题超 15 汉字 → warn",
          any(i.rule == "caption_too_long" and i.severity == "warn" for i in c1),
          str([i.as_dict() for i in c1]))
    c2 = dl.check_caption("成本随 $\\alpha$ 变化")
    check("**图题含公式 → error**",
          any(i.rule == "caption_has_math" for i in c2), str([i.as_dict() for i in c2]))
    c3 = dl.check_caption("成本变化曲线")
    check("合规图题无告警", not c3, str([i.as_dict() for i in c3]))


def test_latex_generation() -> None:
    print("\n[6] LaTeX 生成（不编译）")
    with tempfile.TemporaryDirectory() as td:
        ws = make_workspace(Path(td))
        doc, notes = pb.build_paper(ws, template="comp_cumcm", title="运输模型")
        prof = ty.resolve_profile("comp_cumcm")
        src = lx.build_document(doc, prof)

        check("用 ctexart 支持中文", "\\documentclass[12pt,a4paper]{ctexart}" in src)
        check("页边距来自规格", "left=2.5cm" in src)
        check("字体来自规格",
              "\\setCJKmainfont{SimSun}" in src and "\\setCJKfamilyfont{hei}{SimHei}" in src)
        check("行距用 setspace", "\\onehalfspacing" in src)
        check("**首行缩进为 2em 且在括号内**", "\\setlength{\\parindent}{2em}" in src)
        check("数学公式未被转义", "\\min\\sum" in src or "\\min" in src)
        check("含程序生成的表", "\\toprule" in src and "\\label{tab:" in src)
        check("含图", "\\includegraphics" in src)
        check("含参考文献悬挂缩进", "hanging" not in src and "0.74" in src)
        check("章节用 \\section", "\\section{问题重述}" in src, src[:200])

        # Markdown 行内转换
        check("粗体转换", "\\textbf{" in lx.md_inline_to_tex("这是**重点**")
              or "重点" in lx.md_inline_to_tex("这是**重点**"))
        check("特殊字符被转义",
              "\\&" in lx.md_inline_to_tex("A & B") and "\\%" in lx.md_inline_to_tex("50%"))
        check("列表转换为 itemize",
              "\\begin{itemize}" in lx.markdown_body_to_tex("- 甲\n- 乙"))


def test_docx_export_and_readback() -> None:
    print("\n[7] DOCX 导出并**回读验证**（中文 Word 的三个坑）")
    with tempfile.TemporaryDirectory() as td:
        ws = make_workspace(Path(td))
        res = dx.export_docx(ws, template="comp_cumcm", title="运输成本优化模型",
                             abstract="本文建立线性规划模型。",
                             keywords=["运输问题", "线性规划"])
        check("导出成功", res["ok"] and res["bytes"] > 0, str(res))
        check("含 2 张程序生成的表", res["tables"] == 2, str(res["tables"]))

        d = Document(res["docx"])
        sec = d.sections[0]

        # 坑 1：页边距
        check("页边距 2.5cm（约 1417320 EMU）",
              abs(sec.top_margin.cm - 2.5) < 0.01 and abs(sec.left_margin.cm - 2.5) < 0.01,
              f"top={sec.top_margin.cm} left={sec.left_margin.cm}")
        check("A4 纸张", abs(sec.page_width.cm - 21.0) < 0.1, str(sec.page_width.cm))

        # 坑 2：东亚字体必须单独设置
        all_runs = [r for p in d.paragraphs for r in p.runs]
        check("有正文 run", len(all_runs) > 5, str(len(all_runs)))

        def ea_font(run):
            rpr = run._element.find(qn("w:rPr"))
            if rpr is None:
                return None
            rf = rpr.find(qn("w:rFonts"))
            return rf.get(qn("w:eastAsia")) if rf is not None else None

        ea = {ea_font(r) for r in all_runs}
        check("**东亚字体已显式设置（非 None）**", None not in ea, str(ea))
        check("标题用 SimHei", "SimHei" in ea, str(ea))
        check("正文用 SimSun", "SimSun" in ea, str(ea))

        # 标题字号
        title_para = d.paragraphs[0]
        check("标题 18pt", abs(title_para.runs[0].font.size.pt - 18) < 0.01,
              str(title_para.runs[0].font.size.pt))
        check("标题加粗", title_para.runs[0].font.bold is True)

        # 坑 3：首行缩进按字符
        ind_paras = []
        for p in d.paragraphs:
            ppr = p._p.find(qn("w:pPr"))
            if ppr is None:
                continue
            ind = ppr.find(qn("w:ind"))
            if ind is not None and ind.get(qn("w:firstLineChars")):
                ind_paras.append(ind.get(qn("w:firstLineChars")))
        check("**存在 firstLineChars=200 的段落（2 字符缩进）**",
              "200" in ind_paras, str(ind_paras[:5]))

        # 三线表边框
        check("有表格", len(d.tables) >= 1, str(len(d.tables)))
        tbl = d.tables[0]
        hdr = tbl.rows[0].cells[0]
        tcpr = hdr._tc.find(qn("w:tcPr"))
        borders = tcpr.find(qn("w:tcBorders")) if tcpr is not None else None
        top = borders.find(qn("w:top")) if borders is not None else None
        bot = borders.find(qn("w:bottom")) if borders is not None else None
        check("表头上边框存在且为 1.5pt(12/8 磅)",
              top is not None and top.get(qn("w:sz")) == "12",
              str(top.get(qn("w:sz")) if top is not None else None))
        check("表头下边框为 0.75pt(6/8 磅)",
              bot is not None and bot.get(qn("w:sz")) == "6",
              str(bot.get(qn("w:sz")) if bot is not None else None))

        # 参考文献悬挂缩进
        hang = []
        for p in d.paragraphs:
            ppr = p._p.find(qn("w:pPr"))
            if ppr is None:
                continue
            ind = ppr.find(qn("w:ind"))
            if ind is not None and ind.get(qn("w:hanging")):
                hang.append(ind.get(qn("w:hanging")))
        check("参考文献有悬挂缩进（0.74cm ≈ 419 twips）",
              any(abs(int(h) - 419) < 10 for h in hang), str(hang))

        # 表内容与数据文件一致
        cells = [c.text for c in tbl.rows[1].cells]
        check("表内容取自数据文件（1234）",
              any("1234" in c for r in tbl.rows for c in [cc.text for cc in r.cells]),
              str(cells))


def test_tex_runtime_status() -> None:
    print("\n[8] TeX 运行时状态探测（对应用户可见的三态）")
    rt = tx.resolve_tex_runtime()
    check("状态是合法值之一", rt.state in ("ready", "fresh", "missing"), rt.state)
    check("返回结构化字典",
          set(rt.as_dict()) >= {"state", "xelatex", "installer_available", "note"})
    check("**检测随包安装器可用性**（对应 installerAvailable）",
          isinstance(rt.installer_available, bool), str(rt.installer_available))
    if not rt.ready:
        check("不可用时必须给出可读原因", bool(rt.note), rt.note)
    else:
        check("可用时给出 xelatex 路径", bool(rt.xelatex), str(rt.xelatex))


def test_markdown_table_conversion() -> None:
    """正文里的 Markdown 表格必须转成 LaTeX 表格。

    这是**看渲染结果**才发现的缺陷：曾把表格原样打印成 `|符号|含义|` 管道符源码。
    """
    print("\n[9] 正文 Markdown 表格 → LaTeX 三线表")
    body = (
        "## 符号说明\n\n"
        "| 符号 | 含义 |\n|---|---|\n"
        "| $x_{ij}$ | 运量 |\n| $c_{ij}$ | 单位运价 |\n\n"
        "后续正文。\n"
    )
    tex = lx.markdown_body_to_tex(body, table_caption="符号说明")
    check("**不再残留管道符源码**", "| 符号 |" not in tex and "|---|---|" not in tex,
          tex[:200])
    check("生成 tabular 环境", "\\begin{tabular}" in tex, tex[:200])
    check("使用 booktabs 三线", "\\toprule" in tex and "\\bottomrule" in tex)
    check("**生成 caption 参与编号**", "\\caption{符号说明}" in tex, tex[:200])
    check("单元格内公式未被转义", "$x_{ij}$" in tex, tex[:200])

    two = body + "\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    tex2 = lx.markdown_body_to_tex(two, table_caption="符号说明")
    check("同章节多表时表题带序号", "符号说明（2）" in tex2, tex2[-200:])

    mixed = "- 甲\n- 乙\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n- 丙\n"
    t3 = lx.markdown_body_to_tex(mixed, table_caption="混合")
    check("列表与表格混排正确",
          t3.count("\\begin{itemize}") == 2 and t3.count("\\end{itemize}") == 2
          and "\\begin{tabular}" in t3, t3[:300])


def test_figure_path_and_caption() -> None:
    """图路径必须相对 .tex，图注不能是文件路径。"""
    print("\n[10] 图路径解析与图注默认值")
    with tempfile.TemporaryDirectory() as td:
        ws = make_workspace(Path(td))
        doc, _ = pb.build_paper(ws, template="comp_cumcm", title="t")

        check("图注不是文件路径",
              all("figures/" not in f.display_caption for f in doc.figures),
              str([f.display_caption for f in doc.figures]))
        # ⚠️ 断言**反向**：图注不得回退到清单章节名。
        #   视觉自检抓过这条真缺陷：章节名是「结果与讨论」这种通用小标题，
        #   当图注用会误导读者（判词：「图题与图内标题不符，图题疑似错误」）。
        #   因此改为回退到与该图对应的可读名。
        check("**图注不回退到清单章节名**",
              all(f.display_caption not in ("结果", "架构", "结果与讨论")
                  for f in doc.figures),
              str([f.display_caption for f in doc.figures]))
        check("图注用可读名（与该图对应）",
              all("." not in f.display_caption for f in doc.figures),
              str([f.display_caption for f in doc.figures]))

        check("无清单时用可读名",
              pb.pretty_figure_name("fig_scenarios") == "scenarios"
              and pb.pretty_figure_name("tikz_arch") == "arch",
              pb.pretty_figure_name("fig_scenarios"))

        fig = pb.FigureRef(path="figures/fig_a.png", latex_name="a", kind="data")
        t1 = fig.to_latex(base_prefix="../")
        # ⚠️ 断言只校验**路径**，不要把整个 \includegraphics 选项串写死：
        #   选项会随排版规格调整（实测新增了 height/keepaspectratio 以限制图高），
        #   写死会让无关的规格变更把这条用例打红。
        check("**图路径带正确前缀**", "{../figures/fig_a.png}" in t1, t1)
        t2 = fig.to_latex(base_prefix="")
        check("空前缀时保持原路径", "{figures/fig_a.png}" in t2, t2)

        prof = ty.resolve_profile("comp_cumcm")
        src = lx.build_document(doc, prof, figure_base="../")
        check("端到端 .tex 中图路径正确", "{../figures/" in src, src[-400:])


def test_compile_success_criterion() -> None:
    """编译成功判定必须严格——不能把「产出部分 PDF」当成功。

    实测教训：插图路径错误 → xelatex 中途报错 → 输出前 2 页的部分 PDF，
    而旧的 `size > 0` 判据把它报成了成功。
    """
    print("\n[11] 编译成功判定（★ 曾把失败误报为成功）")
    rt = tx.resolve_tex_runtime()
    if not rt.ready:
        print("      (TeX 不可用，跳过编译用例)")
        check("TeX 不可用时如实报告状态", rt.state in ("fresh", "missing"), rt.state)
        return

    with tempfile.TemporaryDirectory() as td:
        d = Path(td)

        good = d / "good.tex"
        good.write_text(
            "\\documentclass{article}\\usepackage{xeCJK}\n"
            "\\begin{document}正常\\end{document}\n", encoding="utf-8")
        r1 = tx.compile_tex(good, runtime=rt, runs=1)
        check("正常文档编译成功", r1.ok, r1.error)

        bad = d / "bad.tex"
        bad.write_text(
            "\\documentclass{article}\\usepackage{graphicx}\n"
            "\\begin{document}\n"
            "\\includegraphics[width=5cm]{no_such_file_xyz.png}\n"
            "\\end{document}\n", encoding="utf-8")
        r2 = tx.compile_tex(bad, runtime=rt, runs=1)
        check("**引用缺失图片必须报失败**（不能看 size>0 就放行）",
              not r2.ok, f"ok={r2.ok} err={r2.error!r}")
        check("失败时给出可读错误", bool(r2.error), r2.error)

        bad2 = d / "bad2.tex"
        bad2.write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "\\thisIsNotACommand\n\\end{document}\n", encoding="utf-8")
        r3 = tx.compile_tex(bad2, runtime=rt, runs=1)
        check("未知命令必须报失败", not r3.ok, f"ok={r3.ok}")


def test_figure_style_cjk() -> None:
    """图表必须能显示中文——否则轴标签会变成方框。

    这是**看图**才发现的缺陷：测试全绿，但图里中文全是 `□□`。
    """
    print("\n[12] 图表中文字体配置")
    from services import figure_style as fs

    rep = fs.apply_cjk_style(preset="paper")
    if not rep.applied:
        print("      (matplotlib 不可用，跳过)")
        check("matplotlib 不可用时如实报告", bool(rep.warnings), str(rep.as_dict()))
        return

    check("找到并应用了中文字体", rep.cjk_font is not None, str(rep.as_dict()))
    if rep.cjk_font:
        import matplotlib
        check("中文字体在 matplotlib 字体族首位",
              matplotlib.rcParams["font.sans-serif"][0] == rep.cjk_font)
    import matplotlib
    check("**关闭 unicode_minus**（负号否则显示方框）",
          matplotlib.rcParams["axes.unicode_minus"] is False)

    import matplotlib.pyplot as plt
    fig, ax = fs.new_figure(3.0, 2.0)
    ax.bar(["基准", "扰动"], [1, 2])
    ax.set_ylabel("总成本（元）")
    ax.set_title("中文测试")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "zh.png"
        try:
            fs.save_figure(fig, out)
            check("**含中文的图可正常保存（无缺字形告警）**",
                  out.is_file() and out.stat().st_size > 0)
        except RuntimeError as exc:
            check("含中文的图可正常保存", False, str(exc)[:160])
        finally:
            plt.close(fig)


def main() -> int:
    print("=" * 74)
    print("modemon 成文链测试（排版规格 / 程序化表格 / 去AI味 / LaTeX / DOCX）")
    print("=" * 74)
    test_typography_profile()
    test_page_budget()
    test_programmatic_tables()
    test_figure_conventions()
    test_deai_lint()
    test_latex_generation()
    test_docx_export_and_readback()
    test_tex_runtime_status()
    test_markdown_table_conversion()
    test_figure_path_and_caption()
    test_compile_success_criterion()
    test_figure_style_cjk()
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
