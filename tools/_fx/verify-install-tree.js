'use strict';
// Cross-check: does the installed resources/app tree match the Ed25519-signed manifest?
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const installRoot = process.argv[2];              // e.g. E:\...\Modex-MH-Agent
const appRoot = path.join(installRoot, 'resources', 'app');
const manifestPath = path.join(appRoot, 'security', 'runtime-integrity-manifest.json');
const sigPath = path.join(appRoot, 'security', 'runtime-integrity-manifest.sig.json');

const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
const sig = JSON.parse(fs.readFileSync(sigPath, 'utf8'));
const out = [];
const EXCLUDED = new Set(['security/runtime-integrity-manifest.json', 'security/runtime-integrity-manifest.sig.json']);

function sha256(file) {
  const h = crypto.createHash('sha256');
  h.update(fs.readFileSync(file));
  return h.digest('hex');
}

// 1) enumerate actual tree
const actual = [];
(function walk(dir, rel) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name, 'en'))) {
    const r = rel ? rel + '/' + e.name : e.name;
    const full = path.join(dir, e.name);
    const st = fs.lstatSync(full);
    if (st.isSymbolicLink()) { out.push(`SYMLINK: ${r}`); continue; }
    if (st.isDirectory()) walk(full, r);
    else if (st.isFile()) { if (!EXCLUDED.has(r)) actual.push({ rel: r, size: st.size }); }
  }
})(appRoot, '');
actual.sort((a, b) => a.rel.localeCompare(b.rel, 'en'));

out.push(`manifest.files.length      = ${manifest.files.length}`);
out.push(`actual files on disk       = ${actual.length}`);
const signed = new Map(manifest.files.map(f => [f.rel, f]));
const onDisk = new Set(actual.map(f => f.rel));
const missing = manifest.files.filter(f => !onDisk.has(f.rel)).map(f => f.rel);
const extra = actual.filter(f => !signed.has(f.rel)).map(f => f.rel);
out.push(`signed but MISSING on disk  = ${missing.length}${missing.length ? ': ' + missing.slice(0, 40).join(', ') : ''}`);
out.push(`on disk but UNSIGNED        = ${extra.length}${extra.length ? ': ' + extra.slice(0, 40).join(', ') : ''}`);

// 2) verify hashes of the signed file list (full 48 MB)
let mismatch = 0, checked = 0;
const bad = [];
for (const f of manifest.files) {
  const p = path.join(appRoot, ...f.rel.split('/'));
  let st;
  try { st = fs.lstatSync(p); } catch { continue; }
  if (!st.isFile()) continue;
  checked++;
  if (st.size !== f.size || sha256(p) !== f.sha256) { mismatch++; if (bad.length < 20) bad.push(`${f.rel} (size ${st.size} vs ${f.size})`); }
}
out.push(`hash re-verified            = ${checked} files, mismatches = ${mismatch}${bad.length ? ': ' + bad.join('; ') : ''}`);

// 3) runtime_files (critical runtime closure) - verify only the small/select ones plus app.asar
let rtBad = 0, rtChecked = 0;
const rtBadList = [];
for (const f of manifest.runtime_files) {
  const p = path.join(installRoot, ...f.rel.split('/'));
  let st;
  try { st = fs.lstatSync(p); } catch { rtBad++; if (rtBadList.length < 20) rtBadList.push('MISSING ' + f.rel); continue; }
  if (st.size !== f.size) { rtBad++; if (rtBadList.length < 20) rtBadList.push(`SIZE ${f.rel} ${st.size} != ${f.size}`); continue; }
  rtChecked++;
}
out.push(`runtime_files present+size  = ${rtChecked}/${manifest.runtime_files.length}, anomalies = ${rtBad}${rtBadList.length ? ': ' + rtBadList.join('; ') : ''}`);

// 4) full-hash the critical baseline list only (cheap, small) + app.asar
const CRITICAL = ['resources/app.asar', 'runtime/python/python.exe', 'runtime/python/python311.dll',
  'runtime/python/python311.zip', 'runtime/python/python311._pth', 'runtime/python/libcrypto-3.dll',
  'runtime/python/libssl-3.dll', 'runtime/python/_hashlib.pyd', 'runtime/python/_ssl.pyd',
  'runtime/node/node.exe', 'runtime/node/node_modules/@anthropic-ai/claude-code/bin/claude.exe',
  'runtime/git/bin/bash.exe', 'runtime/pandoc/pandoc.exe'];
const rtMap = new Map(manifest.runtime_files.map(f => [f.rel, f]));
out.push('--- critical runtime hashes ---');
for (const rel of CRITICAL) {
  const rec = rtMap.get(rel);
  const p = path.join(installRoot, ...rel.split('/'));
  if (!rec) { out.push(`  ${rel}: NOT IN MANIFEST`); continue; }
  if (!fs.existsSync(p)) { out.push(`  ${rel}: MISSING ON DISK (manifest size ${rec.size})`); continue; }
  const st = fs.statSync(p);
  const ok = st.size === rec.size && sha256(p) === rec.sha256;
  out.push(`  ${rel}: ${ok ? 'MATCH' : 'MISMATCH'} (disk ${st.size} / manifest ${rec.size})`);
}

// 5) signature shape
out.push('');
out.push(`signature: key_id=${sig.key_id} algorithm=${sig.algorithm} key_id_matches_manifest=${sig.key_id === manifest.key_id}`);
out.push(`manifest.runtime_files count = ${manifest.runtime_files.length}`);

fs.writeFileSync(process.argv[3], out.join('\n') + '\n', 'utf8');
process.stdout.write(out.join('\n') + '\n');
