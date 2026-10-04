/**
 * 页面 1／5：工作流（列表 + 新建 + 模板目录）。
 *
 * 相对骨架版的两处增强：
 *   1. 模板下拉走 `/api/templates`（**35 个**，不是枚举的 9 个），
 *      并按"竞赛 / 学术与科研"分组，显示 `display_name`、步数、页数参考、
 *      英文与"需 AI 申报"标记；
 *   2. 右侧补一张**模板目录表**——下拉只能看到选中的那一条，
 *      而"总共 35 个模板"这件事应该一眼可见。
 */

import { $id, esc, pill, WORKFLOW_STATUS } from '../lib/dom.js';
import { groupedOptions, labelOf } from '../lib/labels.js';
import {
  state, subscribe, refreshWorkflows, loadTemplates, createWorkflow, deleteWorkflow,
  workflowProgress,
} from '../lib/store.js';

export const id = 'workflows';
export const hash = '#/workflows';
export const label = '工作流';

let cleanup = null;

export function render(root) {
  root.innerHTML = `
  <div class="page grid-2">
    <section>
      <h2>工作流 <span class="count" id="wfCount"></span></h2>
      <div class="pad stack">
        <input id="title" placeholder="标题，如 2026 国赛 A 题" />
        <select id="template"></select>
        <label class="inline">
          <input type="checkbox" id="checkpoints" checked />
          启用检查点（每步人工确认）
        </label>
        <div class="row">
          <button class="primary" id="createBtn">新建</button>
          <button id="refreshBtn" class="ghost">刷新</button>
        </div>
        <div id="createMsg" class="meta" style="padding:0"></div>
      </div>
      <div class="pad" style="padding-top:0">
        <input id="filter" placeholder="过滤：标题 / 模板 / 状态" />
      </div>
      <div id="wfList"><div class="empty">加载中…</div></div>
    </section>

    <section>
      <h2>模板目录 <span class="count" id="tplCount">…</span></h2>
      <div class="meta" id="tplMeta"></div>
      <div id="tplList"></div>
    </section>
  </div>`;

  const offs = [];
  offs.push(subscribe(onStore));

  $id('createBtn').onclick = onCreate;
  $id('refreshBtn').onclick = () => refreshWorkflows().catch(reportErr);
  $id('filter').oninput = renderList;
  $id('template').onchange = () => {
    highlightTemplate($id('template').value);
  };

  loadTemplates().then(renderTemplates).catch(reportErr);
  refreshWorkflows().then(() => { renderList(); }).catch(reportErr);

  cleanup = () => offs.forEach((f) => f());
  return cleanup;
}

export function unmount() {
  if (cleanup) { cleanup(); cleanup = null; }
}

function reportErr(e) {
  const el = $id('createMsg');
  if (el) el.innerHTML = `<span style="color:var(--err)">${esc(e.message)}</span>`;
}

function onStore(evt) {
  if (!document.getElementById('wfList')) return;   // 已切走
  if (evt.type === 'workflows') renderList();
  if (evt.type === 'templates') renderTemplates(evt.templates);
  if (evt.type === 'select' || evt.type === 'workflow') renderList();
}

// ---------------------------------------------------------------- 模板

function renderTemplates(templates) {
  const tpls = templates || state.templates || [];
  const sel = $id('template');
  if (!sel) return;
  const prev = sel.value;
  sel.innerHTML = groupedOptions(tpls).map((g) => `
    <optgroup label="${esc(g.group)}">
      ${g.items.map((it) => `<option value="${esc(it.value)}">${esc(it.text)}</option>`).join('')}
    </optgroup>`).join('');
  if (prev && tpls.some((t) => t.template === prev)) sel.value = prev;

  $id('tplCount').textContent = `${tpls.length} 个`;
  const withPages = tpls.filter((t) => t.page_advisory).length;
  const ai = tpls.filter((t) => t.requires_ai_disclosure).length;
  $id('tplMeta').innerHTML =
    `来源 <code>/api/templates</code>（模板注册表，非枚举）｜`
    + `${withPages} 个带页数参考，${tpls.length - withPages} 个不限页｜`
    + `${ai} 个需 AI 使用申报`;

  $id('tplList').innerHTML = `
    <table class="tbl">
      <thead><tr><th>模板</th><th>步数</th><th>页数参考</th><th>标记</th></tr></thead>
      <tbody>
      ${tpls.map((t) => `
        <tr data-template="${esc(t.template)}" style="cursor:pointer">
          <td><div style="font-weight:600">${esc(labelOf(t))}</div>
              <div class="mono" style="color:var(--dim)">${esc(t.template)}</div></td>
          <td class="num">${t.step_count}</td>
          <td class="num">${t.page_advisory ?? '不限'}</td>
          <td>${t.requires_ai_disclosure ? pill('需 AI 申报', 'warn') : ''}
              ${String(t.page_rule_mode || '') === 'advisory_max' ? pill('advisory', 'dim') : ''}</td>
        </tr>`).join('')}
      </tbody>
    </table>`;
  for (const tr of Array.from($id('tplList').querySelectorAll('tr[data-template]'))) {
    tr.onclick = () => {
      sel.value = tr.dataset.template;
      highlightTemplate(tr.dataset.template);
      sel.focus();
    };
  }
  highlightTemplate(sel.value);
}

function highlightTemplate(value) {
  const list = $id('tplList');
  if (!list) return;
  for (const tr of Array.from(list.querySelectorAll('tr[data-template]'))) {
    const on = tr.dataset.template === value;
    tr.style.background = on ? 'var(--panel2)' : '';
    tr.style.borderLeft = on ? '3px solid var(--accent)' : '';
  }
}

// ---------------------------------------------------------------- 列表

function renderList() {
  const el = $id('wfList');
  if (!el) return;
  const kw = ($id('filter')?.value || '').trim().toLowerCase();
  const all = state.workflows || [];
  const list = kw
    ? all.filter((w) => `${w.title} ${w.template} ${w.status}`.toLowerCase().includes(kw))
    : all;
  $id('wfCount').textContent = `${all.length} 条`;

  if (!list.length) {
    el.innerHTML = `<div class="empty">${all.length ? '没有匹配的工作流' : '暂无工作流，先在左上新建一个'}</div>`;
    return;
  }
  el.innerHTML = list.map((w) => {
    const p = workflowProgress(w);
    const active = w.id === state.workflowId;
    return `<div class="wf${active ? ' active' : ''}" data-id="${esc(w.id)}">
      <div class="t">${esc(w.title)}
        <button class="del" data-del="${esc(w.id)}" title="删除工作流">✕</button></div>
      <div class="m">${esc(labelOf({ template: w.template, display_name: w.template }))}
        · ${esc(WORKFLOW_STATUS[w.status] || w.status)} · ${p.done}/${p.total} 步
        ${w.page_advisory ? `· 页数参考 ${w.page_advisory}` : ''}</div>
      <div class="mono" style="color:var(--dim);margin-top:2px">${esc(w.id.slice(0, 12))}…</div>
    </div>`;
  }).join('');

  for (const node of Array.from(el.querySelectorAll('.wf'))) {
    node.onclick = (e) => {
      if (e.target.closest('[data-del]')) return;
      location.hash = `#/detail/${node.dataset.id}`;
    };
  }
  for (const btn of Array.from(el.querySelectorAll('[data-del]'))) {
    btn.onclick = async (e) => {
      e.stopPropagation();
      const wfId = btn.dataset.del;
      if (!confirm(`删除工作流 ${wfId.slice(0, 12)}…？该操作不可撤销。`)) return;
      try { await deleteWorkflow(wfId); } catch (err) { reportErr(err); }
    };
  }
}

// ---------------------------------------------------------------- 新建

async function onCreate() {
  const btn = $id('createBtn');
  const title = ($id('title').value || '').trim() || '未命名';
  const template = $id('template').value;
  if (!template) { reportErr(new Error('模板清单未就绪，请稍后重试')); return; }
  btn.disabled = true;
  $id('createMsg').textContent = '创建中…';
  try {
    const w = await createWorkflow({
      template, title, enableCheckpoints: $id('checkpoints').checked,
    });
    $id('title').value = '';
    $id('createMsg').innerHTML =
      `<span style="color:var(--ok)">已创建 ${esc(w.id.slice(0, 12))}…（${esc(w.steps.length)} 步）</span>`;
    location.hash = `#/detail/${w.id}`;
  } catch (e) {
    reportErr(e);
  } finally {
    btn.disabled = false;
  }
}
