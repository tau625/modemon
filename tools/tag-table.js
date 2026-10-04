// Append [证据: <chunk>.js ...] to each row of the §1 tech-stack table, derived from the .js names already cited in the row.
const fs = require('fs');
const P = 'E:/02_Installers/DailyApps/Modex-MH-Agent-RE/reports/03-frontend.md';
let s = fs.readFileSync(P, 'utf8');
const lines = s.split('\n');

const start = lines.findIndex(l => l.startsWith('## 1. 技术栈判定'));
const end = lines.findIndex((l, i) => i > start && l.startsWith('### 1.1'));
if (start < 0 || end < 0) { console.error('section not found', start, end); process.exit(1); }

let tagged = 0;
for (let i = start; i < end; i++) {
  const l = lines[i];
  if (!l.startsWith('|')) continue;
  if (/^\|\s*-+/.test(l)) continue;                 // separator
  if (l.startsWith('| 层次 ')) continue;             // header
  if (l.includes('[证据:')) continue;
  const js = [...new Set((l.match(/[A-Za-z0-9_.\-]+\.(?:pretty\.)?js/g) || [])
    .filter(x => !/^\.js$/.test(x)))];
  if (!js.length) continue;
  lines[i] = l.replace(/\s*\|\s*$/, ' ') + ` [证据: ${js.join(', ')}] |`;
  tagged++;
}
fs.writeFileSync(P, lines.join('\n'), 'utf8');
console.log('rows tagged:', tagged);
