"""图表流水线：把 FigureSpec JSON 变成论文可用的插图。

职责划分（这是替代"手写 TikZ"的关键）
--------------------------------------
**agent 决定语义，引擎负责渲染。**

| 谁 | 做什么 |
|---|---|
| agent | 写声明式的 `FigureSpec` JSON（节点、边、标签、分组） |
| 引擎 | 校验 → 确定性渲染 SVG → 转 PNG → 生成 `latex_includes.tex` |

为什么这样分工：此前 `paper-figure-drawio` 让 agent **手写 TikZ**，
再反复「编译 → 渲染 → 看图 → 改」，每次迭代 20–40 秒且**没有上界**，
是该步骤反复卡死的根源。而 FigureSpec 是**确定性**的：

    同一份 JSON → 同一份 SVG（固定渲染器版本 + 字体）

没有迭代、没有视觉猜测、没有绘图 API。agent 写 JSON 也比写 TikZ 容易得多。

许可
----
渲染器来自上游 **ARIS** 的 `skills/figure-spec`（**MIT License**，
`Copyright (c) 2026 wanshuiyin`）。完整文本见 `modemon/LICENSE-ARIS.txt`；
MIT 的硬性条件是保留版权声明与许可全文，两者都已内嵌于
`services/figure_spec.py` 与 `services/skill_loader.py`。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from . import figure_spec as fs
from . import paper_build as pb

#: FigureSpec JSON 的存放目录与后缀约定
SPEC_DIR = "figures"
SPEC_SUFFIXES = (".spec.json", ".figure.json", ".figurespec.json")

#: LaTeX 章节标题（与既有导出约定一致）
SECTION_TITLE = "流程与架构图"


@dataclass
class FigurePipelineReport:
    rendered: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    includes_tex: Optional[Path] = None

    @property
    def ok(self) -> bool:
        return bool(self.rendered) and not self.errors

    def as_dict(self) -> dict:
        return {"ok": self.ok, "rendered": self.rendered,
                "skipped": self.skipped, "errors": self.errors,
                "includes_tex": str(self.includes_tex) if self.includes_tex else None}


# ---------------------------------------------------------------------------
# 发现
# ---------------------------------------------------------------------------


def find_specs(workspace: Path) -> list[Path]:
    """找 FigureSpec JSON。

    约定放在 `figures/` 下，后缀为 `.spec.json` / `.figure.json` /
    `.figurespec.json`。也接受 `figures/specs/*.json`。

    ⚠️ **按内容去重**：实测 agent 会把**同一份 spec** 用两个名字各写一次
    （`architecture.spec.json` 与 `tikz_architecture.spec.json` 逐字节相同、
    SHA256 一致）。不做去重就会渲染出两张同 `latex_name` 的图 →
    LaTeX 里出现**重复 `\\label`**，交叉引用指向错的那张。
    """
    ws = Path(workspace)
    out: list[Path] = []
    for d in (ws / SPEC_DIR, ws / SPEC_DIR / "specs", ws / "figurespec"):
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if not p.is_file():
                continue
            if p.suffixes and "".join(p.suffixes[-2:]).lower() in SPEC_SUFFIXES:
                out.append(p)
            elif p.suffix.lower() == ".json" and p.parent.name in ("specs", "figurespec"):
                out.append(p)

    # 内容级去重：同一份 spec 只渲染一次（保留文件名最短的那个，通常是"正名"）
    seen: dict[str, Path] = {}
    for p in out:
        try:
            key = hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError:
            continue
        if key not in seen or len(p.name) < len(seen[key].name):
            seen[key] = p
    return sorted(seen.values())


def _read_spec(path: Path) -> tuple[Optional[dict], str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"JSON 解析失败：{exc}"
    if not isinstance(data, dict):
        return None, "顶层必须是对象"
    return data, ""


def _caption_of(spec: dict, fallback: str) -> str:
    """图注：优先用 spec 的 title，其次分组名，最后可读名。

    ⚠️ 不能编造：视觉自检抓过「图题为『图 1 scenarios』」这条——
    缺图注时编一个像模像样的英文名比留白更糟，它掩盖了缺失。
    """
    t = (spec.get("title") or "").strip()
    return t or fallback


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------


def render_specs(
    workspace: Path,
    *,
    python: Optional[str] = None,
    convert_png: bool = True,
) -> FigurePipelineReport:
    """渲染所有 FigureSpec，产出 SVG/PNG 并登记为论文插图。"""
    rep = FigurePipelineReport()
    ws = Path(workspace)
    specs = find_specs(ws)
    if not specs:
        rep.errors.append(f"未找到 FigureSpec（约定：{SPEC_DIR}/*.spec.json）")
        return rep

    for sp in specs:
        data, err = _read_spec(sp)
        if data is None:
            rep.skipped.append({"file": sp.name, "reason": err})
            continue

        ok_v, msg_v = fs.validate_spec(data, python=python)
        if not ok_v:
            rep.errors.append(f"{sp.name} 校验失败：{msg_v[:200]}")
            rep.skipped.append({"file": sp.name, "reason": "validate: " + msg_v[:120]})
            continue

        out_prefix = ws / SPEC_DIR / (sp.stem.replace(".spec", "").replace(".figure", "")
                                      .replace(".figurespec", "") or sp.stem)
        r = fs.render_figure(data, out_prefix, python=python,
                             convert_png=convert_png)
        if not r.ok:
            rep.errors.append(f"{sp.name} 渲染失败：{r.error[:200]}")
            continue

        png_rel: Optional[str] = None
        if r.png and r.png.is_file():
            png_rel = r.png.relative_to(ws).as_posix()
        elif r.svg and r.svg.is_file():
            png_rel = r.svg.relative_to(ws).as_posix()

        caption = _caption_of(data, sp.stem)
        rep.rendered.append({
            "spec": sp.relative_to(ws).as_posix(),
            "svg": r.svg.relative_to(ws).as_posix() if r.svg else None,
            "png": png_rel,
            "caption": caption,
            "notes": list(r.notes),
        })

    return rep


# ---------------------------------------------------------------------------
# 生成 latex_includes.tex
# ---------------------------------------------------------------------------


def write_latex_includes(workspace: Path, rep: FigurePipelineReport) -> Path:
    """把渲染出的图写成 `figures/latex_includes.tex`。

    与既有约定一致：图与本文件同目录，用相对路径引入，
    并登记 `figure` 环境与 `\\caption`。
    """
    ws = Path(workspace)
    out = ws / SPEC_DIR / "latex_includes.tex"

    lines = [
        "%% figures/latex_includes.tex",
        "%% 由 FigureSpec 确定性渲染生成（ARIS figure-spec，MIT License）",
        "%% 在 paper/main.tex 导言区加入 \\usepackage{graphicx} 后",
        "%% 于正文中 \\input{../figures/latex_includes}",
        "%%",
        "%% ⚠️ 图与本文件同目录，故用相对路径；",
        "%%    若编译目录不同请改为 \\graphicspath{{../figures/}}",
        r"\usepackage{graphicx}",
        r"\graphicspath{{../figures/}{figures/}}",
        "",
    ]

    for i, item in enumerate(rep.rendered, 1):
        rel = item.get("png")
        if not rel:
            continue
        # 只要文件名部分（同目录引入）
        fname = Path(rel).name
        cap = str(item.get("caption") or Path(fname).stem)
        cap_tex = pb._tex_escape(cap)
        lines += [
            "%% " + str(item.get("spec", "")),
            r"\begin{figure}[htbp]",
            r"  \centering",
            f"  \\includegraphics[width=14cm,height=9.5cm,keepaspectratio]{{{fname}}}",
            f"  \\caption{{{cap_tex}}}",
            f"  \\label{{fig:arch_{i}}}",
            r"\end{figure}",
            "",
        ]

    if len(rep.rendered) == 0:
        lines.append("%% （无可渲染的 FigureSpec）")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    rep.includes_tex = out
    return out


#: 追加区块的起始标记（用于幂等：重复运行不会重复追加）
MERGE_MARKER = "%% ==== FigureSpec 渲染结果（引擎生成，勿手改）===="


def merge_latex_includes(workspace: Path, rep: FigurePipelineReport) -> Path:
    """把渲染出的图**追加**到 `latex_includes.tex`（幂等）。

    为什么是"追加"而不是"覆盖"：实测中 agent 会**自己手写**一份
    `latex_includes.tex`，里面登记了全部数据图（质量还不错）。
    直接覆盖会把它丢掉。所以只在文件末尾追加一段带标记的区块，
    重复运行先删旧区块再写新区块。

    ⚠️ 这个函数存在的根本原因：**只改提示词是不够的**——
    实测发现 agent 写了 `architecture.spec.json` 却**没人去渲染它**，
    于是 `architecture.png` 根本不存在，论文里那幅架构图是空的。
    agent 同时手写了 `latex_includes.tex`，把"没渲染"这件事**掩盖**了。
    """
    ws = Path(workspace)
    inc = ws / SPEC_DIR / "latex_includes.tex"
    if not rep.rendered:
        return inc

    block = [MERGE_MARKER]
    block.append("%% 由 FigureSpec 确定性渲染（ARIS figure-spec，MIT License）")
    block.append(r"\graphicspath{{../figures/}{figures/}}")
    block.append("")
    for i, item in enumerate(rep.rendered, 1):
        rel = item.get("png")
        if not rel:
            continue
        fname = Path(rel).name
        cap = pb._tex_escape(str(item.get("caption") or Path(fname).stem))
        block += [
            "%% 源：" + str(item.get("spec", "")),
            r"\begin{figure}[htbp]",
            r"  \centering",
            f"  \\includegraphics[width=14cm,height=9.5cm,keepaspectratio]{{{fname}}}",
            f"  \\caption{{{cap}}}",
            f"  \\label{{fig:fspec_{i}}}",
            r"\end{figure}",
            "",
        ]

    old = inc.read_text(encoding="utf-8", errors="replace") if inc.is_file() else ""
    if MERGE_MARKER in old:                      # 幂等：去掉上次的区块
        old = old.split(MERGE_MARKER)[0].rstrip() + "\n"

    inc.parent.mkdir(parents=True, exist_ok=True)
    inc.write_text(old.rstrip() + "\n\n" + "\n".join(block), encoding="utf-8")
    rep.includes_tex = inc
    return inc


def build_figures(workspace: Path, *, python: Optional[str] = None,
                  convert_png: bool = True, merge: bool = False) -> FigurePipelineReport:
    """一站式：发现 → 校验 → 渲染 → 写 `latex_includes.tex`。

    Args:
        merge: True 时**追加**到已有文件（保留 agent 手写内容）；False 整体重写。
    """
    rep = render_specs(workspace, python=python, convert_png=convert_png)
    if merge:
        merge_latex_includes(workspace, rep)
    else:
        write_latex_includes(workspace, rep)
    return rep


# ---------------------------------------------------------------------------
# 供步骤执行器用的门控辅助
# ---------------------------------------------------------------------------


def check_pipeline_output(workspace: Path) -> tuple[bool, str, list[str]]:
    """检查 `paper-figure-drawio` 步骤的产出是否合格。

    Returns:
        (ok, reason, missing)
    """
    ws = Path(workspace)
    inc = ws / SPEC_DIR / "latex_includes.tex"
    if not inc.is_file():
        return False, "缺少 figures/latex_includes.tex", ["figures/latex_includes.tex"]
    size = inc.stat().st_size
    if size < 500:
        return False, f"latex_includes.tex 仅 {size} 字节（要求 ≥500）", []
    return True, f"latex_includes.tex {size} 字节", []


__all__ = [
    "FigurePipelineReport", "render_specs", "write_latex_includes",
    "merge_latex_includes", "build_figures", "find_specs",
    "check_pipeline_output", "SPEC_DIR", "SPEC_SUFFIXES", "SECTION_TITLE",
    "MERGE_MARKER",
]
