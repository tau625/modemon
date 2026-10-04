// Dependency-free JS beautifier: newline + indent on structural tokens.
// usage: node beautify.js <inputFile> <outputFile>
const fs = require('fs');

function isIdentChar(c) { return /[A-Za-z0-9_$]/.test(c); }

function beautify(src) {
  let out = '';
  let i = 0;
  let indent = 0;
  const n = src.length;
  let lastSignificant = ''; // for regex detection

  function nl() {
    // trim trailing spaces
    out = out.replace(/[ \t]+$/, '');
    out += '\n' + '  '.repeat(Math.max(0, indent));
  }

  while (i < n) {
    const c = src[i];
    // comments
    if (c === '/' && src[i + 1] === '/') {
      const e = src.indexOf('\n', i);
      const end = e === -1 ? n : e;
      out += src.slice(i, end);
      i = end;
      continue;
    }
    if (c === '/' && src[i + 1] === '*') {
      const e = src.indexOf('*/', i + 2);
      const end = e === -1 ? n : e + 2;
      out += src.slice(i, end);
      i = end;
      continue;
    }
    // strings
    if (c === '"' || c === "'") {
      let j = i + 1;
      while (j < n) {
        if (src[j] === '\\') { j += 2; continue; }
        if (src[j] === c) break;
        j++;
      }
      out += src.slice(i, Math.min(j + 1, n));
      i = Math.min(j + 1, n);
      lastSignificant = 'str';
      continue;
    }
    if (c === '`') {
      let j = i + 1;
      while (j < n) {
        if (src[j] === '\\') { j += 2; continue; }
        if (src[j] === '`') break;
        j++;
      }
      out += src.slice(i, Math.min(j + 1, n));
      i = Math.min(j + 1, n);
      lastSignificant = 'str';
      continue;
    }
    // regex literal heuristic
    if (c === '/') {
      const prev = out.replace(/\s+$/, '').slice(-1);
      const regexAllowed = !prev || /[=(,:[!&|?{};+\-*%^~<>]/.test(prev) ||
        /(?:^|\W)(return|typeof|case|in|of|new|delete|void|instanceof|do|else|yield|await)$/.test(out.replace(/\s+$/, ''));
      if (regexAllowed) {
        let j = i + 1, inClass = false, ok = false;
        while (j < n) {
          const d = src[j];
          if (d === '\\') { j += 2; continue; }
          if (d === '\n') break;
          if (d === '[') inClass = true;
          else if (d === ']') inClass = false;
          else if (d === '/' && !inClass) { ok = true; break; }
          j++;
        }
        if (ok) {
          j++;
          while (j < n && /[a-z]/.test(src[j])) j++;
          out += src.slice(i, j);
          i = j;
          lastSignificant = 're';
          continue;
        }
      }
    }
    // structure
    if (c === '{') {
      out += '{';
      indent++;
      nl();
      i++;
      continue;
    }
    if (c === '}') {
      indent = Math.max(0, indent - 1);
      out = out.replace(/[ \t]+$/, '');
      if (!out.endsWith('\n')) out += '\n' + '  '.repeat(indent);
      out += '}';
      i++;
      // peek: if next is ; , ) etc. keep inline
      const rest = src.slice(i).match(/^\s*/)[0];
      i += rest.length;
      const nx = src[i];
      if (nx === ';' || nx === ',' || nx === ')' || nx === ']' || nx === '}') {
        // continue inline
      } else {
        nl();
      }
      continue;
    }
    if (c === ';') {
      out += ';';
      i++;
      nl();
      continue;
    }
    if (c === '\n') { i++; continue; }
    if (c === '\r') { i++; continue; }
    out += c;
    i++;
  }
  return out;
}

const [inF, outF] = process.argv.slice(2);
const src = fs.readFileSync(inF, 'utf8');
const res = beautify(src);
fs.writeFileSync(outF, res, 'utf8');
console.log('in', src.length, '-> out', res.length, 'lines', res.split('\n').length);
