const fs = require('fs');
const path = require('path');
const D = 'E:/02_Installers/DailyApps/Modex-MH-Agent-RE/beauty';
const DIST = 'E:/02_Installers/DailyApps/Modex-MH-Agent/resources/app/dist/assets';
const OUT = 'E:/02_Installers/DailyApps/Modex-MH-Agent-RE/reports/_fx/probe3.txt';
const out = [];
const push = (t, s) => out.push(`\n========== ${t} ==========\n${s}`);
function scan(fileRe, needles, before, after, max) {
  const res = [];
  for (const fn of fs.readdirSync(D).sort()) {
    if (!new RegExp(fileRe).test(fn)) continue;
    const txt = fs.readFileSync(path.join(D, fn), 'utf8');
    for (const nd of needles) {
      let i = -1, n = 0;
      while ((i = txt.indexOf(nd, i + 1)) >= 0 && n < max) {
        res.push(`--- [${nd}] ${fn} @${i}\n${txt.slice(Math.max(0, i - before), i + nd.length + after).replace(/\n/g, ' ')}`);
        n++;
      }
    }
  }
  return res.length ? res : ['(no match)'];
}

push('palette/style names (NewWorkflow)', scan('NewWorkflow', ['okabe_ito', 'tol_vibrant', 'morandi', 'framed_journal', 'soft_grid', 'bold_edge', 'journal', 'aurora'], 200, 260, 3));
push('palette/style names (backend-driven? all chunks)', scan('.*', ['okabe_ito', 'tol_vibrant', 'framed_journal'], 150, 200, 2));
push('ArtifactLibrary markdown components map', scan('ArtifactLibrary', ['components:{', 'remarkPlugins:[vl,mh]'], 60, 1500, 2));
push('vite markers', scan('index-BeImsYqE|ChatWorkbench', ['__vite__preload', 'import.meta.env', '__VITE_PRELOAD__', 'vite/modulepreload'], 120, 180, 3));
push('artifact kind detection (ArtifactLibrary)', scan('ArtifactLibrary', ['artifactKind', 'kind:', 'guessKind', 'isMarkdown', 'previewable'], 100, 180, 6));
push('chat config body (useWebSocket)', scan('useWebSocket', ['interaction_mode:o.interaction_mode', 'fetchConfig:async'], 300, 700, 2));
push('chat say body (useWebSocket)', scan('useWebSocket', ['item_kind:`user_message`'], 700, 500, 2));
push('Account page tabs / native sections', scan('Account-CFNFyFpM', ['aria-label:`', 'wallet', 'realname', 'software', '充值', '实名'], 120, 200, 10));
push('WorkflowDetail checkpoint modal API + session', scan('WorkflowDetail', ['checkpoints/current', 'remaining_seconds', 'ACCOUNT_MODEL_REFUSED'], 200, 300, 3));
push('Dashboard actions (start/pause/delete/import/export)', scan('Dashboard', ['工作流', '导入', '导出', '批量'], 130, 220, 8));
push('ScoreChart (WorkflowDetail)', scan('WorkflowDetail', ['ScoreChart', 'scores', 'radar'], 150, 250, 5));
push('index.css tokens count', (() => {
  const s = fs.readFileSync(path.join(DIST, 'index-mr3gZRQa.css'), 'utf8');
  const vars = [...new Set((s.match(/--[a-z0-9-]+(?=:)/g) || []))];
  return [`var count ${vars.length}`, vars.slice(0, 60).join(', '), `\ndata-theme occurrences: ` + (s.match(/data-theme="[a-z]+"/g) || []).slice(0, 12).join(',')];
})());

fs.writeFileSync(OUT, out.join('\n'), 'utf8');
console.log('bytes', out.join('\n').length);
