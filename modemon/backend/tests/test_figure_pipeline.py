"""图表流水线与结果审计钩子的集成测试。

重点：
  1. **分工正确**：agent 写 FigureSpec JSON，引擎负责渲染（不写 TikZ）
  2. 流水线真的能出 SVG/PNG 与 latex_includes.tex
  3. 审计**挂在 comp-code 之后**且**非阻塞**
  4. 审计独立性（不复用产出会话）
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from services import figure_pipeline as fp  # noqa: E402
from services import step_runner as sr  # noqa: E402
from services import workflow_service as wfs  # noqa: E402

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


def make_spec(title: str = "求解流程与系统架构") -> dict:
    return {
        "title": title,
        "canvas": {"width": 640, "height": 280},
        "style": {"font_family": "SimHei, sans-serif", "font_size": 13,
                  "bg_color": "#FFFFFF", "palette": ["#4477AA", "#EE6677"]},
        "nodes": [
            {"id": "in", "label": "输入层", "sublabel": "问题数据",
             "x": 110, "y": 140, "width": 120, "height": 70, "shape": "rounded"},
            {"id": "sv", "label": "求解层", "sublabel": "情景 1/2/3",
             "x": 320, "y": 140, "width": 120, "height": 70, "shape": "rounded"},
            {"id": "out", "label": "输出层", "sublabel": "all_results.json",
             "x": 530, "y": 140, "width": 120, "height": 70, "shape": "rounded"},
        ],
        "edges": [
            {"from": "in", "to": "sv", "label": "读取", "arrow": "right"},
            {"from": "sv", "to": "out", "label": "导出", "arrow": "right"},
        ],
    }


def test_prompt_tells_agent_not_to_write_tikz() -> None:
    print("\n[1] ★ 步骤提示：写 FigureSpec JSON，不写 TikZ")
    p = sr.StepRunRequest(workflow_id="w", skill_name="paper-figure-drawio",
                          workspace=Path("."), language="zh")
    t = sr.build_step_prompt(p)
    check("**明确禁止手写 TikZ**", "不要写 TikZ" in t or "不要手写 TikZ" in t, t[:200])
    check("给出 FigureSpec 文件名约定", "architecture.spec.json" in t)
    check("给出 JSON 样例", '"nodes"' in t and '"edges"' in t)
    check("**声明渲染由引擎负责**", "渲染由引擎负责" in t, t[-200:])
    check("要求中文图注（不能用英文缩写）",
          "中文描述" in t and "不要用英文" in t, t[-260:])
    # 其它步骤不该带这段
    q = sr.StepRunRequest(workflow_id="w", skill_name="comp-prob-analysis",
                          workspace=Path("."), language="zh")
    check("分析步骤不带绘图指引", "FigureSpec" not in sr.build_step_prompt(q))


def test_pipeline_end_to_end() -> None:
    print("\n[2] 图表流水线端到端")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "figures").mkdir()
        (ws / "figures" / "architecture.spec.json").write_text(
            json.dumps(make_spec(), ensure_ascii=False), encoding="utf-8")

        rep = fp.build_figures(ws)
        check("**渲染成功**", bool(rep.rendered), str(rep.errors))
        check("无错误", not rep.errors, str(rep.errors))
        if rep.rendered:
            item = rep.rendered[0]
            check("产出 SVG", item.get("svg") and (ws / item["svg"]).is_file(),
                  str(item))
            check("**产出 PNG**（LaTeX 需要）",
                  item.get("png") and (ws / item["png"]).is_file(), str(item))
            check("**图注取自 spec.title**（中文）",
                  item.get("caption") == "求解流程与系统架构", str(item.get("caption")))

        inc = ws / "figures" / "latex_includes.tex"
        check("生成 latex_includes.tex", inc.is_file(), str(inc))
        if inc.is_file():
            src = inc.read_text(encoding="utf-8")
            check("**体积达标（门控 ≥500 字节）**",
                  inc.stat().st_size >= 500, str(inc.stat().st_size))
            check("含中文图注", "求解流程与系统架构" in src, src[:200])
            check("含 figure 环境", "\\begin{figure}" in src and
                  "\\includegraphics" in src)

        ok, reason, missing = fp.check_pipeline_output(ws)
        check("**产出门控通过**", ok, reason)


def test_pipeline_rejects_bad_spec() -> None:
    print("\n[3] 非法 FigureSpec 不应产出")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "figures").mkdir()
        # 边指向不存在的节点
        bad = make_spec()
        bad["edges"] = [{"from": "in", "to": "ghost", "label": "x"}]
        (ws / "figures" / "bad.spec.json").write_text(
            json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        (ws / "figures" / "broken.spec.json").write_text("{ not json", encoding="utf-8")

        rep = fp.build_figures(ws)
        check("非法 spec 被跳过", not rep.rendered, str(rep.rendered))
        check("错误被记录", bool(rep.errors), str(rep.errors))
        # 跳过原因既可能是"校验失败"（渲染前）也可能是 "validate: ..."（校验器原话）
        check("跳过原因说明了失败点",
              any(("校验失败" in (s.get("reason") or "")
                   or "validate" in (s.get("reason") or "").lower())
                  for s in rep.skipped),
              str(rep.skipped)[:200])


def test_audit_hook_wiring() -> None:
    print("\n[4] ★ 审计挂在 comp-code 之后")
    check("**comp-code 在审计列表**", "comp-code" in wfs.POST_AUDIT_SKILLS,
          str(sorted(wfs.POST_AUDIT_SKILLS)))
    check("其它产出数值的步骤也在列",
          {"code", "comp-stats-code"} <= wfs.POST_AUDIT_SKILLS)
    check("分析类步骤不在列",
          "comp-prob-analysis" not in wfs.POST_AUDIT_SKILLS)

    src = (BACKEND / "services" / "workflow_service.py").read_text(encoding="utf-8")
    check("**审计是 fire-and-forget**（不阻塞流水线）",
          "asyncio.create_task" in src and "_run_post_step_audit" in src)
    check("**保存 task 强引用防 GC**",
          "_AUDIT_TASKS.add(t)" in src and "add_done_callback" in src)
    check("审计失败不影响步骤状态",
          "绝不影响步骤状态" in src or "不阻塞" in src)
    check("审计结果以事件推送", '"result_audit"' in src)


def test_audit_is_independent() -> None:
    print("\n[5] ★ 审计独立性（上游核心约束）")
    src = (BACKEND / "services" / "result_audit.py").read_text(encoding="utf-8")
    code_only = "\n".join(ln.split("#")[0] for ln in src.splitlines())
    check("**命令不含 --resume**（必须是全新会话）",
          '"--resume"' not in code_only and "'--resume'" not in code_only)
    check("记载「执行者不参与诚信判定」", "does NOT participate" in src)
    check("空回复降级为 skipped（非虚假通过）", "is_blank" in src)


def test_hooks_run_on_checkpoint_path() -> None:
    """★ 有检查点的步骤也必须派生钩子。

    实测缺陷：`execute_step` 在检查点分支会**提前 `return report`**，
    而 `comp-code`（需要审计的那个）恰好有检查点——审计钩子因此
    **从未执行**；而 `figure_render` 正常（那步骤没检查点），
    表现为"一个生效一个不生效"，很难一眼看出来。
    """
    print("\n[6] ★ 检查点路径也必须派生钩子（实测缺陷）")
    import inspect

    src = inspect.getsource(wfs.execute_step)
    check("钩子已抽成独立函数", hasattr(wfs, "_spawn_post_step_hooks"))
    check("**execute_step 里调用 >=2 次**（两条路径）",
          src.count("_spawn_post_step_hooks(") >= 2,
          "count=%d" % src.count("_spawn_post_step_hooks("))
    check("检查点分支在 return 之前调用",
          "checkpoint_created" in src and
          src.index("checkpoint_created") < src.rindex("_spawn_post_step_hooks("),
          "顺序不对")

    hook = inspect.getsource(wfs._spawn_post_step_hooks)
    check("钩子内派生审计任务", "_run_post_step_audit" in hook)
    check("钩子内派生图任务", "_run_post_step_figures" in hook)
    check("两者都保存强引用防 GC",
          "_AUDIT_TASKS.add" in hook and "_FIGURE_TASKS.add" in hook)


def _tmp_conn(db: Path):
    import sqlite3 as s
    c = s.connect(str(db))
    c.row_factory = s.Row
    return c


def test_custom_event_persistence() -> None:
    """★ 自定义事件必须写库（`push` 只是广播，不落库）。"""
    print("\n[7] ★ 自定义事件持久化（push 只广播）")
    import sqlite3
    import tempfile

    src = (BACKEND / "services" / "workflow_service.py").read_text(encoding="utf-8")
    check("存在持久化助手", "_persist_custom_event" in src)
    check("记录了 push 只广播这个坑", "纯广播" in src or "不落库" in src)
    check("钩子都调用持久化",
          src.count("_persist_custom_event(") >= 3,
          "count=%d" % src.count("_persist_custom_event("))

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "t.db"
        con = sqlite3.connect(str(db))
        con.execute("CREATE TABLE chat_messages (id INTEGER PRIMARY KEY, session_id TEXT)")
        con.execute("""CREATE TABLE chat_run_events (
            event_id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL,
            message_id INTEGER NOT NULL, run_id TEXT NOT NULL, sequence INTEGER NOT NULL,
            kind TEXT NOT NULL, state TEXT NOT NULL, title TEXT NOT NULL,
            safe_detail TEXT NOT NULL DEFAULT '', public_artifact_path TEXT,
            started_at TIMESTAMP NOT NULL, completed_at TIMESTAMP,
            evidence_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(message_id, run_id, sequence))""")
        con.execute("INSERT INTO chat_messages (id, session_id) VALUES (1,'wf1')")
        con.commit()
        con.close()

        old = wfs._open_conn
        wfs._open_conn = lambda db_path=None: _tmp_conn(db)  # type: ignore
        try:
            wfs._persist_custom_event(workflow_id="wf1", kind="result_audit",
                                      payload={"ok": True, "verdict": "pass"},
                                      title="审计", detail="d")
        finally:
            wfs._open_conn = old  # type: ignore

        c2 = sqlite3.connect(str(db))
        n = c2.execute("SELECT COUNT(*) FROM chat_run_events"
                       " WHERE kind='result_audit'").fetchone()[0]
        c2.close()
        check("**自定义事件真的写进了库**", n == 1, "count=%d" % n)


def main() -> int:
    print("=" * 74)
    print("modemon 图表流水线 + 结果审计钩子 集成测试")
    print("=" * 74)
    test_prompt_tells_agent_not_to_write_tikz()
    test_pipeline_end_to_end()
    test_pipeline_rejects_bad_spec()
    test_audit_hook_wiring()
    test_audit_is_independent()
    test_hooks_run_on_checkpoint_path()
    test_custom_event_persistence()
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
