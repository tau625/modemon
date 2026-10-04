/**
 * 模板的中文名与分组。
 *
 * 为什么需要这层映射：`/api/templates` 的 `display_name` 目前**等于 template 值本身**
 * （实测 35 个全部如此：`comp_tianfu` → display_name `comp_tianfu`），
 * 直接拿它当下拉文案等于给用户看两遍代号。
 *
 * 中文名来源：`reports/03-frontend.md` §7.1「赛题模板目录」（蓝方 NewWorkflow 的
 * 模板常量表，22 个 `comp_*` + 学术/科研条目），分组同理（`comp_` 前缀 = 竞赛）。
 * 注册表里若出现这张表没覆盖的新模板，`labelOf` 回退到 API 的 display_name——
 * 于是新增模板**不会**因为前端字典没跟上而显示成空白。
 */

export const TEMPLATE_LABELS = {
  // —— 竞赛（22）——
  comp_tianfu: '天府杯',
  comp_certcup: '认证杯',
  comp_mathorcup: 'MathorCup 高校数学建模',
  comp_teddy: '泰迪杯（数据挖掘）',
  comp_huadong: '华东杯',
  comp_huazhong: '华中杯',
  comp_wuyi: '五一杯',
  comp_zhongqing: '中青杯',
  comp_yangtze: '长三角高校数模',
  comp_stats: '统计建模大赛',
  comp_shuwei: '数维杯',
  comp_diangong: '电工杯',
  comp_liaoning: '辽宁省 / 东三省',
  comp_apmcm_zh: '亚太赛（中文）',
  comp_shenzhen: '深圳杯',
  comp_huashu: '华数杯',
  comp_cumcm: '国赛 CUMCM（高教社杯）',
  comp_huawei: '华为杯（研赛）',
  comp_mcm: '美赛 MCM / ICM',
  comp_shuwei_en: '数维杯（英文）',
  comp_apmcm: '亚太 APMCM（英文）',
  comp_certcup_en: '认证杯（英文）',
  // —— 通用竞赛入口 ——
  comp_zh: '通用竞赛（中文）',
  comp_en: '通用竞赛（英文）',
  // —— 学术 / 科研（13）——
  paper_writing: '论文撰写',
  paper_from_assets: '素材成文',
  thesis_proposal: '开题报告',
  literature_review: '文献综述',
  course_paper: '课程论文',
  course_report: '课程报告',
  humanities_paper: '人文社科论文',
  grad_project: '毕业设计 / 研究生项目',
  copyright_material: '著作权材料',
  patent_disclosure: '专利交底书',
  full_pipeline: '全流程（竞赛总入口）',
};

/** 英文写作模板（`group:'en'`，页数参考按英文口径）。 */
export const EN_TEMPLATES = new Set([
  'comp_mcm', 'comp_shuwei_en', 'comp_apmcm', 'comp_certcup_en', 'comp_en',
]);

export function labelOf(t) {
  return TEMPLATE_LABELS[t.template] || t.display_name || t.template;
}

export function groupOf(t) {
  return t.template.startsWith('comp_') ? '竞赛模板' : '学术与科研模板';
}

export function langOf(t) {
  return EN_TEMPLATES.has(t.template) ? 'en' : 'zh';
}

/** 下拉一行文案：中文名 · 步数 · 页数参考 · 语言/申报标记。 */
export function optionText(t) {
  const bits = [`${labelOf(t)}（${t.template}）`, `${t.step_count} 步`];
  bits.push(t.page_advisory ? `≤${t.page_advisory} 页` : '页数不限');
  if (langOf(t) === 'en') bits.push('英文');
  if (t.requires_ai_disclosure) bits.push('需 AI 申报');
  return bits.join(' · ');
}

/** 按分组返回 `<optgroup>` 结构（列表页与排版页共用）。 */
export function groupedOptions(templates) {
  const groups = new Map();
  for (const t of templates) {
    const g = groupOf(t);
    if (!groups.has(g)) groups.set(g, []);
    groups.get(g).push(t);
  }
  return Array.from(groups.entries()).map(([g, list]) => ({
    group: g,
    items: list.map((t) => ({ value: t.template, text: optionText(t), raw: t })),
  }));
}
