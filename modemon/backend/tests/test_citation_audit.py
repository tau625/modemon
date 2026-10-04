"""ARIS `citation-audit` 引用审计接入测试。

重点：
  1. **MIT 许可合规**（两条硬性条件：版权声明 + 许可全文）
  2. 上游 skill 正文**取回且未被改一字**（字节数与 SHA256 双断言）
  3. 判决口径与 `result_audit` 一致：**只认结构化标记**
  4. **独立性**：命令不带 `--resume`（不允许执行者审计自己）
  5. **降级语义**：空回复 → `skipped` 而非 `pass`（虚假信心）

测试**不真的拉起 agent**：所有需要调用模型的分支都通过替换
`subprocess.run` 注入桩，断言决策表，不消耗预算也不依赖网络。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
MODEN = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from services import citation_audit as ca  # noqa: E402
from services import skill_loader as sl  # noqa: E402

PASS = 0
FAIL = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  %s" % name)
    else:
        FAIL += 1
        FAILURES.append(name)
        print("  FAIL  %s  %s" % (name, detail[:150]))


def make_paper_ws(root: Path) -> Path:
    """造一个「论文已产出」的工作区。"""
    (root / "paper" / "sections").mkdir(parents=True)
    (root / "paper" / "references.md").write_text(
        "# 参考文献\n\n[1] 张三. 运输问题建模[J]. 2024.\n", encoding="utf-8")
    (root / "paper" / "sections" / "1.intro.md").write_text(
        "# 引言\n\n已有研究见 [1]。\n", encoding="utf-8")
    (root / "paper" / "sections" / "2.model.md").write_text(
        "# 模型\n\n目标函数见 [1]。\n", encoding="utf-8")
    (root / "paper" / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}见 \\cite{zhang2024}\\end{document}\n",
        encoding="utf-8")
    (root / "references.bib").write_text(
        "@article{zhang2024, title={运输问题}, author={张三}, year={2024}}\n",
        encoding="utf-8")
    return root


class _FakeProc:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode


class _StubRun:
    """替换 `subprocess.run`：记录命令，返回预设回复（不拉起 agent）。"""

    def __init__(self, reply: str = "", *, output_json: bool = True,
                 exc: BaseException | None = None) -> None:
        self.reply = reply
        self.output_json = output_json
        self.exc = exc
        self.cmds: list[list[str]] = []

    def __call__(self, cmd, **kwargs):
        self.cmds.append(list(cmd))
        if self.exc is not None:
            raise self.exc
        if self.output_json:
            return _FakeProc(json.dumps({"result": self.reply, "subtype": "success",
                                         "is_error": False}))
        return _FakeProc(self.reply)


class stub_run:
    """临时把 `subprocess.run` 换成桩。"""

    def __init__(self, stub: _StubRun) -> None:
        self.stub = stub

    def __enter__(self) -> _StubRun:
        self._saved = subprocess.run
        subprocess.run = self.stub          # type: ignore[assignment]
        return self.stub

    def __exit__(self, *exc_info) -> None:
        subprocess.run = self._saved        # type: ignore[assignment]


class no_agent:
    """临时让 `_find_agent()` 返回 None（模拟未安装 claude）。"""

    def __enter__(self):
        self._saved = ca._find_agent
        ca._find_agent = lambda: None       # type: ignore[assignment]
        return None

    def __exit__(self, *exc_info) -> None:
        ca._find_agent = self._saved        # type: ignore[assignment]


# ---------------------------------------------------------------------------


def test_license() -> None:
    print("\n[1] ★ MIT 许可合规（两条硬性条件）")
    src = (BACKEND / "services" / "citation_audit.py").read_text(encoding="utf-8")
    check("内嵌版权人", "Copyright (c) 2026 wanshuiyin" in src)
    check("**内嵌许可全文**（含 THE SOFTWARE IS PROVIDED 段）",
          "Permission is hereby granted" in src and
          "THE SOFTWARE IS PROVIDED" in src, "MIT 硬性条件")
    check("含免责声明", "WITHOUT WARRANTY OF ANY KIND" in src)
    check("声明上游仓库", ca.UPSTREAM_REPO.startswith("wanshuiyin/"))
    check("声明许可类型", ca.UPSTREAM_LICENSE == "MIT")
    check("声明版权人常量", "wanshuiyin" in ca.UPSTREAM_COPYRIGHT)
    check("指向许可文件", "LICENSE-ARIS.txt" in src)
    check("LICENSE-ARIS.txt 在位", (MODEN / "LICENSE-ARIS.txt").is_file())


def test_skill_body() -> None:
    print("\n[2] ★ 上游正文取回（原样、未改一字）")
    check("SKILL.md 落位", ca.SKILL_PATH.is_file(), str(ca.SKILL_PATH))
    if not ca.SKILL_PATH.is_file():
        return
    raw = ca.SKILL_PATH.read_bytes()
    check("**字节数与上游一致**（%d）" % ca.UPSTREAM_BYTES,
          len(raw) == ca.UPSTREAM_BYTES, str(len(raw)))
    check("**SHA256 与取回时一致**（未被改动）",
          hashlib.sha256(raw).hexdigest() == ca.UPSTREAM_SHA256,
          hashlib.sha256(raw).hexdigest())
    check("记录 git blob sha", len(ca.UPSTREAM_BLOB_SHA) == 40)
    check("无 BOM", not raw.startswith(b"\xef\xbb\xbf"))

    body, loaded = ca.load_skill_body()
    check("**正文非空且成功加载**", loaded and len(body) > 5000, str(len(body)))
    check("**frontmatter 已被剥离**", not body.lstrip().startswith("---"),
          body[:40])
    check("是上游正文（含标题 Citation Audit）", "# Citation Audit" in body)
    check("含逐条目判决口径 KEEP / FIX / REPLACE / REMOVE",
          "KEEP / FIX / REPLACE / REMOVE" in body)
    check("含幻觉引用检查", "hallucinat" in body)
    check("含裁决决策表", "Verdict decision table" in body)

    spec = sl.load_skill(ca.SKILL_PATH)
    check("**可被 skill_loader 解析**", spec.name == ca.UPSTREAM_SKILL,
          "%s @ %s" % (spec.name, ca.SKILL_PATH))


def test_targets() -> None:
    print("\n[3] 审计对象收集（参考文献 + 正文引用）")
    with tempfile.TemporaryDirectory() as td:
        ws = make_paper_ws(Path(td))
        tgs = ca.collect_citation_targets(ws)
        names = [n for n, _ in tgs]
        check("**找到引用相关文件**", len(tgs) >= 5, str(names))
        for want in ("paper/references.md", "paper/main.tex", "references.bib",
                     "paper/sections/1.intro.md", "paper/sections/2.model.md"):
            check("覆盖 %s" % want, want in names, str(names))
        check("带字节数", all(isinstance(s, int) and s > 0 for _, s in tgs))
        check("路径为相对 posix", all(not n.startswith("/") and "\\" not in n
                                     for n in names))

    with tempfile.TemporaryDirectory() as td:
        empty = Path(td)
        check("空工作区 → 无对象（不假装通过）",
              ca.collect_citation_targets(empty) == [])
    check("路径不存在时不抛异常",
          ca.collect_citation_targets(Path("no_such_dir_xyz")) == [])


def test_prompt() -> None:
    print("\n[4] 提示词契约")
    with tempfile.TemporaryDirectory() as td:
        ws = make_paper_ws(Path(td))
        p = ca.build_prompt(ws)
        check("**包含上游 skill 正文**", len(p) > 8000, str(len(p)))
        check("正文含上游标题", "# Citation Audit" in p)
        check("含待审计文件清单", "paper/references.md" in p
              and "references.bib" in p)
        check("注明工作目录", str(ws) in p)
        check("**明确审计者非产出者**", "不是" in p and "独立判定" in p)
        check("**回复契约：首行顶层结论**", "CITATION_VERDICT:" in p)
        check("**回复契约：通过口径**", "PASS" in p)
        check("**回复契约：问题条目格式**", "ISSUE 1:" in p)
        check("回复契约：结论需落盘", "CITATION_AUDIT.json" in p)
        check("禁止编造条目", "不要" in p and "编造" in p)

        p2 = ca.build_prompt(ws, flags=("--uncited",))
        check("可切换上游模式（--uncited）", "调用模式：--uncited" in p2)
        # ⚠️ 不能用 `"--uncited" not in p` 判默认模式：上游正文里本来就有
        #    `--uncited`（未引用条目检测）。只看**我们注入的模式行**。
        check("默认不注入模式行", "调用模式：" not in p)

        p3 = ca.build_prompt(Path(td), targets=[])
        check("无对象时提示如实报 NOT_APPLICABLE",
              "NOT_APPLICABLE" in p3 and "编造" in p3)

    fb = ca._fallback_prompt()
    check("正文缺失时有最小契约可退", len(fb) > 200 and "ISSUE 1:" in fb)


def test_verdict() -> None:
    print("\n[5] ★ 判决口径（只认结构化标记，与 result_audit 同取舍）")
    for reply, why in (("PASS", "明确通过"),
                       ("", "空回复"),
                       ("   \n", "全空白"),
                       ("整体一致，未见问题。", "泛泛肯定"),
                       ("需要人工再看一下。", "无法解析"),
                       ("所有条目 KEEP，无优先级修复。", "上游全清口径"),
                       ("CITATION_VERDICT: PASS\nPASS", "顶层通过"),
                       ("CITATION_VERDICT: WARN\n元数据有轻微漂移",
                        "WARN 属建议性（元数据漂移由 FIX 行单独判失败）")):
        check("放行：%s" % why, ca.verdict_of(reply) == 0, repr(reply[:40]))
    for reply, why in (("ISSUE 1: [refs] 幻觉条目，DOI 不存在", "标准格式"),
                       ("issue 2：年份对不上", "小写+中文冒号"),
                       ("FINDING 1: 语境不符", "FINDING 标记"),
                       ("### REMOVE: anon2025placeholder", "上游 REMOVE 判决行"),
                       ("### REPLACE-CONTEXT: example2023priorwork in sec/2.tex:42",
                        "上游 REPLACE-CONTEXT 判决行"),
                       ("### FIX: smith2023 metadata drift", "上游 FIX 判决行"),
                       ("CITATION_VERDICT: FAIL\n引用了不存在的论文",
                        "顶层 FAIL")):
        check("判失败：%s" % why, ca.verdict_of(reply) == 1, repr(reply[:48]))

    check("抽取条目（ISSUE 行）",
          len(ca.extract_issues("a\nISSUE 1: x\nISSUE 2: y")) == 2)
    check("抽取条目（含上游判决行）",
          len(ca.extract_issues("ISSUE 1: x\n### REMOVE: k\n正文不算")) == 2)
    check("顶层结论抽取", ca.top_verdict("CITATION_VERDICT: fail") == "FAIL")
    check("无顶层结论时为空", ca.top_verdict("整体一致") == "")

    # ★ 空回复必须降级为 skipped，不能算通过（虚假信心）
    check("**空回复不算通过**（应降级为未判定）",
          ca.is_blank("") and ca.is_blank("   \n"))
    check("有实质内容才算判定",
          not ca.is_blank("PASS") and not ca.is_blank("整体一致"))


def test_decision_table() -> None:
    print("\n[6] ★ 决策表端到端（桩注入，不拉起 agent）")
    with tempfile.TemporaryDirectory() as td:
        ws = make_paper_ws(Path(td))

        with stub_run(_StubRun("ISSUE 1: [refs] 幻觉条目")) as stub:
            r = ca.audit_paper(ws)
        check("有 ISSUE → issue 且 ok=False",
              r.verdict == "issue" and r.ok is False and len(r.issues) == 1,
              str(r.as_dict()))
        check("审计对象被记录", "paper/references.md" in r.targets, str(r.targets))

        with stub_run(_StubRun("CITATION_VERDICT: PASS\nPASS")):
            r = ca.audit_paper(ws)
        check("PASS → pass 且 ok=True", r.verdict == "pass" and r.ok is True,
              str(r.as_dict()))

        with stub_run(_StubRun("")):
            r = ca.audit_paper(ws)
        check("**空回复 → skipped（不是 pass）**",
              r.verdict == "skipped" and r.ok is True, str(r.as_dict()))
        check("空回复给出诊断提示",
              any("未判定" in n for n in r.notes), str(r.notes))

        with stub_run(_StubRun("CITATION_VERDICT: BLOCKED\nbib 读不了")):
            r = ca.audit_paper(ws)
        check("上游 BLOCKED → skipped（不算通过）",
              r.verdict == "skipped" and r.top_verdict == "BLOCKED",
              str(r.as_dict()))

        with stub_run(_StubRun("CITATION_VERDICT: NOT_APPLICABLE\n没有引用")):
            r = ca.audit_paper(ws)
        check("上游 NOT_APPLICABLE → skipped", r.verdict == "skipped",
              str(r.as_dict()))

        with stub_run(_StubRun(exc=subprocess.TimeoutExpired(cmd="x", timeout=1))):
            r = ca.audit_paper(ws)
        check("**超时 → skipped 且不抛异常**", r.verdict == "skipped",
              str(r.as_dict()))

        with stub_run(_StubRun(exc=RuntimeError("boom"))):
            r = ca.audit_paper(ws)
        check("调用异常 → skipped 且不抛异常", r.verdict == "skipped",
              str(r.as_dict()))

        with stub_run(_StubRun("PASS")):
            r = ca.audit_paper(ws)
        check("有效回复里只有泛泛肯定 → 放行（只认结构化标记）",
              r.verdict == "pass", str(r.as_dict()))

        # 非 JSON 信封：仍能从片段抓结构化标记判失败
        with stub_run(_StubRun("blah\nISSUE 9: [refs] 幻觉条目", output_json=False)):
            r = ca.audit_paper(ws)
        check("非 JSON 输出仍能抓结构化标记 → issue",
              r.verdict == "issue", str(r.as_dict()))

        # 非 JSON 且无标记：不可信 → 不判通过
        with stub_run(_StubRun("模型只说了些自然语言，没有结论", output_json=False)):
            r = ca.audit_paper(ws)
        check("**非 JSON 且无标记 → skipped（不判虚假通过）**",
              r.verdict == "skipped", str(r.as_dict()))

        # 没有引用文件 → 不调用模型，直接 skipped
        with stub_run(_StubRun("PASS")) as stub:
            emptyws = Path(td) / "empty"
            emptyws.mkdir()
            r = ca.audit_paper(emptyws)
        check("**无引用文件 → skipped 且不开跑模型**",
              r.verdict == "skipped" and not stub.cmds, str(r.as_dict()))

        with no_agent():
            r = ca.audit_paper(ws)
        check("找不到 claude → skipped（不阻塞）", r.verdict == "skipped",
              str(r.as_dict()))

        r = ca.audit_paper(Path(td) / "no_such_ws")
        check("工作区不存在 → skipped（不抛异常）", r.verdict == "skipped")


def test_independence_and_budget() -> None:
    print("\n[7] ★ 独立性与预算（上游核心约束）")
    src = (BACKEND / "services" / "citation_audit.py").read_text(encoding="utf-8")
    # ⚠️ 排除注释：源码里我写了「不带 --resume」这句话，
    #   只做字符串检查会把注释当成证据而误判。只看代码本体。
    code_only = "\n".join(ln.split("#")[0] for ln in src.splitlines())
    check("**命令本体不含 --resume**（必须是全新会话）",
          '"--resume"' not in code_only and "'--resume'" not in code_only)
    check("源码记载 reviewer 独立性（fresh thread）",
          "Thread independence" in src and "codex-reply" in src)
    check("源码记载防自我赦免的 loop 禁令", "self-acquittal" in src or
          "/loop" in src)
    check("审计失败不阻塞主流程",
          "不阻塞" in src and 'verdict = "skipped"' in src)

    cmd = ca.build_command("claude.exe", "prompt", max_budget_usd=2.0)
    check("命令不含 --resume", "--resume" not in cmd, " ".join(cmd[:6]))
    check("**命令带足预算**", "--max-budget-usd" in cmd and
          cmd[cmd.index("--max-budget-usd") + 1] == "2.0", " ".join(cmd))
    check("命令禁用外部 MCP（可复现）",
          cmd[cmd.index("--strict-mcp-config")] == "--strict-mcp-config" and
          '{"mcpServers": {}}' in cmd)
    check("命令输出 JSON 且非交互",
          "--output-format" in cmd and "--bare" in cmd)
    check("可指定模型", "--model" in ca.build_command("c.exe", "p", model="m"))

    check("**默认预算 ≥ $2.0**", ca.DEFAULT_MAX_BUDGET_USD >= 2.0,
          str(ca.DEFAULT_MAX_BUDGET_USD))
    check("**默认超时 ≥ 1200 秒**", ca.DEFAULT_TIMEOUT_S >= 1200,
          str(ca.DEFAULT_TIMEOUT_S))
    check("正文 31 KB（预算/超时给足的依据）", ca.UPSTREAM_BYTES > 30000,
          str(ca.UPSTREAM_BYTES))

    check("**接线常量：论文步骤触发**",
          {"comp-paper-zh", "comp-paper-en", "comp-paper-huawei"}
          <= ca.CITATION_AUDIT_SKILLS, str(sorted(ca.CITATION_AUDIT_SKILLS)))
    check("接线常量：comp-review 也在列（论文存在时才真正开跑）",
          "comp-review" in ca.CITATION_AUDIT_SKILLS)
    check("接线常量是 frozenset", isinstance(ca.CITATION_AUDIT_SKILLS, frozenset))
    check("事件 kind 常量为 citation_audit",
          ca.CITATION_AUDIT_EVENT_KIND == "citation_audit")


def main() -> int:
    print("=" * 74)
    print("modemon 引用审计（ARIS citation-audit）测试")
    print("=" * 74)
    test_license()
    test_skill_body()
    test_targets()
    test_prompt()
    test_verdict()
    test_decision_table()
    test_independence_and_budget()
    print("\n" + "=" * 74)
    print("PASS %d / FAIL %d" % (PASS, FAIL))
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print("  -", f)
    print("=" * 74)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
