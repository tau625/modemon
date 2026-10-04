#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch and cache upstream ARIS metadata locally so later analysis is offline.

Writes E:\\...\\upstream-ARIS-cache.json with:
  { fetched_at, skills:[...], py_paths:[...], catalog_md:"..." }

Idempotent: skips the network entirely when the cache already exists.
"""
import base64
import json
import os
import re
import sys
import time
import urllib.request

API = "https://api.github.com"
REPO = "wanshuiyin/Auto-claude-code-research-in-sleep"
CACHE = r"E:\02_Installers\DailyApps\Modex-MH-Agent-RE\upstream-ARIS-cache.json"


def gh(path, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(
                "%s/repos/%s/%s" % (API, REPO, path),
                headers={"User-Agent": "re-analysis", "Accept": "application/vnd.github+json"},
            )
            with urllib.request.urlopen(req, timeout=45) as fh:
                return json.loads(fh.read().decode("utf-8"))
        except Exception as exc:  # transient timeouts are common here
            last = exc
            time.sleep(2 * (i + 1))
    raise last


def main():
    force = "--force" in sys.argv
    if os.path.exists(CACHE) and not force:
        with open(CACHE, "r", encoding="utf-8") as fh:
            c = json.load(fh)
        print("cache hit: skills=%d py=%d (use --force to refresh)"
              % (len(c["skills"]), len(c["py_paths"])))
        return

    tree = gh("git/trees/main?recursive=1")
    paths = [n["path"] for n in tree["tree"]]
    skills = sorted({re.match(r"^skills/(?:skills-codex/)?([^/]+)/SKILL\.md$", p).group(1)
                     for p in paths if re.match(r"^skills/(?:skills-codex/)?([^/]+)/SKILL\.md$", p)})
    py_paths = sorted(p for p in paths if p.endswith(".py"))

    catalog = ""
    for n in tree["tree"]:
        if n["path"] == "docs/SKILLS_CATALOG.md":
            blob = gh("git/blobs/%s" % n["sha"])
            catalog = base64.b64decode(blob["content"]).decode("utf-8", "replace")
            break

    with open(CACHE, "w", encoding="utf-8") as fh:
        json.dump({
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "repo": REPO,
            "skills": skills,
            "py_paths": py_paths,
            "catalog_md": catalog,
        }, fh, ensure_ascii=False, indent=1)
    print("cached: skills=%d py=%d catalog=%d chars -> %s"
          % (len(skills), len(py_paths), len(catalog), CACHE))


if __name__ == "__main__":
    main()
