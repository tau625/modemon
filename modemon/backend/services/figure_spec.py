"""确定性图表生成：FigureSpec JSON → SVG → PNG。

这是对上游 **ARIS** `skills/figure-spec` 的接入封装。

许可（必须随分发保留）
--------------------
上游采用 **MIT License**：

    MIT License
    Copyright (c) 2026 wanshuiyin

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.

完整文本见 `modemon/LICENSE-ARIS.txt`。

为什么要它
----------
`paper-figure-drawio` 步骤此前反复卡死：让 agent **手写 TikZ** 再反复
「编译→渲染→看图→改」，每次迭代 20–40 秒且无上界。

ARIS 的 `figure-spec` 走的是**确定性渲染**路线：

    同一份 FigureSpec JSON → 同一份 SVG（固定渲染器版本 + 字体）

没有迭代、没有视觉猜测、不需要绘图 API，而且 SVG 是纯文本可后编辑。
这正是「画图」这件事该有的做法。

本模块补的是**最后一公里**：LaTeX 的 `\\includegraphics` 需要位图，
所以还要 SVG → PNG。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

#: 上游标识（血缘追溯）
UPSTREAM_REPO = "wanshuiyin/Auto-claude-code-research-in-sleep"
UPSTREAM_LICENSE = "MIT"
UPSTREAM_COPYRIGHT = "Copyright (c) 2026 wanshuiyin"

_HERE = Path(__file__).resolve()
#: ARIS 的确定性渲染器（原样保留，未修改）
RENDERER_PATH = _HERE.parents[2] / "skills" / "figure-spec" / "scripts" / "figure_renderer.py"

#: SVG → PNG 的候选转换器
_EDGE_CANDIDATES = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)


@dataclass
class RenderResult:
    ok: bool = False
    svg: Optional[Path] = None
    png: Optional[Path] = None
    notes: list[str] = field(default_factory=list)
    error: str = ""

    def as_dict(self) -> dict:
        return {"ok": self.ok,
                "svg": str(self.svg) if self.svg else None,
                "png": str(self.png) if self.png else None,
                "error": self.error, "notes": self.notes}


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------


def find_renderer() -> Optional[Path]:
    return RENDERER_PATH if RENDERER_PATH.is_file() else None


def render_svg(spec: Path | dict, out_svg: Path,
               *, python: Optional[str] = None) -> tuple[bool, str]:
    """FigureSpec → SVG（调用 ARIS 的确定性渲染器）。

    Returns:
        (ok, message)
    """
    exe = find_renderer()
    if exe is None:
        return False, f"找不到 ARIS 渲染器：{RENDERER_PATH}"

    if isinstance(spec, dict):
        spec_path = out_svg.with_suffix(".spec.json")
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    else:
        spec_path = Path(spec)
        if not spec_path.is_file():
            return False, f"spec 不存在：{spec_path}"

    out_svg.parent.mkdir(parents=True, exist_ok=True)
    py = python or _default_python()
    cmd = [py, str(exe), "render", str(spec_path), "--output", str(out_svg)]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=120,
                           encoding="utf-8", errors="replace")
    except Exception as exc:
        return False, f"渲染器调用失败：{exc}"

    if p.returncode != 0 or not out_svg.is_file():
        return False, f"渲染失败 rc={p.returncode}: {(p.stderr or p.stdout or '')[:300]}"
    return True, (p.stdout or "").strip()


def validate_spec(spec: Path | dict, *, python: Optional[str] = None) -> tuple[bool, str]:
    """校验 FigureSpec 合法性。"""
    exe = find_renderer()
    if exe is None:
        return False, f"找不到 ARIS 渲染器：{RENDERER_PATH}"
    if isinstance(spec, dict):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="fspec-") as td:
            p = Path(td) / "s.json"
            p.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
            return validate_spec(p, python=python)
    py = python or _default_python()
    r = subprocess.run([py, str(exe), "validate", str(spec)],
                       capture_output=True, timeout=60,
                       encoding="utf-8", errors="replace")
    return r.returncode == 0, (r.stdout or r.stderr or "").strip()


# ---------------------------------------------------------------------------
# SVG → PNG
# ---------------------------------------------------------------------------


def find_svg_converter() -> Optional[str]:
    """找一个能把 SVG 渲染成 PNG 的工具。

    ⚠️ **不要认 `convert`**：Windows `system32\\convert.exe` 是磁盘格式转换器，
    不是 ImageMagick。实测核对过——同名不同物，认错会静默失败。
    """
    env = os.environ.get("MODEMON_SVG_CONVERTER")
    if env and Path(env).is_file():
        return env
    for c in _EDGE_CANDIDATES:
        if Path(c).is_file():
            return c
    return None


def svg_to_png(svg: Path, png: Path, *,
               width: int = 0, height: int = 0,
               converter: Optional[str] = None) -> tuple[bool, str]:
    """SVG → PNG（用无头浏览器截图）。

    本机没有 cairosvg/Inkscape/ImageMagick，但 Edge/Chrome 可以无头渲染。
    """
    svg, png = Path(svg), Path(png)
    if not svg.is_file():
        return False, f"SVG 不存在：{svg}"

    tool = converter or find_svg_converter()
    if not tool:
        return False, "没有可用的 SVG→PNG 转换器（试过 Edge/Chrome；不认 system32\\convert）"

    # 从 SVG 头里读尺寸作为截图窗口
    if not (width and height):
        try:
            head = svg.read_text(encoding="utf-8", errors="replace")[:400]
            import re
            w = re.search(r'width="(\d+)"', head)
            h = re.search(r'height="(\d+)"', head)
            width = int(w.group(1)) if w else 720
            height = int(h.group(1)) if h else 320
        except Exception:
            width, height = width or 720, height or 320

    png.parent.mkdir(parents=True, exist_ok=True)
    url = "file:///" + str(svg).replace("\\", "/")
    cmd = [tool, "--headless=new", "--disable-gpu", "--hide-scrollbars",
           "--no-sandbox", "--disable-extensions",
           f"--screenshot={png}", f"--window-size={width},{height}",
           "--default-background-color=FFFFFFFF", url]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=120,
                           encoding="utf-8", errors="replace")
    except Exception as exc:
        return False, f"截图失败：{exc}"

    if not png.is_file():
        return False, f"未产出 PNG：{(p.stderr or '')[:200]}"
    return True, f"{png.stat().st_size} bytes"


# ---------------------------------------------------------------------------
# 一站式
# ---------------------------------------------------------------------------


def render_figure(spec: Path | dict, out_prefix: Path, *,
                  python: Optional[str] = None,
                  convert_png: bool = True) -> RenderResult:
    """FigureSpec → SVG（+ PNG）。"""
    res = RenderResult()
    out_prefix = Path(out_prefix)
    svg = out_prefix.with_suffix(".svg")
    ok, msg = render_svg(spec, svg, python=python)
    if not ok:
        res.error = msg
        return res
    res.svg = svg
    res.notes.append("SVG 已生成（ARIS 确定性渲染器）")

    if convert_png:
        png = out_prefix.with_suffix(".png")
        ok2, msg2 = svg_to_png(svg, png)
        if ok2:
            res.png = png
            res.notes.append(f"PNG 已生成：{msg2}")
        else:
            # PNG 失败**不阻塞**——SVG 本身是可交付的
            res.notes.append(f"PNG 转换失败（SVG 仍可用）：{msg2}")

    res.ok = True
    return res


def describe() -> dict:
    """当前环境的图表生成能力。"""
    return {
        "renderer": str(find_renderer() or ""),
        "renderer_present": find_renderer() is not None,
        "svg_converter": find_svg_converter() or "",
        "upstream": {"repo": UPSTREAM_REPO, "license": UPSTREAM_LICENSE,
                     "copyright": UPSTREAM_COPYRIGHT,
                     "license_file": "LICENSE-ARIS.txt"},
    }


def _default_python() -> str:
    """用随包 Python（科学计算环境齐备）；找不到则退回当前解释器。"""
    p = Path(os.environ.get("MODEMON_MH_ROOT",
                            r"E:\02_Installers\DailyApps\Modex-MH-Agent"))
    exe = p / "runtime" / "python" / ("python.exe" if os.name == "nt" else "python")
    return str(exe) if exe.is_file() else "python"


__all__ = ["RenderResult", "render_figure", "render_svg", "validate_spec",
           "svg_to_png", "find_renderer", "find_svg_converter", "describe",
           "RENDERER_PATH", "UPSTREAM_REPO", "UPSTREAM_LICENSE", "UPSTREAM_COPYRIGHT"]
