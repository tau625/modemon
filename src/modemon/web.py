"""实时进度服务：FastAPI + WebSocket 推送运行事件。

设计：不引入数据库、不引入前端构建。运行状态本来就落在 `runs/<id>/report.json`，
事件本来就追加在 `runs/<id>/logs/events.jsonl`；本模块只是把它们读出来，
并用 WebSocket 把新增事件实时推给浏览器。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

POLL_INTERVAL_S = 0.5

INDEX_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>Modemon · 运行监控</title>
<style>
 body{font-family:system-ui,"Microsoft YaHei",sans-serif;margin:0;background:#0f1115;color:#e6e6e6}
 header{padding:14px 20px;border-bottom:1px solid #262b36;display:flex;gap:16px;align-items:center}
 h1{font-size:16px;margin:0;font-weight:600}
 main{display:grid;grid-template-columns:280px 1fr;height:calc(100vh - 53px)}
 aside{border-right:1px solid #262b36;overflow:auto;padding:10px}
 .run{padding:8px 10px;border-radius:6px;cursor:pointer;font-size:13px;margin-bottom:4px}
 .run:hover{background:#1a1f29}.run.active{background:#233047}
 .muted{color:#8b93a7;font-size:12px}
 #log{padding:14px 18px;overflow:auto;font-family:ui-monospace,Consolas,monospace;font-size:13px;line-height:1.6}
 .ev{margin-bottom:3px;white-space:pre-wrap;word-break:break-word}
 .kind{color:#6aa9ff}.cost{color:#f0c674}.warn{color:#ffb86c}.error{color:#ff6b6b}
 .review{color:#8ce99a}.exec{color:#c099ff}
 #meta{padding:10px 18px;border-bottom:1px solid #262b36;font-size:13px;color:#b9c0d0}
</style></head><body>
<header><h1>Modemon · 运行监控</h1><span class="muted" id="hint">选择左侧的运行查看实时进度</span></header>
<main>
 <aside id="runs"></aside>
 <section>
  <div id="meta">未选择运行</div>
  <div id="log"></div>
 </section>
</main>
<script>
let ws = null, current = null;
async function loadRuns(){
  const r = await fetch('/api/runs'); const runs = await r.json();
  const box = document.getElementById('runs');
  box.innerHTML = runs.length ? '' : '<div class="muted">还没有运行记录</div>';
  for (const run of runs){
    const d = document.createElement('div');
    d.className = 'run' + (run.run_id === current ? ' active' : '');
    d.innerHTML = `<b>${run.run_id}</b><br><span class="muted">${run.status} · ${run.stage_index}/${run.stages}</span>`;
    d.onclick = () => watch(run.run_id);
    box.appendChild(d);
  }
}
function watch(runId){
  current = runId;
  document.getElementById('log').innerHTML = '';
  document.getElementById('hint').textContent = '已连接 ' + runId;
  fetch(`/api/runs/${runId}`).then(r => r.json()).then(s => {
    document.getElementById('meta').textContent =
      `${s.run_id} · ${s.competition} · ${s.status} · 执行者 ${(s.models||{}).executor||'?'} / 评审者 ${(s.models||{}).reviewer||'?'}`;
  });
  if (ws) ws.close();
  ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/runs/${runId}`);
  ws.onmessage = e => {
    const ev = JSON.parse(e.data);
    if (ev.kind === '__reset__') { document.getElementById('log').innerHTML = ''; return; }
    const div = document.createElement('div');
    div.className = 'ev ' + ev.kind;
    const t = new Date((ev.ts||0)*1000).toLocaleTimeString();
    div.innerHTML = `<span class="kind">[${t}] ${ev.kind}</span> ${ev.message||''} <span class="muted">${ev.detail||''}</span>`;
    const log = document.getElementById('log');
    log.appendChild(div); log.scrollTop = log.scrollHeight;
  };
  ws.onclose = () => { setTimeout(loadRuns, 800); };
  loadRuns();
}
loadRuns(); setInterval(loadRuns, 5000);
</script></body></html>
"""


def _runs_root(root: Path) -> Path:
    return Path(root) / "runs"


def create_app(root: Path) -> FastAPI:
    """构建 FastAPI 应用；root 为工程根目录。"""
    root = Path(root).resolve()
    runs_root = _runs_root(root)
    app = FastAPI(title="Modemon", version="0.1.0")

    def _list_runs() -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if not runs_root.exists():
            return items
        for d in sorted(runs_root.iterdir(), reverse=True):
            report = d / "report.json"
            if not d.is_dir() or not report.exists():
                continue
            try:
                data = json.loads(report.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            items.append(
                {
                    "run_id": d.name,
                    "competition": data.get("competition"),
                    "status": data.get("status"),
                    "stage_index": data.get("stage_index"),
                    "stages": len(data.get("stages") or []),
                    "updated_at": data.get("updated_at"),
                }
            )
        return items

    def _report(run_id: str) -> dict[str, Any] | None:
        path = runs_root / run_id / "report.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return INDEX_HTML

    @app.get("/api/runs")
    def api_runs() -> list[dict[str, Any]]:
        return _list_runs()

    @app.get("/api/runs/{run_id}")
    def api_run(run_id: str) -> JSONResponse:
        data = _report(run_id)
        if data is None:
            return JSONResponse({"error": "not found", "run_id": run_id}, status_code=404)
        return JSONResponse(data)

    @app.websocket("/ws/runs/{run_id}")
    async def ws_events(websocket: WebSocket, run_id: str) -> None:
        """推送该运行的事件流：先补发历史，再增量跟随。"""
        await websocket.accept()
        events_file = runs_root / run_id / "logs" / "events.jsonl"
        if not events_file.exists():
            await websocket.send_text(json.dumps({"kind": "__reset__", "message": f"运行 {run_id} 暂无事件"}))
        sent = 0
        try:
            while True:
                if events_file.exists():
                    try:
                        lines = events_file.read_text(encoding="utf-8", errors="replace").splitlines()
                    except OSError:
                        lines = []
                    for line in lines[sent:]:
                        await websocket.send_text(line)
                    sent = len(lines)
                await asyncio.sleep(POLL_INTERVAL_S)
        except WebSocketDisconnect:
            return
        except (RuntimeError, OSError):
            return

    return app
