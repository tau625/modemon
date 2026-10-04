#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""续跑流水线：跳过已完成步骤，从断点接着走（绕过 --resume 的入参要求）。

直接调用 run_full_pipeline.run_pipeline，并先清掉前序已 completed 的步骤
标记为可跳过——通过 workflow API 查状态后逐个启动未完成的步骤。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

B = "http://127.0.0.1:8770"
WF_ID = "27dc89fb63e14347a949c13e9adca36f"
WS = r"C:\Users\SAKE\AppData\Local\Temp\modemon-full-_kmji5xj\ws"

STEP_HINTS = {
    "comp-code": "用 Python 求解，**必须**把原料结果写入 `figures/all_results.json`"
                 "（含最优目标值、各变量取值、情景对比、迭代次数与耗时）。"
                 "论文中任何数值都必须来自该文件。",
    "paper-figure": "画图时**必须先配置中文字体**，否则中文变方框："
                    "matplotlib.rcParams['font.sans-serif']=['SimHei'];"
                    "matplotlib.rcParams['axes.unicode_minus']=False。"
                    "图片命名 `fig_<英文名>.png`，并在 FIGURE_MANIFEST.md 登记。",
    "paper-figure-drawio": "**不要写 TikZ 或 LaTeX 图形代码**——写**声明式 FigureSpec JSON**："
                           "`figures/architecture.spec.json`，由引擎确定性渲染成 SVG/PNG。"
                           "`title` 会作为图注，必须写完整中文描述。",
    "comp-review": "对抗式复核建模与求解，指出最可能被质疑的点，写入 COMP_REVIEW.md。",
    "comp-paper-zh": "撰写完整论文，写入 `paper/main.tex`（XeLaTeX + ctex 可编译）。"
                     "所有数值必须与 `figures/all_results.json` 一致；"
                     "表格用 booktabs 三线表。**不要在加粗标签内写冒号**。",
    "comp-compile-zh": "用 xelatex 编译 `paper/main.tex` 生成 `paper/main.pdf`（编译两遍）。",
}


def http(method, path, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(B + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def main() -> int:
    print("=" * 76)
    print("续跑流水线 %s（跳过已完成步骤）" % WF_ID[:12])
    print("=" * 76)

    wf = http("GET", f"/api/workflows/{WF_ID}")
    steps = wf["steps"]
    print("工作区:", WS)
    print("总时间预算: 120 分钟（本次不设单步上限中断）")
    print()

    for i, s in enumerate(steps, 1):
        mark = {"completed": "[x]", "running": "[>]", "pending": "[ ]",
                "failed": "[!]", "waiting_checkpoint": "[P]"}.get(s["status"], "[?]")
        print("  %s %d. %-24s %s" % (mark, i, s["skill_name"], s["status"]))
    print()

    started_all = time.monotonic()
    TIME_LIMIT = 120 * 60

    for i, s in enumerate(steps, 1):
        skill = s["skill_name"]
        if s["status"] == "completed":
            print("跳过已完成: %s" % skill)
            continue

        if time.monotonic() - started_all >= TIME_LIMIT:
            print("!! 总时间预算耗尽")
            break

        print("-" * 76)
        print("步骤 %d/8: %s   （已用 %.1f 分钟）" % (i, skill,
                                                  (time.monotonic() - started_all) / 60))
        print("-" * 76)

        q = urllib.parse.urlencode({
            "workspace": WS, "max_budget_usd": 5.0,
            "extra_prompt": STEP_HINTS.get(skill, ""),
            "permission_mode": "bypassPermissions",
        })
        t0 = time.monotonic()
        try:
            http("POST", f"/api/workflows/{WF_ID}/steps/{skill}/run?{q}", None, 60)
            print("  已启动")
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                print("  已有任务在跑（409），等待其结束…")
            else:
                print("  启动失败:", exc)
                continue

        # 轮询：超时不中断，续等
        status = "running"
        deadline = time.monotonic() + 40 * 60
        last_note = 0.0
        while True:
            if time.monotonic() - started_all >= TIME_LIMIT:
                print("  !! 总时间预算耗尽")
                break
            w = http("GET", f"/api/workflows/{WF_ID}")
            sv = next((x for x in w["steps"] if x["skill_name"] == skill), {})
            status = sv.get("status", "?")
            if status != "running":
                break
            if time.monotonic() > deadline:
                print("  …单步已达 40 分钟，仍在执行——继续等")
                deadline = time.monotonic() + 40 * 60
            if time.monotonic() - last_note > 120:
                print("    …仍在执行（%.1f 分钟）" % ((time.monotonic() - t0) / 60))
                last_note = time.monotonic()
            time.sleep(5)

        dt = time.monotonic() - t0
        print("  状态: %s   耗时: %.1fs" % (status, dt))
        if sv.get("error_message"):
            print("  错误: %s" % sv["error_message"][:120])

        # 检查点自动批准
        if status == "waiting_checkpoint":
            cp = http("GET", f"/api/workflows/{WF_ID}/checkpoints/current")
            print("  → 检查点暂停，自动批准")
            try:
                http("POST", f"/api/workflows/{WF_ID}/checkpoints/resolve",
                     {"action": "approve", "checkpoint_id": (cp or {}).get("checkpoint_id"),
                      "data": {"note": "续跑自动确认"}})
            except Exception as exc:
                print("  批准失败:", exc)

        if status == "failed":
            print("  !! 失败，继续下一步观察")

    final = http("GET", f"/api/workflows/{WF_ID}")
    done = [x for x in final["steps"] if x["status"] == "completed"]
    print()
    print("=" * 76)
    print("最终状态: %s | 完成 %d/8 | 总耗时 %.1f 分钟"
          % (final["status"], len(done), (time.monotonic() - started_all) / 60))
    print("=" * 76)
    for i, s in enumerate(final["steps"], 1):
        mark = {"completed": "[x]", "running": "[>]", "pending": "[ ]",
                "failed": "[!]", "waiting_checkpoint": "[P]"}.get(s["status"], "[?]")
        print("  %s %d. %-24s %s" % (mark, i, s["skill_name"], s["status"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
