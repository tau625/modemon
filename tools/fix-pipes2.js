// GFM pipe escaping with correct multi-backtick code-span handling.
const fs = require('fs');
const P = 'E:/02_Installers/DailyApps/Modex-MH-Agent-RE/reports/03-frontend.md';

function fixLine(l) {
  let out = '';
  let fence = 0; // 0 = outside code span; >0 = inside a fence of that many backticks
  let j = 0;
  while (j < l.length) {
    if (l[j] === '`') {
      let n = 0;
      while (l[j + n] === '`') n++;
      if (fence === 0) { fence = n; out += '`'.repeat(n); j += n; continue; }
      if (n >= fence) { fence = 0; out += '`'.repeat(n); j += n; continue; }
      out += '`'.repeat(n); j += n; continue;
    }
    const c = l[j];
    if (c === '|') {
      // inside a code span -> must escape. Outside: keep as cell delimiter.
      if (fence > 0 && l[j - 1] !== '\\') { out += '\\|'; j++; continue; }
      // already-escaped pipe outside code span: leave as-is
      out += c; j++; continue;
    }
    if (c === '\\' && l[j + 1] === '|') { out += '\\|'; j += 2; continue; }
    out += c; j++;
  }
  return out;
}

// First pass: un-escape previously over-escaped pipes, then re-escape correctly.
let L = fs.readFileSync(P, 'utf8').split('\n');
let changed = 0;
for (let i = 0; i < L.length; i++) {
  if (!L[i].startsWith('|')) continue;
  const before = L[i];
  const plain = L[i].replace(/\\\|/g, '|');   // normalize: \| -> |
  const after = fixLine(plain);
  if (after !== before) { L[i] = after; changed++; }
}
fs.writeFileSync(P, L.join('\n'), 'utf8');
console.log('rows normalized:', changed);

// validate
const M = fs.readFileSync(P, 'utf8').split('\n');
const strip = x => x.replace(/\\\|/g, '');
let block = [], idx = [], bad = [];
const check = () => {
  if (block.length >= 2) {
    const counts = block.map(x => (strip(x).match(/\|/g) || []).length);
    const u = [...new Set(counts)];
    if (u.length > 1) bad.push('lines ' + idx.join(',') + '  pipes=' + counts.join('/'));
  }
  block = []; idx = [];
};
for (let i = 0; i < M.length; i++) {
  if (M[i].startsWith('|')) { block.push(M[i]); idx.push(i + 1); } else check();
}
check();
console.log(bad.length ? 'INCONSISTENT:\n' + bad.join('\n') : 'OK: all table blocks consistent');
