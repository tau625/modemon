"""ARIS skill 骨架加载器。

用途
----
把上游 **ARIS**（`wanshuiyin/Auto-claude-code-research-in-sleep`）的
skill 骨架接进 modemon：解析 `SKILL.md` 的 frontmatter，把 skill 的
工具约束与提示词模板交给步骤执行器使用。

许可（必须保留）
----------------
上游仓库采用 **MIT License**：

    MIT License
    Copyright (c) 2026 wanshuiyin

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

完整文本见 `modemon/LICENSE-ARIS.txt`。

⚠️ MIT 的唯一硬性条件就是**保留版权声明与许可全文**。因此本目录下的
任何衍生文件都必须连同 `LICENSE-ARIS.txt` 一起分发。

SKILL.md 格式（实测上游）
------------------------
```yaml
---
name: figure-spec
description: "何时使用这个 skill……"
argument-hint: "[description-of-diagram]"
allowed-tools: Bash(*), Read, Write, Edit, mcp__codex__codex
---
# 标题
正文……
```
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

#: 上游标识（血缘追溯用）
UPSTREAM_REPO = "wanshuiyin/Auto-claude-code-research-in-sleep"
UPSTREAM_LICENSE = "MIT"
UPSTREAM_COPYRIGHT = "Copyright (c) 2026 wanshuiyin"

#: 默认 skill 根目录。
#:
#: ⚠️ 层级：本文件在 `modemon/backend/services/`，
#: `parents[2]` 才是 `modemon/`，skill 目录与 backend/、frontend/ 平级。
#: 用 `parents[1]` 会指向 `modemon/backend/skills`（不存在）。
DEFAULT_SKILL_ROOT = Path(__file__).resolve().parents[2] / "skills"

_FRONT_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)


@dataclass
class SkillSpec:
    """一个 skill 的解析结果。"""

    name: str
    description: str = ""
    argument_hint: str = ""
    allowed_tools: tuple[str, ...] = ()
    body: str = ""
    path: Optional[Path] = None

    @property
    def available(self) -> bool:
        return bool(self.name)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "argument_hint": self.argument_hint,
            "allowed_tools": list(self.allowed_tools),
            "body_chars": len(self.body),
            "path": str(self.path) if self.path else None,
            "upstream": UPSTREAM_REPO,
            "license": UPSTREAM_LICENSE,
        }


@dataclass
class SkillCatalog:
    """skill 集合。"""

    root: Path
    skills: dict[str, SkillSpec] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def get(self, name: str) -> Optional[SkillSpec]:
        return self.skills.get(name)

    def names(self) -> list[str]:
        return sorted(self.skills)

    def search(self, keyword: str) -> list[SkillSpec]:
        """按名称/描述关键词找 skill。"""
        k = keyword.lower().strip()
        if not k:
            return []
        out = []
        for s in self.skills.values():
            hay = (s.name + " " + s.description).lower()
            if k in hay:
                out.append(s)
        return sorted(out, key=lambda s: s.name)

    def as_dict(self) -> dict:
        return {
            "root": str(self.root),
            "count": len(self.skills),
            "errors": self.errors,
            "upstream": {
                "repo": UPSTREAM_REPO,
                "license": UPSTREAM_LICENSE,
                "copyright": UPSTREAM_COPYRIGHT,
                "license_file": "LICENSE-ARIS.txt",
            },
            "skills": [s.as_dict() for s in (self.skills[n] for n in self.names())],
        }


# ---------------------------------------------------------------------------
# frontmatter 解析
# ---------------------------------------------------------------------------


def _scalar(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v.strip()


def _parse_tools(v: str) -> tuple[str, ...]:
    """`Bash(*), Read, Write` → ('Bash(*)', 'Read', 'Write')"""
    parts = [p.strip() for p in v.split(",")]
    return tuple(p for p in parts if p)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """拆出 frontmatter 与正文。

    ⚠️ 不引入 YAML 依赖：上游 frontmatter 是**扁平的 key: value**，
    只需处理引号与列表。刻意最小实现，避免引入不可预测的解析差异。
    """
    m = _FRONT_RE.match(text)
    if not m:
        return {}, text
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip().lower()] = v
    return meta, text[m.end():]


def load_skill(path: Path) -> SkillSpec:
    """加载一个 `SKILL.md`。"""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return SkillSpec(name=p.stem, body="", path=p, description=f"读取失败: {exc}")

    meta, body = parse_frontmatter(text)
    return SkillSpec(
        name=_scalar(meta.get("name", "")) or p.parent.name or p.stem,
        description=_scalar(meta.get("description", "")),
        argument_hint=_scalar(meta.get("argument-hint", "")),
        allowed_tools=_parse_tools(meta.get("allowed-tools", "")),
        body=body,
        path=p,
    )


def load_catalog(root: Optional[Path] = None) -> SkillCatalog:
    """扫描 `skills/*/SKILL.md`。

    **回退到 `catalog.json`**：骨架期可能只有目录元数据、还没有
    SKILL.md 正文（建议按需引入而不是全量复制）。此时仍要能
    列出/检索 skill，所以用 catalog 的 name + description 建立
    「元数据条目」（`body` 为空、`path` 为 None 表示正文未引入）。
    """
    r = Path(root) if root else DEFAULT_SKILL_ROOT
    cat = SkillCatalog(root=r)
    if not r.is_dir():
        cat.errors.append(f"skill 根目录不存在: {r}")
        return cat

    for p in sorted(r.glob("*/SKILL.md")):
        s = load_skill(p)
        if not s.name:
            cat.errors.append(f"frontmatter 缺少 name: {p}")
            continue
        if s.name in cat.skills:
            cat.errors.append(f"skill 重名: {s.name}（{p}）")
            continue
        cat.skills[s.name] = s

    if not cat.skills:
        # 正文未引入：用 catalog.json 的元数据建骨架
        meta = load_catalog_json(r)
        for item in meta.get("skills", []):
            name = item.get("name")
            if not name or name in cat.skills:
                continue
            # catalog.json 只有 name/path/bytes，没有 description。
            # 用**名称分词**做可检索文本，否则按主题搜（如 architecture）
            # 会一无所获——实测过。
            tokens = name.replace("-", " ").replace("_", " ")
            cat.skills[name] = SkillSpec(
                name=name,
                description=f"{tokens}（正文未引入，见 {item.get('path', '')}）",
                body="",
                path=None,
            )
        if meta:
            cat.errors.append(
                f"正文未引入：仅从 catalog.json 建立 {len(cat.skills)} 条元数据条目")
    return cat


# ---------------------------------------------------------------------------
# 与步骤执行的衔接
# ---------------------------------------------------------------------------


def tools_for_skill(spec: SkillSpec) -> Optional[tuple[str, ...]]:
    """把 skill 的 `allowed-tools` 变成 `StepRunRequest.allowed_tools`。

    返回 None 表示该 skill 未声明工具约束（交给运行时默认）。
    """
    return spec.allowed_tools or None


def prompt_for_skill(spec: SkillSpec, *, argument: str = "") -> str:
    """生成该 skill 的提示词。

    上游 skill 用 `$ARGUMENTS` 占位（如 `Audit experiment integrity for: $ARGUMENTS`）。
    """
    body = spec.body
    if "$ARGUMENTS" in body:
        body = body.replace("$ARGUMENTS", argument or "（未提供参数）")
    head = f"# Skill: {spec.name}\n\n"
    if spec.description:
        head += f"> 用途：{spec.description}\n\n"
    if argument:
        head += f"参数：{argument}\n\n"
    return head + body


def load_catalog_json(root: Optional[Path] = None) -> dict:
    """读取 `skills/catalog.json`（含来源与许可声明）。"""
    p = (Path(root) if root else DEFAULT_SKILL_ROOT) / "catalog.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


__all__ = [
    "SkillSpec", "SkillCatalog", "load_skill", "load_catalog",
    "tools_for_skill", "prompt_for_skill", "load_catalog_json",
    "parse_frontmatter",
    "UPSTREAM_REPO", "UPSTREAM_LICENSE", "UPSTREAM_COPYRIGHT", "DEFAULT_SKILL_ROOT",
]
