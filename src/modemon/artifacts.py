"""运行目录管理：所有产物、日志、状态都落在 runs/<run_id>/ 下，便于复现与追溯。"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

SUBDIRS = ("artifacts", "code", "results", "results/logs", "figures", "paper", "logs", "prompts")


def new_run_id(tag: str = "run") -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{tag}"


def slugify(text: str, fallback: str = "run") -> str:
    s = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", text).strip("-")
    return s[:40] or fallback


class RunDir:
    def __init__(self, root: Path, run_id: str, create: bool = True) -> None:
        self.root = Path(root)
        self.run_id = run_id
        self.path = self.root / run_id
        if create:
            self.path.mkdir(parents=True, exist_ok=True)
            for sub in SUBDIRS:
                (self.path / sub).mkdir(parents=True, exist_ok=True)

    # ---------- 路径 ----------
    @property
    def report_file(self) -> Path:
        return self.path / "report.json"

    @property
    def events_file(self) -> Path:
        return self.path / "logs" / "events.jsonl"

    def ensure_parent(self, rel: str | Path) -> Path:
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    # ---------- 写 ----------
    def write_text(self, rel: str | Path, text: str) -> Path:
        p = self.ensure_parent(rel)
        p.write_text(text, encoding="utf-8")
        return p

    def write_json(self, rel: str | Path, data: Any) -> Path:
        p = self.ensure_parent(rel)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return p

    def append_jsonl(self, rel: str | Path, data: Any) -> Path:
        p = self.ensure_parent(rel)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(data, ensure_ascii=False) + "\n")
        return p

    # ---------- 读 ----------
    def read_text(self, rel: str | Path) -> str:
        p = self.path / rel
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def exists(self, rel: str | Path) -> bool:
        return (self.path / rel).exists()

    def glob(self, pattern: str) -> list[Path]:
        return sorted(self.path.glob(pattern))

    # ---------- 状态 ----------
    def save_report(self, state: dict[str, Any]) -> Path:
        return self.write_json("report.json", state)

    def load_report(self) -> dict[str, Any]:
        if not self.report_file.exists():
            raise FileNotFoundError(f"运行不存在或缺少 report.json：{self.path}")
        return json.loads(self.report_file.read_text(encoding="utf-8"))


def list_runs(root: Path) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    if not root.exists():
        return runs
    for d in sorted(root.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        rep = d / "report.json"
        if not rep.exists():
            continue
        try:
            data = json.loads(rep.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        runs.append(
            {
                "run_id": d.name,
                "competition": data.get("competition"),
                "status": data.get("status"),
                "stage_index": data.get("stage_index"),
                "stages": len(data.get("stages") or []),
                "created_at": data.get("created_at"),
                "cost_usd": (data.get("usage") or {}).get("cost_usd", 0.0),
            }
        )
    return runs
