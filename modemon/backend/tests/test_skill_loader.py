"""ARIS skill 骨架加载器测试。

重点：
  1. **许可合规**——MIT 的唯一硬性条件是保留版权声明与许可全文
  2. frontmatter 解析（含引号、工具列表）
  3. `$ARGUMENTS` 占位替换
  4. 目录扫描与重名检测
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from services import skill_loader as sl  # noqa: E402

PASS = 0
FAIL = 0
FAILURES: list[str] = []

MODEN = BACKEND.parent


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  %s" % name)
    else:
        FAIL += 1
        FAILURES.append(name)
        print("  FAIL  %s  %s" % (name, detail[:150]))


SAMPLE = """---
name: figure-spec
description: "Generate deterministic diagrams from JSON. Use when user says 架构图."
argument-hint: "[description-of-diagram]"
allowed-tools: Bash(*), Read, Write, Edit, mcp__codex__codex
---

# FigureSpec

正文段落。

为 $ARGUMENTS 生成图。
"""


def test_license_compliance() -> None:
    print("\n[1] ★ MIT 许可合规（唯一硬性条件）")
    lic = MODEN / "LICENSE-ARIS.txt"
    check("LICENSE-ARIS.txt 存在", lic.is_file(), str(lic))
    if lic.is_file():
        t = lic.read_text(encoding="utf-8", errors="replace")
        check("含 MIT 标识", "MIT License" in t)
        check("**含版权声明**（MIT 硬性条件）",
              "Copyright (c) 2026 wanshuiyin" in t, t[:200])
        check("含许可全文（MIT 硬性条件）",
              "Permission is hereby granted" in t and
              "THE SOFTWARE IS PROVIDED" in t)
        check("含免责声明", "WITHOUT WARRANTY OF ANY KIND" in t)

    cat = sl.load_catalog_json()
    if cat:
        up = cat.get("source", {})
        check("catalog 记录上游仓库", up.get("repo") == sl.UPSTREAM_REPO,
              str(up))
        check("catalog 记录许可", up.get("license") == "MIT", str(up))
        check("catalog 记录版权人", "wanshuiyin" in str(up.get("copyright", "")))
        check("catalog 指向许可文件", up.get("license_file") == "LICENSE-ARIS.txt")
    else:
        check("catalog.json 存在", False, "未找到 catalog.json")


def test_frontmatter() -> None:
    print("\n[2] frontmatter 解析")
    meta, body = sl.parse_frontmatter(SAMPLE)
    check("解析出 name", meta.get("name", "").strip() == "figure-spec", str(meta))
    check("保留带引号的 description",
          "deterministic" in meta.get("description", ""), str(meta)[:120])
    check("正文与 frontmatter 分离", body.strip().startswith("# FigureSpec"),
          body[:60])

    spec = sl.load_skill.__wrapped__ if hasattr(sl.load_skill, "__wrapped__") else None
    # 直接用临时文件验证
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "SKILL.md"
        p.write_text(SAMPLE, encoding="utf-8")
        s = sl.load_skill(p)
        check("name 取自 frontmatter", s.name == "figure-spec", s.name)
        check("description 去引号", s.description.startswith("Generate"), s.description[:60])
        check("argument_hint 正确", s.argument_hint == "[description-of-diagram]",
              s.argument_hint)
        check("**allowed-tools 拆成元组**",
              s.allowed_tools == ("Bash(*)", "Read", "Write", "Edit", "mcp__codex__codex"),
              str(s.allowed_tools))
        check("正文保留", "FigureSpec" in s.body)


def test_catalog_scan() -> None:
    print("\n[3] 目录扫描")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "a").mkdir(); (root / "b").mkdir(); (root / "c").mkdir()
        (root / "a" / "SKILL.md").write_text(SAMPLE, encoding="utf-8")
        (root / "b" / "SKILL.md").write_text(
            "---\nname: b\n---\n\nB 正文", encoding="utf-8")
        (root / "c" / "SKILL.md").write_text(
            "---\nname: figure-spec\n---\n\n重名", encoding="utf-8")

        cat = sl.load_catalog(root)
        check("扫描到 2 个有效 skill", len(cat.skills) == 2, str(cat.names()))
        check("重名被检测并记录", any("重名" in e for e in cat.errors), str(cat.errors))
        check("search 命中 description",
              bool(cat.search("architecture")) or bool(cat.search("deterministic")),
              str(cat.names()))
        check("search 大小写不敏感", bool(cat.search("FIGURE")))

    missing = sl.load_catalog(Path("no_such_dir"))
    check("目录不存在时报错而非抛异常",
          bool(missing.errors) and not missing.skills, str(missing.errors))


def test_prompt_and_tools() -> None:
    print("\n[4] 与步骤执行的衔接")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "SKILL.md"
        p.write_text(SAMPLE, encoding="utf-8")
        s = sl.load_skill(p)

        prompt = sl.prompt_for_skill(s, argument="某系统架构")
        check("**$ARGUMENTS 被替换**", "某系统架构" in prompt and "$ARGUMENTS" not in prompt,
              prompt[:160])
        check("prompt 含 skill 名", "figure-spec" in prompt)
        check("prompt 含描述", "deterministic" in prompt)

        noarg = sl.prompt_for_skill(s)
        check("无参数时给出占位说明", "$ARGUMENTS" not in noarg, noarg[:120])

        check("**allowed_tools 传给执行器**",
              sl.tools_for_skill(s) == s.allowed_tools, str(sl.tools_for_skill(s)))

        bare = sl.SkillSpec(name="bare")
        check("未声明工具约束时返回 None（交给运行时默认）",
              sl.tools_for_skill(bare) is None)


def test_provenance() -> None:
    print("\n[5] 血缘可追溯")
    check("声明上游仓库", sl.UPSTREAM_REPO.startswith("wanshuiyin/"))
    check("声明许可类型", sl.UPSTREAM_LICENSE == "MIT")
    check("声明版权人", "wanshuiyin" in sl.UPSTREAM_COPYRIGHT)
    src = (BACKEND / "services" / "skill_loader.py").read_text(encoding="utf-8")
    check("**源码内嵌 MIT 全文**（便于分发时保留）",
          "Permission is hereby granted" in src and
          "Copyright (c) 2026 wanshuiyin" in src)
    check("指向许可文件", "LICENSE-ARIS.txt" in src)


def test_catalog_fallback() -> None:
    print("\n[6] 正文未引入时的骨架回退")
    # 真实目录里可能只有 catalog.json（建议按需引入正文而非全量复制）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        import json
        (root / "catalog.json").write_text(json.dumps({
            "source": {"repo": sl.UPSTREAM_REPO, "license": "MIT"},
            "skills": [
                {"name": "figure-spec", "path": "skills/figure-spec/SKILL.md"},
                {"name": "experiment-audit", "path": "skills/experiment-audit/SKILL.md"},
            ],
        }, ensure_ascii=False), encoding="utf-8")

        cat = sl.load_catalog(root)
        check("**从 catalog.json 建立骨架**", len(cat.skills) == 2, str(cat.names()))
        check("明确标注正文未引入",
              any("正文未引入" in e for e in cat.errors), str(cat.errors))
        s = cat.get("figure-spec")
        check("元数据条目 body 为空（不假装有正文）", s is not None and s.body == "")
        check("path 为 None 表示正文未落地", s is not None and s.path is None)

        # 名称分词要让按主题检索可用
        check("**按主题可检索**", bool(cat.search("figure")), str(cat.names()))
        check("按多词主题可检索", bool(cat.search("audit")))
        check("检索 experiment 命中", any(x.name == "experiment-audit"
                                         for x in cat.search("experiment")))


def main() -> int:
    print("=" * 74)
    print("modemon ARIS skill 骨架测试（★ MIT 许可合规）")
    print("=" * 74)
    test_license_compliance()
    test_frontmatter()
    test_catalog_scan()
    test_prompt_and_tools()
    test_provenance()
    test_catalog_fallback()
    print("\n" + "=" * 74)
    print("PASS %d / FAIL %d" % (PASS, FAIL))
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print("  -", f)
    print("=" * 74)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
