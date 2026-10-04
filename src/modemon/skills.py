"""Skill 引擎：加载 skills/<name>/SKILL.md（YAML front-matter + Jinja2 正文模板）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jinja2 import Environment

_ENV = Environment(trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)


class SkillError(RuntimeError):
    pass


@dataclass
class Skill:
    name: str
    title: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    body: str = ""
    path: Path | None = None

    def render(self, **context: object) -> str:
        try:
            return _ENV.from_string(self.body).render(**context).strip()
        except Exception as exc:  # noqa: BLE001
            raise SkillError(f"Skill {self.name} 模板渲染失败：{exc}") from exc


def _split_front_matter(text: str) -> tuple[dict, str]:
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return {}, text
    lines = stripped.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        raise SkillError("front-matter 缺少结束的 --- 分隔行")
    meta = yaml.safe_load("\n".join(lines[1:end])) or {}
    if not isinstance(meta, dict):
        raise SkillError("front-matter 不是合法的 YAML 映射")
    return meta, "\n".join(lines[end + 1 :])


def load_skill(name: str, skills_dir: Path) -> Skill:
    path = Path(skills_dir) / name / "SKILL.md"
    if not path.exists():
        raise SkillError(f"找不到 Skill：{path}")
    meta, body = _split_front_matter(path.read_text(encoding="utf-8"))
    return Skill(
        name=str(meta.get("name") or name),
        title=str(meta.get("title") or name),
        description=str(meta.get("description") or ""),
        tags=list(meta.get("tags") or []),
        inputs=list(meta.get("inputs") or []),
        outputs=list(meta.get("outputs") or []),
        body=body.strip(),
        path=path,
    )


def list_skills(skills_dir: Path) -> list[Skill]:
    base = Path(skills_dir)
    if not base.exists():
        return []
    skills: list[Skill] = []
    for d in sorted(base.iterdir()):
        if d.is_dir() and (d / "SKILL.md").exists():
            try:
                skills.append(load_skill(d.name, base))
            except SkillError:
                continue
    return skills
