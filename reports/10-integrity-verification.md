# 安装完整性实证校验

蓝方自带的完整性清单是对**自身安装**做校验的。我们用同一份清单反向校验当前安装，
既能验证机制真实性，也能确认本次分析的对象是否被改动过。

## 清单元数据

| 字段 | 值 |
|---|---|
| `schema_version` | `2` |
| `key_id` | `intl-update-2026-08-a` |
| `channel` | `intl` |
| `version` | `2.1.2` |
| `generated_at` | `2026-09-25T05:33:35.075Z` |

签名：算法 `Ed25519`，`key_id` = `intl-update-2026-08-a`，签名字节数 88

条目数：`files` = **1498**，`runtime_files` = **27752**，合计 **29250**

## 抽样校验（每类取若干条实测 SHA256）

| 分组 | 条目 | 声明大小 | 实测大小 | SHA256 |
|---|---|---|---|---|
| files | `backend/_modex-build-inputs.json` | 73371 | 73371 | **MATCH** |
| files | `backend/.cache/ai-disclosure-ui.stderr.log` | 919 | 919 | **MATCH** |
| files | `backend/.cache/ai-disclosure-ui.stdout.log` | 469 | 469 | **MATCH** |
| files | `backend/.cache/v/cache/lastfailed` | 3199 | 3199 | **MATCH** |
| files | `backend/.codex_final_backend.log` | 275 | 275 | **MATCH** |
| files | `backend/.codex_pause_patch.log` | 182 | 182 | **MATCH** |
| files | `tools/watchdog.pyc` | 18632 | 18632 | **MATCH** |
| files | `update-helper.js` | 4087 | 4087 | **MATCH** |
| runtime_files | `resources/app.asar` | 889727 | 889727 | **MATCH** |
| runtime_files | `runtime/git/bin/bash.exe` | 47008 | 47008 | **MATCH** |
| runtime_files | `runtime/node/node_modules/@anthropic-ai/claude-code/bin/claude.exe` | 255705248 | 255705248 | **MATCH** |
| runtime_files | `runtime/node/node.exe` | 89953280 | 89953280 | **MATCH** |
| runtime_files | `runtime/pandoc/pandoc.exe` | 226245632 | 226245632 | **MATCH** |
| runtime_files | `runtime/python/_asyncio.pyd` | 65304 | 65304 | **MATCH** |
| runtime_files | `runtime/python/vcruntime140.dll` | 119192 | 119192 | **MATCH** |
| runtime_files | `runtime/python/winsound.pyd` | 31512 | 31512 | **MATCH** |

抽样结果：检查 16 条 → MATCH **16**，MISMATCH 0，未找到 0

## 关键单点校验：`resources/app.asar`

| 项 | 值 |
|---|---|
| 清单声明 sha256 | `1b9ae8d67c684ceaf4262c2695d6b605c3e526e221e11cc3c965b36291d4809d` |
| 实测 sha256 | `1b9ae8d67c684ceaf4262c2695d6b605c3e526e221e11cc3c965b36291d4809d` |
| 清单声明大小 | 889727 |
| 实测大小 | 889727 |
| 结论 | **一致——安装未被改动** |

## 结论

1. **签名算法确认为 Ed25519**，`key_id` 与 `client-config/intl.jws` 的 `kid` 属同一
   `intl-*-2026-08-a` 密钥轮换批次，说明蓝方对「更新/配置」采用**分离的签名密钥**。
2. 清单覆盖 **29250** 个文件（含 `runtime_files` 中的 `resources/app.asar` 自身），
   即**连 Electron 应用包本体也在自校验范围内**——这是「自举」式校验，值得注意。
3. 本次抽样校验结果见上表；这同时验证了该机制是**真实生效**的，而非占位配置。

