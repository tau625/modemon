// Multi-pattern probe -> single compact report
const fs = require('fs');
const path = require('path');
const D = 'E:\\02_Installers\\DailyApps\\Modex-MH-Agent-RE\\beauty';
const OUT = 'E:\\02_Installers\\DailyApps\\Modex-MH-Agent-RE\\reports\\_fx\\probe.txt';

const SPEC = [
  // --- NewWorkflow: palettes / styles / templates / project types
  { f: 'NewWorkflow-Ld6TEJjT.pretty.js', p: 'DATA_FIG_PALETTES=|DATA_FIG_STYLES=|PALETTES=\\[|STYLES=\\[' , b: 0, a: 900, max: 3 },
  { f: 'NewWorkflow-Ld6TEJjT.pretty.js', p: 'project_type|projectType', b: 120, a: 200, max: 12 },
  { f: 'NewWorkflow-Ld6TEJjT.pretty.js', p: 'template:|templateId|templates\\.', b: 100, a: 220, max: 14 },
  { f: 'NewWorkflow-Ld6TEJjT.pretty.js', p: 'cumcm|mcm|icom|huawei|competition_zh|course_paper|thesis_proposal', b: 100, a: 160, max: 12 },
  // --- skill (step) id -> Chinese name maps anywhere
  { f: '.*\\.pretty\\.js', p: 'problem_analysis', b: 200, a: 400, max: 6 },
  // --- settings keys
  { f: 'Settings-D4EW1h0L.pretty.js', p: 'default_effort|claude_bin|model_context_policies|data_dir|latex|python|export_dir|api_key|base_url|model_id', b: 90, a: 160, max: 30 },
  // --- account/wallet/billing
  { f: 'newApiWallet-BJVw6ude.pretty.js', p: 'orders|adjustments|requests|checkout|balance|quota|recharge|wallet|usage', b: 110, a: 200, max: 20 },
  { f: 'AccountModelCatalog-DdzyHjab.pretty.js', p: 'catalog_source|billing_kind|price_version|newapi-direct|native-messages-v2|unit_microcredits|context_window', b: 90, a: 170, max: 14 },
  // --- artifact kinds / renderer matrix
  { f: 'ArtifactLibrary-BPEftl07.pretty.js', p: 'markdown|latex|\\.tex|\\.pdf|\\.docx', b: 60, a: 120, max: 10 },
  { f: 'ArtifactLibrary-BPEftl07.pretty.js', p: 'recharts|echarts|d3\\.|chart\\.js', b: 90, a: 150, max: 6 },
  // --- checkpoint modal actions
  { f: 'WorkflowDetail-bN89YgNS.pretty.js', p: 'idea_select|approve|feedback|checkpoint_type', b: 130, a: 220, max: 14 },
  // --- editor features
  { f: 'LatexEditor-I1nsgpA4.pretty.js', p: 'compile|latexmk|xelatex|tectonic|bibtex|word_count|undo', b: 90, a: 160, max: 16 },
];

const lines = [];
for (const s of SPEC) {
  const re = new RegExp(s.p, 'g');
  const fileRe = new RegExp('^' + s.f + '$');
  let count = 0;
  lines.push(`\n========== PROBE ${s.p}  (${s.f}) ==========`);
  for (const fn of fs.readdirSync(D).sort()) {
    if (!fileRe.test(fn)) continue;
    const txt = fs.readFileSync(path.join(D, fn), 'utf8');
    const byLine = txt.split('\n');
    let m;
    while ((m = re.exec(txt)) && count < s.max) {
      // line number
      let ln = 1;
      for (let i = 0; i < byLine.length; i++) { if (byLine[i].includes(m[0])) { ln = i + 1; break; } }
      const st = Math.max(0, m.index - s.b);
      const en = Math.min(txt.length, m.index + m[0].length + s.a);
      lines.push(`--- ${fn}:${ln} @${m.index}\n${txt.slice(st, en).replace(/\n/g, ' ')}`);
      count++;
      if (count >= s.max) break;
    }
  }
  if (count === 0) lines.push('(no match)');
}
fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, lines.join('\n'), 'utf8');
console.log('probe bytes', lines.join('\n').length);
