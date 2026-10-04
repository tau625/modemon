/**
 * 事件渲染的**执行级**自检（Node 直接跑前端模块，不装任何依赖）。
 *
 * 为什么需要它：项目刻意"无构建步骤"（没有打包器、没有 jsdom），
 * 于是 `lib/events.js` 的渲染分支平时只能靠读代码确认。这个脚本把纯函数模块
 * 真的 import 进来跑一遍，断言：
 *
 *   1. 三类自定义事件（`result_audit` / `figure_render` / `citation_audit`）
 *      渲染出的标记**互不相同**（类名、verdict 徽记）；
 *   2. `verdict` 语义色与后端口径一致，且 `ok=false` 压过 `verdict`；
 *   3. 载荷里的 HTML 一律被转义（事件内容来自模型产出，不能当可信 HTML）；
 *   4. 模板标签层不丢模板（35 进 35 出）并能回退到 `display_name`。
 *
 * 实现取舍：Node 只把 `.mjs`（或 `type:module` 的包）当 ES module，
 * 而仓库里是 `.js`。这里把 `lib/*.js` 复制成临时 `.mjs` 并改写相对 import，
 * **不改动仓库里的任何文件**，也不新增 package.json（那会暗示引入了 npm 工程）。
 *
 * 手跑：node checks/events_render_check.mjs
 */

import { mkdtempSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const LIB = join(HERE, '..', 'lib');

let PASS = 0;
let FAIL = 0;
const FAILURES = [];

function check(name, cond, detail = '') {
  if (cond) {
    PASS += 1;
    console.log(`  PASS  ${name}`);
  } else {
    FAIL += 1;
    FAILURES.push(name);
    console.log(`  FAIL  ${name}  ${String(detail).slice(0, 200)}`);
  }
}

function section(title) {
  console.log(`\n[${title}]`);
}

// ---------------------------------------------------------------- 加载模块

const MODULES = ['dom.js', 'events.js', 'labels.js', 'api.js'];
const tmp = mkdtempSync(join(tmpdir(), 'modemon-fe-'));
let events;
let labels;
let api;

try {
  for (const f of MODULES) {
    const src = readFileSync(join(LIB, f), 'utf8')
      .replace(/(from\s+['"])(\.\.?\/[^'"]+)\.js(['"])/g, '$1$2.mjs$3');
    writeFileSync(join(tmp, f.replace(/\.js$/, '.mjs')), src, 'utf8');
  }
  events = await import(pathToFileURL(join(tmp, 'events.mjs')).href);
  labels = await import(pathToFileURL(join(tmp, 'labels.mjs')).href);
  api = await import(pathToFileURL(join(tmp, 'api.mjs')).href);
} catch (err) {
  console.log(`  FAIL  前端模块可被真实引擎 import  ${err.message}`);
  console.log('\nPASS 0 / FAIL 1');
  rmSync(tmp, { recursive: true, force: true });
  process.exit(1);
}

//: 与被测模块同源的事件工厂（走 WS 平铺载荷那条路，与后端广播形态一致）。
const mkEvent = (kind, payload, seq) => ({
  ...events.customEventFromWs({ type: kind, workflow_id: 'w-test', ...payload }),
  run_id: 'run-test',
  sequence: seq,
  started_at: '2026-01-01T00:00:01',
});

try {
  section('1. 分类表');
  check('CUSTOM_KINDS 恰好是三类',
    JSON.stringify([...events.CUSTOM_KINDS].sort())
      === JSON.stringify(['citation_audit', 'figure_render', 'result_audit']),
    JSON.stringify(events.CUSTOM_KINDS));
  check('isCustom 只认这三类',
    events.isCustom('result_audit') && events.isCustom('figure_render')
    && events.isCustom('citation_audit') && !events.isCustom('progress'));

  section('2. WS 平铺载荷归一');
  const wsResult = events.customEventFromWs({
    type: 'result_audit', workflow_id: 'w1', triggered_by: 'comp-code',
    skill_used: 'experiment-audit', verdict: 'issue', ok: true,
    issues: ['Z0 与正文矛盾'], notes: ['已比对 all_results.json'],
  });
  check('WS 平铺载荷被归一成事件（去掉信封字段）',
    wsResult.kind === 'result_audit' && wsResult.evidence.verdict === 'issue'
    && wsResult.evidence.triggered_by === 'comp-code');
  check('归一后自动生成标题（含 verdict）', wsResult.title.includes('issue'), wsResult.title);
  check('归一后 state 反映 ok', wsResult.state === 'completed');

  section('3. 三类各自渲染出可区分的标记');
  const evs = [
    mkEvent('result_audit', { verdict: 'pass', ok: true, issues: [], notes: [] }, 1),
    mkEvent('figure_render', {
      ok: true, rendered: [{ spec: 's.json', png: 'figures/a.png' }], skipped: [], errors: [],
    }, 2),
    mkEvent('citation_audit', {
      verdict: 'issue', top_verdict: 'FAIL', ok: true, issues: ['[3] 作者年份与原文不符'],
    }, 3),
  ];
  const rows = evs.map((e) => events.renderRow(e));
  const rowKinds = rows.map((h) => (h.match(/ev custom (\w+)/) || [])[1]);
  check('三类渲染出的类名互不相同且正确',
    JSON.stringify(rowKinds) === JSON.stringify(events.CUSTOM_KINDS),
    JSON.stringify(rowKinds));
  check('结果审计 pass → 绿色徽记', rows[0].includes('chip ok'), rows[0].slice(0, 80));
  check('图表渲染列出产物与张数',
    rows[1].includes('figures/a.png') && rows[1].includes('chip ok'));
  check('引用审计 top_verdict=FAIL → 红色徽记', rows[2].includes('chip bad'));
  check('引用审计的问题被渲染出来', rows[2].includes('作者年份与原文不符'));

  section('4. verdict 语义色（与后端判决口径一致）');
  check('pass → ok', events.verdictTone('result_audit', { verdict: 'pass' }) === 'ok');
  check('issue → warn', events.verdictTone('result_audit', { verdict: 'issue' }) === 'warn');
  check('skipped → dim', events.verdictTone('result_audit', { verdict: 'skipped' }) === 'dim');
  check('top_verdict FAIL → bad',
    events.verdictTone('citation_audit', { verdict: 'pass', top_verdict: 'FAIL' }) === 'bad');
  check('top_verdict PASS → ok',
    events.verdictTone('citation_audit', { verdict: 'issue', top_verdict: 'PASS' }) === 'ok');
  check('ok=false 压过 verdict=pass（没跑成不能显示成审过）',
    events.verdictTone('result_audit', { verdict: 'pass', ok: false }) === 'bad');
  check('figure_render 无产物且有 errors → bad',
    events.verdictTone('figure_render', { ok: true, rendered: [], errors: ['rc=1'] }) === 'bad');
  check('figure_render 有产物 → ok',
    events.verdictTone('figure_render', { ok: true, rendered: [{ png: 'a.png' }] }) === 'ok');
  check('verdictText 带上顶层结论',
    events.verdictText('citation_audit', { verdict: 'issue', top_verdict: 'FAIL' }).includes('FAIL'));

  section('5. 「审计与渲染」高亮面板');
  const panel = events.renderAuditPanel(evs);
  check('三类都有卡片',
    ['result_audit', 'figure_render', 'citation_audit']
      .every((k) => panel.includes(`data-kind="${k}"`)));
  check('面板显示累计次数', panel.includes('共 1 次'), panel.slice(0, 120));
  const emptyPanel = events.renderAuditPanel([]);
  check('没有事件时给出「尚无事件」而不是静默为空',
    emptyPanel.split('尚无事件').length - 1 === 3);
  const twoRounds = events.renderAuditPanel([...evs, mkEvent('result_audit', { verdict: 'issue' }, 4)]);
  check('同一类多次出现时取最新一条（verdict=issue）',
    twoRounds.includes('共 2 次') && /data-kind="result_audit"[^>]*data-verdict="issue"/.test(twoRounds),
    twoRounds.slice(0, 200));

  section('6. 转义（事件载荷来自模型产出，不能当可信 HTML）');
  const xss = events.renderRow(mkEvent('citation_audit', {
    verdict: 'issue', ok: true, issues: ['<img src=x onerror=alert(1)>'],
  }, 5));
  check('问题列表里的 HTML 被转义', !xss.includes('<img') && xss.includes('&lt;img'));

  section('7. 事件流统计与去重键');
  const meta = events.streamMeta(evs);
  check('统计行列全三类计数',
    meta.includes('result_audit 1') && meta.includes('figure_render 1')
    && meta.includes('citation_audit 1'), meta);
  check('同 (run_id, sequence) 视为同一事件',
    events.eventKey({ run_id: 'r', sequence: 5 }) === events.eventKey({ run_id: 'r', sequence: 5 }));
  check('不同 sequence 视为不同事件',
    events.eventKey({ run_id: 'r', sequence: 5 }) !== events.eventKey({ run_id: 'r', sequence: 6 }));
  check('REST 事件按 event_id 去重', events.eventKey({ event_id: 'abc' }) === 'id:abc');

  section('8. 标准事件不受影响');
  const std = events.renderRow({
    kind: 'tool', title: '工具调用：Read',
    safe_detail: 'figures/all_results.json', started_at: '2026-01-01T00:00:02',
  });
  check('普通事件仍走普通行（不带 custom 类）',
    std.includes('class="ev"') && !std.includes('custom') && std.includes('工具调用：Read'));
  check('普通事件带产物路径', std.includes('figures/all_results.json'));

  section('9. 模板标签层');
  const TEMPLATES = [
    'comp_tianfu', 'comp_certcup', 'comp_mathorcup', 'comp_teddy', 'comp_huadong',
    'comp_huazhong', 'comp_wuyi', 'comp_zhongqing', 'comp_yangtze', 'comp_stats',
    'comp_shuwei', 'comp_diangong', 'comp_liaoning', 'comp_apmcm_zh', 'comp_shenzhen',
    'comp_huashu', 'comp_cumcm', 'comp_huawei', 'comp_mcm', 'comp_shuwei_en',
    'comp_apmcm', 'comp_certcup_en', 'paper_writing', 'thesis_proposal',
    'literature_review', 'course_paper', 'course_report', 'paper_from_assets',
    'copyright_material', 'patent_disclosure', 'comp_zh', 'comp_en',
    'full_pipeline', 'humanities_paper', 'grad_project',
  ];
  const raw = TEMPLATES.map((t, i) => ({
    template: t, display_name: t, step_count: 8,
    page_advisory: i < 22 ? 30 : null, page_rule_mode: 'advisory_max',
    requires_ai_disclosure: t === 'comp_cumcm',
  }));
  const groups = labels.groupedOptions(raw);
  const total = groups.reduce((n, g) => n + g.items.length, 0);
  check('groupedOptions 一个模板都不丢（35 进 35 出）', total === 35, total);
  check('分组成竞赛 / 学术与科研两组',
    groups.length === 2 && groups.map((g) => g.group).join(',') === '竞赛模板,学术与科研模板');
  check('每个选项都带模板代号（不会出现无法区分的重复文案）',
    new Set(groups.flatMap((g) => g.items.map((i) => i.text))).size === 35);
  check('选项文案含 display_name 回退、步数与页数参考',
    labels.optionText(raw[0]).includes('comp_tianfu')
    && labels.optionText(raw[0]).includes('8 步')
    && labels.optionText(raw[0]).includes('≤30 页')
    && labels.optionText(raw[30]).includes('页数不限'));
  check('未收录的新模板回退到 display_name',
    labels.labelOf({ template: 'comp_brand_new', display_name: '新模板名' }) === '新模板名');
  check('英文模板识别（影响每页字数口径）',
    labels.langOf({ template: 'comp_mcm' }) === 'en'
    && labels.langOf({ template: 'comp_cumcm' }) === 'zh');
  check('国赛中文名与 AI 申报标记齐备',
    labels.labelOf({ template: 'comp_cumcm', display_name: 'comp_cumcm' }).includes('CUMCM')
    && raw.find((t) => t.requires_ai_disclosure).template === 'comp_cumcm');

  section('10. 表单 URL 编码');
  const url = api.qs({ workspace: 'E:\\modemon-ws\\demo', template: 'comp_cumcm', skip: '' });
  check('qs 丢掉空值并把工作区路径编码',
    !url.includes('skip=') && url.includes('workspace=E%3A'), url);
  check('qs 保留模板参数', url.includes('template=comp_cumcm'));
} catch (err) {
  FAIL += 1;
  FAILURES.push(`渲染自检抛异常: ${err.stack || err.message}`);
  console.log(`  FAIL  渲染自检抛异常  ${err.message}`);
} finally {
  rmSync(tmp, { recursive: true, force: true });
}

console.log(`\n${'='.repeat(74)}`);
console.log(`PASS ${PASS} / FAIL ${FAIL}`);
if (FAILURES.length) {
  console.log('失败项：');
  for (const f of FAILURES) console.log(`  - ${f}`);
}
console.log('='.repeat(74));
process.exit(FAIL ? 1 : 0);
