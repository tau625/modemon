const fs = require('fs');
const P = 'E:/02_Installers/DailyApps/Modex-MH-Agent-RE/reports/03-frontend.md';
const s = fs.readFileSync(P, 'utf8');
const fence = String.fromCharCode(96, 96, 96);
console.log('bytes', Buffer.byteLength(s, 'utf8'), 'chars', s.length, 'lines', s.split('\n').length);
console.log('headings', (s.match(/^#{1,3} /gm) || []).length);
console.log('[证据:] tags', (s.match(/\[证据:/g) || []).length);
console.log('markers: 直接提取', (s.match(/【直接提取】/g) || []).length,
  '| 推断', (s.match(/【推断】/g) || []).length,
  '| 推测', (s.match(/【推测】/g) || []).length);
console.log('table rows', s.split('\n').filter(l => l.startsWith('|')).length);
console.log('code fences (must be even)', (s.split(fence).length - 1));
console.log('sections:', (s.match(/^## .*/gm) || []).map(x => x.slice(0, 40)).join(' | '));
