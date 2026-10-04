// Bracket-aware extraction: pull full template literals / string literals that start with /api
const fs = require('fs');
const path = require('path');
const DIST = 'E:\\02_Installers\\DailyApps\\Modex-MH-Agent\\resources\\app\\dist\\assets';
const OUT = 'E:\\02_Installers\\DailyApps\\Modex-MH-Agent-RE\\reports\\_fx';
const files = () => fs.readdirSync(DIST).filter(f => f.endsWith('.js')).sort();

// read a JS template literal or quoted string starting at index i (s[i] is the quote)
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
      if (depth > 0) {
        if (c === '{') depth++;
        else if (c === '}') depth--;
      }
      j++;
    }
    return null;
  }
  return null;
}

const mode = process.argv[2] || 'api';

function scan(pred) {
  const map = new Map();
  for (const f of files()) {
    const s = fs.readFileSync(path.join(DIST, f), 'utf8');
    for (let i = 0; i < s.length; i++) {
      const c = s[i];
      if (c !== '"' && c !== "'" && c !== '`') continue;
      const lit = readLiteral(s, i);
      if (lit === null) continue;
      const body = lit.slice(1, -1);
      if (body.length < 2 || body.length > 300) continue;
      if (pred(body)) {
        const k = f + '|' + body;
        if (!map.has(k)) map.set(k, { f, body, i, n: 0, q: c });
        map.get(k).n++;
      }
      // do NOT skip ahead: regex literals / apostrophes can cause false starts
    }
  }
  return [...map.values()];
}

if (mode === 'api') {
  const rows = scan(b => b.startsWith('/api/') || b === '/api' || b.startsWith('/api?'));
  rows.sort((a, b) => a.f.localeCompare(b.f) || a.body.localeCompare(b.body));
  fs.writeFileSync(path.join(OUT, 'api-literals.tsv'),
    rows.map(r => `${r.f}\t${r.n}\t${r.body}`).join('\n'), 'utf8');
  const paths = [...new Set(rows.map(r => r.body.replace(/\$\{[^}]*\}/g, '{x}')))].sort();
  fs.writeFileSync(path.join(OUT, 'api-normalized.txt'), paths.join('\n'), 'utf8');
  console.log('literals:', rows.length, 'normalized:', paths.length);
}

if (mode === 'rel') {
  // relative paths that are probably endpoints but not prefixed with /api
  const rows = scan(b => /^\/(workflows|editor|settings|account|license|chat|artifacts|templates|checkpoints|projects|files|health|ws|api)\b/.test(b) && !b.startsWith('/api/'));
  rows.sort((a, b) => a.f.localeCompare(b.f) || a.body.localeCompare(b.body));
  fs.writeFileSync(path.join(OUT, 'rel-literals.tsv'), rows.map(r => `${r.f}\t${r.n}\t${r.body}`).join('\n'), 'utf8');
  console.log('rel literals:', rows.length);

  // also path-only strings starting with '/'
  const rows2 = scan(b => b.startsWith('/') && !b.includes(' ') && !/\.[a-z]{2,4}$/.test(b) && b.length < 90 && /^\/[a-z0-9{}\/$:_-]+$/i.test(b));
  const seen = new Set(rows2.map(r => r.body));
  fs.writeFileSync(path.join(OUT, 'slash-strings.txt'), [...seen].sort().join('\n'), 'utf8');
  console.log('slash strings:', seen.size);
}

if (mode === 'wspath') {
  const rows = scan(b => /ws|websocket/i.test(b) && b.length < 200);
  fs.writeFileSync(path.join(OUT, 'ws-literals.tsv'), rows.map(r => `${r.f}\t${r.n}\t${r.body}`).join('\n'), 'utf8');
  console.log('ws literals:', rows.length);
}
