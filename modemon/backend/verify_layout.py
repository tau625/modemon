#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""论文版面校验器：用**程序化**方式发现"看一眼"才能发现的问题。

为什么需要它
------------
之前的教训是「测试全绿但 PDF 版面是坏的」，只能靠看渲染结果发现。
但"看"不可复用、也不可回归。这里把三类视觉缺陷转成**可执行断言**：

  1. 空白页          —— 一页除去页码后正文不足 N 字符
  2. 孤立标题        —— 章节标题出现在页尾，而它的正文/表在下一页
  3. 图文割裂        —— 图注与所指的图相隔超过 1 页

用法：python verify_layout.py <paper.pdf>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

#: 除去页码后，少于这个字符数算"近乎空白"
BLANK_MIN_CHARS = 60

#: 标题孤立判定：标题在页尾、正文在下一页
ORPHAN_GAP_CHARS = 25


def _body_chars(text: str) -> int:
    """去掉页码后的正文字符数。"""
    body = re.sub(r"(?m)^\s*\d+\s*$", "", text).strip()
    return len(body)


def check(path: Path) -> int:
    try:
        import fitz  # type: ignore
    except Exception as exc:  # pragma: no cover
        print("需要 PyMuPDF：pip install pymupdf  (%s)" % exc)
        return 2

    doc = fitz.open(str(path))
    print("=" * 74)
    print("论文版面校验：%s" % path.name)
    print("=" * 74)

    pages: list[str] = []
    # 每页的**图片面积占比**：图不产生文字，
    # 若只数文字，一整页插图会被误判为"空白页"（实测过）。
    img_cover: list[float] = []
    for i in range(doc.page_count):
        pg = doc[i]
        pages.append(pg.get_text())
        area = 0.0
        try:
            for info in pg.get_images(full=True):
                try:
                    rects = pg.get_image_rects(info[0])
                    area += sum(r.width * r.height for r in rects)
                except Exception:
                    pass
        except Exception:
            pass
        page_area = abs(pg.rect.width * pg.rect.height) or 1.0
        img_cover.append(min(1.0, area / page_area))
    print("页数：%d\n" % doc.page_count)

    fails: list[str] = []
    warns: list[str] = []

    # ---- 1. 空白页 ----
    print("[1] 空白页检查（文字量 + 图片占比，两者皆少才算空白）")
    blank = []
    for i, t in enumerate(pages):
        n = _body_chars(t)
        cover = img_cover[i]
        is_blank = n < BLANK_MIN_CHARS and cover < 0.05
        if is_blank:
            blank.append(i + 1)
        print("    page%-2d %5d 字符  图占比 %3.0f%%  %s"
              % (i + 1, n, cover * 100,
                 "(近乎空白)" if is_blank else ""))
    if blank:
        fails.append("空白页：%s" % blank)
        print("  FAIL  存在近乎空白的页：%s" % blank)
    else:
        print("  PASS  无空白页")

    # ---- 2. 孤立标题 ----
    print("\n[2] 章节标题孤立检查（标题在页尾、内容在下一页）")
    heading_re = re.compile(
        r"(?m)^\s*(\d+)\s+(\d+(?:\.\d+)*|\d)\s+(.+)$"
        r"|^\s*(摘要|参考文献|结果数据表|图表|AI 工具使用情况)\s*$")
    orphans: list[str] = []
    for i, t in enumerate(pages):
        lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
        if not lines:
            continue
        # 取页面最后若干行里是否出现标题
        tail = lines[-3:]
        for ln in tail:
            m = heading_re.match(ln)
            if not m:
                continue
            # 标题后本页剩余正文不足 ORPHAN_GAP_CHARS 字符
            after = t.split(ln)[-1]
            if len(after.strip()) < ORPHAN_GAP_CHARS:
                orphans.append("p%d: %s" % (i + 1, ln[:40]))
    if orphans:
        warns.append("孤立标题 %d 处" % len(orphans))
        print("  WARN  %d 处：\n      %s" % (len(orphans), "\n      ".join(orphans)))
    else:
        print("  PASS  无孤立标题")

    # ---- 3. 图/表与标题的相邻性 ----
    print("\n[3] 图文相邻性（图注与后续内容不应跨页割裂）")
    # 实测：XeLaTeX 把「图 1 标题」拆成两行——一行 `图1`、一行标题正文。
    # 因此两种形态都要认：编号单独成行 / 编号后直接跟标题。
    # ⚠️ 别加 `len(s) > 3` 这类条件：会把单独成行的 `图1`（2 字符）过滤掉。
    cap_re = re.compile(r"^\s*(图|表)\s*(\d+)\s*([.、:：]?\s*\S.*)?$")
    fig_caps = []
    for i, t in enumerate(pages):
        for ln in t.splitlines():
            s = ln.strip()
            if s and cap_re.match(s):
                fig_caps.append((i, s))
    print("    发现 %d 个图/表标题" % len(fig_caps))
    for i, ln in fig_caps[:12]:
        print("      p%d  %s" % (i + 1, ln[:52]))
    # 图注后一页应有其它内容，不应只剩图
    lonely = []
    for i, _ln in fig_caps:
        if _body_chars(pages[i]) < 200 and img_cover[i] < 0.25:
            lonely.append("p%d" % (i + 1))
    if lonely:
        warns.append("内容过少的图表页：%s" % lonely)
        print("  WARN  以下页几乎只有图表：%s" % lonely)
    else:
        print("  PASS  图表页均伴随正文")

    # ---- 4. 交叉引用连续性 ----
    print("\n[4] 交叉引用完整性")
    text = "\n".join(pages)
    # ⚠️ 未解析的引用在 PDF 里是 **`??`**（两个问号，LaTeX 对 `\ref` 的占位），
    #   不是三个。实测中只查 `???` 会**漏报**真实的未解析引用。
    #   只查 `??` 即可——`???` 也含 `??`，无需重复匹配。
    bad = re.findall(r"\?\?", text)
    if bad:
        fails.append("存在未解析的交叉引用 ??：%d 处" % len(bad))
        print("  FAIL  未解析引用 `??` × %d（\\ref 未解析）" % len(bad))
        for i, t in enumerate(pages, 1):
            if "??" in t:
                pos = t.find("??")
                snippet = t[max(0, pos - 40):pos + 20]
                print("      p%d: …%s…" % (i, snippet.replace("\n", " ")))
    else:
        print("  PASS  无未解析交叉引用")
    overfull = re.findall(r"Warning:\s*overfull\s+hbox", text, re.I)
    print("    （LaTeX 超框告警在 .log 中，不在 PDF 文本里）")

    print("\n" + "=" * 74)
    if fails:
        print("FAIL %d 项：%s" % (len(fails), "; ".join(fails)))
    if warns:
        print("WARN %d 项：%s" % (len(warns), "; ".join(warns)))
    if not fails and not warns:
        print("PASS  版面检查全部通过")
    print("=" * 74)
    return 1 if fails else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python verify_layout.py <paper.pdf>")
        raise SystemExit(2)
    raise SystemExit(check(Path(sys.argv[1])))
