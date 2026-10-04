# 01 · 后端架构、API 面与数据模型

> 本报告原计划由子代理完成，该子代理**失败且未产出文件**。
> 后由主控改用**确定性脚本提取 + 明文精读**收口，故证据可复现性高于原计划。
> 证据分级：`【直接提取】` / `【反汇编推断】` / `【推断】` / `【推测】`

---

## 0. 结论先行

| 维度 | 结论 |
|---|---|
| 技术栈 | FastAPI + uvicorn + aiosqlite + SQLite，Python 3.11.9 |
| 分发形态 | **172 个 Cython 编译的 `.pyd`**，无任何 `.py` 源码 |
| 源码规模 | 176 个后端源文件（构建清单口径） |
| 模块划分 | 23 个 router + ~140 个 service |
| API 面 | **92 条**端点，按域：`workflows` 50 / `account` 22 / `settings` 8 / `editor` 7 / `license` 2 / `client-config` 2 / `templates` 1 |
| 数据模型 | 11 张表，254 行建表脚本（**明文，带设计注释**） |
| 动态分析 | **被运行时守卫拒绝**（见 §1.3） |

---

## 1. 后端构成与保护方式

### 1.1 源码树（176 个文件，来自构建清单）

> 【直接提取】`[证据: reports/build-inputs-paths.txt 中 web/backend/** 前缀的 176 条]`

```
web/backend/
├── main.py                    # FastAPI 应用装配
├── config.py                  # 配置
├── license-v2-client.json     # 许可证客户端配置
├── db/schema.sql              # ← 明文！11 张表
├── models/schemas.py          # Pydantic 模型
├── routers/  (23 个)
│   account, account_inference, account_messages, artifact_context, artifacts,
│   chat, chat_internal, checkpoints, cli_gateway, client_config, docx_export,
│   editor, newapi_account, palette_preview, project_preview, settings,
│   style_preview, workflows, ws
└── services/ (~140 个)
    ├── 工作流引擎  workflow_engine, workflow_acceptance, step_recovery,
    │               checkpoint_runtime, chat_stage_progress, focused_runtime
    ├── 对话工作台  chat_* (28 个), agent_state, chat_tool_policy, chat_ticket
    ├── 编辑器      editor_* (18 个)
    ├── 工件与补丁  artifact_*, quality_receipts, public_artifact_access
    ├── 账号与计费  account_* (25 个), license_guard, license_v2_client,
    │               account_credits, wallet_checkout_journal, access_mode
    ├── CLI 网关    cli_gateway_proxy, client_gateway_config, gateway_security,
    │               tls_security, child_environment, child_pids
    ├── 技能胶囊    skill_capsule, skill_crypto, capsule_io, skill_provenance,
    │               skill_source, skill_runtime_policy, skill_mcp
    ├── 排版导出    docx_tool_loader, export_runtime, paper_*
    ├── 运行时守卫  instance_guard, runtime_guard, update_quiescence,
    │               storage_paths, win_proc, workspace_cleanup
    └── prompts/    (8 个 .md，明文)
```

### 1.2 编译方式

- 工具链：`desktop/scripts/cython_build.py`（**构建清单中存在**）【直接提取】
- 产物：全部模块为 `*.cp311-win_amd64.pyd`（Cython 扩展 ABI 标签）
- 残留：仅 `config.pyc`、`models/schemas.pyc`、`services/{paper_source_scope,skill_mcp,_preview_proxy}.pyc` 等 **6 个 `.pyc`** 未编译为 `.pyd`
- 这 6 个 `.pyc` 恰好泄漏了原始源码路径（见 `00-lineage.md` 证据 1）

### 1.3 保护有效性（实测）

尝试导入编译后的 FastAPI app 以枚举权威路由，被守卫拒绝：

```
RuntimeInspectionUnavailable: 完整性验证或运行时约束未通过，未执行任何能力；请使用官方安装器修复
```

> 【直接提取】`[证据: tools/route_probe.py；详见 08-route-probe.md 与 02-desktop-security.md 附录 B]`

**结论**：Cython 只提高了阅读门槛（字符串/符号表仍可提取），
**真正有效的保护是这道运行时守卫**。它阻断了"导入自省"这条最省力的逆向路径。

---

## 2. API 面（92 条端点）

### 2.1 提取方法与可信度

后端路由字面量**未被 Cython 保留**为可检索常量，且导入被守卫阻断。
因此改由**前端 bundle 确定性提取**（前端必须调用每个端点）：

> 【直接提取】脚本 `tools/frontend_api_extract.py` → `09-frontend-api-surface.md` + `_api-paths.txt`

**可信度说明**：路径是前端实际调用的字面量，**比后端推断更可靠**；
但提取的是前端"发起侧"，HTTP **方法**与请求体结构未能确定（bundle 中与方法紧耦合）。
`【直接提取】`（路径）；方法标注为 `【推断】`。

### 2.2 按域分布

| 资源域 | 端点数 |
|---|---|
| `workflows` | **50** |
| `account` | 22 |
| `settings` | 8 |
| `editor` | 7 |
| `license` | 2 |
| `client-config` | 2 |
| `templates` | 1 |
| **合计** | **92** |

### 2.3 `workflows` 域（核心，50 条）

`workflows` 域实为**两套执行体系共用一个前缀**：经典工作流 + 对话工作台。

**经典工作流 / 工件 / 检查点**

| 端点 | 用途 `【推断】` |
|---|---|
| `/api/workflows/{id}/artifacts` | 列出工件 |
| `/api/workflows/{id}/artifacts/{path}` | 读写单个工件 |
| `/api/workflows/{id}/artifacts/upload` | 上传材料 |
| `/api/workflows/{id}/artifacts/extract-status` | 提取进度（对应 `extract_worker`） |
| `/api/workflows/{id}/artifacts/custom-requirements` | 自定义需求 |
| `/api/workflows/{id}/checkpoints/current` | 当前检查点 |
| `/api/workflows/{id}/checkpoints/plan` | 检查点计划 |
| `/api/workflows/{id}/steps/{step}/account-model` | 单步模型覆盖 |
| `/api/workflows/{id}/steps/{step}/effort` | 单步思考强度覆盖 |
| `/api/workflows/export`、`/export-batch`、`/import` | zip 导入导出 |
| `/api/workflows/{id}/artifact-context/inspect/{…}` | 工件上下文检查 |
| `/api/workflows/{id}/artifact-context/prompt/build` | 提示词构建 |

**对话工作台（人机协同）** —— 这是本产品的差异化核心

| 端点 | 用途 `【推断】` |
|---|---|
| `/api/workflows/{id}/chat/say` | 发送用户话轮 |
| `/api/workflows/{id}/chat/messages/{m}/proposal` | 获取执行提议 |
| **`/api/workflows/{id}/chat/messages/{m}/confirm`** | **确认执行（后端硬闸）** |
| `/api/workflows/{id}/chat/messages/{m}/cancel` | 取消 |
| `/api/workflows/{id}/chat/messages/{m}/rollback` | 回滚 |
| `/api/workflows/{id}/chat/messages/{m}/diff` | 查看改动 |
| `/api/workflows/{id}/chat/messages/{m}/resume-draft` | 恢复草稿 |
| `/api/workflows/{id}/chat/messages/{m}/validation-proposal` | 校验提议 |
| `/api/workflows/{id}/chat/decisions`、`/decisions/{n}` | 决策记录 |
| `/api/workflows/{id}/chat/queue`、`/queue/{n}/promote` | 串行队列与提升 |
| `/api/workflows/{id}/chat/forks/{n}/choose` | 分叉选择（对应 `agent_state.choose_fork`） |
| `/api/workflows/{id}/chat/turns/{turn}` | **幂等话轮**（对应 `client_turn_id`） |
| `/api/workflows/{id}/chat/stages/{skill}/accept` | **阶段验收**（对应 `chat_stage_receipts` 表） |
| `/api/workflows/{id}/chat/materials` | 对话材料 |
| `/api/workflows/{id}/chat/config`、`/session`、`/state` | 会话配置与状态 |

> **★ 交叉印证**：`/chat/stages/{skill}/accept` ↔ `chat_stage_receipts(workflow_id, skill_name)`；
> `/chat/turns/{turn}` ↔ `chat_messages.client_turn_id`；
> `/checkpoints/current` ↔ `checkpoints` 表。
> **前端端点与数据库表一一对应**，互为佐证，可信度高。`【直接提取】`

**工作区标准产物名**（从端点字面量中直接可见工件名）：

- `ASSETS_INVENTORY.md`、`ASSETS_CONFLICTS.md`、`PAPER_PLAN.md`

这三个是蓝方**约定的标准产物文件名**，与 `workflow_engine` 的
`_pfa_safety_copy_assets` / `_read_assets_index` / `_should_skip_step_by_assets` 符号一致。
`【直接提取】`

### 2.4 `account` 域（22 条）—— 商业化与多模型账号

| 端点 | 用途 `【推断】` |
|---|---|
| `/api/account/activate` | 激活 |
| `/api/account/identity`、`/identity/withdraw` | 实名/撤回 |
| `/api/account/licenses/claim`、`/licenses/{id}/unbind` | 许可证领取/解绑 |
| `/api/account/inference`、`/inference/operations` | 推理通道 |
| `/api/account/messages`、`/messages/capabilities`、`/messages/operations` | 消息（对应 `account_messages*` 三模块） |
| `/api/account/models` | 模型目录 |
| `/api/account/native/`、`/native/image-settings` | 原生通道 |
| `/api/account/access-mode` | 访问模式（对应 `access_mode`） |
| `/api/account/logout-all` | 全局登出 |

### 2.5 `settings` / `editor` / `license` / `templates`

| 端点 | 用途 `【推断】` |
|---|---|
| `/api/settings`、`/data-dir` | 设置与数据目录 |
| `/api/settings/detect-claude` | 探测 Claude CLI |
| `/api/settings/models/discover` | 模型发现 |
| `/api/settings/presets`、`/presets/{id}` | 模型预设 CRUD（对应 `model_presets` 表） |
| `/api/settings/test/{id}` | 连通性测试 |
| `/api/editor/{id}`、`/model-options` | 编辑器 |
| `/api/editor/{id}/ai-agent-history`、`/ai-agent-version/{v}` | AI 编辑历史与版本 |
| `/api/editor/{id}/generate-image`、`/image-requests/{r}` | 配图生成 |
| `/api/license/`、`/api/license/verify` | 许可证校验 |
| **`/api/templates/{t}/resolve-steps`** | **模板 → 步骤解析** |
| `/api/client-config`、`/refresh` | 签名客户端配置的拉取与刷新 |

> **★ `/api/templates/{t}/resolve-steps`** 是关键端点：它把**模板名**（如 `comp_zh`）
> 解析为**具体步骤列表**。后端 `main` 模块符号含 `resolve_template_steps`、`get_templates`，
> `workflow_engine` 含 `_comp_zh_steps` / `_comp_en_steps`（国赛中文/美赛英文两套步骤）。
> 三者串起来即为：**模板 → resolve-steps → 中/英文竞赛步骤列表 → DAG 执行**。
> `【直接提取 + 推断】`

### 2.6 外部端点（9 条）

> 【直接提取】`[证据: 09-frontend-api-surface.md §D]`

| 端点 | 含义 |
|---|---|
| `https://api.mhcode.ai/v1` | 模型 API（来自 `intl.jws`，非 bundle） |
| `https://license.mingheng.xin/register`、`/privacy` | 许可证激活与隐私 |
| `https://bill.mingheng.xin` | 计费 |
| **`https://openapi.alipay.com`** | **支付宝支付集成** |
| `https://www.mingheng.xin/` | 官网 |
| **`https://www.mcm.edu.cn/html_cn/node/...`（2 条）** | **全国大学生数学建模竞赛官网** |
| `https://embed.diagrams.net/?embed=1&proto=json...` | DrawIO 在线嵌入 |

> **★ 数模竞赛定位的直接证据**：前端 bundle 中硬编码了 **2 条 MCM/国赛官网链接**
> （`www.mcm.edu.cn`）。结合 `competition_zh.json` 自陈"对标 `cumcmthesis.cls`"，
> 数模竞赛是本产品**明确的、第一公民级**的目标场景。`【直接提取】`

### 2.7 WebSocket

**未提取到 `/ws/...` 字面量。** `routers/ws.py` 存在且 `useWebSocket-*.js` chunk 内含 17 条
`/api/...` 字符串，说明实时通道的 URL 很可能**由变量拼接**（如 `${proto}//${host}/api/ws`）。
`【推测】` 需动态抓取确认，而该路径受 §1.3 守卫限制。

---

## 3. 数据模型（11 张表）

`resources/app/backend/db/schema.sql`（254 行）是**本次分析中信息密度最高的明文文件**：
蓝方在其中留下了大量**设计意图与踩坑注释**。运行时数据库 `aris.db`
（`06-runtime-db.md`）证实表结构与之一致。

### 3.1 两套并行执行体系

| 体系 | 表 | 说明 |
|---|---|---|
| 经典工作流 | `workflows`、`workflow_steps`、`workflow_logs`、`checkpoints` | 预设步骤顺序执行，`step_order` 与 `tmpl.sub_steps` 索引强绑定 |
| 对话工作台 | `chat_sessions`、`chat_messages`、`chat_run_events`、`chat_context_events`、`chat_stage_receipts` | 自由顺序人机协同 |
| 配置 | `settings`、`model_presets` | 设置与模型预设 |

蓝方明确警告**两者不可混合**（见 §3.3 第 1 条）。

### 3.2 状态机

```
workflows.status             : pending | running | paused | completed | failed
workflow_steps.status        : pending | running | waiting_checkpoint | completed | failed | skipped
workflow_steps.resume_strategy: NULL | same_session | fresh_context
checkpoints.status           : pending | resolved
chat_messages.status         : proposed | queued | running | done | failed | cancelled | interrupted
chat_messages.operation_kind : run_step | research | patch | validate
chat_messages.execution_scope: full | focused
chat_messages.item_kind      : user_message | assistant_message | task | notice
chat_messages.message_phase  : commentary | final_answer
```

`workflows.auto_resume_count` 的设计注释点明了自动恢复护栏必须跨重启持久化：
> 自动恢复护栏必须跨后端重启持久化，不能只放在 Python 内存字典里。
> 人工 start/resume/restart/rerun 会清零；心跳/启动恢复只递增。

### 3.3 ★ 蓝方留下的关键设计约束（原文摘录）

**这是复现时最该直接吸收的部分**——每一条都是真实踩坑的产物。

| # | 设计点 | 蓝方原文（节选） |
|---|---|---|
| 1 | 两套体系不可混 | ⛔ 独立于 `workflow_steps`：那张表的 `step_order` 与 `tmpl.sub_steps` 索引强绑定，对话是自由顺序的（先画图→回头改建模→又重算），不能按对话顺序新增步骤，**否则会导致"健康检查张冠李戴"**。只有用户确认的完整步骤/质量修复通过硬闸后，才允许按既有 `skill_name` 精确同步对应行；上游重做会把既有下游置回 `pending`。`research`/`patch`/`validate` 始终不写 `workflow_steps`。 |
| 2 | 原话优先 | ⛔ `content` 存【用户原话】，是唯一真相源。与 `instruction` 分开存才谈得上"冲突时以原话为准" —— 混一列就没法在注入时区分优先级。 |
| 3 | 硬闸不能靠前端 | ⛔ `NULL` = 还停在提议卡片没点「跑」。后端硬闸：execute 前必须校验它非空，**不能只靠前端隐藏按钮（双击/网络重发/手动调接口都会绕过前端）**。 |
| 4 | 双 session 不可混用 | `skill_session_id` 与 `chat_sessions.cli_session_id` 是【两个不同的东西】…命名故意不叫 `cli_session_id`，**避免与主会话那列混淆导致续接错对象**。同一 skill 连续追问时用它 `--resume`；换 skill 就不续接（历史全算输入 token，纯浪费）。 |
| 5 | 幂等话轮 | 前端生成的幂等 turn id。网络响应丢失后重试时，**不能把同一句话再喂给长期主会话一次**，否则后续提议/上下文都会重复。 |
| 6 | CAS 并发 | 提议允许用户编辑整理后的 instruction。确认时带 revision 做 CAS，防止"保存编辑"和"确认执行"并发导致**跑了旧指令**。 |
| 7 | 不可变执行快照 | 每张执行卡片自己的不可变执行快照。工作流设置后来变化，也不能让已排队的任务**悄悄换模型、换强度或从"只做问题一"扩成完整步骤**。 |
| 8 | 上游漂移检测 | 提议生成时上游产物的指纹。确认时比对 —— 你收到卡片去吃饭，回来点「跑」，这期间上游可能被改过，卡片上写的"基于 MODELING_REPORT.md@a1b2"已不成立。 |
| 9 | 单次授权 | 用户在确认卡片时明确接受"缺少软依赖仍继续"。**只授权这一次执行**；硬依赖无论此值为何都必须继续拦截。不能只把 force 留在 HTTP 请求里，因为任务真正出队执行时请求早已结束。 |
| 10 | WS 只是通知 | 提议卡片的派生信息也要落库；**WS 只是通知**，断线/重启后仍应完整显示。 |
| 11 | 日志脱敏 | 原始 stream-json、命令、Skill 内容、密钥和私有目录**永不进入** `chat_run_events`。 |
| 12 | 迁移陷阱 | ⛔ `idx_chat_messages_turn_id` 不能在这里创建：`CREATE TABLE IF NOT EXISTS` 不会给旧表补列，老库执行到索引时会先报 `no such column`，**后面的 ALTER TABLE 迁移永远没有机会运行**。 |
| 13 | 成本口径 | 该值**不是权威账单**；自建网关折扣或订阅制以实际服务商为准。 |
| 14 | base_url 不落库 | `base_url` 不存（统一使用 License 签名配置）…请求地址始终由 License 签名配置确定，**不由厂商或预设改写**。 |
| 15 | 数据库膨胀 | 长日志不入库，只存短摘要和实际文件差异；完整流式日志仍只在内存里。 |
| 16 | 验收不可推断 | Explicit acceptance of existing artifacts; stored atomically with stage status. **Never inferred from the number of focused task receipts.** |

> 【直接提取】`[证据: resources/app/backend/db/schema.sql 全文 254 行]`

### 3.4 `chat_messages` —— 全库最复杂的表

**60 个字段**，是"对话即执行面板"这一产品形态的直接映射。
值得注意的字段组：

- **标识**：`client_turn_id`（幂等）、`turn_id`（分组）、`run_id`（产物溯源）
- **执行快照**：`execution_scope`、`focus_target`、`operation_kind`、`source_skill`、`target_paths_json`、`input_versions_json`、`base_versions_json`、`impact_json`
- **版本与回滚**：`version_id`、`rolled_back_at`、`proposal_revision`、`state_revision`
- **模型**：`model_preset_id`、`effort`、`model_used`
- **质量**：`quality_status`、`quality_json`、`dep_fingerprint`、`missing_deps_json`
- **过程**：`progress_phase`、`progress_message`、`progress_json`、`last_progress_at`
- **计费**：`tokens_in`、`tokens_out`

---

## 4. 值得红方复现的后端机制

| 机制 | 证据 | 复现价值 |
|---|---|---|
| **双执行体系隔离** | schema.sql 注释 1 | **高**——避免"自由对话"污染"顺序工作流"的健康检查 |
| **后端硬闸（非前端隐藏）** | `confirmed_at` 注释 | **高**——所有人工确认闸必须落库校验 |
| **不可变执行快照** | `execution_scope` 注释 | **高**——防排队任务被静默改参 |
| **幂等话轮 + CAS** | `client_turn_id` / `proposal_revision` | **高**——分布式/重试场景必备 |
| **上游指纹漂移检测** | `dep_fingerprint` | 中-高 |
| **WS 仅通知、状态落库** | schema 注释 10 | **高**——断线恢复的正确姿势 |
| **模板 → resolve-steps → 步骤列表** | `/api/templates/{t}/resolve-steps` + `_comp_zh_steps` | **高**——数模竞赛双语文案的核心编排点 |
| **导出脱敏** | `chat_run_events` 注释 | 中 |
| **单实例文件锁** | `instance_guard`（见 02 报告） | 中 |

---

## 5. 未获取项（明确声明，未作推测填充）

| 项 | 原因 |
|---|---|
| 各端点的 **HTTP 方法**与请求/响应体结构 | 后端守卫阻断导入；bundle 中方法与路径紧耦合，未能可靠解耦 |
| **WebSocket 协议**（事件名/消息类型） | URL 由变量拼接，未提取到字面量 |
| 后端**完整路由前缀表**（含非 `/api` 前缀） | 同上 |
| `models/schemas.pyc` 的 Pydantic 模型完整字段 | 已反汇编（`pyc_dump/`），但字节码恢复的字段语义有限 |
| skill 正文 | **加密 capsule**，全部 `.pyd` 检索 skill 名命中 0 |
| 中文竞赛正文字符预算的具体数值 | `.pyd` 中仅见 `800（含图表），英文` 片段，中文侧数值未出现 |

---

## 附：本报告的证据文件

| 证据 | 路径 |
|---|---|
| 92 条端点完整清单 | `reports/_api-paths.txt`、`reports/09-frontend-api-surface.md` |
| 模块符号表规模 | `reports/07-surface-extract.md` §D |
| 数据模型运行时对照 | `reports/06-runtime-db.md` |
| 路由探测与守卫拦截 | `reports/08-route-probe.md` |
| 后端源码文件清单（176） | `reports/build-inputs-paths.txt` |
| `.pyc` 反汇编 | `pyc_dump/` |
| `.pyd` 字符串表（11246 条） | `strings/_merged_strings.txt` |
| 中文串（1002 条） | `reports/cjk-strings-from-pyd.md` |
