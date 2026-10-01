"""基础回归测试：离线跑通流水线，锁住关键行为。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from modemon.artifacts import RunDir
from modemon.config import load_config
from modemon.events import EventBus
from modemon.execution import extract_files
from modemon.compliance import check_compliance
from modemon.latex import compile_tex
from modemon.provenance import check_provenance, collect_paper_numbers
from modemon.review import build_revision_block, compute_total, is_passing, number_policy, parse_review
from modemon.workflow import Engine

ROOT = Path(__file__).resolve().parents[1]
HAS_XELATEX = shutil.which("xelatex") is not None


def test_extract_files_with_marker() -> None:
    text = '说明文字\n\n```python\n# file: solve/main.py\nprint("hi")\n```\n'
    bundle = extract_files(text)
    assert list(bundle.files) == ["solve/main.py"]
    assert 'print("hi")' in bundle.files["solve/main.py"]


def test_extract_files_rejects_traversal() -> None:
    text = "```python\n# file: ../evil.py\nprint(1)\n```\n"
    bundle = extract_files(text)
    assert bundle.files == {}
    assert bundle.skipped


def test_extract_files_skips_unmarked_text_block() -> None:
    text = "```\n这是一段普通文本\n```\n"
    bundle = extract_files(text)
    assert bundle.files == {}
    assert bundle.skipped


def test_parse_review_from_fenced_json() -> None:
    payload = """```json
{"stage": "solve_code", "scores": {"正确性": 9, "完整性": 9, "可复现性": 9, "规范性": 9, "创新性": 8},
 "total": 8.9, "verdict": "pass", "issues": [], "must_fix": [], "next_focus": "无需修改"}
```"""
    rv = parse_review(payload, stage="solve_code")
    assert rv.parsed and rv.passed
    assert rv.total == 8.9


def test_parse_review_flags_blocker() -> None:
    payload = '{"total": 9.5, "verdict": "pass", "issues": [{"severity": "高", "problem": "数值无出处"}]}'
    rv = parse_review(payload)
    assert rv.parsed
    assert not rv.passed  # 有高严重度问题，即使总分够也不能算通过


def test_parse_review_handles_garbage() -> None:
    rv = parse_review("模型开始胡说八道，没有 JSON")
    assert not rv.parsed
    assert rv.verdict == "revise"
    assert rv.must_fix


def test_compute_total_uses_weights() -> None:
    total = compute_total({"正确性": 10, "完整性": 0, "可复现性": 0, "规范性": 0, "创新性": 0})
    assert total == 3.0


def test_revision_block_contains_must_fix() -> None:
    rv = parse_review('{"total": 5, "verdict": "revise", "must_fix": ["补充灵敏度分析"]}')
    block = build_revision_block(rv)
    assert "补充灵敏度分析" in block
    assert "修订后的完整产出" in block


def test_extract_files_with_percent_marker() -> None:
    """LaTeX 用 % 注释标注文件路径，抽取器必须认得。"""
    text = "```latex\n% file: paper/main.tex\n\\documentclass{article}\n```\n"
    bundle = extract_files(text)
    assert "paper/main.tex" in bundle.files
    assert bundle.files["paper/main.tex"].startswith("% file:")


@pytest.mark.skipif(not HAS_XELATEX, reason="需要 TeX Live 的 xelatex")
def test_compile_tex_success_and_failure(tmp_path: Path) -> None:
    good = tmp_path / "good.tex"
    good.write_text("\\documentclass{article}\n\\begin{document}\nhello\n\\end{document}\n", encoding="utf-8")
    ok = compile_tex(good, engine="xelatex", timeout=180, log_dir=tmp_path)
    assert ok.ok, ok.error_excerpt
    assert ok.pdf is not None and ok.pdf.exists()
    assert ok.log_path is not None and ok.log_path.exists()

    bad = tmp_path / "bad.tex"
    bad.write_text("\\documentclass{article}\n\\begin{document}\n\\undefinedcmd\n\\end{document}\n", encoding="utf-8")
    failed = compile_tex(bad, engine="xelatex", timeout=180, log_dir=tmp_path)
    assert not failed.ok
    assert "undefined" in failed.error_excerpt.lower()
    assert failed.pdf is None


@pytest.mark.skipif(not HAS_XELATEX, reason="需要 TeX Live 的 xelatex")
def test_compile_repair_loop_offline(tmp_path: Path) -> None:
    """坏论文 → 触发自动回修 → 编译出 PDF（离线 mock 执行者）。"""
    cfg = load_config(competition="cumcm", root=ROOT)
    run = RunDir(tmp_path / "runs", "repair-run")
    run.write_text("paper/main.tex",
                   "\\documentclass{article}\\begin{document}\\undefinedcmd\\end{document}\n")
    bus = EventBus(events_file=run.events_file, verbose=False)

    engine = Engine(cfg, run, bus, mock=True, execute=True)
    info = engine.compile_paper(repair=True)

    assert info["status"] == "ok", info
    assert info["rounds"] >= 1, "应当触发至少一轮回修"
    assert (run.path / "paper" / "main.pdf").exists()
    assert (run.path / "results" / "compile_summary.json").exists()
    assert run.load_report()["compile"]["status"] == "ok"


def test_collect_paper_numbers_skips_latex_noise() -> None:
    text = (
        "\\documentclass[12pt]{ctexart}\n"
        "\\includegraphics[width=0.8\\textwidth]{../figures/fig1.png}\n"
        "\\label{sec:1}\n"
        "峰值水位为 15.3641 米，出现在 6.5 小时；共有 241 个采样点。\n"
    )
    found = {hit.raw for hit in collect_paper_numbers(text)}
    assert {"15.3641", "6.5", "241"} <= found
    assert "0.8" not in found, "图片宽度是排版参数，不应算论文数据"
    assert "12" not in found and "1" not in found, "文档类选项与标签编号不应算数据"


def test_check_provenance_matches_real_results(tmp_path: Path) -> None:
    run = RunDir(tmp_path / "runs", "prov-run")
    run.write_json(
        "results/execution_solve_code.json",
        [{"file": "solve/main.py", "returncode": 0, "result_json": {"峰值": 15.3641, "时刻": 6.5}}],
    )
    run.write_text("paper/main.tex", "峰值 15.36 米，出现在 6.5 小时；另有 999.9 并无出处。")

    report = check_provenance(run.path)
    unmatched = {item["value"] for item in report.unmatched}
    assert "999.9" in unmatched, "凭空出现的数字必须被标出来"
    assert "6.5" not in unmatched and "15.36" not in unmatched, "四舍五入后的数字应能匹配上"
    assert report.ratio < 1.0


def test_compliance_flags_incomplete_paper(tmp_path: Path) -> None:
    run = RunDir(tmp_path / "runs", "comp-bad")
    run.write_text("paper/main.tex", "\\documentclass{ctexart}\n\\begin{document}\n摘要：待补充\n\\end{document}")
    competition = {
        "required_sections": ["摘要", "问题重述", "模型假设", "灵敏度分析"],
        "abstract_first": True,
        "page_limit": 20,
    }
    rep = check_compliance(run.path, competition)
    by_name = {i.name: i for i in rep.items}
    assert by_name["必备章节"].status == "fail"
    assert by_name["占位符残留"].status == "fail"
    assert by_name["参考文献"].status == "fail"
    assert rep.verdict == "fail"


def test_compliance_passes_on_complete_paper(tmp_path: Path) -> None:
    tex = (
        "\\documentclass{ctexart}\n\\begin{document}\n"
        "\\begin{abstract}摘要：模型结论可靠。\\end{abstract}\n"
        "\\section{问题重述}\n\\section{模型假设}\n\\section{模型的建立与求解}\n"
        "\\section{灵敏度分析}\n\\section{模型的评价与推广}\n"
        "\\begin{thebibliography}{9}\\bibitem{a}某文献\\end{thebibliography}\n"
        "\\end{document}\n"
    )
    run = RunDir(tmp_path / "runs", "comp-good")
    run.write_text("paper/main.tex", tex)
    competition = {
        "required_sections": ["摘要", "问题重述", "模型假设", "模型的建立与求解", "灵敏度分析", "模型的评价与推广"],
        "abstract_first": True,
        "page_limit": 20,
    }
    rep = check_compliance(run.path, competition)
    assert not rep.failed, [i.to_dict() for i in rep.failed]


def test_count_pdf_pages_estimates_from_raw(tmp_path: Path) -> None:
    """没有 pypdf 时也要能从 PDF 字节里估算页数。"""
    from modemon.compliance import count_pdf_pages

    pdf = tmp_path / "t.pdf"
    pdf.write_bytes(b"%PDF-1.4\n1 0 obj /Type /Page /Parent 2 0 R endobj\n2 0 obj /Type /Page endobj\n")
    assert count_pdf_pages(pdf) == 2


def test_cli_imports_and_lists_skills() -> None:
    """护栏：cli.py 不在其他测试的导入路径上，这里显式导入并跑一条命令。"""
    from typer.testing import CliRunner

    from modemon.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["skills"])
    assert result.exit_code == 0, result.output
    assert "Skill" in result.output

    help_text = runner.invoke(app, ["--help"]).output
    for command in ("doctor", "run", "compile", "check", "report", "rerun", "runs", "show", "resume", "skills", "serve"):
        assert command in help_text, f"命令 {command} 未注册"


def test_provenance_ignores_its_own_report(tmp_path: Path) -> None:
    """门禁产物不能当作证据，否则数字能自证。"""
    run = RunDir(tmp_path / "runs", "self-ref")
    run.write_json("results/provenance_check.json", {"unmatched": [{"value": "123.4"}]})
    run.write_text("paper/main.tex", "论文里写了 123.4 这个数字。")

    report = check_provenance(run.path)
    assert "123.4" in {item["value"] for item in report.unmatched}
    assert "results/provenance_check.json" not in report.sources


def test_number_policy_switches_by_stage_position() -> None:
    """求解执行之前不该按"必须有运行结果出处"来扣分。"""
    pre = number_policy(has_results=False)
    post = number_policy(has_results=True)
    assert "不因" in pre and "求解执行之前" in pre
    assert "真实运行结果" in post
    assert pre != post


def test_review_gate_requires_no_blockers() -> None:
    high = parse_review('{"total": 9.6, "verdict": "pass", "issues": [{"severity": "高", "problem": "数值无出处"}]}')
    clean = parse_review('{"total": 9.6, "verdict": "pass", "issues": []}')
    assert not is_passing(high, 8.5, True), "有高严重度问题不能判通过"
    assert is_passing(high, 8.5, False), "放宽开关后应当通过"
    assert is_passing(clean, 8.5, True)
    assert not is_passing(clean, 9.9, True)
    assert not is_passing(parse_review("不是 JSON"), 1.0, False)


def test_web_api_and_websocket_progress(tmp_path: Path) -> None:
    """进度服务：列出运行、读取报告、WebSocket 推送事件。"""
    from fastapi.testclient import TestClient

    from modemon.web import create_app

    run = RunDir(tmp_path / "runs", "web-run")
    run.save_report(
        {
            "run_id": "web-run",
            "competition": "cumcm",
            "status": "running",
            "stage_index": 1,
            "stages": [{"id": "a"}, {"id": "b"}],
        }
    )
    run.write_text("logs/events.jsonl", json.dumps({"kind": "stage_start", "message": "赛题解析"}, ensure_ascii=False) + "\n")

    client = TestClient(create_app(tmp_path))
    listing = client.get("/api/runs")
    assert listing.status_code == 200
    assert listing.json()[0]["run_id"] == "web-run"

    assert client.get("/api/runs/web-run").json()["stage_index"] == 1
    assert client.get("/api/runs/does-not-exist").status_code == 404
    assert "Modemon" in client.get("/").text

    with client.websocket_connect("/ws/runs/web-run") as ws:
        first = json.loads(ws.receive_text())
        assert first["kind"] == "stage_start"


def test_provenance_evidence_sources_are_deduped(tmp_path: Path) -> None:
    """两个 glob 模式会重叠，证据文件不能重复计入。"""
    run = RunDir(tmp_path / "runs", "dedup")
    run.write_json("results/execution_solve_code.json", [{"result_json": {"x": 1.5}}])
    run.write_json("results/extra.json", {"y": 2.5})

    report = check_provenance(run.path)
    assert len(report.sources) == len(set(report.sources)), report.sources
    assert report.evidence_count == 2, report.evidence_count


def test_load_problem_text_handles_text_and_rejects_unknown(tmp_path: Path) -> None:
    from modemon.ingest import IngestError, load_problem_text

    md = tmp_path / "p.md"
    md.write_text("赛题正文\r\n\r\n\r\n\r\n第二段   \n", encoding="utf-8")
    text = load_problem_text(md)
    assert "赛题正文" in text and "\r" not in text and "\n\n\n\n" not in text

    bad = tmp_path / "p.doc"
    bad.write_text("old", encoding="utf-8")
    with pytest.raises(IngestError, match="docx"):
        load_problem_text(bad)

    with pytest.raises(IngestError):
        load_problem_text(tmp_path / "missing.txt")


@pytest.mark.skipif(not HAS_XELATEX, reason="需要 TeX Live 生成测试用 PDF")
def test_load_problem_text_extracts_pdf(tmp_path: Path) -> None:
    from modemon.ingest import load_problem_text

    tex = tmp_path / "q.tex"
    tex.write_text(
        "\\documentclass{article}\\begin{document}This is a modeling problem statement.\\end{document}\n",
        encoding="utf-8",
    )
    res = compile_tex(tex, engine="xelatex", timeout=180, log_dir=tmp_path)
    assert res.ok and res.pdf is not None
    text = load_problem_text(res.pdf)
    assert "modeling problem statement" in text


def test_checkpoint_actions_do_not_block_when_not_interactive(tmp_path: Path) -> None:
    """检查点只在交互模式且环节被指定时生效。"""
    cfg = load_config(competition="cumcm", root=ROOT, checkpoints=["modeling_design"])
    run = RunDir(tmp_path / "runs", "cp-run")
    bus = EventBus(events_file=run.events_file, verbose=False)

    quiet = Engine(cfg, run, bus, mock=True, execute=False, interactive=False)
    assert not quiet._should_checkpoint(cfg.stages[1])

    talkative = Engine(cfg, run, bus, mock=True, execute=False, interactive=True)
    assert talkative._should_checkpoint(cfg.stages[1])       # modeling_design 在检查点里
    assert not talkative._should_checkpoint(cfg.stages[0])   # 其他环节不暂停


def test_review_prompt_carries_previous_round_feedback() -> None:
    """评审要有跨轮记忆：首轮不带，次轮必须带上上一轮的必改项与分数。"""
    from modemon.skills import load_skill

    cfg = load_config(competition="cumcm", root=ROOT)
    skill = load_skill("review", cfg.skills_dir)
    common = dict(
        stage_title="建模设计",
        stage_id="modeling_design",
        competition="测试竞赛",
        artifact="产出内容",
        context="上游上下文",
        pass_score=8.5,
        number_policy=number_policy(has_results=True),
    )
    first = skill.render(previous_must_fix=[], previous_total=None, **common)
    assert "上一轮评审结论" not in first

    second = skill.render(previous_must_fix=["把 seed 写死为 42"], previous_total=8.2, **common)
    assert "上一轮评审结论" in second
    assert "把 seed 写死为 42" in second
    assert "8.2" in second
    # 两段式：先逐条核对，再独立重审（防止只看清单造成锚定效应）
    assert "第一步：逐条核对" in second
    assert "第二步：独立重审" in second
    assert "previous_check" in second


def test_run_report_markdown_contains_key_sections(tmp_path: Path) -> None:
    from modemon.report import build_markdown, write_report

    run = RunDir(tmp_path / "runs", "rep-run")
    run.write_text("paper/main.tex", "x")
    state = {
        "run_id": "rep-run",
        "competition": "cumcm",
        "status": "done",
        "created_at": "t0",
        "updated_at": "t1",
        "models": {"executor": "mimo-v2.6-flash", "reviewer": "mimo-v2.6-pro"},
        "problem_file": "examples/problem.txt",
        "usage": {"calls": 3, "prompt_tokens": 10, "completion_tokens": 20, "cost_usd": 0.0},
        "stages": [
            {
                "id": "solve_code",
                "title": "求解实现",
                "status": "done",
                "duration_s": 1.2,
                "rounds": 2,
                "reviews": [{"total": 7.8, "verdict": "revise", "must_fix": ["把 seed 写死"]}],
                "outputs": ["solve/main.py"],
                "exec_results": [
                    {"file": "solve/main.py", "returncode": 0, "duration_s": 0.5, "result_json": {"峰值": 14.97}}
                ],
            }
        ],
        "compile": {"status": "ok", "message": "编译成功", "pdf": "main.pdf", "pdf_bytes": 1000, "rounds": 1},
        "provenance": {
            "matched": 1, "total": 2, "ratio": 0.5, "evidence_count": 5,
            "unmatched": [{"value": "9.9", "file": "paper/main.tex", "context": "上下文"}],
        },
        "compliance": {
            "verdict": "fail", "failed": 1, "warned": 0,
            "items": [{"name": "参考文献", "status": "fail", "detail": "未找到"}],
        },
    }
    md = build_markdown(run.path, state)
    for token in ("运行报告", "环节与评审轨迹", "求解实现", "把 seed 写死", "14.97",
                  "编译", "数值溯源", "合规检查", "学术诚信"):
        assert token in md, f"报告缺少：{token}"

    written = write_report(run.path, state)
    assert written.exists() and "运行报告" in written.read_text(encoding="utf-8")


def test_from_stage_skips_completed_prefix(tmp_path: Path) -> None:
    """断点续跑 / 单步重跑：从中间环节开始，前面已完成的环节不再重跑。"""
    cfg = load_config(competition="cumcm", root=ROOT)
    run = RunDir(tmp_path / "runs", "resume-run")
    bus = EventBus(events_file=run.events_file, verbose=False)

    engine = Engine(cfg, run, bus, mock=True, execute=False)
    state = engine.run_pipeline("这是一道测试赛题。", from_stage="solve_code")

    assert [rec["id"] for rec in state["stages"]] == ["solve_code", "figures", "paper_outline", "paper_writing"]
    assert state["status"] == "done"
    assert state["stage_index"] == len(cfg.stages)
    assert run.load_report()["stages"], "报告必须落盘，续跑依赖它"


def test_provider_retries_with_thinking_disabled_when_content_empty() -> None:
    """真实故障：思考把输出预算吃光导致正文为空 —— 必须自动关思考重试，而不是直接失败。"""
    from types import SimpleNamespace

    from modemon.config import ModelCfg, ProviderCfg
    from modemon.providers import OpenAICompatProvider

    calls: list[dict] = []

    class _Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            thinking = (kwargs.get("extra_body") or {}).get("thinking", {}).get("type")
            if thinking == "disabled":
                message = SimpleNamespace(content='{"ok": true}', reasoning_content=None)
            else:
                message = SimpleNamespace(content="", reasoning_content="思考" * 200)
            return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)

    provider = object.__new__(OpenAICompatProvider)
    provider.cfg = ModelCfg(provider="xiaomi", model="mimo-test", max_tokens=100)
    provider.provider_cfg = ProviderCfg(base_url="http://example.invalid", api_key_env="NOPE_KEY")
    provider.retry = 3
    provider.timeout = 1
    provider.pricing = {}
    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))

    resp = provider.complete([{"role": "user", "content": "hi"}])

    assert resp.text == '{"ok": true}'
    assert len(calls) == 2, "第一次正文为空，应自动关思考重试一次"
    assert "extra_body" not in calls[0]
    assert calls[1]["extra_body"]["thinking"]["type"] == "disabled"


def test_review_failure_keeps_run_alive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """评审接口故障不能毁掉整条长跑流水线，已产出的内容必须保留。"""
    from modemon.providers import LLMError

    cfg = load_config(competition="cumcm", root=ROOT)
    run = RunDir(tmp_path / "runs", "review-fail")
    bus = EventBus(events_file=run.events_file, verbose=False)
    engine = Engine(cfg, run, bus, mock=True, execute=False)

    def boom(*args, **kwargs):
        raise LLMError("模拟评审接口故障")

    monkeypatch.setattr(engine, "_review_stage", boom)
    state = engine.run_pipeline("赛题正文")

    failed = [r for r in state["stages"] if r.get("review_error")]
    assert failed, "应当记录评审失败"
    assert all(r["status"] == "review_failed" for r in failed)
    assert state["status"] == "finished_with_issues"
    assert (run.path / "paper" / "main.tex").exists(), "评审失败也要保留已产出内容"
    assert run.load_report()["stages"], "进度必须落盘以便续跑"


def test_pricing_config_drives_cost_estimate(tmp_path: Path) -> None:
    """pricing 段必须真的被读取，而不是死配置。"""
    from modemon.providers import estimate_cost_usd

    # 内置表覆盖 deepseek-flash
    builtin = estimate_cost_usd(
        "deepseek-flash", {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000}
    )
    assert builtin > 0

    # 自定义单价（例如用户套餐里的 mimo 价格）
    custom = estimate_cost_usd(
        "mimo-v2.6-flash",
        {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000},
        {"in_miss": 0.10, "out": 0.40},
    )
    assert abs(custom - 0.50) < 1e-9, custom

    # 缓存命中要单独计价
    cached = estimate_cost_usd(
        "m", {"prompt_tokens": 1_000_000, "prompt_cache_hit_tokens": 1_000_000, "completion_tokens": 0},
        {"in_miss": 10.0, "in_hit": 0.01, "out": 1.0},
    )
    assert abs(cached - 0.01) < 1e-9, cached

    # 没有价格表就只统计用量，不编造金额
    assert estimate_cost_usd("unknown-model", {"prompt_tokens": 999, "completion_tokens": 999}) == 0.0


def test_config_exposes_pricing_section() -> None:
    cfg = load_config(competition="cumcm", root=ROOT)
    assert isinstance(cfg.pricing, dict)  # 允许为空，但必须是可读结构


def test_rerun_cli_reruns_only_target_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`mma rerun` 要真的重跑目标环节，且不碰上游已完成产物。"""
    from typer.testing import CliRunner

    import modemon.cli as cli

    shutil.copytree(ROOT / "configs", tmp_path / "configs", dirs_exist_ok=True)
    shutil.copytree(ROOT / "skills", tmp_path / "skills", dirs_exist_ok=True)
    problem = tmp_path / "problem.txt"
    problem.write_text("赛题正文：水位峰值估计。", encoding="utf-8")

    real_load_config = cli.load_config
    monkeypatch.setattr(cli, "load_config", lambda **kwargs: real_load_config(root=tmp_path, **kwargs))

    runner = CliRunner()
    first = runner.invoke(cli.app, ["run", "-p", str(problem), "--provider", "mock",
                                    "--no-execute", "--run-id", "rr", "--quiet"])
    assert first.exit_code == 0, first.output

    run_root = tmp_path / "runs" / "rr"
    assert len(json.loads((run_root / "report.json").read_text(encoding="utf-8"))["stages"]) == 6

    # 在目标环节与上游产物上各留一个记号
    (run_root / "solve" / "main.py").write_text("# SENTINEL-DOWNSTREAM", encoding="utf-8")
    (run_root / "artifacts" / "01_problem_analysis.md").write_text("# SENTINEL-UPSTREAM", encoding="utf-8")

    second = runner.invoke(cli.app, ["rerun", "rr", "solve_code", "--provider", "mock", "--no-execute"])
    assert second.exit_code == 0, second.output

    report = json.loads((run_root / "report.json").read_text(encoding="utf-8"))
    assert [r["id"] for r in report["stages"]] == [
        "problem_analysis", "modeling_design", "solve_code", "figures", "paper_outline", "paper_writing"
    ]
    assert "SENTINEL-DOWNSTREAM" not in (run_root / "solve" / "main.py").read_text(encoding="utf-8"), \
        "目标环节必须被重新执行"
    assert "SENTINEL-UPSTREAM" in (run_root / "artifacts" / "01_problem_analysis.md").read_text(encoding="utf-8"), \
        "上游产物不应被重跑"


def test_resume_cli_continues_pending_stages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """中断后 mma resume 只补跑未完成的环节（此前该命令无测试覆盖，藏着 NameError）。"""
    from typer.testing import CliRunner

    import modemon.cli as cli

    shutil.copytree(ROOT / "configs", tmp_path / "configs", dirs_exist_ok=True)
    shutil.copytree(ROOT / "skills", tmp_path / "skills", dirs_exist_ok=True)
    problem = tmp_path / "problem.txt"
    problem.write_text("赛题正文。", encoding="utf-8")

    real_load_config = cli.load_config
    monkeypatch.setattr(cli, "load_config", lambda **kwargs: real_load_config(root=tmp_path, **kwargs))

    runner = CliRunner()
    first = runner.invoke(cli.app, ["run", "-p", str(problem), "--provider", "mock",
                                    "--no-execute", "--run-id", "rs", "--quiet"])
    assert first.exit_code == 0, first.output

    run_root = tmp_path / "runs" / "rs"
    report = json.loads((run_root / "report.json").read_text(encoding="utf-8"))
    report["stages"] = [r for r in report["stages"] if r["id"] not in ("paper_outline", "paper_writing")]
    (run_root / "report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

    second = runner.invoke(cli.app, ["resume", "rs", "--provider", "mock", "--no-execute"])
    assert second.exit_code == 0, second.output

    ids = [s["id"] for s in json.loads((run_root / "report.json").read_text(encoding="utf-8"))["stages"]]
    assert ids == ["problem_analysis", "modeling_design", "solve_code", "figures",
                   "paper_outline", "paper_writing"], ids
    # 用量要接着累计，不能清零
    assert json.loads((run_root / "report.json").read_text(encoding="utf-8"))["usage"]["calls"] > 0


def test_parse_review_captures_previous_check() -> None:
    """两段式评审：必须能解析"上一轮必改项逐条核对"的结果。"""
    payload = (
        '{"total": 9.1, "verdict": "pass", "issues": [], "must_fix": [],'
        ' "previous_check": ['
        '{"item": "把 MC_SEED 写死", "status": "已落实", "evidence": "§3.1 第 9 步"},'
        '{"item": "统一 φ=0 口径", "status": "未落实", "evidence": "仍有两处矛盾"}]}'
    )
    rv = parse_review(payload)
    assert rv.total == 9.1
    assert len(rv.previous_check) == 2
    assert len(rv.resolved_previous) == 1
    assert rv.resolved_previous[0]["item"] == "把 MC_SEED 写死"
    assert rv.to_dict()["previous_check"]


def test_extract_files_keeps_unterminated_block() -> None:
    """真实故障：输出被 max_tokens 截断、结尾围栏丢失 —— 整篇论文不能被丢弃。"""
    text = (
        "```latex\n% file: paper/main.tex\n\\documentclass{ctexart}\n"
        "\\begin{document}\n这里是被截断的正文，没有结尾围栏"
    )
    bundle = extract_files(text)
    assert "paper/main.tex" in bundle.files, "未闭合的代码块也要落盘"
    assert "被截断的正文" in bundle.files["paper/main.tex"]
    assert bundle.unterminated == ["paper/main.tex"], "要标记出来以便上层告警"


def test_stage_max_tokens_override_and_truncation_flag() -> None:
    from types import SimpleNamespace

    from modemon.config import ModelCfg, ProviderCfg, StageCfg
    from modemon.providers import OpenAICompatProvider

    assert StageCfg(id="x", title="t", skill="s", max_tokens=64000).max_tokens == 64000

    calls: list[dict] = []

    class _Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            message = SimpleNamespace(content="ok", reasoning_content=None)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=message, finish_reason="length")], usage=None
            )

    provider = object.__new__(OpenAICompatProvider)
    provider.cfg = ModelCfg(provider="xiaomi", model="m", max_tokens=1000)
    provider.provider_cfg = ProviderCfg(base_url="http://example.invalid", api_key_env="NOPE_KEY")
    provider.retry = 1
    provider.timeout = 1
    provider.pricing = {}
    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))

    resp = provider.complete([{"role": "user", "content": "hi"}], max_tokens=64000)
    assert calls[0]["max_tokens"] == 64000, "环节级 max_tokens 必须覆盖模型级默认值"
    assert resp.truncated and resp.finish_reason == "length"


def test_context_budget_is_configurable(tmp_path: Path) -> None:
    """上下文预算必须走配置：论文环节曾只看到建模方案的三分之一。"""
    cfg = load_config(competition="cumcm", root=ROOT)
    assert cfg.run.context_per_artifact == 20000
    assert cfg.run.context_total == 160000

    cfg.run.context_per_artifact = 50
    run = RunDir(tmp_path / "runs", "ctx-run")
    run.write_text("artifacts/a.md", "X" * 5000)
    bus = EventBus(events_file=run.events_file, verbose=False)
    engine = Engine(cfg, run, bus, mock=True, execute=False)
    engine.state["stages"] = [
        {"id": "a", "title": "A", "status": "done", "outputs": ["artifacts/a.md"], "exec_results": []}
    ]
    context = engine._build_context()
    assert len(context) < 1000, f"应按配置截断，实际 {len(context)} 字符"


def test_compliance_requires_minimum_figures(tmp_path: Path) -> None:
    """竞赛论文缺图是硬伤：低于 min_figures 应判不通过。"""
    run = RunDir(tmp_path / "runs", "fig-count")
    run.write_text(
        "paper/main.tex",
        "\\documentclass{ctexart}\\begin{document}\\includegraphics{../figures/fig1.png}\\end{document}",
    )
    (run.path / "figures" / "fig1.png").write_bytes(b"fake-png")

    rep = check_compliance(run.path, {"min_figures": 3})
    by_name = {i.name: i for i in rep.items}
    assert by_name["图片数量"].status == "fail"
    assert rep.verdict == "fail"

    ok = check_compliance(run.path, {"min_figures": 1})
    assert not [i for i in ok.items if i.name == "图片数量" and i.status == "fail"]


def test_compliance_flags_missing_figure_file(tmp_path: Path) -> None:
    run = RunDir(tmp_path / "runs", "fig-missing")
    run.write_text("paper/main.tex", "\\includegraphics{../figures/nope.png}")
    rep = check_compliance(run.path, {"min_figures": 1})
    by_name = {i.name: i for i in rep.items}
    assert by_name["图片文件"].status == "fail"
    assert "nope.png" in by_name["图片文件"].detail


def test_compliance_detects_truncated_document(tmp_path: Path) -> None:
    """被截断的 LaTeX 缺 \\end{document}，但依然可能编译出半篇 —— 必须判不通过。"""
    run = RunDir(tmp_path / "runs", "truncated")
    run.write_text("paper/main.tex", "\\documentclass{ctexart}\n\\begin{document}\n正文写到一半就断了")
    rep = check_compliance(run.path, {})
    by_name = {i.name: i for i in rep.items}
    assert by_name["文档完整性"].status == "fail"
    assert "截断" in by_name["文档完整性"].detail
    assert rep.verdict == "fail"


def test_compliance_flags_too_few_pages(tmp_path: Path) -> None:
    run = RunDir(tmp_path / "runs", "short-paper")
    run.write_text("paper/main.tex", "\\documentclass{ctexart}\\begin{document}短\\end{document}")
    body = b"".join(b"%d 0 obj /Type /Page endobj\n" % i for i in range(6))
    (run.path / "paper" / "main.pdf").write_bytes(b"%PDF-1.4\n" + body)

    rep = check_compliance(run.path, {"min_pages": 15})
    by_name = {i.name: i for i in rep.items}
    assert by_name["页数"].status == "fail", by_name["页数"].detail
    assert "至少 15 页" in by_name["页数"].detail
    assert rep.page_count == 6


def test_context_lists_generated_figures(tmp_path: Path) -> None:
    """上下文必须列出真实图表文件名，否则论文环节只能猜文件名并猜错。"""
    cfg = load_config(competition="cumcm", root=ROOT)
    run = RunDir(tmp_path / "runs", "fig-ctx")
    (run.path / "figures" / "fig1_water_level_fit.png").write_bytes(b"fake")
    bus = EventBus(events_file=run.events_file, verbose=False)
    engine = Engine(cfg, run, bus, mock=True, execute=False)

    context = engine._build_context()
    assert "已生成的真实图表文件" in context
    assert "figures/fig1_water_level_fit.png" in context
    assert "../figures/" in context


def test_long_call_emits_heartbeat_events(tmp_path: Path) -> None:
    """长调用期间要有心跳事件，否则监控页无法区分"在跑"与"卡死"。"""
    import time as _time

    from modemon.providers import LLMResponse

    cfg = load_config(competition="cumcm", root=ROOT)
    cfg.run.heartbeat_s = 0.05
    run = RunDir(tmp_path / "runs", "beat-run")
    bus = EventBus(events_file=run.events_file, verbose=False)
    engine = Engine(cfg, run, bus, mock=True, execute=False)

    class _SlowProvider:
        model = "stub-model"

        def complete(self, messages, **kwargs):
            _time.sleep(0.2)
            return LLMResponse(text="ok", model="stub-model", provider="stub", usage={})

    engine._call(_SlowProvider(), "提示词", role="executor", stage=cfg.stages[0], rnd=0)
    assert any(e["kind"] == "llm_wait" for e in bus.events), "应当发出心跳事件"

    # 关闭心跳后不应再产生该类事件
    bus2 = EventBus(events_file=None, verbose=False)
    engine.bus = bus2
    cfg.run.heartbeat_s = 0
    engine._call(_SlowProvider(), "提示词", role="executor", stage=cfg.stages[0], rnd=0)
    assert not any(e["kind"] == "llm_wait" for e in bus2.events)


def test_stage_thinking_applies_to_executor_only(tmp_path: Path) -> None:
    """环节级 thinking 只该影响执行者；评审者是质量门禁，应保留自己的思考设置。"""
    from types import SimpleNamespace

    from modemon.providers import LLMResponse

    cfg = load_config(competition="cumcm", root=ROOT)
    cfg.run.heartbeat_s = 0
    paper_stage = [s for s in cfg.stages if s.id == "paper_writing"][0]
    assert paper_stage.thinking == "off"

    seen: dict[str, object] = {}

    class _Recorder:
        model = "stub"

        def complete(self, messages, **kwargs):
            seen["thinking"] = kwargs.get("thinking")
            return LLMResponse(text="ok", model="stub", provider="stub", usage={})

    run = RunDir(tmp_path / "runs", "think-scope")
    bus = EventBus(events_file=None, verbose=False)
    engine = Engine(cfg, run, bus, mock=True, execute=False)

    engine._call(_Recorder(), "p", role="executor", stage=paper_stage, rnd=0)
    assert seen["thinking"] == "off", "执行者应遵循环节设置"

    engine._call(_Recorder(), "p", role="reviewer", stage=paper_stage, rnd=0)
    assert seen["thinking"] is None, "评审者不应被环节设置强行关掉思考"


def test_figure_inventory_shared_by_context_and_repair_prompt(tmp_path: Path) -> None:
    """图片清单必须同时进入下游上下文与编译回修提示词，否则模型无从改对路径。"""
    from modemon.skills import load_skill

    cfg = load_config(competition="cumcm", root=ROOT)
    run = RunDir(tmp_path / "runs", "fig-inv")
    (run.path / "figures" / "fig1_water_level_fit.png").write_bytes(b"fake")
    engine = Engine(cfg, run, build := EventBus(events_file=None, verbose=False), mock=True, execute=False)

    inventory = engine._figure_inventory()
    assert "figures/fig1_water_level_fit.png" in inventory
    assert "../figures/" in inventory
    assert inventory in engine._build_context()

    skill = load_skill("latex_fix", cfg.skills_dir)
    prompt = skill.render(compile_log="! LaTeX Error: File not found", paper_files="源文件",
                          figures=inventory, competition="测试")
    assert "fig1_water_level_fit.png" in prompt
    assert "不要编造新文件名" in prompt


@pytest.mark.skipif(not HAS_XELATEX, reason="需要 TeX Live 的 xelatex")
def test_compile_repair_rolls_back_damaging_repair(tmp_path: Path) -> None:
    """实测事故：回修模型只输出部分文件，把完整论文覆盖成半成品 —— 必须回滚。"""
    cfg = load_config(competition="cumcm", root=ROOT)
    run = RunDir(tmp_path / "runs", "rollback-run")
    original = (
        "\\documentclass{article}\\begin{document}\n"
        + ("这是一段应当被保留的正文内容。" * 800)
        + "\n\\undefinedcmd\n\\end{document}\n"
    )
    run.write_text("paper/main.tex", original)
    bus = EventBus(events_file=run.events_file, verbose=False)

    engine = Engine(cfg, run, bus, mock=True, execute=True)
    info = engine.compile_paper(repair=True)

    assert info["rounds"] >= 1, "应当尝试过回修"
    assert (run.path / "paper" / "main.tex").read_text(encoding="utf-8") == original, \
        "破坏性回修必须被回滚，原版必须完好"
    assert any("回滚" in (e.get("message") or "") for e in bus.events), "应当明确报出回滚"


def test_extract_files_accepts_bare_marker_without_fences() -> None:
    """实测事故：回修模型不写代码围栏，只给 `% file:` 开头的裸文本，不能被整体丢弃。"""
    text = (
        "% file: paper/main.tex\n\\documentclass{ctexart}\n"
        "\\begin{document}\n正文\n\\end{document}\n"
    )
    bundle = extract_files(text)
    assert "paper/main.tex" in bundle.files
    assert bundle.bare_blocks == ["paper/main.tex"]
    assert bundle.files["paper/main.tex"].startswith("% file:")
    assert "\\documentclass" in bundle.files["paper/main.tex"]


def test_extract_files_splits_multiple_bare_files() -> None:
    text = "# file: a.py\nprint(1)\n# file: b.py\nprint(2)\n"
    bundle = extract_files(text)
    assert set(bundle.files) == {"a.py", "b.py"}
    assert "print(1)" in bundle.files["a.py"]
    assert "print(2)" in bundle.files["b.py"]


def test_repair_budget_is_configurable() -> None:
    cfg = load_config(competition="cumcm", root=ROOT)
    assert cfg.run.repair_max_tokens == 64000, "编译回修要重发整篇论文，预算不能太小"


def test_parse_and_apply_latex_patches() -> None:
    from modemon.latex import apply_patches, parse_patches

    source = "\\begin{document}\n公式 $x_2$\n\\end{document}\n"
    patches = parse_patches('```json\n[{"find": "$x_2$", "replace": "$x_2^2$", "why": "补指数"}]\n```')
    assert len(patches) == 1
    patched, ok, notes = apply_patches(source, patches)
    assert ok and "$x_2^2$" in patched and notes[0].endswith("已应用")


def test_apply_patches_rejects_ambiguous_or_missing() -> None:
    from modemon.latex import apply_patches

    source = "AAA\nAAA\nBBB\n"
    _, ok, notes = apply_patches(source, [{"find": "AAA", "replace": "X"}])
    assert not ok and "不唯一" in notes[0]

    _, ok2, notes2 = apply_patches(source, [{"find": "ZZZ", "replace": "X"}])
    assert not ok2 and "未匹配" in notes2[0]


def test_parse_patches_ignores_other_json() -> None:
    from modemon.latex import parse_patches

    assert parse_patches('{"total": 9}') == []
    assert parse_patches("这里没有任何 JSON 数组") == []


def test_mock_pipeline_end_to_end(tmp_path: Path) -> None:
    """离线全流程：6 个环节全部完成，评审回路真的触发过修订。"""
    cfg = load_config(competition="cumcm", root=ROOT)
    run = RunDir(tmp_path / "runs", "test-run")
    bus = EventBus(events_file=run.events_file, verbose=False)

    engine = Engine(cfg, run, bus, mock=True, execute=False)
    state = engine.run_pipeline("这是一道测试赛题，用于验证流水线。")

    assert len(state["stages"]) == len(cfg.stages)
    assert all(rec["status"] == "done" for rec in state["stages"]), state["stages"]

    # 文本产物与代码产物都落盘
    assert (run.path / "artifacts" / "01_problem_analysis.md").exists()
    assert (run.path / "solve" / "main.py").exists()
    assert (run.path / "paper" / "main.tex").exists()

    # 评审回路：至少有一个环节经历了"需改 → 修订 → 通过"
    reviewed = [rec for rec in state["stages"] if rec["review_total"] is not None]
    assert reviewed, "评审环节没有产生任何评分"
    assert any(len(rec["reviews"]) >= 2 for rec in reviewed), "对抗回路没有触发修订"

    # 报告可回读，且不含体积巨大的中间文本
    report = run.load_report()
    assert report["run_id"] == "test-run"
    assert all("artifact_text" not in rec for rec in report["stages"])
