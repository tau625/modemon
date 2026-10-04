"""LaTeX 导出：把论文模型渲染成可编译的 `.tex` 并编译为 PDF。

排版参数**全部取自 `typography` 的规格**（该规格的数值恢复自蓝方，
而蓝方又自陈对标公开的 `cumcmthesis.cls`）：

    A4 / 页边距 2.5cm / 正文 12pt / 1.5 倍行距 / 首行缩进 2 字符
    标题 15-14-12-11pt / 三线表 / 图宽上限 14cm / 参考文献悬挂缩进 0.74cm

与蓝方的差异：蓝方用自研 docx 引擎 + `.cls`；这里用 `ctexart` + `booktabs`
直接产出可编译 LaTeX，**同一份论文模型可分别导出 docx 与 pdf**。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from . import paper_build as pb
from . import tex_runtime as tx
from . import typography as ty

#: LaTeX 特殊字符转义
_ESC = (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("$", r"\$"),
        ("#", r"\#"), ("_", r"\_"), ("{", r"\{"), ("}", r"\}"),
        ("~", r"\textasciitilde{}"), ("^", r"\textasciicircum{}"))

#: **引擎产出标识**——写在 `.tex` 的首行。
#:
#: 用途：区分「本引擎生成的文件」与「agent / 人写的文件」。
#: 为什么必须有：`export_latex` 的默认输出名是 `paper/main.tex`，而 agent
#: 在 `comp-paper-zh` 步骤里也可能**直接写** `paper/main.tex`。实测中一次导出
#: 就把 agent 写的 27,538 B 完整论文覆盖成 1,845 B 的桩，而且回报 `ok: true`
#: ——这是本项目唯一的 P0 数据丢失缺陷。有了首行标记，导出前就能判定归属：
#: **没有标记的 `.tex` 一律视为他人产物，改名保留而不是覆盖。**
EXPORT_MARKER = "% modemon:generated-latex-export"


def is_engine_generated(tex_text: str) -> bool:
    """判断一份 `.tex` 是否由本引擎生成（看首行生成标记）。

    只认**首行**：正文里偶然出现同名字符串（比如引用本文档的说明）不算数。
    BOM 与首行前导空白都容忍——编辑器保存过一轮就可能带上。
    """
    if not tex_text.strip():
        return False
    first = tex_text.lstrip("\ufeff").splitlines()[0]
    return first.strip() == EXPORT_MARKER


def tex_escape(s: str) -> str:
    for a, b in _ESC:
        s = s.replace(a, b)
    return s


def md_inline_to_tex(s: str) -> str:
    """把 Markdown 行内标记转成 LaTeX。

    只处理**行内**要素（粗体/斜体/行内代码/链接/交叉引用），块级交给上层。
    刻意保持最小实现，避免引入难以预测的 Markdown 库。

    ## 交叉引用语法

        @ref(tab:results)   →  \\ref{tab:results}
        @ref(fig:monte)     →  \\ref{fig:monte}

    为什么需要它：表号/图号由 LaTeX 自动分配，正文硬编码「见表 1」
    会随表格增减而**错位**。实测中正文写「表 1、表 2」，而实际表号是
    表 2、表 3（前面还有一张符号说明表占了表 1），视觉自检直接判了
    「交叉引用编号整体错位」。用 `@ref` 让编号永远正确。
    """
    import re

    # 先抽出要原样保留的内容，避免被转义
    math: list[str] = []

    def stash(m: re.Match[str]) -> str:
        math.append(m.group(0))
        return f"\x00M{len(math) - 1}\x00"

    s = re.sub(r"\$\$[^$]+\$\$|\$[^$\n]+\$", stash, s)

    # 交叉引用：@ref(kind:name)。
    # ⚠️ 转换结果必须**暂存**，不能直接留回字符串——
    #   下一步的 tex_escape 会把它 `\ref{...}` 里的反斜杠和花括号转义掉。
    #   实测：`@ref(tab:results)` 被转成了 `\textbackslash\{\}ref\{tab:results\}`。
    refs: list[str] = []

    def stash_ref(m: re.Match[str]) -> str:
        kind, name = m.group(1), m.group(2)
        refs.append(f"\\ref{{{kind}:{name}}}")
        return f"\x00R{len(refs) - 1}\x00"

    s = re.sub(r"@ref\(([A-Za-z_]\w*)\s*:\s*([\w.\-]+)\)", stash_ref, s)

    s = tex_escape(s)
    # 行内代码
    s = re.sub(r"`([^`]+)`", lambda m: r"\texttt{" + m.group(1) + "}", s)
    # 粗体 / 斜体
    s = re.sub(r"\*\*([^*]+)\*\*", lambda m: r"\textbf{" + m.group(1) + "}", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", lambda m: r"\emph{" + m.group(1) + "}", s)
    # 链接
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
               lambda m: r"\href{" + m.group(2) + "}{" + m.group(1) + "}", s)
    # 恢复公式与交叉引用
    for i, raw in enumerate(math):
        s = s.replace(f"\x00M{i}\x00", raw)
    for i, raw in enumerate(refs):
        s = s.replace(f"\x00R{i}\x00", raw)
    return s


def markdown_body_to_tex(body: str, *, table_caption: str = "") -> str:
    """把一段 Markdown 章节体转成 LaTeX。

    处理：**表格**、列表、段落与行内标记。

    Args:
        table_caption: 正文内 Markdown 表格的表题。
            若不传，表会**没有 `\\caption` 从而不参与编号**——
            实测中出现过"符号说明表无编号、后面的表却是表 1"的不一致。
            默认用所属章节标题，保持编号连续。

    ⚠️ 表格必须处理：曾漏掉这一步，正文里的 Markdown 表格被原样打印成
    `|符号|含义|` 这样的管道符源码——**测试查不出来，只有看渲染结果才能发现**。
    """
    import re

    lines = body.splitlines()
    out: list[str] = []
    in_item = False
    i = 0
    tbl_index = 0

    def close_list() -> None:
        nonlocal in_item
        if in_item:
            out.append(r"\end{itemize}")
            in_item = False

    while i < len(lines):
        line = lines[i]

        # ---- Markdown 表格 ----
        if line.strip().startswith("|") and i + 1 < len(lines) \
                and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            close_list()
            header = _split_md_row(line)
            rows: list[list[str]] = []
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows.append(_split_md_row(lines[j]))
                j += 1
            tbl_index += 1
            cap = table_caption or "表格"
            if tbl_index > 1:
                cap = f"{cap}（{tbl_index}）"
            out.append(_md_table_to_tex(header, rows, caption=cap))
            i = j
            continue

        if not line.strip():
            close_list()
            out.append("")
            i += 1
            continue

        m = re.match(r"^(\s*)[-*+]\s+(.*)$", line)
        n = re.match(r"^(\s*)\d+[.)]\s+(.*)$", line)
        if m or n:
            if not in_item:
                out.append(r"\begin{itemize}")
                in_item = True
            out.append(r"  \item " + md_inline_to_tex((m or n).group(2)))  # type: ignore[union-attr]
            i += 1
            continue

        close_list()
        out.append(md_inline_to_tex(line))
        i += 1

    close_list()
    return "\n".join(out)


def _split_md_row(line: str) -> list[str]:
    """拆一行 Markdown 表格（去掉首尾竖线，保护转义竖线）。"""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    s = s.replace(r"\|", "\x00PIPE\x00")
    return [c.strip().replace("\x00PIPE\x00", "|") for c in s.split("|")]


def _md_table_to_tex(header: list[str], rows: list[list[str]], *, caption: str = "") -> str:
    """Markdown 表格 → LaTeX 三线表（booktabs）。

    `caption` 非空时会生成 `\\caption`，让 LaTeX 参与自动编号；
    否则该表不编号，可能与后续表编号不一致。
    """
    ncol = max([len(header)] + [len(r) for r in rows]) if (header or rows) else 0
    if ncol == 0:
        return ""
    col = "l" + "c" * (ncol - 1)
    # [htbp]：正常浮动，由 placeins 的 \FloatBarrier 限制在本节内
    lines = [r"\begin{table}[htbp]", r"  \centering"]
    if caption:
        lines.append(f"  \\caption{{{md_inline_to_tex(caption)}}}")
    lines += [f"  \\begin{{tabular}}{{{col}}}", r"    \toprule",
              "    " + " & ".join(md_inline_to_tex(c) for c in header) + r" \\",
              r"    \midrule"]
    for r in rows:
        cells = (list(r) + [""] * ncol)[:ncol]
        lines.append("    " + " & ".join(md_inline_to_tex(c) for c in cells) + r" \\")
    lines += [r"    \bottomrule", r"  \end{tabular}", r"\end{table}"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 文档模板
# ---------------------------------------------------------------------------


def _spacing_command(line_spacing: float) -> str:
    """把 Word 语义的行距映射为 LaTeX。

    ⚠️ **这是近似映射**：Word 的"1.5 倍行距"与 LaTeX 的 `\\linespread` 基数不同
    （LaTeX baselineskip ≈ 1.2×字号），两者无法精确等价。
      - 1.0 → `\\singlespacing`
      - 1.5 → `\\onehalfspacing`
      - 2.0 → `\\doublespacing`
      - 其它 → `\\setstretch{x}`，取 `x ≈ 行距 / 1.2` 的经验值
    """
    if abs(line_spacing - 1.0) < 1e-6:
        return r"\singlespacing"
    if abs(line_spacing - 1.5) < 1e-6:
        return r"\onehalfspacing"
    if abs(line_spacing - 2.0) < 1e-6:
        return r"\doublespacing"
    return f"\\setstretch{{{line_spacing / 1.2:.3f}}}"


def build_preamble(profile: ty.StyleProfile, *, language: str = "zh") -> str:
    """按规格生成导言区。"""
    p = profile
    f = p.fonts
    geo = p.page
    body = p.body
    L = [
        # ★ 首行生成标记：`export_latex` 靠它区分「引擎自己的产物」与「agent 的产物」。
        #   没有这一行 ⇒ 导出时按「他人产物」处理，改名保留而非覆盖（见 EXPORT_MARKER）。
        EXPORT_MARKER,
        r"% !TEX program = xelatex",
        r"\documentclass[12pt,a4paper]{ctexart}",
        r"\usepackage{geometry}",
        f"\\geometry{{top={geo['margin_top_cm']}cm,bottom={geo['margin_bottom_cm']}cm,"
        f"left={geo['margin_left_cm']}cm,right={geo['margin_right_cm']}cm}}",
        r"\usepackage{graphicx}",
        r"\usepackage{booktabs}",
        r"\usepackage{array}",
        # ★ 浮动体策略：**不要用 float 宏包的 [H]**。
        #
        # 实测教训：先试了 [H]（就地固定），结果出现**整页空白**——
        # 因为 [H] 要求图表必须在当前位置放下，放不下就整体推到下一页，
        # 又不能用文字填补，于是留下空白页。比原来的漂移更糟。
        #
        # 正确的组合是：[htbp] 让 LaTeX 正常浮动 + placeins 的 \FloatBarrier
        # 把浮动体裁在**本节范围内**。这样既不漂到文末，也不产生空白页。
        r"\usepackage[section]{placeins}",
        # ★ \\captionof：在不使用浮动环境时给出带编号的标题。
        #   文末的纯浮动体区块（结果数据表 / 图表）用它做**非浮动**排版，
        #   避免"标题落单"与"整页空白"。
        r"\usepackage{caption}",
        r"\usepackage{longtable}",
        r"\usepackage{amsmath,amssymb}",
        r"\usepackage{setspace}",
        r"\usepackage[hidelinks]{hyperref}",
        r"\usepackage{enumitem}",
        r"\usepackage{xcolor}",
        "",
        "% ---- 字体（取自排版规格）----",
        f"\\setCJKmainfont{{{f['chinese_body']}}}",
        f"\\setCJKfamilyfont{{hei}}{{{f['chinese_heading']}}}",
        f"\\setmainfont{{{f['latin']}}}",
        f"\\setmonofont{{{f['monospace']}}}",
        r"\newcommand{\hei}{\CJKfamily{hei}}",
        "",
        "% ---- 版式（行距为近似映射，见 _spacing_command）----",
        _spacing_command(float(body["line_spacing"])),
        f"\\setlength{{\\parindent}}{{{body['first_line_indent_chars']}em}}",
        r"\setlength{\parskip}{0pt}",
        # ★ 表题 / 图题字重统一。
        #   视觉自检报过「表题字重不一致」：只给全局 `\captionsetup` 时，
        #   表与图的题注分别继承 caption 宏包对 `table` / `figure` 的不同默认
        #   （label 是否加粗、字号继承链不同），同一篇论文里两种题注看起来不是一套。
        #   这里对两类**各钉一份完全相同的设置**，把字重/字号/标签间距对齐；
        #   全局那一行保留，管住 `\captionof` 之外的其它题注。
        r"\captionsetup{font=small,labelsep=quad}",
        r"\captionsetup[table]{font=small,labelsep=quad}",
        r"\captionsetup[figure]{font=small,labelsep=quad}",
        "",
        r"\begin{document}",
    ]
    return "\n".join(L)


def caption_inside_environment(block: str) -> str:
    """把非浮动块里的 `\\captionof` / `\\label` 收进 `center` 环境内。

    ## 为什么需要

    `TableSpec.to_inline_latex()` 把 `\\captionof{table}` 排在 `\\begin{center}`
    **之前**，`FigureSpec.to_inline_latex()` 把它排在 `\\end{center}` **之后**。
    两种写法都让 `\\captionof` 落在任何 box / 环境之外，caption 宏包随即报：

        Package caption Warning: \\setcaptiontype outside box or environment

    警告本身不致命，但它说明题注的编号归属是**未定义**的——编号可能在后续
    增删图表时错位。

    ## 做法

    在**导出边界**做等价包装：把题注移进所属的 `center` 环境，并保持它相对
    主体的位置不变（中文论文规范：**表题在上、图题在下**）。

    ## 幂等性

    若传入的块里题注已经在 `center` 环境内，原样返回。因此上游哪天直接在
    `paper_build` 里修好，这里也不会重复包装。
    """
    lines = block.splitlines()
    if not lines:
        return block

    def _is_caption(ln: str) -> bool:
        s = ln.strip()
        return s.startswith((r"\captionof", r"\label"))

    cap_lines = [ln.strip() for ln in lines if _is_caption(ln)]
    if not cap_lines:
        return block

    begins = [i for i, ln in enumerate(lines)
              if ln.strip().startswith(r"\begin{center}")]
    ends = [i for i, ln in enumerate(lines)
            if ln.strip().startswith(r"\end{center}")]

    if not begins or not ends or ends[-1] < begins[0]:
        # 完全没有 center 环境：整体包一层，题注保持原有相对次序
        return "\n".join([r"\begin{center}"]
                         + ["  " + ln.strip() for ln in lines]
                         + [r"\end{center}"])

    first_cap = next(i for i, ln in enumerate(lines) if _is_caption(ln))
    last_cap = next(i for i in range(len(lines) - 1, -1, -1)
                    if _is_caption(lines[i]))
    if begins[0] < first_cap and last_cap < ends[-1]:
        return block  # 题注已在环境内 → 幂等返回

    caption_above = first_cap < begins[0]   # 表格：题注在主体之上
    body = [ln for ln in lines if not _is_caption(ln)]
    b2 = next(i for i, ln in enumerate(body)
              if ln.strip().startswith(r"\begin{center}"))
    e2 = next(i for i in range(len(body) - 1, -1, -1)
              if body[i].strip().startswith(r"\end{center}"))

    moved = ["  " + c for c in cap_lines]
    if caption_above:
        return "\n".join(body[:b2 + 1] + moved + body[b2 + 1:])
    return "\n".join(body[:e2] + moved + body[e2:])


def build_document(
    doc: pb.PaperDoc,
    profile: ty.StyleProfile,
    *,
    include_tables: bool = True,
    include_figures: bool = True,
    include_ai_disclosure: bool = True,
    figure_base: str = "",
) -> str:
    """生成完整 `.tex`。

    Args:
        figure_base: 从 `.tex` 所在目录指向工作区根的前缀（如 `../`）。
            `\\includegraphics` 的路径相对于 `.tex` 文件，必须给对，
            否则编译会在插图处中断并产出截断的 PDF。
    """
    p = profile
    L: list[str] = [build_preamble(profile, language=doc.language), ""]

    # ---- 标题区 ----
    t = p.title
    L += [
        r"\begin{center}",
        f"  {{\\hei\\fontsize{{{t['font_size_pt']}}}{{{t['font_size_pt'] + 6}}}\\selectfont "
        f"\\textbf{{{tex_escape(doc.title)}}}}}",
        r"\end{center}",
        r"\vspace{6pt}",
        "",
    ]

    # ---- 摘要 ----
    if doc.abstract:
        ab = p.data.get("abstract", {})
        L += [
            r"\begin{center}",
            f"  {{\\hei\\fontsize{{{ab.get('label_size_pt', 14)}}}{{{ab.get('label_size_pt', 14) + 6}}}\\selectfont "
            f"\\textbf{{摘要}}}}",
            r"\end{center}",
            r"\vspace{4pt}",
            "",
            markdown_body_to_tex(doc.abstract),
            "",
        ]
    if doc.keywords:
        kw = p.data.get("keywords", {})
        L += [
            f"\\noindent{{\\hei\\fontsize{{{kw.get('label_size_pt', 12)}}}"
            f"{{{kw.get('label_size_pt', 12) + 4}}}\\selectfont\\textbf{{关键词}}}}\\quad "
            + "；".join(tex_escape(k) for k in doc.keywords),
            "",
        ]

    # ⚠️ **无摘要时不要断页**。
    #   实测：agent 把摘要写成**分节**（`paper/sections/00_摘要.md`），
    #   于是 `doc.abstract` 为空 → 无条件 `\newpage` 让第 1 页只剩一个标题
    #   （版面校验报「近乎空白页」），而摘要在第 2 页。
    #   无摘要时让首个分节自然接在标题下——这也符合竞赛论文惯例
    #   （标题与摘要同页）。
    if doc.abstract:
        L += [r"\newpage", ""]

    # ---- 正文 ----
    for s in doc.sections:
        # 正文首部的 `# 标题` 通常就是文档标题，避免重复渲染
        if s.level == 1 and doc.title and s.title.strip() == doc.title.strip() and not s.body.strip():
            continue
        if s.level == 1:
            L.append(f"\\section{{{tex_escape(s.title)}}}")
        elif s.level == 2:
            L.append(f"\\subsection{{{tex_escape(s.title)}}}")
        else:
            L.append(f"\\subsubsection{{{tex_escape(s.title)}}}")
        if s.body.strip():
            L.append(markdown_body_to_tex(s.body, table_caption=s.title))
        L.append("")

    # ---- 表格（程序生成，附在结果章节后） ----
    # ⚠️ 这里用**非浮动**排版（to_inline_latex）：
    #   浮动环境在纯浮动体区块里必然出病——`[htbp]` 让标题落单、
    #   `[H]` 留出没有文字可填的空白。改为 \\captionof 后版面确定。
    if include_tables and doc.tables:
        L.append(r"\section*{结果数据表}")
        L.append(r"\addcontentsline{toc}{section}{结果数据表}")
        for tspec in doc.tables:
            # ★ 题注入环境：`to_inline_latex()` 把 `\captionof` 排在 center 之外，
            #   caption 宏包会报 "outside box or environment"。包装后表题仍在表格上方。
            L.append(caption_inside_environment(tspec.to_inline_latex()))
            L.append("")

    # ---- 图 ----
    if include_figures and doc.figures:
        L.append(r"\section*{图表}")
        L.append(r"\addcontentsline{toc}{section}{图表}")
        for f in doc.figures:
            L.append(caption_inside_environment(
                f.to_inline_latex(width_cm=float(p.image["max_width_cm"]),
                                  base_prefix=figure_base)))
            L.append("")

    # ---- 参考文献 ----
    # 非浮动排版后不再需要 \FloatBarrier，保留一处以吸收正文段落里的浮动体
    L.append(r"\FloatBarrier")
    if doc.references:
        refs = p.references
        L += [
            r"\section*{参考文献}",
            r"\addcontentsline{toc}{section}{参考文献}",
            f"\\begin{{list}}{{}}{{\\setlength{{\\leftmargin}}{{{refs['hanging_indent_cm']}cm}}"
            f"\\setlength{{\\itemindent}}{{-{refs['hanging_indent_cm']}cm}}"
            f"\\fontsize{{{refs['font_size_pt']}}}{{{refs['font_size_pt'] + 3}}}\\selectfont}}",
        ]
        for i, r in enumerate(doc.references, 1):
            # ★ 编号渲染成 `[1]`，而不是裸 `1`。
            #   `\item[{i}]` 只出 `1`，与「[1][2][3]」的引用惯例不符。
            #   `\item[{[i]}]` 用花括号包住方括号，LaTeX 才会把 `[1]` 当成完整标签
            #   （直接写 `\item[[1]]` 会在第一个 `]` 处截断成 `[1`）。
            L.append(f"  \\item[{{[{i}]}}] {tex_escape(r)}")
        L += [r"\end{list}", ""]

    # ---- AI 使用申报（国赛要求） ----
    if include_ai_disclosure and doc.ai_disclosure:
        L += [
            r"\section*{AI 工具使用情况}",
            r"\addcontentsline{toc}{section}{AI 工具使用情况}",
            r"\begin{enumerate}[leftmargin=2em]",
        ]
        for rec in doc.ai_disclosure:
            tool = tex_escape(str(rec.get("tool_name", "")))
            purpose = tex_escape(str(rec.get("purpose", "")))
            used = tex_escape(str(rec.get("output_used", "")))
            L.append(f"  \\item \\textbf{{{tool}}}：{purpose}"
                     + (f"（采用情况：{used}）" if used else ""))
        L += [r"\end{enumerate}", ""]

    L.append(r"\end{document}")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 端到端
# ---------------------------------------------------------------------------


@dataclass
class ExportResult:
    """导出结果。

    `ok` 是**唯一**的成功判据：正文为空、编译失败、以及未来任何前置条件
    不满足时都必须为 False。历史上这里只看「有没有产出文件」，把
    `body_chars=0` 的桩导出报成了成功——和「size > 0 即成功」是同一类错误。
    """

    ok: bool
    tex: Optional[str] = None
    pdf: Optional[str] = None
    pages: Optional[int] = None
    compile_error: str = ""
    error: str = ""
    log_tail: str = ""
    budget: Optional[dict[str, Any]] = None
    notes: list[str] = None  # type: ignore[assignment]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok, "tex": self.tex, "pdf": self.pdf, "pages": self.pages,
            "compile_error": self.compile_error, "error": self.error,
            "log_tail": self.log_tail,
            "budget": self.budget, "notes": self.notes or [],
        }


#: `body_chars == 0` 时的错误文案（调用方与测试都按它判定「空正文」）。
EMPTY_BODY_ERROR = (
    "正文为空（body_chars=0）：paper/sections/*.md、paper/main.md 与 agent 直出的 "
    "paper/main.tex 都没有可用正文，本次导出不作为成功"
)


def _unique_path(p: Path) -> Path:
    """目标已存在时返回 `stem.N.suffix` 形式的可用路径（N 从 2 起）。"""
    if not p.exists():
        return p
    i = 2
    while True:
        cand = p.with_name(f"{p.stem}.{i}{p.suffix}")
        if not cand.exists():
            return cand
        i += 1


def _archive_existing_tex(tex_path: Path, notes: list[str]) -> Optional[Path]:
    """若 `tex_path` 已存在且**非本引擎生成**，改名归档；返回归档路径。

    ★ P0：绝不覆盖 agent / 人工写的 `.tex`。

    判定依据是首行生成标记（`EXPORT_MARKER`）：
      - 有标记 → 是本引擎上一轮的产物，直接覆盖，不留垃圾文件；
      - 无标记 → 视为他人产物，改名成 `main.agent.tex`（已被占用则
        `main.agent.2.tex`…），**内容一字不动**地保留下来。

    实测教训：这里原先无条件覆盖，把 agent 直写的 27,538 B 完整论文冲成
    1,845 B 的桩，而且回报 `ok: true`——一次导出即摧毁 `comp-paper-zh` 的全部产出。
    """
    if not tex_path.is_file():
        return None
    try:
        existing = tex_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        existing = ""
    if is_engine_generated(existing):
        return None

    keep = _unique_path(tex_path.with_name(f"{tex_path.stem}.agent{tex_path.suffix}"))
    tex_path.rename(keep)
    notes.append(
        f"`paper/{tex_path.name}` 已存在且非本引擎生成（首行无生成标记），"
        f"已改名保留为 `paper/{keep.name}`；本次导出未覆盖该文件")
    return keep


def export_latex(
    workspace: Path,
    *,
    template: str = "comp_cumcm",
    language: str = "zh",
    title: str = "",
    abstract: str = "",
    keywords: Optional[list[str]] = None,
    compile_pdf: bool = True,
    tex_name: str = "main.tex",
) -> ExportResult:
    """从工作区装配论文并导出 LaTeX（可选编译 PDF）。

    产出写入 `<workspace>/paper/`。

    ## 三条硬约束（都来自实测缺陷）

    1. **agent 直出成品 → 只编译不重建**：`pb.build_paper` 检出
       `paper/main.tex` 是 agent 的成品（无引擎生成标记、且自带
       `\\documentclass`）时置 `doc.is_prebuilt`。此时**原样编译那个文件**，
       不重新装配、不改名、不写入——重建就等于覆盖 agent 的成品（P0）。
    2. **不覆盖他人产物**：走装配路径时若 `paper/<tex_name>` 已存在且无引擎
       生成标记，先改名归档再落盘（见 `_archive_existing_tex`）。
    3. **空正文不算成功**：`body_chars == 0` → `ok=False` + `error`，
       并且**不再编译 PDF**——桩 PDF「看起来成功」正是要消除的假信号。
    """
    ws = Path(workspace)
    paper_dir = ws / "paper"
    paper_dir.mkdir(parents=True, exist_ok=True)

    doc, notes = pb.build_paper(ws, template=template, language=language,
                                title=title, abstract=abstract, keywords=keywords)

    profile = ty.resolve_profile(template)
    budget = doc.budget().as_dict()
    body_chars = int(budget.get("body_chars") or 0)
    if budget.get("over_limit"):
        notes.append(
            f"页数估算 {budget['estimated_pages']} 页超过参考上限 {budget['limit']} 页"
            "（**仅提示，不作门控**）")

    # ------------------------------------------------------------------
    # 路径 A：agent 直出成品 —— 只编译，不重建、不改动
    # ------------------------------------------------------------------
    if getattr(doc, "is_prebuilt", False):
        prebuilt_path = ws / str(doc.prebuilt_tex)
        res = ExportResult(ok=True, tex=str(prebuilt_path), budget=budget, notes=notes)
        res.notes.append(
            "走「只编译不重建」路径：未按 Markdown 重新装配，"
            f"未改动 `{doc.prebuilt_tex}`（agent 直出成品）")
        if body_chars == 0:
            res.ok = False
            res.error = EMPTY_BODY_ERROR
            res.notes.append("未编译 PDF：正文为空时不再产出「看起来成功」的桩 PDF")
            return res
        if compile_pdf:
            cr = tx.compile_tex(prebuilt_path)
            res.log_tail = cr.log_tail
            if cr.ok:
                res.pdf = cr.pdf
                res.pages = cr.pages
                if cr.pages and budget.get("limit") and cr.pages > int(budget["limit"]):
                    res.notes.append(
                        f"实测 {cr.pages} 页 > 参考上限 {budget['limit']} 页（advisory）")
            else:
                res.ok = False
                res.compile_error = cr.error
        return res

    # ------------------------------------------------------------------
    # 路径 B：按 Markdown 分节重新装配
    # ------------------------------------------------------------------
    # 表格落盘，便于溯源与人工核对
    if doc.tables:
        pb.write_table_files(ws, doc.tables)

    # ★ 计算「.tex 所在目录 → 工作区根」的相对前缀。
    #   `\includegraphics` 的路径相对于 .tex 文件；图在 <ws>/figures/、
    #   .tex 在 <ws>/paper/，因此多数情况下需要 `../`。
    import os as _os
    rel = _os.path.relpath(str(ws.resolve()), str(paper_dir.resolve()))
    figure_base = "" if rel == "." else rel.replace("\\", "/") + "/"

    tex_src = build_document(doc, profile, figure_base=figure_base)
    tex_path = paper_dir / tex_name

    # ★ P0：先归档他人产物，再落盘。顺序不能颠倒——颠倒就是覆盖。
    _archive_existing_tex(tex_path, notes)
    tex_path.write_text(tex_src, encoding="utf-8")

    res = ExportResult(ok=True, tex=str(tex_path), budget=budget, notes=notes)

    # ★ P0：空正文 → 明确失败，且不编译。
    #   旧行为：产出 2 页桩 PDF 并报 ok:true。桩看着像论文，掩盖了
    #   「引擎根本没找到正文」这个事实。
    if body_chars == 0:
        res.ok = False
        res.error = EMPTY_BODY_ERROR
        res.notes.append("未编译 PDF：正文为空时不再产出「看起来成功」的桩 PDF")
        return res

    if compile_pdf:
        cr = tx.compile_tex(tex_path)
        res.log_tail = cr.log_tail
        if cr.ok:
            res.pdf = cr.pdf
            res.pages = cr.pages
            if cr.pages and budget.get("limit") and cr.pages > int(budget["limit"]):
                res.notes.append(
                    f"实测 {cr.pages} 页 > 参考上限 {budget['limit']} 页（advisory）")
        else:
            res.ok = False
            res.compile_error = cr.error
    return res


__all__ = [
    "ExportResult", "build_preamble", "build_document", "export_latex",
    "tex_escape", "md_inline_to_tex", "markdown_body_to_tex",
    "caption_inside_environment", "is_engine_generated",
    "EXPORT_MARKER", "EMPTY_BODY_ERROR",
]
