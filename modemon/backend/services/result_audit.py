"""结果诚信审计（接入上游 ARIS 的 `experiment-audit` skill）。

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
LLM agent 可能产出**看似可信的假结果**，上游 skill 归纳了四类：

1. **假 ground truth** —— 用模型输出造"参考答案"，再报高一致率当性能
2. **分数归一化** —— 拿模型自己的最大值做除数，得到 0.99+
3. **幽灵结果** —— 引用不存在的文件或从未调用的函数里的数字
4. **范围不足** —— 2 个场景的试跑被写成"全面评估"

原文强调这**不是蓄意欺骗**，而是缺少完整性约束的 agent 的失败模式。

本模块在竞赛流水线里的位置：`comp-code` 产出 `all_results.json` 之后，
由**独立的第二遍** agent 读代码与结果做审计。

⚠️ 独立性是关键
--------------
上游原文：

    **The executor collects file paths. The external reviewer backend reads code
    and judges integrity. The executor does NOT participate in integrity judgment.**

以及：

    > Do not wrap this skill in `/loop`, `/schedule`… a loop that accepts its own
    > output to decide when to stop crosses into self-acquittal.

所以：**审计必须是新的一次 agent 调用，不能复用产出结果的那个会话**，
也不得把审计结论当作自动放行的依据。
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

UPSTREAM_REPO = "wanshuiyin/Auto-claude-code-research-in-sleep"
UPSTREAM_LICENSE = "MIT"
UPSTREAM_COPYRIGHT = "Copyright (c) 2026 wanshuiyin"

_HERE = Path(__file__).resolve()
SKILL_PATH = _HERE.parents[2] / "skills" / "experiment-audit" / "SKILL.md"

#: 只认结构化标记（与 vision 自检同一取舍：评审是「加分项」不是「硬门槛」）
ISSUE_RE = re.compile(r"(?mi)^\s*(?:ISSUE|FINDING)\s*\d*\s*[:：]")
#: 诚信结论标记（上游 skill 的审计输出约定）
VERDICT_RE = re.compile(r"(?mi)^\s*(?:VERDICT|结论)\s*[:：]\s*(\S+)")


@dataclass
class AuditResult:
    ok: bool = True
    #: pass | issue | skipped
    verdict: str = "skipped"
    issues: list[str] = field(default_factory=list)
    raw_reply: str = ""
    skill_used: str = ""
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"ok": self.ok, "verdict": self.verdict, "issues": self.issues,
                "skill_used": self.skill_used, "notes": self.notes,
                "raw_reply": self.raw_reply[:600]}


# ---------------------------------------------------------------------------
# skill 正文
# ---------------------------------------------------------------------------


def load_skill_body() -> tuple[str, bool]:
    """读取 `experiment-audit/SKILL.md` 正文。

    Returns:
        (body, loaded)  loaded=False 表示正文尚未引入（骨架期）。
    """
    if SKILL_PATH.is_file():
        text = SKILL_PATH.read_text(encoding="utf-8", errors="replace")
        # 去掉 frontmatter
        m = re.match(r"\A---\s*\n.*?\n---\s*\n?", text, re.S)
        return (text[m.end():] if m else text), True
    return "", False


def _fallback_prompt() -> str:
    """正文未引入时的最小审计契约（保证功能可用）。"""
    return """# 实验/结果诚信审计（最小契约）

请检查工作区内的**代码**与**结果文件**是否自洽，重点看四类问题：

1. **假 ground truth** —— 是否用模型输出构造"参考答案"再报高一致率？
2. **分数归一化** —— 是否拿模型自身最大值做除数，得到 0.99+ 的虚高指标？
3. **幽灵结果** —— 是否引用了**不存在的文件**或**从未调用的函数**里的数字？
4. **范围不足** —— 是否把很小的样本/场景说成"全面评估"？

同时核对：结果文件里的数值是否都能由代码重算得出，论文里的数字是否与结果文件一致。

如果全部没问题，只回答一个词：PASS
如果有问题，逐条列出，格式：
ISSUE 1: [位置] [问题描述]
"""


def build_prompt(workspace: Path, *, result_file: str = "figures/all_results.json") -> str:
    body, loaded = load_skill_body()
    if not loaded:
        body = _fallback_prompt()

    ws = Path(workspace)
    files = []
    for p in sorted(ws.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(ws)
        if any(x in rel.parts for x in (".git", "__pycache__", "node_modules")):
            continue
        try:
            files.append((rel.as_posix(), p.stat().st_size))
        except OSError:
            continue

    listing = "\n".join(f"- `{n}`（{s} 字节）" for n, s in files[:40])

    return f"""{body}

---

## 本次审计对象

工作目录：`{ws}`

待审计文件：
{listing}

重点核对：`{result_file}` 中的数值是否都能由代码重算得出；
论文/报告中引用的数字是否与该文件一致。

⚠️ 你**不是**这些结果的产出者，你的职责是独立判定其可信性。
"""


def verdict_of(reply: str) -> int:
    """把审计回复映射成 0=通过 / 1=有问题。

    与 vision 自检同口径：**只认结构化标记**，泛泛评论/无法解析一律放行。
    否则审计会变成"永远挑出一条"的橡皮图章式否决。

    ⚠️ 但**空回复不等于通过**：
    空说明检查根本没跑成，判 `pass` 是**虚假信心**（实测踩过：审计返回
    `pass` 而回复是空的）。空回复交给调用方判 `skipped`。
    """
    if not reply or not reply.strip():
        return 0
    return 1 if ISSUE_RE.search(reply) else 0


def is_blank(reply: str) -> bool:
    """回复是否为空/无实质内容——据此把结论降级为 skipped 而非 pass。"""
    return not (reply or "").strip()


def extract_issues(reply: str) -> list[str]:
    return [ln.strip() for ln in (reply or "").splitlines() if ISSUE_RE.match(ln.strip())]


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------


def _find_agent() -> Optional[str]:
    p = Path(os.environ.get("MODEMON_MH_ROOT",
                            r"E:\02_Installers\DailyApps\Modex-MH-Agent"))
    exe = (p / "runtime" / "node" / "node_modules" /
           "@anthropic-ai" / "claude-code" / "bin" / "claude.exe")
    return str(exe) if exe.is_file() else None


def audit_workspace(
    workspace: Path,
    *,
    result_file: str = "figures/all_results.json",
    model: Optional[str] = None,
    max_budget_usd: Optional[float] = None,
    timeout_s: int = 1200,
) -> AuditResult:
    """对工作区做一次**独立的**诚信审计。

    ⚠️ 永不抛异常；任何失败都降级为 `verdict=skipped`，不阻塞主流程。
    ⚠️ 这是**新的一次 agent 调用**——不复用产出结果的会话（上游的核心约束）。

    预算与超时：默认 $2.0 / 20 分钟。**都给足**——SKILL.md 正文就 12 KB，
    加上工作区清单与多轮推理，实测 $0.8 会被 `error_max_budget_usd` 截断、
    600 秒会超时，两者都导致**空回复**（诊断到的真因）。
    """
    if max_budget_usd is None:
        max_budget_usd = float(os.environ.get("MODEMON_AUDIT_BUDGET_USD", "2.0"))
    res = AuditResult()
    body, loaded = load_skill_body()
    res.skill_used = "experiment-audit" if loaded else "experiment-audit(最小契约)"
    if not loaded:
        res.notes.append("skill 正文未引入，使用最小审计契约")

    exe = _find_agent()
    if not exe:
        res.notes.append("找不到 claude 可执行文件，跳过审计")
        res.verdict = "skipped"
        return res

    ws = Path(workspace)
    if not ws.is_dir():
        res.notes.append(f"工作区不存在：{ws}")
        res.verdict = "skipped"
        return res

    try:
        from . import tool_env as te

        env, _rep = te.prepare_child_env()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        prompt = build_prompt(ws, result_file=result_file)
        cmd = [exe, "-p", prompt,
               "--output-format", "json", "--bare",
               "--permission-mode", "acceptEdits",
               "--mcp-config", '{"mcpServers": {}}', "--strict-mcp-config",
               "--max-budget-usd", str(max_budget_usd)]
        if model:
            cmd += ["--model", model]
        # 独立审计：**不带 --resume**，保证是全新会话

        p = subprocess.run(cmd, cwd=str(ws), env=env, capture_output=True,
                           timeout=timeout_s, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        res.notes.append("审计超时，跳过（不阻塞）")
        res.verdict = "skipped"
        return res
    except Exception as exc:
        res.notes.append("审计调用失败：%s" % exc)
        res.verdict = "skipped"
        return res

    reply = ""
    parse_note = ""
    try:
        import json
        data = json.loads(p.stdout or "{}")
        reply = data.get("result") or ""
        parse_note = "subtype=%s is_error=%s" % (data.get("subtype"),
                                                 data.get("is_error"))
    except Exception:
        reply = (p.stdout or "")[-2000:]
        parse_note = "输出非 JSON，取末尾片段"

    res.raw_reply = reply
    # 诊断信息：空回复必须能查到为什么
    res.notes.append("exit=%s %s 输出 %d 字符"
                     % (p.returncode, parse_note, len(p.stdout or "")))

    if is_blank(reply):
        # ⚠️ 空回复 ≠ 通过。说明审计没真正跑成，
        #    判 pass 就是虚假信心（实测踩过）。降级为 skipped。
        res.verdict = "skipped"
        res.ok = True
        res.notes.append("审计回复为空——**未判定**（不是通过）；"
                         "请检查模型/预算/输出解析")
        return res

    if verdict_of(reply) == 0:
        res.verdict = "pass"
        res.ok = True
    else:
        res.verdict = "issue"
        res.ok = False
        res.issues = extract_issues(reply)
    return res


__all__ = [
    "AuditResult", "audit_workspace", "load_skill_body", "build_prompt",
    "verdict_of", "extract_issues", "SKILL_PATH",
    "UPSTREAM_REPO", "UPSTREAM_LICENSE", "UPSTREAM_COPYRIGHT",
]
