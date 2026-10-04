/**
 * DOM 与格式化小工具（无依赖）。
 *
 * 只放"到处都用得上、且与业务无关"的东西：选择器、转义、时间、
 * 文本截断。任何涉及接口/状态的逻辑都不放这里，避免工具模块变成第二份真相源。
 */

export const $ = (sel, root = document) => root.querySelector(sel);
export const $id = (id) => document.getElementById(id);

/** HTML 转义。**所有插入 innerHTML 的外部数据都必须过这里。** */
export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

/** 时间戳只显示到秒，库里的两种形态（ISO / SQLite CURRENT_TIMESTAMP）都能吃。 */
export function fmtTs(raw) {
  if (!raw) return '';
  const s = String(raw).replace(' ', 'T');
  const m = s.match(/T(\d{2}:\d{2}:\d{2})/);
  return m ? m[1] : s.slice(0, 19);
}

export function fmtBytes(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '-';
  const v = Number(n);
  if (v < 1024) return `${v} B`;
  if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`;
  return `${(v / 1024 / 1024).toFixed(2)} MB`;
}

export function truncate(s, n = 400) {
  const t = String(s ?? '');
  return t.length > n ? `${t.slice(0, n)}…` : t;
}

export const WORKFLOW_STATUS = {
  pending: '待执行', running: '执行中', paused: '已暂停',
  completed: '已完成', failed: '失败',
};

export const STEP_STATUS = {
  pending: '待执行', running: '执行中', waiting_checkpoint: '等待确认',
  completed: '已完成', failed: '失败', skipped: '已跳过', paused: '已暂停',
};

export function pill(text, tone = 'dim') {
  return `<span class="chip ${tone}">${esc(text)}</span>`;
}
