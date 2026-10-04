// Emit every path-literal call site with the following ~300 chars (to catch method:/headers/body:)
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
  '/style-preview', '/projects', '/files', '/native', '/ws/'];

const rows = [];
for (const f of files()) {
  const s = fs.readFileSync(path.join(DIST, f), 'utf8');
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (c !== '"' && c !== "'" && c !== '`') continue;
    const lit = readLiteral(s, i);
    if (lit === null) continue;
    const body = lit.slice(1, -1);
    if (body.length < 3 || body.length > 300) continue;
    const varPrefixed = /^\$\{[A-Za-z_$][\w$.]*\}/.test(body);
    const startsPath = body.startsWith('/') || varPrefixed;
    if (!startsPath) continue;
    if (!KEYS.some(k => body.includes(k))) continue;
    if (body.includes('\n')) continue;
    let after = s.slice(i + lit.length, i + lit.length + 260).replace(/\n/g, ' ');
    // capture preceding 120 chars to see helper fn name
    let before = s.slice(Math.max(0, i - 130), i).replace(/\n/g, ' ');
    rows.push({ f, body, after, before });
  }
}

const lines = rows.map(r =>
  `### ${r.f}\nURL: ${r.body}\nBEFORE: ...${r.before}\nAFTER: ${r.after}\n`);
fs.writeFileSync(path.join(OUT, 'callsites.txt'), lines.join('\n'), 'utf8');
console.log('callsites:', rows.length);
