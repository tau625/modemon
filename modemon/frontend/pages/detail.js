/**
 * 页面 2／5：执行详情（步骤 + 检查点 + 实时事件 + 回放）。
 *
 * 三栏：
 *   左   当前工作流 / 步骤状态 / 检查点确认
 *   中   **审计与渲染**（三类自定义事件高亮）+ 运行事件流
 *   右   控制台（工作区、预算、连续执行、回放、遗体修复）
 *
 * 关键取舍：
 *   - 状态一律以 REST 为准；WS 只做实时通知。回放走 `/run-events`，
 *     WS 断线后不会丢事件（`/run-events` 是权威历史）。
 *   - `result_audit` / `figure_render` / `citation_audit` **不混进普通事件流**，
 *     在顶部单独成卡：它们的 `verdict` 是"能不能信这份产出"的结论，
 *     不能跟着日志一起滚走。
 */

import { $id, esc, fmtTs, truncate, STEP_STATUS, WORKFLOW_STATUS } from '../lib/dom.js';
import { CUSTOM_KINDS, renderRow, renderAuditPanel, streamMeta } from '../lib/events.js';
import {
  state, subscribe, selectWorkflow, refreshWorkflow, refreshWorkflows, replayEvents,
  runStep, runAll, resolveCheckpoint, repairWorkflow, setWorkspace, workflowProgress, getJSON,
} from '../lib/store.js';
import { labelOf } from '../lib/labels.js';

export const id = 'detail';
export const hash = '#/detail';
export const label = '执行详情';

let cleanup = null;
let timer = null;

export function render(root, param) {
  root.innerHTML = `
  <div class="page grid-3">
    <section>
      <h2>步骤 <span class="count" id="stepCount"></span></h2>
      <div class="pad" style="padding-bottom:0">
        <select id="wfPicker"></select>
      </div>
      <div id="wfHeader" class="empty">左侧选择或新建一个工作流</div>
      <div id="checkpointArea"></div>
      <div id="stepList"></div>
    </section>

    <section>
      <h2>审计与渲染（自定义事件） <span class="count" id="hookCount"></span></h2>
      <div class="pad" style="padding-bottom:0">
        <div class="meta" style="padding:0 0 8px">
          三类钩子事件单独取最新一条做卡片——<code>verdict</code> 是判断
          "产出能不能用"的依据，不该跟着日志滚走。
        </div>
        <div class="kpis" id="auditPanel"></div>
      </div>
      <h2 style="border-top:1px solid var(--line);margin-top:10px">
        运行事件（实时） <span class="count" id="evCount"></span>
      </h2>
      <div class="pad" style="padding-bottom:0">
        <div class="row">
          <button id="replayBtn">回放事件</button>
          <label class="inline" style="margin-left:6px">
            <input type="checkbox" id="allMessages" />
            跨全部步骤
          </label>
          <span class="grow"></span>
          <button id="clearBtn" class="ghost">清屏</button>
        </div>
        <div class="meta" id="evMeta" style="padding:6px 0 0"></div>
      </div>
      <div id="events"></div>
    </section>

    <section>
      <h2>控制台</h2>
      <div class="pad stack">
        <label class="field">工作区绝对路径
          <input id="workspace" placeholder="E:\\modemon-ws\\demo" />
        </label>
        <div class="row">
          <button id="runAllBtn">连续执行到检查点</button>
          <button id="repairBtn" class="ghost">修复僵尸状态</button>
        </div>
        <div class="row">
          <label class="field grow" style="flex:1">单次预算 USD
            <input id="budget" value="0.40" />
          </label>
        </div>
        <label class="inline">
          <input type="checkbox" id="strictMode" />
          严格模式（能力不足则拒绝执行）
        </label>
        <div id="consoleMsg" class="meta" style="padding:0"></div>
      </div>
      <h2 style="border-top:1px solid var(--line)">进度</h2>
      <div class="pad"><div class="kpis" id="progressKpis"></div></div>
      <h2 style="border-top:1px solid var(--line)">后台任务</h2>
      <div class="pad" id="runsBox"><span class="empty">—</span></div>
    </section>
  </div>`;

  $id('workspace').value = state.workspace;
  $id('budget').value = state.budget;
  $id('strictMode').checked = state.strict;
  $id('allMessages').checked = state.replayAllMessages;

  $id('workspace').onchange = (e) => setWorkspace(e.target.value.trim());
  $id('budget').onchange = (e) => { state.budget = e.target.value.trim() || '0.40'; };
  $id('strictMode').onchange = (e) => { state.strict = e.target.checked; };
  $id('allMessages').onchange = async (e) => {
    state.replayAllMessages = e.target.checked;
    await replayEvents();
  };
  $id('replayBtn').onclick = () => replayEvents().catch(consoleMsgErr);
  $id('runAllBtn').onclick = () => withMsg(() => runAll(8));
  $id('repairBtn').onclick = () => withMsg(async () => {
    const r = await repairWorkflow();
    consoleMsg(`遗体修复：回收 ${r?.count ?? r?.repaired?.length ?? 0} 条`, 'ok');
  });
  $id('clearBtn').onclick = () => {
    $id('events').innerHTML = '';
    $id('evMeta').textContent = '已清屏（再次「回放事件」可从库里取回）';
  };
  $id('wfPicker').onchange = (e) => {
    if (e.target.value) location.hash = `#/detail/${e.target.value}`;
  };

  const offs = [subscribe(onStore)];
  cleanup = () => { offs.forEach((f) => f()); };
  timer = setInterval(tickCheckpoint, 1000);

  refreshWorkflows().then(renderPicker).catch(consoleMsgErr);
  refreshRuns();

  const target = param || state.workflowId;
  const boot = (target && target !== state.workflowId)
    ? selectWorkflow(target)
    : Promise.resolve(refreshWorkflow());
  boot.then(() => {
    renderHeader(); renderPicker(); renderSteps(); renderCheckpoint();
    renderAuditPanelInto(); renderEventsFull();
  }).catch(consoleMsgErr);

  return () => { if (cleanup) cleanup(); if (timer) { clearInterval(timer); timer = null; } };
}

export function unmount() {
  if (cleanup) { cleanup(); cleanup = null; }
  if (timer) { clearInterval(timer); timer = null; }
}

function consoleMsg(text, tone = '') {
  const el = $id('consoleMsg');
  if (!el) return;
  const color = tone === 'err' ? 'var(--err)' : tone === 'ok' ? 'var(--ok)' : 'var(--dim)';
  el.innerHTML = `<span style="color:${color}">${esc(text)}</span>`;
}
function consoleMsgErr(e) { consoleMsg(e.message, 'err'); }

async function withMsg(fn, okText = '已提交（后台执行，进度见事件流）') {
  try { consoleMsg('执行中…'); await fn(); consoleMsg(okText, 'ok'); }
  catch (e) { consoleMsgErr(e); }
}

/** `/api/runs` 的轮询节流：事件成串到达时没必要每个事件都打一次接口。 */
let runsFetchedAt = 0;
function refreshRunsThrottled() {
  const now = performance.now();
  if (now - runsFetchedAt < 3000) return;
  runsFetchedAt = now;
  refreshRuns();
}

function onStore(evt) {
  if (!document.getElementById('events')) return;   // 页面已切走
  switch (evt.type) {
    case 'workflow':
      renderHeader(); renderProgress(); renderSteps(); renderCheckpoint();
      break;
    case 'workflows':
      renderPicker();
      break;
    case 'event':
      appendEvent(evt.event);
      if (evt.event._custom) renderAuditPanelInto();
      refreshRunsThrottled();
      break;
    case 'events-reset':
      renderEventsFull();
      renderAuditPanelInto();
      break;
    default:
      break;
  }
}

// ---------------------------------------------------------------- 选择器 / 头部

function renderPicker() {
  const sel = $id('wfPicker');
  if (!sel) return;
  const list = state.workflows || [];
  sel.innerHTML = `<option value="">— 选择工作流（${list.length}）—</option>`
    + list.map((w) => `<option value="${esc(w.id)}">${esc(w.title)} · ${esc(w.template)}</option>`).join('');
  sel.value = state.workflowId || '';
}

function renderHeader() {
  const el = $id('wfHeader');
  if (!el) return;
  const w = state.workflow;
  if (!w) { el.className = 'empty'; el.textContent = '尚未选择工作流'; return; }
  el.className = 'pad';
  el.innerHTML = `
    <div style="font-weight:600">${esc(w.title)}</div>
    <div class="meta" style="padding:4px 0 0">
      ${esc(labelOf({ template: w.template, display_name: w.template }))}
      <span class="mono">${esc(w.template)}</span>
      · ${esc(WORKFLOW_STATUS[w.status] || w.status)}
      ${w.page_advisory ? `· 页数参考 ${w.page_advisory}（advisory）` : '· 页数不限'}
      · 检查点${w.steps?.some((s) => s.has_checkpoint) ? '已启用' : '未启用'}
    </div>
    <div class="mono" style="color:var(--dim)">${esc(w.id)}</div>`;
}

function renderProgress() {
  const el = $id('progressKpis');
  if (!el) return;
  const w = state.workflow;
  if (!w) { el.innerHTML = '<div class="empty">未选择工作流</div>'; return; }
  const p = workflowProgress(w);
  const failed = (w.steps || []).filter((s) => s.status === 'failed').length;
  el.innerHTML = `
    <div class="kpi"><div class="v">${p.done}/${p.total}</div><div class="l">已完成步骤</div></div>
    <div class="kpi"><div class="v">${p.pct}%</div><div class="l">完成度</div></div>
    <div class="kpi"><div class="v" style="color:${failed ? 'var(--err)' : 'inherit'}">${failed}</div>
      <div class="l">失败步骤</div></div>
    <div class="kpi"><div class="v">${w.page_advisory ?? '∞'}</div><div class="l">页数参考</div></div>`;
}

// ---------------------------------------------------------------- 步骤 / 检查点

function renderSteps() {
  const el = $id('stepList');
  if (!el) return;
  const steps = state.steps || [];
  $id('stepCount').textContent = `${steps.length} 步`;
  if (!steps.length) { el.innerHTML = '<div class="empty">无步骤</div>'; return; }

  el.innerHTML = steps.map((s) => {
    const busy = s.status === 'running';
    return `<div class="step" data-skill="${esc(s.skill_name)}">
      <div class="dot ${esc(s.status)}"></div>
      <div style="min-width:0">
        <div class="name">${esc(s.display_name)}</div>
        <div class="sub">${esc(s.skill_name)} · ${esc(STEP_STATUS[s.status] || s.status)}
          ${s.has_checkpoint ? `· 检查点:${esc(s.checkpoint_type || '')}` : ''}</div>
        ${(s.output_files || []).length
          ? `<div class="sub">产出 ${esc((s.output_files || []).slice(0, 3).join('、'))}</div>` : ''}
        ${s.error_message
          ? `<div class="sub" style="color:var(--err)">${esc(truncate(s.error_message, 200))}</div>` : ''}
      </div>
      <div class="acts"></div>
    </div>`;
  }).join('');

  for (const node of Array.from(el.querySelectorAll('.step'))) {
    const step = steps.find((s) => s.skill_name === node.dataset.skill);
    const btn = document.createElement('button');
    btn.textContent = step.status === 'running' ? '执行中' : '执行';
    btn.disabled = step.status === 'running' || step.status === 'completed';
    btn.onclick = () => withMsg(async () => {
      await runStep(step.skill_name);
      renderProgress();
    });
    node.querySelector('.acts').appendChild(btn);
  }
}

function tickCheckpoint() {
  const el = $id('cpRemain');
  const cp = state.checkpoint;
  if (!el || !cp) return;
  if (state.checkpointDeadline == null) { el.textContent = '—'; return; }
  const left = Math.max(0, Math.round((state.checkpointDeadline - performance.now()) / 1000));
  el.textContent = left > 0 ? `${left} 秒` : '已到期（等待后端回收）';
}

function renderCheckpoint() {
  const el = $id('checkpointArea');
  if (!el) return;
  el.innerHTML = '';
  const cp = state.checkpoint;
  if (!cp) return;
  const d = document.createElement('div');
  d.className = 'ck';
  d.innerHTML = `
    <div class="hd">⏸ 需要确认：${esc(cp.step_name)}</div>
    <div style="font-size:12px;color:var(--dim)">
      类型 <span class="mono">${esc(cp.checkpoint_type)}</span>
      · 剩余等待 <span id="cpRemain">—</span>
      · checkpoint_id <span class="mono">${esc(String(cp.checkpoint_id ?? '').slice(0, 12))}</span>
    </div>
    <details style="margin-top:6px">
      <summary style="color:var(--dim);font-size:11px;cursor:pointer">检查点数据</summary>
      <div class="mono" style="color:var(--dim)">${esc(truncate(JSON.stringify(cp.data || {}), 600))}</div>
    </details>`;
  const row = document.createElement('div');
  row.className = 'row';
  row.style.marginTop = '8px';
  const mk = (text, action, cls) => {
    const b = document.createElement('button');
    b.textContent = text; b.className = cls;
    b.onclick = () => withMsg(async () => {
      await resolveCheckpoint(action);
      renderSteps(); renderProgress();
    }, action === 'approve' ? '已批准，工作流继续推进' : '已停在检查点（步骤标记完成，保持暂停）');
    return b;
  };
  row.append(mk('批准并继续', 'approve', 'ok'), mk('停在检查点', 'stop', 'stop'));
  d.appendChild(row);
  el.appendChild(d);
  tickCheckpoint();
}

// ---------------------------------------------------------------- 事件

function renderAuditPanelInto() {
  const el = $id('auditPanel');
  if (!el) return;
  el.innerHTML = renderAuditPanel(state.events);
  const counts = CUSTOM_KINDS.map(
    (k) => `${k} ${state.events.filter((e) => e.kind === k).length}`);
  $id('hookCount').textContent = counts.join(' · ');
}

function renderEventsFull() {
  const el = $id('events');
  if (!el) return;
  el.innerHTML = state.events.map(renderRow).join('');
  updateMeta();
  el.scrollTop = el.scrollHeight;
}

function appendEvent(ev) {
  const el = $id('events');
  if (!el) return;
  const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  el.insertAdjacentHTML('beforeend', renderRow(ev));
  if (nearBottom) el.scrollTop = el.scrollHeight;
  updateMeta();
}

function updateMeta() {
  const el = $id('evMeta');
  if (!el) return;
  el.textContent = streamMeta(state.events)
    + (state.replayAllMessages ? '｜范围：全部步骤' : '｜范围：最近一条任务');
  $id('evCount').textContent = `${state.events.length} 条`;
}

// ---------------------------------------------------------------- 后台任务

async function refreshRuns() {
  const box = $id('runsBox');
  if (!box) return;
  try {
    const r = await getJSON('/api/runs');
    const list = r.active || [];
    box.innerHTML = list.length
      ? list.map((x) => `<div class="mono" style="color:var(--dim)">
          ${esc(x.workflow_id?.slice(0, 12) || '')} ${esc(x.skill_name || '')}
          ${x.started_at ? `· ${esc(fmtTs(x.started_at))}` : ''}</div>`).join('')
      : '<span class="empty">无正在运行的后台任务</span>';
  } catch (e) {
    box.innerHTML = `<span class="empty">查询失败：${esc(e.message)}</span>`;
  }
}
