/**
 * 页面 5／5：运行时与工具。
 *
 * 两个数据源，都是"如实声明"型接口（宁可暴露短板，也不让约束静默失效）：
 *   - `GET /api/runtimes`   —— agent 运行时及其能力矩阵
 *   - `GET /api/tex-runtime` —— TeX 运行时**三态**：ready / fresh / missing
 *
 * TeX 三态为什么要一眼可辨：`fresh`（随包 MiKTeX 未初始化）与 `missing`（没装）
 * 的**表现完全不同**——前者编译到一半才报 setup，后者一上来就找不到可执行文件；
 * 而二者都会让"编译步失败"。这一页先把它们分开显示，避免把 `fresh` 当成 `missing`
 * 去重装一套 TeX。
 */

import { $id, esc, pill, fmtTs } from '../lib/dom.js';
import { getJSON } from '../lib/api.js';
import { state, loadRuntimes, loadTexRuntime } from '../lib/store.js';

export const id = 'runtime';
export const hash = '#/runtime';
export const label = '运行时与工具';

let cleanup = null;
let timer = null;

const TEX_STATE = {
  ready: { tone: 'ok', zh: '可用', hint: 'xelatex 探测通过（用一篇 xeCJK 极小文档实测，不是只看 --version）。可直接编译中文 PDF。' },
  fresh: { tone: 'warn', zh: '未初始化', hint: '随包 TeX 存在但尚未完成首次 setup。直接编译会在中途要求安装/初始化，编译步会失败。' },
  missing: { tone: 'bad', zh: '未找到', hint: '本机与随包目录都没有可用的 xelatex；编译步必然失败，LaTeX 导出只能产出 .tex。' },
  unknown: { tone: 'dim', zh: '未知', hint: '状态查询失败，见下方说明。' },
};

/** 能力字段 → 中文标签（缺失时提示用）。 */
const CAP_LABELS = {
  streaming: '流式输出',
  session_resume: '会话续跑',
  model_selection: '模型选择',
  tool_allowlist: '工具白名单',
  tool_denylist: '工具黑名单',
  mcp_pinning: 'MCP 固定',
  budget_limit: '预算上限',
  structured_output: '结构化输出',
  extra_dirs: '附加目录',
  skip_ambient_config: '跳过环境配置',
  model_fallback: '模型回退',
};

export function render(root) {
  root.innerHTML = `
  <div class="page grid-2w">
    <section>
      <h2>TeX 运行时 <span class="count" id="texState"></span></h2>
      <div id="texBox"><div class="empty">检测中…</div></div>

      <h2 style="border-top:1px solid var(--line)">运行时能力</h2>
      <div class="pad" id="rtBox"><div class="empty">检测中…</div></div>
    </section>

    <section>
      <h2>后台任务与健康</h2>
      <div class="pad stack" id="opsBox"><div class="empty">…</div></div>
      <div class="pad">
        <button id="refreshBtn">重新检测</button>
      </div>
      <h2 style="border-top:1px solid var(--line)">宿主信息</h2>
      <div class="pad" id="hostBox"></div>
    </section>
  </div>`;

  $id('refreshBtn').onclick = () => reload(true);
  cleanup = () => {};
  reload(false);
  timer = setInterval(refreshOps, 15000);
  return () => { if (cleanup) cleanup(); if (timer) { clearInterval(timer); timer = null; } };
}

export function unmount() {
  if (cleanup) { cleanup(); cleanup = null; }
  if (timer) { clearInterval(timer); timer = null; }
}

async function reload(force) {
  await Promise.all([
    loadTexRuntime(force).then(paintTex).catch((e) => { $id('texBox').innerHTML = errBox(e.message); }),
    loadRuntimes(force).then(paintRuntimes).catch((e) => { $id('rtBox').innerHTML = errBox(e.message); }),
  ]);
  paintHost();
  refreshOps();
}

const errBox = (m) => `<div class="banner err"><div class="t">✕ 检测失败</div>
  <div class="body">${esc(m)}</div></div>`;

function paintTex(tex) {
  const s = TEX_STATE[tex.state] || TEX_STATE.unknown;
  $id('texState').innerHTML = pill(s.zh, s.tone);
  $id('texBox').innerHTML = `
    <div class="banner ${s.tone === 'dim' ? '' : s.tone}">
      <div class="t">${s.tone === 'ok' ? '✓' : s.tone === 'bad' ? '✕' : '⚠'} TeX 运行时：${esc(tex.state ?? 'unknown')}（${esc(s.zh)}）</div>
      <div class="body">${esc(s.hint)}</div>
      <div class="body" style="color:var(--dim)">${esc(tex.note || '')}</div>
    </div>
    <table class="tbl"><tbody>
      <tr><th style="width:34%">xelatex</th><td class="mono">${esc(tex.xelatex || '未找到')}</td></tr>
      <tr><th>latexmk</th><td class="mono">${esc(tex.latexmk || '未找到')}</td></tr>
      <tr><th>root</th><td class="mono">${esc(tex.root || '—')}</td></tr>
      <tr><th>随包安装器</th><td>${tex.installer_available
        ? pill('存在（可完成 setup）', 'ok') : pill('不存在', 'dim')}</td></tr>
    </tbody></table>
    ${(tex.warnings || []).length
      ? `<div class="warnbox" style="margin:10px 0 0">${tex.warnings.map(esc).join('<br/>')}</div>` : ''}`;
}

function paintRuntimes(r) {
  const raw = r.runtimes || [];
  // 注册表里同名运行时会以"连字符/下划线别名"各注册一次（`claude-code` 与
  // `claude_code`），display 名相同。这里按能力里的 `name` 去重展示，但把
  // 别名一并列出来——静默合并会让人以为少了一个运行时。
  const byName = new Map();
  for (const x of raw) {
    const key = (x.capabilities && x.capabilities.name) || x.runtime;
    if (!byName.has(key)) byName.set(key, { display: key, entries: [] });
    byName.get(key).entries.push(x);
  }
  const priority = r.default_priority || [];
  const cards = Array.from(byName.values()).map(({ display, entries }) => {
    const e = entries[0];
    if (e.error) {
      return `<div class="card"><div class="hd">${esc(display)} ${pill('适配器错误', 'bad')}</div>
        <div class="d mono" style="color:var(--err)">${esc(e.error)}</div></div>`;
    }
    const caps = e.capabilities || {};
    const missing = Object.entries(caps)
      .filter(([k, v]) => v === false && CAP_LABELS[k])
      .map(([k]) => CAP_LABELS[k]);
    const aliases = entries.map((x) => x.runtime);
    const rank = priority.indexOf(display);
    return `<div class="card" style="margin-bottom:8px">
      <div class="hd">${esc(display)}
        ${e.available ? pill('可用', 'ok') : pill('不可用', 'bad')}
        ${rank >= 0 ? pill(`优先级 #${rank + 1}`, 'dim') : ''}</div>
      <div class="d" style="color:var(--dim);font-size:11px">
        注册名：${aliases.map((a) => `<code>${esc(a)}</code>`).join(' / ')}
        ${entries.length > 1 ? `（${entries.length} 个别名，按能力名去重展示）` : ''}
      </div>
      <div style="margin-top:4px">
        ${missing.length
          ? `<span class="chip warn">不支持 ${missing.length} 项</span>
             <span style="font-size:11px;color:var(--dim)">：${missing.map(esc).join('、')}</span>`
          : `<span class="chip ok">能力齐备</span>`}
      </div>
      <table class="tbl" style="margin-top:6px"><tbody>
        <tr><th style="width:34%">权限模式</th><td class="mono">${esc((caps.permission_modes || []).join(' / ') || '—')}</td></tr>
        <tr><th>思考强度</th><td class="mono">${esc((caps.effort_levels || []).join(' / ') || '—')}</td></tr>
      </tbody></table>
    </div>`;
  });
  $id('rtBox').innerHTML = cards.join('')
    || '<div class="empty">没有任何注册的运行时</div>';
}

function paintHost() {
  const el = $id('hostBox');
  if (!el) return;
  el.innerHTML = `<table class="tbl"><tbody>
      <tr><th style="width:34%">页面 URL</th><td class="mono">${esc(location.href)}</td></tr>
      <tr><th>WebSocket</th><td>${state.wsConnected ? pill('已连接', 'ok') : pill('未连接', 'dim')}</td></tr>
      <tr><th>当前工作流</th><td class="mono">${esc(state.workflowId || '未选择')}</td></tr>
      <tr><th>工作区</th><td class="mono">${esc(state.workspace)}</td></tr>
      <tr><th>模板缓存</th><td>${state.templates ? `${state.templates.length} 个` : '未加载'}</td></tr>
    </tbody></table>`;
}

async function refreshOps() {
  const el = $id('opsBox');
  if (!el) return;
  try {
    const [runs, health] = await Promise.all([
      getJSON('/api/runs'),
      getJSON('/api/health'),
    ]);
    const active = runs.active || [];
    el.innerHTML = `
      <div class="kpis">
        <div class="kpi"><div class="v" style="color:${active.length ? 'var(--run)' : 'inherit'}">${active.length}</div>
          <div class="l">正在运行的后台任务</div></div>
        <div class="kpi"><div class="v">${health.ok ? '✓' : '✕'}</div>
          <div class="l">/api/health</div></div>
      </div>
      ${active.length ? `<div class="card">${active.map((x) => `<div class="mono" style="color:var(--dim)">
          ${esc(x.workflow_id?.slice(0, 12) || '')} · ${esc(x.skill_name || '')}
          ${x.started_at ? `· 自 ${esc(fmtTs(x.started_at))}` : ''}</div>`).join('')}</div>`
        : '<div class="empty">无后台任务</div>'}`;
  } catch (e) {
    el.innerHTML = `<div class="empty">查询失败：${esc(e.message)}</div>`;
  }
}
