'use strict';
// Read the Electron fuse wire directly out of the shipped executable.
const fs = require('fs');
const SENTINEL = Buffer.from('dL7pKGdnNz796PbbjQWNKmHXBZaB9tsX', 'ascii');
const exe = process.argv[2];
const raw = fs.readFileSync(exe);
const off = raw.indexOf(SENTINEL);
console.log('exe:', exe, 'size:', raw.length);
console.log('sentinel offset:', off, '(0x' + off.toString(16) + ')');
const header = off + SENTINEL.length;
const version = raw[header];
const length = raw[header + 1];
const wire = raw.subarray(header + 2, header + 2 + length).toString('ascii');
console.log('fuse version:', version, 'length:', length, 'wire:', wire);
const NAMES = [
  'RunAsNode',
  'EnableCookieEncryption',
  'EnableNodeOptionsEnvironmentVariable',
  'EnableNodeCliInspectArguments',
  'EnableEmbeddedAsarIntegrityValidation',
  'OnlyLoadAppFromAsar',
  'LoadBrowserProcessSpecificV8Snapshot',
  'GrantFileProtocolExtraPrivileges',
];
wire.split('').forEach((c, i) => {
  const label = c === '1' ? 'ENABLED ' : c === '0' ? 'disabled' : c === 'r' ? 'REMOVED ' : '?' + c;
  console.log(`  [${i}] ${label} ${NAMES[i] || '(unknown fuse)'}`);
});
// ASAR integrity block: does the exe embed an app.asar header hash?
const marker = Buffer.from('{"files":{', 'utf8');
const idx = raw.indexOf(marker);
console.log('embedded asar-integrity JSON candidate offset:', idx);
if (idx >= 0) console.log('  ...' + raw.subarray(idx, idx + 200).toString('utf8').replace(/[^\x20-\x7e]/g, '.'));
