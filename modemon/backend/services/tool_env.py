"""为 agent 子进程准备工具环境。

要解决的问题
------------
agent 是在子进程里跑的，它**看不到我们进程内解析出来的工具路径**。
最典型的是第 8 步「编译与合规检查」：需要 `xelatex`，
而本机可用的 TeX 是**系统装的**（随包 MiKTeX 未初始化，见 `tex_runtime`）。
若不把它的 bin 目录放进子进程 PATH，agent 会直接失败。

蓝方有同名模块 `services/child_environment.py` 处理这件事，本模块是等价的实现。

设计要点
--------
- **只增不改**：在现有 PATH 前**追加**新目录，不覆盖用户已有的环境变量。
- **只加存在的路径**：不做乐观假设，路径不存在就不加（但记录）。
- **可观测**：返回准备了什么、跳过了什么，便于排查"为什么 agent 说找不到工具"。
"""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

#: 随包 runtime 根（可由环境变量覆盖）
MH_ROOT = Path(os.environ.get("MODEMON_MH_ROOT",
                              r"E:\02_Installers\DailyApps\Modex-MH-Agent"))

#: 需要在 PATH 中可见的工具目录（按优先级）
TOOL_DIRS: tuple[tuple[str, Path], ...] = (
    ("python", MH_ROOT / "runtime" / "python"),
    ("node", MH_ROOT / "runtime" / "node"),
    ("pandoc", MH_ROOT / "runtime" / "pandoc"),
    ("git", MH_ROOT / "runtime" / "git" / "mingw64" / "bin"),
    ("texlive", MH_ROOT / "runtime" / "texlive" / "miktex" / "bin" / "x64"),
)

#: 需要**前置**的随包工具。
#:
#: `python`：随包 4.24 GB 的 Python 是精心配好的科学计算环境
#: （numpy/scipy/matplotlib/pulp 等），而系统 Python 未必有这些包。
#: agent 求解建模题时依赖它，因此必须前置。
#:
#: 其余（node/pandoc/git）作兜底追加即可——系统版本通常更新且够用。
FRONT_TOOLS = frozenset({"python"})

#: 需要探测是否可用的命令（用于报告缺失项）
REQUIRED_TOOLS = ("python", "xelatex", "node", "git")


@dataclass
class ToolEnvReport:
    added: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    present_already: list[str] = field(default_factory=list)
    found: dict[str, Optional[str]] = field(default_factory=dict)
    tex_source: str = ""
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"added_paths": self.added, "missing": self.missing,
                "already_in_path": self.present_already, "tools": self.found,
                "tex_source": self.tex_source, "warnings": self.warnings}


def _which_in(exe: str, dirs: list[str]) -> Optional[str]:
    for d in dirs:
        p = Path(d) / (exe + (".exe" if platform.system() == "Windows" else ""))
        if p.is_file():
            return str(p)
    return None


def prepare_child_env(
    base: Optional[dict[str, str]] = None,
    *,
    tool_dirs: tuple[tuple[str, Path], ...] = TOOL_DIRS,
    extra_dirs: tuple[Path, ...] = (),
) -> tuple[dict[str, str], ToolEnvReport]:
    """构造 agent 子进程的环境变量。

    Returns:
        (env, report)
    """
    env = dict(base if base is not None else os.environ)
    rep = ToolEnvReport()

    path_parts = [p for p in env.get("PATH", "").split(os.pathsep) if p]

    def add(d: Path, *, front: bool = False) -> None:
        """把目录加入 PATH。

        front=False（默认）：**追加**为兜底——不遮蔽用户环境里更好的版本。
        front=True：**移到最前**——用于我们已探测确认要使用的工具。

        ⚠️ 实测教训：曾把所有随包目录一律插到最前，结果随包的
        **未初始化 MiKTeX** 遮蔽了系统已装的 TeXLive，导致编译必然失败。
        """
        s = str(d)
        if not d.is_dir():
            rep.missing.append(s)
            return
        if s in path_parts:
            if not front:
                rep.present_already.append(s)
                return
            path_parts.remove(s)          # 已在 PATH 中：移到最前
        if front:
            path_parts.insert(0, s)
        else:
            path_parts.append(s)
        rep.added.append(("front:" + s) if front else s)

    # 随包运行时：python 前置（科学计算环境），其余兜底追加
    for name, d in tool_dirs:
        add(d, front=(name in FRONT_TOOLS))
    for d in extra_dirs:
        add(Path(d))

    # 系统装的 TeX：**前置**。
    # 随包 MiKTeX 未初始化（fresh installation），只有探测通过的才能用；
    # `resolve_tex_runtime` 会实际编译一个极小文档来验证，因此它给的是可信结果。
    try:
        from . import tex_runtime as tx

        rt = tx.resolve_tex_runtime(probe=True)
        if rt.xelatex:
            add(Path(rt.xelatex).parent, front=True)
            rep.tex_source = rt.note
        else:
            rep.warnings.append(f"无可用 TeX 运行时（{rt.state}）：{rt.note}")
    except Exception as exc:  # 探测失败不应阻断执行
        rep.warnings.append(f"TeX 运行时探测失败: {exc}")

    env["PATH"] = os.pathsep.join(path_parts)

    # 让子进程也用 UTF-8，避免中文路径/输出乱码
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONLEGACYWINDOWSSTDIO", "0")

    # 关闭可能干扰 agent 的交互式分页
    env.setdefault("GIT_PAGER", "cat")
    env.setdefault("PAGER", "cat")
    env.setdefault("NO_COLOR", "1")

    # ★ TeX 必须非交互。
    #   实测：随包 MiKTeX 处于"未初始化"状态时会**等待用户确认 setup**，
    #   agent 调它就会无限挂起（表现为步骤"静默超时"）。
    #   这些变量让它遇到缺包/未初始化时**直接报错**而不是等人。
    env.setdefault("MIKTEX_AUTOINSTALL", "no")
    env.setdefault("MIKTEX_QUIET", "1")
    env.setdefault("MIKTEX_INTERACTION_MODE", "nonstopmode")
    env.setdefault("TEXMFVAR", str(MH_ROOT / "runtime" / "texlive" / "userdata" / "texmf-var"))
    # 让 latexmk 也不要交互
    env.setdefault("LATEXMK_QUIET", "1")

    for exe in REQUIRED_TOOLS:
        rep.found[exe] = shutil.which(exe, path=env["PATH"])

    return env, rep


def describe_tools() -> dict:
    """当前环境下各关键工具是否可用（供 API/前端展示）。"""
    _env, rep = prepare_child_env()
    return rep.as_dict()


__all__ = ["ToolEnvReport", "prepare_child_env", "describe_tools",
           "TOOL_DIRS", "REQUIRED_TOOLS", "MH_ROOT"]
