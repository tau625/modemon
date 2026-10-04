// Frontend bundle extraction toolkit (no deps).
// usage: node fx.js <mode> [args...]
const fs = require('fs');
const path = require('path');

const DIST = 'E:\\02_Installers\\DailyApps\\Modex-MH-Agent\\resources\\app\\dist\\assets';
const OUT = 'E:\\02_Installers\\DailyApps\\Modex-MH-Agent-RE\\reports\\_fx';

function files() {
  return fs.readdirSync(DIST).filter(f => f.endsWith('.js')).sort();
}
function read(f) { return fs.readFileSync(path.join(DIST, f), 'utf8'); }

function uniq(arr) { return [...new Set(arr)]; }

// ---------- mode: apis ----------
// Collect /api/... literals (single, double, backtick) and bare occurrences.
function modeApis() {
  const rows = [];
  for (const f of files()) {
    const s = read(f);
    const re = /["'`]\/api\/[^"'`\s\\]{0,160}/g;
    let m;
    while ((m = re.exec(s))) {
      rows.push({ f, lit: m[0].slice(1), i: m.index });
    }
    // also occurrences not preceded by quote (e.g. concatenated)
    const re2 = /\/api\/[A-Za-z0-9_\-{}\/.:$]{2,160}/g;
    while ((m = re2.exec(s))) {
      rows.push({ f, lit: m[0], i: m.index });
    }
  }
  // dedupe by file+lit, keep count
  const map = new Map();
  for (const r of rows) {
    const k = r.f + '|' + r.lit;
    if (!map.has(k)) map.set(k, { ...r, n: 0 }); 
    map.get(k).n++;
  }
  const all = [...map.values()].sort((a, b) => a.f.localeCompare(b.f) || a.lit.localeCompare(b.lit));
  const lines = all.map(r => `${r.f}\t${r.n}\t${r.lit}`);
  fs.writeFileSync(path.join(OUT, 'apis.tsv'), lines.join('\n'), 'utf8');
  console.log('api rows:', all.length);
  // path-only unique
  const paths = uniq(all.map(r => r.lit.split('?')[0]));
  fs.writeFileSync(path.join(OUT, 'apis-paths.txt'), paths.sort().join('\n'), 'utf8');
  console.log('unique paths:', paths.length);
}

// ---------- mode: ctx ----------
// node fx.js ctx <regexSource> <before> <after> [fileFilterRegex]
function modeCtx() {
  const [, , , patSrc, beforeS, afterS, filt] = process.argv;
  const pat = new RegExp(patSrc, 'g');
  const before = parseInt(beforeS || '80', 10), after = parseInt(afterS || '80', 10);
  const filtRe = filt ? new RegExp(filt) : null;
  const out = [];
  for (const f of files()) {
    if (filtRe && !filtRe.test(f)) continue;
    const s = read(f);
    let m;
    while ((m = pat.exec(s))) {
      out.push(`### ${f} @${m.index}\n${s.slice(Math.max(0, m.index - before), m.index + m[0].length + after).replace(/\n/g, '\\n')}\n`);
      if (out.length > 4000) break;
    }
  }
  fs.writeFileSync(path.join(OUT, 'ctx.txt'), out.join('\n'), 'utf8');
  console.log('ctx hits:', out.length);
}

// ---------- mode: strings ----------
// Extract all string literals & object keys from a file matching a filter.
function modeStrings() {
  const [, , , filt] = process.argv;
  const filtRe = new RegExp(filt);
  const set = new Set();
  for (const f of files()) {
    if (!filtRe.test(f)) continue;
    const s = read(f);
    const re = /"((?:[^"\\\n]|\\.){2,80})"|'((?:[^'\\\n]|\\.){2,80})'|`((?:[^`\\\n]|\\.){2,80})`/g;
    let m;
    while ((m = re.exec(s))) set.add(m[1] || m[2] || m[3]);
  }
  const arr = [...set].sort();
  fs.writeFileSync(path.join(OUT, 'strings.txt'), arr.join('\n'), 'utf8');
  console.log('strings:', arr.length);
}

// ---------- mode: keys ----------
// Extract identifier-like keys: key: , .key, key= etc. Filters to snake_case or camelCase words
function modeKeys() {
  const [, , , filt, minLen] = process.argv;
  const filtRe = new RegExp(filt);
  const min = parseInt(minLen || '4', 10);
  const set = new Set();
  for (const f of files()) {
    if (!filtRe.test(f)) continue;
    const s = read(f);
    const re = /([A-Za-z_$][A-Za-z0-9_$]{2,60})\s*:/g;
    let m;
    while ((m = re.exec(s))) if (m[1].length >= min) set.add(m[1]);
  }
  fs.writeFileSync(path.join(OUT, 'keys.txt'), [...set].sort().join('\n'), 'utf8');
  console.log('keys:', set.size);
}

// ---------- mode: ws ----------
function modeWs() {
  const out = [];
  for (const f of files()) {
    const s = read(f);
    const re = /(?:onmessage|addEventListener|type:|event:|action:|kind:|method:)\s*["'`]([A-Za-z0-9_.:\-]{3,60})["'`]/g;
    let m;
    while ((m = re.exec(s))) out.push(`${f}\t${m[0]}`);
  }
  fs.writeFileSync(path.join(OUT, 'ws.txt'), out.join('\n'), 'utf8');
  console.log('ws rows:', out.length);
}

const mode = process.argv[2];
const modes = { apis: modeApis, ctx: modeCtx, strings: modeStrings, keys: modeKeys, ws: modeWs };
if (!modes[mode]) { console.error('unknown mode', mode); process.exit(1); }
fs.mkdirSync(OUT, { recursive: true });
modes[mode]();
