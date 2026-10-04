/**
 * HTTP 封装（同源相对路径，与后端错误契约对齐）。
 *
 * 后端错误契约有两种形态，**必须同时兼容**（`main.py` 的
 * `ModemonError` / `HTTPException` handler 明确写了这一点）：
 *   {"detail": "字符串"}
 *   {"detail": {"message": "...", "code": "..."}}
 *
 * 这里把两者归一成 ApiError，带 `status` / `code` / `message` 三个字段，
 * 让页面能区分"业务失败（ok=false）"与"请求失败（HTTP 非 2xx）"——
 * 这是两条不同的展示路径，不能混。
 */

export class ApiError extends Error {
  constructor(message, { status = 0, code = '', body = null } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.body = body;
  }
}

function describe(status, body, statusText) {
  const detail = body && typeof body === 'object' ? body.detail : body;
  if (typeof detail === 'string' && detail) return { message: detail, code: '' };
  if (detail && typeof detail === 'object') {
    return {
      message: `${detail.message || statusText || '请求失败'}`
        + (detail.code ? ` [${detail.code}]` : ''),
      code: detail.code || '',
    };
  }
  return { message: statusText || `HTTP ${status}`, code: '' };
}

export async function api(path, opts = {}) {
  let res;
  try {
    res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts });
  } catch (e) {
    throw new ApiError(`网络请求失败：${e.message}`, { status: 0 });
  }
  const text = await res.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = text; }
  if (!res.ok) {
    const { message, code } = describe(res.status, body, res.statusText);
    throw new ApiError(`HTTP ${res.status}: ${message}`, { status: res.status, code, body });
  }
  return body;
}

export const getJSON = (path) => api(path);

export const postJSON = (path, body) => api(path, {
  method: 'POST',
  body: JSON.stringify(body ?? {}),
});

/** 查询串：只保留非空值，`true/false` 由调用方自己转字符串（与后端 Query 一致）。 */
export function qs(params) {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params || {})) {
    if (v === undefined || v === null || v === '') continue;
    sp.set(k, String(v));
  }
  return sp.toString();
}
