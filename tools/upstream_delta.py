#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quantify "upstream-inherited vs in-house" by diffing ARIS skills against
Modex skill identifiers recovered from the Cython .pyd string table.

Network: uses api.github.com (verified reachable from this host).
"""
import base64
import json
import os
import re
import sys
import urllib.request

API = "https://api.github.com"
REPO = "wanshuiyin/Auto-claude-code-research-in-sleep"
OUT = r"E:\02_Installers\DailyApps\Modex-MH-Agent-RE\reports"
STRINGS = r"E:\02_Installers\DailyApps\Modex-MH-Agent-RE\strings"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "re-analysis", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=60) as fh:
        return json.loads(fh.read().decode("utf-8"))


def fetch_aris_skill_names():
    tree = get("%s/repos/%s/git/trees/main?recursive=1" % (API, REPO))
    names = set()
    for node in tree.get("tree", []):
        p = node["path"]
        m = re.match(r"^skills/(?:skills-codex/)?([^/]+)/SKILL\.md$", p)
        if m:
            names.add(m.group(1))
    return sorted(names), tree


def modex_identifiers():
    """Collect candidate skill/template identifiers from extracted strings."""
    tokens = set()
    path = os.path.join(STRINGS, "_merged_strings.txt")
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            for tok in re.findall(r"[a-z][a-z0-9_]{3,40}", line):
                tokens.add(tok)
    return tokens


def main():
    os.makedirs(OUT, exist_ok=True)
    aris, tree = fetch_aris_skill_names()
    print("ARIS skills found:", len(aris))
    with open(os.path.join(OUT, "aris-skills.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(aris))

    tokens = modex_identifiers()
    print("Modex identifier tokens:", len(tokens))

    # hyphen -> underscore so ARIS names are comparable to Python identifiers
    aris_us = {n.replace("-", "_"): n for n in aris}
    hit = sorted(k for k in aris_us if k in tokens)
    miss = sorted(k for k in aris_us if k not in tokens)

    lines = []
    lines.append("# ARIS(上游) vs Modex(蓝方) skill 标识符差分")
    lines.append("")
    lines.append("ARIS 仓库: https://github.com/%s" % REPO)
    lines.append("")
    lines.append("## ARIS 全部 skill (%d)" % len(aris))
    lines.append("")
    lines.append(", ".join("`%s`" % n for n in aris))
    lines.append("")
    lines.append("## 在 Modex 的 .pyd 字符串表中直接命中 (%d/%d)" % (len(hit), len(aris)))
    lines.append("")
    lines.append("> 命中 = 该 skill 名（`-`→`_`）作为标识符出现在 Modex 编译产物里，")
    lines.append("> 说明该 skill 名被蓝方沿用为内部标识符（强同源证据）。")
    lines.append("")
    for k in hit:
        lines.append("- `%s`  (ARIS: `%s`)" % (k, aris_us[k]))
    lines.append("")
    lines.append("## 未在 Modex 字符串表中命中 (%d)" % len(miss))
    lines.append("")
    for k in miss:
        lines.append("- `%s`" % aris_us[k])
    lines.append("")

    # Modex-side workflow templates declared in schema.sql comments
    schema = r"E:\02_Installers\DailyApps\Modex-MH-Agent\resources\app\backend\db\schema.sql"
    if os.path.exists(schema):
        with open(schema, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        m = re.search(r"template TEXT NOT NULL,\s*--\s*(.+)", text)
        if m:
            lines.append("## Modex schema.sql 声明的 workflow 模板")
            lines.append("")
            lines.append("`%s`" % m.group(1).strip())
            lines.append("")

    with open(os.path.join(OUT, "delta-aris-vs-modex.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print("hit=%d miss=%d" % (len(hit), len(miss)))
    print("overlap:", ", ".join(hit[:40]))


if __name__ == "__main__":
    main()
