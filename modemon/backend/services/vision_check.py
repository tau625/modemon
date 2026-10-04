"""排版/图表视觉自检。

对应蓝方的 `tools/tikz_vision_check.py` 与 `tools/data_fig_vision_check.py`。
本模块按**恢复到的原文规格**实现，不是凭印象设计。

================================================================
⚠️ 最重要的一条工程教训（原文 docstring 完整记载）
================================================================
vision 自检**必须是「加分项」，不是「硬门槛」**。

蓝方早期的判决是「首行非纯 PASS 即 FAIL」，而检查提示词里带主观项
（"有没有大片空白""整体是否美观"）——几何图几乎必然被挑出至少一条问题，
于是每张图烧满 2 轮重新编译，表现为"画完卡很久"。
根因就在 vision 侧，不在编译侧。

修复口径：**只认结构化的 `ISSUE n:` 标记**，其余（空回复 / 泛泛肯定 /
无法解析 / 明确 PASS）一律放行。

================================================================
退出码契约（对齐原文）
================================================================
    0 = 通过（PASS）
    1 = 有问题（输出具体问题描述）
    2 = API 不可用（未配置 key 或调用失败）
"""

from __future__ import annotations

import base64
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

# ---------------------------------------------------------------------------
# 原文规格常量
# ---------------------------------------------------------------------------

#: 图片体积防御：vision API 单图通常限制 ~5MB；base64 放大约 33%，
#: 所以原图阈值留到 3.5MB。超过则用 PIL 等比压缩。
_MAX_IMG_BYTES = 3_500_000

#: 判决正则：**只认结构化标记**
ISSUE_RE = re.compile(r"(?mi)^\s*ISSUE\s*\d*\s*[:：]")

#: TikZ 图的 7 项检查（原文逐字）
TIKZ_CHECK_ITEMS: tuple[str, ...] = (
    "文字是否被截断、重叠或超出节点边框？",
    "连线上的标注文字是否跟节点重叠或被遮挡？",
    "节点间距是否均匀，有没有挤在一起的？",
    "有没有大片空白区域（布局不紧凑）？",
    "箭头方向是否合理，有没有连线穿过节点？",
    "对齐是否整齐：本应竖直成一列的节点有没有明显左右错开？"
    "本应水平成一行的节点有没有明显上下参差？"
    "连线是否明显歪斜、没接在节点中央？并列节点大小是否明显不一？"
    "（只报肉眼一眼可见的错位，不必追究几像素的细微差别）",
    "整体是否美观、专业、适合放在学术论文中？",
)

#: 数据图的检查项（同口径：只报客观缺陷）
DATA_FIG_CHECK_ITEMS: tuple[str, ...] = (
    "中文文字是否显示为方框、乱码或缺失（这是最严重的问题）？",
    "坐标轴刻度、轴标题、图例文字是否被截断或重叠？",
    "数据点/柱条/曲线是否超出绘图区或被裁剪？",
    "图例是否遮挡了数据内容？",
    "颜色区分是否清晰可辨（相近颜色是否难以区分）？",
    "文字大小是否适合印在学术论文中（是否小到看不清）？",
    "整体是否专业、适合放在学术论文中？",
)

#: 论文整页的检查项
PAGE_CHECK_ITEMS: tuple[str, ...] = (
    "中文文字是否显示为方框、乱码或缺失？",
    "是否出现大片空白、标题孤立在页尾而内容在下一页？",
    "表格/图片是否被裁剪、溢出页边距或压住文字？",
    "图表标题（图 n / 表 n）是否与对应的图表放在一起？",
    "段落缩进、字号层级是否一致、专业？",
    "公式是否被截断、错位或与正文重叠？",
    "整体是否符合中文数学建模竞赛论文的排版规范？",
)

REPLY_INSTRUCTION = (
    "\n如果全部没问题，只回答一个词：PASS\n"
    "如果有问题，逐条列出每个问题的具体位置和描述，格式：\n"
    "ISSUE 1: [位置] [问题描述]\n"
)


# ---------------------------------------------------------------------------
# 判决
# ---------------------------------------------------------------------------


def verdict(reply: str) -> int:
    """把 vision 回复映射成退出码。

    对齐 drawio_vision 的口径：**vision 是「加分项」不是「硬门槛」** ——
    只在出现结构化 `ISSUE n:` 标记时才判 FAIL，
    泛泛评论 / 无法解析 / 空回复一律放行（0）。

    ⛔ 旧逻辑是「首行非纯 PASS 即 FAIL」，配合提示词里的主观项
       （大片空白 / 是否美观），几何图永远被挑出至少一条 →
       每张烧满 2 轮重编，是「画完卡很久」的 vision 侧根因。
    """
    if not reply or not reply.strip():
        return 0
    m = ISSUE_RE.search(reply)
    if m:
        return 1
    return 0  # 含 PASS / 泛泛肯定 / 无法解析 → 保守放行，不阻塞


def extract_issues(reply: str) -> list[str]:
    """抽出结构化的 `ISSUE n: ...` 条目。"""
    if not reply:
        return []
    out = []
    for line in reply.splitlines():
        if ISSUE_RE.match(line):
            out.append(line.strip())
    return out


# ---------------------------------------------------------------------------
# 图片读取与体积防御
# ---------------------------------------------------------------------------


def load_image(path: Path) -> Optional[tuple[str, str]]:
    """读取图片 → (base64, mime)。

    超过阈值时用 PIL 等比压缩，避免超 vision API 单图限制；
    PIL 缺失或压缩失败则回退原图。返回 None 表示无法读取（调用方据此跳过）。
    """
    p = Path(path)
    if not p.is_file():
        return None
    try:
        raw = p.read_bytes()
    except OSError:
        return None
    if not raw:
        return None

    suffix = p.suffix.lower()
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp", ".gif": "image/gif"}.get(suffix, "image/png")

    if len(raw) > _MAX_IMG_BYTES:
        try:
            from PIL import Image  # type: ignore
            import io

            with Image.open(p) as im:
                im = im.convert("RGB")
                # 等比缩到体积达标（粗调：按面积线性缩）
                scale = (_MAX_IMG_BYTES / len(raw)) ** 0.5
                w, h = im.size
                im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))),
                               Image.LANCZOS)
                buf = io.BytesIO()
                im.save(buf, format="PNG", optimize=True)
                raw = buf.getvalue()
                mime = "image/png"
        except Exception:
            pass  # 压缩失败回退原图（原文行为）

    return base64.b64encode(raw).decode("ascii"), mime


# ---------------------------------------------------------------------------
# 提示词组装
# ---------------------------------------------------------------------------


def build_prompt(items: Sequence[str], *, subject: str = "这张图") -> str:
    lines = [f"请检查{subject}的排版质量，逐项判断：", ""]
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. {it}")
    lines.append(REPLY_INSTRUCTION)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 后端：可插拔
# ---------------------------------------------------------------------------


@dataclass
class VisionResult:
    ok: bool = True
    #: pass | issue | skipped | error
    verdict: str = "skipped"
    issues: list[str] = field(default_factory=list)
    raw_reply: str = ""
    backend: str = ""
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"ok": self.ok, "verdict": self.verdict, "issues": self.issues,
                "backend": self.backend, "notes": self.notes,
                "raw_reply": self.raw_reply[:500]}


class VisionBackend:
    """视觉后端接口。返回模型的文字回复；失败时抛异常。"""

    name = "base"

    def describe(self) -> str:
        return self.name

    def ask(self, image_b64: str, mime: str, prompt: str) -> str:  # pragma: no cover
        raise NotImplementedError


class OpenAIBackend(VisionBackend):
    """直连 OpenAI 兼容的 vision API。

    凭据优先级（原文）：`EDITOR_AI_API_KEY`+`EDITOR_AI_BASE_URL` 优先，
    回退 `OPENAI_API_KEY`+`OPENAI_BASE_URL`。
    """

    name = "openai"

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self.model = model
        self.api_key = (os.environ.get("EDITOR_AI_API_KEY")
                        or os.environ.get("OPENAI_API_KEY"))
        self.base_url = (os.environ.get("EDITOR_AI_BASE_URL")
                         or os.environ.get("OPENAI_BASE_URL")
                         or "https://api.openai.com/v1")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def ask(self, image_b64: str, mime: str, prompt: str) -> str:
        import json
        import urllib.request

        if not self.api_key:
            raise RuntimeError("未配置 EDITOR_AI_API_KEY / OPENAI_API_KEY")

        body = {
            "model": self.model,
            "max_tokens": 800,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url",
                     "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                ],
            }],
        }
        req = urllib.request.Request(
            self.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode("utf-8"))
        return ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""


class AgentVisionBackend(VisionBackend):
    """用 Claude Code 自己看图。

    为什么需要它：agent 的 `Read` 工具**能看图片**（实测中它确实
    `Read .../page-1.png` 并据此修正 TikZ）。于是视觉自检不必依赖
    外部 vision API —— 在没有 OPENAI 类凭据的环境里也能跑。
    """

    name = "agent"

    def __init__(self, model: Optional[str] = None) -> None:
        self.model = model

    @property
    def available(self) -> bool:
        return self._find_exe() is not None

    def _find_exe(self) -> Optional[str]:
        for rel in (r"runtime\node\node_modules\@anthropic-ai\claude-code\bin\claude.exe",):
            p = Path(os.environ.get("MODEMON_MH_ROOT",
                                    r"E:\02_Installers\DailyApps\Modex-MH-Agent")) / rel
            if p.is_file():
                return str(p)
        import shutil
        return shutil.which("claude")

    def ask(self, image_b64: str, mime: str, prompt: str) -> str:
        # 不直接传 base64（占上下文），而是把图写到临时文件让 agent Read
        raise RuntimeError("AgentVisionBackend 走 ask_image()")


def choose_backend(prefer: Optional[str] = None) -> VisionBackend:
    """挑一个可用后端：优先 OpenAI 兼容 vision API，退回到 agent 自看图。"""
    if prefer == "openai":
        return OpenAIBackend()
    if prefer == "agent":
        return AgentVisionBackend()
    ob = OpenAIBackend()
    if ob.available:
        return ob
    return AgentVisionBackend()


# ---------------------------------------------------------------------------
# 视觉能力标定（★ 防止"假 PASS"）
# ---------------------------------------------------------------------------

#: 标定探针里写的文字。模型能读出它才说明真看得见图。
_PROBE_TEXT = "42"


def _make_probe_png(target: Path) -> bool:
    """生成一张带已知文字的小图，用于标定模型是否真能看图。"""
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore
    except Exception:
        return False
    try:
        im = Image.new("RGB", (320, 160), "white")
        d = ImageDraw.Draw(im)
        try:
            font = ImageFont.truetype("arial.ttf", 96)
        except Exception:
            font = ImageFont.load_default()
        d.text((90, 20), _PROBE_TEXT, fill="black", font=font)
        target.parent.mkdir(parents=True, exist_ok=True)
        im.save(str(target))
        return True
    except Exception:
        return False


_VISION_CAPABILITY: dict[str, Optional[bool]] = {}


def check_vision_capability(backend: Optional[VisionBackend] = None) -> bool:
    """**标定**：这个后端到底能不能看见图？

    为什么必须做：实测中模型不支持图像输入时，agent 的 `Read` 读到的是
    无用信息，模型只能凭提示词文字回答 **PASS** —— 于是一张中文全变方框的图
    被判成通过。这比不检查更糟，它给的是**虚假信心**。

    所以先问一张图里写的是什么数字（答案是 42）。答不上来就认定
    「视觉不可用」，调用方应报 `skipped` 而不是 `pass`。
    """
    be = backend or choose_backend()
    key = be.name + ":" + (getattr(be, "model", "") or "")
    if key in _VISION_CAPABILITY:
        return bool(_VISION_CAPABILITY[key])

    with tempfile.TemporaryDirectory(prefix="visionprobe-") as td:
        probe = Path(td) / "probe.png"
        if not _make_probe_png(probe):
            _VISION_CAPABILITY[key] = None
            return False
        try:
            if isinstance(be, AgentVisionBackend):
                reply = _ask_via_agent(probe, "这张图里写的是什么数字？只回答数字本身。")
            else:
                img = load_image(probe)
                if img is None:
                    _VISION_CAPABILITY[key] = None
                    return False
                reply = be.ask(img[0], img[1],
                               "这张图里写的是什么数字？只回答数字本身。")
        except Exception:
            _VISION_CAPABILITY[key] = None
            return False

    ok = _PROBE_TEXT in (reply or "")
    _VISION_CAPABILITY[key] = ok
    return ok


def reset_capability_cache() -> None:
    _VISION_CAPABILITY.clear()


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def check_image(
    path: Path,
    *,
    items: Sequence[str] = DATA_FIG_CHECK_ITEMS,
    subject: str = "这张图",
    backend: Optional[VisionBackend] = None,
) -> VisionResult:
    """对一张图做视觉自检。

    **永不抛异常**：任何失败都降级成 `verdict=skipped`，不阻塞主流程
    （对应原文「校验失败不得阻塞主流程」）。
    """
    res = VisionResult()
    img = load_image(path)
    if img is None:
        res.notes.append(f"图片无法读取，跳过：{path}")
        res.verdict = "skipped"
        return res

    b64, mime = img
    prompt = build_prompt(items, subject=subject)
    be = backend or choose_backend()
    res.backend = be.name

    # ★ 先标定视觉能力。答不出探针内容 = 看不见图 = 不能信任回复。
    #   不做这一步，模型看不了图就会一律回答 PASS，
    #   于是中文变方框的图也被判通过（实测过）。
    if not check_vision_capability(be):
        res.verdict = "skipped"
        res.ok = True
        res.notes.append("vision 不可用（模型无法真正读取图像）——跳过而非放行")
        return res

    try:
        if isinstance(be, AgentVisionBackend):
            reply = _ask_via_agent(path, prompt)
        else:
            reply = be.ask(b64, mime, prompt)
    except Exception as exc:
        res.notes.append("vision 调用失败：%s" % exc)
        res.verdict = "skipped"      # ← 不阻塞
        res.ok = True
        return res

    res.raw_reply = reply or ""
    code = verdict(reply)
    if code == 0:
        res.verdict = "pass"
        res.ok = True
    else:
        res.verdict = "issue"
        res.ok = False
        res.issues = extract_issues(reply)
    return res


def _ask_via_agent(image_path: Path, prompt: str) -> str:
    """让 Claude Code 看图并回答（不依赖外部 vision API）。

    ⚠️ 提示词必须**内联**到 `-p`，不能写成临时文件再让 agent 读——
    临时目录在 agent 的允许工作目录之外，`Read` 会被权限拦截，
    agent 就拿不到检查清单与 `ISSUE n:` 格式要求，只能给泛泛评论；
    而按判决口径泛泛评论一律放行，于是**什么都看不出来**（实测过）。
    """
    exe = AgentVisionBackend()._find_exe()
    if not exe:
        raise RuntimeError("找不到 claude 可执行文件")

    from . import tool_env as te

    env, _rep = te.prepare_child_env()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    msg = (f"请用 Read 工具查看图片 `{image_path}`，然后按下面的要求作答。\n\n"
           f"{prompt}\n\n"
           "只按上面的格式回答，不要输出额外说明。")

    cmd = [
        exe, "-p", msg,
        "--output-format", "json",
        "--bare",
        "--permission-mode", "acceptEdits",
        "--mcp-config", '{"mcpServers": {}}',
        "--strict-mcp-config",
        "--max-budget-usd", "0.30",
    ]
    p = subprocess.run(cmd, cwd=str(image_path.parent), env=env,
                       capture_output=True, timeout=300,
                       encoding="utf-8", errors="replace")
    try:
        import json
        data = json.loads(p.stdout)
        return data.get("result") or ""
    except Exception:
        return (p.stdout or "")[-2000:]


def check_paper_pdf(
    pdf: Path,
    *,
    max_pages: int = 12,
    backend: Optional[VisionBackend] = None,
) -> list[VisionResult]:
    """把 PDF 逐页渲染成图并做视觉自检。"""
    out: list[VisionResult] = []
    try:
        import fitz  # type: ignore
    except Exception as exc:
        r = VisionResult(notes=["需要 PyMuPDF：%s" % exc])
        return [r]

    pdf = Path(pdf)
    if not pdf.is_file():
        return [VisionResult(notes=["PDF 不存在：%s" % pdf])]

    with tempfile.TemporaryDirectory(prefix="pagevision-") as td:
        doc = fitz.open(str(pdf))
        for i in range(min(doc.page_count, max_pages)):
            img_path = Path(td) / ("page%02d.png" % (i + 1))
            doc[i].get_pixmap(dpi=110).save(str(img_path))
            r = check_image(img_path, items=PAGE_CHECK_ITEMS,
                            subject=f"论文第 {i + 1} 页", backend=backend)
            r.notes.append("page=%d" % (i + 1))
            out.append(r)
        doc.close()
    return out


def check_figure(path: Path, *, tikz: bool = False,
                 backend: Optional[VisionBackend] = None) -> VisionResult:
    """数据图 / TikZ 图自检。"""
    items = TIKZ_CHECK_ITEMS if tikz else DATA_FIG_CHECK_ITEMS
    subject = "这张 TikZ 流程图" if tikz else "这张数据图"
    return check_image(Path(path), items=items, subject=subject, backend=backend)


# ---------------------------------------------------------------------------
# CLI：对齐原文的退出码契约
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="排版/图表视觉自检")
    ap.add_argument("path", help="图片或 PDF")
    ap.add_argument("--kind", choices=("fig", "tikz", "page", "pdf"), default="fig")
    ap.add_argument("--backend", choices=("openai", "agent"), default=None)
    ap.add_argument("--max-pages", type=int, default=12)
    a = ap.parse_args(argv)

    path = Path(a.path)
    be = choose_backend(a.backend) if a.backend else choose_backend()

    if a.kind in ("pdf", "page") or path.suffix.lower() == ".pdf":
        results = check_paper_pdf(path, max_pages=a.max_pages, backend=be)
    else:
        results = [check_figure(path, tikz=(a.kind == "tikz"), backend=be)]

    if any(r.verdict == "skipped" for r in results) and \
            all(r.verdict == "skipped" for r in results):
        for r in results:
            for n in r.notes:
                print("  note: %s" % n)
        print("API 不可用或图片无法读取（退出码 2）")
        return 2

    had_issue = False
    for r in results:
        tag = {"pass": "PASS", "issue": "ISSUE", "skipped": "SKIP",
               "error": "ERR"}.get(r.verdict, "?")
        page = next((n for n in r.notes if n.startswith("page=")), "")
        print("[%s] %s backend=%s" % (tag, page, r.backend))
        for it in r.issues:
            print("   %s" % it)
        for n in r.notes:
            if not n.startswith("page="):
                print("   note: %s" % n)
        if r.verdict == "issue":
            had_issue = True

    return 1 if had_issue else 0


if __name__ == "__main__":
    raise SystemExit(main())
