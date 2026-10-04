"""模型服务层：统一的 OpenAI 兼容客户端 + 离线 Mock。

设计要点：
- 一个角色（executor / reviewer）绑定一个 ModelCfg，可指向任意 OpenAI 兼容端点，
  因此"换一家模型当评审者"只需改配置，不用改业务代码。
- 只发送配置里显式给出的参数；服务端不认的参数（如思考模式的 temperature）会被自动剔除后重试。
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from modemon.config import ModelCfg, ProviderCfg

LOGGER = logging.getLogger("mma.providers")

# 价格表（USD / 1M tokens）。取"高峰未命中价"作为保守估计，避免低估成本。
# 官方低谷价为高峰价的一半；中国法定节假日全天按低谷计。
PRICES_USD_PER_MTOK: dict[str, dict[str, float]] = {
    "deepseek-flash": {"in_miss": 0.30, "in_hit": 0.006, "out": 1.20},
    "deepseek-v4-pro": {"in_miss": 1.32, "in_hit": 0.044, "out": 3.96},
}


def estimate_cost_usd(model: str, usage: dict[str, int], price: dict[str, float] | None = None) -> float:
    """按价格表估算成本。price 为空时回落到内置表；都没有则返回 0（只统计用量）。"""
    table = price or PRICES_USD_PER_MTOK.get(model)
    if not table:
        return 0.0
    miss = usage.get("prompt_cache_miss_tokens")
    if miss is None:
        miss = max(0, usage.get("prompt_tokens", 0) - usage.get("prompt_cache_hit_tokens", 0))
    hit = usage.get("prompt_cache_hit_tokens", 0)
    out = usage.get("completion_tokens", 0)
    return (
        miss * float(table.get("in_miss", 0.0))
        + hit * float(table.get("in_hit", 0.0))
        + out * float(table.get("out", 0.0))
    ) / 1_000_000


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    duration_s: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)
    price: dict[str, float] | None = None  # 来自 configs 的 pricing 段
    finish_reason: str | None = None       # "length" 表示被 max_tokens 截断

    @property
    def truncated(self) -> bool:
        return self.finish_reason == "length"

    @property
    def cost_usd(self) -> float:
        return estimate_cost_usd(self.model, self.usage, self.price)


class LLMError(RuntimeError):
    pass


class LLMProvider(ABC):
    name = "base"

    def __init__(self, cfg: ModelCfg, provider_cfg: ProviderCfg | None = None, *, retry: int = 3,
                 timeout: float = 900.0, pricing: dict[str, dict[str, float]] | None = None) -> None:
        self.cfg = cfg
        self.provider_cfg = provider_cfg
        self.retry = max(1, retry)
        self.timeout = timeout
        self.pricing = pricing or {}

    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        meta: dict[str, Any] | None = None,
        thinking: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        ...

    @property
    def model(self) -> str:
        return self.cfg.model


class OpenAICompatProvider(LLMProvider):
    """任何 OpenAI 兼容端点：DeepSeek / ModelScope / 硅基流动 / 自建中转。"""

    name = "openai_compat"

    def __init__(self, cfg: ModelCfg, provider_cfg: ProviderCfg, *, retry: int = 3, timeout: float = 900.0,
                 pricing: dict[str, dict[str, float]] | None = None) -> None:
        super().__init__(cfg, provider_cfg, retry=retry, timeout=timeout, pricing=pricing)
        api_key = provider_cfg.resolve_key()
        if not api_key:
            raise LLMError(
                f"环境变量 {provider_cfg.api_key_env} 未设置：请复制 .env.example 为 .env 并填入 Key"
            )
        from openai import OpenAI  # 延迟导入，未装也能用 mock 模式

        self._client = OpenAI(base_url=provider_cfg.base_url, api_key=api_key, timeout=timeout)

    def _build_kwargs(
        self,
        messages: list[dict[str, str]],
        *,
        drop: set[str],
        thinking: str | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        cfg = self.cfg
        kwargs: dict[str, Any] = {"model": cfg.model, "messages": messages}
        limit = max_tokens or cfg.max_tokens
        if "max_tokens" not in drop and limit:
            kwargs["max_tokens"] = limit
        if "temperature" not in drop and cfg.temperature is not None:
            kwargs["temperature"] = cfg.temperature
        if "reasoning_effort" not in drop and cfg.reasoning_effort:
            kwargs["reasoning_effort"] = cfg.reasoning_effort
        if "response_format" not in drop and cfg.json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        # 思考模式开关：环节级设置优先于模型级设置；"off" 可显著降低耗时与输出 token
        mode = thinking if thinking is not None else cfg.thinking
        if mode in ("on", "off") and "thinking" not in drop:
            extra = dict(kwargs.get("extra_body") or {})
            extra["thinking"] = {"type": "enabled" if mode == "on" else "disabled"}
            kwargs["extra_body"] = extra
        return kwargs

    @staticmethod
    def _looks_unsupported(message: str) -> bool:
        lowered = message.lower()
        keywords = ("unsupported", "not support", "does not support", "invalid", "unknown", "unexpected", "unrecognized")
        return any(k in lowered for k in keywords)

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        meta: dict[str, Any] | None = None,
        thinking: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        drop: set[str] = set()
        last_err: Exception | None = None
        disable_thinking = False  # 思考吃光输出预算时，退化为关闭思考重试

        for attempt in range(1, self.retry + 1):
            started = time.time()
            try:
                resp = self._client.chat.completions.create(
                    **self._build_kwargs(
                        messages, drop=drop,
                        thinking="off" if disable_thinking else thinking,
                        max_tokens=max_tokens,
                    )
                )
            except Exception as exc:  # noqa: BLE001 —— 统一成带诊断信息的 LLMError
                msg = str(exc)
                lowered = msg.lower()
                # 服务端不接受的参数：剔除后立即重试，不计入退避
                candidate = None
                if self._looks_unsupported(msg):
                    for param in ("thinking", "reasoning_effort", "temperature", "response_format", "max_tokens"):
                        if param in lowered or (param == "thinking" and "extra_body" in lowered):
                            candidate = param
                            break
                if candidate and candidate not in drop:
                    drop.add(candidate)
                    continue
                last_err = exc
                if attempt < self.retry:
                    time.sleep(min(2 ** attempt, 20))
                continue

            duration = time.time() - started
            choice = resp.choices[0] if resp.choices else None
            text = (choice.message.content or "") if choice else ""
            if not text.strip():
                reasoning = getattr(choice.message, "reasoning_content", None) if choice else None
                if reasoning and not disable_thinking:
                    # 真实遭遇过：思考 4 万多字符把 max_tokens 全部吃光，正文为空。
                    # 这类失败不该让整条流水线挂掉，自动关闭思考再试一次。
                    LOGGER.warning(
                        "模型只产出思考、正文为空（思考 %d 字符），改为关闭思考模式重试", len(reasoning)
                    )
                    disable_thinking = True
                    continue
                snippet = f"（reasoning_content 长度 {len(reasoning)}）" if reasoning else ""
                raise LLMError(f"模型返回空内容：model={self.cfg.model} {snippet}")

            usage: dict[str, int] = {}
            u = getattr(resp, "usage", None)
            if u is not None:
                for key in ("prompt_tokens", "completion_tokens", "total_tokens",
                            "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"):
                    val = getattr(u, key, None)
                    if isinstance(val, int):
                        usage[key] = val
                # 思考型模型：记录思考 token，便于观察预算消耗
                ctd = getattr(u, "completion_tokens_details", None)
                reasoning = getattr(ctd, "reasoning_tokens", None) if ctd is not None else None
                if isinstance(reasoning, int):
                    usage["reasoning_tokens"] = reasoning
                # 部分端点把缓存命中数放在 prompt_tokens_details.cached_tokens
                ptd = getattr(u, "prompt_tokens_details", None)
                cached = getattr(ptd, "cached_tokens", None) if ptd is not None else None
                if isinstance(cached, int) and "prompt_cache_hit_tokens" not in usage:
                    usage["prompt_cache_hit_tokens"] = cached
                if "prompt_cache_hit_tokens" in usage and "prompt_cache_miss_tokens" not in usage:
                    usage["prompt_cache_miss_tokens"] = max(
                        0, usage.get("prompt_tokens", 0) - usage["prompt_cache_hit_tokens"]
                    )

            finish_reason = getattr(choice, "finish_reason", None) if choice else None
            if finish_reason == "length":
                LOGGER.warning(
                    "输出被 max_tokens 截断（model=%s, limit=%s）：建议提高该环节的 max_tokens 或分章节生成",
                    self.cfg.model, max_tokens or self.cfg.max_tokens,
                )

            return LLMResponse(
                text=text.strip(),
                model=self.cfg.model,
                provider=self.provider_cfg.base_url if self.provider_cfg else self.name,
                usage=usage,
                duration_s=duration,
                meta=meta or {},
                price=self.pricing.get(self.cfg.model),
                finish_reason=finish_reason,
            )

        raise LLMError(f"调用失败（已重试 {self.retry} 次）：{last_err}")


# --------------------------------------------------------------------------------------
# 离线 Mock：不消耗任何额度即可跑通整条流水线，用于验证管道与回归测试
# --------------------------------------------------------------------------------------

_MOCK_SOLVE = '''```python
# file: solve/main.py
"""求解脚本（mock 数据，用于离线验证流水线）。"""
import json
import os

import numpy as np

np.random.seed(42)
os.makedirs("results", exist_ok=True)

t = np.linspace(0, 24, 241)
level = 10 + 5 * np.sin(2 * np.pi * t / 24) + np.random.normal(0, 0.3, t.size)
peak_idx = int(np.argmax(level))
result = {
    "问题1": {"峰值": round(float(level[peak_idx]), 4), "峰值时刻": round(float(t[peak_idx]), 2)},
    "问题2": {"均值": round(float(level.mean()), 4), "标准差": round(float(level.std()), 4)},
}
with open("results/q1.json", "w", encoding="utf-8") as fh:
    json.dump(result, fh, ensure_ascii=False, indent=2)
print("RESULT_JSON " + json.dumps(result, ensure_ascii=False))
```'''

_MOCK_FIGURES = '''```python
# file: figures/make_figures.py
"""制图脚本（mock 数据）。"""
import json
import os

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt
import numpy as np

os.makedirs("figures", exist_ok=True)
os.makedirs("results", exist_ok=True)

with open("results/q1.json", encoding="utf-8") as fh:
    data = json.load(fh)

t = np.linspace(0, 24, 241)
level = 10 + 5 * np.sin(2 * np.pi * t / 24)

fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot(t, level, color="#1f77b4", linewidth=2, label="水位模拟")
ax.axhline(data["问题2"]["均值"], color="#d62728", linestyle="--", label="均值")
ax.scatter([data["问题1"]["峰值时刻"]], [data["问题1"]["峰值"]], color="black", zorder=5, label="峰值")
ax.set_xlabel("时间 (h)")
ax.set_ylabel("水位 (m)")
ax.set_title("水位变化与峰值定位")
ax.legend()
ax.grid(alpha=0.3)
fig.savefig("figures/fig1_water_level.png", dpi=300, bbox_inches="tight")
print("FIGURES_OK")
```'''

_MOCK_LATEX = '''```latex
% file: paper/main.tex
\\documentclass[12pt,a4paper]{ctexart}
\\usepackage{amsmath,amssymb,graphicx,booktabs,geometry,hyperref}
\\geometry{left=2.5cm,right=2.5cm,top=2.5cm,bottom=2.5cm}
\\title{基于时序分析的数学建模示例论文}
\\author{Modemon}
\\date{\\today}
\\begin{document}
\\maketitle
\\begin{abstract}
本文针对示例赛题建立时序模型，峰值水位为 应填入真实数值 米，出现在 应填入真实数值 小时。
\\end{abstract}
\\section{问题重述}
\\section{模型假设}
\\section{符号说明}
\\section{模型的建立与求解}
\\begin{equation}
y(t) = A\\sin(\\omega t + \\varphi) + C
\\end{equation}
\\section{模型检验}
\\section{灵敏度分析}
\\section{模型的评价与推广}
\\begin{thebibliography}{9}
\\bibitem{ref1} 示例参考文献（待补充真实文献）。
\\end{thebibliography}
\\end{document}
```'''


class MockProvider(LLMProvider):
    """确定性离线提供方：让整条流水线（含真实执行与评审回路）不花钱即可验证。"""

    name = "mock"

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        meta: dict[str, Any] | None = None,
        thinking: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        meta = meta or {}
        role = meta.get("role", "executor")
        stage_id = meta.get("stage_id", "")
        rnd = int(meta.get("round", 0))

        if role == "reviewer":
            total = 7.5 if rnd <= 1 else 9.2
            payload = {
                "stage": stage_id,
                "scores": {"正确性": total - 0.2, "完整性": total, "可复现性": total + 0.1,
                           "规范性": total - 0.3, "创新性": total - 0.5},
                "total": total,
                "verdict": "pass" if total >= 8.5 else "revise",
                "strong_points": ["结构基本完整"],
                "issues": [{"severity": "中", "location": "全文", "problem": "（mock）部分数值缺少出处标注",
                            "fix": "在每个数值后标注其来源文件与字段"}],
                "must_fix": ["为所有数值补充来源标注"] if total < 8.5 else [],
                "next_focus": "数值溯源",
            }
            text = json.dumps(payload, ensure_ascii=False)
        elif stage_id in ("solve_code",):
            text = "下面是求解代码。\n\n" + _MOCK_SOLVE
        elif stage_id == "figures":
            text = "下面是制图代码。\n\n" + _MOCK_FIGURES
        elif stage_id == "paper_writing":
            text = "下面是论文 LaTeX 源码。\n\n" + _MOCK_LATEX
        elif stage_id == "latex_fix":
            text = "已修复编译错误，输出完整文件。\n\n" + _MOCK_LATEX
        elif stage_id == "problem_analysis":
            text = (
                "# 赛题解析（mock）\n\n## 1. 背景与情境\n示例场景。\n\n## 2. 已知条件与数据清单\n"
                "| 编号 | 名称 | 数值/范围 | 单位 | 来源 | 备注 |\n|---|---|---|---|---|---|\n| D1 | 水位 | 5~15 | m | 题中第 2 段 | — |\n\n"
                "## 3. 待解决问题\n- 问题 1：输入=时序数据，处理=峰值检测，输出=峰值与时刻\n"
                "- 问题 2：输入=时序数据，处理=统计量，输出=均值与标准差\n\n"
                "## 4. 隐含假设（初判）\n- 假设 1：采样间隔均匀，依据：题目给出等间隔记录\n\n"
                "## 5. 关键难点与陷阱\n- 噪声干扰峰值定位\n\n## 6. 建模方向候选\n- 方向 A：时序分解（推荐）\n"
            )
        elif stage_id == "modeling_design":
            text = (
                "# 建模设计（mock）\n\n## 1. 模型假设\n- 假设 1：周期为 24h\n\n## 2. 符号说明\n"
                "| 符号 | 含义 | 单位 | 类型 |\n|---|---|---|---|\n| $A$ | 振幅 | m | 参数 |\n\n"
                "## 3. 模型建立\n目标函数 $\\min \\sum (y_i - \\hat y_i)^2$，参数 $A=5, C=10$。\n\n"
                "## 4. 模型检验方案\n留一法交叉验证。\n\n## 5. 灵敏度分析方案\n扰动 $A$ 与 $C$ ±10%。\n\n"
                "## 6. 模型评价与推广\n优点：可解释；缺点：未考虑随机扰动。\n"
            )
        elif stage_id == "paper_outline":
            text = (
                "# 论文大纲（mock）\n\n## 1. 标题与摘要要点\n- 标题：基于时序分析的建模\n- 摘要要点：峰值 12.3 m（来源 results/q1.json）\n\n"
                "## 2. 章节结构表\n| 章节 | 篇幅 | 核心内容 | 图表 | 评分点 |\n|---|---|---|---|---|\n"
                "| 摘要 | 1 页 | 方法与结论 | — | 摘要 |\n| 问题重述 | 1 页 | — | — | 完整 |\n\n"
                "## 3. 图表清单\n| 编号 | 类型 | 标题 | 来源 | 章节 |\n|---|---|---|---|---|\n| 图 1 | 折线 | 水位变化 | figures/fig1_water_level.png | 第 4 节 |\n\n"
                "## 4. 公式与符号规划\n$y(t)=A\\sin(\\omega t+\\varphi)+C$\n\n## 5. 结论要点\n- 问题 1：峰值 12.3 m\n"
            )
        else:
            text = f"# {stage_id}（mock 产出）\n\n（此内容由离线 Mock 生成，仅用于验证流水线。）\n"

        return LLMResponse(
            text=text,
            model=f"mock/{stage_id or role}",
            provider="mock",
            usage={"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300},
            duration_s=0.0,
            meta=meta,
        )


def build_provider(
    cfg: ModelCfg,
    provider_cfg: ProviderCfg | None,
    *,
    mock: bool = False,
    retry: int = 3,
    timeout: float = 900.0,
    pricing: dict[str, dict[str, float]] | None = None,
) -> LLMProvider:
    if mock:
        return MockProvider(cfg, provider_cfg, retry=retry, timeout=timeout, pricing=pricing)
    if provider_cfg is None:
        raise LLMError(f"服务商 {cfg.provider!r} 未配置")
    return OpenAICompatProvider(cfg, provider_cfg, retry=retry, timeout=timeout, pricing=pricing)
