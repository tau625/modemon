#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""完整 8 步国赛流水线真实执行。

走真实 HTTP + WebSocket + 真实 Claude Code，检查点自动批准（模拟人工确认）。
每步预算与总预算都有上限，超限即停。

用法：
    python run_full_pipeline.py [--budget-per-step 0.35] [--budget-total 2.20]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

BASE = "http://127.0.0.1:8770"
OUT = Path(r"E:\02_Installers\DailyApps\Modex-MH-Agent-RE\reports\23-full-pipeline.md")

PROBLEM = """2026 年全国大学生数学建模竞赛 A 题（模拟）

某物流公司运营 3 个配送中心（DC1/DC2/DC3）与 4 个需求点（R1–R4）。
各配送中心的可用供应量为 DC1=35、DC2=25、DC3=30（单位：吨）。
各需求点的需求量为 R1=20、R2=25、R3=20、R4=25（单位：吨）。
单位运价矩阵（元/吨）如下：

        R1   R2   R3   R4
DC1      8   12   10   14
DC2     11    7   13    9
DC3     12   10    6   11

请建立数学模型，求总运输成本最小的调运方案，并回答：
（1）最优调运方案与最小总成本；
（2）若 DC2 的供应量因故障下降 30%，最优成本如何变化；
（3）给出该方案对运价整体波动的稳定性分析。

要求：论文包含摘要、问题重述、模型假设、符号说明、模型建立、
求解结果、灵敏度分析与参考文献，篇幅不超过 30 页。
"""

#: 每步的额外提示（相当于把 skill 契约交给 agent）
STEP_HINTS: dict[str, str] = {
    "comp-prob-analysis": "把赛题原文中的全部数据（运价矩阵、供应量、需求量）逐条抄录进分析文件，"
                          "不要遗漏任何数值。",
    "comp-code": "用 Python 求解，**必须**把原料结果写入 `figures/all_results.json`"
                 "（含最优目标值、各变量取值、三个情景的对比、迭代次数与耗时）。"
                 "论文中的任何数值都必须来自该文件。",
    "paper-figure": "画图时**必须先配置中文字体**，否则中文会变成方框："
                    "`import matplotlib; matplotlib.rcParams['font.sans-serif']=['SimHei'];"
                    "matplotlib.rcParams['axes.unicode_minus']=False`。"
                    "图片命名为 `fig_<英文名>.png`，并在 `figures/FIGURE_MANIFEST.md` 中登记。",
    "paper-figure-drawio": "画流程图/架构图，命名以 `tikz_` 开头，并在 FIGURE_MANIFEST.md 登记。",
    "comp-review": "对建模与求解做对抗式复核，指出最可能被评委质疑的点，写入 COMP_REVIEW.md。",
    "comp-paper-zh": "撰写完整论文，写入 `paper/main.tex`（XeLaTeX + ctex 可编译）。"
                     "所有数值必须与 `figures/all_results.json` 一致；"
                     "表格用 booktabs 三线表；公式用 LaTeX 数学环境。"
                     "**不要在加粗标签内写冒号**（写成 `**标签**：内容`）。",
    "comp-compile-zh": "用 xelatex 编译 `paper/main.tex` 生成 `paper/main.pdf`"
                       "（编译两遍以解析交叉引用）。若缺宏包请如实记录，不要伪造 PDF。",
}


def http(method: str, path: str, body: dict | None = None, timeout: float = 60) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def build_workspace() -> Path:
    ws = Path(tempfile.mkdtemp(prefix="modemon-full-")) / "ws"
    (ws / "user_data").mkdir(parents=True)
    (ws / "user_data" / "problem.txt").write_text(PROBLEM, encoding="utf-8")
    return ws


def run_pipeline(budget_per_step: float, budget_total: float,
                 time_limit_s: float = 0.0,
                 resume_wf: str = "", workspace: str = "",
                 step_deadline_s: float = 3600.0) -> int:
    print("=" * 78)
    print("完整 8 步国赛流水线（真实 Claude Code + HTTP + 检查点）")
    print("=" * 78)

    if resume_wf:
        wf_id = resume_wf
        wf = http("GET", f"/api/workflows/{wf_id}")
        if not workspace:
            raise SystemExit("--resume 必须同时给出 --workspace（工作区不能从库里反推）")
        ws = Path(workspace)
        print("**续跑已有工作流**:", wf_id)
        done0 = [s["skill_name"] for s in wf["steps"] if s["status"] == "completed"]
        print("已完成步骤（将跳过）:", done0 or "无")
    else:
        ws = build_workspace()
        wf = http("POST", "/api/workflows", {
            "template": "comp_cumcm", "title": "2026 国赛 A 题（全流程）",
            "enable_checkpoints": True,
        })
        wf_id = wf["id"]

    print("工作区:", ws)
    print("每步预算上限: %s   总预算上限: %s"
          % (("$%.2f" % budget_per_step) if budget_per_step > 0 else "不限",
             ("$%.2f" % budget_total) if budget_total > 0 else "不限"))
    print("单步等待上限: %.0f 分钟" % (step_deadline_s / 60))
    if time_limit_s:
        print("总时间上限: %.0f 分钟（比赛时间约束）" % (time_limit_s / 60))
    print()

    wf = http("GET", f"/api/workflows/{wf_id}")
    steps = [s["skill_name"] for s in wf["steps"]]
    print("工作流:", wf_id, "步骤:", len(steps))
    for i, s in enumerate(steps, 1):
        print("  %d. %s" % (i, s))
    print()

    records: list[dict] = []
    total_cost = 0.0
    interrupted = ""
    started_all = time.monotonic()

    for idx, skill in enumerate(steps, 1):
        # 续跑时跳过已完成（以及正在跑的，下面会等）
        cur = http("GET", f"/api/workflows/{wf_id}")
        sv = next((s for s in cur["steps"] if s["skill_name"] == skill), {})
        if sv.get("status") == "completed":
            print("跳过已完成: %s" % skill)
            records.append({"skill": skill, "status": "completed", "duration_s": 0,
                            "skipped": True})
            continue

        if budget_total > 0 and total_cost >= budget_total:
            interrupted = f"总预算已达上限 ${total_cost:.3f}"
            print("!! " + interrupted)
            break
        elapsed = time.monotonic() - started_all
        if time_limit_s and elapsed >= time_limit_s:
            interrupted = f"时间已达上限 {elapsed / 60:.1f} 分钟"
            print("!! " + interrupted)
            break

        print("-" * 78)
        print("步骤 %d/%d: %s   （已用 %.1f 分钟）" % (idx, len(steps), skill, elapsed / 60))
        print("-" * 78)

        q = urllib.parse.urlencode({
            "workspace": str(ws),
            "max_budget_usd": budget_per_step,
            "extra_prompt": STEP_HINTS.get(skill, ""),
            # ★ 必须放开权限，否则 Claude Code 的沙箱会拦住解释器执行——
            #   实测 agent 明确报出 "The sandbox gates interpreter execution"，
            #   于是 comp-code 无法运行求解脚本，卡在反复试探里出不来。
            #   本流水线在独立临时工作区运行，属于"自主求解"的正常模式。
            "permission_mode": "bypassPermissions",
        })
        t0 = time.monotonic()
        try:
            acc = http("POST", f"/api/workflows/{wf_id}/steps/{skill}/run?{q}", None, 60)
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                print("  该工作流已有任务在跑（409），等待其结束…")
                acc = {"accepted": False, "note": "waited for in-flight task"}
            else:
                print("  启动失败:", exc)
                records.append({"skill": skill, "status": "launch_failed", "error": str(exc)})
                continue

        # 轮询至完成（后台任务）。
        #
        # ⚠️ 单步等待上限**不是失败**，只是"这步比预期慢"。
        #   实测踩过：comp-code 跑了 25 分钟被脚本判超时 `break` 退出，
        #   但那步骤其实还在后台正常推进——脚本自己掐断了流水线，
        #   而不是步骤真的挂了。
        #   因此改为：超过单步上限时**只提示、继续等**（继续以同样的上限
        #   续等），只有**总时间预算**耗尽才真正停下来。
        status = "running"
        step_view = {}
        deadline = time.monotonic() + step_deadline_s
        last_note = 0.0
        waited_rounds = 0
        while True:
            if time_limit_s and (time.monotonic() - started_all) >= time_limit_s:
                interrupted = f"{skill} 时总时间预算耗尽"
                break
            w = http("GET", f"/api/workflows/{wf_id}")
            step_view = next((s for s in w["steps"] if s["skill_name"] == skill), {})
            status = step_view.get("status", "?")
            if status != "running":
                break
            if time.monotonic() > deadline:
                waited_rounds += 1
                print("  …单步等待已达 %.0f 分钟，仍在执行——继续等（不中断）"
                      % (step_deadline_s / 60))
                deadline = time.monotonic() + step_deadline_s
            if time.monotonic() - last_note > 120:
                print("    …仍在执行（%.1f 分钟）" % ((time.monotonic() - t0) / 60))
                last_note = time.monotonic()
            time.sleep(5)

        if status == "running":
            records.append({"skill": skill, "status": "aborted_running",
                            "duration_s": round(time.monotonic() - t0, 1)})
            break

        dt = time.monotonic() - t0

        # 从运行事件里取**本次 run** 的花费（total_cost_usd 是单次 CLI 调用的累计值）
        cost = None
        try:
            ev = http("GET", f"/api/workflows/{wf_id}/run-events?all_messages=true&limit=3000")
            per_run: dict[str, float] = {}
            for e in ev["events"]:
                evd = e.get("evidence") or {}
                c = evd.get("cost_usd")
                if isinstance(c, (int, float)):
                    per_run[e["run_id"]] = max(per_run.get(e["run_id"], 0.0), float(c))
            # 该步的 run_id 取自最近一组事件
            step_runs = [e["run_id"] for e in ev["events"]
                         if e.get("kind") == "started"]
            if step_runs:
                cost = per_run.get(step_runs[-1])
            total_cost = sum(per_run.values())
        except Exception as exc:
            print("  (花费统计失败: %s)" % exc)

        print("  状态     : %s" % status)
        print("  耗时     : %.1fs" % dt)
        print("  内容累计花费: %s" % (("$%.4f" % total_cost) if total_cost else "n/a"))
        if step_view.get("error_message"):
            print("  错误     : %s" % str(step_view["error_message"])[:120])

        rec = {"skill": skill, "status": status, "duration_s": round(dt, 1),
               "cost_usd_cumulative": cost, "error": step_view.get("error_message") or ""}

        # 检查点：自动批准（模拟人工确认）
        if status == "waiting_checkpoint":
            cp = http("GET", f"/api/workflows/{wf_id}/checkpoints/current")
            print("  → 检查点暂停（remaining_seconds=%s），自动批准"
                  % (cp or {}).get("remaining_seconds"))
            r = http("POST", f"/api/workflows/{wf_id}/checkpoints/resolve",
                     {"action": "approve",
                      "checkpoint_id": (cp or {}).get("checkpoint_id"),
                      "data": {"note": "pipeline 自动确认"}})
            rec["checkpoint_resolved"] = r.get("status")
            rec["status"] = "completed"

        records.append(rec)

        # 每步后列出工作区产物
        produced = sorted(
            p.relative_to(ws).as_posix()
            for p in ws.rglob("*") if p.is_file()
        )
        print("  工作区现有: %s" % (", ".join(produced[:8]) or "（空）"))
        print()

        if status == "failed":
            print("  !! 该步骤失败，继续下一步以便观察后续行为")
    else:
        pass

    # 收尾：工作流最终状态
    final = http("GET", f"/api/workflows/{wf_id}")
    done = [s for s in final["steps"] if s["status"] == "completed"]
    total_elapsed = time.monotonic() - started_all
    print("=" * 78)
    print("最终状态: %s  |  完成 %d/%d 步  |  累计花费 $%.4f  |  总耗时 %.1f 分钟"
          % (final["status"], len(done), len(steps), total_cost, total_elapsed / 60))
    print("=" * 78)

    # 成文链：导出论文
    export = None
    try:
        export = http("POST", "/api/paper/export", {
            "workspace": str(ws), "template": "comp_cumcm",
            "title": "基于线性规划的运输成本优化模型",
            "formats": ["latex", "docx"], "compile_pdf": True,
        }, 600)
    except Exception as exc:
        print("论文导出失败:", exc)
    lint = None
    try:
        lint = http("GET", "/api/paper/lint?workspace=" + urllib.parse.quote(str(ws))
                    + "&template=comp_cumcm")
    except Exception:
        pass

    write_report(wf_id, ws, records, final, total_cost, export, lint, interrupted,
                 total_elapsed)
    return 0


def write_report(wf_id, ws, records, final, total_cost, export, lint, interrupted,
                 total_elapsed=0.0) -> None:
    lines = [
        "# 完整 8 步国赛流水线 · 真实执行记录",
        "",
        "> 由 `run_full_pipeline.py` 生成。**真实调用 Claude Code**，"
        "检查点自动批准（模拟人工确认）。",
        "> 出于安全考虑，本报告不记录任何凭据信息。",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| 工作流 | `{wf_id}` |",
        f"| 模板 | `comp_cumcm`（国赛，8 步，启用检查点） |",
        f"| 工作区 | `{ws}` |",
        f"| **累计花费** | **${total_cost:.4f}** |",
        f"| **总耗时** | **{total_elapsed / 60:.1f} 分钟** |",
        f"| 最终状态 | **{final['status']}** |",
        f"| 完成步骤 | {len([s for s in final['steps'] if s['status'] == 'completed'])} / {len(final['steps'])} |",
        "",
    ]
    if interrupted:
        lines += [f"> ⚠️ 提前停止：{interrupted}", ""]

    lines += [
        "## 逐步结果",
        "",
        "| # | 步骤 | 状态 | 耗时(s) | 说明 |",
        "|---|---|---|---|---|",
    ]
    for i, r in enumerate(records, 1):
        note = r.get("error") or ("检查点已批准" if r.get("checkpoint_resolved") else "")
        lines.append("| %d | `%s` | **%s** | %s | %s |"
                     % (i, r["skill"], r["status"], r.get("duration_s", "-"),
                        str(note)[:80].replace("|", "\\|")))

    lines += [
        "",
        "## 工作区最终产物",
        "",
        "```",
    ]
    for p in sorted(ws.rglob("*")):
        if p.is_file():
            lines.append("%-46s %8d B" % (p.relative_to(ws).as_posix(), p.stat().st_size))
    lines += ["```", ""]

    if export:
        lines += ["## 成文链导出", "", "```json",
                  json.dumps(export, ensure_ascii=False, indent=1)[:2500], "```", ""]
    if lint:
        lines += [f"## 去 AI 味检查",
                  "",
                  f"- 通过：**{lint.get('ok')}**（errors {lint.get('error_count')} / "
                  f"warns {lint.get('warn_count')}）",
                  ""]
        for iss in (lint.get("issues") or [])[:20]:
            lines.append(f"- [{iss['severity']}] `{iss['rule']}`: {iss['message'][:80]}")

    lines += [
        "",
        "## 步骤级事件（按 run_id 汇总）",
        "",
        "| 步骤 | 事件数 | 最后状态 |",
        "|---|---|---|",
    ]
    try:
        ev = http("GET", f"/api/workflows/{wf_id}/run-events?limit=2000")
        by_run: dict[str, list] = {}
        for e in ev["events"]:
            by_run.setdefault(e["run_id"], []).append(e)
        for rid, evs in by_run.items():
            lines.append("| `%s…` | %d | %s |"
                         % (rid[:10], len(evs), evs[-1]["state"]))
    except Exception:
        pass

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("报告已写入:", OUT)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget-per-step", type=float, default=5.0)
    ap.add_argument("--budget-total", type=float, default=0.0,
                    help="0 = 不限（按用户要求：预算不是约束，时间才是）")
    ap.add_argument("--time-limit-min", type=float, default=0.0,
                    help="0 = 不限；单位分钟，用于模拟比赛时间约束")
    ap.add_argument("--step-deadline-min", type=float, default=40.0,
                    help="单步等待上限（分钟）——超时**不中断**，只是续等提示")
    ap.add_argument("--resume", default="", help="续跑指定工作流 id")
    ap.add_argument("--workspace", default="", help="配合 --resume 指定工作区")
    a = ap.parse_args()
    raise SystemExit(run_pipeline(
        a.budget_per_step, a.budget_total,
        a.time_limit_min * 60 if a.time_limit_min else 0.0,
        resume_wf=a.resume, workspace=a.workspace,
        step_deadline_s=a.step_deadline_min * 60))
