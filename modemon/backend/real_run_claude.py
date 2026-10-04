#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真实端到端验证：用本机 Claude Code 跑通一个完整步骤。

这是**唯一会真实调用模型**的测试，因此：
  - 只跑最便宜的步骤（comp-review，主产物阈值 40 字节）
  - 用 --max-budget-usd 硬性限制花费
  - 结果写入 reports 供留档

用法：
    python tools/real_run_claude.py [--budget 0.30]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

from services import agent_runtime as ar  # noqa: E402
from services import step_runner as sr  # noqa: E402
from services import workflow_engine as we  # noqa: E402

OUT = Path(r"E:\02_Installers\DailyApps\Modex-MH-Agent-RE\reports\19-real-claude-run.md")


def build_workspace(root: Path) -> Path:
    """造一个有内容的假工作区，让评审步骤有东西可评。"""
    ws = root / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "MODELING_REPORT.md").write_text(
        "# 建模报告\n\n"
        "## 1. 问题重述\n"
        "某工厂需在给定约束下最小化运输成本。\n\n"
        "## 2. 模型假设\n"
        "- 供需平衡\n- 运输成本与运量成正比\n\n"
        "## 3. 模型建立\n"
        "设 x_ij 为从 i 到 j 的运量，目标函数为 min sum c_ij * x_ij，\n"
        "约束为各产地供给上限与各销地需求下限。\n\n"
        "## 4. 求解结果\n"
        "最优成本 1234 元。\n",
        encoding="utf-8",
    )
    (ws / "PROBLEM_ANALYSIS.md").write_text("# 赛题分析\n目标与约束已列明。\n", encoding="utf-8")
    return ws


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=0.30)
    ap.add_argument("--runtime", default="claude-code")
    args = ap.parse_args()

    print("=" * 74)
    print("真实端到端：Claude Code 跑 comp-review 步骤")
    print("=" * 74)

    rt = ar.resolve_runtime(args.runtime)
    print("运行时      :", rt.capabilities.name)
    print("可用        :", rt.is_available())
    print("预算上限    :", args.budget, "USD")
    print("能力        :", json.dumps(rt.capabilities.as_dict(), ensure_ascii=False))
    print()

    with tempfile.TemporaryDirectory(prefix="modemon-real-") as td:
        ws = build_workspace(Path(td))
        print("工作区      :", ws)
        print("已有产物    :", sorted(p.name for p in ws.iterdir()))
        print()

        req = sr.StepRunRequest(
            workflow_id="real-1",
            skill_name="comp-review",
            workspace=ws,
            template="comp_cumcm",
            language="zh",
            runtime=args.runtime,
            max_budget_usd=args.budget,
            strict=False,          # 允许降级，但会如实记录
            extra_prompt=(
                "请只用中文输出一份简短的核心逻辑对抗复核意见（200 字以内），"
                "写入 COMP_REVIEW.md。指出建模与求解中最可能被评委质疑的 2 个点。"
            ),
        )

        t0 = time.monotonic()
        events = []
        outcome = None
        async for item in sr.run_step(req):
            if isinstance(item, sr.StepRunOutcome):
                outcome = item
            else:
                events.append(item)
                if item.kind in (ar.EventKind.STARTED, ar.EventKind.TOOL,
                                 ar.EventKind.ERROR):
                    print(f"  [{item.kind.value:9}] {item.text[:90]}")
        assert outcome is not None

        print()
        print("-" * 74)
        print("结果")
        print("-" * 74)
        print("  ok          :", outcome.ok)
        print("  runtime     :", outcome.runtime)
        print("  事件数      :", outcome.event_count)
        print("  会话 id     :", outcome.session_id)
        print("  花费 USD    :", outcome.cost_usd)
        print("  tokens in/out:", outcome.tokens_in, "/", outcome.tokens_out)
        print("  耗时 s      :", outcome.duration_s)
        print("  降级项      :", outcome.degraded)
        print("  守卫        :", json.dumps(outcome.guard, ensure_ascii=False))
        print("  错误码      :", outcome.error_code or "(无)")
        print("  错误        :", outcome.error or "(无)")
        print()
        print("  质量门：")
        for g in outcome.gates:
            print("    -", g.get("gate"), "ok=", g.get("ok"),
                  ("| " + str(g.get("reason"))[:80]) if g.get("reason") else "")

        produced = ws / "COMP_REVIEW.md"
        print()
        print("  产物 COMP_REVIEW.md 存在:", produced.exists(),
              ("(%d 字节)" % produced.stat().st_size) if produced.exists() else "")
        body = produced.read_text(encoding="utf-8") if produced.exists() else ""
        print("  产物前 400 字：")
        print("    " + body[:400].replace("\n", "\n    "))

        # 写报告
        lines = [
            "# 真实端到端验证：Claude Code 执行 comp-review 步骤",
            "",
            "> 本文件由 `tools/real_run_claude.py` 生成，是**唯一真实调用模型**的验证。",
            "> 使用本机 `~/.claude/settings.json` 中已配置的端点（第三方 Anthropic 兼容网关）。",
            "> **出于安全考虑，本报告不记录任何凭据信息。**",
            "",
            "## 运行时能力声明",
            "",
            "```json",
            json.dumps(rt.capabilities.as_dict(), ensure_ascii=False, indent=1),
            "```",
            "",
            "## 请求",
            "",
            f"- 步骤：`comp-review`（主产物阈值 {we.min_size_for('comp-review')} 字节）",
            f"- 模板：`comp_cumcm`（页数参考 30，advisory）",
            f"- 预算上限：{args.budget} USD",
            "- 严格模式：关闭（允许降级，但降级事实会记录）",
            "",
            "## 结果",
            "",
            "| 项 | 值 |",
            "|---|---|",
            f"| 成功 | **{outcome.ok}** |",
            f"| 运行时 | `{outcome.runtime}` |",
            f"| 事件数 | {outcome.event_count} |",
            f"| 会话 id | `{outcome.session_id}` |",
            f"| 花费 (USD) | {outcome.cost_usd} |",
            f"| tokens in / out | {outcome.tokens_in} / {outcome.tokens_out} |",
            f"| 耗时 (s) | {outcome.duration_s} |",
            f"| 能力降级 | {outcome.degraded or '无'} |",
            f"| 错误码 | `{outcome.error_code}` |",
            "",
            "## 工作区守卫",
            "",
            "```json",
            json.dumps(outcome.guard, ensure_ascii=False, indent=1),
            "```",
            "",
            "## 质量门",
            "",
            "| 门 | 通过 | 说明 |",
            "|---|---|---|",
        ]
        for g in outcome.gates:
            lines.append("| `%s` | %s | %s |" % (
                g.get("gate"), g.get("ok"), str(g.get("reason") or "")[:120]))
        lines += [
            "",
            f"## 产物 `COMP_REVIEW.md`",
            "",
            f"存在：**{produced.exists()}**"
            + (f"（{produced.stat().st_size} 字节）" if produced.exists() else ""),
            "",
            "```markdown",
            body[:3000],
            "```",
            "",
            "## 事件序列（前 30 条）",
            "",
            "| # | kind | 文本（截断） |",
            "|---|---|---|",
        ]
        for i, e in enumerate(events[:30], 1):
            lines.append("| %d | `%s` | %s |" % (
                i, e.kind.value, e.text[:100].replace("|", "\\|").replace("\n", " ")))
        lines.append("")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text("\n".join(lines), encoding="utf-8")
        print()
        print("报告已写入:", OUT)

        return 0 if outcome.ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
