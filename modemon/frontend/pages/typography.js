/**
 * 页面 4／5：排版规格。
 *
 * 数据源 `GET /api/typography/{template}`（返回该模板**实际使用**的规格，
 * 含 `source`：外部 JSON 覆盖还是内置恢复值）。
 *
 * 为什么要看这一页：论文的"字号/行距/缩进/页数上限"是评审的硬性观感项，
 * 而它们散落在 LaTeX 导出、Word 导出、页数预算三处。这里把它们**逐字**摊开，
 * 并配一份用同一批数值渲染的样例——数值对不对，一眼能看出来，
 * 比读 `{"body":{"line_spacing":1.5}}` 直观得多。
 */

import { $id, esc, pill } from '../lib/dom.js';
import { groupedOptions, labelOf, langOf } from '../lib/labels.js';
import { getJSON } from '../lib/api.js';
import { loadTemplates } from '../lib/store.js';
export const id = 'typography';
export const hash = '#/typography';
export const label = '排版规格';

let cleanup = null;

const SECTION_TITLES = {
  page: '页面与页边距',
  fonts: '字体',
  headings: '标题层级',
  body: '正文',
  title: '论文标题',
  table: '表格',
  references: '参考文献',
  image: '图片',
  code_block: '代码块',
  abstract: '摘要',
  keywords: '关键词',
};

export function render(root) {
  root.innerHTML = `
  <div class="page grid-2">
    <section>
      <h2>选择模板</h2>
      <div class="pad stack">
        <select id="template"></select>
        <div class="meta" style="padding:0" id="tplInfo"></div>
      </div>
      <h2>关键指标</h2>
      <div class="pad"><div class="kpis" id="kpis"><div class="empty">…</div></div></div>
      <h2>提示</h2>
      <div class="pad" id="warnings"><span class="empty">—</span></div>
    </section>

    <section>
      <h2>规格明细</h2>
      <div class="pad stack" id="detail"><div class="empty">选择模板后加载…</div></div>
      <h2 style="border-top:1px solid var(--line)">样例预览（用真实数值渲染）</h2>
      <div class="pad" id="preview"></div>
    </section>
  </div>`;

  loadTemplates().then((tpls) => {
    const sel = $id('template');
    sel.innerHTML = groupedOptions(tpls).map((g) => `<optgroup label="${esc(g.group)}">`
      + g.items.map((it) => `<option value="${esc(it.value)}">${esc(it.text)}</option>`).join('')
      + '</optgroup>').join('');
    const prefer = tpls.find((t) => t.template === 'comp_cumcm') ? 'comp_cumcm' : tpls[0]?.template;
    sel.value = prefer || '';
    sel.onchange = () => load(sel.value);
    load(sel.value);
  }).catch((e) => { $id('detail').innerHTML = errBox(e.message); });

  cleanup = () => {};
  return cleanup;
}

export function unmount() { if (cleanup) { cleanup(); cleanup = null; } }

const errBox = (m) => `<div class="banner err"><div class="t">✕ 加载失败</div>
  <div class="body">${esc(m)}</div></div>`;

async function load(template) {
  if (!template) return;
  $id('detail').innerHTML = '<div class="empty">加载中…</div>';
  try {
    const r = await getJSON(`/api/typography/${encodeURIComponent(template)}`);
    paint(template, r);
  } catch (e) {
    $id('detail').innerHTML = errBox(e.message);
    $id('kpis').innerHTML = '<div class="empty">—</div>';
    $id('preview').innerHTML = '';
  }
}

function paint(template, r) {
  const s = r.style || {};
  const en = langOf({ template }) === 'en';
  const perPage = en ? r.chars_per_page_en : r.chars_per_page_zh;

  $id('tplInfo').innerHTML =
    `${esc(labelOf({ template, display_name: template }))} <span class="mono">${esc(template)}</span>
     · 规格 <code>${esc(r.name)}</code>
     · 来源 ${pill(r.source === 'builtin' ? '内置恢复值' : r.source, r.source === 'builtin' ? 'dim' : 'warn')}`;

  $id('kpis').innerHTML = `
    <div class="kpi"><div class="v">${r.page_limit ?? '不限'}</div><div class="l">页数参考（advisory）</div></div>
    <div class="kpi"><div class="v">${perPage ?? '—'}</div>
      <div class="l">${en ? '英文词/页' : '中文字/页'}</div></div>
    <div class="kpi"><div class="v">${s.body?.font_size_pt ?? '—'} pt</div><div class="l">正文字号</div></div>
    <div class="kpi"><div class="v">${s.body?.line_spacing ?? '—'}</div><div class="l">正文行距</div></div>
    <div class="kpi"><div class="v">${s.body?.first_line_indent_chars ?? '—'} 字</div><div class="l">首行缩进</div></div>
    <div class="kpi"><div class="v">${r.page_limit && perPage
      ? Math.round(r.page_limit * perPage / 1000) + 'k' : '—'}</div>
      <div class="l">${r.page_limit ? `满页上限约 ${r.page_limit * perPage} 字` : '无上限'}</div></div>`;

  $id('warnings').innerHTML = (r.warnings || []).length
    ? `<div class="warnbox" style="margin:0">${r.warnings.map(esc).join('<br/>')}</div>`
    : '<span class="empty">无提示</span>';

  $id('detail').innerHTML = Object.entries(SECTION_TITLES)
    .filter(([k]) => s[k] && typeof s[k] === 'object')
    .map(([k, t]) => `<div class="card">
        <div class="hd">${esc(t)}</div>
        <table class="tbl"><tbody>
          ${Object.entries(s[k]).map(([kk, vv]) => `<tr>
            <th style="width:46%">${esc(kk)}</th>
            <td>${esc(typeof vv === 'object' ? JSON.stringify(vv) : String(vv))}</td>
          </tr>`).join('')}
        </tbody></table>
      </div>`).join('')
    + `<details class="card">
         <summary style="cursor:pointer;color:var(--dim);font-size:12px">原始响应</summary>
         <pre class="mono" style="white-space:pre-wrap;color:var(--dim)">${esc(JSON.stringify(r, null, 1))}</pre>
       </details>`;

  $id('preview').innerHTML = buildPreview(s, r, template);
}

/** 用真实规格数值渲染一段样例（字号 pt → px 按 96dpi 换算）。 */
function buildPreview(s, r, template) {
  const pt = (v, fallback) => `${Math.round((Number(v ?? fallback) || fallback) * 4 / 3)}px`;
  const body = s.body || {};
  const title = s.title || {};
  const h = s.headings || {};
  const fonts = s.fonts || {};
  const table = s.table || {};
  return `<div class="preview" style="
      margin:0;font-family:${esc(fonts.latin || 'Times New Roman')},serif;
      font-size:${pt(body.font_size_pt, 12)};line-height:${body.line_spacing || 1.5}">
    <div class="pv-title" style="
      font-size:${pt(title.font_size_pt, 18)};
      font-family:${esc(title.font_family || fonts.chinese_heading || 'SimHei')},sans-serif;
      font-weight:${title.bold === false ? 400 : 700};
      text-align:${esc(title.alignment || 'center')};
      margin:${title.space_before_pt ?? 12}pt 0 ${title.space_after_pt ?? 6}pt">
      样例论文标题
    </div>
    <div class="pv-h1" style="
      font-size:${pt(h.level1_pt, 15)};font-family:${esc(fonts.chinese_heading || 'SimHei')},sans-serif;
      text-align:${esc(h.level1_alignment || 'center')};margin:10px 0 6px">
      一、问题重述
    </div>
    <div class="pv-h1" style="
      font-size:${pt(h.level2_pt, 14)};font-family:${esc(fonts.chinese_heading || 'SimHei')},sans-serif;
      text-align:${esc(h.level2_alignment || 'left')};margin:8px 0 4px">
      1.1 背景
    </div>
    <div class="pv-body" style="text-indent:${body.first_line_indent_chars ?? 2}em;text-align:justify">
      正文样例：字号 ${body.font_size_pt ?? 12}pt、行距 ${body.line_spacing ?? 1.5}、
      首行缩进 ${body.first_line_indent_chars ?? 2} 字。字体族为
      ${esc(fonts.chinese_body || 'SimSun')}（中文）/ ${esc(fonts.latin || 'Times New Roman')}（西文）。
    </div>
    <table style="width:60%;margin:10px auto;border-collapse:collapse;font-size:${pt(table.font_size_pt, 10.5)}">
      <thead><tr>
        <th style="border-top:${table.top_border_pt ?? 1.5}pt solid #000;
                   border-bottom:${table.header_border_pt ?? 0.75}pt solid #000;
                   padding:3px 6px;text-align:${esc(table.cell_alignment || 'center')}">变量</th>
        <th style="border-top:${table.top_border_pt ?? 1.5}pt solid #000;
                   border-bottom:${table.header_border_pt ?? 0.75}pt solid #000;
                   padding:3px 6px;text-align:${esc(table.cell_alignment || 'center')}">取值</th>
      </tr></thead>
      <tbody><tr>
        <td style="border-bottom:${table.bottom_border_pt ?? 1.5}pt solid #000;padding:3px 6px;text-align:center">α</td>
        <td style="border-bottom:${table.bottom_border_pt ?? 1.5}pt solid #000;padding:3px 6px;text-align:center">0.05</td>
      </tr></tbody>
    </table>
    <div class="pv-caption">图 1　样例图注（图注字号与正文分离）</div>
    <div style="margin-top:8px;color:#555;font-size:11px">
      模板 <code>${esc(template)}</code> · 页数参考 ${r.page_limit ?? '不限'} ·
      ${esc(r.name)} · source=${esc(r.source)}
    </div>
  </div>`;
}
