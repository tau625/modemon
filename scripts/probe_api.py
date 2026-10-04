"""连通性自检：用配置里的执行者 / 评审者各发一次最小请求，验证端点、模型名与参数兼容性。

用法：
    .venv\\Scripts\\python.exe scripts\\probe_api.py
不会打印任何密钥内容，只显示是否已配置。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from modemon.config import load_config  # noqa: E402
from modemon.providers import build_provider  # noqa: E402

PLAIN_PROMPT = "请只回复两个字：收到"
JSON_PROMPT = '请只输出一个 json 对象：{"ok": true, "note": "连通测试"}'


def main() -> int:
    cfg = load_config()
    failed = 0
    for role in ("executor", "reviewer"):
        model = cfg.models[role]
        provider_cfg = cfg.provider_cfg(role)
        key_state = "已配置" if provider_cfg.resolve_key() else "缺失"
        print(f"\n[{role}] provider={model.provider}  model={model.model}")
        print(f"        base_url={provider_cfg.base_url}")
        print(f"        key_env={provider_cfg.api_key_env}  key={key_state}  json_mode={model.json_mode}")

        if not provider_cfg.resolve_key():
            print("        → 跳过：密钥未配置")
            failed += 1
            continue

        prompt = JSON_PROMPT if model.json_mode else PLAIN_PROMPT
        try:
            provider = build_provider(model, provider_cfg, retry=1, timeout=120)
            resp = provider.complete([{"role": "user", "content": prompt}], meta={"role": role, "stage_id": "probe"})
            text = resp.text.replace("\n", " ")[:120]
            print(f"        → 成功  {resp.duration_s:.2f}s  usage={resp.usage or '（未返回）'}")
            print(f"          回复：{text}")
        except Exception as exc:  # noqa: BLE001
            print(f"        → 失败：{type(exc).__name__}: {str(exc)[:400]}")
            failed += 1

    print(f"\n结论：{'全部通过' if failed == 0 else f'{failed} 个角色未通过'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
