/**
 * modemon 前端壳：路由 + 顶栏 + 全局状态接线。
 *
 * 设计原则（后端测试 `test_collaboration.py::test_frontend_served` 会核对这一句）：
 * **WebSocket 只用于实时通知，状态一律以 REST 为准。**
 * 断线重连后通过 REST 全量回放事件，不依赖 WS 补发历史——
 * 这条规则来自蓝方的经验（"WS 只是通知，断线/重启后仍应完整显示"）。
 * 具体实现见 `lib/store.js`（WS 连接、退避重连、事件去重都在那里）。
 *
 * 为什么是 **hash 路由** 而不是多个 HTML 文件：
 *   - 切页不重新加载文档 ⇒ WebSocket 连接、"当前工作流"选择、事件缓冲都留着，
 *     否则每次点导航都要重连并重新回放事件；
 *   - 只有一个 shell，顶栏与徽标不必在 5 个文件里各写一遍（少一处漂移源）。
 *
 * 页面模块契约：
 *   `render(root, param)`  渲染进 <main>（返回清理函数由页面自行忽略）
 *   `unmount()`            路由切走时调用（清定时器/订阅）
 *
 * 仍然是**无构建步骤**：原生 ES module，浏览器直接跑。
 */

import { $id, esc, WORKFLOW_STATUS } from './lib/dom.js';
import {
  state, setRoute, subscribe, loadTemplates, loadRuntimes, loadTexRuntime,
  refreshWorkflows, workflowProgress,
} from './lib/store.js';

import * as workflows from './pages/workflows.js';
import * as detail from './pages/detail.js';
import * as paper from './pages/paper.js';
import * as typography from './pages/typography.js';
import * as runtime from './pages/runtime.js';

//: 路由表。key 即 `#/<key>`，detail 支持 `#/detail/<workflow_id>`。
const ROUTES = { workflows, detail, paper, typography, runtime };
const DEFAULT_ROUTE = 'workflows';

let current = null;          // 当前挂载的页面模块
let lastToken = null;        // 上一次渲染的路由标识（防同一路由重复挂载）

// ---------------------------------------------------------------- 路由解析

function parseHash() {
  const raw = (location.hash || '').replace(/^#\/?/, '');
  const [name, param] = raw.split('/');
  const key = ROUTES[name] ? name : DEFAULT_ROUTE;
  return { key, param: param ? decodeURIComponent(param) : null };
}

function paintNav(key) {
  for (const a of Array.from(document.querySelectorAll('#nav a'))) {
    a.classList.toggle('active', a.dataset.route === key);
  }
}

function handleRoute() {
  const { key, param } = parseHash();
  // 启动时会给空 hash 兜一个默认值，浏览器随后也会派发 hashchange；
  // 用 token 去重，避免同一路由被挂载两次（会打两遍接口、建两条 WS）。
  const token = `${key}/${param ?? ''}`;
  if (token === lastToken) return;
  lastToken = token;
  setRoute(key, param);

  // ES module 命名空间对象是不可扩展的，**不能**往模块上挂清理函数，
  // 所以清理职责统一交给各页面自己的 `unmount()`。
  if (current && current.unmount) {
    try { current.unmount(); } catch (e) { console.error(e); }
  }
  const root = $id('view');
  root.innerHTML = '';
  current = ROUTES[key];
  paintNav(key);
  document.title = `modemon · ${current.label}`;

  try {
    current.render(root, param);
  } catch (e) {
    console.error(e);
    root.innerHTML = `<div class="banner err"><div class="t">✕ 页面渲染失败</div>
      <div class="body">${esc(e.message)}</div>
      <div class="body" style="color:var(--dim)">模块 <code>${esc(key)}</code></div></div>`;
  }
}

// ---------------------------------------------------------------- 顶栏

function paintBadges() {
  const ws = $id('wsBadge');
  ws.textContent = state.wsConnected ? 'WebSocket 已连接' : 'WebSocket 未连接';
  ws.className = 'badge ' + (state.wsConnected ? 'on' : 'off');
  ws.title = state.workflowId ? `订阅 ${state.workflowId}` : '未选择工作流时不建立连接';

  const rt = $id('rtBadge');
  const rts = state.runtimes?.runtimes || null;
  if (state.tex) {
    const tone = { ready: 'on', fresh: 'warn', missing: 'off' }[state.tex.state] || '';
    const zh = { ready: 'TeX 可用', fresh: 'TeX 未初始化', missing: 'TeX 缺失' }[state.tex.state];
    rt.textContent = `${zh || 'TeX ' + state.tex.state}`
      + (rts ? ` · 运行时 ${new Set(rts.filter((x) => x.available).map((x) => x.runtime)).size} 个可用` : '');
    rt.className = `badge ${tone}`;
  } else if (rts) {
    const avail = new Set(rts.filter((x) => x.available).map((x) => x.runtime));
    rt.textContent = avail.size ? `运行时: ${Array.from(avail).join(', ')}` : '无可用运行时';
    rt.className = 'badge ' + (avail.size ? 'on' : 'off');
  } else {
    rt.textContent = '运行时检测中…';
    rt.className = 'badge';
  }

  const wf = $id('wfBadge');
  const w = state.workflow;
  if (w) {
    const p = workflowProgress(w);
    wf.textContent = `${w.title.slice(0, 16)} · ${WORKFLOW_STATUS[w.status] || w.status} · ${p.done}/${p.total}`;
    wf.className = 'badge on';
    wf.title = `${w.id}（点击进入执行详情）`;
  } else {
    wf.textContent = '未选择工作流';
    wf.className = 'badge';
    wf.title = '';
  }
}

function wireBadges() {
  $id('wfBadge').style.cursor = 'pointer';
  $id('wfBadge').onclick = () => {
    if (state.workflowId) location.hash = `#/detail/${state.workflowId}`;
    else location.hash = '#/workflows';
  };
  $id('rtBadge').style.cursor = 'pointer';
  $id('rtBadge').onclick = () => { location.hash = '#/runtime'; };
}

// ---------------------------------------------------------------- 启动

function boot() {
  wireBadges();
  subscribe((evt) => {
    if (['ws', 'workflow', 'workflows', 'runtimes', 'tex', 'select'].includes(evt.type)) {
      paintBadges();
    }
  });

  window.addEventListener('hashchange', handleRoute);

  // 页面级未捕获异常不该让整页白屏——顶部给一条可读的错误提示。
  window.addEventListener('error', (e) => reportFatal(e.message));
  window.addEventListener('unhandledrejection', (e) => reportFatal(e.reason?.message || String(e.reason)));

  // 全局只拉一次：模板（35 个）与运行时/TeX 状态（顶栏要用）
  loadTemplates().catch((e) => reportFatal(`模板加载失败：${e.message}`));
  loadRuntimes().then(paintBadges).catch(() => {});
  loadTexRuntime().then(paintBadges).catch(() => {});
  refreshWorkflows().catch(() => {});

  if (!location.hash) location.hash = `#/${DEFAULT_ROUTE}`;
  handleRoute();
  paintBadges();
}

function reportFatal(msg) {
  if (!msg) return;
  let node = $id('fatalBar');
  if (!node) {
    document.body.insertAdjacentHTML('afterbegin', '<div id="fatalBar"></div>');
    node = $id('fatalBar');
  }
  node.innerHTML = `<div style="padding:6px 16px;background:#2a1416;color:#ffb4ae;
    font-size:12px;border-bottom:1px solid var(--err)">
    前端异常：${esc(msg)}（页面其余功能可能仍可用）</div>`;
  window.setTimeout(() => { if (node) node.innerHTML = ''; }, 12000);
}

boot();
