#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dump Python 3.11 .pyc: original source path, names, consts, disassembly.

Usage: python pyc_dump.py <pyc_root> <out_root>
"""
import dis
import io
import marshal
import os
import struct
import sys
import json

MAGIC_311 = 3495  # 0x0DA5 -> CPython 3.11


def read_code(path):
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < 16:
        return None, {}
    magic = struct.unpack("<H", data[:2])[0]
    flags = struct.unpack("<I", data[4:8])[0]
    meta = {
        "magic": magic,
        "flags": flags,
        "header_len": 16,
    }
    try:
        code = marshal.loads(data[16:])
    except Exception as exc:  # pragma: no cover
        try:
            code = marshal.loads(data[12:])
            meta["header_len"] = 12
        except Exception:
            return None, {"error": str(exc), **meta}
    return code, meta


def collect(code, out, depth=0):
    """Walk nested code objects collecting structure."""
    entry = {
        "qualname": code.co_qualname,
        "name": code.co_name,
        "filename": code.co_filename,
        "firstlineno": code.co_firstlineno,
        "argcount": code.co_argcount,
        "posonly": getattr(code, "co_posonlyargcount", 0),
        "kwonly": code.co_kwonlyargcount,
        "nlocals": code.co_nlocals,
        "varnames": list(code.co_varnames),
        "cellvars": list(code.co_cellvars),
        "freevars": list(code.co_freevars),
        "names": list(code.co_names),
        "documentation": None,
        "consts": [],
        "children": [],
    }
    if code.co_consts and isinstance(code.co_consts[0], str):
        # conventional docstring slot
        if code.co_name != "<module>":
            entry["documentation"] = code.co_consts[0]
    for c in code.co_consts:
        if isinstance(c, str):
            entry["consts"].append(c)
        elif isinstance(c, (int, float, bool)) or c is None:
            entry["consts"].append(c)
        elif isinstance(c, (bytes,)):
            entry["consts"].append("<bytes:%d>" % len(c))
        elif isinstance(c, tuple):
            entry["consts"].append("<tuple:%d>" % len(c))
        elif isinstance(c, frozenset):
            entry["consts"].append("<frozenset:%d>" % len(c))
        elif hasattr(c, "co_code"):
            entry["children"].append(collect(c, out, depth + 1))
    return entry


def dis_text(code):
    buf = io.StringIO()
    try:
        dis.dis(code, file=buf, depth=None)
    except TypeError:
        dis.dis(code, file=buf)
    return buf.getvalue()


def main():
    root, out_root = sys.argv[1], sys.argv[2]
    os.makedirs(out_root, exist_ok=True)
    index = []
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if not fn.endswith(".pyc"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            code, meta = read_code(full)
            if code is None:
                index.append({"file": rel, "error": meta.get("error", "unreadable")})
                continue
            struct_dump = collect(code, out_root)
            asm = dis_text(code)
            stem = rel.replace(os.sep, "__").replace(".pyc", "")
            with open(os.path.join(out_root, stem + ".dis.txt"), "w", encoding="utf-8") as fh:
                fh.write("# original filename: %s\n# module: %s\n\n" % (code.co_filename, code.co_name))
                fh.write(asm)
            index.append({
                "file": rel,
                "orig_source_path": code.co_filename,
                "module_doc": struct_dump.get("documentation"),
                "n_names": len(code.co_names),
                "names": list(code.co_names),
                "const_strings": [c for c in code.co_consts if isinstance(c, str)],
                "structure": struct_dump,
                "meta": meta,
            })
    with open(os.path.join(out_root, "_index.json"), "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=1)
    print("pyc files analysed:", len(index))
    for e in index:
        if "error" in e:
            print("  ERROR", e["file"], e["error"])
        else:
            print("  %-46s <- %s" % (e["file"], e["orig_source_path"]))


if __name__ == "__main__":
    main()
