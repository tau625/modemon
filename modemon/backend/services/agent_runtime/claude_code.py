"""Claude Code CLI 适配器。

接口依据（实测 `claude --help`，v2.1.132）：

    claude -p "<prompt>" --output-format stream-json --verbose
           --effort <low|medium|high|xhigh|max>
           --model <m> --allowedTools ... --disallowedTools ...
           --tools ... --add-dir ... --max-budget-usd <n>
           --mcp-config <path> --strict-mcp-config
           --bare --settings <json>
           --resume <session-id> | --session-id <uuid> --fork-session

★ 关键：`--strict-mcp-config`
---------------------------
其官方说明为「Only use MCP servers from --mcp-config, ignoring all other MCP
configurations」。这正是蓝方在 `chat_tool_policy` 中**自认无法解决**的问题：

    实测（Phase 0）：不加它时，【工作区根目录的 .mcp.json 会被自动加载】。
    我在工作区放了个假 MCP server，它连上了、工具进了主会话。

蓝方的应对是「每次起主会话都对账一次实际清单，发现白名单外的工具立刻告警」——
即**事后检测**。而 `--strict-mcp-config` 是**事前阻断**。
本适配器默认开启它，把这类攻击面从"补偿性控制"提升为"结构性消除"。

`--tools` 与 `--allowedTools` 的区别
-----------------------------------
蓝方实测结论：「`--allowedTools` 不是工具挂载白名单，不能用它移除内建工具；
请求 7 个白名单工具，CLI 实际给了 27 个」。
本适配器因此**同时**使用 `--tools`（限定内建工具集合）与 `--disallowedTools`
（显式屏蔽），并把 `--allowedTools` 只当作"提示"而非安全边界。
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import time
from pathlib import Path
from typing import AsyncIterator, Optional

from .base import (
    AgentRuntime,
    Capabilities,
    EventKind,
    RunEvent,
    RunSpec,
    RuntimeUnavailable,
)

#: 允许的思考强度档位（实测自 --help）
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")

#: 权限模式档位（实测自 --help）
PERMISSION_MODES = ("acceptEdits", "auto", "bypassPermissions", "default", "dontAsk", "plan")

#: 子进程流读取上限。
#:
#: asyncio 默认只有 64 KiB，而 agent 的一行 JSON 很容易超过它
#: （长工具结果、长模型输出都会挤在一行里）。实测会抛
#: `ValueError: Separator is found, but chunk is longer than limit`
#: 并让整个步骤中断。这里给到 32 MiB。
STREAM_LIMIT = 32 * 1024 * 1024


def find_executable() -> Optional[str]:
    """按优先级查找 claude 可执行文件。

    优先级刻意把**随包的真实 `.exe`** 排在 PATH 之前：
    npm 全局安装通常会留下 `claude.CMD` 包装脚本，而 `.CMD` 经 `cmd.exe` 传参
    会引入引号/花括号被改写的风险（例如 `--mcp-config` 的 JSON 参数）。
    直接调用 PE 二进制可以完全绕开这一层。
    """
    env = os.environ.get("MODEMON_CLAUDE_BIN")
    if env and Path(env).is_file():
        return env

    # 1) 随包分发的真实二进制
    base = Path(os.environ.get("MODEMON_MH_ROOT", r"E:\02_Installers\DailyApps\Modex-MH-Agent"))
    bundled = (base / "runtime" / "node" / "node_modules" / "@anthropic-ai"
               / "claude-code" / "bin" / ("claude.exe" if platform.system() == "Windows" else "claude"))
    if bundled.is_file():
        return str(bundled)

    # 2) PATH 中的真实 exe
    for cand in ("claude.exe", "claude") if platform.system() == "Windows" else ("claude",):
        which = shutil.which(cand)
        if which and not which.lower().endswith(".cmd"):
            return which

    # 3) 最后才接受 .CMD / .ps1 包装脚本
    which = shutil.which("claude")
    return which


def find_node() -> Optional[str]:
    env = os.environ.get("MODEMON_NODE_BIN")
    if env and Path(env).is_file():
        return env
    which = shutil.which("node")
    if which:
        return which
    bundled = Path(r"E:\02_Installers\DailyApps\Modex-MH-Agent") / "runtime" / "node" / "node.exe"
    return str(bundled) if bundled.is_file() else None


class ClaudeCodeRuntime(AgentRuntime):
    def __init__(self, executable: Optional[str] = None) -> None:
        self._exe = executable or find_executable()

    # -- 能力 ---------------------------------------------------------------

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(
            name="claude-code",
            streaming=True,
            session_resume=True,
            effort_levels=EFFORT_LEVELS,
            model_selection=True,
            tool_allowlist=True,
            tool_denylist=True,
            mcp_pinning=True,            # --strict-mcp-config
            budget_limit=True,           # --max-budget-usd
            structured_output=True,      # --json-schema
            extra_dirs=True,             # --add-dir
            skip_ambient_config=True,    # --bare
            permission_modes=PERMISSION_MODES,
            model_fallback=True,         # --fallback-model
        )

    def is_available(self) -> bool:
        return bool(self._exe and Path(self._exe).is_file())

    # -- 命令构造（可独立审计） ---------------------------------------------

    def build_command(self, spec: RunSpec) -> list[str]:
        if not self.is_available():
            raise RuntimeUnavailable("claude 可执行文件未找到")

        cmd: list[str] = [str(self._exe), "-p", spec.prompt,
                          "--output-format", "stream-json", "--verbose"]

        if spec.skip_ambient_config:
            # 跳过 hooks / 插件 / CLAUDE.md 自动发现 / keychain 读取
            # 实测副作用（有益）：工具集收敛为 Bash/Edit/Read，攻击面更小
            cmd += ["--bare"]

        # ★ 权限模式：`-p` 非交互模式下**默认拒绝写文件**。
        #   实测：不加此项时 agent 完成了评审却无法落盘，
        #   只能把结论打在 stdout 上，导致质量门判为「主产物缺失」。
        mode = spec.permission_mode
        if mode and mode in PERMISSION_MODES:
            cmd += ["--permission-mode", mode]

        if spec.system_prompt:
            cmd += ["--append-system-prompt", spec.system_prompt]

        if spec.model:
            cmd += ["--model", spec.model]
        # ★ 备用模型：额度耗尽/过载时由 CLI **在同一次调用内**自动切换，
        #   比在上一层做重试更快也更省上下文。
        if spec.fallback_model:
            cmd += ["--fallback-model", spec.fallback_model]
        if spec.effort and spec.effort in EFFORT_LEVELS:
            cmd += ["--effort", spec.effort]

        # ★ MCP 隔离：钉死在显式配置上，忽略其它一切 MCP 配置来源
        #
        # ⚠️ 实测坑：空配置必须是 `{"mcpServers": {}}`，**不能是 `{}`**。
        #    传 `{}` 会得到：
        #        Error: Invalid MCP configuration:
        #        mcpServers: Does not adhere to MCP server configuration schema
        #    表现为 agent 启动异常、无法写文件、退出码 1——
        #    症状像"权限问题"，实际是配置 schema 不合法。
        if spec.isolate_mcp:
            cfg = str(spec.mcp_config) if spec.mcp_config else '{"mcpServers": {}}'
            cmd += ["--mcp-config", cfg]
            cmd += ["--strict-mcp-config"]

        # ★ 工具策略：用 --tools 限定内建集合（--allowedTools 不是白名单，
        #   蓝方实测「请求 7 个实际给 27 个」，故不作为安全边界）
        if spec.allowed_tools:
            cmd += ["--tools", ",".join(spec.allowed_tools)]
        elif spec.allowed_tools is not None:
            cmd += ["--tools", ""]          # 显式空列表 = 禁用全部内建工具
        if spec.disallowed_tools:
            cmd += ["--disallowedTools", " ".join(spec.disallowed_tools)]

        for d in spec.add_dirs:
            cmd += ["--add-dir", str(d)]

        if spec.max_budget_usd is not None:
            cmd += ["--max-budget-usd", str(spec.max_budget_usd)]
        if spec.output_json_schema:
            cmd += ["--json-schema", spec.output_json_schema]
        if spec.resume_session_id:
            cmd += ["--resume", spec.resume_session_id]
        return cmd

    # -- 执行 ---------------------------------------------------------------

    async def run(self, spec: RunSpec) -> AsyncIterator[RunEvent]:
        cmd = self.build_command(spec)
        env = {**os.environ, **spec.env, "CLAUDE_CODE_SIMPLE": "1" if spec.skip_ambient_config else "0"}

        started = time.monotonic()
        yield RunEvent(EventKind.STARTED, text="claude-code started",
                       data={"runtime": "claude-code", "workspace": str(spec.workspace)})

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(spec.workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # ★ stdin 必须指向 DEVNULL。
            #   实测：agent 运行 xelatex 等工具时，某些异常路径会**等待标准输入**，
            #   进程既不退出也不产出，表现为"静默超时"（我们只能等到超时才发现）。
            #   接上 DEVNULL 后，这类读取会立即得到 EOF 并快速失败，
            #   把"无限挂起"变成"明确报错"。
            stdin=asyncio.subprocess.DEVNULL,
            env=env,
            # ★ 流读取上限：默认只有 64 KiB，而 agent 的单行 JSON 很容易超
            #   （长工具结果、长消息）——实测会抛
            #   `ValueError: Separator is found, but chunk is longer than limit`。
            limit=STREAM_LIMIT,
        )

        final_text = ""
        fallback_lines: list[str] = []
        denied: list[str] = []
        result_subtype = ""
        result_is_error = False
        api_error_status = None
        session_id: Optional[str] = None
        #: 该步**实际生效**的模型（从流里的 assistant.message.model 取，
        #: 而不是请求参数——预设可能被网关映射成别的模型，
        #: 落库快照必须反映真实生效值，否则历史回看会失真）。
        actual_model: Optional[str] = None
        cost: Optional[float] = None
        tin = tout = None
        try:
            assert proc.stdout is not None
            while True:
                remaining = spec.timeout_s - (time.monotonic() - started)
                if remaining <= 0:
                    proc.kill()
                    yield RunEvent(EventKind.ERROR, text="整体超时", data={"code": "TIMEOUT"})
                    return
                try:
                    raw = await asyncio.wait_for(proc.stdout.readline(),
                                                 timeout=min(remaining, spec.inactivity_timeout_s))
                except asyncio.TimeoutError:
                    yield RunEvent(EventKind.ERROR, text="静默超时（无输出）",
                                   data={"code": "INACTIVITY_TIMEOUT",
                                         "silent_s": spec.inactivity_timeout_s})
                    proc.kill()
                    return
                if not raw:
                    break
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    # 非 JSON 文本（例如工具被权限拦下后模型直接把结论打在 stdout）。
                    # **必须留存**：否则 agent 的产出会连同 best-effort 结果一起丢失。
                    fallback_lines.append(line)
                    yield RunEvent(EventKind.LOG, text=line[:500])
                    continue

                mtype = msg.get("type")
                if mtype == "system":
                    session_id = msg.get("session_id") or session_id
                    if msg.get("subtype") == "init":
                        yield RunEvent(EventKind.PROGRESS, text="会话已建立",
                                       data={"session_id": session_id,
                                             "tools": msg.get("tools", [])})
                elif mtype == "assistant":
                    used_model = (msg.get("message") or {}).get("model")
                    if used_model:
                        actual_model = used_model
                    for block in (msg.get("message") or {}).get("content", []):
                        btype = block.get("type")
                        if btype == "text":
                            final_text += block.get("text", "")
                            yield RunEvent(EventKind.PROGRESS,
                                           text=block.get("text", "")[:1000])
                        elif btype == "tool_use":
                            yield RunEvent(EventKind.TOOL, text=block.get("name", ""),
                                           data={"input": str(block.get("input"))[:400]})
                        elif btype == "thinking":
                            yield RunEvent(EventKind.LOG,
                                           text="[thinking] " + block.get("thinking", "")[:300])
                elif mtype == "user":
                    for block in (msg.get("message") or {}).get("content", []):
                        if block.get("type") == "tool_result":
                            content = block.get("content")
                            text = content if isinstance(content, str) else str(content)
                            if block.get("is_error"):
                                # ⚠️ 工具被拒**不等于本次运行失败**：
                                #    实测中 agent 会换路径/换工具继续完成任务，
                                #    最终产物可能依然合格。
                                #    故只作为「告警」记录，不置 error_code，
                                #    否则会因一次被拒就跳过质量门、丢掉已完成的工作。
                                denied.append(text[:300])
                                yield RunEvent(
                                    EventKind.LOG,
                                    text="工具调用被拒（agent 可能已改用其它路径）",
                                    data={"code": "TOOL_DENIED", "detail": text[:300]})
                            else:
                                yield RunEvent(EventKind.TOOL, text="tool_result",
                                               data={"result": text[:300]})
                elif mtype == "result":
                    final_text = msg.get("result") or final_text
                    session_id = msg.get("session_id") or session_id
                    cost = msg.get("total_cost_usd")
                    usage = msg.get("usage") or {}
                    tin = usage.get("input_tokens")
                    tout = usage.get("output_tokens")
                    # ★ 记录 result 的 subtype 与 is_error。
                    #   只报 "NONZERO_EXIT" 会丢掉具体原因：实测中
                    #   `--max-budget-usd` 触顶时 CLI 给出
                    #   subtype="error_max_budget_usd" 且 exit 1，
                    #   笼统的退出码会让人误以为是程序崩溃。
                    result_subtype = msg.get("subtype") or ""
                    result_is_error = bool(msg.get("is_error"))
                    api_status = msg.get("api_error_status")
                    if api_status:
                        api_error_status = api_status
                    for d in (msg.get("permission_denials") or []):
                        denied.append(str(d)[:300])
                else:
                    yield RunEvent(EventKind.LOG, text=line[:300])
        finally:
            try:
                await asyncio.wait_for(proc.wait(), timeout=10)
            except asyncio.TimeoutError:
                proc.kill()

        # 兜底：若结构化流没给出最终文本，用非 JSON 行的累积内容，
        # 避免"agent 明明干了活却拿不到结果"。
        if not final_text.strip() and fallback_lines:
            final_text = "\n".join(fallback_lines)
            degraded_note = "final_text_from_raw_stdout"
        else:
            degraded_note = ""

        ok = proc.returncode == 0 and not result_is_error

        # 精确化错误码：把 CLI 的 subtype 直接暴露出来，
        # 让"预算触顶"与"程序崩溃"能区分开。
        code = ""
        if not ok:
            if result_subtype == "error_max_budget_usd":
                code = "MAX_BUDGET_USD"
            elif api_error_status in (429, 402, 503, 529):
                # 额度耗尽 / 限流 / 过载 —— 可由上层切换模型重试
                code = "QUOTA_OR_OVERLOAD"
            elif result_subtype:
                code = f"RESULT_{result_subtype.upper()}"
            else:
                code = "NONZERO_EXIT"

        yield RunEvent(
            EventKind.RESULT if ok else EventKind.ERROR,
            text=final_text,
            data={
                "session_id": session_id, "cost_usd": cost,
                "tokens_in": tin, "tokens_out": tout,
                "exit_code": proc.returncode,
                "duration_s": round(time.monotonic() - started, 3),
                "code": code,
                "result_subtype": result_subtype,
                "api_error_status": api_error_status,
                "fallback": degraded_note,
                "permission_denials": denied,
                "actual_model": actual_model,
            },
        )
