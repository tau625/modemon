#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract printable strings (ASCII + UTF-8/UTF-16LE) from binary files.

Cython-compiled .pyd modules keep every Python-level literal in .rdata, so this
recovers route paths, SQL, prompt text, error codes and symbol names.

Usage: python strings_dump.py <root_or_file> <out_dir> [min_len]
"""
import os
import re
import sys

def _compile(min_len):
    ascii_re = re.compile(("[\x20-\x7e]{%d,}" % min_len).encode("ascii"))
    utf16_re = re.compile((r"(?:[\x20-\x7e]\x00){%d,}" % min_len).encode("ascii"), re.DOTALL)
    return ascii_re, utf16_re


def strings_from(data, min_len):
    ascii_re, utf16_re = _compile(min_len)
    out = []
    for m in ascii_re.finditer(data):
        out.append(("ascii", m.group().decode("ascii", "replace")))
    for m in utf16_re.finditer(data):
        raw = m.group()
        try:
            s = raw.decode("utf-16-le")
        except Exception:
            continue
        if len(s) >= min_len:
            out.append(("utf16", s))
    return out


def main():
    target, out_dir = sys.argv[1], sys.argv[2]
    min_len = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    os.makedirs(out_dir, exist_ok=True)

    files = []
    if os.path.isfile(target):
        files = [target]
    else:
        for dirpath, _d, fns in os.walk(target):
            for fn in fns:
                if fn.lower().endswith((".pyd", ".so", ".dll", ".exe")):
                    files.append(os.path.join(dirpath, fn))

    # merged output, cheaply de-duplicated while keeping order
    merged = {}
    for full in files:
        rel = os.path.relpath(full, os.path.dirname(target) if os.path.isfile(target) else target)
        with open(full, "rb") as fh:
            data = fh.read()
        items = strings_from(data, min_len)
        stem = rel.replace(os.sep, "__")
        with open(os.path.join(out_dir, stem + ".strings.txt"), "w", encoding="utf-8") as fh:
            for kind, s in items:
                fh.write(s + "\n")
        for _kind, s in items:
            merged.setdefault(s, set()).add(rel)
        print("%-60s %8d strings  %8.1f MB" % (rel, len(items), len(data) / 1048576.0))

    with open(os.path.join(out_dir, "_merged_strings.txt"), "w", encoding="utf-8") as fh:
        for s in merged:
            fh.write(s + "\n")
    print("\nunique strings:", len(merged))
    print("merged ->", os.path.join(out_dir, "_merged_strings.txt"))


if __name__ == "__main__":
    main()
