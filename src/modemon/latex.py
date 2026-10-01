"""LaTeX 编译与报错定位。

把「编译 → 抓错误 → 回灌给执行者修 → 再编译」这条闭环所需的最小能力独立出来，
既供工作流引擎调用，也供 CLI 单独使用（不带修复的纯编译）。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

ERROR_HINT_RE = re.compile(
    r"(^!|LaTeX Error|Undefined control sequence|Missing \$|Runaway argument|"
    r"Emergency stop|File .* not found|Package .* Error)",
    re.I,
)


@dataclass
class CompileResult:
    ok: bool = False
    engine: str = ""
    engine_path: str = ""
    returncode: int = -1
    duration_s: float = 0.0
    pdf: Path | None = None
    log_path: Path | None = None
    error_excerpt: str = ""
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "engine": self.engine,
            "returncode": self.returncode,
            "duration_s": round(self.duration_s, 2),
            "pdf": self.pdf.name if self.pdf else None,
            "pdf_bytes": self.pdf.stat().st_size if self.pdf and self.pdf.exists() else 0,
            "log": self.log_path.name if self.log_path else None,
            "message": self.message,
        }


def _extract_json_array(text: str) -> list | None:
    """从回复里抠出第一个完整的 JSON 数组（容忍解释文字与代码围栏）。"""
    start = text.find("[")
    while start != -1:
        depth, in_str, escaped = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(data, list):
                        return data
        start = text.find("[", start + 1)
    return None


def parse_patches(text: str) -> list[dict]:
    """解析补丁式修复结果：[{"find": ..., "replace": ..., "why": ...}, ...]。

    为什么需要补丁：实测该端点单次输出约 1.45 万 token 就到头，
    整篇论文（3~5 万字符）根本没法一次重发，全文件回修必然截断。
    """
    data = _extract_json_array(text)
    if not data:
        return []
    patches: list[dict] = []
    for item in data:
        if isinstance(item, dict) and str(item.get("find") or "").strip():
            patches.append(
                {
                    "find": str(item.get("find")),
                    "replace": str(item.get("replace") or ""),
                    "why": str(item.get("why") or ""),
                }
            )
    return patches


def apply_patches(text: str, patches: list[dict]) -> tuple[str, bool, list[str]]:
    """逐条应用补丁；要求每条 find 在原文中**唯一命中**，否则整体视为失败。"""
    notes: list[str] = []
    result = text
    for index, patch in enumerate(patches, 1):
        find = patch.get("find", "")
        replace = patch.get("replace", "")
        count = result.count(find)
        if count == 0:
            notes.append(f"补丁{index} 未匹配到原文")
            continue
        if count > 1:
            notes.append(f"补丁{index} 片段不唯一（{count} 处）")
            continue
        result = result.replace(find, replace, 1)
        notes.append(f"补丁{index} 已应用")
    ok = bool(patches) and all(n.endswith("已应用") for n in notes)
    return result, ok, notes


def find_paper(run_root: Path) -> Path | None:
    """找到入口 .tex：优先 main.tex / paper.tex，否则取第一个。"""
    paper_dir = Path(run_root) / "paper"
    if not paper_dir.exists():
        return None
    tex_files = sorted(paper_dir.glob("*.tex"))
    if not tex_files:
        return None
    for cand in tex_files:
        if cand.stem.lower() in ("main", "paper", "thesis"):
            return cand
    return tex_files[0]


def extract_error(log: str, limit: int = 30) -> str:
    """从编译日志里截出最有用的一段：以第一条真正的 TeX 错误为中心。"""
    lines = log.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("!"):
            return "\n".join(lines[max(0, i - 3) : i + limit])
    for i, line in enumerate(lines):
        if ERROR_HINT_RE.search(line):
            return "\n".join(lines[max(0, i - 3) : i + limit])
    return "\n".join(lines[-limit:])


def compile_tex(
    tex: Path,
    *,
    engine: str = "xelatex",
    timeout: int = 300,
    passes: int = 1,
    log_dir: Path | None = None,
    log_name: str | None = None,
) -> CompileResult:
    """编译指定 .tex，返回结构化结果（不改动源文件）。"""
    tex = Path(tex)
    if not tex.exists():
        return CompileResult(ok=False, engine=engine, message=f"源文件不存在：{tex}")

    engine_path = shutil.which(engine)
    if not engine_path:
        return CompileResult(ok=False, engine=engine, message=f"未找到编译引擎 {engine}，请确认 TeX Live 已加入 PATH")

    pdf_path = tex.with_suffix(".pdf")
    if pdf_path.exists():
        pdf_path.unlink()  # 避免把上一次的旧 PDF 误判成本次成功

    started = time.perf_counter()
    logs: list[str] = []
    returncode = -1
    for _ in range(max(1, passes)):
        try:
            proc = subprocess.run(
                [engine_path, "-interaction=nonstopmode", "-halt-on-error", tex.name],
                cwd=str(tex.parent),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            returncode = proc.returncode
            logs.append((proc.stdout or "") + "\n" + (proc.stderr or ""))
            if proc.returncode != 0:
                break
        except subprocess.TimeoutExpired:
            duration = time.perf_counter() - started
            return CompileResult(
                ok=False, engine=engine, engine_path=engine_path, returncode=124,
                duration_s=duration, message=f"编译超时（>{timeout}s）",
            )
    duration = time.perf_counter() - started

    log_text = "\n".join(logs)
    log_path: Path | None = None
    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / (log_name or f"compile_{tex.stem}.log")
        log_path.write_text(log_text, encoding="utf-8")

    ok = returncode == 0 and pdf_path.exists()
    return CompileResult(
        ok=ok,
        engine=engine,
        engine_path=engine_path,
        returncode=returncode,
        duration_s=duration,
        pdf=pdf_path if pdf_path.exists() else None,
        log_path=log_path,
        error_excerpt="" if ok else extract_error(log_text),
        message="编译成功" if ok else f"编译失败（exit={returncode}）",
    )
