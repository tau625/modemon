const fs = require('fs');
const D = 'E:/02_Installers/DailyApps/Modex-MH-Agent-RE/beauty';
const OUT = 'E:/02_Installers/DailyApps/Modex-MH-Agent-RE/reports/_fx/literals.txt';
const out = [];
const push = (t, s) => out.push(`\n========== ${t} ==========\n${s}`);

function grab(file, startPat, maxLen) {
  const s = fs.readFileSync(`${D}/${file}`, 'utf8');
  const m = s.match(startPat);
  if (!m) return `(not found: ${startPat})`;
  const i = m.index;
  return s.slice(i, i + maxLen).replace(/\n/g, ' ');
}

// template catalogue in NewWorkflow: var Te=[{...}]
push('NewWorkflow Te catalogue (templates)', grab('NewWorkflow-Ld6TEJjT.pretty.js', /var Te=\[\{/, 4200));

// exported DATA_FIG_PALETTES (T) and DATA_FIG_STYLES (ve)
{
  const s = fs.readFileSync(`${D}/NewWorkflow-Ld6TEJjT.pretty.js`, 'utf8');
  for (const name of ['var T=', 'var ve=', 'DATA_FIG']) {
    let i = s.indexOf(name);
    out.push(`\n--- [${name}] @${i}\n` + (i >= 0 ? s.slice(i, i + 2600).replace(/\n/g, ' ') : '(none)'));
  }
}

// ChatWorkbench skill display map + status map
{
  const s = fs.readFileSync(`${D}/ChatWorkbench-B0gSrHl3.pretty.js`, 'utf8');
  const pats = [/var ue=\{/, /ue=\{/, /an=\{/, /var pe=\{/, /pe=\{/];
  for (const p of pats) {
    const m = s.match(p);
    if (m) out.push(`\n--- ChatWorkbench [${p}] @${m.index}\n` + s.slice(m.index, m.index + 2400).replace(/\n/g, ' '));
  }
}

// progress phase map / status label maps
{
  const s = fs.readFileSync(`${D}/ChatWorkbench-B0gSrHl3.pretty.js`, 'utf8');
  for (const k of ['preparing_content', 'reasoning']) {
    let i = s.indexOf(k);
    if (i >= 0) out.push(`\n--- ChatWorkbench phase key [${k}] @${i}\n` + s.slice(Math.max(0, i - 900), i + 900).replace(/\n/g, ' '));
  }
}

// WorkflowDetail: step skill map / skill display names
{
  const s = fs.readFileSync(`${D}/WorkflowDetail-bN89YgNS.pretty.js`, 'utf8');
  const m = s.match(/ue\[Ne\]|skill_name\]/);
  for (const k of ['problem_analysis', 'display_name']) {
    let i = s.indexOf(k);
    if (i >= 0) out.push(`\n--- WorkflowDetail [${k}] @${i}\n` + s.slice(Math.max(0, i - 1200), i + 1200).replace(/\n/g, ' '));
  }
}

// index: theme + version + api helper
{
  const s = fs.readFileSync(`${D}/index-BeImsYqE.pretty.js`, 'utf8');
  for (const k of ['function me(e=', 'MH Agent-theme']) {
    let i = s.indexOf(k);
    if (i >= 0) out.push(`\n--- index [${k}] @${i}\n` + s.slice(Math.max(0, i - 300), i + 1800).replace(/\n/g, ' '));
  }
}

fs.writeFileSync(OUT, out.join('\n'), 'utf8');
console.log('bytes', out.join('\n').length);
