#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 README 缺陷表统计「哪种验证手段抓到最多缺陷」。

用途：指导后续该把力气投在哪类验证上。
"""
from __future__ import annotations

import collections
import re
from pathlib import Path

RE = Path(__file__).resolve().parent.parent / "modemon" / "README.md"

#: 把表中的自由文本归一到 4 类可比的验证手段
NORMALIZE: list[tuple[str, str]] = [
    # 1) 真实执行（跑起来才暴露）
    ("真实流水线", "A. 真实执行"),
    ("真实运行", "A. 真实执行"),
    ("真实闭环运行", "A. 真实执行"),
    ("端到端运行", "A. 真实执行"),
    # 2) 看/查产物（编译出来、渲染出来、看一眼）
    ("看渲染结果", "B. 检查渲染/编译产物"),
    ("真实编译产物检查", "B. 检查渲染/编译产物"),
    ("真实编译", "B. 检查渲染/编译产物"),
    ("版面校验", "B. 检查渲染/编译产物"),
    # 3) 测试（单测/集成/回归）
    ("单测", "C. 测试"),
    ("集成测试", "C. 测试"),
    ("回归测试", "C. 测试"),
    # 4) 自查
    ("自查发现", "D. 自查 / 复核"),
]


def main() -> int:
    t = RE.read_text(encoding="utf-8")
    sec = t[t.index("### 7.2 "):t.index("### 7.2b")]

    # ⚠️ 逐行按「|」切分并取**最后一列**——直接用正则会被单元格里的
    #   转义管道符（`\|符号\|含义\|`）骗到，实测漏过 1 行。
    rows: list[tuple[str, str, str]] = []
    for line in sec.splitlines():
        if not re.match(r"^\|\s*\d+\s*\|", line):
            continue
        num = re.match(r"^\|\s*(\d+)\s*\|", line).group(1)     # type: ignore[union-attr]
        body = line.strip().strip("|")
        cells = body.split("|")
        how = cells[-1].strip().replace("**", "")
        desc = cells[1].strip() if len(cells) > 1 else ""
        rows.append((num, desc, how))

    print("  抽到 %d 行" % len(rows))
    missing = [n for n in (str(i) for i in range(1, len(rows) + 1)) if n not in {r[0] for r in rows}]
    if missing:
        print("  ⚠️ 编号缺失:", missing)

    def norm(how: str) -> str:
        for key, val in NORMALIZE:
            if key in how:
                return val
        return "E. 未分类：" + how

    cats: dict[str, list[str]] = collections.defaultdict(list)
    for num, desc, how in rows:
        cats[norm(how)].append(num)

    total = len(rows)
    print()
    print("  === 按验证手段统计（%d 项）===" % total)
    for k in sorted(cats):
        v = cats[k]
        bar = "█" * len(v)
        print("    %-22s %2d 项 (%2.0f%%)  %s" % (k, len(v), len(v) * 100.0 / total, bar))

    print()
    print("  === 明细 ===")
    for k in sorted(cats):
        print("    %s: #%s" % (k, ", ".join(cats[k])))

    # 交叉：A 类（真实执行）与 B 类（检查产物）合计占比
    ab = len(cats.get("A. 真实执行", [])) + len(cats.get("B. 检查渲染/编译产物", []))
    print()
    print("  ★ A+B（必须真跑 + 必须看产物）= %d/%d = %.0f%%" % (ab, total, ab * 100.0 / total))
    print("  ★ C（测试能抓到）= %d/%d = %.0f%%" % (len(cats.get("C. 测试", [])), total,
                                                  len(cats.get("C. 测试", [])) * 100.0 / total))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
