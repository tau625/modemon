#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""High-precision CJK string extraction from Cython .pyd binaries.

Naive byte scanning produces false positives because x64 machine code contains
byte pairs in the E4-E9 / 80-BF ranges. Real string-table entries are filtered by
requiring a high CJK ratio plus only "text-like" characters.

Usage: python cjk_strings.py <backend_dir> <out_file>
"""
import os
import re
import sys

CJK_B = (
    b"(?:[\xe4-\xe9][\x80-\xbf]{2}"          # U+4E00-U+9FFF
    b"|\xe3\x80[\x80-\xbf]"                   # U+3000-U+303F
    b"|\xef[\xbc-\xbf][\x80-\xbf]"            # U+FF00-U+FFEF fullwidth
    b"|\xe2\x80[\x98-\x9d\xa6]"               # quotes / ellipsis
    b"|\xc2\xb7)"                             # middle dot
)
RUN = re.compile(b"(?:[\x20-\x7e]|" + CJK_B + b"){4,}")

# text-like after decoding: ascii printable, CJK, CJK punctuation, fullwidth,
# quotes, brackets, spaces. Anything else (box drawing, random symbols) is noise.
TEXTY = re.compile(
    r"^[\x20-\x7e\u3000-\u303f\u4e00-\u9fff\uff00-\uffef"
    r"\u2018\u2019\u201c\u201d\u2013\u2014\u2026\u00b7\u2192\u2190\u2264\u2265"
    r"\u00d7\u00f7\u2022\u25cf\u25a0\s]*$"
)


def score(s):
    cjk = sum(1 for c in s if "\u4e00" <= c <= "\u9fff")
    return cjk, cjk / max(1, len(s))


def main():
    base, out_file = sys.argv[1], sys.argv[2]
    min_cjk = 3
    min_ratio = 0.35

    per_module = {}
    for dp, _d, fns in os.walk(base):
        for fn in fns:
            if not fn.endswith(".pyd"):
                continue
            data = open(os.path.join(dp, fn), "rb").read()
            hits = []
            for m in RUN.finditer(data):
                raw = m.group()
                if not re.search(CJK_B, raw):
                    continue
                try:
                    s = raw.decode("utf-8")
                except Exception:
                    continue
                cjk, ratio = score(s)
                if cjk < min_cjk or ratio < min_ratio:
                    continue
                if not TEXTY.match(s):
                    continue
                hits.append(s.strip())
            if hits:
                per_module[fn] = sorted(set(hits))

    total = 0
    with open(out_file, "w", encoding="utf-8") as fh:
        fh.write("# 从 Cython .pyd 提取的高置信度中文串（按模块）\n\n")
        fh.write("过滤：CJK 字符 >= %d、CJK 占比 >= %.2f、仅文本类字符。\n\n" % (min_cjk, min_ratio))
        for fn in sorted(per_module):
            fh.write("## %s  (%d 条)\n\n" % (fn, len(per_module[fn])))
            for s in per_module[fn]:
                fh.write("- %s\n" % s)
            fh.write("\n")
            total += len(per_module[fn])
    print("modules with CJK: %d, total strings: %d -> %s" % (len(per_module), total, out_file))


if __name__ == "__main__":
    main()
