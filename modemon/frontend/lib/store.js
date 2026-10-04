/**
 * 全局状态 + 订阅（无框架，最小实现）。
 *
 * 设计原则（沿用骨架版、也是蓝方的经验）：
 *
 *   **WebSocket 只用于实时通知，状态一律以 REST 为准。**
 *   断线重连后通过 REST 全量回放，不依赖 WS 补发历史。
 *
 * 页面模块**不直接改 DOM 状态**，而是订阅这里的事件重新渲染自己那一块。
 * 这样切换路由不会丢状态（当前工作流、事件缓冲、WS 连接都留在 store 里）。
 */

import { api, getJSON, postJSON } from './api.js';
import { customEventFromWs, eventKey, isCustom } from './events.js';

const LS_WORKSPACE = 'modemon.workspace';

export const state = {
  route: 'workflows',
  routeParam: null,
  /** 模板清单（35 个，来自 /api/templates）——工作流与排版页共用，只拉一次。 */
  templates: null,
  workflows: [],
  workflowId: null,
  workflow: null,
  steps: [],
  checkpoint: null,
  checkpointDeadline: null,     // performance.now() 基准，用于本地倒计时插值
  events: [],
  ws: null,
  wsConnected: false,
  wsRetry: 0,
  pingTimer: null,
  runtimes: null,
  tex: null,
  workspace: localStorage.getItem(LS_WORKSPACE) || 'E:\\modemon-ws\\demo',
  budget: '0.40',
  strict: false,
  replayAllMessages: false,
  running: false,               // 本地"已发起执行"标记（真实状态仍以 REST/WS 为准）
  lastError: '',
};

const MAX_EVENTS = 800;
let seen = new Set();
const listeners = new Set();

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function emit(type, payload = {}) {
  for (const fn of Array.from(listeners)) {
    try { fn({ type, ...payload }); } catch (e) { console.error('[store] listener failed', e); }
  }
}

export function setWorkspace(v) {
  state.workspace = v;
  try { localStorage.setItem(LS_WORKSPACE, v); } catch { /* 隐私模式忽略 */ }
}

export function setRoute(route, param = null) {
  state.route = route;
  state.routeParam = param;
  emit('route', { route, param });
}

// ---------------------------------------------------------------- 载入

export async function loadTemplates(force = false) {
  if (state.templates && !force) return state.templates;
  const r = await getJSON('/api/templates');
  state.templates = r.templates || [];
  emit('templates', { templates: state.templates });
  return state.templates;
}

export async function loadRuntimes(force = false) {
  if (state.runtimes && !force) return state.runtimes;
  try {
    state.runtimes = await getJSON('/api/runtimes');
  } catch (e) {
    state.runtimes = { runtimes: [], default_priority: [], error: e.message };
  }
  emit('runtimes', { runtimes: state.runtimes });
  return state.runtimes;
}

export async function loadTexRuntime(force = false) {
  if (state.tex && !force) return state.tex;
  try {
    state.tex = await getJSON('/api/tex-runtime');
  } catch (e) {
    state.tex = { state: 'unknown', note: e.message, warnings: [] };
  }
  emit('tex', { tex: state.tex });
  return state.tex;
}

export async function refreshWorkflows() {
  try {
    state.workflows = await getJSON('/api/workflows');
  } catch (e) {
    state.workflows = [];
    state.lastError = e.message;
  }
  emit('workflows', { workflows: state.workflows });
  return state.workflows;
}

export async function refreshWorkflow() {
  if (!state.workflowId) { state.workflow = null; state.steps = []; return null; }
  const w = await getJSON(`/api/workflows/${encodeURIComponent(state.workflowId)}`);
  state.workflow = w;
  state.steps = w.steps || [];
  try {
    state.checkpoint = await getJSON(
      `/api/workflows/${encodeURIComponent(state.workflowId)}/checkpoints/current`);
  } catch {
    state.checkpoint = null;
  }
  state.checkpointDeadline = state.checkpoint && state.checkpoint.remaining_seconds != null
    ? performance.now() + Number(state.checkpoint.remaining_seconds) * 1000
    : null;
  emit('workflow', { workflow: state.workflow, checkpoint: state.checkpoint });
  return w;
}

// ---------------------------------------------------------------- 工作流动作

export async function selectWorkflow(id) {
  if (state.workflowId !== id) {
    state.workflowId = id;
    clearEvents();
  }
  disconnectWS();
  await refreshWorkflow();
  connectWS();
  await replayEvents();
  await refreshWorkflows();
  emit('select', { workflowId: id });
}

export async function createWorkflow({ template, title, enableCheckpoints }) {
  const w = await postJSON('/api/workflows', {
    template, title, params: {}, enable_checkpoints: !!enableCheckpoints,
  });
  await refreshWorkflows();
  await selectWorkflow(w.id);
  return w;
}

export async function deleteWorkflow(id) {
  await api(`/api/workflows/${encodeURIComponent(id)}`, { method: 'DELETE' });
  if (state.workflowId === id) {
    state.workflowId = null;
    state.workflow = null;
    state.steps = [];
    state.checkpoint = null;
    clearEvents();
    disconnectWS();
    emit('workflow', { workflow: null, checkpoint: null });
  }
  await refreshWorkflows();
}

export async function repairWorkflow() {
  if (!state.workflowId) return null;
  const r = await postJSON(`/api/workflows/${encodeURIComponent(state.workflowId)}/repair`);
  await refreshWorkflow();
  return r;
}

/** 单步执行（后台任务：202 立即返回，进度走 WS / REST）。 */
export async function runStep(skillName) {
  const q = new URLSearchParams({
    workspace: state.workspace,
    max_budget_usd: state.budget || '0.4',
    strict: state.strict ? 'true' : 'false',
    template: state.workflow?.template || 'comp_zh',
  });
  const rep = await api(
    `/api/workflows/${encodeURIComponent(state.workflowId)}/steps/${encodeURIComponent(skillName)}/run?${q}`,
    { method: 'POST' });
  await refreshWorkflow();
  return rep;
}

export async function runAll(maxSteps = 8) {
  const q = new URLSearchParams({
    workspace: state.workspace,
    max_steps: String(maxSteps),
    max_budget_usd: state.budget || '0.4',
  });
  const rep = await api(
    `/api/workflows/${encodeURIComponent(state.workflowId)}/run?${q}`, { method: 'POST' });
  await refreshWorkflow();
  return rep;
}

export async function resolveCheckpoint(action) {
  const r = await postJSON(
    `/api/workflows/${encodeURIComponent(state.workflowId)}/checkpoints/resolve`,
    { action, checkpoint_id: state.checkpoint?.checkpoint_id ?? null, data: {} });
  state.checkpoint = null;
  await refreshWorkflow();
  return r;
}

export async function replayEvents() {
  if (!state.workflowId) return [];
  const suffix = state.replayAllMessages ? '&all_messages=true' : '';
  const r = await getJSON(
    `/api/workflows/${encodeURIComponent(state.workflowId)}/run-events?limit=800${suffix}`);
  resetEvents(r.events || []);
  return state.events;
}

// ---------------------------------------------------------------- 事件缓冲

export function clearEvents() {
  state.events = [];
  seen = new Set();
  emit('events-reset', { events: state.events });
}

function resetEvents(list) {
  state.events = [];
  seen = new Set();
  for (const ev of list) pushEvent(ev, false);
  emit('events-reset', { events: state.events });
}

/** 去重后追加。WS 与 REST 回放会给出同一批事件，必须按 (run_id, sequence) 去重。 */
export function pushEvent(ev, notify = true) {
  const key = eventKey(ev);
  if (seen.has(key)) return false;
  seen.add(key);
  state.events.push({ ...ev, _key: key, _custom: isCustom(ev.kind) });
  if (state.events.length > MAX_EVENTS) {
    const dropped = state.events.shift();
    if (dropped) seen.delete(dropped._key);
  }
  if (notify) emit('event', { event: state.events[state.events.length - 1] });
  return true;
}

// ---------------------------------------------------------------- WebSocket

export function connectWS() {
  disconnectWS();
  if (!state.workflowId) return;
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const url = `${proto}://${location.host}/ws/${encodeURIComponent(state.workflowId)}`;
  let ws;
  try { ws = new WebSocket(url); } catch (e) { setWs(false); return; }
  state.ws = ws;

  ws.onopen = () => {
    state.wsRetry = 0;
    setWs(true);
    state.pingTimer = setInterval(() => {
      try { ws.send('ping'); } catch { /* 断开由 onclose 处理 */ }
    }, 10000);
  };
  ws.onclose = () => {
    setWs(false);
    stopPing();
    const delay = Math.min(1000 * 2 ** state.wsRetry++, 15000);
    setTimeout(() => { if (state.workflowId) connectWS(); }, delay);
  };
  ws.onerror = () => setWs(false);
  ws.onmessage = (e) => {
    if (e.data === 'pong') return;
    let msg;
    try { msg = JSON.parse(e.data); } catch { return; }
    handleWsMessage(msg);
  };
}

export function disconnectWS() {
  stopPing();
  if (state.ws) {
    const ws = state.ws;
    state.ws = null;
    try { ws.onclose = null; ws.close(); } catch { /* 已断开 */ }
  }
  setWs(false);
}

function stopPing() {
  if (state.pingTimer) { clearInterval(state.pingTimer); state.pingTimer = null; }
}

function setWs(on) {
  state.wsConnected = on;
  emit('ws', { connected: on });
}

function handleWsMessage(msg) {
  if (msg.workflow_id && state.workflowId && msg.workflow_id !== state.workflowId) return;

  if (isCustom(msg.type)) {
    pushEvent(customEventFromWs(msg));
    return;
  }

  switch (msg.type) {
    case 'hello':
      if (msg.workflow) {
        state.workflow = { ...(state.workflow || {}), ...msg.workflow };
        state.steps = msg.steps || state.steps;
        state.checkpoint = msg.pending_checkpoint || null;
        emit('workflow', { workflow: state.workflow, checkpoint: state.checkpoint });
      }
      break;
    case 'run_event':
      // WS 的 run_event 没有 evidence（自定义事件的载荷不在这一条里），照实渲染即可
      if (msg.event) pushEvent({ ...msg.event, run_id: msg.run_id, source: 'ws' });
      break;
    case 'checkpoint_created':
      state.checkpoint = {
        checkpoint_id: msg.checkpoint_id, step_name: msg.skill_name,
        checkpoint_type: msg.checkpoint_type, remaining_seconds: null,
      };
      state.checkpointDeadline = null;
      emit('workflow', { workflow: state.workflow, checkpoint: state.checkpoint });
      refreshWorkflow().catch(() => {});
      break;
    case 'checkpoint_resolved':
      state.checkpoint = null;
      state.checkpointDeadline = null;
      emit('workflow', { workflow: state.workflow, checkpoint: null });
      refreshWorkflow().catch(() => {});
      break;
    case 'step_started':
    case 'step_completed':
    case 'step_failed':
    case 'workflow_completed':
      refreshWorkflow().catch(() => {});
      refreshWorkflows().catch(() => {});
      break;
    case 'heartbeat':
      break;
    default:
      break;
  }
}

// ---------------------------------------------------------------- 派生值

export function workflowProgress(w) {
  const steps = (w && w.steps) || [];
  const done = steps.filter((s) => s.status === 'completed').length;
  return { done, total: steps.length, pct: steps.length ? Math.round(done / steps.length * 100) : 0 };
}

export function findWorkflow(id) {
  return state.workflows.find((w) => w.id === id) || null;
}

export { api, getJSON, postJSON };
