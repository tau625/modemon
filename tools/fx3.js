// Capture every string/template literal that looks like an HTTP path, incl. `${base}/...` style.
const fs = require('fs');
const path = require('path');
const DIST = 'E:\\02_Installers\\DailyApps\\Modex-MH-Agent\\resources\\app\\dist\\assets';
const OUT = 'E:\\02_Installers\\DailyApps\\Modex-MH-Agent-RE\\reports\\_fx';
const files = () => fs.readdirSync(DIST).filter(f => f.endsWith('.js')).sort();

function readLiteral(s, i) {
  const q = s[i];
  if (q === '"' || q === "'") {
    let j = i + 1;
    while (j < s.length) {
      if (s[j] === '\\') { j += 2; continue; }
      if (s[j] === q) return s.slice(i, j + 1);
      if (s[j] === '\n') return null;
      j++;
    }
    return null;
  }
  if (q === '`') {
    let j = i + 1, depth = 0;
    while (j < s.length) {
      const c = s[j];
      if (c === '\\') { j += 2; continue; }
      if (depth === 0 && c === '`') return s.slice(i, j + 1);
      if (c === '$' && s[j + 1] === '{') { depth++; j += 2; continue; }
      if (depth > 0) { if (c === '{') depth++; else if (c === '}') depth--; }
      j++;
    }
    return null;
  }
  return null;
}

const KEYS = ['/workflows', '/editor', '/settings', '/account', '/license', '/chat', '/artifacts',
  '/checkpoints', '/templates', '/steps', '/logs', '/messages', '/client-config', '/palette-preview',
  '/style-preview', '/projects', '/files', '/health', '/native'];

const map = new Map();
for (const f of files()) {
  const s = fs.readFileSync(path.join(DIST, f), 'utf8');
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (c !== '"' && c !== "'" && c !== '`') continue;
    const lit = readLiteral(s, i);
    if (lit === null) continue;
    const body = lit.slice(1, -1);
    if (body.length < 4 || body.length > 400) continue;
    const varPrefixed = /^\$\{[A-Za-z_$][\w$.]*\}/.test(body);
    const startsPath = body.startsWith('/') || varPrefixed;
    const hasKey = KEYS.some(k => body.includes(k)) || (varPrefixed && (body.match(/\//g) || []).length >= 1);
    if (startsPath && hasKey) {
      const k = f + '|' + body;
      if (!map.has(k)) map.set(k, { f, body, n: 0 });
      map.get(k).n++;
    }
  }
}

const rows = [...map.values()].sort((a, b) => a.f.localeCompare(b.f) || a.body.localeCompare(b.body));
fs.writeFileSync(path.join(OUT, 'path-literals.tsv'),
  rows.map(r => `${r.f}\t${r.n}\t${r.body}`).join('\n'), 'utf8');

// normalized: replace ${...} with {x}
const norm = new Map();
for (const r of rows) {
  const nb = r.body.replace(/\$\{[^}]*\}/g, '{x}');
  if (!norm.has(nb)) norm.set(nb, new Set());
  norm.get(nb).add(r.f);
}
const lines = [...norm.entries()].sort((a, b) => a[0].localeCompare(b[0]))
  .map(([k, v]) => `${[...v].join(',')}\t${k}`);
fs.writeFileSync(path.join(OUT, 'path-normalized.tsv'), lines.join('\n'), 'utf8');
console.log('path literals:', rows.length, 'normalized:', lines.length);
