"""工作流引擎：串起 Skill → 执行者 → 真实执行 → 对抗评审 → 修订 → 落盘 → 可恢复。

一条铁律：下游环节能看到的"事实"，只有真实执行产生的输出与人工确认过的产物。
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from modemon.artifacts import RunDir
from modemon.config import AppConfig, StageCfg
from modemon.events import EventBus
from modemon.execution import extract_files, run_python_files, write_files
from modemon.compliance import check_compliance
from modemon.latex import apply_patches, compile_tex, find_paper, parse_patches
from modemon.provenance import check_provenance
from modemon.providers import LLMProvider, LLMResponse, build_provider
from modemon.review import ReviewResult, build_revision_block, is_passing, number_policy, parse_review
from modemon.skills import load_skill

SYSTEM_PROMPT = (
    "你是数学建模竞赛团队中的资深专家。严格遵守用户给出的输出格式约定；"
    "绝对禁止编造数据、文献与实验结果——所有数值必须来自真实执行输出或题目原文。"
)

TEXT_SUFFIXES = {".md", ".tex", ".txt", ".json", ".csv"}


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    by_model: dict[str, dict[str, float]] = field(default_factory=dict)

    def add(self, resp: LLMResponse) -> None:
        self.calls += 1
        self.prompt_tokens += int(resp.usage.get("prompt_tokens", 0))
        self.completion_tokens += int(resp.usage.get("completion_tokens", 0))
        self.cost_usd += resp.cost_usd
        bucket = self.by_model.setdefault(resp.model, {"calls": 0, "cost_usd": 0.0})
        bucket["calls"] += 1
        bucket["cost_usd"] = round(bucket["cost_usd"] + resp.cost_usd, 6)

    def to_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "by_model": self.by_model,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Usage":
        """续跑时把历史成本接回来，避免覆盖已有账目。"""
        usage = cls()
        usage.calls = int(data.get("calls", 0))
        usage.prompt_tokens = int(data.get("prompt_tokens", 0))
        usage.completion_tokens = int(data.get("completion_tokens", 0))
        usage.cost_usd = float(data.get("cost_usd", 0.0))
        usage.by_model = dict(data.get("by_model") or {})
        return usage


class Engine:
    def __init__(
        self,
        cfg: AppConfig,
        run: RunDir,
        bus: EventBus,
        *,
        mock: bool = False,
        execute: bool = True,
        python_exe: str | None = None,
        interactive: bool = False,
    ) -> None:
        self.cfg = cfg
        self.run = run
        self.bus = bus
        self.mock = mock
        self.execute = execute
        self.python_exe = python_exe or cfg.run.solve_python
        self.interactive = interactive
        self.usage = Usage()
        self._reviewer: LLMProvider | None = None

        if not mock:
            self.executor: LLMProvider = build_provider(
                cfg.models["executor"], cfg.provider_cfg("executor"),
                retry=cfg.run.retry, timeout=cfg.run.request_timeout_s, pricing=cfg.pricing,
            )
        else:
            self.executor = build_provider(cfg.models["executor"], None, mock=True,
                                           retry=cfg.run.retry, timeout=cfg.run.request_timeout_s,
                                           pricing=cfg.pricing)

        self.state: dict[str, Any] = {
            "run_id": run.run_id,
            "competition": cfg.competition.get("id"),
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": "",
            "status": "created",
            "stage_index": 0,
            "mock": mock,
            "models": {
                "executor": cfg.models["executor"].model,
                "reviewer": cfg.models["reviewer"].model,
            },
            "stages": [],
            "usage": self.usage.to_dict(),
        }

    # ------------------------------------------------------------------ provider
    @property
    def reviewer(self) -> LLMProvider:
        if self._reviewer is None:
            if self.mock:
                self._reviewer = build_provider(
                    self.cfg.models["reviewer"], None, mock=True,
                    retry=self.cfg.run.retry, timeout=self.cfg.run.request_timeout_s, pricing=self.cfg.pricing,
                )
            else:
                self._reviewer = build_provider(
                    self.cfg.models["reviewer"], self.cfg.provider_cfg("reviewer"),
                    retry=self.cfg.run.retry, timeout=self.cfg.run.request_timeout_s, pricing=self.cfg.pricing,
                )
        return self._reviewer

    def _call(
        self,
        provider: LLMProvider,
        prompt: str,
        *,
        role: str,
        stage: StageCfg,
        rnd: int,
    ) -> LLMResponse:
        # 环节级 thinking 只作用于该环节的**执行者**：写作/绘图这类任务关思考是为了省预算，
        # 但评审者是质量门禁，应当保持自己的思考设置（默认服务端开启）。
        if role == "executor":
            thinking = stage.thinking or self.cfg.models[role].thinking
        else:
            thinking = self.cfg.models[role].thinking
        self.bus.emit(
            "llm_call",
            f"{role} 调用 {provider.model}（{stage.title} 第 {rnd} 轮）",
            detail=f"{len(prompt)} 字符 · 思考={thinking or '服务端默认'}",
        )
        resp = self._complete_with_heartbeat(provider, prompt, role=role, stage=stage, rnd=rnd, thinking=thinking)
        self.usage.add(resp)
        if resp.truncated:
            self.bus.emit(
                "warn",
                f"{provider.model} 输出被 max_tokens 截断（{stage.title} 第 {rnd} 轮）",
                detail=f"输出 {resp.usage.get('completion_tokens', '?')} tokens；建议提高该环节 max_tokens 或分章节生成",
            )
        self.usage.add(resp)
        self.bus.emit(
            "cost",
            f"{provider.model}: {resp.usage.get('prompt_tokens', 0)}+{resp.usage.get('completion_tokens', 0)} tokens"
            f" ≈ ${resp.cost_usd:.4f}",
            detail=f"{resp.duration_s:.1f}s",
        )
        return resp

    def _complete_with_heartbeat(
        self,
        provider: LLMProvider,
        prompt: str,
        *,
        role: str,
        stage: StageCfg,
        rnd: int,
        thinking: str | None,
    ) -> LLMResponse:
        """调用模型，并在等待期间定期发心跳事件。

        非流式接口在长调用期间没有任何中间信号，监控页上看起来像卡死；
        心跳只是"旁路"事件，不触碰请求本身，因此不会引入新的失败面。
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        meta = {"role": role, "stage_id": stage.id, "round": rnd, "thinking": thinking}
        interval = float(self.cfg.run.heartbeat_s or 0)
        if interval <= 0:
            return provider.complete(messages, meta=meta, thinking=thinking, max_tokens=stage.max_tokens)

        stop = threading.Event()
        started = time.time()

        def beat() -> None:
            while not stop.wait(interval):
                self.bus.emit(
                    "llm_wait",
                    f"仍在等待 {provider.model} 返回（{stage.title} 第 {rnd} 轮）",
                    detail=f"已等待 {time.time() - started:.0f}s",
                )

        thread = threading.Thread(target=beat, daemon=True)
        thread.start()
        try:
            return provider.complete(messages, meta=meta, thinking=thinking, max_tokens=stage.max_tokens)
        finally:
            stop.set()

    # ------------------------------------------------------------------ context
    def _competition_text(self) -> str:
        return yaml.safe_dump(self.cfg.competition, allow_unicode=True, sort_keys=False)

    def _build_context(self) -> str:
        """把已完成的产物与**真实执行结果**拼成下游可见的事实集合。"""
        chunks: list[str] = []
        total = 0

        for rec in self.state["stages"]:
            if rec.get("status") not in ("done", "needs_work", "review_failed"):
                continue
            head = f"## 已完成的环节：{rec['title']}（{rec['id']}）"
            body: list[str] = [head]

            for rel in rec.get("outputs", []):
                path = self.run.path / rel
                if not path.exists() or path.suffix.lower() not in TEXT_SUFFIXES:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")[: self.cfg.run.context_per_artifact]
                body.append(f"### 文件 {rel}\n```\n{text}\n```")

            if rec.get("exec_results"):
                lines = ["### 真实执行结果（论文中的数值只能取自此处）"]
                for item in rec["exec_results"]:
                    status = "成功" if item.get("returncode") == 0 else f"失败(exit={item.get('returncode')})"
                    lines.append(f"- `{item['file']}` → {status}")
                    if item.get("result_json"):
                        lines.append("```json\n" + json.dumps(item["result_json"], ensure_ascii=False, indent=2)[:4000] + "\n```")
                    elif item.get("stderr_tail"):
                        lines.append("```\n" + item["stderr_tail"][-1200:] + "\n```")
                body.append("\n".join(lines))

            block = "\n\n".join(body)
            if total + len(block) > self.cfg.run.context_total:
                chunks.append("（上下文已达上限，后续产物被截断）")
                break
            chunks.append(block)
            total += len(block)

        # 已生成的真实图表清单：不列出确切文件名，下游只能靠猜，必然猜错并导致编译失败
        chunks.append(self._figure_inventory())

        if not chunks:
            return "（暂无上游产物）"
        return "\n\n---\n\n".join(chunks)

    # ------------------------------------------------------------------ apply
    def _apply(self, stage: StageCfg, text: str) -> dict[str, Any]:
        if stage.kind == "code":
            bundle = extract_files(text)
            written = write_files(self.run.path, bundle.files)
            outputs = [p.relative_to(self.run.path).as_posix() for p in written]

            if not written:
                self.bus.emit(
                    "warn",
                    f"[{stage.id}] 未从回复中抽到任何文件，本环节产出为空",
                    detail=f"跳过 {len(bundle.skipped)} 个代码块"
                    + (f"；未闭合（疑似截断）{len(bundle.unterminated)} 个" if bundle.unterminated else ""),
                )
            elif bundle.bare_blocks:
                self.bus.emit(
                    "warn",
                    f"[{stage.id}] 回复未使用代码围栏，已按 `# file:` 标记裸文本落盘：{', '.join(bundle.bare_blocks)}",
                )
            if written and bundle.unterminated:
                self.bus.emit(
                    "warn",
                    f"[{stage.id}] 代码块未闭合（疑似被截断）：{', '.join(bundle.unterminated)}",
                    detail="已按实际内容落盘，请检查是否完整",
                )

            exec_results: list[dict[str, Any]] = []
            if stage.execute and self.execute and written:
                self.bus.emit("exec", f"真实运行 {len([p for p in written if p.suffix == '.py'])} 个脚本",
                              detail="工作目录=运行根目录")
                results = run_python_files(
                    self.run.path,
                    written,
                    python_exe=self.python_exe,
                    timeout=self.cfg.run.execute_timeout_s,
                )
                exec_results = [r.summary() for r in results]
                for r in results:
                    flag = "成功" if r.ok else f"失败(exit={r.returncode})"
                    detail = ""
                    if r.result_json:
                        detail = json.dumps(r.result_json, ensure_ascii=False)[:200]
                    self.bus.emit("exec", f"{r.file} → {flag}", detail=detail)
                self.run.write_json(f"results/execution_{stage.id}.json", exec_results)

            return {
                "outputs": outputs,
                "exec_results": exec_results,
                "skipped_blocks": bundle.skipped,
                "unterminated_blocks": bundle.unterminated,
            }

        rel = stage.artifact or f"artifacts/{stage.id}.md"
        self.run.write_text(rel, text)
        return {"outputs": [rel], "exec_results": [], "skipped_blocks": []}

    # ------------------------------------------------------------------ stages
    def _has_execution_results(self) -> bool:
        """本次运行是否已经产出真实运行结果（决定评审的数值口径）。"""
        for rec in self.state["stages"]:
            for item in rec.get("exec_results") or []:
                if item.get("result_json") is not None:
                    return True
        return False

    def _review_stage(
        self,
        stage: StageCfg,
        context: str,
        artifact_text: str,
        rnd: int,
        previous: ReviewResult | None = None,
    ) -> ReviewResult:
        skill = load_skill("review", self.cfg.skills_dir)
        prompt = skill.render(
            stage_title=stage.title,
            stage_id=stage.id,
            competition=self._competition_text(),
            artifact=artifact_text[: self.cfg.run.context_per_artifact * 3],
            context=context,
            pass_score=self.cfg.run.pass_score,
            number_policy=number_policy(self._has_execution_results()),
            previous_must_fix=(previous.must_fix if previous else []),
            previous_total=(previous.total if previous else None),
        )
        self.run.write_text(f"prompts/review_{stage.id}_round{rnd}.txt", prompt)
        resp = self._call(self.reviewer, prompt, role="reviewer", stage=stage, rnd=rnd)
        self.run.write_text(f"logs/review_{stage.id}_round{rnd}_raw.json", resp.text)
        return parse_review(resp.text, stage=stage.id, model=resp.model)

    def _process_stage(self, stage: StageCfg, problem_text: str, context: str) -> dict[str, Any]:
        started = time.time()
        skill = load_skill(stage.skill, self.cfg.skills_dir)
        base_prompt = skill.render(
            problem_text=problem_text,
            competition=self._competition_text(),
            context=context,
            stage_id=stage.id,
            stage_title=stage.title,
            pass_score=self.cfg.run.pass_score,
        )

        record: dict[str, Any] = {
            "id": stage.id,
            "title": stage.title,
            "kind": stage.kind,
            "status": "running",
            "reviews": [],
            "review_total": None,
            "outputs": [],
            "exec_results": [],
            "skipped_blocks": [],
            "rounds": 0,
        }
        self.bus.emit("stage_start", f"[{stage.id}] {stage.title}")

        self.run.write_text(f"prompts/{stage.id}_round0.txt", base_prompt)
        resp = self._call(self.executor, base_prompt, role="executor", stage=stage, rnd=0)
        self.run.write_text(f"logs/{stage.id}_round0_raw.md", resp.text)
        record.update(self._apply(stage, resp.text))
        record["rounds"] = 1
        current_text = resp.text

        if stage.review:
            previous_review: ReviewResult | None = None
            for rnd in range(1, self.cfg.run.max_review_rounds + 1):
                try:
                    review = self._review_stage(stage, context, current_text, rnd, previous_review)
                except Exception as exc:  # noqa: BLE001 —— 评审接口故障不该毁掉已产出的成果
                    record["review_error"] = f"{type(exc).__name__}: {exc}"
                    record["status"] = "review_failed"
                    self.bus.emit("error", f"[{stage.id}] 评审调用失败，保留当前产出：{exc}")
                    break
                record["reviews"].append(review.to_dict())
                previous_review = review
                record["review_total"] = review.total
                detail = f"必改 {len(review.must_fix)} 条 · 高严重度 {len(review.blockers)} 条"
                if review.previous_check:
                    detail += f" · 上轮已落实 {len(review.resolved_previous)}/{len(review.previous_check)} 条"
                self.bus.emit(
                    "review",
                    f"[{stage.id}] 评审 {review.total}/10 → {review.verdict or 'revise'}"
                    + ("" if review.parsed else "（JSON 解析失败）"),
                    detail=detail,
                )
                if is_passing(review, self.cfg.run.pass_score, self.cfg.run.require_no_blockers):
                    break
                if rnd == self.cfg.run.max_review_rounds:
                    record["status"] = "needs_work"
                    self.bus.emit("warn", f"[{stage.id}] 已达评审轮次上限仍未通过，保留当前版本")
                    break

                self.bus.emit("revise", f"[{stage.id}] 按评审意见修订（第 {rnd} 轮）")
                rev_prompt = (
                    base_prompt
                    + build_revision_block(review)
                    + "\n\n# 上一轮你的产出（在此基础上修订）\n\n"
                    + current_text[: self.cfg.run.context_per_artifact * 3]
                )
                self.run.write_text(f"prompts/{stage.id}_revise{rnd}.txt", rev_prompt)
                resp = self._call(self.executor, rev_prompt, role="executor", stage=stage, rnd=rnd)
                self.run.write_text(f"logs/{stage.id}_revise{rnd}_raw.md", resp.text)
                record.update(self._apply(stage, resp.text))
                record["rounds"] = rnd + 1
                current_text = resp.text

        if record["status"] == "running":
            record["status"] = "done"
        record["artifact_text"] = current_text
        record["duration_s"] = round(time.time() - started, 2)
        self.bus.emit("stage_done", f"[{stage.id}] {stage.title} 完成",
                      detail=f"{record['duration_s']}s")
        return record

    def _report_state(self) -> dict[str, Any]:
        """落盘用的状态：剥掉体积大的中间文本，避免 report.json 膨胀。"""
        state = {k: v for k, v in self.state.items() if k != "stages"}
        state["stages"] = [
            {k: v for k, v in rec.items() if k != "artifact_text"} for rec in self.state["stages"]
        ]
        return state

    # ------------------------------------------------------------------ 编译闭环
    def _figure_inventory(self) -> str:
        """真实图表清单：不给出确切文件名，模型只能猜，并必然猜错。"""
        figures = sorted(self.run.path.glob("figures/*.png")) + sorted(self.run.path.glob("figures/*.pdf"))
        if not figures:
            return "（本次运行没有生成图表文件）"
        lines = ["## 已生成的真实图表文件（必须**逐字引用**下列路径，不要自行编造文件名）"]
        for path in figures:
            lines.append(f"- `{path.relative_to(self.run.path).as_posix()}`（{path.stat().st_size:,} 字节）")
        lines.append("")
        lines.append("在 LaTeX 中引用时，从 paper/ 出发的相对路径形如 `../figures/<上述文件名>`。")
        return "\n".join(lines)

    def _paper_source_text(self, limit_each: int = 14000) -> str:
        """把论文源文件拼给模型看，用于编译回修。"""
        paper_dir = self.run.path / "paper"
        chunks: list[str] = []
        if paper_dir.exists():
            for path in sorted(paper_dir.rglob("*")):
                if path.is_file() and path.suffix.lower() in (".tex", ".bib", ".cls", ".sty"):
                    text = path.read_text(encoding="utf-8", errors="replace")[:limit_each]
                    rel = path.relative_to(self.run.path).as_posix()
                    chunks.append(f"### {rel}\n```\n{text}\n```")
        return "\n\n".join(chunks) or "（没有找到论文源文件）"

    def compile_paper(self, *, repair: bool | None = None) -> dict[str, Any]:
        """编译论文；失败时把报错回灌给执行者自动回修，直到成功或轮次用尽。"""
        tex = find_paper(self.run.path)
        if tex is None:
            info: dict[str, Any] = {"status": "skipped", "message": "没有找到论文 .tex 文件，跳过编译"}
            self.state["compile"] = info
            self.run.save_report(self._report_state())
            return info

        repair_enabled = self.cfg.run.compile_paper if repair is None else repair
        attempts: list[dict[str, Any]] = []
        comp = compile_tex(
            tex,
            engine=self.cfg.run.latex_engine,
            timeout=self.cfg.run.compile_timeout_s,
            log_dir=self.run.path / "results",
            log_name="compile.log",
        )
        attempts.append(comp.to_dict())
        self.bus.emit("exec", f"{self.cfg.run.latex_engine} 编译 {tex.name} → {'成功' if comp.ok else '失败'}",
                      detail=comp.message)

        rounds = 0
        original_tex = tex.read_text(encoding="utf-8", errors="replace")
        while not comp.ok and repair_enabled and rounds < self.cfg.run.max_compile_rounds:
            rounds += 1
            self.bus.emit("revise", f"编译失败，第 {rounds} 轮自动回修", detail=f"错误摘要 {len(comp.error_excerpt)} 字符")
            stage = StageCfg(id="latex_fix", title="LaTeX 编译修复", skill="latex_fix", kind="code",
                             artifact="paper/", max_tokens=self.cfg.run.repair_max_tokens)
            skill = load_skill("latex_fix", self.cfg.skills_dir)
            prompt = skill.render(
                compile_log=comp.error_excerpt,
                paper_files=self._paper_source_text(),
                figures=self._figure_inventory(),
                competition=self._competition_text(),
            )
            self.run.write_text(f"prompts/latex_fix_round{rounds}.txt", prompt)
            try:
                resp = self._call(self.executor, prompt, role="executor", stage=stage, rnd=rounds)
            except Exception as exc:  # noqa: BLE001 —— 回修失败不应中断整条流水线
                self.bus.emit("error", f"回修调用失败，保留当前版本：{exc}")
                break
            self.run.write_text(f"logs/latex_fix_round{rounds}_raw.md", resp.text)
            # 回修前对论文源文件做快照：实测回修模型可能只输出部分文件，
            # 若无保护就会把一篇完整论文覆盖成半成品（50K 字符 → 14K 字符）。
            paper_dir = self.run.path / "paper"
            snapshot = {p: p.read_text(encoding="utf-8", errors="replace") for p in paper_dir.rglob("*.tex")}
            applied = self._apply(stage, resp.text)
            repaired = tex.read_text(encoding="utf-8", errors="replace") if tex.exists() else ""

            problem: str | None = None
            if not applied.get("outputs"):
                problem = "模型未返回可写入的文件"
            elif len(repaired) < len(original_tex) * 0.8:
                problem = f"内容从 {len(original_tex)} 字符骤减到 {len(repaired)} 字符，疑似只输出了部分文件"
            elif "\\end{document}" not in repaired:
                problem = "缺少 \\end{document}，文档不完整"

            if problem:
                # 回滚整文件覆盖造成的破坏，再尝试补丁式修复（输出量小，不受输出上限影响）
                for path, content in snapshot.items():
                    path.write_text(content, encoding="utf-8")
                for path in paper_dir.rglob("*.tex"):
                    if path not in snapshot:
                        path.unlink()

                patches = parse_patches(resp.text)
                if not patches:
                    self.bus.emit("warn", f"回修产出不可用，已回滚保留原版：{problem}")
                    break
                patched, ok, notes = apply_patches(original_tex, patches)
                if ok and "\\end{document}" in patched and len(patched) >= len(original_tex) * 0.8:
                    tex.write_text(patched, encoding="utf-8")
                    original_tex = patched
                    self.run.write_json(f"results/latex_patch_round{rounds}.json",
                                        {"patches": patches, "notes": notes})
                    self.bus.emit("revise", f"已应用 {len(patches)} 处补丁式修复",
                                  detail="; ".join(notes[:3]))
                else:
                    self.bus.emit("warn", f"补丁式修复未生效，保持原版：{'; '.join(notes[:3])}")
                    break

            comp = compile_tex(
                tex,
                engine=self.cfg.run.latex_engine,
                timeout=self.cfg.run.compile_timeout_s,
                log_dir=self.run.path / "results",
                log_name="compile.log",
            )
            attempts.append(comp.to_dict())
            self.bus.emit("exec", f"第 {rounds} 轮回修后编译 → {'成功' if comp.ok else '失败'}", detail=comp.message)

        info = {
            "status": "ok" if comp.ok else ("failed" if repair_enabled else "failed_no_repair"),
            "rounds": rounds,
            "engine": self.cfg.run.latex_engine,
            "pdf": comp.pdf.name if comp.pdf else None,
            "pdf_bytes": comp.pdf.stat().st_size if comp.pdf and comp.pdf.exists() else 0,
            "message": comp.message,
            "error_excerpt": "" if comp.ok else comp.error_excerpt[:4000],
            "attempts": attempts,
        }
        self.state["compile"] = info
        self.state["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.state["usage"] = self.usage.to_dict()
        self.run.write_json("results/compile_summary.json", info)
        self.run.save_report(self._report_state())
        return info

    def check_provenance_gate(self) -> dict[str, Any]:
        """数值溯源门禁：论文里的数字必须在真实执行结果或赛题原文中找得到。"""
        report = check_provenance(self.run.path)
        info = report.to_dict()
        self.state["provenance"] = info
        self.run.write_json("results/provenance_check.json", info)
        sample = info["unmatched"][0]["value"] if info["unmatched"] else "无"
        self.bus.emit(
            "review",
            f"数值溯源：{info['matched']}/{info['total']} 个数字找到出处（{info['ratio'] * 100:.0f}%）",
            detail=f"未匹配示例 {sample} · 证据 {info['evidence_count']} 个数",
        )
        self.run.save_report(self._report_state())
        return info

    def check_compliance_gate(self) -> dict[str, Any]:
        """竞赛合规门禁：页数、必备章节、图表引用、参考文献、占位符残留。"""
        report = check_compliance(self.run.path, self.cfg.competition)
        info = report.to_dict()
        self.state["compliance"] = info
        self.run.write_json("results/compliance_check.json", info)
        self.bus.emit(
            "review",
            f"合规检查：{info['verdict'].upper()}",
            detail=f"不通过 {info['failed']} 项 · 提醒 {info['warned']} 项",
        )
        self.run.save_report(self._report_state())
        return info

    # ------------------------------------------------------------------ 检查点
    def _should_checkpoint(self, stage: StageCfg) -> bool:
        return bool(self.interactive and stage.id in (self.cfg.run.checkpoints or []))

    def _checkpoint_action(self, stage: StageCfg, record: dict[str, Any]) -> str:
        """在关键决策点暂停，等待人工确认：继续 / 重跑本环节 / 中止。"""
        total = record.get("review_total")
        must_fix: list[str] = []
        for review in record.get("reviews") or []:
            must_fix.extend(review.get("must_fix") or [])

        detail = f"评审 {total}/10 · 必改 {len(must_fix)} 条" if total is not None else "该环节无评审"
        self.bus.emit("checkpoint", f"检查点：{stage.title} 已完成", detail=detail)
        for item in must_fix[:5]:
            self.bus.console.print(f"    [yellow]·[/yellow] {item}")
        outputs = ", ".join(record.get("outputs") or []) or "（无产物）"
        self.bus.console.print(f"    [dim]产物：{outputs}[/dim]")

        while True:
            try:
                choice = self.bus.console.input(
                    "    [bold][c][/bold] 继续   [bold][r][/bold] 重跑本环节   [bold][q][/bold] 中止  > "
                ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                return "continue"  # 非交互环境（如后台运行）不阻塞流水线
            if choice in ("", "c", "continue", "继续"):
                return "continue"
            if choice in ("r", "rerun", "重跑"):
                self.bus.emit("checkpoint", f"按人工要求重跑环节 {stage.id}")
                return "rerun"
            if choice in ("q", "quit", "中止"):
                return "quit"
            self.bus.console.print("    [dim]请输入 c（继续）/ r（重跑）/ q（中止）[/dim]")

    # ------------------------------------------------------------------ run
    def run_pipeline(
        self,
        problem_text: str,
        *,
        problem_file: str | None = None,
        from_stage: str | None = None,
    ) -> dict[str, Any]:
        self.state["problem_file"] = problem_file
        self.state["status"] = "running"
        start_idx = 0
        if from_stage:
            ids = [s.id for s in self.cfg.stages]
            if from_stage not in ids:
                raise ValueError(f"未知环节 {from_stage!r}，可选：{', '.join(ids)}")
            start_idx = ids.index(from_stage)

        self.bus.emit("run_start", f"运行 {self.run.run_id} 启动", detail=f"竞赛={self.state['competition']} 从第 {start_idx + 1} 步开始")
        self.run.write_text("artifacts/00_problem.md", problem_text)

        for idx, stage in enumerate(self.cfg.stages):
            if idx < start_idx:
                continue
            if any(rec.get("id") == stage.id and rec.get("status") in ("done", "needs_work") for rec in self.state["stages"]):
                self.bus.emit("warn", f"[{stage.id}] 已有完成记录，跳过（用 --from-stage 可重跑）")
                continue

            context = self._build_context()
            try:
                record = self._process_stage(stage, problem_text, context)
            except Exception as exc:  # noqa: BLE001 —— 长跑流水线必须可续跑，不能整条崩掉
                self.bus.emit("error", f"[{stage.id}] 环节执行失败：{exc}")
                self.state["status"] = "failed"
                self.state["error"] = f"{stage.id}: {type(exc).__name__}: {exc}"
                self.state["usage"] = self.usage.to_dict()
                self.state["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                self.run.save_report(self._report_state())
                self.bus.emit("warn", f"进度已保存，可用 mma resume {self.run.run_id} 续跑")
                return self.state
            self.state["stages"] = [r for r in self.state["stages"] if r.get("id") != stage.id] + [record]
            self.state["stage_index"] = idx + 1
            self.state["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            self.state["usage"] = self.usage.to_dict()
            self.run.save_report(self._report_state())

            # 人工检查点：暂停等待确认 / 重跑 / 中止
            while self._should_checkpoint(stage):
                action = self._checkpoint_action(stage, record)
                if action == "continue":
                    break
                if action == "quit":
                    self.state["status"] = "aborted_at_checkpoint"
                    self.state["usage"] = self.usage.to_dict()
                    self.state["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    self.run.save_report(self._report_state())
                    self.bus.emit("checkpoint", f"在检查点 {stage.id} 人工中止运行")
                    return self.state
                # rerun：先摘掉本环节记录，保证上下文里不含它自己的产物
                self.state["stages"] = [r for r in self.state["stages"] if r.get("id") != stage.id]
                context = self._build_context()
                record = self._process_stage(stage, problem_text, context)
                self.state["stages"] = [r for r in self.state["stages"] if r.get("id") != stage.id] + [record]
                self.state["usage"] = self.usage.to_dict()
                self.run.save_report(self._report_state())

        self.state["status"] = "done" if all(
            r.get("status") == "done" for r in self.state["stages"]
        ) else "finished_with_issues"
        self.state["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.state["usage"] = self.usage.to_dict()
        self.run.save_report(self._report_state())

        if self.execute and self.cfg.run.compile_paper:
            info = self.compile_paper()
            if info.get("status") == "ok":
                self.bus.emit("artifact", f"论文已编译：{info.get('pdf')}",
                              detail=f"{info.get('pdf_bytes', 0)} 字节")
            else:
                self.bus.emit("warn", "论文未能编译成功，运行标记为有遗留问题")
                self.state["status"] = "finished_with_issues"
                self.run.save_report(self._report_state())
            self.check_provenance_gate()
            self.check_compliance_gate()

        from modemon.report import write_report  # 局部导入避免循环依赖

        report_path = write_report(self.run.path, self._report_state())

        self.bus.emit(
            "run_done",
            f"运行结束：{self.state['status']}",
            detail=f"{self.usage.calls} 次调用 · ${self.usage.cost_usd:.4f} · 产物在 {self.run.path}"
            f" · 复盘报告 {report_path.name}",
        )
        return self.state
