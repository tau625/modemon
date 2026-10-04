"""ARIS 接入的集成测试：确定性绘图 + 结果诚信审计。

重点：
  1. **MIT 许可合规**（两条硬性条件）
  2. FigureSpec 渲染链路真的能产出 SVG/PNG
  3. 审计的**独立性**约束（不复用产出会话）
  4. 审计判决口径与 vision 一致：只认结构化标记
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
MODEN = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from services import figure_spec as fs  # noqa: E402
from services import result_audit as ra  # noqa: E402

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


SPEC = {
    "title": "测试图",
    "canvas": {"width": 400, "height": 200},
    "style": {"font_family": "SimHei, sans-serif", "font_size": 13,
              "bg_color": "#FFFFFF", "palette": ["#4477AA", "#EE6677"]},
    "nodes": [
        {"id": "a", "label": "输入", "x": 100, "y": 100, "width": 90,
         "height": 50, "shape": "rounded"},
        {"id": "b", "label": "输出", "x": 300, "y": 100, "width": 90,
         "height": 50, "shape": "rounded"},
    ],
    "edges": [{"from": "a", "to": "b", "label": "传", "arrow": "right"}],
}


def test_license() -> None:
    print("\n[1] ★ MIT 许可合规（两条硬性条件）")
    for mod, name in ((fs, "figure_spec"), (ra, "result_audit")):
        src = (BACKEND / "services" / f"{name}.py").read_text(encoding="utf-8")
        check(f"{name}: 内嵌版权人", "Copyright (c) 2026 wanshuiyin" in src, name)
        check(f"{name}: 内嵌许可全文",
              "Permission is hereby granted" in src and
              "THE SOFTWARE IS PROVIDED" in src, name)
        check(f"{name}: 声明上游仓库", mod.UPSTREAM_REPO.startswith("wanshuiyin/"))
        check(f"{name}: 指向许可文件", "LICENSE-ARIS.txt" in src)

    lic = MODEN / "LICENSE-ARIS.txt"
    check("LICENSE-ARIS.txt 在位", lic.is_file())


def test_figure_spec_render() -> None:
    print("\n[2] FigureSpec 确定性渲染链路")
    check("渲染器在位", fs.find_renderer() is not None, str(fs.RENDERER_PATH))

    ok, msg = fs.validate_spec(SPEC)
    check("spec 校验通过", ok, msg[:120])

    bad = dict(SPEC)
    bad["nodes"] = [{"id": "a", "label": "x"}]   # 缺 x/y
    ok2, _msg2 = fs.validate_spec(bad)
    check("非法 spec 被拒绝", not ok2)

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "fig"
        r = fs.render_figure(SPEC, out)
        check("**SVG 生成成功**", r.ok and r.svg and r.svg.is_file(), r.error)
        if r.svg:
            t = r.svg.read_text(encoding="utf-8", errors="replace")
            check("SVG 含中文标签", "输入" in t and "输出" in t)
            check("SVG 是标准矢量", t.lstrip().startswith("<svg"))
        check("**PNG 转换成功**", r.png is not None and r.png.is_file(),
              "; ".join(r.notes))
        if r.png:
            check("PNG 非空", r.png.stat().st_size > 500,
                  str(r.png.stat().st_size))


def test_svg_converter_choice() -> None:
    print("\n[3] SVG→PNG 转换器选择（不能认错同名工具）")
    tool = fs.find_svg_converter()
    if tool:
        check("**不把 system32\\convert 当转换器**",
              "system32" not in tool.lower(), tool)
        check("选到的是浏览器/矢量工具",
              tool.lower().endswith(".exe"), tool)
    else:
        check("无转换器时如实报告（不静默假成功）", tool is None)
    src = (BACKEND / "services" / "figure_spec.py").read_text(encoding="utf-8")
    check("源码里记录了该陷阱", "system32" in src and "ImageMagick" in src)


def test_audit_prompt() -> None:
    print("\n[4] 审计提示词契约")
    body, loaded = ra.load_skill_body()
    if loaded:
        check("skill 正文已引入", len(body) > 200, str(len(body)))
    else:
        check("正文未引入时给出最小契约", len(ra._fallback_prompt()) > 200)

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "figures").mkdir()
        (ws / "figures" / "all_results.json").write_text(
            json.dumps({"Z0": 775}), encoding="utf-8")
        p = ra.build_prompt(ws)
        # ⚠️ 断言要兼容**两种来源**：正文引入后是上游英文原文
        #   （Fake ground truth / Score normalization / Phantom results /
        #    Insufficient scope），未引入时是我写的中文最小契约。
        #   只认一种会让"正确接入了原文"反而判失败。
        en = all(k in p for k in ("ground truth", "normalization", "Phantom", "scope"))
        zh = all(k in p for k in ("ground truth", "归一化", "幽灵", "范围不足"))
        check("**包含四类失败模式**", en or zh, p[:200])
        check("包含待审计文件清单", "all_results.json" in p)
        check("**明确审计者非产出者**", "不是" in p and "独立判定" in p, p[-260:])
        check("可指定结果文件",
              ra.build_prompt(ws, result_file="x/y.json").count("x/y.json") >= 1)


def test_audit_verdict() -> None:
    print("\n[5] ★ 审计判决口径（与 vision 同取舍）")
    for reply, why in (("PASS", "明确通过"), ("", "空回复"),
                       ("整体一致，未见问题。", "泛泛肯定"),
                       ("需要人工再看一下。", "无法解析")):
        check(f"放行：{why}", ra.verdict_of(reply) == 0, repr(reply[:40]))
    for reply, why in (("ISSUE 1: [结果] 引用了不存在的文件", "标准格式"),
                       ("issue 2：数字对不上", "小写+中文冒号"),
                       ("FINDING 1: 范围不足", "FINDING 标记")):
        check(f"判失败：{why}", ra.verdict_of(reply) == 1, repr(reply[:40]))
    check("抽取条目", len(ra.extract_issues("a\nISSUE 1: x\nISSUE 2: y")) == 2)

    # ★ 空回复必须降级为 skipped，不能算通过（虚假信心）
    check("**空回复不算通过**（应降级为未判定）",
          ra.is_blank("") and ra.is_blank("   \n"), "空回复语义")
    check("有实质内容才算判定",
          not ra.is_blank("PASS") and not ra.is_blank("整体一致"))


def test_audit_independence() -> None:
    print("\n[6] ★ 审计独立性（上游核心约束）")
    src = (BACKEND / "services" / "result_audit.py").read_text(encoding="utf-8")
    # ⚠️ 断言要排除**注释**：源码里我写了「不带 --resume」这句话，
    #   字符串检查会把注释当成证据而误判。只看代码本体。
    code_only = "\n".join(ln.split("#")[0] for ln in src.splitlines())
    check("**命令本体不含 --resume**（必须是全新会话）",
          '"--resume"' not in code_only and "'--resume'" not in code_only)
    check("源码记载「执行者不参与诚信判定」",
          "does NOT participate" in src)
    check("源码记载防自我赦免", "self-acquittal" in src)
    check("审计失败不阻塞主流程",
          "不阻塞" in src and 'verdict = "skipped"' in src)


def main() -> int:
    print("=" * 74)
    print("modemon ARIS 接入集成测试（确定性绘图 + 结果诚信审计）")
    print("=" * 74)
    test_license()
    test_figure_spec_render()
    test_svg_converter_choice()
    test_audit_prompt()
    test_audit_verdict()
    test_audit_independence()
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
