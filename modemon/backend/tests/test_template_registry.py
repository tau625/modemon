"""模板注册表 + 编排回退 回归测试。

对照基线：
- `reports/04-methodology.md` §3.2 的 **22 行竞赛模板表**（value/label/赛期/lang/pages/stars）
- `pyc_dump/backend__models__schemas.dis.txt` 里恢复的原始 `TemplateType` 枚举成员
- `reports/17-comp-pipeline-blueprint.md` 的 8 步契约与超时真值

原则：**只断言能从证据推出来的东西**。学术/ip 族的步骤名是自研命名，
因此这里只断言「结构自洽 + 可解析 + 分组/页数正确」，不假装它们是恢复真值。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import template_registry as reg  # noqa: E402
from services import workflow_engine as we  # noqa: E402

# ---------------------------------------------------------------------------
# 对照基线：reports/04-methodology.md §3.2（逐行照录，勿改动）
# 键 = value，值 = (label, 赛期, lang, pages, stars)
# ---------------------------------------------------------------------------

TRUTH_COMP = {
    "comp_tianfu": ("天府杯", "3月", "zh", 30, 4),
    "comp_certcup": ("认证杯", "4-5月", "zh", 35, 3),
    "comp_mathorcup": ("MathorCup", "4月", "zh", 30, 4),
    "comp_teddy": ("泰迪杯", "4月", "zh", 40, 3),
    "comp_huadong": ("华东杯", "4-5月", "zh", 30, 2),
    "comp_huazhong": ("华中杯", "4-5月", "zh", 30, 2),
    "comp_wuyi": ("五一杯", "5月", "zh", 30, 3),
    "comp_zhongqing": ("中青杯", "5月", "zh", 30, 3),
    "comp_yangtze": ("长三角", "5月", "zh", 30, 2),
    "comp_stats": ("统计建模大赛", "5月", "zh", 30, 3),
    "comp_shuwei": ("数维杯", "5月", "zh", 30, 3),
    "comp_diangong": ("电工杯", "5-6月", "zh", 30, 4),
    "comp_liaoning": ("辽宁省/东三省", "6月", "zh", 30, 2),
    "comp_apmcm_zh": ("亚太赛中文 (APMCM)", "6月", "zh", 25, 3),
    "comp_shenzhen": ("深圳杯", "7-9月", "zh", 30, 4),
    "comp_huashu": ("华数杯", "8月", "zh", 30, 3),
    "comp_cumcm": ("国赛 (CUMCM)", "9月", "zh", 30, 5),
    "comp_huawei": ("华为杯", "9月", "zh", 50, 5),
    "comp_mcm": ("美赛 (MCM/ICM)", "2月", "en", 25, 5),
    "comp_shuwei_en": ("数维杯国际赛", "11月", "en", 25, 3),
    "comp_apmcm": ("亚太 (APMCM)", "11月", "en", 25, 3),
    "comp_certcup_en": ("小美赛 (认证杯国际)", "12月", "en", 25, 3),
}

#: 前端产品面（§3.7 / §3.8 / §3.4）
TRUTH_ACADEMIC = ("paper_writing", "thesis_proposal", "literature_review", "course_paper", "course_report")
TRUTH_IP = ("copyright_material", "patent_disclosure")

#: 原始 `TemplateType` 枚举里出现、但不在前端产品面上的成员（schemas.dis.txt）
TRUTH_EXTRA = ("comp_zh", "comp_en", "full_pipeline", "humanities_paper", "grad_project")

#: 蓝方恢复真值：`inactivity_timeout`（静默上限）
TRUTH_TIMEOUT = {
    "comp-prob-analysis": 5400, "comp-modeling": 5400, "comp-code": 5400,
    "paper-figure": 5400, "paper-figure-drawio": 5400, "comp-review": 5400,
    "comp-paper-zh": 2700, "comp-paper-en": 2700,
    "comp-compile-zh": 2700, "comp-compile-en": 2700,
}

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  %s" % name)
    else:
        FAIL += 1
        print("  FAIL  %s  %s" % (name, detail))


# ---------------------------------------------------------------------------


def test_registry_data() -> None:
    print("\n[1] 注册表数据完整性（§3.2 / §3.7 / §3.8）")
    problems = reg.validate_registry()
    check("注册表自检无问题", not problems, "; ".join(problems))
    check("产品面模板 = 30", len(reg.TEMPLATES) == 30, "got %d" % len(reg.TEMPLATES))
    check("竞赛模板 = 22", len(reg.specs(reg.GROUP_COMPETITION)) == 22)
    check("学术模板 = 5", len(reg.specs(reg.GROUP_ACADEMIC)) == 5)
    check("资产模板 = 1", len(reg.specs(reg.GROUP_FROM_ASSETS)) == 1)
    check("ip 模板 = 2", len(reg.specs(reg.GROUP_IP)) == 2)
    check("兼容值 = 5", len(reg.EXTRA_TEMPLATES) == 5, "got %d" % len(reg.EXTRA_TEMPLATES))
    check("全部可解析值 = 35", len(reg.values()) == 35, "got %d" % len(reg.values()))

    # 每一行与 §3.2 表格逐字段比对
    for value, (label, month, lang, pages, stars) in TRUTH_COMP.items():
        spec = reg.get(value)
        if spec is None:
            check("%s 在注册表里" % value, False, "缺失")
            continue
        got = (spec.label, spec.month, spec.lang, spec.pages, spec.stars)
        check("%-18s = %s" % (value, label), got == (label, month, lang, pages, stars),
              "got %s want %s" % (got, (label, month, lang, pages, stars)))

    # 与恢复出来的原始枚举交叉印证
    for value in TRUTH_EXTRA:
        check("兼容值 %s 可解析且不降级" % value,
              we.resolve_template(value).degraded is False, value)

    # 组内无重复、组外无遗漏
    check("22 个竞赛 value 与表格键集合一致",
          set(reg.values(reg.GROUP_COMPETITION)) == set(TRUTH_COMP))
    for value in TRUTH_ACADEMIC:
        check("学术模板 %s 存在" % value, reg.get(value) is not None)
    for value in TRUTH_IP:
        check("ip 模板 %s 存在" % value, reg.get(value) is not None)
    check("comp_zh / comp_en 为兼容值（非产品面）",
          reg.get("comp_zh").group == reg.GROUP_GENERIC
          and reg.get("comp_en").group == reg.GROUP_GENERIC)


def test_all_values_resolve() -> None:
    print("\n[2] 35 个 value 全部可解析（绝不抛异常）")
    for value in reg.values():
        try:
            tmpl = we.resolve_template(value)
            ok = True
            detail = ""
        except Exception as exc:  # noqa: BLE001 - 任何异常都算失败
            tmpl, ok, detail = None, False, "%s: %s" % (type(exc).__name__, exc)
        check("resolve_template(%s) 不抛异常" % value, ok, detail)
        if tmpl is None:
            continue
        check("  %s 未降级" % value, tmpl.degraded is False, tmpl.degraded_reason)
        check("  %s 步骤数 > 0" % value, len(tmpl.sub_steps) > 0)

    # 竞赛模板：页数 / 星级 / lang 与 §3.2 一致，且由 lang 决定论文步技能
    for value, (_, _, lang, pages, stars) in TRUTH_COMP.items():
        tmpl = we.resolve_template(value)
        check("%s 页数 = %s" % (value, pages), tmpl.pages == pages, "got %s" % tmpl.pages)
        check("%s 星级 = %s" % (value, stars), tmpl.stars == stars, "got %s" % tmpl.stars)
        check("%s lang = %s" % (value, lang), tmpl.lang == lang, "got %s" % tmpl.lang)
        limit, mode = we.resolve_page_rule(value)
        check("%s 页数规则 (advisory_max)" % value, limit == pages and mode == "advisory_max")
        if lang == "en":
            check("%s 走英文论文步" % value, tmpl.sub_steps[6].skill_name == "comp-paper-en")
            check("%s 走英文编译步" % value, tmpl.sub_steps[7].skill_name == "comp-compile-en")
        else:
            check("%s 走中文论文步" % value,
                  tmpl.sub_steps[-2].skill_name in ("comp-paper-zh", "comp-paper-huawei"),
                  tmpl.sub_steps[-2].skill_name)


def test_degrade_is_graceful() -> None:
    print("\n[3] 未知 value 优雅降级（不抛异常 + 记 degraded）")
    zh_names = we.comp_zh_steps()
    for bad in ("not_a_template", "comp_tianfu_typo", "COMP_MCMX", "  ", ""):
        tmpl = we.resolve_template(bad)
        check("未知 %r 不抛异常" % bad, True)
        check("未知 %r 标记降级" % bad, tmpl.degraded is True, tmpl.degraded_reason)
        check("未知 %r 回退通用中文序列" % bad, tmpl.skill_names == tuple(s.skill_name for s in zh_names))
        check("未知 %r 有降级原因" % bad, bool(tmpl.degraded_reason))

    # 非字符串输入：旧实现会在这里 AttributeError / TypeError
    for weird in (None, 42, 3.14, True, object()):
        try:
            tmpl = we.resolve_template(weird)  # type: ignore[arg-type]
            check("非字符串输入 %r 不抛异常且降级" % (weird,), tmpl.degraded is True)
        except Exception as exc:  # noqa: BLE001
            check("非字符串输入 %r 不抛异常" % (weird,), False, "%s: %s" % (type(exc).__name__, exc))

    # 枚举输入（TemplateType）与大小写/空白容错
    check("枚举输入解析为对应 value",
          we.resolve_template(we.TemplateType.COMP_CUMCM).template_value == "comp_cumcm")
    check("大写/空白输入也能解析",
          we.resolve_template("  COMP_CUMCM  ").template_value == "comp_cumcm")
    check("未知模板页数返回 None 且模式仍为 advisory_max",
          we.resolve_page_rule("not_a_template") == (None, "advisory_max"))
    check("未知模板 min_size 走默认值", we.min_size_for("whatever-new-skill") == we.DEFAULT_MIN_SIZE)


def test_comp_stats_sequence() -> None:
    print("\n[4] comp_stats = 唯一编排例外（5 步，首步选题规划）")
    steps = we.comp_stats_steps()
    check("comp_stats_steps 返回 5 步", len(steps) == 5, "got %d" % len(steps))
    check("首步 = 选题规划", steps[0].skill_name == "comp-topic-plan" and steps[0].display_name == "选题规划")
    check("首步带检查点（选题需人工确认）",
          steps[0].has_checkpoint is True and steps[0].checkpoint_type == "approve")
    check("第 2 步 = 数据采集与分析", steps[1].display_name == "数据采集与分析", steps[1].display_name)
    check("第 3/4/5 步 = 图表/论文/编译",
          tuple(s.skill_name for s in steps[2:]) == ("paper-figure", "comp-paper-zh", "comp-compile-zh"))
    check("五阶段与 §3.2 描述一致（无独立「建模求解」步）",
          all(s.skill_name != "comp-modeling" for s in steps))

    tmpl = we.resolve_template("comp_stats")
    check("resolve_template(comp_stats) 也是 5 步", len(tmpl.sub_steps) == 5)
    check("comp_stats 的 sequence = comp_stats", tmpl.sequence == reg.SEQ_COMP_STATS)
    check("comp_stats 页数 = 30", tmpl.pages == 30)

    # 数据步是可 select 的：默认名 + 已被下游审计识别的名字
    alt = we.comp_stats_steps(code_skill="comp-stats-code")
    check("数据步可 select 为 comp-stats-code", alt[1].skill_name == "comp-stats-code")
    check("两种取名的步骤数一致（select 不复制 DAG）", len(alt) == len(steps))
    check("两个候选名都在 STATS_CODE_SKILLS 里",
          set(we.STATS_CODE_SKILLS) == {"comp-data-analysis", "comp-stats-code"})
    check("非法 code_skill 回落到默认名",
          we.comp_stats_steps(code_skill="nope")[1].skill_name == we.STATS_CODE_SKILLS[0])
    for name in we.STATS_CODE_SKILLS:
        check("%s 有二级文件约束（与 comp-code 同契约）" % name,
              we.required_companions_for(name) == ("code/main.py", "figures/all_results.json"))
    check("comp-data-analysis 的 min_size 与 comp-code 同档",
          we.min_size_for("comp-data-analysis") == we.min_size_for("comp-code") == 1000)


def test_huawei_variant() -> None:
    print("\n[5] 华为杯：步骤级 select，不复制 DAG")
    hw = we.resolve_template("comp_huawei")
    zh = we.resolve_template("comp_cumcm")
    check("华为杯步骤数 = 中文通用序列长度（8）", len(hw.sub_steps) == len(zh.sub_steps) == 8)
    check("华为杯 sequence 仍是 comp_zh", hw.sequence == reg.SEQ_COMP_ZH)
    check("华为杯带 variant 标记", hw.variant == "huawei", str(hw.variant))
    check("华为杯页数 = 50（其余中文赛事多为 30）", hw.pages == 50)
    check("华为杯论文步 = comp-paper-huawei", hw.sub_steps[6].skill_name == "comp-paper-huawei")
    check("华为杯编译步沿用中文编译技能", hw.sub_steps[7].skill_name == "comp-compile-zh")

    # DAG 复用：只有 2 步不同（建模 + 论文），其余 6 步逐字段相同
    diff = [
        i for i, (a, b) in enumerate(zip(hw.sub_steps, zh.sub_steps)) if a != b
    ]
    check("与国赛仅 2 步不同（求解深度 + 论文）", diff == [1, 6], str(diff))
    check("前 6 步技能名保持不变",
          [s.skill_name for s in hw.sub_steps[:6]] == [s.skill_name for s in zh.sub_steps[:6]])
    check("建模步技能名不变，只带变体元数据",
          hw.sub_steps[1].skill_name == "comp-modeling"
          and hw.sub_steps[1].variant == "huawei"
          and hw.sub_steps[1].select_from == "comp-modeling")
    check("华为杯论文步绑签名模板包",
          hw.sub_steps[6].template_bundle == "comp-paper-zh/templates/huawei")
    check("模板包缺失时 fail-closed（不得静默降级为通用 ctexart）",
          hw.sub_steps[6].fail_closed is True)
    check("非华为杯步骤不带 huawei 标记",
          all(s.variant is None for s in zh.sub_steps))

    # 显式 huawei=True 覆盖：仍复用 zh 序列
    forced = we.resolve_template("comp_cumcm", huawei=True)
    check("huawei=True 复用同一序列且换论文技能",
          len(forced.sub_steps) == 8 and forced.sub_steps[6].skill_name == "comp-paper-huawei")
    check("未知模板 + huawei=True 仍不抛异常",
          we.resolve_template("nope", huawei=True).degraded is True)


def test_language_and_orchestration_split() -> None:
    print("\n[6] 双轨编排：22 个竞赛只由 3 套序列支撑")
    comp = reg.specs(reg.GROUP_COMPETITION)
    seqs = {s.sequence for s in comp}
    check("竞赛模板只用到 3 套编排", seqs == set(reg.COMPETITION_SEQUENCES), str(seqs))
    zh_count = sum(1 for s in comp if s.lang == "zh")
    en_count = sum(1 for s in comp if s.lang == "en")
    zh_seq = sum(1 for s in comp if s.sequence == reg.SEQ_COMP_ZH)
    check("18 个中文竞赛（含华为杯）", zh_count == 18, "got %d" % zh_count)
    check("4 个英文竞赛共用 comp_en", en_count == 4, "got %d" % en_count)
    check("17 个中文竞赛共用 comp_zh 序列（第 18 个是 comp_stats 例外）",
          zh_seq == 17, "got %d" % zh_seq)
    check("华为杯仍在 comp_zh 编排里（不是第 4 套 DAG）",
          reg.get("comp_huawei").sequence == reg.SEQ_COMP_ZH)
    check("只有 comp_stats 用 stats 序列",
          [s.value for s in comp if s.sequence == reg.SEQ_COMP_STATS] == ["comp_stats"])
    for value in ("comp_tianfu", "comp_teddy", "comp_certcup", "comp_shenzhen"):
        check("%s 走中文序列" % value,
              we.resolve_template(value).skill_names == we.resolve_template("comp_cumcm").skill_names)
    for value in ("comp_mcm", "comp_shuwei_en", "comp_apmcm", "comp_certcup_en"):
        check("%s 走英文序列" % value,
              we.resolve_template(value).skill_names == we.resolve_template("comp_mcm").skill_names)
    product_non_comp = (reg.GROUP_ACADEMIC, reg.GROUP_FROM_ASSETS, reg.GROUP_IP)
    check("学术/ip/资产模板都不复用竞赛序列",
          all(s.sequence not in reg.COMPETITION_SEQUENCES
              for s in reg.specs() if s.group in product_non_comp))


def test_tiered_timeouts() -> None:
    print("\n[7] 单步超时分级（写作 40 分钟 / 分析 15 分钟）")
    check("写作类档位 = 40 分钟", we.STEP_TIMEOUT_TIERS["writing"] == 2400)
    check("分析类档位 = 15 分钟", we.STEP_TIMEOUT_TIERS["analysis"] == 900)
    check("comp-paper-zh 归入写作档", we.timeout_tier("comp-paper-zh") == "writing")
    check("comp-paper-huawei 归入写作档", we.timeout_tier("comp-paper-huawei") == "writing")
    check("comp-paper-zh 单步预算 = 2400", we.tiered_inactivity_timeout("comp-paper-zh") == 2400)
    check("comp-prob-analysis 归入分析档", we.timeout_tier("comp-prob-analysis") == "analysis")
    check("comp-prob-analysis 单步预算 = 900", we.tiered_inactivity_timeout("comp-prob-analysis") == 900)
    check("comp-code 归入计算档", we.timeout_tier("comp-code") == "compute")
    check("comp-compile-zh 归入编译档", we.timeout_tier("comp-compile-zh") == "compile")
    check("未知技能归入最长档（宁多等，不误杀）",
          we.timeout_tier("brand-new-skill") == "default"
          and we.tiered_inactivity_timeout("brand-new-skill") == we.UNKNOWN_STEP_TIMEOUT)
    check("非字符串也不抛异常", we.timeout_tier(None) == "default" and we.timeout_tier(7) == "default")

    # 不变量：单步预算不超过「静默上限真值」
    skills = {s.skill_name for v in reg.values() for s in we.resolve_template(v).sub_steps}
    bad = sorted(
        s for s in skills if we.tiered_inactivity_timeout(s) > we.inactivity_timeout(s)
    )
    check("分级预算 <= 蓝方静默上限真值（%d 个技能）" % len(skills), not bad, str(bad))
    check("写作类预算 >= 实测需要的 24.5 分钟", we.WRITE_STEP_TIMEOUT >= 1470)
    check("inactivity_timeout(tiered=True) 等价于分级函数",
          we.inactivity_timeout("comp-paper-zh", tiered=True) == 2400)
    for skill, want in TRUTH_TIMEOUT.items():
        check("inactivity_timeout(%s) 真值不变 = %d" % (skill, want),
              we.inactivity_timeout(skill) == want, "got %s" % we.inactivity_timeout(skill))


def test_resolution_stability() -> None:
    print("\n[8] 解析稳定性（幂等 + docx 模式不破坏其它不变量）")
    for value in ("comp_cumcm", "comp_mcm", "comp_stats", "comp_huawei", "paper_writing"):
        a, b = we.resolve_template(value), we.resolve_template(value)
        check("%s 两次解析一致" % value, a.skill_names == b.skill_names)
    t = we.resolve_template("comp_cumcm", docx_mode=True)
    check("docx 模式把 paper/main.tex 改为 paper/main.md",
          t.sub_steps[6].primary_output == "paper/main.md", str(t.sub_steps[6].primary_output))
    check("docx 模式仍保留 8 步", len(t.sub_steps) == 8)
    check("docx 模式保留变体元数据",
          we.resolve_template("comp_huawei", docx_mode=True).sub_steps[6].fail_closed is True)
    check("docx 模式不改非论文产物",
          t.sub_steps[0].primary_output == "PROBLEM_ANALYSIS.md"
          and t.sub_steps[7].output_files == ("paper/main.docx",))
    check("docx 模式下成稿步 = .docx（不是 .md，也不是 .pdf）",
          t.sub_steps[7].primary_output == "paper/main.docx", str(t.sub_steps[7].primary_output))
    check("docx 模式不改图表产物",
          t.sub_steps[3].output_files == ("figures/latex_includes.tex",))
    check("docx 模式对已是 .md 的步骤幂等",
          we.resolve_template("paper_writing", docx_mode=True).sub_steps[3].primary_output == "paper/main.md")
    check("pipeline_skill 含解析值", t.pipeline_skill == "pipeline-comp_cumcm")
    check("step_count 属性可用", we.resolve_template("comp_stats").step_count == 5)


def test_other_families() -> None:
    print("\n[9] 学术 / from_assets / ip 族步骤契约")
    check("学术卡片含规划→分析→图表→撰写→预检→导出",
          tuple(s.skill_name for s in we.academic_steps())
          == ("paper-plan", "paper-analysis", "paper-figure", "paper-writing", "docx-precheck", "docx-export"))
    check("paper_writing 分支切换只换撰写技能（步骤数不变）",
          len(we.academic_steps("nature")) == len(we.academic_steps("academic_zh"))
          and we.academic_steps("nature")[3].skill_name == "nature-writing")
    check("未知分支回落到默认分支",
          we.academic_steps("nope")[3].skill_name == we.academic_steps()[3].skill_name)
    check("resolve_template(paper_writing, branch=nature) 生效",
          we.resolve_template("paper_writing", branch="nature").sub_steps[3].skill_name == "nature-writing")
    check("讲座/文献族含真实性验证步",
          "citation-verify" in [s.skill_name for s in we.literature_review_steps()])
    check("开题报告 4 步", len(we.thesis_proposal_steps()) == 4)
    check("课程论文 5 步且含可选数据分析", len(we.course_paper_steps()) == 5
          and we.course_paper_steps()[1].optional is True)
    check("课程报告 6 步且含 2 个可选步",
          len(we.course_report_steps()) == 6
          and sum(1 for s in we.course_report_steps() if s.optional) == 2)
    fas = we.from_assets_steps()
    check("from_assets 首步 = 资产盘点（带 assets_resolve 检查点）",
          fas[0].skill_name == "assets-inventory" and fas[0].checkpoint_type == "assets_resolve")
    check("from_assets 三步可合法跳过（缺失进入 missing_assets 而非直接失败）",
          {s.skill_name for s in fas if s.optional}
          == {"paper-analysis", "paper-figure", "paper-figure-drawio"})
    check("资产跳过规则与 §6.2 的三条一致", set(we.ASSET_SKIP_RULES) == set(
        {"paper-analysis", "paper-figure", "paper-figure-drawio"}))
    check("软著资料含源码/申请表/操作手册",
          {s.skill_name for s in we.copyright_material_steps()}
          >= {"copyright-source", "copyright-form", "copyright-manual"})
    check("专利交底书含技术方案与保护点",
          {s.skill_name for s in we.patent_disclosure_steps()} >= {"patent-solution", "patent-claims"})
    check("ip / 学术族都以 docx-export 收尾",
          all(steps[-1].skill_name == "docx-export"
              for steps in (we.copyright_material_steps(), we.patent_disclosure_steps(),
                            we.thesis_proposal_steps(), we.course_paper_steps())))
    check("每种编排都能构造出非空步骤链",
          all(we.build_sequence(k) for k in reg.SEQUENCES))
    check("未知编排键回退通用中文序列",
          we.build_sequence("nope")[0].skill_name == "comp-prob-analysis")


def test_backward_compatibility() -> None:
    print("\n[10] 与既有契约不冲突（蓝方恢复真值 + schemas 枚举）")
    check("国赛 8 步首步 = comp-prob-analysis / 赛题分析",
          we.comp_zh_steps()[0].skill_name == "comp-prob-analysis"
          and we.comp_zh_steps()[0].display_name == "赛题分析")
    check("美赛 8 步第 7 步 = comp-paper-en", we.comp_en_steps()[6].skill_name == "comp-paper-en")
    check("中英文前 6 步同名",
          [s.skill_name for s in we.comp_zh_steps()[:6]] == [s.skill_name for s in we.comp_en_steps()[:6]])
    check("comp-code 二级文件约束不变",
          we.required_companions_for("comp-code") == ("code/main.py", "figures/all_results.json"))
    check("默认 min_size = 100", we.min_size_for("nonexistent") == 100)

    # PAGE_LIMIT 覆盖全部注册值，且旧的 9 个值一字未变
    check("PAGE_LIMIT 覆盖全部 35 个值", set(we.PAGE_LIMIT) == set(reg.values()))
    for value, want in (("comp_zh", None), ("comp_en", None), ("course_paper", None),
                        ("thesis_proposal", None), ("comp_mathorcup", 30), ("comp_huawei", 50)):
        check("PAGE_LIMIT[%s] = %s" % (value, want), we.PAGE_LIMIT.get(value) == want
              and value in we.PAGE_LIMIT)

    # models.schemas.TemplateType 的 9 个值必须全部落在注册表内
    try:
        from models import schemas as S

        for member in S.TemplateType:
            check("schemas.TemplateType 的 %s 可解析" % member.value,
                  reg.is_known(member.value))
            check("  %s 不降级" % member.value, we.resolve_template(member).degraded is False)
    except Exception as exc:  # noqa: BLE001
        check("可导入 models.schemas 做交叉校验", False, "%s: %s" % (type(exc).__name__, exc))


def test_paper_body_gate_alignment() -> None:
    print("\n[11] 正文格式约定对齐：sections/*.md > main.md > prebuilt main.tex")
    zh = "中"
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)

        # 空工作区：三种承载形态都没有
        r = we.check_primary_output(ws, "comp-paper-zh")
        check("空工作区判「正文缺失」（三种形态都找过）",
              (not r.ok) and "正文缺失" in r.reason, r.reason)
        check("空工作区 paper_body_chars = (0, none)", we.paper_body_chars(ws) == (0, "none"))

        # --- 1) 约定格式：paper/sections/*.md ---
        sec = ws / "paper" / "sections"
        sec.mkdir(parents=True)
        (sec / "01_问题重述.md").write_text(zh * 6000, encoding="utf-8")
        r = we.check_primary_output(ws, "comp-paper-zh")
        check("sections 只有 6000 字符 < 10000 -> 不合格", (not r.ok) and "过小" in r.reason, r.reason)
        (sec / "02_模型建立.md").write_text(zh * 5000, encoding="utf-8")
        r = we.check_primary_output(ws, "comp-paper-zh")
        check("sections 合计 11000 字符 -> 通过", r.ok and "sections" in r.reason, r.reason)
        check("paper_body_chars 按文件名装配并累加",
              we.paper_body_chars(ws) == (11000, "sections"), str(we.paper_body_chars(ws)))
        check("非正文文件不参与计数（.docx/.txt 被忽略）",
              (sec / "notes.txt").write_text(zh * 5000, encoding="utf-8") is not None
              and we.paper_body_chars(ws) == (11000, "sections"))
        check("华为杯论文步走同一判定",
              we.check_primary_output(ws, "comp-paper-huawei").ok is True)
        check("英文论文步走同一判定",
              we.check_primary_output(ws, "comp-paper-en").ok is True)

        # sections 优先于 main.md（即使 main.md 也很长）
        (ws / "paper" / "main.md").write_text(zh * 20000, encoding="utf-8")
        check("sections 优先于 main.md",
              we.paper_body_chars(ws) == (11000, "sections"), str(we.paper_body_chars(ws)))

    # --- 阈值边界：独立工作区，避免与上面的文件累加 ---
    with tempfile.TemporaryDirectory() as td:
        w2 = Path(td)
        sec2 = w2 / "paper" / "sections"
        sec2.mkdir(parents=True)
        f = sec2 / "01_导言.md"
        f.write_text(zh * 9999, encoding="utf-8")
        check("总字符数 9999 < 10000 -> 不合格",
              we.check_primary_output(w2, "comp-paper-zh").ok is False)
        f.write_text(zh * 10000, encoding="utf-8")
        check("总字符数 10000 恰好达标 -> 通过（阈值含等号）",
              we.check_primary_output(w2, "comp-paper-zh").ok is True)
        (sec2 / "02_方法.md").write_text(zh * 500, encoding="utf-8")
        check("多文件按总字符数累加（10000+500）",
              we.paper_body_chars(w2) == (10500, "sections"), str(we.paper_body_chars(w2)))
        (sec2 / "03_空章节.md").write_text("   \n", encoding="utf-8")
        check("空白分节不计入文件数也不计字符",
              we.paper_body_chars(w2) == (10500, "sections"), str(we.paper_body_chars(w2)))

    # --- 2) 回退到 paper/main.md（读到「## 附录」之前） ---
    with tempfile.TemporaryDirectory() as td:
        w3 = Path(td)
        (w3 / "paper").mkdir()
        (w3 / "paper" / "main.md").write_text(
            zh * 10000 + "\n## 附录\n" + zh * 99999, encoding="utf-8")
        check("退到 main.md 且不算附录", we.paper_body_chars(w3) == (10000, "main_md"),
              str(we.paper_body_chars(w3)))
        check("main.md 恰好达标 -> 通过", we.check_primary_output(w3, "comp-paper-zh").ok is True)

    # --- 3) agent 直出的成品 paper/main.tex ---
    with tempfile.TemporaryDirectory() as td:
        w4 = Path(td)
        (w4 / "paper").mkdir()
        body = "x" * 12000
        (w4 / "paper" / "main.tex").write_text(
            "\\documentclass[12pt]{ctexart}\n\\begin{document}\n" + body + "\n\\end{document}\n",
            encoding="utf-8",
        )
        check("识别 agent 直出的成品 main.tex",
              we.paper_body_chars(w4)[1] == "prebuilt_tex", str(we.paper_body_chars(w4)))
        check("prebuilt 也能通过门控", we.check_primary_output(w4, "comp-paper-zh").ok is True)
        check("prebuilt 正文按 LaTeX 正文计数（排除导言区）",
              we.paper_body_chars(w4)[0] >= 12000, str(we.paper_body_chars(w4)))

        # 引擎自己的产物**不算**正文来源（否则「正文被删空」会骗过门控）
        (w4 / "paper" / "main.tex").write_text(
            "% modemon:generated-latex-export\n\\documentclass{ctexart}\n"
            "\\begin{document}\n" + body + "\n\\end{document}\n",
            encoding="utf-8",
        )
        check("带引擎生成标记的 main.tex 不认作正文",
              we.paper_body_chars(w4) == (0, "none"), str(we.paper_body_chars(w4)))
        check("只有引擎产物 -> 判正文缺失",
              we.check_primary_output(w4, "comp-paper-zh").ok is False)

        # 结构不完整（缺 \documentclass）的 .tex 也不能冒充正文
        (w4 / "paper" / "main.tex").write_text(body, encoding="utf-8")
        check("结构不完整的 main.tex 不算正文",
              we.paper_body_chars(w4) == (0, "none"), str(we.paper_body_chars(w4)))

    # --- 非正文步骤不受影响；变体/学术族的技能现在能查到主产物约束 ---
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        check("非正文步骤仍按文件判定",
              we.check_primary_output(ws, "comp-modeling").ok is False)
        r = we.check_primary_output(ws, "docx-precheck")
        check("学术族技能能查到主产物约束（旧实现静默放行）",
              (not r.ok) and "DOCX_PRECHECK.md" in r.reason, r.reason)
        check("figures/ 目录型判定不受影响",
              we.check_primary_output(ws, "paper-figure").ok is False)
        check("未知技能仍放行（无主产物约束）",
              we.check_primary_output(ws, "no-such-skill").ok is True)

    # --- 页数预检走同一来源 ---
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "paper" / "sections").mkdir(parents=True)
        (ws / "paper" / "sections" / "01_x.md").write_text(zh * 16000, encoding="utf-8")
        pages, chars = we.check_paper_body_pages(ws, language="zh")
        check("页数预检读 sections（16000 字 -> 20 页）", pages == 20 and chars == 16000,
              "got %s/%s" % (pages, chars))
        (ws / "paper" / "main.md").write_text(zh * 800, encoding="utf-8")
        pages, chars = we.check_paper_body_pages(ws, language="zh")
        check("页数预检优先 sections 而非 main.md", chars == 16000, str(chars))
        check("英文页数预算仍为 2200 字/页",
              we.check_paper_body_pages(ws, language="en")[0] == 7,
              str(we.check_paper_body_pages(ws, language="en")))


def main() -> int:
    print("=" * 72)
    print("modemon 模板注册表 + 编排解析回归")
    print("=" * 72)
    test_registry_data()
    test_all_values_resolve()
    test_degrade_is_graceful()
    test_comp_stats_sequence()
    test_huawei_variant()
    test_language_and_orchestration_split()
    test_tiered_timeouts()
    test_resolution_stability()
    test_other_families()
    test_backward_compatibility()
    test_paper_body_gate_alignment()
    print("\n" + "=" * 72)
    print("PASS %d / FAIL %d" % (PASS, FAIL))
    print("=" * 72)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
