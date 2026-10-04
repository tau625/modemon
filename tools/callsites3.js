// Precise: for each path literal, bound the enclosing call expression and find method: inside it.
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

// find end index of the enclosing call: first ')' at relative depth 0 after literal
function callEnd(s, start) {
  let depth = 0, j = start;
  while (j < s.length && j < start + 1500) {
    const c = s[j];
    if (c === '"' || c === "'" || c === '`') {
      const l = readLiteral(s, j);
      if (l) { j += l.length; continue; }
    }
    if (c === '(') depth++;
    else if (c === ')') { if (depth === 0) return j; depth--; }
    else if (c === ';') return j;
    j++;
  }
  return j;
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
    if (body.length < 3 || body.length > 300 || body.includes('\n')) continue;
    const varPrefixed = /^\$\{[A-Za-z_$][\w$.]*\}/.test(body);
    if (!(body.startsWith('/') || varPrefixed)) continue;
    if (!KEYS.some(k => body.includes(k))) continue;
    const end = callEnd(s, i + lit.length);
    const span = s.slice(i + lit.length, end);
    const m = span.match(/method:\s*[`'"]([A-Z]+)[`'"]/);
    const method = m ? m[1] : (/\bmethod:/.test(span) ? '?' : 'GET');
    const kind = /FormData/.test(span) ? 'formdata' : (/JSON\.stringify/.test(span) ? 'json' : '');
    const before = s.slice(Math.max(0, i - 200), i).replace(/\n/g, ' ').slice(-90);
    rows.push({ f, body, method, kind, before, span: span.replace(/\n/g, ' ').slice(0, 150) });
  }
}

const seen = new Set();
const lines = [];
for (const r of rows) {
  const k = [r.f, r.body, r.method, r.kind].join('\t');
  if (seen.has(k)) continue;
  seen.add(k);
  lines.push(`${r.f}\t${r.method}\t${r.kind || '-'}\t${r.body}\t${r.span}`);
}
fs.writeFileSync(path.join(OUT, 'endpoint-map3.tsv'), lines.join('\n'), 'utf8');
console.log('rows', seen.size);
