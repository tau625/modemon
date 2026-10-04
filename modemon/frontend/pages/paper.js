/**
 * 页面 3／5：成文预览（论文装配 / 导出）。
 *
 * ★ 本页最重要的一条：**`ok=false` 必须醒目报错。**
 *
 * 项目的历史教训是"失败被显示成成功"——导出接口即使在正文为空、
 * TeX 编译失败、DOCX 写盘失败时也会返回 **HTTP 200 + `ok:false`**，
 * 只按 HTTP 状态判定就会把一份空论文显示成"导出成功"。
 * 因此这里的判定顺序是：
 *   1. 请求本身失败（非 2xx / 网络）→ 红色错误条（含后端 `code` 与诊断编号）；
 *   2. 请求成功但 `ok !== true` → **同样红色**，逐格式列出 `error` / `compile_error` / `notes`；
 *   3. 只有 `ok === true` 才显示绿色成功。
 */

import { $id, esc, pill, fmtBytes, truncate } from '../lib/dom.js';
import { groupedOptions, langOf } from '../lib/labels.js';
import { getJSON, postJSON, qs } from '../lib/api.js';
import { state, loadTemplates, loadTexRuntime } from '../lib/store.js';

export const id = 'paper';
export const hash = '#/paper';
export const label = '成文预览';

let cleanup = null;

export function render(root) {
  root.innerHTML = `
  <div class="page grid-2b">
    <section>
      <h2>导出参数</h2>
      <div class="pad stack">
        <label class="field">工作区绝对路径
          <input id="ws" placeholder="E:\\modemon-ws\\demo" />
        </label>
        <label class="field">模板
          <select id="template"></select>
        </label>
        <label class="field">论文标题（留空则由正文首行推断）
          <input id="title" placeholder="例如：基于 XGBoost 的 …" />
        </label>
        <label class="field">摘要（留空则不注入）
          <textarea id="abstract" rows="4" placeholder="摘要正文…"></textarea>
        </label>
        <label class="field">关键词（逗号分隔）
          <input id="keywords" placeholder="数学建模, 优化, 灵敏度分析" />
        </label>
        <div class="row wrap">
          <label class="inline"><input type="checkbox" id="fmtLatex" checked /> LaTeX</label>
          <label class="inline"><input type="checkbox" id="fmtDocx" checked /> Word</label>
          <label class="inline"><input type="checkbox" id="compilePdf" checked /> 编译 PDF</label>
        </div>
        <div class="meta" style="padding:0">TeX 运行时：<span id="texChip"></span></div>
        <div class="row">
          <button class="primary" id="exportBtn">装配并导出</button>
          <button id="lintBtn">论文体检</button>
        </div>
        <div class="meta" style="padding:0">
          表格由程序从 <code>figures/all_results.json</code> 生成，不经过模型——
          论文里的数字错了就是硬伤。
        </div>
      </div>
    </section>

    <section>
      <h2>导出结果</h2>
      <div id="result"><div class="empty">尚未导出。填好工作区后点「装配并导出」。</div></div>
    </section>
  </div>`;

  $id('ws').value = state.workspace;
  $id('ws').onchange = (e) => { state.workspace = e.target.value.trim(); };
  $id('exportBtn').onclick = () => doExport();
  $id('lintBtn').onclick = () => doLint();

  loadTemplates().then((tpls) => {
    const sel = $id('template');
    sel.innerHTML = groupedOptions(tpls).map((g) => `<optgroup label="${esc(g.group)}">`
      + g.items.map((it) => `<option value="${esc(it.value)}">${esc(it.text)}</option>`).join('')
      + '</optgroup>').join('');
    sel.value = tpls.some((t) => t.template === 'comp_cumcm') ? 'comp_cumcm' : (tpls[0]?.template || '');
    sel.onchange = () => paintTex();
  }).catch((e) => showError(e.message, ''));

  paintTex();
  cleanup = () => {};
  return cleanup;
}

export function unmount() { if (cleanup) { cleanup(); cleanup = null; } }

async function paintTex() {
  const el = $id('texChip');
  if (!el) return;
  const tex = await loadTexRuntime();
  const tone = { ready: 'ok', fresh: 'warn', missing: 'bad' }[tex.state] || 'dim';
  const zh = { ready: '可用', fresh: '未初始化（需先完成 setup）', missing: '未找到' }[tex.state] || tex.state;
  el.innerHTML = `${pill(zh, tone)} <span class="mono">${esc(tex.xelatex || tex.note || '')}</span>`;
}

function showError(msg, code) {
  const el = $id('result');
  if (!el) return;
  el.innerHTML = `
    <div class="banner err">
      <div class="t">✕ 请求失败</div>
      <div class="body">${esc(msg)}</div>
      ${code ? `<div class="body"><code>code=${esc(code)}</code></div>` : ''}
      <div class="body" style="color:var(--dim)">
        这是"请求没成功"，与"导出成功但结果不合格"是两回事，两者都不会被显示成成功。
      </div>
    </div>`;
}

// ---------------------------------------------------------------- 导出

async function doExport() {
  const btn = $id('exportBtn');
  const workspace = ($id('ws').value || '').trim();
  if (!workspace) { showError('请先填写工作区绝对路径', ''); return; }
  const formats = [];
  if ($id('fmtLatex').checked) formats.push('latex');
  if ($id('fmtDocx').checked) formats.push('docx');
  if (!formats.length) { showError('至少勾选一种导出格式', ''); return; }

  const body = {
    workspace,
    template: $id('template').value,
    language: langOf({ template: $id('template').value }),
    title: $id('title').value.trim(),
    abstract: $id('abstract').value.trim(),
    keywords: ($id('keywords').value || '').split(',').map((s) => s.trim()).filter(Boolean),
    formats,
    compile_pdf: $id('compilePdf').checked,
  };

  btn.disabled = true;
  $id('result').innerHTML = `<div class="empty">导出中…（TeX 编译可能耗时较久）</div>`;
  try {
    const r = await postJSON('/api/paper/export', body);
    renderResult(r, body);
  } catch (e) {
    showError(e.message, e.code);
  } finally {
    btn.disabled = false;
  }
}

function renderResult(r, body) {
  const el = $id('result');
  const results = r.results || {};
  const latex = results.latex || null;
  const docx = results.docx || null;
  const ok = r.ok === true;

  // ---- 顶部横幅：**只有 ok===true 才是成功** ----
  let banner;
  if (ok) {
    const pages = latex?.pages;
    banner = `<div class="banner ok">
      <div class="t">✓ 导出成功</div>
      <div class="body">模板 ${esc(r.template || body.template)}
        ${latex?.pdf ? `· PDF <code>${esc(latex.pdf)}</code>` : ''}
        ${pages != null ? `· ${pages} 页` : ''}
        ${docx?.docx ? `· DOCX <code>${esc(docx.docx)}</code>` : ''}
      </div>
    </div>`;
  } else {
    const reasons = [];
    if (!Object.keys(results).length) reasons.push('没有任何格式产出（formats 为空或全部失败）');
    if (latex && latex.ok !== true) {
      reasons.push(`LaTeX 失败：${latex.error || latex.compile_error || '未知原因'}`);
    }
    if (docx && docx.ok !== true) reasons.push(`Word 失败：${docx.error || '未知原因'}`);
    if (latex && latex.ok === true && docx && docx.ok === true) {
      reasons.push('各格式均返回 ok，但整体仍为 ok=false（见下方原始响应）');
    }
    banner = `<div class="banner err">
      <div class="t">✕ 导出失败（ok=false）</div>
      <div class="body">本次<strong>没有</strong>产出可直接提交的论文。HTTP 200 不代表成功——
        判定依据是响应体里的 <code>ok</code> 字段。</div>
      <ul style="margin:6px 0 0 18px;color:#ffb4ae">
        ${reasons.map((x) => `<li>${esc(x)}</li>`).join('')}
      </ul>
      <div class="body" style="color:var(--dim)">工作区 <code>${esc(r.workspace || body.workspace)}</code></div>
    </div>`;
  }

  const latexCard = latex ? card('LaTeX', [
    ['ok', pill(String(latex.ok), latex.ok === true ? 'ok' : 'bad')],
    ['tex', latex.tex ? `<code>${esc(latex.tex)}</code>` : '—'],
    ['pdf', latex.pdf ? `<code>${esc(latex.pdf)}</code>` : '—'],
    ['页数 pages', latex.pages ?? '—'],
    ['compile_error', latex.compile_error
      ? `<span style="color:var(--err)">${esc(truncate(latex.compile_error, 400))}</span>` : '（无）'],
    ['error', latex.error
      ? `<span style="color:var(--err)">${esc(latex.error)}</span>` : '（无）'],
  ], latex) : '';

  const docxCard = docx ? card('Word', [
    ['ok', pill(String(docx.ok), docx.ok === true ? 'ok' : 'bad')],
    ['docx', docx.docx ? `<code>${esc(docx.docx)}</code>` : '—'],
    ['大小', fmtBytes(docx.bytes)],
    ['章节 / 表格 / 图 / 参考文献',
      `${docx.sections ?? '-'} / ${docx.tables ?? '-'} / ${docx.figures ?? '-'} / ${docx.references ?? '-'}`],
  ], docx) : '';

  el.innerHTML = banner
    + `<div class="pad stack">
         ${latexCard}${docxCard}
         ${!latex && !docx ? '<div class="empty">响应里没有任何格式结果</div>' : ''}
         <details class="card">
           <summary style="cursor:pointer;color:var(--dim);font-size:12px">原始响应（诊断用）</summary>
           <pre class="mono" style="white-space:pre-wrap;color:var(--dim)">${esc(JSON.stringify(r, null, 1))}</pre>
         </details>
       </div>`;
}

/** 单格式卡片：字段表 + `notes` + 页数预算（`budget`）。 */
function card(title, rows, raw) {
  const notes = raw.notes || [];
  const b = raw.budget || null;
  const budgetRows = b ? [
    ['正文字数', b.body_chars ?? '—'],
    ['每页字数', b.chars_per_page ?? '—'],
    ['估算页数', b.estimated_pages ?? '—'],
    ['页数上限', b.limit ?? '不限'],
    ['超限', b.over_limit === true
      ? `<span style="color:var(--warn)">超出 ${b.over_by ?? 0} 页</span>` : '否'],
  ] : [];
  return `<div class="card">
    <div class="hd">${esc(title)}
      ${raw.ok === true ? pill('ok', 'ok') : pill('未成功', 'bad')}
      ${b?.advisory ? pill('页数 advisory', 'dim') : ''}</div>
    <table class="tbl">
      <tbody>${rows.map(([k, v]) => `<tr><th style="width:120px">${esc(k)}</th><td>${v}</td></tr>`).join('')}</tbody>
    </table>
    ${budgetRows.length ? `<div style="margin-top:8px;font-weight:600">页数预算</div>
      <table class="tbl"><tbody>
      ${budgetRows.map(([k, v]) => `<tr><th style="width:120px">${esc(k)}</th><td>${v}</td></tr>`).join('')}
      </tbody></table>` : ''}
    ${notes.length ? `<div style="margin-top:8px;font-weight:600">notes（${notes.length}）</div>
      <ul>${notes.map((n) => `<li>${esc(n)}</li>`).join('')}</ul>` : ''}
    ${raw.log_tail ? `<details style="margin-top:6px">
      <summary style="cursor:pointer;color:var(--dim);font-size:11px">编译日志尾部</summary>
      <pre class="mono" style="white-space:pre-wrap;color:var(--dim)">${esc(truncate(raw.log_tail, 2000))}</pre>
      </details>` : ''}
  </div>`;
}

// ---------------------------------------------------------------- 体检

async function doLint() {
  const workspace = ($id('ws').value || '').trim();
  if (!workspace) { showError('请先填写工作区绝对路径', ''); return; }
  const template = $id('template').value;
  $id('result').innerHTML = '<div class="empty">体检中…</div>';
  try {
    const r = await getJSON(`/api/paper/lint?${qs({ workspace, template })}`);
    const rows = (r.issues || []).map((i) => `<tr>
      <td>${i.severity === 'error' ? pill('error', 'bad') : pill(i.severity || 'warn', 'warn')}</td>
      <td class="mono">${esc(i.rule)}</td>
      <td>${esc(i.message)}</td>
      <td class="mono">${i.line ?? ''}</td>
      <td class="mono" style="color:var(--dim)">${esc(truncate(i.excerpt || '', 120))}</td></tr>`).join('');
    $id('result').innerHTML = `
      <div class="banner ${r.ok ? 'ok' : 'err'}">
        <div class="t">${r.ok ? '✓ 去 AI 味检查通过' : '✕ 去 AI 味检查未通过'}</div>
        <div class="body">error ${r.error_count ?? 0} · warn ${r.warn_count ?? 0}
          ${r.notes?.length ? `· notes ${r.notes.length}` : ''}</div>
      </div>
      <div class="pad stack">
        <table class="tbl">
          <thead><tr><th>级别</th><th>规则</th><th>说明</th><th>行</th><th>片段</th></tr></thead>
          <tbody>${rows || '<tr><td colspan="5" class="empty">无问题</td></tr>'}</tbody>
        </table>
        ${r.notes?.length ? `<div class="card"><div class="hd">notes</div>
          <ul>${r.notes.map((n) => `<li>${esc(String(n))}</li>`).join('')}</ul></div>` : ''}
      </div>`;
  } catch (e) {
    showError(e.message, e.code);
  }
}
