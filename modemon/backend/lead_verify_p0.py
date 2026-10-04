#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lead 验收：P0 导出安全（不覆盖 agent 产物 + 空正文不报成功）。"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

from services import latex_export as lx  # noqa: E402

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
        print("  FAIL  %s  %s" % (name, detail[:140]))


AGENT_TEX = r"""% !TEX program = xelatex
\documentclass[12pt,a4paper]{ctexart}
\usepackage{graphicx}
\begin{document}
\section{问题重述}
某物流公司拥有 3 个仓库与 4 个配送点，需要确定最优调运方案。

\section{模型建立}
以总运输成本最小为目标，建立线性规划模型。
\end{document}
"""


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else ""


def main() -> int:
    print("=" * 74)
    print("Lead 验收：P0 导出安全")
    print("=" * 74)

    # --- 场景 1：已有 agent 直出的成品 main.tex，导出不得摧毁它 ---
    print("\n[1] 导出不得摧毁 agent 的成品 .tex")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "figures").mkdir()
        (ws / "paper").mkdir()
        (ws / "figures" / "all_results.json").write_text(
            json.dumps({"scenario1": {"Z0": 775.0, "iterations": 3}}), encoding="utf-8")
        tex = ws / "paper" / "main.tex"
        tex.write_text(AGENT_TEX, encoding="utf-8")
        h0 = sha(tex)
        n0 = len(AGENT_TEX.encode())

        r = lx.export_latex(ws, template="comp_cumcm", language="zh",
                            title="t", compile_pdf=False)

        # agent 的成品必须**仍在且未被改写**
        still = tex.is_file() and sha(tex) == h0
        check("**agent 成品仍在且逐字节未变**", still,
              "size %s -> %s" % (n0, tex.stat().st_size if tex.is_file() else -1))
        print("      ok=%s body_chars=%s notes=%s"
              % (r.ok, getattr(r, "body_chars", "?"),
                 [str(x)[:70] for x in (getattr(r, "notes", []) or [])[:2]]))

    # --- 场景 2：空工作区 → 不得报成功 ---
    print("\n[2] 空正文导出不得报成功")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        r = lx.export_latex(ws, template="comp_cumcm", language="zh",
                            title="t", compile_pdf=False)
        check("**ok is False**", r.ok is False, "ok=%s" % r.ok)
        check("给出可读 error", bool(getattr(r, "error", "")),
              str(getattr(r, "error", ""))[:120])

    # --- 场景 3：preamble 不再重复引入 caption ---
    print("\n[3] preamble 宏包不重复")
    from services import typography as ty
    p = lx.build_preamble(ty.resolve_profile("comp_cumcm"), language="zh")
    check("caption 只引入 1 次", p.count("\\usepackage{caption}") == 1,
          str(p.count("\\usepackage{caption}")))

    print("\n" + "=" * 74)
    print("PASS %d / FAIL %d" % (PASS, FAIL))
    for f in FAILURES:
        print("  -", f)
    print("=" * 74)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
