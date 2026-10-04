# 运行时数据库 aris.db 结构（只读检查）

路径: `C:\Users\SAKE\AppData\Roaming\ModexData\library-aJL7Wi\db\aris.db`
大小: 136.0 KB

对象统计: table=11 index=9

## 表与行数

| 表 | 行数 |
|---|---|
| `chat_context_events` | 0 |
| `chat_messages` | 0 |
| `chat_run_events` | 0 |
| `chat_sessions` | 0 |
| `chat_stage_receipts` | 0 |
| `checkpoints` | 0 |
| `model_presets` | 0 |
| `settings` | 0 |
| `workflow_logs` | 0 |
| `workflow_steps` | 0 |
| `workflows` | 0 |

## 各表字段

### `chat_context_events`

| # | 列 | 类型 | 非空 | 默认 |
|---|---|---|---|---|
| 0 | `id` | INTEGER |  |  |
| 1 | `session_id` | TEXT | 是 |  |
| 2 | `workflow_id` | TEXT | 是 |  |
| 3 | `source_message_id` | INTEGER | 是 |  |
| 4 | `event_type` | TEXT | 是 |  |
| 5 | `payload` | TEXT | 是 |  |
| 6 | `consumed_at` | TIMESTAMP |  |  |
| 7 | `created_at` | TIMESTAMP |  | CURRENT_TIMESTAMP |

### `chat_messages`

| # | 列 | 类型 | 非空 | 默认 |
|---|---|---|---|---|
| 0 | `id` | INTEGER |  |  |
| 1 | `session_id` | TEXT | 是 |  |
| 2 | `role` | TEXT | 是 |  |
| 3 | `content` | TEXT | 是 |  |
| 4 | `intent` | TEXT |  |  |
| 5 | `skill_name` | TEXT |  |  |
| 6 | `instruction` | TEXT |  |  |
| 7 | `eta_minutes` | INTEGER |  |  |
| 8 | `run_id` | TEXT |  |  |
| 9 | `dep_fingerprint` | TEXT |  |  |
| 10 | `confirmed_at` | TIMESTAMP |  |  |
| 11 | `force_confirmed` | INTEGER | 是 | 0 |
| 12 | `status` | TEXT |  | 'done' |
| 13 | `error_message` | TEXT |  |  |
| 14 | `skill_session_id` | TEXT |  |  |
| 15 | `client_turn_id` | TEXT |  |  |
| 16 | `turn_id` | TEXT |  |  |
| 17 | `item_kind` | TEXT |  |  |
| 18 | `message_phase` | TEXT |  |  |
| 19 | `proposal_revision` | INTEGER | 是 | 1 |
| 20 | `state_revision` | INTEGER | 是 | 0 |
| 21 | `quality_status` | TEXT |  |  |
| 22 | `quality_json` | TEXT | 是 | '{}' |
| 23 | `outputs_json` | TEXT | 是 | '[]' |
| 24 | `missing_deps_json` | TEXT | 是 | '[]' |
| 25 | `result_summary` | TEXT |  |  |
| 26 | `result_outputs_json` | TEXT | 是 | '[]' |
| 27 | `execution_scope` | TEXT | 是 | 'full' |
| 28 | `focus_target` | TEXT |  |  |
| 29 | `operation_kind` | TEXT | 是 | 'run_step' |
| 30 | `source_skill` | TEXT |  |  |
| 31 | `target_paths_json` | TEXT | 是 | '[]' |
| 32 | `input_versions_json` | TEXT | 是 | '{}' |
| 33 | `target_sections_json` | TEXT | 是 | '{}' |
| 34 | `base_versions_json` | TEXT | 是 | '{}' |
| 35 | `impact_json` | TEXT | 是 | '[]' |
| 36 | `diff_json` | TEXT | 是 | '[]' |
| 37 | `version_id` | TEXT |  |  |
| 38 | `rolled_back_at` | TIMESTAMP |  |  |
| 39 | `model_preset_id` | TEXT |  |  |
| 40 | `effort` | TEXT |  |  |
| 41 | `model_used` | TEXT |  |  |
| 42 | `progress_phase` | TEXT |  |  |
| 43 | `progress_message` | TEXT |  |  |
| 44 | `progress_json` | TEXT | 是 | '{}' |
| 45 | `started_at` | TIMESTAMP |  |  |
| 46 | `last_progress_at` | TIMESTAMP |  |  |
| 47 | `completed_at` | TIMESTAMP |  |  |
| 48 | `tokens_in` | INTEGER |  |  |
| 49 | `tokens_out` | INTEGER |  |  |
| 50 | `created_at` | TIMESTAMP |  | CURRENT_TIMESTAMP |
| 51 | `updated_at` | TIMESTAMP |  | CURRENT_TIMESTAMP |

### `chat_run_events`

| # | 列 | 类型 | 非空 | 默认 |
|---|---|---|---|---|
| 0 | `event_id` | TEXT |  |  |
| 1 | `workflow_id` | TEXT | 是 |  |
| 2 | `message_id` | INTEGER | 是 |  |
| 3 | `run_id` | TEXT | 是 |  |
| 4 | `sequence` | INTEGER | 是 |  |
| 5 | `kind` | TEXT | 是 |  |
| 6 | `state` | TEXT | 是 |  |
| 7 | `title` | TEXT | 是 |  |
| 8 | `safe_detail` | TEXT | 是 | '' |
| 9 | `public_artifact_path` | TEXT |  |  |
| 10 | `started_at` | TIMESTAMP | 是 |  |
| 11 | `completed_at` | TIMESTAMP |  |  |
| 12 | `evidence_json` | TEXT | 是 | '{}' |
| 13 | `created_at` | TIMESTAMP |  | CURRENT_TIMESTAMP |

### `chat_sessions`

| # | 列 | 类型 | 非空 | 默认 |
|---|---|---|---|---|
| 0 | `id` | TEXT |  |  |
| 1 | `workflow_id` | TEXT | 是 |  |
| 2 | `cli_session_id` | TEXT |  |  |
| 3 | `active_turn_mode` | TEXT |  |  |
| 4 | `active_focus_target` | TEXT |  |  |
| 5 | `active_turn_id` | TEXT |  |  |
| 6 | `cost_usd` | REAL | 是 | 0 |
| 7 | `cost_report_count` | INTEGER | 是 | 0 |
| 8 | `created_at` | TIMESTAMP |  | CURRENT_TIMESTAMP |
| 9 | `last_active_at` | TIMESTAMP |  | CURRENT_TIMESTAMP |

### `chat_stage_receipts`

| # | 列 | 类型 | 非空 | 默认 |
|---|---|---|---|---|
| 0 | `workflow_id` | TEXT | 是 |  |
| 1 | `skill_name` | TEXT | 是 |  |
| 2 | `snapshot` | TEXT | 是 |  |
| 3 | `evidence_json` | TEXT | 是 |  |
| 4 | `accepted_at` | TIMESTAMP | 是 | CURRENT_TIMESTAMP |

### `checkpoints`

| # | 列 | 类型 | 非空 | 默认 |
|---|---|---|---|---|
| 0 | `id` | INTEGER |  |  |
| 1 | `workflow_id` | TEXT | 是 |  |
| 2 | `step_name` | TEXT | 是 |  |
| 3 | `checkpoint_type` | TEXT | 是 |  |
| 4 | `data` | TEXT |  | '{}' |
| 5 | `response` | TEXT |  |  |
| 6 | `status` | TEXT |  | 'pending' |
| 7 | `created_at` | TIMESTAMP |  | CURRENT_TIMESTAMP |
| 8 | `resolved_at` | TIMESTAMP |  |  |

### `model_presets`

| # | 列 | 类型 | 非空 | 默认 |
|---|---|---|---|---|
| 0 | `id` | TEXT |  |  |
| 1 | `name` | TEXT | 是 |  |
| 2 | `model_id` | TEXT | 是 |  |
| 3 | `api_key` | TEXT | 是 | '' |
| 4 | `provider_id` | TEXT | 是 | '' |
| 5 | `created_at` | TIMESTAMP |  | CURRENT_TIMESTAMP |

### `settings`

| # | 列 | 类型 | 非空 | 默认 |
|---|---|---|---|---|
| 0 | `key` | TEXT |  |  |
| 1 | `value` | TEXT | 是 | '' |
| 2 | `updated_at` | TIMESTAMP |  | CURRENT_TIMESTAMP |

### `workflow_logs`

| # | 列 | 类型 | 非空 | 默认 |
|---|---|---|---|---|
| 0 | `id` | INTEGER |  |  |
| 1 | `workflow_id` | TEXT | 是 |  |
| 2 | `step_name` | TEXT |  |  |
| 3 | `level` | TEXT |  | 'info' |
| 4 | `message` | TEXT | 是 |  |
| 5 | `created_at` | TIMESTAMP |  | CURRENT_TIMESTAMP |

### `workflow_steps`

| # | 列 | 类型 | 非空 | 默认 |
|---|---|---|---|---|
| 0 | `id` | INTEGER |  |  |
| 1 | `workflow_id` | TEXT | 是 |  |
| 2 | `skill_name` | TEXT | 是 |  |
| 3 | `display_name` | TEXT | 是 |  |
| 4 | `step_order` | INTEGER | 是 |  |
| 5 | `status` | TEXT |  | 'pending' |
| 6 | `has_checkpoint` | INTEGER |  | 0 |
| 7 | `checkpoint_type` | TEXT |  |  |
| 8 | `output_files` | TEXT |  | '[]' |
| 9 | `started_at` | TIMESTAMP |  |  |
| 10 | `completed_at` | TIMESTAMP |  |  |
| 11 | `error_message` | TEXT |  |  |
| 12 | `model_used` | TEXT |  |  |
| 13 | `resume_session_id` | TEXT |  |  |
| 14 | `resume_error_code` | TEXT |  |  |
| 15 | `resume_strategy` | TEXT |  |  |

### `workflows`

| # | 列 | 类型 | 非空 | 默认 |
|---|---|---|---|---|
| 0 | `id` | TEXT |  |  |
| 1 | `template` | TEXT | 是 |  |
| 2 | `title` | TEXT | 是 |  |
| 3 | `params` | TEXT |  | '{}' |
| 4 | `status` | TEXT |  | 'pending' |
| 5 | `current_step` | TEXT |  |  |
| 6 | `workspace_dir` | TEXT |  |  |
| 7 | `enable_checkpoints` | INTEGER |  | 0 |
| 8 | `auto_resume_count` | INTEGER | 是 | 0 |
| 9 | `auto_resume_last_at` | TIMESTAMP |  |  |
| 10 | `created_at` | TIMESTAMP |  | CURRENT_TIMESTAMP |
| 11 | `updated_at` | TIMESTAMP |  | CURRENT_TIMESTAMP |

## 关键表样本数据

