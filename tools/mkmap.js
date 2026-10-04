const fs = require('fs');
const IN = 'E:/02_Installers/DailyApps/Modex-MH-Agent-RE/reports/_fx/callsites.txt';
const OUT = 'E:/02_Installers/DailyApps/Modex-MH-Agent-RE/reports/_fx/endpoint-map.tsv';
const t = fs.readFileSync(IN, 'utf8');
const blocks = t.split('### ').filter(Boolean);
const seen = new Set();
const out = [];
for (const b of blocks) {
  const f = b.split('\n')[0].trim();
  const u = (b.match(/URL: (.*)/) || [])[1] || '';
  const after = (b.match(/AFTER: (.*)/) || [])[1] || '';
  const before = (b.match(/BEFORE: \.\.\.(.*)/) || [])[1] || '';
  let method = 'GET';
  const m = after.match(/method:\s*[`'"]([A-Z]+)[`'"]/);
  if (m) method = m[1];
  else if (/^\s*,\s*\{\s*method:/.test(after)) method = '?';
  const k = f + '|' + u + '|' + method;
  if (seen.has(k)) continue;
  seen.add(k);
  out.push([f.replace(/\.js$/, ''), method, u, before.slice(-45).replace(/\t/g, ' ')].join('\t'));
}
fs.writeFileSync(OUT, out.join('\n'), 'utf8');
console.log('rows', out.length);
