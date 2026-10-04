"""命令行入口：doctor / skills / run / runs / show / resume。"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from modemon import __version__
from modemon.artifacts import RunDir, list_runs, new_run_id, slugify
from modemon.config import PROJECT_ROOT, load_config
from modemon.events import EventBus
from modemon.compliance import check_compliance
from modemon.ingest import IngestError, load_problem_text
from modemon.latex import compile_tex, find_paper
from modemon.provenance import check_provenance
from modemon.report import write_report
from modemon.skills import list_skills
from modemon.workflow import Engine, Usage

app = typer.Typer(add_completion=False, help="Modemon —— 自研数学建模智能体")
console = Console()

PKGS = ["numpy", "matplotlib", "pandas", "scipy", "openai", "yaml", "pydantic", "typer", "rich", "jinja2"]


def _has(pkg: str) -> bool:
    return importlib.util.find_spec(pkg) is not None


@app.command()
def version() -> None:
    """打印版本。"""
    console.print(f"Modemon [bold]{__version__}[/bold]  (根目录 {PROJECT_ROOT})")


@app.command()
def doctor(competition: str = typer.Option("cumcm", "--competition", "-c")) -> None:
    """环境自检：解释器、依赖、LaTeX、API Key、Skill 与流水线。"""
    table = Table(title="环境自检", show_lines=False)
    table.add_column("项目", style="cyan")
    table.add_column("状态")
    table.add_column("说明", style="dim")

    table.add_row("Python", f"[green]{sys.version.split()[0]}[/green]", sys.executable)
    missing = [p for p in PKGS if not _has(p)]
    table.add_row(
        "依赖包",
        "[green]齐全[/green]" if not missing else f"[yellow]缺 {len(missing)}[/yellow]",
        "全部可用" if not missing else "缺失：" + ", ".join(missing) + "（求解代码需要 numpy/matplotlib/pandas/scipy）",
    )

    xelatex = shutil.which("xelatex")
    table.add_row("xelatex", "[green]可用[/green]" if xelatex else "[yellow]未找到[/yellow]",
                  xelatex or "论文编译需要 TeX Live（本机路径可由 PATH 提供）")
    pandoc = shutil.which("pandoc")
    table.add_row("pandoc", "[green]可用[/green]" if pandoc else "[dim]未找到[/dim]",
                  pandoc or "仅在需要导出 docx 时用到，可选")

    try:
        cfg = load_config(competition=competition)
    except Exception as exc:  # noqa: BLE001
        table.add_row("配置", "[red]加载失败[/red]", str(exc))
        console.print(table)
        raise typer.Exit(code=1) from exc

    key_ok = []
    for role in ("executor", "reviewer"):
        pc = cfg.provider_cfg(role)
        ok = bool(pc.resolve_key())
        key_ok.append((role, cfg.models[role].model, pc.api_key_env, ok))
    for role, model, env_name, ok in key_ok:
        table.add_row(
            f"{role} Key",
            "[green]已配置[/green]" if ok else "[yellow]未配置[/yellow]",
            f"{model} ← {env_name}" + ("" if ok else "（复制 .env.example 为 .env 后填入）"),
        )

    skills = list_skills(cfg.skills_dir)
    table.add_row("Skill", f"{len(skills)} 个", ", ".join(s.name for s in skills))
    table.add_row("流水线", f"{len(cfg.stages)} 步", " → ".join(s.id for s in cfg.stages))
    table.add_row("竞赛 Profile", f"{cfg.competition.get('name', competition)}",
                  f"语言={cfg.competition.get('language')} 页数上限={cfg.competition.get('page_limit')}")
    console.print(table)


@app.command()
def skills(competition: str = typer.Option("cumcm", "--competition", "-c")) -> None:
    """列出所有 Skill。"""
    cfg = load_config(competition=competition)
    table = Table(title=f"Skill（{cfg.skills_dir}）")
    for col in ("名称", "标题", "输入", "输出", "标签"):
        table.add_column(col)
    for s in list_skills(cfg.skills_dir):
        table.add_row(s.name, s.title, ", ".join(s.inputs), ", ".join(s.outputs), ", ".join(s.tags))
    console.print(table)


@app.command()
def run(
    problem: Path = typer.Option(..., "--problem", "-p", exists=True, dir_okay=False, readable=True,
                                 help="赛题文件：支持 .txt / .md / .pdf / .docx"),
    competition: str = typer.Option("cumcm", "--competition", "-c", help="竞赛 Profile：cumcm / mcm"),
    provider: str = typer.Option("auto", "--provider", help="auto=真实调用模型；mock=离线跑通管道"),
    run_id: str | None = typer.Option(None, "--run-id", help="自定义运行 ID"),
    from_stage: str | None = typer.Option(None, "--from-stage", help="从指定环节开始（跳过之前的）"),
    max_rounds: int | None = typer.Option(None, "--max-rounds", help="对抗评审最大轮数"),
    pass_score: float | None = typer.Option(None, "--pass-score", help="评审通过线（10 分制）"),
    executor_model: str | None = typer.Option(None, "--executor-model"),
    reviewer_model: str | None = typer.Option(None, "--reviewer-model"),
    execute: bool = typer.Option(True, "--execute/--no-execute", help="是否真实运行生成的代码"),
    thinking: str = typer.Option("auto", "--thinking", help="思考模式：auto=服务端默认；on=强制开；off=关闭（快很多）"),
    checkpoints: list[str] = typer.Option(None, "--checkpoint", help="在这些环节完成后暂停等待人工确认，可重复指定"),
    interactive: bool = typer.Option(True, "--interactive/--no-interactive",
                                     help="检查点是否等待键盘输入（后台运行时自动跳过）"),
    python_exe: str | None = typer.Option(None, "--python-exe", help="跑生成代码用的解释器路径"),
    quiet: bool = typer.Option(False, "--quiet", help="只输出关键事件"),
) -> None:
    """执行一次完整流水线。"""
    if provider not in ("auto", "mock"):
        raise typer.BadParameter("--provider 只能是 auto 或 mock")
    if thinking not in ("auto", "on", "off"):
        raise typer.BadParameter("--thinking 只能是 auto / on / off")

    cfg = load_config(
        competition=competition,
        executor_model=executor_model,
        reviewer_model=reviewer_model,
        max_review_rounds=max_rounds,
        pass_score=pass_score,
        thinking=None if thinking == "auto" else thinking,
        checkpoints=list(checkpoints) if checkpoints else None,
    )
    try:
        problem_text = load_problem_text(problem)
    except IngestError as exc:
        console.print(f"[red]读取赛题失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    rid = run_id or new_run_id(slugify(problem.stem, "problem"))
    rd = RunDir(cfg.runs_dir, rid)
    bus = EventBus(events_file=rd.events_file, console=console, verbose=not quiet)

    bus.emit("run_start", f"赛题：{problem.name}", detail=f"运行目录 {rd.path}")
    engine = Engine(cfg, rd, bus, mock=(provider == "mock"), execute=execute, python_exe=python_exe,
                    interactive=interactive)
    state = engine.run_pipeline(problem_text, problem_file=str(problem), from_stage=from_stage)

    table = Table(title="环节结果")
    for col in ("环节", "状态", "评审", "产物", "耗时(s)"):
        table.add_column(col)
    for rec in state["stages"]:
        total = rec.get("review_total")
        table.add_row(
            f"{rec['id']} {rec['title']}",
            "[green]done[/green]" if rec["status"] == "done" else f"[yellow]{rec['status']}[/yellow]",
            f"{total}/10" if total is not None else "—",
            ", ".join(rec.get("outputs", [])[:3]) or "—",
            str(rec.get("duration_s", "")),
        )
    console.print(table)
    usage = state["usage"]
    console.print(f"[bold]产物目录[/bold]：{rd.path}")
    if usage["cost_usd"] > 0:
        console.print(f"[bold]成本估算[/bold]：${usage['cost_usd']:.4f}（{usage['calls']} 次调用）")
    else:
        console.print(f"[bold]成本估算[/bold]：价格表未收录该模型，仅统计用量（{usage['calls']} 次调用）")
    console.print(
        f"[dim]tokens：输入 {usage['prompt_tokens']} / 输出 {usage['completion_tokens']}"
        f"（思考 token 计入输出）；可在 configs/default.yaml 的 pricing 段填价格后估算金额[/dim]"
    )


@app.command("compile")
def compile_run(
    run_id: str = typer.Argument(..., help="运行 ID"),
    competition: str = typer.Option("cumcm", "--competition", "-c"),
    repair: bool = typer.Option(False, "--repair/--no-repair", help="编译失败时调用执行者自动回修"),
    max_rounds: int = typer.Option(2, "--max-rounds", help="自动回修最大轮数"),
) -> None:
    """编译某次运行的论文（可选自动回修）。"""
    cfg = load_config(competition=competition)
    rd = RunDir(cfg.runs_dir, run_id, create=False)
    if not rd.report_file.exists():
        console.print(f"[red]找不到运行 {run_id}（{rd.path}）[/red]")
        raise typer.Exit(code=1)

    if not repair:
        tex = find_paper(rd.path)
        if tex is None:
            console.print("[yellow]该运行没有论文 .tex 文件[/yellow]")
            raise typer.Exit(code=1)
        res = compile_tex(tex, engine=cfg.run.latex_engine, timeout=cfg.run.compile_timeout_s,
                          log_dir=rd.path / "results", log_name="compile.log")
        head = "[green]编译成功[/green]" if res.ok else "[red]编译失败[/red]"
        console.print(f"{head} {res.message}  用时 {res.duration_s:.1f}s")
        if res.pdf:
            console.print(f"PDF：{res.pdf}（{res.pdf.stat().st_size} 字节）")
        if not res.ok:
            console.print("[dim]" + res.error_excerpt[:1500] + "[/dim]")
        return

    cfg.run.max_compile_rounds = max_rounds
    bus = EventBus(events_file=rd.events_file, console=console)
    engine = Engine(cfg, rd, bus, execute=True)
    engine.state = rd.load_report()
    engine.usage = Usage.from_dict(engine.state.get("usage") or {})
    info = engine.compile_paper(repair=True)
    head = "[green]编译成功[/green]" if info["status"] == "ok" else "[red]仍编译失败[/red]"
    console.print(f"{head}  回修 {info['rounds']} 轮  {info.get('message', '')}")
    if info.get("pdf"):
        console.print(f"PDF：{rd.path / 'paper' / info['pdf']}（{info['pdf_bytes']} 字节）")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="监听地址"),
    port: int = typer.Option(8765, "--port", help="监听端口"),
    competition: str = typer.Option("cumcm", "--competition", "-c"),
) -> None:
    """启动进度监控服务（浏览器打开 http://host:port 看实时事件流）。"""
    cfg = load_config(competition=competition)
    try:
        import uvicorn
    except ImportError:  # pragma: no cover
        console.print('[red]缺少 web 依赖：uv pip install --python .venv\\Scripts\\python.exe -e ".[web]"[/red]')
        raise typer.Exit(code=1) from None

    from modemon.web import create_app

    console.print(f"[green]监控服务启动[/green]  http://{host}:{port}   （运行目录：{cfg.runs_dir}）")
    console.print("[dim]按 Ctrl+C 停止[/dim]")
    uvicorn.run(create_app(cfg.root), host=host, port=port, log_level="warning")


@app.command("check")
def check_run(
    run_id: str = typer.Argument(..., help="运行 ID"),
    competition: str = typer.Option("cumcm", "--competition", "-c"),
    only: str = typer.Option("all", "--only", help="只跑其中一项：all / provenance / compliance"),
    min_ratio: float = typer.Option(0.0, "--min-ratio", help="匹配率低于该值则退出码 1（0=只报告不拦截）"),
    show: int = typer.Option(20, "--show", help="列出多少条未匹配数字"),
) -> None:
    """数值溯源 + 竞赛合规门禁：论文数字能否溯源、是否满足竞赛硬性要求。"""
    cfg = load_config(competition=competition)
    rd = RunDir(cfg.runs_dir, run_id, create=False)
    if not rd.report_file.exists():
        console.print(f"[red]找不到运行 {run_id}（{rd.path}）[/red]")
        raise typer.Exit(code=1)

    report = check_provenance(rd.path)
    rd.write_json("results/provenance_check.json", report.to_dict())

    if only in ("all", "provenance"):
        console.print(f"[bold]数值溯源核对[/bold]  {run_id}")
        console.print(f"论文中数值 {report.total} 个，找到出处 {report.matched} 个 "
                      f"→ 匹配率 [bold]{report.ratio * 100:.1f}%[/bold]")
        console.print(f"[dim]证据库：{report.evidence_count} 个数，来自 {', '.join(report.sources) or '（无）'}[/dim]")

        if report.unmatched:
            table = Table(title=f"未匹配的数字（前 {min(show, len(report.unmatched))} / {len(report.unmatched)} 条）")
            table.add_column("数值", style="yellow")
            table.add_column("文件", style="cyan")
            table.add_column("上下文", style="dim")
            for item in report.unmatched[:show]:
                table.add_row(item["value"], item["file"], item["context"][:90])
            console.print(table)
            console.print("[dim]提示：未匹配不等于错误——可能来自模型自设参数或四舍五入；请人工确认这些数字是否有依据。[/dim]")
        else:
            console.print("[green]全部数字都能在真实结果或赛题原文中找到出处。[/green]")

    comp = None
    if only in ("all", "compliance"):
        comp = check_compliance(rd.path, cfg.competition)
        rd.write_json("results/compliance_check.json", comp.to_dict())
        console.print(f"\n[bold]竞赛合规检查[/bold]  {cfg.competition.get('name', competition)}")
        ctable = Table(show_header=True, header_style="bold")
        ctable.add_column("检查项")
        ctable.add_column("结论")
        ctable.add_column("说明", style="dim")
        icons = {"pass": "[green]通过[/green]", "warn": "[yellow]提醒[/yellow]", "fail": "[red]不通过[/red]"}
        for item in comp.items:
            ctable.add_row(item.name, icons.get(item.status, item.status), item.detail)
        console.print(ctable)
        console.print(f"结论：[bold]{comp.verdict.upper()}[/bold]"
                      + (f"（页数 {comp.page_count}/{comp.page_limit}）" if comp.page_count else ""))

    failed = False
    if comp is not None and comp.verdict == "fail":
        failed = True
    if only in ("all", "provenance") and min_ratio > 0 and report.ratio < min_ratio:
        console.print(f"[red]匹配率低于门限 {min_ratio:.0%}，判定为不通过。[/red]")
        failed = True

    # 把门禁结论写回运行状态，这样 mma show / mma report 都能看到
    state = rd.load_report()
    state["provenance"] = report.to_dict()
    if comp is not None:
        state["compliance"] = comp.to_dict()
    rd.save_report(state)

    if failed:
        raise typer.Exit(code=1)


@app.command()
def report(
    run_id: str = typer.Argument(..., help="运行 ID"),
    competition: str = typer.Option("cumcm", "--competition", "-c"),
) -> None:
    """生成该运行的 Markdown 复盘报告（runs/<id>/REPORT.md）。"""
    cfg = load_config(competition=competition)
    rd = RunDir(cfg.runs_dir, run_id, create=False)
    if not rd.report_file.exists():
        console.print(f"[red]找不到运行 {run_id}（{rd.path}）[/red]")
        raise typer.Exit(code=1)

    path = write_report(rd.path, rd.load_report())
    console.print(f"[green]报告已生成[/green]：{path}")


@app.command()
def rerun(
    run_id: str = typer.Argument(..., help="运行 ID"),
    stage: str = typer.Argument(..., help="要重跑的环节 id（见 mma skills / pipeline.yaml）"),
    competition: str = typer.Option("cumcm", "--competition", "-c"),
    provider: str = typer.Option("auto", "--provider", help="auto=真实调用；mock=离线"),
    execute: bool = typer.Option(True, "--execute/--no-execute"),
    thinking: str = typer.Option("auto", "--thinking"),
    keep_downstream: bool = typer.Option(
        False, "--keep-downstream", help="保留该环节之后已完成的产物（默认一并作废，避免上下游不一致）"
    ),
) -> None:
    """只重跑某个环节：调完 Skill 或提示词后，几分钟验证效果，不必重跑整条流水线。"""
    cfg = load_config(competition=competition, thinking=None if thinking == "auto" else thinking)
    rd = RunDir(cfg.runs_dir, run_id, create=False)
    if not rd.report_file.exists():
        console.print(f"[red]找不到运行 {run_id}（{rd.path}）[/red]")
        raise typer.Exit(code=1)

    ids = [s.id for s in cfg.stages]
    if stage not in ids:
        console.print(f"[red]未知环节 {stage!r}，可选：{', '.join(ids)}[/red]")
        raise typer.Exit(code=1)

    state = rd.load_report()
    problem_file = state.get("problem_file") or ""
    if not problem_file or not Path(problem_file).exists():
        console.print("[red]报告里没有可用的赛题文件路径，无法重跑。[/red]")
        raise typer.Exit(code=1)

    index = ids.index(stage)
    if keep_downstream:
        kept = [r for r in state.get("stages", []) if r.get("id") != stage]
        console.print(f"[yellow]保留后续产物[/yellow]：重跑 {stage}，之后环节的记录不动（可能上下不一致）")
    else:
        kept = [r for r in state.get("stages", []) if r.get("id") in ids[:index]]
        dropped = [r.get("id") for r in state.get("stages", []) if r.get("id") not in ids[:index]]
        if dropped:
            console.print(f"[yellow]作废后续环节[/yellow]：{', '.join(str(d) for d in dropped)}")

    state["stages"] = kept
    state["status"] = "rerun"
    rd.save_report(state)

    problem_text = load_problem_text(Path(problem_file))
    bus = EventBus(events_file=rd.events_file, console=console)
    engine = Engine(cfg, rd, bus, mock=(provider == "mock"), execute=execute, interactive=False)
    engine.state = state
    engine.usage = Usage.from_dict(state.get("usage") or {})
    bus.emit("run_start", f"重跑 {run_id} 的环节 {stage}", detail=f"保留 {len(kept)} 个已完成环节")
    final = engine.run_pipeline(problem_text, problem_file=problem_file, from_stage=stage)
    console.print(f"[green]重跑完成[/green]：{rd.path}（状态 {final['status']}）")


@app.command()
def runs(competition: str = typer.Option("cumcm", "--competition", "-c")) -> None:
    """列出历史运行。"""
    cfg = load_config(competition=competition)
    table = Table(title=f"运行记录（{cfg.runs_dir}）")
    for col in ("运行 ID", "竞赛", "状态", "进度", "创建时间", "成本($)"):
        table.add_column(col)
    for r in list_runs(cfg.runs_dir):
        table.add_row(r["run_id"], str(r["competition"]), str(r["status"]),
                      f"{r['stage_index']}/{r['stages']}", str(r["created_at"]), f"{r['cost_usd']:.4f}")
    console.print(table)


@app.command()
def show(run_id: str = typer.Argument(..., help="运行 ID"), competition: str = typer.Option("cumcm", "--competition", "-c")) -> None:
    """查看某次运行的产物与评审轨迹。"""
    cfg = load_config(competition=competition)
    rd = RunDir(cfg.runs_dir, run_id, create=False)
    state = rd.load_report()

    console.print(f"[bold]运行 {run_id}[/bold]  竞赛={state.get('competition')}  状态={state.get('status')}")
    console.print(f"模型：执行者={state.get('models', {}).get('executor')}  评审者={state.get('models', {}).get('reviewer')}  离线={state.get('mock')}")
    console.print(f"成本：${state.get('usage', {}).get('cost_usd', 0):.4f}  tokens={state.get('usage', {}).get('prompt_tokens', 0)}+{state.get('usage', {}).get('completion_tokens', 0)}")

    for rec in state.get("stages", []):
        console.print(f"\n[cyan]▶ {rec['id']} · {rec['title']}[/cyan]  ({rec['status']})")
        scores = [f"第{i}轮 {r['total']}/10({'通过' if r['verdict'] == 'pass' else '需改'})"
                  for i, r in enumerate(rec.get("reviews", []), 1)]
        if scores:
            console.print("  评审：" + " → ".join(scores))
        for rel in rec.get("outputs", []):
            console.print(f"  · {rel}")
        for item in rec.get("exec_results", []):
            flag = "ok" if item.get("returncode") == 0 else f"exit={item.get('returncode')}"
            note = ""
            if item.get("result_json"):
                note = "  " + str(item["result_json"])[:160]
            console.print(f"  ⚙ {item['file']} [{flag}]{note}")

    compile_info = state.get("compile")
    if compile_info:
        status = compile_info.get("status")
        color = "green" if status == "ok" else "yellow"
        suffix = f" · 自动回修 {compile_info.get('rounds')} 轮" if compile_info.get("rounds") else ""
        console.print(f"\n[bold]编译[/bold]：[{color}]{status}[/{color}] {compile_info.get('message', '')}{suffix}")
        if compile_info.get("pdf"):
            console.print(f"  PDF：paper/{compile_info['pdf']}（{compile_info.get('pdf_bytes', 0)} 字节）")

    prov = state.get("provenance")
    if prov:
        console.print(f"[bold]数值溯源[/bold]：{prov.get('matched')}/{prov.get('total')} 命中"
                      f"（{prov.get('ratio', 0) * 100:.0f}%）· 证据 {prov.get('evidence_count')} 个数")

    comp = state.get("compliance")
    if comp:
        color = "green" if comp.get("verdict") == "pass" else ("yellow" if comp.get("verdict") == "warn" else "red")
        console.print(f"[bold]合规检查[/bold]：[{color}]{comp.get('verdict')}[/{color}]"
                      f" · 不通过 {comp.get('failed')} 项 / 提醒 {comp.get('warned')} 项")

    figures = rd.glob("figures/*.png")
    if figures:
        console.print("\n[bold]图表[/bold]：" + ", ".join(p.name for p in figures))
    console.print(f"\n产物根目录：{rd.path}")


@app.command()
def resume(
    run_id: str = typer.Argument(..., help="运行 ID"),
    competition: str = typer.Option("cumcm", "--competition", "-c"),
    provider: str = typer.Option("auto", "--provider"),
    execute: bool = typer.Option(True, "--execute/--no-execute"),
) -> None:
    """从上次中断处续跑（复用已有产物）。"""
    cfg = load_config(competition=competition)
    rd = RunDir(cfg.runs_dir, run_id, create=False)
    state = rd.load_report()
    problem_file = state.get("problem_file")
    if not problem_file or not Path(problem_file).exists():
        console.print("[red]报告里没有可用的赛题文件路径，无法续跑；请用 run --run-id 重新指定赛题。[/red]")
        raise typer.Exit(code=1)

    done = {r["id"] for r in state.get("stages", []) if r.get("status") in ("done", "needs_work")}
    pending = [s.id for s in cfg.stages if s.id not in done]
    if not pending:
        console.print("[green]该运行已全部完成，无需续跑。[/green]")
        return

    problem_text = load_problem_text(Path(problem_file))
    bus = EventBus(events_file=rd.events_file, console=console)
    engine = Engine(cfg, rd, bus, mock=(provider == "mock"), execute=execute)
    engine.state = state
    engine.usage = Usage.from_dict(state.get("usage") or {})  # 接回历史成本
    bus.emit("run_start", f"续跑 {run_id}", detail=f"从 {pending[0]} 开始")
    engine.run_pipeline(problem_text, problem_file=problem_file, from_stage=pending[0])
    console.print(f"[green]续跑完成[/green]：{rd.path}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
