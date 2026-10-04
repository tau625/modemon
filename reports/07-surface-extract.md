# 确定性表面提取（脚本产出，非人工推断）

本文件由 `tools/extract_surface.py` 从已采集的字符串表与 asar 源码直接生成，
**不含任何人工推断**，可视为原始证据索引。

## A. HTTP 路由

共提取到 **6** 条 `/api/...` 路径。

| 路由族 | 条数 | 路径 |
|---|---|---|
| `/api/editor` | 3 | `/api/editor`<br>`/api/editor/{wf_id}/serve`<br>`/api/editor/{wf_id}/serve/status` |
| `/api/palette-preview` | 1 | `/api/palette-preview` |
| `/api/settings` | 1 | `/api/settings` |
| `/api/style-preview` | 1 | `/api/style-preview` |

### 按所属模块（含这些路由字符串的 .pyd）

| 模块 | 路由数 |
|---|---|
| `(merged)` | 6 |
| `routers__chat_internal` | 1 |
| `routers__palette_preview` | 1 |
| `routers__project_preview` | 3 |
| `routers__style_preview` | 1 |
| `services__chat_ticket` | 1 |

## B. WebSocket / 事件通道

未提取到 `/ws/...` 形式的字面量（通道可能由常量拼接或在前端定义）。

## C. Electron IPC 通道

共 **13** 个通道名。

| 通道 | 出现在 |
|---|---|
| `dialog:pick-folder` | `main.js`, `preload.js` |
| `intl` | `main.js`, `updater.js` |
| `latex-install-progress` | `preload.js` |
| `latex:get-status` | `main.js`, `preload.js` |
| `latex:install` | `main.js`, `preload.js` |
| `update-available` | `preload.js` |
| `update-progress` | `preload.js` |
| `updater:abort` | `main.js`, `preload.js` |
| `updater:apply-and-restart` | `main.js`, `preload.js` |
| `updater:check-now` | `main.js`, `preload.js` |
| `updater:get-cached` | `main.js`, `preload.js` |
| `updater:skip-version` | `main.js`, `preload.js` |
| `updater:start-download` | `main.js`, `preload.js` |

## D. 后端模块符号表规模（qualname 计数）

从字符串表恢复的 `模块.限定名` 符号，可反映每个模块的公开面大小。

| 模块 | 符号数 | 顶层函数样例 |
|---|---|---|
| `workflow_engine` | 227 | `__defaults__`, `__pyx_defaults`, `__pyx_scope_struct_100_genexpr`, `__pyx_scope_struct_101_genexpr`, `__pyx_scope_struct_102_genexpr`, `__pyx_scope_struct_103_genexpr` |
| `editor` | 189 | `__defaults__`, `__pyx_defaults`, `__pyx_defaults1`, `__pyx_scope_struct_10_genexpr`, `__pyx_scope_struct_11_genexpr`, `__pyx_scope_struct_12_genexpr` |
| `chat_executor` | 109 | `__pyx_scope_struct_10_genexpr`, `__pyx_scope_struct_11__create_repair_proposal`, `__pyx_scope_struct_12_genexpr`, `__pyx_scope_struct_13_check_deps_for`, `__pyx_scope_struct_14__persist_progress`, `__pyx_scope_struct_15__publish_run_events` |
| `chat` | 103 | `__defaults__`, `__pyx_defaults`, `__pyx_scope_struct_10__pending_context`, `__pyx_scope_struct_11_genexpr`, `__pyx_scope_struct_12__active_runtime_context`, `__pyx_scope_struct_13_genexpr` |
| `workflows` | 85 | `__defaults__`, `__pyx_defaults`, `__pyx_scope_struct_10_get_one`, `__pyx_scope_struct_11_get_logs`, `__pyx_scope_struct_12_start`, `__pyx_scope_struct_13__stage_cli_resume_choice` |
| `artifact_patch` | 82 | `__defaults__`, `__pyx_defaults`, `__pyx_defaults1`, `__pyx_scope_struct_10_genexpr`, `__pyx_scope_struct_11_genexpr`, `__pyx_scope_struct_12_genexpr` |
| `chat_internal` | 55 | `__defaults__`, `__pyx_defaults`, `__pyx_scope_struct_10_state`, `__pyx_scope_struct_11_list_artifacts`, `__pyx_scope_struct_12_read_artifact`, `__pyx_scope_struct_13_read_image` |
| `claude_runner` | 53 | `__defaults__`, `__pyx_defaults`, `__pyx_scope_struct_10_genexpr`, `__pyx_scope_struct_11_genexpr`, `__pyx_scope_struct_12_run_skill`, `__pyx_scope_struct_13__run_skill_scoped` |
| `agent_state` | 52 | `__pyx_scope_struct_10_recover_committed_run`, `__pyx_scope_struct_11_genexpr`, `__pyx_scope_struct_12_choose_fork`, `__pyx_scope_struct_13_update`, `__pyx_scope_struct_14_genexpr`, `__pyx_scope_struct_15_genexpr` |
| `state_store` | 46 | `__defaults__`, `__pyx_defaults`, `__pyx_scope_struct_10_save_settings`, `__pyx_scope_struct_11_get_setting`, `__pyx_scope_struct_12_list_presets`, `__pyx_scope_struct_13_get_preset` |
| `artifacts` | 42 | `__pyx_scope_struct_10__scan_artifacts`, `__pyx_scope_struct_11_genexpr`, `__pyx_scope_struct_12_upload_files`, `__pyx_scope_struct_13_extract_status`, `__pyx_scope_struct_14_upload_custom_requirements`, `__pyx_scope_struct_15_update_artifact` |
| `chat_memory` | 41 | `__defaults__`, `__pyx_defaults`, `__pyx_scope_struct_10_genexpr`, `__pyx_scope_struct_11_build_context`, `__pyx_scope_struct_12_genexpr`, `__pyx_scope_struct_13_genexpr` |
| `editor_exports` | 41 | `__defaults__`, `__pyx_defaults`, `__pyx_scope_struct_10_genexpr`, `__pyx_scope_struct_11_synchronize_plain_word_edits`, `__pyx_scope_struct_12_genexpr`, `__pyx_scope_struct_13_genexpr` |
| `newapi_account` | 39 | `__defaults__`, `__pyx_defaults`, `__pyx_scope_struct_10_wallet`, `__pyx_scope_struct_11_checkout`, `__pyx_scope_struct_12_orders`, `__pyx_scope_struct_13_query` |
| `access_mode` | 39 | `__pyx_scope_struct_10_genexpr`, `__pyx_scope_struct_11_genexpr`, `__pyx_scope_struct_12_prepare_task_payers`, `__pyx_scope_struct_13_payer_task`, `__pyx_scope_struct_14_decorate`, `__pyx_scope_struct_15_wrapped` |
| `editor_contract` | 39 | `__pyx_scope_struct_10_genexpr`, `__pyx_scope_struct_11_genexpr`, `__pyx_scope_struct_12_genexpr`, `__pyx_scope_struct_13_read_only_tools`, `__pyx_scope_struct_14_genexpr`, `__pyx_scope_struct_15_dependencies` |
| `paper_modeling_quality` | 39 | `__pyx_scope_struct_10_genexpr`, `__pyx_scope_struct_11_genexpr`, `__pyx_scope_struct_1_genexpr`, `__pyx_scope_struct_2__extract_display_math`, `__pyx_scope_struct_3_genexpr`, `__pyx_scope_struct_4_genexpr` |
| `main` | 37 | `__pyx_scope_struct_10_desktop_security_headers`, `__pyx_scope_struct_11_health`, `__pyx_scope_struct_12_prepare_desktop_update`, `__pyx_scope_struct_13_get_templates`, `__pyx_scope_struct_14_resolve_template_steps`, `__pyx_scope_struct_15_serve_logo` |
| `paper_submission_contract` | 37 | `__defaults__`, `__pyx_defaults`, `__pyx_scope_struct_10__run_checker_attempt`, `__pyx_scope_struct_11_genexpr`, `__pyx_scope_struct_12__materialized_checkers`, `__pyx_scope_struct_13_check_paper_submission_contract` |
| `chat_session` | 36 | `__defaults__`, `__pyx_defaults`, `__pyx_scope_struct_10__read_loop`, `__pyx_scope_struct_11__on_event`, `__pyx_scope_struct_12_genexpr`, `__pyx_scope_struct_13_genexpr` |
| `editor_agent` | 36 | `__pyx_scope_struct_10_genexpr`, `__pyx_scope_struct_11_genexpr`, `__pyx_scope_struct_12_genexpr`, `__pyx_scope_struct_13_execute`, `__pyx_scope_struct_14_genexpr`, `__pyx_scope_struct_15__execute` |
| `skill_crypto` | 36 | `__pyx_scope_struct_1_skill_key_scope`, `__pyx_scope_struct_2_decrypt_bytes`, `__pyx_scope_struct_3_genexpr`, `__pyx_scope_struct_4_genexpr`, `__pyx_scope_struct_5_validate_encrypted_skills_dir`, `__pyx_scope_struct_6_genexpr` |
| `chat_materials` | 35 | `__defaults__`, `__pyx_defaults`, `__pyx_scope_struct_10_evidence`, `__pyx_scope_struct_11_genexpr`, `__pyx_scope_struct_1_genexpr`, `__pyx_scope_struct_2_genexpr` |
| `chat_stage_progress` | 34 | `__pyx_scope_struct_10_genexpr`, `__pyx_scope_struct_11_genexpr`, `__pyx_scope_struct_12_genexpr`, `__pyx_scope_struct_13_genexpr`, `__pyx_scope_struct_14_genexpr`, `__pyx_scope_struct_15_genexpr` |
| `cli_gateway_proxy` | 34 | `__pyx_scope_struct_1_genexpr`, `__pyx_scope_struct_2__redact_provider_error`, `__pyx_scope_struct_3_iter_bytes`, `__pyx_scope_struct_4__open_provider`, `__pyx_scope_struct_5_genexpr`, `__pyx_scope_struct_6_genexpr` |
| `account` | 33 | `__pyx_scope_struct_10_account_models`, `__pyx_scope_struct_11_account_credits`, `__pyx_scope_struct_12_unbind`, `__pyx_scope_struct_13__wallet_handler`, `__pyx_scope_struct_14_handle`, `__pyx_scope_struct_15_genexpr` |
| `workspace_cleanup` | 33 | `__defaults__`, `__pyx_defaults`, `__pyx_scope_struct_1_genexpr`, `__pyx_scope_struct_2_utils_in_use`, `__pyx_scope_struct_3_cleanup_workspace_protected_material`, `__pyx_scope_struct_4_genexpr` |
| `chat_run_events` | 32 | `__defaults__`, `__pyx_defaults`, `__pyx_scope_struct_10_list_events`, `__pyx_scope_struct_11_persist_many`, `__pyx_scope_struct_1_genexpr`, `__pyx_scope_struct_2_genexpr` |
| `editor_transactions` | 32 | `__pyx_scope_struct_10_genexpr`, `__pyx_scope_struct_11_genexpr`, `__pyx_scope_struct_1_public`, `__pyx_scope_struct_2_genexpr`, `__pyx_scope_struct_3_target`, `__pyx_scope_struct_4_genexpr` |
| `runtime_guard` | 32 | `__pyx_scope_struct_10_genexpr`, `__pyx_scope_struct_11_genexpr`, `__pyx_scope_struct_1_genexpr`, `__pyx_scope_struct_2__verify_runtime_manifest`, `__pyx_scope_struct_3_genexpr`, `__pyx_scope_struct_4_load_trusted_gateway_policy` |
| `account_messages` | 31 | `__defaults__`, `__pyx_defaults`, `__pyx_scope_struct_10_submit`, `__pyx_scope_struct_11_genexpr`, `__pyx_scope_struct_1_capabilities`, `__pyx_scope_struct_1_genexpr` |
| `settings` | 31 | `__pyx_scope_struct_10_set_data_dir`, `__pyx_scope_struct_11_test_agent_connection`, `__pyx_scope_struct_12_detect_claude`, `__pyx_scope_struct_1_update_settings`, `__pyx_scope_struct_2_genexpr`, `__pyx_scope_struct_3__saved_preset_response` |
| `license_v2_client` | 31 | `__pyx_scope_struct_10_genexpr`, `__pyx_scope_struct_11_genexpr`, `__pyx_scope_struct_12_genexpr`, `__pyx_scope_struct_1_genexpr`, `__pyx_scope_struct_2_genexpr`, `__pyx_scope_struct_3_genexpr` |
| `account_inference` | 30 | `__pyx_scope_struct_10_genexpr`, `__pyx_scope_struct_11_genexpr`, `__pyx_scope_struct_1_capabilities`, `__pyx_scope_struct_1_genexpr`, `__pyx_scope_struct_2_operations`, `__pyx_scope_struct_2_transaction` |
| `paper_readiness` | 30 | `__pyx_scope_struct_1_genexpr`, `__pyx_scope_struct_2_genexpr`, `__pyx_scope_struct_3_genexpr`, `__pyx_scope_struct_4_genexpr`, `__pyx_scope_struct_5_genexpr`, `__pyx_scope_struct_6_genexpr` |
| `account_messages_codec` | 29 | `__defaults__`, `__pyx_defaults`, `__pyx_scope_struct_1_genexpr`, `__pyx_scope_struct_2__tree`, `__pyx_scope_struct_3_genexpr`, `__pyx_scope_struct_4_genexpr` |
| `artifact_graph` | 27 | `__pyx_scope_struct_1_genexpr`, `__pyx_scope_struct_2_genexpr`, `__pyx_scope_struct_3__iter_files`, `__pyx_scope_struct_4__python_output_literals`, `__pyx_scope_struct_5_genexpr`, `__pyx_scope_struct_6__source_candidates` |
| `editor_runs` | 26 | `__pyx_scope_struct_10_shutdown`, `__pyx_scope_struct_1_genexpr`, `__pyx_scope_struct_2_genexpr`, `__pyx_scope_struct_3_start`, `__pyx_scope_struct_4_execute`, `__pyx_scope_struct_5_genexpr` |
| `newapi_desktop` | 26 | `__pyx_scope_struct_10_receipts`, `__pyx_scope_struct_11_genexpr`, `__pyx_scope_struct_12_genexpr`, `__pyx_scope_struct_1_history`, `__pyx_scope_struct_2_genexpr`, `__pyx_scope_struct_3_usage` |
| `account_execution` | 24 | `__pyx_scope_struct_10_genexpr`, `__pyx_scope_struct_11_request_text`, `__pyx_scope_struct_1_selected_model`, `__pyx_scope_struct_2_genexpr`, `__pyx_scope_struct_3_genexpr`, `__pyx_scope_struct_4_transaction` |
| `license_guard` | 24 | `__pyx_scope_struct_1_run_protected_preparation`, `__pyx_scope_struct_2_workflow_step_license_scope`, `__pyx_scope_struct_3_genexpr`, `__pyx_scope_struct__begin_workflow_license_scope_async`, `_get_license_dir`, `_get_license_file` |
| `chat_queue` | 23 | `__pyx_scope_struct_1__maybe_await`, `__pyx_scope_struct_2_enqueue`, `__pyx_scope_struct_3__consume`, `__pyx_scope_struct_4__drain_all`, `__pyx_scope_struct_5_drain`, `__pyx_scope_struct__get` |
| `claude_session_store` | 23 | `__defaults__`, `__pyx_defaults`, `__pyx_defaults1`, `__pyx_scope_struct__workspace_session_scope`, `_assert_safe_root`, `_canonical_workspace` |
| `model_context` | 23 | `__pyx_scope_struct_1_context_catalog`, `__pyx_scope_struct_2_genexpr`, `__pyx_scope_struct_3_genexpr`, `__pyx_scope_struct_4_genexpr`, `__pyx_scope_struct_5_consume_launch_context`, `__pyx_scope_struct_6_genexpr` |
| `account_cli_bridge` | 22 | `__defaults__`, `__pyx_defaults`, `__pyx_scope_struct_10_start`, `__pyx_scope_struct_11_setup`, `__pyx_scope_struct_12_do_POST`, `__pyx_scope_struct_1_genexpr` |
| `chat_registry` | 21 | `__pyx_scope_struct_1_ensure`, `__pyx_scope_struct_2_drop`, `__pyx_scope_struct_3_rebuild`, `__pyx_scope_struct_4_rotate_if_needed`, `__pyx_scope_struct_5_drop_all`, `__pyx_scope_struct_6_reap_idle` |
| `focused_runtime` | 21 | `__pyx_scope_struct_1_genexpr`, `__pyx_scope_struct_2_genexpr`, `__pyx_scope_struct_3_genexpr`, `__pyx_scope_struct_4_compile_batch`, `__pyx_scope_struct_5_consume`, `__pyx_scope_struct_6_genexpr` |
| `instance_guard` | 21 | `__pyx_scope_struct_1_acquire`, `__pyx_scope_struct_2__handle_previous`, `__pyx_scope_struct_3__start_parent_watchdog`, `__pyx_scope_struct___port_responds`, `_can_bind`, `_handle_previous` |
| `project_server` | 20 | `__defaults__`, `__pyx_defaults`, `__pyx_scope_struct_10_cleanup_port_range`, `__pyx_scope_struct_1_genexpr`, `__pyx_scope_struct_2__kill_tree`, `__pyx_scope_struct_3__build_env` |
| `skill_capsule` | 20 | `__pyx_scope_struct_10_genexpr`, `__pyx_scope_struct_1_genexpr`, `__pyx_scope_struct_2__strict_json`, `__pyx_scope_struct_3_genexpr`, `__pyx_scope_struct_4_genexpr`, `__pyx_scope_struct_5_genexpr` |
| `account_credits` | 19 | `__pyx_scope_struct_1_text`, `__pyx_scope_struct_2_genexpr`, `__pyx_scope_struct_3_genexpr`, `__pyx_scope_struct_4_genexpr`, `__pyx_scope_struct__genexpr`, `_invalid` |
| `chat_contract` | 19 | `__pyx_scope_struct_1_genexpr`, `__pyx_scope_struct_2_genexpr`, `__pyx_scope_struct_3_genexpr`, `__pyx_scope_struct_4_load_description`, `__pyx_scope_struct__definition`, `bind` |
| `workspace_context` | 19 | `__defaults__`, `__pyx_defaults`, `__pyx_scope_struct_1_genexpr`, `__pyx_scope_struct_2_genexpr`, `__pyx_scope_struct_3_genexpr`, `__pyx_scope_struct_4_genexpr` |
| `chat_decisions` | 18 | `__pyx_scope_struct_1_genexpr`, `__pyx_scope_struct_2_extract_forks`, `__pyx_scope_struct_3_genexpr`, `__pyx_scope_struct__genexpr`, `_clean_obj`, `_coerce_forks` |
| `chat_progress` | 18 | `__pyx_scope_struct_1_genexpr`, `__pyx_scope_struct_2_genexpr`, `__pyx_scope_struct_3__append`, `__pyx_scope_struct_4_genexpr`, `__pyx_scope_struct__genexpr`, `_completed_activity` |
| `chat_read_context` | 18 | `__defaults__`, `__pyx_defaults`, `__pyx_scope_struct_1_genexpr`, `__pyx_scope_struct_2_build_workspace_evidence`, `__pyx_scope_struct_3_genexpr`, `__pyx_scope_struct_4_genexpr` |
| `readiness_sources` | 18 | `__pyx_scope_struct_10_genexpr`, `__pyx_scope_struct_1_documents`, `__pyx_scope_struct_2_genexpr`, `__pyx_scope_struct_3_visit`, `__pyx_scope_struct_4_genexpr`, `__pyx_scope_struct_5_genexpr` |
| `account_center` | 17 | `__pyx_scope_struct_1_genexpr`, `__pyx_scope_struct_2_genexpr`, `__pyx_scope_struct_3_sanitize_identity`, `__pyx_scope_struct_4_genexpr`, `__pyx_scope_struct_5_genexpr`, `__pyx_scope_struct__genexpr` |
| `account_inference_shadow` | 17 | `__pyx_scope_struct_1_genexpr`, `__pyx_scope_struct_2_task_lock`, `__pyx_scope_struct_3_transaction`, `__pyx_scope_struct_4_request`, `__pyx_scope_struct_5__binding_matches`, `__pyx_scope_struct_6_genexpr` |
| `client_gateway_config` | 17 | `__pyx_scope_struct_1_refresh`, `__pyx_scope_struct_2_genexpr`, `__pyx_scope_struct_3__start_async_refresh`, `__pyx_scope_struct_4_wait_until_ready`, `__pyx_scope_struct_5_wait_for_config`, `__pyx_scope_struct_6_refresh_loop` |

