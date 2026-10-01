"""配置加载：默认配置 + 流水线 + 竞赛 Profile，支持环境变量与 CLI 覆盖。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, field_validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _normalize_thinking(value: object) -> object:
    """YAML 1.1 会把 on/off/yes/no 解析成布尔值，这里统一归一成字符串。"""
    if isinstance(value, bool):
        return "on" if value else "off"
    return value


class ModelCfg(BaseModel):
    provider: str = "deepseek"
    model: str = "deepseek-flash"
    temperature: float | None = 0.3
    max_tokens: int = 16000
    json_mode: bool = False
    reasoning_effort: str | None = None
    # 思考模式："on" 强制开启 / "off" 关闭（省时省钱）/ None 用服务端默认
    thinking: str | None = None

    _norm_thinking_model = field_validator("thinking", mode="before")(_normalize_thinking)


class ProviderCfg(BaseModel):
    base_url: str
    api_key_env: str
    api_key: str | None = None

    def resolve_key(self) -> str | None:
        if self.api_key:
            return self.api_key
        val = os.environ.get(self.api_key_env, "").strip()
        return val or None


class RunCfg(BaseModel):
    output_dir: str = "runs"
    max_review_rounds: int = 2
    pass_score: float = 8.5
    require_no_blockers: bool = True  # 有"高严重度"问题时即使总分达标也判不通过
    request_timeout_s: int = 900
    execute_timeout_s: int = 600
    retry: int = 3
    solve_python: str | None = None  # 跑生成代码用的解释器；留空则用当前解释器
    # 论文编译闭环
    compile_paper: bool = True       # 流水线跑完自动编译论文
    max_compile_rounds: int = 2      # 编译失败时自动回修的最大轮数
    latex_engine: str = "xelatex"
    compile_timeout_s: int = 300
    checkpoints: list[str] = []       # 在这些环节完成后暂停等待人工确认（交互模式下生效）
    # 上下文预算：上游产物注入下游提示词的上限（字符）。
    # 太小会丢信息（论文环节曾只看到建模方案的三分之一），太大则吃 token 与费用。
    context_per_artifact: int = 20000
    context_total: int = 160000
    heartbeat_s: float = 60.0         # 长调用期间每多少秒发一次"仍在等待"事件（0=关闭）
    repair_max_tokens: int = 64000    # 编译回修要重发整篇论文，预算需与长文环节相当


class StageCfg(BaseModel):
    id: str
    title: str
    skill: str
    kind: Literal["text", "code"] = "text"
    review: bool = False
    execute: bool = False
    artifact: str = ""
    thinking: str | None = None  # 覆盖该环节的思考模式："on"/"off"/None=跟随模型配置
    max_tokens: int | None = None  # 覆盖该环节的输出上限（长文环节需要更大预算）

    _norm_thinking_stage = field_validator("thinking", mode="before")(_normalize_thinking)


class AppConfig(BaseModel):
    root: Path
    run: RunCfg
    models: dict[str, ModelCfg]
    providers: dict[str, ProviderCfg]
    stages: list[StageCfg]
    competition: dict[str, Any] = {}
    pricing: dict[str, dict[str, float]] = {}   # 模型价格表，用于估算成本（USD / 1M tokens）

    def provider_cfg(self, role: str) -> ProviderCfg:
        model = self.models[role]
        if model.provider not in self.providers:
            raise KeyError(
                f"配置里没有服务商 {model.provider!r}（models.{role}.provider），"
                f"可选：{', '.join(sorted(self.providers))}"
            )
        return self.providers[model.provider]

    @property
    def skills_dir(self) -> Path:
        return self.root / "skills"

    @property
    def runs_dir(self) -> Path:
        d = Path(self.run.output_dir)
        return d if d.is_absolute() else self.root / d


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在：{path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"配置文件格式错误（顶层必须是映射）：{path}")
    return data


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_dotenv(root: Path) -> None:
    """读取 .env（不存在则静默跳过）。不覆盖已存在的真实环境变量。"""
    env_file = root / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def load_config(
    competition: str = "cumcm",
    root: Path | None = None,
    *,
    executor_model: str | None = None,
    reviewer_model: str | None = None,
    max_review_rounds: int | None = None,
    pass_score: float | None = None,
    thinking: str | None = None,
    checkpoints: list[str] | None = None,
) -> AppConfig:
    root = (root or PROJECT_ROOT).resolve()
    _load_dotenv(root)

    raw: dict[str, Any] = _read_yaml(root / "configs" / "default.yaml")
    raw = _deep_merge(raw, _read_yaml(root / "configs" / "pipeline.yaml"))

    comp_file = root / "configs" / "competitions" / f"{competition}.yaml"
    comp = _read_yaml(comp_file)
    comp.setdefault("id", competition)

    models = {k: ModelCfg(**v) for k, v in (raw.get("models") or {}).items()}
    providers = {k: ProviderCfg(**v) for k, v in (raw.get("providers") or {}).items()}
    stages = [StageCfg(**s) for s in (raw.get("stages") or [])]
    run = RunCfg(**(raw.get("run") or {}))

    if not stages:
        raise ValueError("流水线为空：请检查 configs/pipeline.yaml")
    if "executor" not in models or "reviewer" not in models:
        raise ValueError("配置缺少 models.executor 或 models.reviewer")

    # CLI 覆盖
    if executor_model:
        models["executor"].model = executor_model
    if reviewer_model:
        models["reviewer"].model = reviewer_model
    if max_review_rounds is not None:
        run.max_review_rounds = max_review_rounds
    if pass_score is not None:
        run.pass_score = pass_score
    if thinking in ("on", "off"):
        for role in ("executor", "reviewer"):
            models[role].thinking = thinking
    if checkpoints:
        run.checkpoints = list(checkpoints)

    return AppConfig(
        root=root,
        run=run,
        models=models,
        providers=providers,
        stages=stages,
        competition=comp,
        pricing={str(k): dict(v) for k, v in (raw.get("pricing") or {}).items() if isinstance(v, dict)},
    )
