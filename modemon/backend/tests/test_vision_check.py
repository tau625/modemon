"""视觉自检回归测试。

重点是**判决口径**：vision 必须是「加分项」不是「硬门槛」。

蓝方原文 docstring 完整记载了失败模式：
旧逻辑「首行非纯 PASS 即 FAIL」+ 提示词里的主观项（大片空白 / 是否美观）
→ 几何图**必然**被挑出至少一条 → 每张烧满 2 轮重编 → 「画完卡很久」。

因此这里把该口径固化为断言：**只有结构化 `ISSUE n:` 才算失败**。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from services import vision_check as vc  # noqa: E402

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


def test_verdict_rule() -> None:
    print("\n[1] ★ 判决口径：只有 ISSUE n: 才算失败")

    # --- 必须放行（否则就退回"每张烧满 2 轮重编"的老路） ---
    must_pass = [
        ("PASS", "明确通过"),
        ("", "空回复"),
        ("  ", "空白回复"),
        ("整体还可以，布局大致合理。", "泛泛肯定"),
        ("有些地方可以更紧凑，但不影响理解。", "泛泛评论"),
        ("图 1：运输方案。颜色区分尚可。", "客观描述"),
        ("无法判断，建议人工复核。", "无法解析"),
        ("整体是否美观、专业？", "复述问题而非作答"),
        ("solutions look fine; no blockers.", "英文泛泛评论"),
    ]
    for reply, why in must_pass:
        check("放行：%s" % why, vc.verdict(reply) == 0,
              "verdict=%d reply=%r" % (vc.verdict(reply), reply[:60]))

    # --- 必须判失败 ---
    must_fail = [
        ("ISSUE 1: [左上] 文字被截断", "标准格式"),
        ("ISSUE 2: [中央] 节点重叠", "带序号"),
        ("issue 1: [左上] 文字被截断", "小写也能识别"),
        ("ISSUE: [左上] 文字被截断", "无序号"),
        ("ISSUE1: 文字被截断", "冒号前无空格"),
        ("  issue  3 ： 节点挤在一起", "中文冒号"),
        ("说明：\nISSUE 1: A\nISSUE 2: B", "多条中识别"),
    ]
    for reply, why in must_fail:
        check("判失败：%s" % why, vc.verdict(reply) == 1,
              "verdict=%d reply=%r" % (vc.verdict(reply), reply[:60]))

    # --- 边界：不该误判 ---
    edge = [
        ("ISSUEFAIL", "非标记词"),
        ("这是 issue 说明，但不是结构化条目", "正文提到 issue"),
        ("ISSUE 标记的格式是 ISSUE n:", "讲解格式本身"),
    ]
    for reply, why in edge:
        check("不误判：%s" % why, vc.verdict(reply) == 0,
              "verdict=%d reply=%r" % (vc.verdict(reply), reply[:60]))


def test_extract_issues() -> None:
    print("\n[2] ISSUE 条目抽取")
    txt = "前置说明\nISSUE 1: [左上] 文字被截断\n普通行\nissue 2 ： 节点重叠\n"
    got = vc.extract_issues(txt)
    check("抽取到 2 条", len(got) == 2, str(got))
    check("条目内容正确", "文字被截断" in got[0] and "节点重叠" in got[1], str(got))
    check("空回复不抽", vc.extract_issues("") == [])


def test_prompt_contract() -> None:
    print("\n[3] 提示词契约（7 项 + ISSUE 格式）")
    p = vc.build_prompt(vc.TIKZ_CHECK_ITEMS, subject="这张 TikZ 图")
    check("含全部 7 项检查", all(it in p for it in vc.TIKZ_CHECK_ITEMS),
          "缺失项=%s" % [i for i in vc.TIKZ_CHECK_ITEMS if i not in p][:2])
    check("含 PASS 指令", "PASS" in p)
    check("含 ISSUE 格式说明", "ISSUE 1:" in p, p[-160:])
    check("TikZ 检查恰为 7 项（对齐原文）", len(vc.TIKZ_CHECK_ITEMS) == 7,
          str(len(vc.TIKZ_CHECK_ITEMS)))
    check("数据图检查含中文方框检测", "方框" in vc.DATA_FIG_CHECK_ITEMS[0])
    check("论文页检查含方框检测", any("方框" in x for x in vc.PAGE_CHECK_ITEMS))


def test_image_size_defense() -> None:
    print("\n[4] 图片体积防御（超限压缩，读不出则跳过）")
    check("阈值 3.5MB（对齐原文）", vc._MAX_IMG_BYTES == 3_500_000,
          str(vc._MAX_IMG_BYTES))
    check("不存在的文件返回 None（调用方跳过）",
          vc.load_image(Path("no_such_file.png")) is None)

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "big.png"
        try:
            from PIL import Image
            import numpy as np
            a = (np.random.rand(2000, 2000, 3) * 255).astype("uint8")
            Image.fromarray(a).save(str(p))
        except Exception:
            print("      (PIL/numpy 不可用，跳过压缩用例)")
            return
        if p.stat().st_size <= vc._MAX_IMG_BYTES:
            print("      (生成的图未超过阈值，跳过压缩用例)")
            return
        got = vc.load_image(p)
        check("超限图仍能读取（压缩或回退）", got is not None)
        if got:
            check("返回 (base64, mime) 二元组", len(got) == 2 and got[1].startswith("image/"),
                  str(type(got)))


def test_result_contract() -> None:
    print("\n[5] 结果对象与退出码契约")
    r = vc.VisionResult()
    check("默认 skipped 不阻塞", r.verdict == "skipped" and r.ok is True)
    d = r.as_dict()
    check("as_dict 可序列化", isinstance(d, dict) and "verdict" in d)
    check("raw_reply 有截断上限", len(d["raw_reply"]) <= 500)

    # 退出码：0=PASS 1=有问题 2=API 不可用（对齐原文 docstring）
    import inspect
    src = inspect.getsource(vc.main)
    check("CLI 契约含 0/1/2 三种退出码", "return 2" in src and "return 1" in src,
          "缺退出码")


def main() -> int:
    print("=" * 74)
    print("modemon 排版视觉自检测试（★ 判决口径：ISSUE n: 才算失败）")
    print("=" * 74)
    test_verdict_rule()
    test_extract_issues()
    test_prompt_contract()
    test_image_size_defense()
    test_result_contract()
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
