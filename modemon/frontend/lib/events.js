/**
 * 运行事件的分类与渲染。
 *
 * 为什么单独一个模块：事件流里混着**两类完全不同的东西**——
 *
 *   1. agent 运行事件（`started / progress / tool / result / error`），
 *      有 `title` + `safe_detail`，是过程；
 *   2. **自定义钩子事件**（`result_audit` / `figure_render` / `citation_audit`），
 *      载荷里带 `verdict` / `issues` / `rendered`，是**可核验的结论**。
 *
 * 第 2 类对用户价值最高（"这篇论文的数字可信吗 / 图真的渲染出来了吗 /
 * 引用审过了吗"），但它们的字段不在 `ALLOWED_EVENT_KEYS` 里，走的是
 * `sanitize_custom_evidence` 的独立白名单——所以前端**不能**按普通事件
 * 那一套 `title/safe_detail` 去渲染，必须认识它们的载荷。
 *
 * 两条数据来源的形态不同，这里统一归一：
 *   - REST `/run-events`：`{kind, title, safe_detail, evidence:{verdict,...}}`
 *   - WebSocket：`{type:'result_audit', workflow_id, verdict, ok, issues, ...}`（顶层平铺）
 */

import { esc, fmtTs } from './dom.js';

/** 三类自定义事件（与后端 `_persist_custom_event` 的 kind 逐字一致）。 */
export const CUSTOM_KINDS = ['result_audit', 'figure_render', 'citation_audit'];

/** kind → 展示元数据。`custom:true` 的走高亮分支。 */
export const EVENT_META = {
  started: { label: '开始', tone: 'dim' },
  progress: { label: '进展', tone: 'dim' },
  tool: { label: '工具', tone: 'accent' },
  result: { label: '结果', tone: 'ok' },
  error: { label: '错误', tone: 'bad' },
  heartbeat: { label: '心跳', tone: 'dim' },
  result_audit: { label: '结果审计', tone: 'run', custom: true },
  figure_render: { label: '图表渲染', tone: 'accent', custom: true },
  citation_audit: { label: '引用审计', tone: 'ok', custom: true },
};

export const isCustom = (kind) => CUSTOM_KINDS.includes(kind);

export function metaOf(kind) {
  return EVENT_META[kind] || { label: kind, tone: 'dim' };
}

// ---------------------------------------------------------------- 归一

/** WebSocket 上的自定义事件是**平铺**的，去掉信封字段即为载荷。 */
export function customEventFromWs(msg) {
  const payload = {};
  for (const [k, v] of Object.entries(msg)) {
    if (k === 'type' || k === 'workflow_id') continue;
    payload[k] = v;
  }
  return {
    kind: msg.type,
    run_id: '',
    sequence: null,
    state: payload.ok === false ? 'failed' : 'completed',
    title: autoTitle(msg.type, payload),
    safe_detail: autoDetail(msg.type, payload),
    public_artifact_path: null,
    started_at: new Date().toISOString(),
    completed_at: new Date().toISOString(),
    evidence: payload,
    source: 'ws',
  };
}

function autoTitle(kind, p) {
  if (kind === 'result_audit') return `结果诚信审计：${p.verdict ?? '-'}`;
  if (kind === 'citation_audit') return `引用审计：${p.verdict ?? '-'}`;
  if (kind === 'figure_render') return `FigureSpec 渲染：${(p.rendered || []).length} 张`;
  return kind;
}

function autoDetail(kind, p) {
  const issues = (p.issues || []).map((x) => String(x));
  if (issues.length) return issues.slice(0, 3).join('; ');
  if (kind === 'figure_render' && (p.errors || []).length) {
    return (p.errors || []).slice(0, 3).join('; ');
  }
  return (p.notes || []).slice(0, 3).map((x) => String(x)).join('; ');
}

/** 自定义事件的载荷：REST 走 `evidence`，WS 归一后也放在 `evidence`。 */
export function payloadOf(ev) {
  if (isCustom(ev.kind)) return ev.evidence || {};
  return ev.evidence || {};
}

/** 去重键：REST 有 event_id，WS 有 (run_id, sequence)；自定义事件按时间+verdict。 */
export function eventKey(ev) {
  if (ev.event_id) return `id:${ev.event_id}`;
  if (ev.run_id && ev.sequence !== null && ev.sequence !== undefined) {
    return `seq:${ev.run_id}:${ev.sequence}`;
  }
  return `k:${ev.kind}:${ev.started_at}:${(ev.title || '').slice(0, 40)}`;
}

// ---------------------------------------------------------------- 判决

/**
 * `verdict` → 语义色。
 *
 * 取值口径来自后端（**只认结构化标记**）：
 *   - `result_audit` / `citation_audit.verdict`：`pass` | `issue` | `skipped`
 *   - `citation_audit.top_verdict`：`PASS` | `WARN` | `FAIL` | `NOT_APPLICABLE` | `BLOCKED` | `ERROR`
 *
 * `ok===false` 一律压过 verdict（"没跑成"不能被显示成"审过了"）。
 */
export function verdictTone(kind, p = {}) {
  if (p.ok === false) return 'bad';
  if (kind === 'figure_render') {
    return (p.rendered || []).length ? 'ok' : ((p.errors || []).length ? 'bad' : 'dim');
  }
  const top = String(p.top_verdict || '').toUpperCase();
  const topMap = {
    PASS: 'ok', WARN: 'warn', FAIL: 'bad',
    NOT_APPLICABLE: 'dim', BLOCKED: 'warn', ERROR: 'bad',
  };
  if (top && topMap[top]) return topMap[top];
  const v = String(p.verdict || '').toLowerCase();
  return { pass: 'ok', issue: 'warn', skipped: 'dim', fail: 'bad' }[v] || 'dim';
}

/** 卡片/行上显示的判决文本（把最有信息量的那个字段挑出来）。 */
export function verdictText(kind, p = {}) {
  if (kind === 'figure_render') {
    if (p.ok === false) return '渲染失败';
    return `${(p.rendered || []).length} 张渲染 / ${(p.skipped || []).length} 张跳过`;
  }
  const parts = [];
  if (p.verdict) parts.push(String(p.verdict));
  if (p.top_verdict && String(p.top_verdict) !== String(p.verdict)) {
    parts.push(`顶层 ${p.top_verdict}`);
  }
  return parts.join(' · ') || '-';
}

// ---------------------------------------------------------------- 渲染

function issuesBlock(title, list) {
  if (!list || !list.length) return '';
  return `<details><summary>${esc(title)}（${list.length}）</summary><ul>`
    + list.map((x) => `<li>${esc(typeof x === 'string' ? x : JSON.stringify(x))}</li>`).join('')
    + '</ul></details>';
}

/** 事件流里的一行。自定义事件走 `custom` 分支（左侧着色 + verdict 徽记）。 */
export function renderRow(ev) {
  const m = metaOf(ev.kind);
  const ts = `<span class="ts">${esc(fmtTs(ev.started_at))}</span>`;

  if (!m.custom) {
    const detail = ev.safe_detail || '';
    return `<div class="ev" data-kind="${esc(ev.kind)}">
      ${ts}<span class="k ${esc(ev.kind)}">${esc(ev.kind)}</span>
      <span>${esc(ev.title || '')}</span>
      ${detail ? `<div class="d">${esc(detail)}</div>` : ''}
      ${ev.public_artifact_path ? `<div class="d">📄 ${esc(ev.public_artifact_path)}</div>` : ''}
    </div>`;
  }

  const p = payloadOf(ev);
  const tone = verdictTone(ev.kind, p);
  const parts = [];
  if (ev.kind === 'figure_render') {
    for (const r of (p.rendered || []).slice(0, 4)) {
      const name = r && typeof r === 'object' ? (r.png || r.svg || r.spec) : r;
      if (name) parts.push(`🖼 ${name}`);
    }
    if (!parts.length && p.includes_tex) parts.push(`📄 ${p.includes_tex}`);
  }
  const issuesTitle = ev.kind === 'figure_render' ? '未渲染明细' : '问题与说明';
  const notesTitle = ev.kind === 'result_audit' ? '审计说明' : '说明';

  return `<div class="ev custom ${esc(ev.kind)}" data-kind="${esc(ev.kind)}">
    ${ts}<span class="k ${esc(ev.kind)}">${esc(ev.kind)}</span>
    <span class="chip ${tone}">${esc(verdictText(ev.kind, p))}</span>
    <span>${esc(ev.title || m.label)}</span>
    ${parts.length ? `<div class="d">${parts.map(esc).join('<br/>')}</div>` : ''}
    ${!parts.length && ev.safe_detail ? `<div class="d">${esc(ev.safe_detail)}</div>` : ''}
    ${issuesBlock(issuesTitle, p.issues)}
    ${issuesBlock('errors', p.errors)}
    ${issuesBlock(notesTitle, p.notes)}
    ${p.upstream && p.upstream.repo
      ? `<div class="d">上游 ${esc(p.upstream.repo)} · ${esc(p.upstream.license || '')}</div>` : ''}
  </div>`;
}

/**
 * 「审计与渲染」高亮面板：每类**取最新一条**做卡片。
 *
 * 这是三类自定义事件的价值所在——`verdict` 就是要一眼看到的那个字段，
 * 所以不放事件流里等比滚动，而是固定在顶部。
 */
export function renderAuditPanel(events) {
  const latest = {};
  const counts = {};
  for (const ev of events) {
    if (!isCustom(ev.kind)) continue;
    counts[ev.kind] = (counts[ev.kind] || 0) + 1;
    latest[ev.kind] = ev;                       // 数组有序 → 最后一条即最新
  }
  const cards = CUSTOM_KINDS.map((kind) => {
    const ev = latest[kind];
    if (!ev) {
      return `<div class="card" data-kind="${kind}">
        <div class="hd">${esc(EVENT_META[kind].label)}
          <span class="chip dim">尚无事件</span></div>
        <div class="d" style="color:var(--dim);font-size:11px">
          该步骤跑完后由后端钩子派生；未执行时事件也不会凭空出现。</div>
      </div>`;
    }
    const p = payloadOf(ev);
    const tone = verdictTone(kind, p);
    const rows = [];
    if (kind === 'figure_render') {
      rows.push(`渲染 ${(p.rendered || []).length} 张 · 跳过 ${(p.skipped || []).length} 张`);
      if (p.includes_tex) rows.push(`登记文件 ${p.includes_tex}`);
    } else if (p.skill_used) {
      rows.push(`审计技能 ${p.skill_used}`);
    }
    return `<div class="card" data-kind="${kind}" data-verdict="${esc(verdictText(kind, p))}">
      <div class="hd">${esc(EVENT_META[kind].label)}
        <span class="chip ${tone}">${esc(verdictText(kind, p))}</span>
        <span style="flex:1"></span>
        <span class="chip dim">共 ${counts[kind] || 1} 次</span>
      </div>
      <div class="d" style="color:var(--dim);font-size:11px">
        ${esc(fmtTs(ev.started_at))}${p.triggered_by ? ` · 由 ${esc(p.triggered_by)} 触发` : ''}
      </div>
      ${rows.map((r) => `<div style="font-size:11px;margin-top:2px">${esc(r)}</div>`).join('')}
      ${(p.issues || []).length
        ? `<ul>${(p.issues || []).slice(0, 5).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
      ${!(p.issues || []).length && (p.notes || []).length
        ? `<ul>${(p.notes || []).slice(0, 3).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
      ${kind === 'figure_render' && (p.errors || []).length
        ? `<ul>${(p.errors || []).slice(0, 3).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
    </div>`;
  });
  return cards.join('');
}

/** 事件流统计行文案（含自定义事件计数——否则"没有审计"看不出来）。 */
export function streamMeta(events) {
  const c = {};
  for (const ev of events) c[ev.kind] = (c[ev.kind] || 0) + 1;
  const custom = CUSTOM_KINDS
    .map((k) => `${k} ${c[k] || 0}`)
    .join(' · ');
  return `共 ${events.length} 条事件（先落库、后广播）｜自定义事件：${custom}`;
}
