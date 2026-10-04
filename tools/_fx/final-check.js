'use strict';
const fs = require('fs');
const p = 'E:/02_Installers/DailyApps/Modex-MH-Agent-RE/reports/02-desktop-security.md';
const s = fs.readFileSync(p, 'utf8');
const fence = s.split('```').length - 1;
console.log('bytes:', Buffer.byteLength(s), 'lines:', s.split('\n').length);
console.log('code fences:', fence, '-> balanced:', fence % 2 === 0);
console.log('evidence tags [证据:', (s.match(/\[证据/g) || []).length);
console.log('【直接提取】:', (s.match(/【直接提取】/g) || []).length,
  ' 【推断】:', (s.match(/【推断】/g) || []).length,
  ' 【推测】:', (s.match(/【推测】/g) || []).length);
console.log('sections:');
for (const m of s.matchAll(/^## .*$/gm)) console.log('  ' + m[0]);
console.log('leftover "21 个敏感":', (s.match(/21 个敏感/g) || []).length);
console.log('marker left:', s.includes('APPEND-MARKER'));
