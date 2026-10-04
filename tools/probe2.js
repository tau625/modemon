const fs = require('fs');
const path = require('path');
const D = 'E:\\02_Installers\\DailyApps\\Modex-MH-Agent-RE\\beauty';
const OUT = 'E:\\02_Installers\\DailyApps\\Modex-MH-Agent-RE\\reports\\_fx\\probe2.txt';

// simple substring scan with context
function scan(fileRe, needles, before, after, max) {
  const out = [];
  for (const fn of fs.readdirSync(D).sort()) {
    if (!new RegExp(fileRe).test(fn)) continue;
    const txt = fs.readFileSync(path.join(D, fn), 'utf8');
    for (const nd of needles) {
      let i = -1, n = 0;
      while ((i = txt.indexOf(nd, i + 1)) >= 0 && n < max) {
        const st = Math.max(0, i - before), en = Math.min(txt.length, i + nd.length + after);
        out.push(`--- [${nd}] ${fn} @${i}\n${txt.slice(st, en).replace(/\n/g, ' ')}`);
        n++;
      }
    }
  }
  return out;
}

const CH = [];
const push = (title, arr) => { CH.push(`\n========== ${title} ==========`); CH.push(...(arr.length ? arr : ['(no match)'])); };

push('markdown pipeline libs (ArtifactLibrary)',
  scan('ArtifactLibrary', ['remark', 'rehype', 'micromark', 'mdast', 'hast-util', 'unified', 'marked', 'markdown-it', 'highlight.js', 'hljs', 'prism', 'shiki', 'react-markdown', 'remark-gfm', 'remark-math', 'rehype-katex'], 120, 200, 3));

push('recharts / chart lib (WorkflowDetail)',
  scan('WorkflowDetail', ['recharts', 'ResponsiveContainer', 'RadarChart', 'BarChart', 'LineChart'], 100, 160, 3));

push('artifact category table (ArtifactLibrary)',
  scan('ArtifactLibrary', ['beginnerHint:`需要时再查看`'], 1400, 300, 1));

push('chat interaction_mode / progress phases (useWebSocket + ChatWorkbench)',
  scan('useWebSocket|ChatWorkbench', ['interaction_mode', 'progress_phase', 'item_kind', 'execution_scope'], 110, 200, 6));

push('chat stage / skill display (ChatWorkbench)',
  scan('ChatWorkbench', ['run_step', 'focused_run', 'patch', 'research', 'validate', 'repair'], 90, 160, 6));

push('Dashboard workflow card fields (Dashboard)',
  scan('Dashboard', ['status===', 'current_step', 'steps.length', 'progress'], 110, 180, 8));

push('react-router future flags / version',
  scan('jsx-runtime|index-BeImsYqE', ['v7_startTransition', 'v7_relativeSplatPath', 'future:', 'useViewTransitionState', 'startTransition'], 130, 200, 6));

push('Account page native billing / realname / software (Account)',
  scan('Account-CFNFyFpM', ['realname', 'wallet', 'software', 'checkout', 'orders', 'credits', 'balance'], 110, 190, 8));

push('NewWorkflow AI disclosure / competition guard',
  scan('NewWorkflow', ['AI 使用记录', 'comp_', 'enable_comp_review', 'competition'], 130, 220, 10));

push('editor: word/docx/latex toolchain (LatexEditor)',
  scan('LatexEditor', ['xelatex', 'latexmk', 'bibtex', 'word_count', 'docx', 'count_chapter', 'texlive', 'MiKTeX'], 120, 200, 8));

push('localStorage keys',
  scan('.*', ['localStorage.getItem(', 'localStorage.setItem('], 90, 130, 14));

push('CSS version banners',
  (() => {
    const C = 'E:\\02_Installers\\DailyApps\\Modex-MH-Agent\\resources\\app\\dist\\assets';
    const o = [];
    for (const f of fs.readdirSync(C).filter(f => f.endsWith('.css'))) {
      const s = fs.readFileSync(path.join(C, f), 'utf8');
      const m = s.match(/\/\*![^*]{0,200}/g) || [];
      o.push(`--- ${f}\n${m.join('\n').slice(0, 700)}`);
    }
    return o;
  })());

fs.writeFileSync(OUT, CH.join('\n'), 'utf8');
console.log('bytes', CH.join('\n').length);
