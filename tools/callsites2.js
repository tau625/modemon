// Emit every path-literal call site with a wide following window + method/body analysis.
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
  '/style-preview', '/projects', '/files', '/docs', '/docx', '/serve', '/compile'];

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
    if (!(body.startsWith('/') || varPrefixed)) continue;
    if (!KEYS.some(k => body.includes(k))) continue;
    if (body.includes('\n')) continue;
    const after = s.slice(i + lit.length, i + lit.length + 700).replace(/\n/g, ' ');
    const before = s.slice(Math.max(0, i - 400), i).replace(/\n/g, ' ');
    const m = after.match(/method:\s*[`'"]([A-Z]+)[`'"]/);
    const method = m ? m[1] : (after.match(/^\s*,\s*\{\s*[`'"]?method/) ? '?' : 'GET*');
    const bodyKind = /new FormData|FormData\(/.test(after) ? 'formdata' : (/JSON\.stringify/.test(after) ? 'json' : '');
    rows.push({ f, body, method, bodyKind, after: after.slice(0, 320), before: before.slice(-120) });
  }
}

const seen = new Set();
const lines = [];
for (const r of rows) {
  const k = r.f + '|' + r.body + '|' + r.method + '|' + r.bodyKind;
  if (seen.has(k)) continue;
  seen.add(k);
  lines.push(`### ${r.f}\nURL: ${r.body}\nMETHOD: ${r.method}  BODY: ${r.bodyKind || '-'}\nAFTER: ${r.after}\nBEFORE: ...${r.before}\n`);
}
fs.writeFileSync(path.join(OUT, 'callsites2.txt'), lines.join('\n'), 'utf8');
const tsv = [...seen].map(k => k.replace(/\|/g, '\t'));
fs.writeFileSync(path.join(OUT, 'endpoint-map2.tsv'), tsv.join('\n'), 'utf8');
console.log('rows', seen.size);
