#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手动跑 paper-figure-drawio 步骤，从原始 stream-json 里 dump **工具入参**。

我的适配器刻意不持久化工具入参（防泄露），但排查卡死时必须看到它们。
本脚本绕过适配器，直接抓原始流。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

from services import tool_env as te  # noqa: E402
from services import workflow_engine as we  # noqa: E402

WS = Path(r"E:\02_Installers\DailyApps\Modex-MH-Agent-RE\.drawio-probe\ws")
EXE = Path(r"E:\02_Installers\DailyApps\Modex-MH-Agent\runtime\node"
           r"\node_modules\@anthropic-ai\claude-code\bin\claude.exe")

PROMPT = """# 任务：流程与架构图绘制

当前步骤技能：`paper-figure-drawio`

## 范围（严格遵守）

**本步骤只做一件事：产出下面列出的文件。**

- 不要提前执行后续步骤的工作；
- 不要为了「先摸清情况」反复运行命令；读必要的文件即可，**尽早开始写产物**；
- 完成后立即结束。

## 工作区

工作目录：`%s`

**所有产出文件都必须写在这个目录下**。

## 必须产出

- `figures/latex_includes.tex`

主产物：`figures/`  最低体量要求：**500 字节**

补充要求：画流程图/架构图，命名以 `tikz_` 开头，并在 FIGURE_MANIFEST.md 登记。
""" % WS


def main() -> int:
    env, _rep = te.prepare_child_env()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    cmd = [
        str(EXE), "-p", PROMPT,
        "--output-format", "stream-json", "--verbose",
        "--bare",
        "--permission-mode", "bypassPermissions",
        "--mcp-config", '{"mcpServers": {}}', "--strict-mcp-config",
        "--max-budget-usd", "1.20",
        "--model", "mimo-v2.6-flash[1M]",
    ]
    print("启动（限时 8 分钟，只看工具入参）…")
    t0 = time.monotonic()
    p = subprocess.Popen(cmd, cwd=str(WS), stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, env=env, text=True,
                         encoding="utf-8", errors="replace")

    tools: list[tuple[str, str]] = []
    try:
        for line in p.stdout:  # type: ignore[union-attr]
            line = line.strip()
            if not line:
                continue
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            if m.get("type") == "assistant":
                for b in (m.get("message") or {}).get("content", []):
                    if b.get("type") == "tool_use":
                        inp = b.get("input") or {}
                        cmd_txt = (inp.get("command") or inp.get("file_path")
                                   or json.dumps(inp, ensure_ascii=False))
                        tools.append((b.get("name", ""), str(cmd_txt)))
                        print("  [%5.1fs] %-8s %s"
                              % (time.monotonic() - t0, b.get("name", ""),
                                 str(cmd_txt)[:160]))
            if m.get("type") == "result":
                print("\n结果: subtype=%s is_error=%s cost=%.4f"
                      % (m.get("subtype"), m.get("is_error"),
                         m.get("total_cost_usd") or 0))
                break
            if time.monotonic() - t0 > 480:
                print("\n!! 8 分钟到，主动中止")
                p.kill()
                break
    finally:
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()

    print("\n=== 共 %d 次工具调用 ===" % len(tools))
    print("=== figures/ 现状 ===")
    fig = WS / "figures"
    if fig.is_dir():
        for f in sorted(fig.iterdir()):
            if f.is_file():
                print("  %9d B  %s" % (f.stat().st_size, f.name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
