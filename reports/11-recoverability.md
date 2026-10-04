# 后端可复现性量化评估

**问题**：Modex 的后端（176 个源文件 / 172 个 Cython `.pyd`）能被复现到什么程度？

**方法**：Cython 编译后，**函数名（qualname）与 docstring 会保留在字符串表中**，
而**函数体逻辑不会**。因此可复现性 ≈ 我们能恢复多少「接口规格」，
再加上多少「行为描述」。下面逐模块量化。

## 总览

| 指标 | 值 |
|---|---|
| 后端源文件（构建清单口径） | **166** |
| 编译模块（.pyd/.pyc） | **200** |
| 恢复出的**函数级符号**（已剔除 `__pyx_*` 内部名） | **2625** |
| 恢复出的**业务语义文本**（docstring/日志/错误信息/策略注释） | **1960** |
| 已识别并剔除的**解释器样板串**（噪声，非产品知识） | 11440 |

> ⚠️ 初版脚本把 13400 条
> 全部计为产品知识，其中绝大多数实为 CPython/Cython 运行时错误消息
> （如 `can't send non-None value to a just-started coroutine`）。
> 现已剔除。**保留这条修正记录**，以免高估可复现性。

> ⚠️ 关键：**函数体实现（算法、SQL、状态转移）零恢复**。
> 符号与文本只能界定「有什么函数、大致干什么」，不能给出「怎么做的」。

## 逐模块恢复度（按符号数排序，前 45）

| 模块 | 函数符号 | 行为描述 | 相对恢复度 |
|---|---|---|---|
| `routers__editor` | 107 | 23 | **高**（接口清晰） |
| `services__workflow_engine` | 101 | 64 | **高**（接口清晰） |
| `services__chat_executor` | 69 | 14 | 中 |
| `routers__chat` | 57 | 8 | 中 |
| `routers__workflows` | 53 | 14 | 中 |
| `services__artifact_patch` | 50 | 13 | 中 |
| `routers__chat_internal` | 43 | 10 | 中 |
| `services__agent_state` | 38 | 8 | 中 |
| `services__state_store` | 32 | 6 | 中 |
| `services__chat_memory` | 31 | 14 | 中 |
| `services__paper_modeling_quality` | 31 | 12 | 中 |
| `routers__artifacts` | 30 | 6 | 中 |
| `services__skill_crypto` | 30 | 11 | 中 |
| `services__access_mode` | 29 | 11 | 中 |
| `services__cli_gateway_proxy` | 29 | 14 | 中 |
| `services__workspace_cleanup` | 29 | 8 | 中 |
| `main` | 28 | 22 | 中 |
| `services__chat_materials` | 28 | 5 | 中 |
| `services__claude_runner` | 27 | 18 | 中 |
| `services__license_guard` | 26 | 17 | 中 |
| `routers__newapi_account` | 25 | 4 | 中 |
| `services__chat_run_events` | 25 | 8 | 中 |
| `services__editor_runs` | 25 | 4 | 中 |
| `routers__settings` | 24 | 3 | 中 |
| `services__chat_queue` | 24 | 3 | 中 |
| `services__claude_session_store` | 24 | 12 | 中 |
| `services__editor_exports` | 24 | 7 | 中 |
| `services__editor_transactions` | 24 | 7 | 中 |
| `services__instance_guard` | 24 | 3 | 中 |
| `services__paper_readiness` | 24 | 8 | 中 |
| `services__runtime_guard` | 24 | 6 | 中 |
| `services__account_messages_codec` | 23 | 4 | 中 |
| `routers__account` | 22 | 4 | 中 |
| `services__editor_contract` | 22 | 17 | 中 |
| `services__license_v2_client` | 22 | 5 | 中 |
| `services__model_context` | 22 | 8 | 中 |
| `services__paper_submission_contract` | 22 | 16 | 中 |
| `services__artifact_graph` | 21 | 7 | 中 |
| `services__chat_decisions` | 21 | 3 | 中 |
| `services__chat_contract` | 20 | 5 | 中 |
| `services__chat_registry` | 20 | 4 | 中 |
| `services__focused_runtime` | 19 | 4 | 中 |
| `services__account_credits` | 18 | 3 | 中 |
| `services__account_execution` | 18 | 10 | 中 |
| `services__chat_stage_progress` | 18 | 6 | 中 |

## 恢复度为「几乎无」的模块（0 个）

这些模块只恢复了模块名与 `__pyx_*` 内部符号，**没有任何语义信息**：


