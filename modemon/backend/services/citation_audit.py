"""引用审计（接入上游 ARIS 的 `citation-audit` skill）。

许可（必须随分发保留）
----------------------
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

skill 正文本体在 `modemon/skills/citation-audit/SKILL.md`：取自
`api.github.com/repos/wanshuiyin/Auto-claude-code-research-in-sleep`，
blob `693698d325223dea72ecfbdeee3778e3d0080fd3`，**31067 字节**，
SHA256 `7f68355f009a93077c76ba8d999cc00df0a3a87fbe3e4cba1b5f5e0df0810c2e`，
逐字节原样保留、未改一字（`UPSTREAM_BYTES` 有测试断言把门）。

为什么需要它
------------
竞赛论文的引用规范是**硬性要求**，而在本模块接入前流水线**完全没有引用校验**
（`reports/26-project-review-gaps.md` §6 认定的最高优先 ARIS 缺口）。

上游 skill 归纳的引用失败模式（**都不是蓄意欺骗**，而是缺少完整性约束的
agent 的失败模式）：

1. **幻觉引用** —— 条目根本不存在（编造作者 / 期刊 / DOI），最严重
2. **元数据漂移** —— 论文真实存在，但作者 / 年份 / 会议名写错
3. **版本错配** —— 引的是 arXiv v1，却按 v3 的结论描述
4. **语境错配** —— 论文真实存在，但它并不支持被引处的那句论断
5. **cite-key 冲突 / 未引用条目** —— key 重名，或 bib 里有从未被引的条目

本模块在竞赛流水线里的位置：`comp-paper-zh`（或英文对应步骤）产出论文之后，
由**独立的第二遍** agent 读参考文献与正文引用做审计。

⚠️ 独立性是关键
--------------
上游原文（Thread independence）：

    Every invocation uses a fresh `mcp__codex__codex` thread. Never
    `codex-reply`. Do not accept prior audit outputs (PROOF_AUDIT,
    PAPER_CLAIM_AUDIT, EXPERIMENT_LOG) as input — the fresh thread preserves
    reviewer independence.

以及正文顶部的硬约束：

    > 🔒 **Do not wrap this skill in `/loop`, `/schedule`, or `CronCreate`.**
    > It is verdict-bearing — it judges bibliographic correctness.

对应到 modemon：**审计必须是新的一次 agent 调用（命令不带 `--resume`）**，
审计者不参与论文产出；审计**永不抛异常**，任何失败只降级为 `skipped`。

与 `result_audit.py` 的关系
--------------------------
结构**刻意对齐** `services/result_audit.py`（同一套判决口径、同一套降级语义），
差别只在审计对象——那边审 `figures/all_results.json` 的**数值诚信**，
这边审 `paper/references.md` / `paper/sections/*.md` / `paper/main.tex`
的**引用诚信**。
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

#: 上游标识（血缘追溯用）
UPSTREAM_REPO = "wanshuiyin/Auto-claude-code-research-in-sleep"
UPSTREAM_LICENSE = "MIT"
UPSTREAM_COPYRIGHT = "Copyright (c) 2026 wanshuiyin"
UPSTREAM_SKILL = "citation-audit"

#: 取回时的 git blob sha 与字节数（正文落地校验用）
UPSTREAM_BLOB_SHA = "693698d325223dea72ecfbdeee3778e3d0080fd3"
UPSTREAM_BYTES = 31067
UPSTREAM_SHA256 = ("7f68355f009a93077c76ba8d999cc00df0a3a87fbe3e4cba1b5f5e0df0810c2e")

#: 默认预算 / 超时。
#:
#: 都给足：`citation-audit` 正文本体 **31067 字节**（约 experiment-audit 12.7 KB
#: 的 2.4 倍），加上工作区清单、逐条目核对与多轮推理，给少了会以
#: `error_max_budget_usd` / 超时收场，两者都表现为**空回复**
#: （experiment-audit 已实测踩过：$0.8 + 600 s → 空回复）。
DEFAULT_MAX_BUDGET_USD = 2.0
DEFAULT_TIMEOUT_S = 1200

_HERE = Path(__file__).resolve()
SKILL_PATH = _HERE.parents[2] / "skills" / "citation-audit" / "SKILL.md"

#: 【供 Lead 接线】产出论文后需要做**引用审计**的步骤。
#:
#: - `comp-paper-zh` / `comp-paper-en` / `comp-paper-huawei`：论文撰写步骤，
#:   审计对象此时才存在（`paper/**`）。
#: - `comp-review`：任务要求在此步骤后也触发。它在中文序列里**位于论文撰写
#:   之前**（`_COMMON_HEAD_STEPS` 末尾），因此**只有**在论文已存在时才会
#:   真正开跑；否则由「未发现引用文件」闸门降级为 `skipped`，**不报假通过**。
CITATION_AUDIT_SKILLS: frozenset[str] = frozenset({
    "comp-paper-zh", "comp-paper-en", "comp-paper-huawei", "comp-review",
})

#: 【供 Lead 接线】落库 / 广播用的事件 kind（`chat_run_events.kind`）。
CITATION_AUDIT_EVENT_KIND = "citation_audit"

#: 只认**结构化标记**（与 `result_audit` / vision 自检同一取舍）：
#: 评审是「加分项」不是「硬门槛」，泛泛评论必须放行，
#: 否则审计会变成"永远挑出一条"的橡皮图章式否决。
ISSUE_RE = re.compile(r"(?mi)^\s*(?:ISSUE|FINDING)\s*\d*\s*[:：]")

#: 上游报告形态的结构化标记：`## Priority Fixes` 下的
#: `### REMOVE: <key>` / `### REPLACE-CONTEXT: <key> in file:line` / `### FIX: <key>`。
#: 这些是**逐条目判决**，属于结构化证据，同样判失败
#: （判决口径见上游 "Verdict decision table"：REPLACE/REMOVE → FAIL）。
FIX_RE = re.compile(
    r"(?mi)^\s*#{0,4}\s*(?:REMOVE|REPLACE-CONTEXT|REPLACE|FIX)\s*[:：]\s*\S")

#: 顶层结论（上游 `CITATION_AUDIT.json` 的 `verdict` 字段取值）。
#:
#: `PASS | WARN | FAIL | NOT_APPLICABLE | BLOCKED | ERROR`
TOP_VERDICT_RE = re.compile(
    r"(?im)^\s*(?:CITATION_VERDICT|VERDICT|结论)\s*[:：]\s*([A-Za-z_\u4e00-\u9fff]+)")

#: 顶层结论 = 硬失败：只要出现 REPLACE/REMOVE 级问题即为 FAIL。
FAIL_TOP_VERDICTS = frozenset({"FAIL"})

#: 顶层结论 = **审计没跑成**（不是通过）。照实降级为 `skipped`：
#: `NOT_APPLICABLE`（论文里没有可审的引用）、`BLOCKED`（bib 读不了）、
#: `ERROR`（评审调用失败）。把它们当 `pass` 就是虚假信心。
NOT_RUN_TOP_VERDICTS = frozenset({"NOT_APPLICABLE", "BLOCKED", "ERROR"})

#: 待审引用文件（相对工作区）。顺序即优先级：先 bib / 参考文献，再正文。
TARGET_PATTERNS: tuple[str, ...] = (
    "paper/references.md", "paper/references.tex", "paper/refs.md",
    "paper/reference.md", "paper/ref.md",
    "paper/*.bib", "references.bib", "refs.bib", "references.md",
    "paper/main.tex", "paper/main.md",
    "paper/sections/*.md", "paper/sections/*.tex",
    "paper/references/*.md", "paper/ref/*.md",
    "sections/*.md", "sections/*.tex",
)

_SKIP_PARTS = frozenset({
    ".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
})


@dataclass
class CitationAuditResult:
    """一次引用审计的结论。"""

    ok: bool = True
    #: pass | issue | skipped
    verdict: str = "skipped"
    #: 上游顶层结论原文（PASS/WARN/FAIL/NOT_APPLICABLE/BLOCKED/ERROR，可能为空）
    top_verdict: str = ""
    issues: list[str] = field(default_factory=list)
    raw_reply: str = ""
    skill_used: str = ""
    notes: list[str] = field(default_factory=list)
    #: 本次实际审到的引用文件（相对路径）
    targets: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"ok": self.ok, "verdict": self.verdict,
                "top_verdict": self.top_verdict, "issues": self.issues,
                "skill_used": self.skill_used, "notes": self.notes,
                "targets": self.targets, "raw_reply": self.raw_reply[:600]}


# ---------------------------------------------------------------------------
# skill 正文
# ---------------------------------------------------------------------------


def load_skill_body() -> tuple[str, bool]:
    """读取 `citation-audit/SKILL.md` 正文（**去掉 frontmatter**）。

    Returns:
        (body, loaded)  loaded=False 表示正文尚未引入（骨架期）。
    """
    if SKILL_PATH.is_file():
        text = SKILL_PATH.read_text(encoding="utf-8", errors="replace")
        m = re.match(r"\A---\s*\n.*?\n---\s*\n?", text, re.S)
        return (text[m.end():] if m else text), True
    return "", False


def _fallback_prompt() -> str:
    """正文未引入时的最小审计契约（保证功能可用，不让流水线空转）。"""
    return """# 引用审计（最小契约）

请核对这篇论文的**参考文献**与**正文引用**是否真实、归属正确、语境相符：

1. **幻觉引用** —— 条目是否根本不存在（编造的作者 / 期刊 / DOI / 年份）？
2. **元数据漂移** —— 论文真实存在，但作者 / 年份 / 会议名是否写错？
3. **版本错配** —— 引的是 arXiv v1，却按 v3 的结论描述？
4. **语境错配** —— 被引论文**是否真的支持**被引处的那句论断？
5. **cite-key 冲突 / 未引用条目** —— key 是否重名？bib 里是否有从未被引的条目？

如果全部没问题，只回答一个词：PASS
如果有问题，逐条列出，格式：
ISSUE 1: [条目或文件:行号] [类别] [证据]
"""


# ---------------------------------------------------------------------------
# 审计对象
# ---------------------------------------------------------------------------


def collect_citation_targets(workspace: Path, *, limit: int = 60) -> list[tuple[str, int]]:
    """收集本次要审的引用相关文件：`[(相对路径, 字节数), ...]`。

    覆盖 `paper/references.md`（参考文献）、`paper/sections/*.md`（正文引用）、
    `paper/main.tex`（LaTeX 正文与 `\\cite{...}`）以及 `*.bib`。
    找不到就返回空列表——由调用方降级为 `skipped`，**不假装通过**。
    """
    ws = Path(workspace)
    seen: dict[str, int] = {}
    if not ws.is_dir():
        return []
    for pat in TARGET_PATTERNS:
        if len(seen) >= limit:
            break
        try:
            matches = sorted(ws.glob(pat))
        except (OSError, ValueError):
            continue
        for p in matches:
            if len(seen) >= limit:
                break
            if not p.is_file():
                continue
            try:
                rel = p.relative_to(ws)
            except ValueError:
                continue
            if any(part in _SKIP_PARTS for part in rel.parts):
                continue
            try:
                size = p.stat().st_size
            except OSError:
                continue
            seen.setdefault(rel.as_posix(), size)
    return sorted(seen.items())


def build_prompt(workspace: Path, *, targets: Optional[list[tuple[str, int]]] = None,
                 flags: tuple[str, ...] = ()) -> str:
    """拼出审计提示词：上游 skill 正文 + 待审文件清单 + **回复契约**。

    `flags` 用于切换上游模式（如 `--uncited` 未引用条目检测、
    `--soft-only` 只改写正文不动 bib）；默认空 = 上游标准模式。

    ⚠️ 回复契约必须显式写死：审计结论是**给引擎解析**的，
    不能让 agent 只给一段自然语言总结（那样判决会退化成"看谁写得像"）。
    """
    body, loaded = load_skill_body()
    if not loaded:
        body = _fallback_prompt()

    ws = Path(workspace)
    tgs = list(targets) if targets is not None else collect_citation_targets(ws)
    listing = "\n".join("- `%s`（%d 字节）" % (n, s) for n, s in tgs) \
        or "- （未发现引用相关文件——请如实报告 NOT_APPLICABLE，不要编造条目）"
    flag_line = ""
    if flags:
        flag_line = "\n调用模式：%s\n" % " ".join(str(f) for f in flags)

    return f"""{body}

---

## 本次审计对象（modemon 竞赛流水线）

工作目录：`{ws}`

待审计文件：
{listing}
{flag_line}
## 回复契约（引擎按此解析，**不要**只给自然语言结论）

1. **首行**给出顶层结论：`CITATION_VERDICT: <PASS|WARN|FAIL|NOT_APPLICABLE|BLOCKED|ERROR>`
   （取值口径见上文 skill 正文的 "Verdict decision table"）
2. 若所有条目的「存在性 / 元数据 / 语境」三轴均无问题：随后只回答一个词 `PASS`
3. 若发现问题：**逐条**列出，每行一条，格式为
   `ISSUE 1: [条目或文件:行号] [类别] [证据]`
   类别取 `hallucinated` / `metadata_drift` / `version_mismatch` /
   `wrong_context` / `key_conflict`
4. 结论同时落盘：`CITATION_AUDIT.md`（人读报告）+ `CITATION_AUDIT.json`（机读账本）

⚠️ 你**不是**这篇论文的产出者，你的职责是**独立判定**引用是否真实、归属正确、语境相符。
⚠️ 没有证据支持的推断不要写进报告；无法核实的条目如实标注 `unverified`，
**不要**为了让报告看起来完整而编造条目信息。
"""


# ---------------------------------------------------------------------------
# 判决口径
# ---------------------------------------------------------------------------


def verdict_of(reply: str) -> int:
    """把审计回复映射成 0=放行 / 1=有问题。

    与 `result_audit.verdict_of` 同口径：**只认结构化标记**
    （行首 `ISSUE n:` / `FINDING n:`，或上游报告里的 `### REMOVE:` /
    `### REPLACE-CONTEXT:` / `### FIX:` 逐条目判决行），
    泛泛评论、无法解析一律放行。

    ⚠️ 但**空回复不等于通过**：空说明审计根本没跑成，判 `pass` 是**虚假信心**。
    空回复交给调用方判 `skipped`（见 `is_blank`）。
    """
    if not reply or not reply.strip():
        return 0
    if ISSUE_RE.search(reply) or FIX_RE.search(reply):
        return 1
    return 1 if top_verdict(reply) in FAIL_TOP_VERDICTS else 0


def top_verdict(reply: str) -> str:
    """抽取上游顶层结论（`CITATION_VERDICT: FAIL` → `FAIL`）；抽不到返回空串。"""
    m = TOP_VERDICT_RE.search(reply or "")
    return (m.group(1) or "").upper() if m else ""


def is_blank(reply: str) -> bool:
    """回复是否为空/无实质内容——据此把结论降级为 skipped 而非 pass。"""
    return not (reply or "").strip()


def extract_issues(reply: str) -> list[str]:
    """抽取结构化问题条目（`ISSUE n:` 行 + 上游 `### REMOVE:/FIX:` 判决行）。"""
    out: list[str] = []
    for ln in (reply or "").splitlines():
        s = ln.strip()
        if ISSUE_RE.match(s) or FIX_RE.match(s):
            out.append(s)
    return out


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------


def _find_agent() -> Optional[str]:
    """定位 claude 可执行文件（允许 `MODEMON_CLAUDE_EXE` 覆盖）。"""
    override = os.environ.get("MODEMON_CLAUDE_EXE")
    if override and Path(override).is_file():
        return override
    p = Path(os.environ.get("MODEMON_MH_ROOT",
                            r"E:\02_Installers\DailyApps\Modex-MH-Agent"))
    exe = (p / "runtime" / "node" / "node_modules" /
           "@anthropic-ai" / "claude-code" / "bin" / "claude.exe")
    return str(exe) if exe.is_file() else None


def build_command(exe: str, prompt: str, *,
                  max_budget_usd: float = DEFAULT_MAX_BUDGET_USD,
                  model: Optional[str] = None) -> list[str]:
    """构造**独立**审计调用命令。

    ⚠️ 刻意**不带 `--resume`**：复用产出论文的那个会话 = 让执行者审计自己，
    违反上游的 reviewer-independence 约束。本函数是独立性的单一真源。
    """
    cmd = [exe, "-p", prompt,
           "--output-format", "json", "--bare",
           "--permission-mode", "acceptEdits",
           "--mcp-config", '{"mcpServers": {}}', "--strict-mcp-config",
           "--max-budget-usd", str(max_budget_usd)]
    if model:
        cmd += ["--model", model]
    return cmd


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def audit_paper(
    workspace: Path,
    *,
    model: Optional[str] = None,
    max_budget_usd: Optional[float] = None,
    timeout_s: Optional[int] = None,
    flags: tuple[str, ...] = (),
) -> CitationAuditResult:
    """对论文工作区做一次**独立的**引用审计。

    ⚠️ 永不抛异常；任何失败都降级为 `verdict=skipped`，不阻塞主流程。
    ⚠️ 这是**新的一次 agent 调用**——不复用产出论文的会话（上游核心约束）。

    预算与超时：默认 $2.0 / 1200 秒（可用 `MODEMON_CITATION_BUDGET_USD` /
    `MODEMON_CITATION_TIMEOUT_S` 覆盖）。正文 31 KB，给少了会截断成空回复。
    """
    if max_budget_usd is None:
        max_budget_usd = _env_float("MODEMON_CITATION_BUDGET_USD",
                                    DEFAULT_MAX_BUDGET_USD)
    if timeout_s is None:
        timeout_s = _env_int("MODEMON_CITATION_TIMEOUT_S", DEFAULT_TIMEOUT_S)

    res = CitationAuditResult()
    body, loaded = load_skill_body()
    res.skill_used = UPSTREAM_SKILL if loaded else "%s(最小契约)" % UPSTREAM_SKILL
    if not loaded:
        res.notes.append("skill 正文未引入，使用最小审计契约")

    ws = Path(workspace)
    if not ws.is_dir():
        res.notes.append("工作区不存在：%s" % ws)
        res.verdict = "skipped"
        return res

    targets = collect_citation_targets(ws)
    res.targets = [n for n, _ in targets]
    if not targets:
        # 没有引用文件 → 没有可审对象。**不能判 pass**（那是虚假信心），
        # 也不能报 issue（那是凭空指控）。如实降级为 skipped。
        res.verdict = "skipped"
        res.notes.append("未发现引用相关文件（paper/references.md、"
                         "paper/sections/*.md、paper/main.tex、*.bib），跳过引用审计")
        return res
    res.notes.append("待审计文件 %d 个" % len(targets))

    exe = _find_agent()
    if not exe:
        res.notes.append("找不到 claude 可执行文件，跳过引用审计")
        res.verdict = "skipped"
        return res

    try:
        from . import tool_env as te

        env, _rep = te.prepare_child_env()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        prompt = build_prompt(ws, targets=targets, flags=flags)
        cmd = build_command(exe, prompt, max_budget_usd=max_budget_usd, model=model)

        p = subprocess.run(cmd, cwd=str(ws), env=env, capture_output=True,
                           timeout=timeout_s, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        res.notes.append("引用审计超时（%s 秒），跳过（不阻塞）" % timeout_s)
        res.verdict = "skipped"
        return res
    except Exception as exc:
        res.notes.append("引用审计调用失败：%s" % exc)
        res.verdict = "skipped"
        return res

    reply = ""
    parse_note = ""
    parsed = True
    try:
        import json
        data = json.loads(p.stdout or "{}")
        reply = data.get("result") or ""
        parse_note = "subtype=%s is_error=%s" % (data.get("subtype"),
                                                 data.get("is_error"))
    except Exception:
        # 兜底：从末尾片段里仍然尝试抓结构化标记（判失败），
        # 但**绝不**因为"没解析出 JSON"就判通过——见下面的 parsed 闸门。
        reply = (p.stdout or "")[-2000:]
        parse_note = "输出非 JSON，取末尾片段"
        parsed = False

    res.raw_reply = reply
    res.top_verdict = top_verdict(reply)
    # 诊断信息：空回复必须能查到为什么
    res.notes.append("exit=%s %s 输出 %d 字符"
                     % (p.returncode, parse_note, len(p.stdout or "")))

    if is_blank(reply):
        # ⚠️ 空回复 ≠ 通过。说明审计没真正跑成（预算截断 / 超时 / 解析失败），
        #    判 pass 就是虚假信心。降级为 skipped。
        res.verdict = "skipped"
        res.ok = True
        res.notes.append("引用审计回复为空——**未判定**（不是通过）；"
                         "请检查模型/预算/超时/输出解析")
        return res

    if verdict_of(reply) == 1:
        res.verdict = "issue"
        res.ok = False
        res.issues = extract_issues(reply)
        return res

    if not parsed:
        # 输出不是预期的 JSON 信封，且里面也没有任何结构化标记：
        # 这次调用**不可信**，但也没有证据判 issue。如实降级为 skipped。
        # （判 pass 就是虚假信心——与"空回复"是同一类坑。）
        res.verdict = "skipped"
        res.ok = True
        res.notes.append("输出无法解析为预期 JSON 且未见结构化标记——**未判定**")
        return res

    if res.top_verdict in NOT_RUN_TOP_VERDICTS:
        # 审计自述"没审成"（无引用 / bib 读不了 / 评审调用失败）→ 同样不算通过。
        res.verdict = "skipped"
        res.ok = True
        res.notes.append("上游顶层结论 %s：本次**未给出通过结论**" % res.top_verdict)
        return res

    res.verdict = "pass"
    res.ok = True
    return res


__all__ = [
    "CitationAuditResult", "audit_paper", "load_skill_body", "build_prompt",
    "build_command", "collect_citation_targets", "verdict_of", "extract_issues",
    "top_verdict", "is_blank", "SKILL_PATH",
    "CITATION_AUDIT_SKILLS", "CITATION_AUDIT_EVENT_KIND",
    "DEFAULT_MAX_BUDGET_USD", "DEFAULT_TIMEOUT_S",
    "TARGET_PATTERNS", "ISSUE_RE", "FIX_RE",
    "UPSTREAM_REPO", "UPSTREAM_LICENSE", "UPSTREAM_COPYRIGHT",
    "UPSTREAM_SKILL", "UPSTREAM_BLOB_SHA", "UPSTREAM_BYTES", "UPSTREAM_SHA256",
]
