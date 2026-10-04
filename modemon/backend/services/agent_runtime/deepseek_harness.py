"""DeepSeek Harness (dsh) 适配器。

接口依据（实测 `dsh --help` 与 `dsh --profile headless --help`，v0.1.5-rc.1）：

    dsh [--profile <name>] [--patch <path>] [启动器参数] [应用参数...]

    dsh --profile headless [options] [task...]
        Answer one task, stream reasoning to stderr,
        print the final assistant message, and exit.

即：**推理过程走 stderr，最终答复走 stdout**，进程结束即完成，是一次性任务模式。

能力边界（如实声明）
-------------------
dsh 的 headless profile **不提供**命令行级的
模型选择 / 思考强度 / 工具白名单 / MCP 钉住 / 预算上限——
这些由 **profile 配置**决定，而非本次调用。

因此本适配器对这些能力一律声明 `False`，由上层决定降级策略。
这是本抽象层存在的核心理由：**不假装拥有自己没有的能力。**
"""

from __future__ import annotations

import asyncio
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

#: 子进程流读取上限（同 claude_code：默认 64 KiB 太小）
STREAM_LIMIT = 32 * 1024 * 1024


def find_launcher() -> Optional[tuple[str, list[str]]]:
    """返回 (可执行文件, 前置参数)。

    dsh 在 Windows 上通常只提供 `.cmd` / `.ps1` 包装器；
    `.ps1` 在受限执行策略下无法运行，故优先走 `node <bin.js>` 直调。
    """
    env = os.environ.get("MODEMON_DSH_BIN")
    if env and Path(env).is_file():
        return str(env), []

    # 优先：npm 全局包内的 bin.js（绕开 .ps1/.cmd 包装器）
    npm_dir = Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules"
    bin_js = npm_dir / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
    if bin_js.is_file():
        node = shutil.which("node") or os.environ.get("MODEMON_NODE_BIN")
        if node and Path(node).is_file():
            return str(node), [str(bin_js)]

    suffix = ".cmd" if platform.system() == "Windows" else ""
    which = shutil.which("dsh" + suffix) or shutil.which("dsh")
    if which:
        return which, []
    return None


class DeepSeekHarnessRuntime(AgentRuntime):
    def __init__(
        self,
        profile: str = "headless",
        launcher: Optional[tuple[str, list[str]]] = None,
    ) -> None:
        self.profile = profile
        self._found = launcher if launcher is not None else find_launcher()

    # -- 能力 ---------------------------------------------------------------

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(
            name="deepseek-harness",
            # 事件来自 stderr 文本行（非结构化流），故保守声明
            streaming=True,
            # headless 的一次性任务模式未提供会话恢复开关
            session_resume=False,
            effort_levels=(),
            model_selection=False,
            tool_allowlist=False,
            tool_denylist=False,
            mcp_pinning=False,
            budget_limit=False,
            structured_output=False,
            extra_dirs=False,
            skip_ambient_config=False,
        )

    def is_available(self) -> bool:
        return self._found is not None

    # -- 命令构造 -----------------------------------------------------------

    def build_command(self, spec: RunSpec) -> list[str]:
        if not self.is_available():
            raise RuntimeUnavailable("dsh 启动器未找到")
        exe, prefix = self._found  # type: ignore[misc]
        return [exe, *prefix, "--profile", self.profile, spec.prompt]

    # -- 执行 ---------------------------------------------------------------

    async def run(self, spec: RunSpec) -> AsyncIterator[RunEvent]:
        cmd = self.build_command(spec)
        env = {**os.environ, **spec.env}
        # 用 profile 指定的 home，避免污染用户默认配置
        if spec.env.get("DSH_HOME"):
            env["DSH_HOME"] = spec.env["DSH_HOME"]

        started = time.monotonic()
        yield RunEvent(EventKind.STARTED, text="deepseek-harness started",
                       data={"runtime": "deepseek-harness", "profile": self.profile,
                             "workspace": str(spec.workspace)})

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(spec.workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # stdin 接 DEVNULL：避免子进程等待标准输入而无限挂起
            # （实测会让步骤表现为"静默超时"）
            stdin=asyncio.subprocess.DEVNULL,
            env=env,
            # 同 claude_code：asyncio 默认 64 KiB 太小，
            # 长行会让 readline 抛 `ValueError: chunk is longer than limit`
            limit=STREAM_LIMIT,
        )

        async def pump(stream, kind: EventKind, sink: Optional[list[str]]) -> None:
            """读取一行并分发。

            - stderr 是推理流 -> LOG 事件
            - stdout 是最终答复 -> 收集到 sink
            """
            while True:
                line = await stream.readline()
                if not line:
                    return
                text = line.decode("utf-8", "replace").rstrip()
                if not text:
                    continue
                if sink is not None:
                    sink.append(text)
                else:
                    await queue.put(RunEvent(kind, text=text[:500]))

        # 用队列合并两个流，避免任一侧阻塞
        queue: asyncio.Queue[RunEvent] = asyncio.Queue()
        stdout_chunks: list[str] = []

        assert proc.stdout is not None and proc.stderr is not None
        tasks = [
            asyncio.create_task(pump(proc.stdout, EventKind.RESULT, stdout_chunks)),
            asyncio.create_task(pump(proc.stderr, EventKind.LOG, None)),
        ]

        timed_out = False
        while True:
            if all(t.done() for t in tasks):
                break
            remaining = spec.timeout_s - (time.monotonic() - started)
            if remaining <= 0:
                timed_out = True
                proc.kill()
                break
            try:
                ev = await asyncio.wait_for(
                    queue.get(), timeout=min(remaining, spec.inactivity_timeout_s))
                yield ev
            except asyncio.TimeoutError:
                if proc.returncode is None:
                    yield RunEvent(EventKind.ERROR, text="静默超时（无输出）",
                                   data={"code": "INACTIVITY_TIMEOUT",
                                         "silent_s": spec.inactivity_timeout_s})
                    proc.kill()
                    timed_out = True
                break
            except asyncio.CancelledError:
                proc.kill()
                raise

        await asyncio.gather(*tasks, return_exceptions=True)
        while not queue.empty():
            yield queue.get_nowait()

        try:
            await asyncio.wait_for(proc.wait(), timeout=10)
        except asyncio.TimeoutError:
            proc.kill()

        while not queue.empty():
            yield queue.get_nowait()

        if timed_out:
            return

        ok = proc.returncode == 0
        yield RunEvent(
            EventKind.RESULT if ok else EventKind.ERROR,
            text="\n".join(stdout_chunks).strip(),
            data={
                "exit_code": proc.returncode,
                "duration_s": round(time.monotonic() - started, 3),
                "code": "" if ok else "NONZERO_EXIT",
                "note": "stderr 为推理流；最终答复取自 stdout",
            },
        )
