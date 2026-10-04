const fs = require('fs');
const path = require('path');
const DIST = 'E:/02_Installers/DailyApps/Modex-MH-Agent/resources/app/dist/assets';
const OUT = 'E:/02_Installers/DailyApps/Modex-MH-Agent-RE/tools/_fx/external-urls.txt';
const map = new Map();
for (const f of fs.readdirSync(DIST).filter(x => x.endsWith('.js'))) {
  const s = fs.readFileSync(path.join(DIST, f), 'utf8');
  const re = /https?:\/\/[^\s"'`\\)<>]+/g;
  let m;
  while ((m = re.exec(s))) {
    const k = f + '|' + m[0];
    map.set(k, (map.get(k) || 0) + 1);
  }
}
const rows = [...map.keys()].sort();
fs.writeFileSync(OUT, rows.join('\n'), 'utf8');
const byUrl = new Map();
for (const r of rows) { const [f, u] = r.split('|'); if (!byUrl.has(u)) byUrl.set(u, new Set()); byUrl.get(u).add(f); }
console.log('unique urls:', byUrl.size);
for (const [u, fs_] of [...byUrl.entries()].sort()) console.log([...fs_].join(',').slice(0, 60) + '\t' + u);
