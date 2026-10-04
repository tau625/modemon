"""TeX 运行时探测与编译。

为什么单独成模块
----------------
蓝方为此专门做了桌面 IPC `latex:get-status`，返回
`{state: 'ready'|'partial'|'missing', hasXelatex, miktexDir, installerAvailable}`，
并在启动日志里写明「检查工具可用性（**不等待** LaTeX 在线安装）」。

这说明一个真实约束：**随包的 LaTeX 开箱不可用**。
实测确认——随包的 MiKTeX 从未初始化，直接调用会得到：

    It seems that this is a fresh TeX installation.
    Please finish the setup before proceeding.
    xelatex: major issue: So far, you have not checked for MiKTeX updates.

因此本模块的职责是**如实报告状态**，而不是假装能编译。
探测顺序：显式配置 → 系统 TeX → 随包 TeX。
"""

from __future__ import annotations

import glob
import os
import platform
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

EXE = "xelatex.exe" if platform.system() == "Windows" else "xelatex"

#: 随包 TeX 的候选根目录
BUNDLED_ROOTS = (
    Path(r"E:\02_Installers\DailyApps\Modex-MH-Agent\runtime\texlive"),
)

#: 系统 TeX 的常见位置（用于优先复用用户已装且已初始化的 TeX）
SYSTEM_GLOBS = (
    r"D:\04_IDEs\texlive\*\bin\windows",
    r"C:\texlive\*\bin\windows",
    r"C:\Program Files\MiKTeX\miktex\bin\x64",
    r"C:\Users\*\AppData\Local\Programs\MiKTeX\miktex\bin\x64",
)


@dataclass
class TexRuntime:
    """一个可用的（或不可用的）TeX 运行时。"""

    state: str = "missing"          # ready | fresh | missing
    xelatex: Optional[str] = None
    latexmk: Optional[str] = None
    root: Optional[str] = None
    installer_available: bool = False
    note: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.state == "ready" and self.xelatex is not None

    def as_dict(self) -> dict:
        return {
            "state": self.state, "xelatex": self.xelatex, "latexmk": self.latexmk,
            "root": self.root, "installer_available": self.installer_available,
            "note": self.note, "warnings": list(self.warnings),
        }


def _find_installer() -> bool:
    """随包是否带 MiKTeX 安装器（对应蓝方的 `installerAvailable`）。"""
    for root in BUNDLED_ROOTS:
        if (root.parent / "miktex-setup.exe").is_file():
            return True
    return False


def _probe(exe: str, *, timeout: int = 60) -> tuple[bool, str]:
    """跑一次极小文档，判断该 xelatex 是否**真的可用于中文编译**。

    只检查 `--version` 不够——"fresh installation" 的 MiKTeX 版本号正常，
    但一编译就要求先完成 setup。
    """
    import tempfile

    doc = (
        "\\documentclass{article}\n"
        "\\usepackage{xeCJK}\n"
        "\\begin{document}探测\\end{document}\n"
    )
    with tempfile.TemporaryDirectory(prefix="modemon-tex-") as td:
        tex = Path(td) / "probe.tex"
        tex.write_text(doc, encoding="utf-8")
        env = {**os.environ, "PATH": str(Path(exe).parent) + os.pathsep + os.environ.get("PATH", "")}
        try:
            p = subprocess.run(
                [exe, "-interaction=nonstopmode", "-halt-on-error", "probe.tex"],
                cwd=td, capture_output=True, timeout=timeout, env=env,
            )
        except subprocess.TimeoutExpired:
            return False, "编译探测超时"
        except OSError as exc:
            return False, f"无法执行: {exc}"

        log = (p.stdout or b"").decode("utf-8", "replace") + \
              (p.stderr or b"").decode("utf-8", "replace")
        if "fresh TeX installation" in log or "finish the setup" in log:
            return False, "fresh TeX installation（需先完成 MiKTeX setup）"
        if not (Path(td) / "probe.pdf").is_file():
            tail = "\n".join(log.strip().splitlines()[-4:])
            return False, f"未产出 PDF：{tail[:300]}"
        return True, ""


def resolve_tex_runtime(*, prefer_system: bool = True, probe: bool = True) -> TexRuntime:
    """解析可用的 TeX 运行时。

    优先级：显式环境变量 → 系统 TeX（已初始化）→ 随包 TeX。
    **优先复用系统 TeX**：随包的常常需要先跑安装器，而用户已装的通常可用。
    """
    rt = TexRuntime(installer_available=_find_installer())

    candidates: list[tuple[str, str]] = []
    env = os.environ.get("MODEMON_XELATEX")
    if env and Path(env).is_file():
        candidates.append(("env", env))

    def _system_candidates() -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        for pat in SYSTEM_GLOBS:
            for hit in sorted(glob.glob(pat)):
                exe = Path(hit) / EXE
                if exe.is_file():
                    found.append(("system", str(exe)))
        return found

    def _bundled_candidates() -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        for root in BUNDLED_ROOTS:
            for d in (root / "miktex" / "bin" / "x64",
                      root / "executables" / "windows-x64"):
                exe = d / EXE
                if exe.is_file():
                    found.append(("bundled", str(exe)))
        return found

    if prefer_system:
        candidates += _system_candidates() + _bundled_candidates()
    else:
        candidates += _bundled_candidates() + _system_candidates()

    seen: set[str] = set()
    for origin, exe in candidates:
        if exe in seen:
            continue
        seen.add(exe)
        parent = str(Path(exe).parent)
        if probe:
            ok, why = _probe(exe)
        else:
            ok, why = True, ""
        if ok:
            lm = str(Path(parent) / ("latexmk.exe" if platform.system() == "Windows" else "latexmk"))
            rt.state = "ready"
            rt.xelatex = exe
            rt.latexmk = lm if Path(lm).is_file() else None
            rt.root = parent
            rt.note = f"来源：{origin}"
            return rt
        rt.warnings.append(f"{origin}@{exe}: {why}")

    # 一个都不能用
    if candidates:
        rt.state = "fresh" if any("fresh" in w for w in rt.warnings) else "missing"
        rt.note = ("随包 TeX 尚未初始化，需先运行 MiKTeX 安装器完成 setup"
                   if rt.state == "fresh" else "未找到可用的 TeX 运行时")
    else:
        rt.state = "missing"
        rt.note = "未找到 xelatex"
    return rt


# ---------------------------------------------------------------------------
# 编译
# ---------------------------------------------------------------------------


@dataclass
class CompileResult:
    ok: bool
    pdf: Optional[str] = None
    pages: Optional[int] = None
    duration_s: float = 0.0
    log_tail: str = ""
    error: str = ""

    def as_dict(self) -> dict:
        return {"ok": self.ok, "pdf": self.pdf, "pages": self.pages,
                "duration_s": self.duration_s, "error": self.error,
                "log_tail": self.log_tail}


def compile_tex(
    tex_path: Path,
    *,
    runtime: Optional[TexRuntime] = None,
    runs: int = 2,
    timeout: int = 300,
) -> CompileResult:
    """编译 .tex 为 PDF。

    跑两遍以解析交叉引用。**不自动安装缺失宏包**——
    在线安装不可控且可能很慢；缺包时如实报错，由上层决定是否安装。
    """
    rt = runtime or resolve_tex_runtime()
    if not rt.ready:
        return CompileResult(ok=False, error=f"TeX 运行时不可用（{rt.state}）：{rt.note}")

    tex_path = Path(tex_path).resolve()
    cwd = tex_path.parent
    env = {**os.environ, "PATH": str(Path(rt.xelatex).parent) + os.pathsep + os.environ.get("PATH", "")}
    t0 = time.monotonic()
    log_all = ""

    for _ in range(max(1, runs)):
        try:
            p = subprocess.run(
                [rt.xelatex, "-interaction=nonstopmode", "-halt-on-error",
                 tex_path.name],
                cwd=str(cwd), capture_output=True, timeout=timeout, env=env,
            )
        except subprocess.TimeoutExpired:
            return CompileResult(ok=False, duration_s=round(time.monotonic() - t0, 2),
                                 error=f"编译超时（>{timeout}s）")
        log_all += (p.stdout or b"").decode("utf-8", "replace")
        log_all += (p.stderr or b"").decode("utf-8", "replace")
        if p.returncode != 0:
            break

    pdf = tex_path.with_suffix(".pdf")
    # ⚠️ 判定必须严格：`returncode == 0` 且 PDF 存在。
    #    曾用 `pdf.exists() and size > 0`，后果是：
    #    插图路径错误 → xelatex 中途报错 → 只输出前 2 页的部分 PDF，
    #    而我们却报 "ok: True" —— **把失败伪装成了成功**。
    #    宁可报失败让上层看到真实错误，也不要"看起来成功"。
    ok = p.returncode == 0 and pdf.is_file()
    tail = "\n".join(log_all.strip().splitlines()[-25:])

    pages = None
    if ok:
        pages = _pdf_pages(pdf)
    error = ""
    if not ok:
        m = re.search(r"^! (.+)$", log_all, re.M)
        error = m.group(1)[:300] if m else "编译失败（详见日志）"

    return CompileResult(ok=ok, pdf=str(pdf) if ok else None, pages=pages,
                         duration_s=round(time.monotonic() - t0, 2),
                         log_tail=tail, error=error)


def _pdf_pages(pdf: Path) -> Optional[int]:
    """用 PyMuPDF 数页数（用于校验 advisory 页数预算）。"""
    try:
        import fitz  # type: ignore

        with fitz.open(str(pdf)) as d:
            return int(d.page_count)
    except Exception:
        return None


__all__ = ["TexRuntime", "CompileResult", "resolve_tex_runtime", "compile_tex", "EXE"]
