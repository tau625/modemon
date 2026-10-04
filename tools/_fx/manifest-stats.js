'use strict';
// Analysis helper: statistics for the 5.8 MB runtime integrity manifest.
const fs = require('fs');
const path = require('path');

const file = process.argv[2];
const raw = fs.readFileSync(file);
const m = JSON.parse(raw.toString('utf8'));

const out = [];
out.push(`file: ${file}`);
out.push(`raw_bytes: ${raw.length} (${(raw.length / 1024 / 1024).toFixed(2)} MB)`);
out.push(`top_level_keys: ${Object.keys(m).sort().join(', ')}`);
out.push(`schema_version: ${m.schema_version}`);
out.push(`key_id: ${m.key_id}`);
out.push(`channel: ${m.channel}`);
out.push(`version: ${m.version}`);
out.push(`generated_at: ${m.generated_at}`);
out.push(`files.length: ${m.files.length}`);
out.push(`runtime_files.length: ${m.runtime_files.length}`);
const sum = a => a.reduce((s, f) => s + f.size, 0);
out.push(`files.total_bytes: ${sum(m.files)} (${(sum(m.files) / 1024 / 1024).toFixed(1)} MB)`);
out.push(`runtime_files.total_bytes: ${sum(m.runtime_files)} (${(sum(m.runtime_files) / 1024 / 1024).toFixed(1)} MB)`);

function ext(rel) {
  const base = rel.split('/').pop();
  const i = base.lastIndexOf('.');
  return i <= 0 ? '(noext)' : base.slice(i).toLowerCase();
}
function tally(list, label) {
  const byTop = new Map();
  const byExt = new Map();
  for (const f of list) {
    const top = f.rel.includes('/') ? f.rel.split('/')[0] : '(root)';
    const t = byTop.get(top) || { n: 0, b: 0 };
    t.n++; t.b += f.size; byTop.set(top, t);
    const e = ext(f.rel);
    const x = byExt.get(e) || { n: 0, b: 0 };
    x.n++; x.b += f.size; byExt.set(e, x);
  }
  out.push('');
  out.push(`## ${label} by top-level dir (count desc)`);
  for (const [k, v] of [...byTop.entries()].sort((a, b) => b[1].n - a[1].n)) {
    out.push(`  ${k}\t${v.n}\t${(v.b / 1024 / 1024).toFixed(2)} MB`);
  }
  out.push('');
  out.push(`## ${label} by extension (count desc, top 40)`);
  for (const [k, v] of [...byExt.entries()].sort((a, b) => b[1].n - a[1].n).slice(0, 40)) {
    out.push(`  ${k}\t${v.n}\t${(v.b / 1024 / 1024).toFixed(2)} MB`);
  }
}

tally(m.files, 'files');
tally(m.runtime_files, 'runtime_files');

out.push('');
out.push('## runtime_files full list (rel, size)');
for (const f of [...m.runtime_files].sort((a, b) => a.rel.localeCompare(b.rel, 'en'))) {
  out.push(`  ${f.rel}\t${f.size}`);
}

out.push('');
out.push('## largest 25 entries in files');
for (const f of [...m.files].sort((a, b) => b.size - a.size).slice(0, 25)) {
  out.push(`  ${f.rel}\t${f.size}`);
}

out.push('');
out.push('## depth distribution (files)');
const depth = new Map();
for (const f of m.files) {
  const d = f.rel.split('/').length;
  depth.set(d, (depth.get(d) || 0) + 1);
}
for (const [k, v] of [...depth.entries()].sort((a, b) => a[0] - b[0])) out.push(`  depth ${k}\t${v}`);

const target = process.argv[3];
if (target) fs.writeFileSync(target, out.join('\n') + '\n', 'utf8');
process.stdout.write(out.join('\n') + '\n');
