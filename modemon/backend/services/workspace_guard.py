"""工作区守卫：在把工作区交给 agent 之前，消除「环境注入能力」的面。

要解决的问题
------------
蓝方在 `chat_tool_policy` 的源码注释里记录了他们实测出的攻击面，并**自认无法修复**：

    实测（Phase 0）：不加它时，【工作区根目录的 .mcp.json 会被自动加载】。
    我在工作区放了个假 MCP server，它连上了、工具进了主会话：
    就等于给主会话注入了任意能力。
    ...
    黑名单挡不住（名字不可预知），全在审计闸外面。

而工作区**正是用户上传文件落地的地方**——所以这不是理论风险。

本守卫采取**纵深防御**
----------------------
1. **能力层**（首选）：Claude Code 的 `--strict-mcp-config` 会忽略一切环境 MCP 配置。
   这是事前阻断，由适配器能力 `mcp_pinning` 保证。
2. **文件层**（兜底，与运行时无关）：本守卫在运行前扫描工作区，
   发现可被自动加载的配置来源就**隔离**它（移到隔离区），并记录处置事实。

第 2 层对**所有**运行时都生效，包括不具备 `mcp_pinning` 能力的那些——
这正是"能力协商 + 降级"要落地的地方。
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

#: 会被 agent 运行时自动加载、从而注入能力的文件名。
#: 依据：Claude Code / Codex / 多数 agent CLI 的约定。
INJECTABLE_BASENAMES = (
    ".mcp.json",
    "mcp.json",
    ".mcp-config.json",
    ".codex/config.toml",
    ".cursor/mcp.json",
)

#: 会被自动读取为指令的文件（可被用来做提示注入）
INSTRUCTION_BASENAMES = (
    "CLAUDE.md",
    "AGENTS.md",
    ".cursorrules",
)

#: 扫描时跳过的目录
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "runtime", "dist", ".cache", "figures_out",
}

#: 工作区顶层被允许的已知产物/目录（用于「多余文件」提示，不作阻断）
EXPECTED_TOP = {
    "PROBLEM_ANALYSIS.md", "MODELING_REPORT.md", "RESULTS.md",
    "COMP_REVIEW.md", "PAPER_PLAN.md", "ASSETS_INVENTORY.md", "ASSETS_CONFLICTS.md",
    "code", "figures", "paper", "data", "refine-logs", "user_data",
    "CLAUDE.md", "RUN.md",
}


@dataclass
class Finding:
    kind: str            # injectable_config | instruction_file | stray_executable
    path: Path
    detail: str = ""


@dataclass
class GuardReport:
    ok: bool = True
    findings: list[Finding] = field(default_factory=list)
    quarantined: list[tuple[Path, Path]] = field(default_factory=list)
    quarantine_dir: Optional[Path] = None
    degraded: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(f.kind == "injectable_config" for f in self.findings) and not self.quarantined

    def summary(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "blocked": self.blocked,
            "findings": [{"kind": f.kind, "path": str(f.path), "detail": f.detail}
                         for f in self.findings],
            "quarantined": [{"src": str(a), "dst": str(b)} for a, b in self.quarantined],
            "quarantine_dir": str(self.quarantine_dir) if self.quarantine_dir else None,
            "degraded": list(self.degraded),
        }


def scan_workspace(workspace: Path, *, max_depth: int = 6) -> list[Finding]:
    """扫描工作区中可被自动加载的配置与指令文件。

    只扫描**工作区内部**——不会跟着符号链接跑到系统目录去。
    """
    findings: list[Finding] = []
    ws = Path(workspace).resolve()
    if not ws.is_dir():
        return findings

    injectable = {n.lower() for n in INJECTABLE_BASENAMES}
    instruct = {n.lower() for n in INSTRUCTION_BASENAMES}

    for path in ws.rglob("*"):
        try:
            rel = path.relative_to(ws)
        except ValueError:
            continue
        if len(rel.parts) > max_depth:
            continue
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        # 不跟随符号链接/目录联接，避免被诱导到工作区之外
        if path.is_symlink():
            findings.append(Finding("stray_symlink", path, "符号链接（不跟随）"))
            continue
        if not path.is_file():
            continue

        name = path.name.lower()
        posix_rel = rel.as_posix().lower()
        if name in injectable or any(posix_rel.endswith(p) for p in injectable):
            findings.append(
                Finding("injectable_config", path,
                        "该文件会被 agent 运行时自动加载，可用于注入任意能力")
            )
        elif name in instruct and rel.parts and len(rel.parts) <= 2:
            findings.append(
                Finding("instruction_file", path,
                        "指令文件：内容会成为模型上下文，需确认为项目自身产物")
            )
    return findings


def guard_workspace(
    workspace: Path,
    *,
    quarantine_root: Optional[Path] = None,
    isolate: bool = True,
) -> GuardReport:
    """运行前守卫。

    Args:
        workspace: 工作区根目录。
        quarantine_root: 隔离区根目录；默认放在工作区**之外**
            （`<workspace>.guard-quarantine`），避免被 agent 再次读到。
        isolate: True 时把可注入配置**移动**到隔离区；False 时仅报告并阻断。

    Returns:
        GuardReport。`blocked` 为 True 表示存在注入面且未被隔离，**必须拒绝运行**。
    """
    report = GuardReport()
    report.findings = scan_workspace(workspace)

    injectables = [f for f in report.findings if f.kind == "injectable_config"]
    if not injectables:
        return report

    if not isolate:
        report.ok = False
        report.degraded.append("workspace_guard: 未隔离可注入配置，已阻断运行")
        return report

    root = quarantine_root or workspace.parent / (workspace.name + ".guard-quarantine")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    report.quarantine_dir = root

    stamp = time.strftime("%Y%m%d-%H%M%S")
    for f in injectables:
        try:
            rel = f.path.relative_to(Path(workspace).resolve())
        except ValueError:
            rel = Path(f.path.name)
        dst = root / stamp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(f.path), str(dst))
        report.quarantined.append((f.path, dst))
        report.degraded.append(f"quarantined:{rel.as_posix()}")
    return report


def write_workspace_context(
    workspace: Path,
    *,
    artifacts: Iterable[str] = (),
    figure_descriptions: Optional[dict[str, str]] = None,
    budget_chars: int = 6000,
) -> Path:
    """生成工作区上下文文件（`CLAUDE.md`）。

    这是蓝方验证有效的低成本上下文工程手法：
    「在工作区生成 CLAUDE.md，为 Claude CLI 提供项目上下文」
    「扫描工作区中的图片文件，用 vision LLM 描述内容，追加到 CLAUDE.md 正文中」

    这里做**字符预算**，避免上下文无限膨胀（蓝方遇到的是 110K tokens 导致输出截断）。
    """
    ws = Path(workspace)
    lines = [
        "# 工作区上下文",
        "",
        "本文件由 modemon 生成，供 agent 了解当前工作区状态。",
        "",
    ]
    if artifacts:
        lines += ["## 已有产物", ""]
        for a in sorted(set(artifacts)):
            p = ws / a
            mark = "✓" if p.exists() else "✗"
            size = f"{p.stat().st_size}B" if p.exists() and p.is_file() else ""
            lines.append(f"- {mark} `{a}` {size}")
        lines.append("")

    if figure_descriptions:
        lines += ["## 图表说明", ""]
        for name, desc in list(figure_descriptions.items())[:50]:
            lines.append(f"- `{name}`: {desc[:100]}")   # 单图描述截断
        lines.append("")

    text = "\n".join(lines)
    if len(text) > budget_chars:
        text = text[:budget_chars] + "\n\n…（上下文已按预算截断）\n"

    out = ws / "CLAUDE.md"
    out.write_text(text, encoding="utf-8")
    return out


__all__ = [
    "Finding", "GuardReport", "scan_workspace", "guard_workspace",
    "write_workspace_context", "INJECTABLE_BASENAMES", "INSTRUCTION_BASENAMES",
]
