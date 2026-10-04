"""运行报告：把一次 run 的完整情况汇总成人类可读的 Markdown。

用途：复盘、存档、分享。包含环节与评审轨迹、门禁结论、产物清单、用量统计。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

SKIP_DIRS = {"prompts", "logs", "code"}
SKIP_SUFFIXES = {".aux", ".log", ".out", ".toc", ".bak"}


def _stage_section(rec: dict[str, Any]) -> list[str]:
    lines = [f"### {rec.get('id')} · {rec.get('title')}", ""]
    status = rec.get("status")
    badge = {"done": "✅ 完成", "needs_work": "⚠️ 完成但未达标", "running": "🔄 进行中"}.get(status, str(status))
    lines.append(f"- 状态：{badge}　耗时：{rec.get('duration_s', '')}s　执行轮次：{rec.get('rounds', '')}")

    reviews = rec.get("reviews") or []
    if reviews:
        trail = " → ".join(
            f"第{i}轮 {r.get('total')}/10（{'通过' if r.get('verdict') == 'pass' else '需改'}）"
            for i, r in enumerate(reviews, 1)
        )
        lines.append(f"- 评审轨迹：{trail}")

    outputs = rec.get("outputs") or []
    if outputs:
        lines.append(f"- 产物：{', '.join(outputs[:8])}")

    exec_results = rec.get("exec_results") or []
    for item in exec_results:
        flag = "成功" if item.get("returncode") == 0 else f"失败(exit={item.get('returncode')})"
        lines.append(f"- 执行 `{item.get('file')}` → {flag}（{item.get('duration_s')}s）")
        payload = item.get("result_json")
        if isinstance(payload, dict):
            for key, value in list(payload.items())[:6]:
                lines.append(f"  - {key} = {value}")

    if reviews:
        must_fix = (reviews[-1].get("must_fix") or [])[:6]
        if must_fix:
            lines.append("- 待改进（最后一轮评审）：")
            lines += [f"  {i}. {item}" for i, item in enumerate(must_fix, 1)]

    lines.append("")
    return lines


def _gate_section(state: dict[str, Any]) -> list[str]:
    lines = ["## 质量门禁", ""]

    compile_info = state.get("compile") or {}
    if compile_info:
        lines.append(f"- **编译**：{compile_info.get('status')} — {compile_info.get('message', '')}")
        if compile_info.get("pdf"):
            lines.append(f"  - PDF：`{compile_info['pdf']}`（{compile_info.get('pdf_bytes', 0)} 字节）"
                         f"{'，自动回修 ' + str(compile_info.get('rounds')) + ' 轮' if compile_info.get('rounds') else ''}")
    else:
        lines.append("- **编译**：未执行")

    prov = state.get("provenance") or {}
    if prov:
        lines.append(f"- **数值溯源**：{prov.get('matched')}/{prov.get('total')} 命中"
                     f"（{prov.get('ratio', 0) * 100:.0f}%），证据 {prov.get('evidence_count')} 个数")
        unmatched = prov.get("unmatched") or []
        for item in unmatched[:8]:
            lines.append(f"  - ⚠️ `{item.get('value')}`（{item.get('file')}）：…{item.get('context', '')[:70]}…")
    else:
        lines.append("- **数值溯源**：未执行")

    comp = state.get("compliance") or {}
    if comp:
        lines.append(f"- **合规检查**：{comp.get('verdict')}（不通过 {comp.get('failed')} 项 / 提醒 {comp.get('warned')} 项）")
        for item in comp.get("items") or []:
            if item.get("status") != "pass":
                mark = "❌" if item["status"] == "fail" else "⚠️"
                lines.append(f"  - {mark} {item.get('name')}：{item.get('detail')}")
    else:
        lines.append("- **合规检查**：未执行")

    lines.append("")
    return lines


def _inventory(run_root: Path) -> list[str]:
    lines = ["## 产物清单", ""]
    for path in sorted(run_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(run_root)
        if rel.parts[0] in SKIP_DIRS or path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if rel.name in ("report.json", "REPORT.md"):
            continue
        lines.append(f"- `{rel.as_posix()}`（{path.stat().st_size:,} 字节）")
    lines.append("")
    return lines


def build_markdown(run_root: Path, state: dict[str, Any]) -> str:
    run_root = Path(run_root)
    usage = state.get("usage") or {}
    models = state.get("models") or {}

    lines = [
        f"# 运行报告 · {state.get('run_id', run_root.name)}",
        "",
        f"- 竞赛：{state.get('competition')}",
        f"- 状态：**{state.get('status')}**",
        f"- 创建：{state.get('created_at')}　更新：{state.get('updated_at')}",
        f"- 模型：执行者 `{models.get('executor')}` / 评审者 `{models.get('reviewer')}`"
        + ("　（离线 Mock 模式）" if state.get("mock") else ""),
        f"- 赛题文件：`{state.get('problem_file')}`",
        f"- 用量：{usage.get('calls', 0)} 次调用，输入 {usage.get('prompt_tokens', 0)} / "
        f"输出 {usage.get('completion_tokens', 0)} tokens"
        + (f"，估算成本 ${usage['cost_usd']:.4f}" if usage.get("cost_usd") else "（价格表未收录该模型）"),
        f"- 报告生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 环节与评审轨迹",
        "",
    ]

    for rec in state.get("stages") or []:
        lines += _stage_section(rec)

    lines += _gate_section(state)
    lines += _inventory(run_root)

    lines += [
        "## 学术诚信提示",
        "",
        "本报告由自动化流程生成。**论文中的数据、引用与结论必须人工复核**；",
        "参加竞赛或投稿请遵守相应的学术规范，最终责任在使用者本人。",
        "",
    ]
    return "\n".join(lines)


def write_report(run_root: Path, state: dict[str, Any], *, filename: str = "REPORT.md") -> Path:
    target = Path(run_root) / filename
    target.write_text(build_markdown(run_root, state), encoding="utf-8")
    return target
