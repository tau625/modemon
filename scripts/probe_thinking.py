"""探测小米 MiMo 端点对"思考模式"的控制方式与耗时影响。

背景：实测执行者单次调用耗时 ~289s（思考 token 上万）。如果能按环节关闭或降档思考，
整条流水线会快数倍。此脚本逐个试候选参数，记录是否被接受、耗时与思考 token 数。

用法：.venv\\Scripts\\python.exe scripts\\probe_thinking.py
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from openai import OpenAI

PROMPT = "1+1 等于几？只回答数字。"
MAX_TOKENS = 200
PER_CALL_TIMEOUT = 150

VARIANTS: list[tuple[str, dict]] = [
    ("baseline(默认思考)", {}),
    ("reasoning_effort=low", {"reasoning_effort": "low"}),
    ("enable_thinking=False", {"extra_body": {"enable_thinking": False}}),
    ("thinking.type=disabled", {"extra_body": {"thinking": {"type": "disabled"}}}),
    ("chat_template_kwargs", {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}),
]


def load_env() -> None:
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    load_env()
    client = OpenAI(
        base_url="https://token-plan-cn.xiaomimimo.com/v1",
        api_key=os.environ["XIAOMI_API_KEY"],
        timeout=PER_CALL_TIMEOUT,
    )
    print(f"{'变体':28} {'结果':6} {'耗时(s)':>8} {'输出tok':>8} {'思考tok':>8}  回复")
    for name, kwargs in VARIANTS:
        started = time.perf_counter()
        try:
            resp = client.chat.completions.create(
                model="mimo-v2.6-flash",
                messages=[{"role": "user", "content": PROMPT}],
                max_tokens=MAX_TOKENS,
                **kwargs,
            )
            elapsed = time.perf_counter() - started
            usage = resp.usage
            details = getattr(usage, "completion_tokens_details", None)
            reasoning = getattr(details, "reasoning_tokens", None)
            content = (resp.choices[0].message.content or "").replace("\n", " ")[:24]
            print(f"{name:28} {'OK':6} {elapsed:8.1f} {usage.completion_tokens:8} {str(reasoning):>8}  {content!r}")
        except Exception as exc:  # noqa: BLE001
            elapsed = time.perf_counter() - started
            print(f"{name:28} {'FAIL':6} {elapsed:8.1f} {'-':>8} {'-':>8}  {type(exc).__name__}: {str(exc)[:120]}")


if __name__ == "__main__":
    main()
