# 权威 API 契约（路由模块内省）

**方法**：FastAPI 的 `APIRouter` 保存每条 `APIRoute`，其中含
`path` / `methods` / `status_code` / `body_field` / `response_field` / `dependant`。
这是**权威契约**，比从 minified bundle 反推可靠。

| 指标 | 值 |
|---|---|
| 路由模块 | 19（成功 18，失败 1） |
| **路由总数** | **205** |
| 带**请求体模型**的 | **52** |
| 请求体模型**字段已展开**的 | **44** |
| 带**响应模型字段**的 | **0** |
| 有端点 docstring 的 | 65 |

方法分布：`POST`=91, `GET`=89, `PUT`=8, `DELETE`=7, `PATCH`=6

## 失败模块（1）

- `routers.client_config` — ateway_config.py", line 29, in init client_gateway_config
  File "runtime_guard.py", line 442, in runtime_guard.load_trusted_gateway_policy
runtime_

## 路由全表（205 条）

| 方法 | 路径 | 状态码 | 端点 | 请求体 | 响应模型 |
|---|---|---|---|---|---|
| - | `None` | - | `None` | - | - |
| - | `None` | - | `None` | - | - |
| - | `None` | - | `None` | - | - |
| GET | `/api/account/access-mode` | - | `access_mode_status` | - | - |
| POST | `/api/account/access-mode` | - | `select_access_mode` | - | - |
| POST | `/api/account/activate` | - | `activate` | - | - |
| POST | `/api/account/bind-email` | - | `account-bind-email` | - | - |
| GET | `/api/account/credits` | - | `account_credits` | - | - |
| GET | `/api/account/identity` | - | `account-identity-status` | - | - |
| POST | `/api/account/identity` | - | `account-identity-submit` | - | - |
| POST | `/api/account/identity/withdraw` | - | `account-identity-withdraw` | - | - |
| POST | `/api/account/licenses/claim` | - | `account-license-claim` | - | - |
| POST | `/api/account/licenses/{license_id}/unbind` | - | `unbind` | - | - |
| POST | `/api/account/login` | - | `login` | - | - |
| POST | `/api/account/logout` | - | `logout` | - | - |
| POST | `/api/account/logout-all` | - | `account-logout-all` | - | - |
| POST | `/api/account/model-account` | - | `account-model-account-link` | - | - |
| GET | `/api/account/model-account` | - | `account-model-account-status` | - | - |
| GET | `/api/account/models` | - | `account_models` | - | - |
| POST | `/api/account/register` | - | `account-register` | - | - |
| POST | `/api/account/reset-password` | - | `account-reset-password` | - | - |
| POST | `/api/account/send-code` | - | `account-send-code` | - | - |
| GET | `/api/account/status` | - | `status` | - | - |
| GET | `/api/account/wallet/catalog` | - | `account-wallet-catalog` | - | - |
| GET | `/api/account/wallet/entries` | - | `account-wallet-entries` | - | - |
| GET | `/api/account/wallet/history` | - | `account-wallet-history` | - | - |
| POST | `/api/account/wallet/orders` | - | `account-wallet-orders` | - | - |
| GET | `/api/account/wallet/orders` | - | `account-wallet-orders` | - | - |
| GET | `/api/account/wallet/orders/{order_id}` | - | `account-wallet-orders/{order_id}` | - | - |
| POST | `/api/account/wallet/quotes` | - | `account-wallet-quotes` | - | - |
| GET | `/api/account/workbench-access` | - | `workbench_access_status` | - | - |
| POST | `/api/editor/{wf_id}/ai-agent` | - | `ai_agent_endpoint` | `AiAgentRequest` | - |
| POST | `/api/editor/{wf_id}/ai-agent-apply` | - | `ai_agent_apply` | `AiAgentApplyRequest` | - |
| GET | `/api/editor/{wf_id}/ai-agent-check` | - | `ai_agent_check` | - | - |
| POST | `/api/editor/{wf_id}/ai-agent-discard` | - | `ai_agent_discard` | - | - |
| GET | `/api/editor/{wf_id}/ai-agent-events/{run_id}` | - | `ai_agent_events` | - | - |
| GET | `/api/editor/{wf_id}/ai-agent-history` | - | `ai_agent_history` | - | - |
| GET | `/api/editor/{wf_id}/ai-agent-runs` | - | `ai_agent_runs` | - | - |
| GET | `/api/editor/{wf_id}/ai-agent-runs/{run_id}` | - | `ai_agent_run_history` | - | - |
| POST | `/api/editor/{wf_id}/ai-agent-stop` | - | `ai_agent_stop` | - | - |
| POST | `/api/editor/{wf_id}/ai-agent-undo` | - | `ai_agent_undo` | - | - |
| GET | `/api/editor/{wf_id}/ai-agent-version/{version_id}` | - | `ai_agent_version` | - | - |
| POST | `/api/editor/{wf_id}/ai-edit` | - | `ai_edit_endpoint` | `AiEditRequest` | - |
| DELETE | `/api/editor/{wf_id}/chat-history` | - | `clear_chat_history` | - | - |
| GET | `/api/editor/{wf_id}/chat-history` | - | `get_chat_history` | - | - |
| POST | `/api/editor/{wf_id}/compile` | - | `compile_paper` | `CompileRequest` | - |
| POST | `/api/editor/{wf_id}/create-file` | - | `create_file` | `CreateFileRequest` | - |
| POST | `/api/editor/{wf_id}/describe-image` | - | `describe_image_endpoint` | - | - |
| GET | `/api/editor/{wf_id}/docx` | - | `get_docx` | - | - |
| GET | `/api/editor/{wf_id}/docx-status` | - | `docx_status` | - | - |
| GET | `/api/editor/{wf_id}/download` | - | `download_file` | - | - |
| POST | `/api/editor/{wf_id}/drawio-export` | - | `drawio_export` | `DrawioExportRequest` | - |
| DELETE | `/api/editor/{wf_id}/file` | - | `delete_file` | - | - |
| GET | `/api/editor/{wf_id}/file` | - | `read_file` | - | - |
| PUT | `/api/editor/{wf_id}/file` | - | `save_file` | `SaveRequest` | - |
| GET | `/api/editor/{wf_id}/file-preview-html` | - | `file_preview_html` | - | - |
| GET | `/api/editor/{wf_id}/files` | - | `list_files` | - | - |
| POST | `/api/editor/{wf_id}/generate-image` | - | `generate_image` | `GenerateImageRequest` | - |
| GET | `/api/editor/{wf_id}/image-check` | - | `image_check` | - | - |
| GET | `/api/editor/{wf_id}/image-requests/{request_id}` | - | `image_request_status` | - | - |
| GET | `/api/editor/{wf_id}/mode` | - | `get_mode` | - | - |
| GET | `/api/editor/{wf_id}/model-options` | - | `editor_model_options` | - | - |
| GET | `/api/editor/{wf_id}/pdf` | - | `get_pdf` | - | - |
| POST | `/api/editor/{wf_id}/run-script` | - | `run_script` | `RunScriptRequest` | - |
| POST | `/api/editor/{wf_id}/run-script-stop` | - | `stop_run_script` | - | - |
| POST | `/api/editor/{wf_id}/serve` | - | `start_serve` | `ServeRequest` | - |
| DELETE | `/api/editor/{wf_id}/serve` | - | `stop_serve` | - | - |
| GET | `/api/editor/{wf_id}/serve/status` | - | `serve_status` | - | - |
| GET | `/api/editor/{wf_id}/stats` | - | `get_stats` | - | - |
| POST | `/api/editor/{wf_id}/upload` | - | `upload_file` | `Body_upload_file_api_editor__wf_id__upload_post` | - |
| POST | `/api/internal/chat/artifacts/image` | - | `read_image` | `VisualArtifactIn` | `dict` |
| POST | `/api/internal/chat/artifacts/list` | - | `list_artifacts` | `StateIn` | `dict` |
| POST | `/api/internal/chat/artifacts/material` | - | `read_material` | `ArtifactIn` | `dict` |
| POST | `/api/internal/chat/artifacts/read` | - | `read_artifact` | `ArtifactIn` | `dict` |
| POST | `/api/internal/chat/artifacts/search` | - | `search_artifacts` | `SearchIn` | `dict` |
| POST | `/api/internal/chat/capabilities` | - | `capabilities` | `StateIn` | `dict` |
| POST | `/api/internal/chat/deps` | - | `deps` | `DepsIn` | `dict` |
| POST | `/api/internal/chat/propose` | - | `propose` | `ProposeIn` | `dict` |
| POST | `/api/internal/chat/state` | - | `state` | `StateIn` | `dict` |
| POST | `/api/internal/model-tools/chat/completions` | - | `proxy_model_tool` | - | - |
| POST | `/api/internal/model-tools/images/generations` | - | `proxy_model_tool` | - | - |
| GET | `/api/palette-preview` | - | `palette_preview` | - | - |
| GET | `/api/settings` | - | `get_settings` | - | - |
| PUT | `/api/settings` | - | `update_settings` | `SettingsUpdate` | - |
| GET | `/api/settings/data-dir` | - | `get_data_dir` | - | - |
| PUT | `/api/settings/data-dir` | - | `set_data_dir` | `DataDirUpdate` | - |
| GET | `/api/settings/detect-claude` | - | `detect_claude` | - | - |
| POST | `/api/settings/models/discover` | - | `get_available_models` | `ModelDiscoveryBody` | - |
| POST | `/api/settings/presets` | - | `create_preset` | `PresetBody` | - |
| GET | `/api/settings/presets` | - | `get_presets` | - | - |
| DELETE | `/api/settings/presets/{preset_id}` | - | `remove_preset` | - | - |
| PUT | `/api/settings/presets/{preset_id}` | - | `update_preset` | `PresetBody` | - |
| POST | `/api/settings/test/{agent}` | - | `test_agent_connection` | - | - |
| GET | `/api/style-preview` | - | `style_preview` | - | - |
| POST | `/api/workflows` | 201 | `create` | `WorkflowCreate` | `dict` |
| GET | `/api/workflows` | - | `list_all` | - | `list` |
| POST | `/api/workflows/export-batch` | - | `export_batch` | `_BatchExportRequest` | - |
| POST | `/api/workflows/import` | - | `import_workflows` | `Body_import_workflows_api_workflows_import_post` | - |
| DELETE | `/api/workflows/{wf_id}` | - | `delete` | - | `dict` |
| GET | `/api/workflows/{wf_id}` | - | `get_one` | - | `dict` |
| GET | `/api/workflows/{wf_id}/artifact-context/inspect/{artifact_path:path}` | - | `get_artifact_context` | - | `dict` |
| POST | `/api/workflows/{wf_id}/artifact-context/prompt/build` | - | `build_artifact_prompt` | `PromptIn` | `dict` |
| GET | `/api/workflows/{wf_id}/artifacts` | - | `list_artifacts` | - | - |
| POST | `/api/workflows/{wf_id}/artifacts/custom-requirements` | - | `upload_custom_requirements` | `Body_upload_custom_requirements_api_workflows__wf_id__artifacts_custom_requirements_post` | - |
| GET | `/api/workflows/{wf_id}/artifacts/export` | - | `export_workspace` | - | - |
| GET | `/api/workflows/{wf_id}/artifacts/extract-status` | - | `extract_status` | - | - |
| POST | `/api/workflows/{wf_id}/artifacts/upload` | - | `upload_files` | `Body_upload_files_api_workflows__wf_id__artifacts_upload_post` | - |
| GET | `/api/workflows/{wf_id}/artifacts/{path:path}` | - | `read_artifact` | - | - |
| PUT | `/api/workflows/{wf_id}/artifacts/{path:path}` | - | `update_artifact` | `ArtifactUpdateBody` | - |
| GET | `/api/workflows/{wf_id}/chat/config` | - | `get_chat_config` | - | `dict` |
| PATCH | `/api/workflows/{wf_id}/chat/config` | - | `patch_chat_config` | `ChatConfigIn` | `dict` |
| POST | `/api/workflows/{wf_id}/chat/decisions` | - | `add_decision` | `DecisionIn` | `dict` |
| DELETE | `/api/workflows/{wf_id}/chat/decisions/{decision_id}` | - | `revoke_decision` | - | `dict` |
| GET | `/api/workflows/{wf_id}/chat/forks` | - | `forks` | - | `dict` |
| POST | `/api/workflows/{wf_id}/chat/forks/{fork_id}/choose` | - | `choose_fork` | `ForkChoiceIn` | `dict` |
| GET | `/api/workflows/{wf_id}/chat/history` | - | `history` | - | `dict` |
| GET | `/api/workflows/{wf_id}/chat/materials` | - | `materials_status` | - | `dict` |
| POST | `/api/workflows/{wf_id}/chat/materials/prepare` | - | `prepare_materials` | `MaterialPrepareIn` | `dict` |
| POST | `/api/workflows/{wf_id}/chat/materials/upload` | - | `upload_materials` | `Body_upload_materials_api_workflows__wf_id__chat_materials_upload_post` | `dict` |
| GET | `/api/workflows/{wf_id}/chat/messages` | - | `messages` | - | `dict` |
| POST | `/api/workflows/{wf_id}/chat/messages/{msg_id}/cancel` | - | `cancel` | - | `dict` |
| POST | `/api/workflows/{wf_id}/chat/messages/{msg_id}/confirm` | - | `confirm` | `Optional` | `dict` |
| GET | `/api/workflows/{wf_id}/chat/messages/{msg_id}/diff` | - | `message_diff` | - | `dict` |
| GET | `/api/workflows/{wf_id}/chat/messages/{msg_id}/events` | - | `message_run_events` | - | `dict` |
| PATCH | `/api/workflows/{wf_id}/chat/messages/{msg_id}/proposal` | - | `edit_proposal` | `ProposalEditIn` | `dict` |
| POST | `/api/workflows/{wf_id}/chat/messages/{msg_id}/resume-draft` | - | `resume_focused_draft` | `ResumeDraftIn` | `dict` |
| POST | `/api/workflows/{wf_id}/chat/messages/{msg_id}/rollback` | - | `rollback_message_patch` | `Optional` | `dict` |
| GET | `/api/workflows/{wf_id}/chat/messages/{msg_id}/rollback-preview` | - | `rollback_preview` | - | `dict` |
| POST | `/api/workflows/{wf_id}/chat/messages/{msg_id}/validation-proposal` | - | `create_validation_proposal` | - | `dict` |
| GET | `/api/workflows/{wf_id}/chat/queue` | - | `queue` | - | `dict` |
| POST | `/api/workflows/{wf_id}/chat/queue/{msg_id}/promote` | - | `promote` | - | `dict` |
| POST | `/api/workflows/{wf_id}/chat/say` | - | `say` | `SayIn` | `dict` |
| DELETE | `/api/workflows/{wf_id}/chat/session` | - | `close_session` | - | `dict` |
| POST | `/api/workflows/{wf_id}/chat/session` | - | `open_session` | - | `dict` |
| POST | `/api/workflows/{wf_id}/chat/stages/{skill}/accept` | - | `accept_existing_stage` | `StageAcceptIn` | `dict` |
| GET | `/api/workflows/{wf_id}/chat/state` | - | `state` | - | `dict` |
| GET | `/api/workflows/{wf_id}/chat/turns/{turn_id}` | - | `turn_receipt` | - | `dict` |
| POST | `/api/workflows/{wf_id}/checkpoint` | - | `submit_checkpoint` | `dict` | `dict` |
| GET | `/api/workflows/{wf_id}/checkpoints/current` | - | `get_current_checkpoint` | - | `dict` |
| PUT | `/api/workflows/{wf_id}/checkpoints/plan` | - | `save_plan` | `PlanDraft` | `dict` |
| POST | `/api/workflows/{wf_id}/checkpoints/resolve` | - | `resolve` | `CheckpointResponse` | `dict` |
| GET | `/api/workflows/{wf_id}/export` | - | `export_one` | - | - |
| POST | `/api/workflows/{wf_id}/export-docx` | - | `export_docx` | `DocxExportRequest` | - |
| GET | `/api/workflows/{wf_id}/logs` | - | `get_logs` | - | `list` |
| PATCH | `/api/workflows/{wf_id}/mode` | - | `set_workflow_mode` | `dict` | `dict` |
| POST | `/api/workflows/{wf_id}/pause` | - | `pause` | - | `dict` |
| POST | `/api/workflows/{wf_id}/restart` | - | `restart` | - | `dict` |
| POST | `/api/workflows/{wf_id}/resume` | - | `resume` | `Optional` | `dict` |
| POST | `/api/workflows/{wf_id}/start` | - | `start` | - | `dict` |
| PATCH | `/api/workflows/{wf_id}/steps/{skill_name}/account-model` | - | `set_account_step_model` | `dict` | `dict` |
| PATCH | `/api/workflows/{wf_id}/steps/{skill_name}/effort` | - | `set_step_effort` | `dict` | `dict` |
| PATCH | `/api/workflows/{wf_id}/steps/{skill_name}/model` | - | `set_step_model` | `dict` | `dict` |
| POST | `/api/workflows/{wf_id}/steps/{skill_name}/rerun` | - | `rerun_step` | - | `dict` |
| GET | `/inference/capabilities` | - | `capabilities` | - | - |
| GET | `/inference/capabilities` | - | `capabilities` | - | - |
| GET | `/inference/operations` | - | `operations` | - | - |
| GET | `/inference/operations` | - | `operations` | - | - |
| POST | `/inference/operations` | - | `submit` | - | - |
| POST | `/inference/operations` | - | `submit` | - | - |
| GET | `/inference/operations/{operation_id}` | - | `recover` | - | - |
| GET | `/inference/operations/{operation_id}` | - | `recover` | - | - |
| GET | `/messages/capabilities` | - | `capabilities` | - | - |
| GET | `/messages/capabilities` | - | `capabilities` | - | - |
| GET | `/messages/operations` | - | `operations` | - | - |
| GET | `/messages/operations` | - | `operations` | - | - |
| POST | `/messages/operations` | - | `submit` | - | - |
| POST | `/messages/operations` | - | `submit` | - | - |
| GET | `/messages/operations/{operation_id}` | - | `recover` | - | - |
| GET | `/messages/operations/{operation_id}` | - | `recover` | - | - |
| GET | `/native/adjustments` | - | `adjustments` | - | - |
| GET | `/native/adjustments` | - | `adjustments` | - | - |
| POST | `/native/checkout` | - | `checkout` | - | - |
| POST | `/native/checkout` | - | `checkout` | - | - |
| GET | `/native/history` | - | `history` | - | - |
| GET | `/native/history` | - | `history` | - | - |
| GET | `/native/image-settings` | - | `image_settings` | - | - |
| GET | `/native/image-settings` | - | `image_settings` | - | - |
| PUT | `/native/image-settings` | - | `save_image_settings` | - | - |
| PUT | `/native/image-settings` | - | `save_image_settings` | - | - |
| POST | `/native/login/verify` | - | `verify` | - | - |
| POST | `/native/login/verify` | - | `verify` | - | - |
| GET | `/native/orders` | - | `orders` | - | - |
| GET | `/native/orders` | - | `orders` | - | - |
| POST | `/native/orders/{number}/query` | - | `query` | - | - |
| POST | `/native/orders/{number}/query` | - | `query` | - | - |
| GET | `/native/realname` | - | `realname` | - | - |
| GET | `/native/realname` | - | `realname` | - | - |
| POST | `/native/register` | - | `handle` | - | - |
| POST | `/native/register` | - | `handle` | - | - |
| POST | `/native/register-code` | - | `handle` | - | - |
| POST | `/native/register-code` | - | `handle` | - | - |
| GET | `/native/requests` | - | `requests` | - | - |
| GET | `/native/requests` | - | `requests` | - | - |
| POST | `/native/reset-email` | - | `handle` | - | - |
| POST | `/native/reset-email` | - | `handle` | - | - |
| GET | `/native/software` | - | `software` | - | - |
| GET | `/native/software` | - | `software` | - | - |
| POST | `/native/software/consent` | - | `software_consent` | - | - |
| POST | `/native/software/consent` | - | `software_consent` | - | - |
| GET | `/native/usage` | - | `usage` | - | - |
| GET | `/native/usage` | - | `usage` | - | - |
| GET | `/native/wallet` | - | `wallet` | - | - |
| GET | `/native/wallet` | - | `wallet` | - | - |
| POST | `/v1/messages` | - | `proxy_messages` | - | - |
| - | `/ws/{workflow_id}` | - | `ws_endpoint` | - | - |

## ★ 请求体模型字段（完整契约，去重）

### `AiAgentRequest`  ← `POST` /api/editor/{wf_id}/ai-agent

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `message` | `<class 'str'>` | 是 |  |
| `current_file` | `<class 'str'>` |  | '' |
| `compile_log` | `<class 'str'>` |  | '' |
| `request_id` | `<class 'str'>` |  | '' |
| `auto_export` | `<class 'bool'>` |  | True |
| `auto_repair` | `<class 'bool'>` |  | True |
| `allowed_paths` | `list[str] | None` |  | None |
| `permission_mode` | `typing.Literal['project', 'intent']` |  | 'project' |
| `account_model` | `dict | None` |  | None |

### `AiAgentApplyRequest`  ← `POST` /api/editor/{wf_id}/ai-agent-apply

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `paths` | `list[str]` | 是 |  |
| `run_id` | `<class 'str'>` |  | '' |

### `AiEditRequest`  ← `POST` /api/editor/{wf_id}/ai-edit

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `message` | `<class 'str'>` | 是 |  |
| `current_file` | `<class 'str'>` | 是 |  |
| `current_content` | `<class 'str'>` | 是 |  |
| `compile_log` | `<class 'str'>` |  | '' |
| `ref_file` | `<class 'str'>` |  | '' |
| `role` | `<class 'str'>` |  | 'auto' |
| `current_sha256` | `typing.Optional[str]` |  | None |
| `account_model` | `dict | None` |  | None |

### `CompileRequest`  ← `POST` /api/editor/{wf_id}/compile

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `source_md` | `<class 'str'>` |  | '' |

### `CreateFileRequest`  ← `POST` /api/editor/{wf_id}/create-file

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `path` | `<class 'str'>` | 是 |  |
| `content` | `<class 'str'>` |  | '' |

### `DrawioExportRequest`  ← `POST` /api/editor/{wf_id}/drawio-export

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `path` | `<class 'str'>` | 是 |  |

### `SaveRequest`  ← `PUT` /api/editor/{wf_id}/file

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `path` | `<class 'str'>` | 是 |  |
| `content` | `<class 'str'>` | 是 |  |
| `expected_sha256` | `typing.Optional[str]` |  | None |

### `GenerateImageRequest`  ← `POST` /api/editor/{wf_id}/generate-image

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `prompt` | `<class 'str'>` | 是 |  |
| `lang` | `typing.Literal['zh', 'en']` |  | 'zh' |
| `aspect_ratio` | `typing.Literal['1:1', '16:9', '3:2', '4:3', '9:16', '2:3', '3:4']` |  | '3:2' |
| `filename` | `<class 'str'>` |  | '' |
| `model_id` | `<class 'str'>` |  | '' |
| `request_id` | `<class 'str'>` |  | PydanticUndefined |

### `RunScriptRequest`  ← `POST` /api/editor/{wf_id}/run-script

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `path` | `<class 'str'>` | 是 |  |
| `cwd` | `typing.Literal['workspace', 'script']` |  | 'workspace' |

### `ServeRequest`  ← `POST` /api/editor/{wf_id}/serve

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `mode` | `<class 'str'>` |  | 'both' |

### `Body_upload_file_api_editor__wf_id__upload_post`  ← `POST` /api/editor/{wf_id}/upload

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `file` | `<class 'fastapi.datastructures.UploadFile'>` | 是 |  |

### `VisualArtifactIn`  ← `POST` /api/internal/chat/artifacts/image

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `session_id` | `<class 'str'>` | 是 |  |
| `workflow_id` | `<class 'str'>` | 是 |  |
| `path` | `<class 'str'>` | 是 |  |
| `page` | `<class 'int'>` |  | 1 |

### `StateIn`  ← `POST` /api/internal/chat/artifacts/list

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `session_id` | `<class 'str'>` | 是 |  |
| `workflow_id` | `<class 'str'>` | 是 |  |

### `ArtifactIn`  ← `POST` /api/internal/chat/artifacts/material

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `session_id` | `<class 'str'>` | 是 |  |
| `workflow_id` | `<class 'str'>` | 是 |  |
| `path` | `<class 'str'>` | 是 |  |

### `SearchIn`  ← `POST` /api/internal/chat/artifacts/search

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `session_id` | `<class 'str'>` | 是 |  |
| `workflow_id` | `<class 'str'>` | 是 |  |
| `query` | `<class 'str'>` | 是 |  |

### `DepsIn`  ← `POST` /api/internal/chat/deps

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `session_id` | `<class 'str'>` | 是 |  |
| `workflow_id` | `<class 'str'>` | 是 |  |
| `skill` | `<class 'str'>` | 是 |  |
| `input_paths` | `list[str]` |  | PydanticUndefined |

### `ProposeIn`  ← `POST` /api/internal/chat/propose

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `session_id` | `<class 'str'>` | 是 |  |
| `workflow_id` | `<class 'str'>` | 是 |  |
| `skill` | `<class 'str'>` | 是 |  |
| `instruction` | `<class 'str'>` |  | '' |
| `raw_text` | `<class 'str'>` |  | '' |
| `execution_scope` | `typing.Literal['full', 'focused']` |  | 'full' |
| `focus_target` | `<class 'str'>` |  | '' |
| `operation_kind` | `typing.Optional[typing.Literal['run_step', 'focused_run', 'research', 'patch', 'validate']]` |  | None |
| `target_paths` | `list[str]` |  | PydanticUndefined |
| `target_sections` | `dict[str, list[str]]` |  | PydanticUndefined |
| `input_paths` | `list[str]` |  | PydanticUndefined |

### `SettingsUpdate`  ← `PUT` /api/settings

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `settings` | `typing.Dict[str, str]` | 是 |  |

### `DataDirUpdate`  ← `PUT` /api/settings/data-dir

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `data_dir` | `<class 'str'>` | 是 |  |

### `ModelDiscoveryBody`  ← `POST` /api/settings/models/discover

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `api_key` | `<class 'str'>` |  | '' |
| `preset_id` | `<class 'str'>` |  | '' |
| `agent` | `typing.Optional[typing.Literal['executor', 'reviewer', 'editor_ai', 'gpt_image']]` |  | None |
| `force_refresh` | `<class 'bool'>` |  | False |

### `PresetBody`  ← `POST` /api/settings/presets

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `name` | `<class 'str'>` | 是 |  |
| `model_id` | `<class 'str'>` | 是 |  |
| `api_key` | `<class 'str'>` |  | '' |
| `context_mode` | `typing.Optional[typing.Literal['auto', '200k', '1m']]` |  | None |

### `WorkflowCreate`  ← `POST` /api/workflows

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `template` | `<enum 'TemplateType'>` | 是 |  |
| `title` | `<class 'str'>` | 是 |  |
| `params` | `typing.Dict` |  | PydanticUndefined |
| `enable_checkpoints` | `<class 'bool'>` |  | False |

### `_BatchExportRequest`  ← `POST` /api/workflows/export-batch

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `ids` | `list[str]` | 是 |  |

### `Body_import_workflows_api_workflows_import_post`  ← `POST` /api/workflows/import

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `file` | `<class 'fastapi.datastructures.UploadFile'>` | 是 |  |

### `PromptIn`  ← `POST` /api/workflows/{wf_id}/artifact-context/prompt/build

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `path` | `<class 'str'>` | 是 |  |
| `instruction` | `<class 'str'>` | 是 |  |
| `action` | `typing.Literal['modify', 'regenerate', 'validate']` |  | 'modify' |

### `Body_upload_custom_requirements_api_workflows__wf_id__artifacts_custom_requirements_post`  ← `POST` /api/workflows/{wf_id}/artifacts/custom-requirements

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `file` | `<class 'fastapi.datastructures.UploadFile'>` | 是 |  |

### `Body_upload_files_api_workflows__wf_id__artifacts_upload_post`  ← `POST` /api/workflows/{wf_id}/artifacts/upload

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `files` | `typing.List[fastapi.datastructures.UploadFile]` | 是 |  |
| `target_dir` | `typing.Optional[str]` |  | 'user_data' |
| `mark_as_problem` | `<class 'bool'>` |  | False |
| `prepare_chat_materials` | `<class 'bool'>` |  | False |

### `ArtifactUpdateBody`  ← `PUT` /api/workflows/{wf_id}/artifacts/{path:path}

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `content` | `<class 'str'>` | 是 |  |

### `ChatConfigIn`  ← `PATCH` /api/workflows/{wf_id}/chat/config

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `interaction_mode` | `typing.Literal['auto', 'conversation', 'focused', 'full']` | 是 |  |
| `model_preset_id` | `<class 'str'>` |  | '' |
| `effort` | `<class 'str'>` |  | '' |
| `project_brief` | `typing.Optional[chat.ChatProjectBriefIn]` |  | None |

### `DecisionIn`  ← `POST` /api/workflows/{wf_id}/chat/decisions

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `topic` | `<class 'str'>` | 是 |  |
| `choice` | `<class 'str'>` | 是 |  |
| `rejected` | `<class 'str'>` |  | '' |
| `evidence` | `<class 'str'>` |  | '' |

### `ForkChoiceIn`  ← `POST` /api/workflows/{wf_id}/chat/forks/{fork_id}/choose

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `choice` | `typing.Optional[str]` |  | None |
| `skip` | `<class 'bool'>` |  | False |
| `action` | `typing.Optional[typing.Literal['select', 'accept_recommendation', 'defer', 'reopen']]` |  | None |
| `expected_revision` | `typing.Optional[int]` |  | None |
| `expected_choice_label` | `typing.Optional[str]` |  | None |

### `MaterialPrepareIn`  ← `POST` /api/workflows/{wf_id}/chat/materials/prepare

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `paths` | `list[str] | None` |  | None |
| `retry` | `<class 'bool'>` |  | False |

### `Body_upload_materials_api_workflows__wf_id__chat_materials_upload_post`  ← `POST` /api/workflows/{wf_id}/chat/materials/upload

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `files` | `list[fastapi.datastructures.UploadFile]` | 是 |  |

### `ProposalEditIn`  ← `PATCH` /api/workflows/{wf_id}/chat/messages/{msg_id}/proposal

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `instruction` | `<class 'str'>` | 是 |  |
| `revision` | `<class 'int'>` | 是 |  |
| `execution_scope` | `typing.Optional[typing.Literal['full', 'focused']]` |  | None |
| `focus_target` | `typing.Optional[str]` |  | None |
| `model_preset_id` | `typing.Optional[str]` |  | None |
| `effort` | `typing.Optional[str]` |  | None |
| `target_paths` | `typing.Optional[list[str]]` |  | None |
| `target_sections` | `typing.Optional[dict[str, list[str]]]` |  | None |

### `ResumeDraftIn`  ← `POST` /api/workflows/{wf_id}/chat/messages/{msg_id}/resume-draft

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `revision` | `<class 'int'>` | 是 |  |
| `resolution` | `<class 'str'>` |  | '' |

### `SayIn`  ← `POST` /api/workflows/{wf_id}/chat/say

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `text` | `<class 'str'>` | 是 |  |
| `turn_id` | `typing.Optional[str]` |  | None |
| `mode` | `typing.Literal['auto', 'conversation', 'focused', 'full']` |  | 'auto' |
| `focus_target` | `<class 'str'>` |  | '' |

### `StageAcceptIn`  ← `POST` /api/workflows/{wf_id}/chat/stages/{skill}/accept

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `snapshot` | `<class 'str'>` | 是 |  |

### `PlanDraft`  ← `PUT` /api/workflows/{wf_id}/checkpoints/plan

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `checkpoint_id` | `<class 'str'>` | 是 |  |
| `content` | `<class 'str'>` | 是 |  |

### `CheckpointResponse`  ← `POST` /api/workflows/{wf_id}/checkpoints/resolve

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `action` | `typing.Literal['approve', 'select', 'feedback', 'stop']` | 是 |  |
| `checkpoint_id` | `typing.Optional[str]` |  | None |
| `data` | `typing.Dict` |  | {} |

### `DocxExportRequest`  ← `POST` /api/workflows/{wf_id}/export-docx

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `source_file` | `typing.Optional[str]` |  | None |
| `style_profile` | `typing.Optional[str]` |  | None |
| `engine` | `typing.Optional[str]` |  | 'auto' |

## 响应模型字段（去重）

## 查询参数（有 query 参数的路由）

| 路径 | 方法 | query 参数 |
|---|---|---|
| `/api/editor/{wf_id}/ai-agent-check` | GET | log_offset?, run_id?, request_id? |
| `/api/editor/{wf_id}/ai-agent-discard` | POST | run_id? |
| `/api/editor/{wf_id}/ai-agent-events/{run_id}` | GET | after? |
| `/api/editor/{wf_id}/ai-agent-runs` | GET | limit?, before? |
| `/api/editor/{wf_id}/ai-agent-stop` | POST | run_id?, request_id? |
| `/api/editor/{wf_id}/ai-agent-undo` | POST | version_id? |
| `/api/editor/{wf_id}/describe-image` | POST | path?, expected_sha256? |
| `/api/editor/{wf_id}/docx` | GET | allow_stale?, expected_sha256? |
| `/api/editor/{wf_id}/download` | GET | path? |
| `/api/editor/{wf_id}/file` | GET | path? |
| `/api/editor/{wf_id}/file` | DELETE | path? |
| `/api/editor/{wf_id}/file-preview-html` | GET | path?, expected_sha256? |
| `/api/editor/{wf_id}/files` | GET | show_hidden?, view?, collection?, offset?, limit?, query?, snapshot?, refresh? |
| `/api/editor/{wf_id}/serve` | DELETE | kind? |
| `/api/editor/{wf_id}/stats` | GET | path? |
| `/api/editor/{wf_id}/upload` | POST | path?, expected_sha256? |
| `/api/palette-preview` | GET | colors? |
| `/api/style-preview` | GET | frame?, grid?, lw?, font?, legend?, bg? |
| `/api/workflows/{wf_id}/artifacts` | GET | view?, collection?, offset?, limit?, query?, snapshot?, refresh? |
| `/api/workflows/{wf_id}/artifacts/extract-status` | GET | target_dir? |
| `/api/workflows/{wf_id}/artifacts/{path:path}` | GET | raw?, preview?, as_png? |
| `/api/workflows/{wf_id}/chat/forks` | GET | pending_only? |
| `/api/workflows/{wf_id}/chat/history` | GET | before?, limit? |
| `/api/workflows/{wf_id}/chat/messages` | GET | after?, before?, limit? |
| `/api/workflows/{wf_id}/chat/messages/{msg_id}/events` | GET | after_sequence?, limit? |
| `/api/workflows/{wf_id}/export` | GET | mode? |
| `/api/workflows/{wf_id}/logs` | GET | limit?, compact? |
| `/native/adjustments` | GET | page? |
| `/native/adjustments` | GET | page? |
| `/native/history` | GET | page?, start?, end?, model? |
| `/native/history` | GET | page?, start?, end?, model? |
| `/native/orders` | GET | page? |
| `/native/orders` | GET | page? |
| `/native/requests` | GET | page? |
| `/native/requests` | GET | page? |
| `/native/usage` | GET | start?, end?, model?, cursor? |
| `/native/usage` | GET | start?, end?, model?, cursor? |

## 有说明文档的端点（65）

### `POST` /api/editor/{wf_id}/describe-image

```
手动触发图片描述（用于已有图片或 PDF 转图片）
```

### `GET` /api/editor/{wf_id}/docx

```
返回 Markdown 模式编译产出的 .docx 文件，浏览器会下载。
```

### `GET` /api/editor/{wf_id}/docx-status

```
Expose freshness separately from availability, including legacy exports.
```

### `GET` /api/editor/{wf_id}/file-preview-html

```
对二进制文件（如 .docx）返回 HTML 预览，iframe 可直接 src= 加载，避免 JSON 长度问题。
```

### `POST` /api/editor/{wf_id}/generate-image

```
使用已配置的生图模型；断线后可凭请求编号读取，不重复派发。
```

### `GET` /api/editor/{wf_id}/image-check

```
检查 GPT Image API 是否已配置
```

### `GET` /api/editor/{wf_id}/mode

```
返回工作流的编辑器模式：latex 或 markdown。

前端进入编辑器时调用此端点，根据返回的 mode 决定：
- 默认打开哪个文件
- 文件树显示哪些文件类型
- "编译"按钮的行为（xelatex 或 docx-export）
- AI 系统提示词（LATEX_SYSTEM_PROMPT 或 MARKDOWN_SYSTEM_PROMPT）
```

### `POST` /api/editor/{wf_id}/run-script-stop

```
Stop only the Python tree spawned by this editor workflow.
```

### `POST` /api/editor/{wf_id}/serve

```
启动本地预览服务。
```

### `DELETE` /api/editor/{wf_id}/serve

```
停止本地预览服务。kind 省略则停全部；否则停 frontend/backend。
```

### `GET` /api/editor/{wf_id}/serve/status

```
查询本地预览服务状态。
```

### `GET` /api/editor/{wf_id}/stats

```
返回字数统计和 PDF 页数信息（兼容 LaTeX/Markdown 双模式）。

- 不传 path: 返回全文统计 + PDF/估算页数 + max_pages
- 传 path: 返回该文件的字数统计
```

### `POST` /api/internal/chat/deps

```
主会话想在提议之前先确认能不能跑时用。
```

### `POST` /api/internal/chat/propose

```
MCP 工具调用它，然后【立刻返回】—— 不等执行。

⛔ MCP 是请求-响应协议，comp-code 要跑 32 分钟，客户端等不到就超时。
   所以这里只建 proposed 记录 + 广播卡片，真正执行走后端自己的队列。
```

### `POST` /api/internal/chat/state

```
.mh/STATE.json 的摘要。回答"某数字哪来的/为什么这么定/踩过什么坑"用。

⛔ 只返回记忆内容，不含任何配置或密钥。
```

### `POST` /api/internal/model-tools/chat/completions

```
No desktop control credential is granted to model tool processes.
```

### `POST` /api/internal/model-tools/images/generations

```
No desktop control credential is granted to model tool processes.
```

### `GET` /api/settings

```
返回所有配置（API Key 脱敏）
```

### `PUT` /api/settings

```
批量保存配置（跳过脱敏占位值与无权覆盖的 URL 字段）
```

### `PUT` /api/settings/data-dir

```
Select an existing complete data library; never switch into an empty partial copy.
```

### `GET` /api/settings/detect-claude

```
自动探测 Claude CLI 路径
```

### `POST` /api/settings/models/discover

```
从固定官方中转获取当前 Key 真正可用的模型列表。
```

### `GET` /api/settings/presets

```
列出预设与上下文（Key 脱敏；元数据仅查内存短缓存）。
```

### `POST` /api/settings/presets

```
新建预设。
```

### `PUT` /api/settings/presets/{preset_id}

```
更新预设和显式上下文选项；脱敏 Key/省略模式都保留原值。
```

### `DELETE` /api/settings/presets/{preset_id}

```
删除预设。已被角色/工作流引用的会在执行时回退全局，不影响运行。
```

### `POST` /api/settings/test/{agent}

```
测试 API 连通性
```

### `POST` /api/workflows/export-batch

```
批量导出多个工作流为单个 zip。
```

### `POST` /api/workflows/import

```
从 zip 文件导入工作流。支持单个和批量导出的 zip。
```

### `POST` /api/workflows/{wf_id}/artifacts/custom-requirements

```
上传自定义要求文档。任何支持的格式（含 Word/PDF）都会被转成纯文本写入 CUSTOM_REQUIREMENTS.md。
```

### `GET` /api/workflows/{wf_id}/artifacts/export

```
导出工作区为 zip 文件（只包含用户需要的文件）
```

### `GET` /api/workflows/{wf_id}/artifacts/extract-status

```
查询当前目录下所有文件的提取状态. 前端轮询用.

返回结构:
{
  "files": {
    "01.pdf": {"status": "done", "extracted_path": "01_extracted.txt", ...},
    "02.pdf": {"status": "extracting", ...},
    "03.pdf": {"status": "failed", "error": "..."},
  },
  "summary": {"total": 3, "pending": 0, "extracting": 1, "done": 1, "failed": 1}
}
```

### `POST` /api/workflows/{wf_id}/artifacts/upload

```
上传用户文件到工作区（数据、大纲、参考文献等）。
target_dir 可选值：'user_data'（默认）、''（根目录）、'paper'、'figures'。

``mark_as_problem`` couples the uploaded source and its internal marker in
one request.  This prevents collaborative/automatic vision selection from
diverging when a second, best-effort marker upload is lost.
```

### `PUT` /api/workflows/{wf_id}/artifacts/{path:path}

```
更新（或创建）产物文件。用于用户在线编辑大纲等文本文件。
```

### `GET` /api/workflows/{wf_id}/artifacts/{path:path}

```
读取或下载产物文件。
- `?raw=true` 下载原始文件
- `?preview=html` 返回 HTML 预览（仅对 .docx 有效，可被 iframe 直接 src= 加载）
- `?as_png=true` 把 .pdf 首页渲染成 PNG 返回（浏览器 <img> 无法显示 PDF，
  流程图/架构图/TikZ 图是矢量 PDF，预览时经此转 PNG 才能显示）
```

### `POST` /api/workflows/{wf_id}/chat/decisions

```
手工记一条决定。

⛔ 为什么必须有这个入口：自动识别（chat_decisions.detect_rejection）
   必然有漏 ——「别用遗传算法」能认，「GA 不合适」「那套方法风险大」未必。
   没有手工兜底就又是"看起来在记、实际漏了"，比没有这功能更坑人。
```

### `DELETE` /api/workflows/{wf_id}/chat/decisions/{decision_id}

```
撤销一条决定（你改主意了，但还没有新的替代）。
```

### `GET` /api/workflows/{wf_id}/chat/forks

```
岔路口清单。默认只返回还没选的。
```

### `POST` /api/workflows/{wf_id}/chat/forks/{fork_id}/choose

```
选定一个岔路口。

⛔ 选完【立刻写进决定清单】—— 这是整个岔路口功能的意义所在：
   不写进去的话，你的选择只停留在界面上，下一步 skill 根本不知道。
```

### `GET` /api/workflows/{wf_id}/chat/history

```
Independent task history across sessions, including old and failed work.
```

### `GET` /api/workflows/{wf_id}/chat/messages

```
拉消息列表。

⛔ 前端 WS 重连后必须调这个 —— WS 不补发，断线期间丢的提议卡片
   只能靠重拉。库是真相源，WS 只是实时加速。
```

### `POST` /api/workflows/{wf_id}/chat/messages/{msg_id}/cancel

```
取消提议或正在跑的任务。

⛔ 三种状态三种处理：
   proposed —— 直接改库（还没进队列）
   queued   —— 改库，消费循环出队时会跳过（不碰进程）
   running  —— 必须杀进程
```

### `POST` /api/workflows/{wf_id}/chat/messages/{msg_id}/confirm

```
用户点「跑」。这是唯一能让 skill 真正执行的入口。

⛔ 三道闸按顺序：
   ① 消息必须是 proposed 状态（不能重复确认、不能确认已取消的）
   ② 依赖必须齐（出队时还会再查一次，因为排队期间可能变）
   ③ 上游指纹必须没变 —— 你收到卡片去吃饭，回来点「跑」，
      这期间上游可能被改过，卡片上写的"基于 X@a1b2"已不成立
```

### `GET` /api/workflows/{wf_id}/chat/messages/{msg_id}/diff

```
返回已提交局部修改的可审阅差异；不读取或暴露私有 Skill。
```

### `GET` /api/workflows/{wf_id}/chat/messages/{msg_id}/events

```
Replay sanitized V2 execution events after a per-run sequence.

WebSocket delivery is only a low-latency hint.  This endpoint is the
authoritative reconnect path and deliberately returns no raw model stream.
```

### `PATCH` /api/workflows/{wf_id}/chat/messages/{msg_id}/proposal

```
只允许改系统整理的执行要点；用户原话永远保持只读。
```

### `POST` /api/workflows/{wf_id}/chat/messages/{msg_id}/resume-draft

```
Reopen the SAME card for review, never queue/run it automatically.
```

### `POST` /api/workflows/{wf_id}/chat/messages/{msg_id}/rollback

```
安全撤销一次局部修改。

撤销不是“强制覆盖旧文件”：只有文件仍等于该 patch 的提交版本时才允许，
后续任何人工或 AI 修改都会触发冲突并拒绝撤销。
```

### `GET` /api/workflows/{wf_id}/chat/messages/{msg_id}/rollback-preview

```
Read-only eligibility snapshot. POST independently rechecks before undo.
```

### `POST` /api/workflows/{wf_id}/chat/messages/{msg_id}/validation-proposal

```
从真实完成产物直接创建只读质检卡，不再经过主模型二次意图判断。
```

### `GET` /api/workflows/{wf_id}/chat/queue

```
队列面板：正在跑的 + 排队中的，带每条的 skill 和预计耗时。

⛔ 正在跑的那条已经不在队列里了（消费循环 get 出来了），要单独取。
```

### `POST` /api/workflows/{wf_id}/chat/queue/{msg_id}/promote

```
插到队首。

⛔ 不打断正在跑的那条 —— 那会损坏工作区（两个进程写同一批文件）。
   只是排到它后面第一个。想立刻跑就先 cancel 当前那条。
```

### `DELETE` /api/workflows/{wf_id}/chat/session

```
关闭会话（前端离开工作台、或用户主动结束）。
```

### `POST` /api/workflows/{wf_id}/chat/stages/{skill}/accept

```
User-triggered local acceptance, no model, no paper rewrite, no next run.
```

### `GET` /api/workflows/{wf_id}/chat/state

```
工作区记忆摘要（决定 / 运行 / 过期）。前端侧栏用。
```

### `GET` /api/workflows/{wf_id}/chat/turns/{turn_id}

```
Exact read-only receipt, independent of CLI liveness or the latest page.
```

### `GET` /api/workflows/{wf_id}/export

```
导出单个工作流为 zip。
mode=full（默认）：全量导出（DB 元数据 + 全部工作区文件），行为同旧版。
mode=clean：参赛精简版（只 paper/code/figures/结果，剔工具产物与自举头 + README）。
```

### `POST` /api/workflows/{wf_id}/export-docx

```
Use exactly the editor's source/profile/quality/publication pipeline.
```

### `GET` /api/workflows/{wf_id}/logs

```
从数据库读取历史日志（WebSocket 断开后的兜底）
```

### `PATCH` /api/workflows/{wf_id}/mode

```
切换工作流的运行模式（写 params.chat_mode）。

body: { chat_mode: bool }

⛔ 两种模式互斥，切换前必须确认对面没在跑：
   · 切去协同 → 全自动不能在跑（否则两个进程抢同一工作区）
   · 切回全自动 → 对话队列不能有任务在跑
这两条后端硬拦，不能只靠前端弹确认框。
```

### `POST` /api/workflows/{wf_id}/restart

```
完全重置工作流，重新从头执行所有步骤。
```

### `PATCH` /api/workflows/{wf_id}/steps/{skill_name}/account-model

```
Save a server-listed account model without restarting or spending credits.
```

### `PATCH` /api/workflows/{wf_id}/steps/{skill_name}/effort

```
修改工作流某步骤的思考强度（写 params.step_efforts），可选自动重跑本步。

body: { effort: str（low/medium/high/xhigh/max；空串=删除该步覆盖，回退全局）, rerun: bool }

与 set_step_model 完全同构（同一把启动锁、同样的清键逻辑、同样的 running 自动重跑）。
⛔ 值必须过 effort.sanitize：CLI 对非法 --effort 直接报错退出，脏值落库
   会让该步骤之后每次启动都失败。非法值一律当"清除该步覆盖"处理。
```

### `PATCH` /api/workflows/{wf_id}/steps/{skill_name}/model

```
修改工作流某步骤用的模型预设（写 params.step_models），可选自动重跑本步。

body: { preset_id: str（空串=删除该步覆盖，回退全局）, rerun: bool }
- 更新 params 后：pending/未跑的步骤下次跑自然生效；
- rerun=true 或该步当前 running → 复用单步重跑（取消旧进程 + run_single_step），立即换模型生效。
```

### `POST` /api/workflows/{wf_id}/steps/{skill_name}/rerun

```
重新执行工作流中的单个步骤。
```

