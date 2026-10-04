// GFM: inside table rows, a literal | inside a code span must be escaped as \|
const fs = require('fs');
const P = 'E:/02_Installers/DailyApps/Modex-MH-Agent-RE/reports/03-frontend.md';
const lines = fs.readFileSync(P, 'utf8').split('\n');
let fixed = 0, rows = 0;
for (let i = 0; i < lines.length; i++) {
  const l = lines[i];
  if (!l.startsWith('|')) continue;
  rows++;
  let out = '';
  let inCode = false;
  for (let j = 0; j < l.length; j++) {
    const c = l[j];
    if (c === '`') { inCode = !inCode; out += c; continue; }
    if (c === '|' && inCode && l[j - 1] !== '\\') { out += '\\|'; fixed++; continue; }
    out += c;
  }
  lines[i] = out;
}
fs.writeFileSync(P, lines.join('\n'), 'utf8');
console.log('table rows:', rows, 'pipes escaped:', fixed);

// re-validate pipe consistency within each table block
const L = fs.readFileSync(P, 'utf8').split('\n');
let block = [], bad = [];
const check = () => {
  if (block.length < 2) { block = []; return; }
  const counts = block.map(x => (x.replace(/\\\|/g, '').match(/\|/g) || []).length);
  const u = [...new Set(counts)];
  if (u.length > 1) bad.push('lines ' + block.idx.join(',') + ' pipes=' + counts.join('/'));
  block = [];
};
for (let i = 0; i < L.length; i++) {
  if (L[i].startsWith('|')) { if (!block.length) block.idx = []; block.push(L[i]); block.idx.push(i + 1); }
  else check();
}
check();
console.log(bad.length ? 'INCONSISTENT BLOCKS:\n' + bad.join('\n') : 'all table blocks consistent');
