"""执行沙箱：把模型产出的代码块落盘，并**真实运行**，收集真实数值结果。

这是本工程的信任基石：论文里出现的数字只能来自这里的真实输出。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

FENCE_RE = re.compile(
    r"^[ \t]*```([A-Za-z0-9_+\-.]*)[ \t]*\r?\n(.*?)(?:^[ \t]*```[ \t]*$|\Z)",
    re.S | re.M,
)
FILE_MARK_RE = re.compile(r"^\s*(?:#|//|%|--)\s*file\s*[:=]\s*(\S+)\s*$", re.I)

EXT_BY_LANG = {
    "python": ".py", "py": ".py",
    "latex": ".tex", "tex": ".tex",
    "markdown": ".md", "md": ".md",
    "json": ".json", "yaml": ".yaml", "yml": ".yml",
    "javascript": ".js", "js": ".js", "bash": ".sh", "sh": ".sh",
}

RESULT_PREFIX = "RESULT_JSON"


@dataclass
class ExecResult:
    file: str
    returncode: int
    duration_s: float
    stdout: str
    stderr: str
    result_json: dict | None = None
    log_path: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def summary(self) -> dict:
        return {
            "file": self.file,
            "returncode": self.returncode,
            "duration_s": round(self.duration_s, 2),
            "result_json": self.result_json,
            "stdout_tail": self.stdout[-1500:],
            "stderr_tail": self.stderr[-1500:],
            "log": self.log_path,
        }


@dataclass
class ExtractedBundle:
    files: dict[str, str] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    unterminated: list[str] = field(default_factory=list)  # 缺少结尾围栏（多为被 max_tokens 截断）
    bare_blocks: list[str] = field(default_factory=list)   # 没有用代码围栏，只靠 `# file:` 标记裸输出


def extract_files(text: str, *, default_dir: str = "") -> ExtractedBundle:
    """从模型回复中抽取带 `# file: 路径` 标记的代码块。

    允许最后一个代码块**没有结尾围栏**：真实发生过输出被 max_tokens 截断、
    结尾围栏丢失，若从严匹配会把整篇论文（2 万多字符）全部丢弃。
    """
    bundle = ExtractedBundle()
    for idx, match in enumerate(FENCE_RE.finditer(text), start=1):
        lang = (match.group(1) or "").strip().lower()
        body = match.group(2)
        lines = body.splitlines()

        rel: str | None = None
        for line in lines[:3]:
            m = FILE_MARK_RE.match(line)
            if m:
                rel = m.group(1).strip().strip('"\'`')
                break
        if rel is None:
            if not lang or lang in ("json", "text", "bash", "sh"):
                bundle.skipped.append(f"代码块 {idx}（语言={lang or '未标注'}）缺少 `# file:` 路径标记")
                continue
            ext = EXT_BY_LANG.get(lang, ".txt")
            rel = f"{default_dir}/block{idx}{ext}" if default_dir else f"block{idx}{ext}"

        rel = rel.replace("\\", "/").lstrip("/")
        if ".." in rel.split("/"):
            bundle.skipped.append(f"代码块 {idx} 路径非法（含 ..）：{rel}")
            continue
        bundle.files[rel] = body.rstrip() + "\n"
        if not match.group(0).rstrip().endswith("```"):
            bundle.unterminated.append(rel)

    # 兜底：模型有时完全不写围栏，只给 `% file: 路径` 开头的裸文本。
    # 实测在"编译回修"里发生过，导致修复产出被整体丢弃。
    if not bundle.files:
        lines = text.splitlines()
        starts: list[tuple[int, str]] = []
        for index, line in enumerate(lines):
            marker = FILE_MARK_RE.match(line)
            if marker:
                starts.append((index, marker.group(1).strip().strip("\"'`")))
        for position, (start, rel) in enumerate(starts):
            end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
            rel = rel.replace("\\", "/").lstrip("/")
            if ".." in rel.split("/"):
                bundle.skipped.append(f"裸文本段 {position + 1} 路径非法（含 ..）：{rel}")
                continue
            bundle.files[rel] = "\n".join(lines[start:end]).strip() + "\n"
            bundle.bare_blocks.append(rel)

    return bundle


def write_files(run_root: Path, files: dict[str, str], *, subdir: str = "") -> list[Path]:
    """把抽取出的文件写到运行根目录下（路径由模型给出的 `# file:` 标记决定）。"""
    written: list[Path] = []
    base = (run_root / subdir).resolve() if subdir else run_root.resolve()
    for rel, content in files.items():
        target = (base / rel).resolve()
        if not str(target).startswith(str(base)):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(target)
    return written


def _parse_result_json(stdout: str, stderr: str) -> dict | None:
    for stream in (stdout, stderr):
        for line in reversed(stream.splitlines()):
            line = line.strip()
            if RESULT_PREFIX in line:
                payload = line.split(RESULT_PREFIX, 1)[1].strip()
                payload = payload.lstrip(":：").strip()
                try:
                    data = json.loads(payload)
                    return data if isinstance(data, dict) else {"value": data}
                except json.JSONDecodeError:
                    continue
    return None


def run_python_files(
    run_root: Path,
    files: list[Path],
    *,
    python_exe: str | None = None,
    timeout: int = 600,
    extra_env: dict[str, str] | None = None,
) -> list[ExecResult]:
    """在运行根目录下依次执行生成的 Python 文件。工作目录 = 运行根目录。"""
    python_exe = python_exe or sys.executable
    scripts = [p for p in files if p.suffix.lower() == ".py"]
    # 入口脚本优先
    scripts.sort(key=lambda p: (0 if p.name in ("main.py", "run.py") else 1, str(p)))

    env = dict(os.environ)
    env.setdefault("MPLBACKEND", "Agg")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    if extra_env:
        env.update(extra_env)

    results: list[ExecResult] = []
    for script in scripts:
        rel = script.relative_to(run_root).as_posix()
        started = __import__("time").perf_counter()
        try:
            proc = subprocess.run(
                [python_exe, rel],
                cwd=str(run_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=env,
            )
            rc, out, err = proc.returncode, proc.stdout or "", proc.stderr or ""
        except subprocess.TimeoutExpired as exc:
            rc, out, err = 124, (exc.stdout or "") if isinstance(exc.stdout, str) else "", f"超时（>{timeout}s）"
        duration = __import__("time").perf_counter() - started

        log_path = run_root / "results" / "logs" / (rel.replace("/", "__") + ".log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            f"$ python {rel}\nexit={rc} duration={duration:.2f}s\n--- stdout ---\n{out}\n--- stderr ---\n{err}\n",
            encoding="utf-8",
        )
        results.append(
            ExecResult(
                file=rel,
                returncode=rc,
                duration_s=duration,
                stdout=out,
                stderr=err,
                result_json=_parse_result_json(out, err),
                log_path=log_path.relative_to(run_root).as_posix(),
            )
        )
    return results
