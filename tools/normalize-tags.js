// Normalize 【`file:line`, ...】 evidence-only tags to [证据: file:line, ...]
const fs = require('fs');
const P = 'E:/02_Installers/DailyApps/Modex-MH-Agent-RE/reports/03-frontend.md';
let s = fs.readFileSync(P, 'utf8');
let n = 0;

s = s.replace(/【([^】]*)】/g, (full, inner) => {
  const hasBacktick = inner.includes('`');
  const isConfidence = /直接提取|推断|推测|反证/.test(inner);
  const isEvidence = /证据/.test(inner);
  if (hasBacktick && !isConfidence && !isEvidence) {
    n++;
    return '[证据: ' + inner.replace(/`/g, '') + ']';
  }
  if (isEvidence && hasBacktick) {
    n++;
    return '[证据: ' + inner.replace(/^证据[：:]\s*/, '').replace(/`/g, '') + ']';
  }
  return full;
});

fs.writeFileSync(P, s, 'utf8');
console.log('tags normalized:', n);
console.log('remaining [证据:]:', (s.match(/\[证据:/g) || []).length);
console.log('confidence markers:', (s.match(/【直接提取】/g) || []).length, (s.match(/【推断】/g) || []).length, (s.match(/【推测】/g) || []).length);
console.log('leftover bracket tags:', (s.match(/【[^】]*】/g) || []).length);
const uniq = [...new Set(s.match(/【[^】]*】/g) || [])];
console.log(uniq.slice(0, 20).join(' | '));
