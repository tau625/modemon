#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract strings incl. CJK from binaries via byte-level UTF-8/UTF-16 patterns.

CPython 3.11 stores str literals as ASCII (1B), UCS-2 (2B) or UCS-4 (4B); Cython
emits the static initialiser as a UTF-8 C literal, so CJK appears as UTF-8 bytes.
A bytes regex cannot use \\uXXXX escapes, hence the explicit byte ranges.

Usage: python strings_cjk.py <root_or_file> <out_dir> [min_len]
"""
import os
import re
import sys

# UTF-8 byte patterns for the ranges that matter for Chinese prose
CJK_B = (
    b"(?:"
    b"[\xe4-\xe9][\x80-\xbf]{2}"        # U+4E00-U+9FFF  CJK ideographs
    b"|\xe3\x80[\x80-\xbf]"             # U+3000-U+303F  CJK punctuation
    b"|\xef[\xbc-\xbf][\x80-\xbf]"      # U+FF00-U+FFEF  fullwidth forms
    b"|\xe2\x80[\x98-\x9d\xa6]"         # quotes / ellipsis
    b"|\xc2\xb7"                        # middle dot
    b")"
)
# UTF-16LE: BMP CJK -> low byte arbitrary, high byte 0x4E-0x9F
CJK_B16 = b"(?:[\x00-\xff][\x4e-\x9f])"


def build(min_len):
    ascii_re = re.compile((b"[\x20-\x7e]{%d,}" % min_len))
    utf8_re = re.compile((b"(?:[\x20-\x7e]|" + CJK_B + b"){%d,}" % min_len))
    utf16_re = re.compile((b"(?:[\x20-\x7e]\x00|" + CJK_B16 + b"){%d,}" % min_len))
    return ascii_re, utf8_re, utf16_re


def main():
    target, out_dir = sys.argv[1], sys.argv[2]
    min_len = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    os.makedirs(out_dir, exist_ok=True)

    files = []
    if os.path.isfile(target):
        files = [target]
    else:
        for dp, _d, fns in os.walk(target):
            for fn in fns:
                if fn.lower().endswith((".pyd", ".so", ".dll", ".exe")):
                    files.append(os.path.join(dp, fn))

    ascii_re, utf8_re, utf16_re = build(min_len)
    merged = set()

    for full in files:
        rel = os.path.basename(full)
        with open(full, "rb") as fh:
            data = fh.read()
        items = []
        for m in ascii_re.finditer(data):
            items.append(m.group().decode("ascii", "replace"))
        for m in utf8_re.finditer(data):
            raw = m.group()
            if not re.search(CJK_B, raw):
                continue
            try:
                items.append(raw.decode("utf-8"))
            except Exception:
                pass
        for m in utf16_re.finditer(data):
            raw = m.group()
            if not re.search(CJK_B16, raw):
                continue
            try:
                items.append(raw.decode("utf-16-le"))
            except Exception:
                pass

        zh = [s for s in items if any("\u4e00" <= ch <= "\u9fff" for ch in s)]
        with open(os.path.join(out_dir, rel + ".all.txt"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(items))
        with open(os.path.join(out_dir, rel + ".zh.txt"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(zh))
        merged.update(items)
        print("%-56s total=%6d zh=%5d" % (rel, len(items), len(zh)))

    with open(os.path.join(out_dir, "_merged.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(sorted(merged)))
    zh_all = sorted(s for s in merged if any("\u4e00" <= ch <= "\u9fff" for ch in s))
    with open(os.path.join(out_dir, "_merged_zh.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(zh_all))
    print("\nunique=%d  zh_unique=%d" % (len(merged), len(zh_all)))


if __name__ == "__main__":
    main()
