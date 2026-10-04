# Modex-MH-Agent 逆向分析报告

> 红蓝对抗 · 红方一号选手
> 分析对象：`E:\02_Installers\DailyApps\Modex-MH-Agent`（Modex-MH-Agent **v2.1.2**, branch `release/intl`）
> 分析日期：2026-10-01　|　分析方式：**静态逆向为主 + 运行时数据只读取证**，全程未修改目标任何文件

---

## 0. 一句话结论

**Modex-MH-Agent 不是从零自研的产品：它源自开源项目 ARIS（`Auto-claude-code-research-in-sleep`），
在其上叠加了一整套商业化工程**（Electron 桌面壳 + Cython 编译保护的 FastAPI 后端 + React 前端
+ 加密 skill capsule + 许可证/计费/CLI 网关），并针对**中文数学建模竞赛**做了旁路特化。

对红方最重要的三个推论：

1. **方法论骨架在 GitHub 上完全公开**（ARIS，83 个 skill）。直接取用即可，无需逆向——这是成本最低的复现路径。
2. **蓝方真正自研的是"工程增量"**：工作流引擎、中文 docx/LaTeX 排版链路、多模型账号体系、CLI 网关、
   以及**数学建模竞赛特化层**。这些才是要逆向学习的目标。
3. **蓝方的方法论本体（skill 正文）提取不到**——被封装为**加密 capsule**，本次全套静态手段命中 0。
   但**上游模板可原样复用**，竞赛层必须自建（见 §2.3）。

---

## 1. 目标画像

| 项目 | 值 | 证据 |
|---|---|---|
| 产品名 | Modex-MH-Agent（"Modex · MH Agent"） | `dist/build-info.json`、`asar/package.json` |
| 版本 | 2.1.2，分支 `release/intl`，构建于 2026-09-25T05:28:25Z | `dist/build-info.json` |
| 厂商 | 明珩科技 | `asar/package.json` |
| 形态 | Electron 桌面应用（主程序 188,753,408 字节） | 目录枚举 |
| 定位 | **AI 数学建模竞赛智能体**：国赛/美赛/华为杯全流程 | 见 §6.3 的 MCM 官网硬编码 |
| 安装体积 | **7.16 GB** | 实测 |
| 服务端点 | `api.mhcode.ai/v1`、`license.mingheng.xin`、`bill.mingheng.xin`、`openapi.alipay.com` | `intl.jws` + bundle |
| 发行版 | 国内版 + 国际版**两个 appId**，共用同一数据目录 | `instance_guard` 内置注释 |

### 1.1 运行时构成（7.16 GB 的真实开销）

| 组件 | 体积 | 用途 |
|---|---|---|
| `runtime/python` | **4.24 GB** | 后端 + 科学计算栈（tensorflow / torch / catboost / xgboost / paddle / ortools / cvxpy / cv2…） |
| `runtime/texlive` | 0.99 GB | LaTeX 论文编译 |
| `runtime/node` | 0.57 GB | 含 `@anthropic-ai/claude-code` CLI（243 MB 单文件） |
| `runtime/draw.io` | 0.39 GB | DrawIO 架构图 |
| `runtime/git` | 0.31 GB | 便携 Git |
| `runtime/pandoc` | 0.21 GB | 文档转换 |
| `miktex-setup.exe` | 138 MB | MiKTeX 安装器（未安装） |

> 【直接提取】`runtime/python/python.exe -V` → `Python 3.11.9`；全部 `.pyd` 为 `cp311-win_amd64`，ABI 一致。

**红方提示**：这个体积本身就是产品价值（开箱即用的完整科研工具链），
但代价是**冷启动 17 分钟**（见 §7.2）——这是蓝方最大的产品弱点。

---

## 2. 血缘鉴定（★核心发现）

完整论证见 [`00-lineage.md`](00-lineage.md)，共**六层证据链**。

### 2.1 六层证据

| # | 证据 | 强度 |
|---|---|---|
| 1 | **52 个 `.pyc` 的 `co_filename` 全部指向** `D:\项目\Auto-claude-code-research-in-sleep-main\desktop\_tmp_backend\...` | ★★★ 最硬 |
| 2 | 运行时数据库文件名就是 **`aris.db`** | ★★★ |
| 3 | `schema.sql` 的 workflow 模板名与 ARIS skill 名机械对应（`-`→`_`） | ★★★ |
| 4 | 模块划分沿革：`desktop/_tmp_backend` → `web/backend`，`desktop/_tmp_tools` → `tools/` | ★★ |
| 5 | **随包分发的 `templates/README.md` 原样保留上游 `/skill-name` 引用与 Workflow 1/1.5/3 非连续编号** | ★★★ |
| 6 | **随包分发的明文提示词** `course_docx_drawio_png.md:6` 残留同一开发路径 | ★★★ |

**证据 5 的价值**：ARIS 的 skill 编号并非连续（1 / 1.5 / 2 / 3 / 4 / 5 / 6 / M）。
Modex 的模板 README 复用了**同一套非连续编号**，且保留了原样调用示例：

```bash
cp templates/EXPERIMENT_PLAN_TEMPLATE.md refine-logs/EXPERIMENT_PLAN.md
/experiment-bridge
```

**证据 6 的价值**：证据 1 依赖 `.pyc`（可被辩解为"编译环境残留"），
而证据 6 是**明文 Markdown**，难以同样辩解：

```bash
# resources/app/backend/services/prompts/course_docx_drawio_png.md:6
DRAWIO=$(command -v draw.io 2>/dev/null || echo 'D:/项目/Auto-claude-code-research-in-sleep-main/desktop/runtime/draw.io/draw.io.exe')
```

### 2.2 上游 ARIS

- 仓库：<https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep>
- 规模：**83 个 skill**、130 个 Python 工具
- 形态：Markdown-only skills，跨模型评审循环 + idea 发现 + 实验自动化
- 完整目录已保存：[`aris-skills-catalog.md`](aris-skills-catalog.md)

### 2.3 ★ 边界：上游继承 vs 蓝方自研（红方复现的路线图）

| Modex workflow 模板 | ARIS 上游 | 关系 |
|---|---|---|
| `idea_discovery`、`experiment_bridge`、`paper_writing` | `/idea-discovery`、`/experiment-bridge`、`/paper-writing` | **直接沿袭** |
| `auto_review` | `/auto-review-loop`（含 -llm / -minimax 三个变体） | 族系沿袭（**蓝方收敛为一个开关**） |
| `full_pipeline`、`thesis_proposal`、`literature_review`、`course_paper`、`course_report`、`humanities_paper`、`comp_*` | — | **蓝方新增** |

**最重要的分层判断（来自 `04-methodology.md`）**：

> **上游模板层是纯 AI 科研血统，不是数模竞赛血统。**
> `templates/` 9 个模板正文全是 `NeurIPS 2026` / `8x RTX 3090` / `WandB` / `ImageNet`；
> 竞赛能力**完全靠旁路层承载**（`comp_*` + `covers/` + `competition_*.json`），上游模板**未改写**。

⇒ **复现含义**：上游模板可**原样取用**；竞赛层必须**自建**。

**且**：ARIS 的 83 个 skill 中**无任何** CUMCM/MCM/华为杯赛事支持，
**也无任何** Word/docx 成文链路（其 `paper-write` 只覆盖 ICLR/NeurIPS/ICML/IEEE/ACL 等；
`paper-compile` 是 LaTeX→PDF）。这是"竞赛 + docx 增补属蓝方自研"的最强支撑。

**另需注意**：ARIS 上游 `/figure-spec` 的描述已含 "CJK width estimation"，
**勿将 CJK 能力误判为蓝方原创**。

### 2.4 为什么 skill 语料提取不到

全部 `.pyd` 检索 83 个 ARIS skill 名 → **命中 0**；`capsule` 出现 93 次、`skill_crypto` 49 次。
对应 `services/` 中的 `skill_capsule` / `skill_crypto` / `capsule_io` / `skill_provenance` / `skill_source`。

⇒ **蓝方把 skill 正文封装为加密 capsule，运行时装载**。这是有效的保护（与运行时守卫并列）。
**红方无法从本机提取 skill 正文，但可从公开上游取得同源骨架。**

---

## 3. 技术架构全景

### 3.1 进程模型

```
Electron 主进程 (asar/main.js)
  ├─ 单实例锁（国内版/国际版双 appId 共用数据目录 → 需额外文件锁互斥）
  ├─ 8 阶段启动编排（见 §7.2）
  ├─ Spawn Python 后端 (uvicorn, 127.0.0.1:<随机端口>)
  ├─ Spawn Claude Code CLI 子进程（经 loopback 作用域令牌代理）
  └─ 更新器 / 运行时完整性校验 / 存储恢复
        │
        ├─ Python 后端（172 个 Cython .pyd）
        │     ├─ 19 个 router 模块 → **205 条路由**（权威口径）+ 2 条实时通道
        │     ├─ ~140 个 service
        │     └─ SQLite (aris.db, 11 张表)
        │
        └─ React 前端（Vite 构建，由后端同源托管）
              ← 渲染进程加载 http://127.0.0.1:<port>，权限白名单仅限该源
```

**关键**：前端所有 `fetch('/api/...')` 都是**同源相对路径**，
由同一个 uvicorn 进程同时托管 `dist` 静态文件与 `/api`、`/ws`。
`[证据: asar/main.js 的 appOrigin 与 loadURL]`

### 3.2 代码规模（构建清单口径，547 条）

| 目录 | 文件数 | 性质 |
|---|---|---|
| `web/backend/**` | **176** | FastAPI 后端源码 → 172 个 `.pyd` |
| `desktop/scripts/**` | **147** | QA / 发布 / 代码签名 / 容量审计脚本 |
| `web/frontend/**` | **138** | React 前端源码 → Vite minified |
| `desktop/security/**` | 18 | 安全模块 |
| `tools/**` | 62 | 文档/排版/检索/视觉校验工具 |

### 3.3 前端技术栈（精确判定）

> 【直接提取】`[证据: 03-frontend.md，基于自研括号感知美化 + 定点阅读]`

| 层次 | 选型 | 版本 |
|---|---|---|
| UI 框架 | **React** | **19.2.4** |
| 路由 | **React Router**（数据路由） | 7.x |
| 状态管理 | **Zustand**（内联进 chunk） | v5 形态 |
| 构建 | **Vite** | — |
| CSS | **Tailwind CSS** | **v4.2.2** |
| 数学渲染 | **KaTeX** | **0.16.42** |
| Markdown | react-markdown v9+ + remark/rehype-katex | — |
| 图表 | **Recharts** | — |
| LaTeX 编辑器 | **自研**（受控 textarea + 自研 undo/diff 状态机） | — |
| UI 组件库 | **无**（纯 Tailwind + 自研组件 + emoji 图标） | — |
| 网络 | **原生 `fetch`**（无 axios） | — |

**两处值得注意的判断**：
- 报告正确识别出 chunk 内的 redux/immer/reselect **是 Recharts 的传递依赖，不是业务状态管理**
  （切片名全为 `chartLayout` / `legend` / `tooltip` 等 Recharts 内部切片）；
- 编辑器**未使用** Monaco/CodeMirror（在 245 KB CSS 与全部 chunk 中命中数为 0），是自研方案。

### 3.4 后端模块划分（172 个）

| 域 | 规模 | 代表模块 |
|---|---|---|
| 工作流引擎 | ~10 | `workflow_engine`(**3.1 MB**，后端最大), `workflow_acceptance`, `step_recovery`, `checkpoint_runtime` |
| 对话工作台 | ~28 | `chat_executor`(838 KB), `chat_session`, `chat_queue`, `chat_tool_policy`, `chat_ticket` |
| 编辑器 | ~18 | `editor_agent`, `editor_transactions`, `editor_exports`, `editor_contract` |
| 工件与补丁 | ~8 | `artifact_patch`(621 KB), `artifact_graph`, `artifact_catalogue` |
| 账号与计费 | ~25 | `account_*`, `license_guard`, `license_v2_client`, `account_credits` |
| CLI 网关 | ~6 | `cli_gateway_proxy`, `client_gateway_config`, `tls_security` |
| 技能胶囊 | 7 | `skill_capsule`, `skill_crypto`, `capsule_io`, `skill_provenance` |
| 排版导出 | ~6 | `docx_tool_loader`, `export_runtime`, `paper_*` |
| 运行时守卫 | ~8 | `instance_guard`, `runtime_guard`, `win_proc`, `storage_paths` |

### 3.5 API 面（**205 条权威路由** + 40 个请求体契约）

后端路由字面量未被 Cython 保留，且**导入被运行时守卫阻断**（§7.4 已有修正说明），
故先后用了三条路径，最终以**路由模块内省**为权威口径：

| 方法 | 结果 | 局限 |
|---|---|---|
| 主控确定性脚本（前端 bundle 字面量） | 92 条 | 只匹配 `/api/` 字面量，漏 base 常量拼接 |
| 子代理括号感知提取（前端 bundle） | ≈142 条 | 覆盖更全，但仍是**调用侧** |
| **★ 路由模块内省（`APIRouter` 对象）** | **205 条** | **权威**——含 path/methods/status_code/请求体/参数 |

> **方法学教训**：前端反推只是"被调用到的子集"；
> **`APIRouter` 里的才是全量真相**。两次从"看得见的部分"外推全量，都不完整。

#### 3.5.1 权威数据

| 指标 | 值 |
|---|---|
| 路由模块 | 19（成功 **18**，`routers.client_config` 被守卫拦截） |
| **路由总数** | **205** |
| 带**请求体模型**的 | **52**（其中 **44 个字段已展开**） |
| 唯一请求体模型 | **40** |
| 有端点 docstring 的 | 65 |
| 方法分布 | `POST` 最多，其次 `GET` / `PUT` / `PATCH` / `DELETE` |

**★ 一个刻意的设计选择**：`response_model` 分布为
`None`=148、`dict`=55、`list`=2 ⇒ **蓝方后端基本不声明响应模型，直接返回 dict**。
好处是灵活、避免 schema 漂移；代价是**前端拿不到类型保证**，
这也是前端必须自己写接口白名单正则（§3.5.2）的原因。

#### 3.5.2 路径分布与新增发现

| 前缀 | 条数 |
|---|---|
| `/api/workflows` | 59 |
| `/api/editor` | 39 |
| `/api/account` | 28 |
| **`/api/internal`** | **11** ← **新增发现** |
| `/api/settings` | 11 |
| `/inference/operations`、`/messages/operations` | 各 6 |
| `/native/*`（image-settings / software / orders / realname / login / register…） | 多条 |

**★ `/api/internal/chat/*` 是 MCP 回调面**（此前完全未知），共 5 条：

```
POST /api/internal/chat/propose          ← 产生执行提议（ProposeIn）
POST /api/internal/chat/deps             ← 依赖查询（DepsIn）
POST /api/internal/chat/capabilities     ← 能力查询（StateIn）
POST /api/internal/chat/state            ← 状态查询（StateIn）
POST /api/internal/chat/artifacts/list   ← 产物列举（StateIn）
```

这对应 `schema.sql` 注释里说的「MCP 是独立进程，不能共享 Python ContextVar，
把短暂字段落库，才能在 `propose_skill` 回调时由后端硬性保证…」——
即 **MCP 子进程通过这组内部 HTTP 接口回调主后端**。

#### 3.5.3 ★ 关键枚举（`Literal` 真值全部恢复）

| 模型.字段 | 取值 |
|---|---|
| `ModelDiscoveryBody.agent` | **`['executor','reviewer','editor_ai','gpt_image']`** ← **四个智能体角色** |
| `CheckpointResponse.action` | `['approve','select','feedback','stop']` |
| `SayIn.mode` / `ChatConfigIn.interaction_mode` | `['auto','conversation','focused','full']` |
| `ProposeIn.operation_kind` | `['run_step','focused_run','research','patch','validate']` |
| `ProposeIn.execution_scope` | `['full','focused']` |
| `ForkChoiceIn.action` | `['select','accept_recommendation','defer','reop…]` |
| `PromptIn.action` | `['modify','regenerate','validate']` |
| `PresetBody.context_mode` | `['auto','200k','1m']` ← **上下文窗口档位** |
| `GenerateImageRequest.aspect_ratio` | `['1:1','16:9','3:2','4:3','9:16','2:3','3:4']` |
| `GenerateImageRequest.lang` | `['zh','en']` |
| `AiAgentRequest.permission_mode` | `['project','intent']` |
| `RunScriptRequest.cwd` | `['workspace','script']` |

#### 3.5.4 关键请求体字段

```python
# POST /api/workflows  —— 创建工作流
WorkflowCreate(template: TemplateType, title: str,
               params: Dict, enable_checkpoints: bool = False)

# POST /api/workflows/{wf}/chat/say  —— 用户发言（幂等）
SayIn(text: str, turn_id: Optional[str], mode: Literal[...], focus_target: str)

# PATCH /api/workflows/{wf}/chat/messages/{msg}/proposal  —— 编辑提议（CAS）
ProposalEditIn(instruction: str, revision: int,          # ← 乐观并发
               execution_scope, focus_target, model_preset_id, effort,
               target_paths, target_sections)

# POST /api/internal/chat/propose  —— MCP 回调产生提议
ProposeIn(session_id, workflow_id, skill, instruction, raw_text,
          execution_scope: Literal['full','focused'] = 'full',
          focus_target: str = '', operation_kind, target_paths,
          target_sections, input_paths)

# POST /api/workflows/{wf}/checkpoints/resolve
CheckpointResponse(action: Literal['approve','select','feedback','stop'],
                   checkpoint_id: Optional[str], data: Dict = {})

# POST /api/workflows/{wf}/chat/stages/{skill}/accept  —— 阶段验收
StageAcceptIn(snapshot: str)                              # ← 与 chat_stage_receipts 表对应

# POST /api/settings/presets
PresetBody(name, model_id, api_key='', context_mode: Literal['auto','200k','1m'])
```

完整契约见 [`18-api-contract.md`](18-api-contract.md)（205 条路由全表 + 40 个请求体模型字段 + 65 条端点文档）
与机器可读的 [`18-api-contract.json`](18-api-contract.json)。

#### 3.5.5 两条实时通道（此前误判为"未提取到"）

| 通道 | 机制 | 细节 |
|---|---|---|
| 工作流实时 | **WebSocket** `ws://127.0.0.1:{port}/ws/{workflow_id}` | 纯文本 `ping`/`pong` 心跳 10 s；退避 `min(2^n*1000, 30000)*(0.8+rand*0.2)`；信封 `{type, workflow_id, …}`；**`type.startsWith('chat_')` 分流到 chatStore，否则 workflowStore**；工作流 11 种 + 聊天 12 种 + run_event 13 种事件已全量列表化 |
| 编辑器 AI Agent | **fetch + ReadableStream 手写 SSE** | `POST /api/editor/{id}/ai-agent`；**run id 取自响应头 `X-Editor-Run-Id`**；按 `\n\n` 分帧、`data:` JSON；事件 `progress` / `log` / `heartbeat` / `result`（`result` 终止）；每 read 30 s 超时；断线用同一请求编号恢复 |

> 前一条是标准 WS；后一条**不是** `EventSource`，而是手写 SSE 解析器——
> 说明蓝方为了在 POST 上获得流式响应而绕开了 `EventSource` 只能 GET 的限制。

**交叉印证**：前端端点与数据库表**一一对应**，互为佐证。

---

## 4. 数据模型与设计约束

`resources/app/backend/db/schema.sql`（254 行，**明文**）是本次分析中**信息密度最高的文件**。
11 张表、两套并行执行体系。完整解读见 [`01-backend-api-and-data.md`](01-backend-api-and-data.md)。

### 4.1 两套并行执行体系

| 体系 | 表 |
|---|---|
| 经典工作流 | `workflows`、`workflow_steps`、`workflow_logs`、`checkpoints` |
| 对话工作台 | `chat_sessions`、`chat_messages`、`chat_run_events`、`chat_context_events`、`chat_stage_receipts` |
| 配置 | `settings`、`model_presets` |

蓝方明确警告**两者不可混合**，原因见下。

### 4.2 ★ 蓝方留下的 16 条设计约束（复现时最该直接吸收）

每条都是真实踩坑的产物。**原文摘录**：

| # | 设计点 | 蓝方原文（节选） |
|---|---|---|
| 1 | 双体系隔离 | ⛔ 独立于 `workflow_steps`：其 `step_order` 与 `tmpl.sub_steps` 索引强绑定，对话是自由顺序的（先画图→回头改建模→又重算），不能按对话顺序新增步骤，**否则会导致"健康检查张冠李戴"** |
| 2 | 原话优先 | ⛔ `content` 存【用户原话】，是唯一真相源。与 `instruction` 分开存才谈得上"冲突时以原话为准" |
| 3 | 硬闸不能靠前端 | ⛔ 后端硬闸：execute 前必须校验 `confirmed_at` 非空，**不能只靠前端隐藏按钮（双击/网络重发/手动调接口都会绕过前端）** |
| 4 | 双 session 命名 | `skill_session_id` 与 `chat_sessions.cli_session_id` 是【两个不同的东西】…命名故意不叫 `cli_session_id`，避免**续接错对象** |
| 5 | 幂等话轮 | 网络响应丢失后重试时，**不能把同一句话再喂给长期主会话一次** |
| 6 | CAS 并发 | 确认时带 revision 做 CAS，防止"保存编辑"和"确认执行"并发导致**跑了旧指令** |
| 7 | 不可变快照 | 不能让已排队的任务**悄悄换模型、换强度或从"只做问题一"扩成完整步骤** |
| 8 | 上游漂移 | 你收到卡片去吃饭，回来点「跑」，这期间上游可能被改过 |
| 9 | 单次授权 | 只授权**这一次**执行；硬依赖无论如何都必须继续拦截 |
| 10 | WS 只是通知 | **WS 只是通知**，断线/重启后仍应完整显示 |
| 11 | 日志脱敏 | 原始 stream-json、命令、Skill 内容、密钥和私有目录**永不进入**表 |
| 12 | 迁移陷阱 | ⛔ `CREATE TABLE IF NOT EXISTS` 不会给旧表补列，老库执行到索引时会先报 `no such column`，**后面的 ALTER TABLE 迁移永远没有机会运行** |
| 13 | 成本口径 | 该值**不是权威账单** |
| 14 | base_url 不落库 | 请求地址始终由 License 签名配置确定，**不由厂商或预设改写** |
| 15 | 防膨胀 | 长日志不入库，只存短摘要；完整流式日志只在内存 |
| 16 | 验收不可推断 | **Never inferred from the number of focused task receipts** |

`chat_messages` 共 **60 个字段**，是全库最复杂的表——"对话即执行面板"形态的直接映射。

---

## 5. 数模方法论层与质量门

完整分析见 [`04-methodology.md`](04-methodology.md)（1107 行）。

### 5.1 明文的流程与规范资产

| 资产 | 数量 | 内容 |
|---|---|---|
| `templates/` | 9 个 | RESEARCH_BRIEF → CONTRACT → IDEA_CANDIDATES → EXPERIMENT_PLAN → EXPERIMENT_LOG → FINDINGS → PAPER_PLAN → NARRATIVE_REPORT |
| `prompts/` | 8 个 | docx 写作、课程论文、图表语言、LaTeX 模板 |
| `docx_style_profiles/` | 13 个 | 竞赛中文、中文学位论文、文献综述、华为杯封面… |

### 5.2 ★ 中文排版引擎的参数可从公开来源反推

> `04-methodology.md` 的关键结论

- `competition_zh.json:2` 自陈**"对标 `cumcmthesis.cls`"**（国赛官方 LaTeX 模板）
- `covers/huawei.json:2` 自陈**"对标 `gmcmthesis.cls`"**，且 `:41` 直接使用 LaTeX booktabs 方言
  `border_style: "Xhline"`
- 13 个 profile **共用同一骨架**：A4 / 2.5 cm 页边距 / SimHei + SimSun + Times New Roman /
  三线表 1.5–0.75–1.5 pt / 悬挂缩进 0.74 cm；差异仅在**级别字号、行距、分页、图宽** 4 维

⇒ **profile 数据无需逆向，可从公开 `.cls` 反推**。这大幅降低复现成本。

### 5.3 ★ 防幻觉的机制性设计（产品护城河）

- **表格不做 LLM 誊抄**：程序生成 `figures/TABLE_*.md`，再由 shell `cat >> paper/main.md` 直接拼接
- **数值必须从 `all_results.json` 读取**
- 配套全套"去 AI 味"约束：图题 ≤15 汉字、禁公式、空格替冒号，
  以及最高频痕迹 `**标签：**` 的冒号必须写在 `**` 外

### 5.4 引擎层质量门（从 `.pyd` 中文串恢复，共 1002 条）

`workflow_engine`（81 条）暴露了完整的质量门规则：

| 机制 | 证据串（节选） |
|---|---|
| 图表健康检查（静态） | "图表步骤健康检查(静态版, 不依赖 files_created)" |
| 图表健康检查（动态） | "对图表步骤做严格健康检查(动态版, 基于本步骤的文件增量)" |
| 四种合法跳过 | "真实新增图 / 用户禁用 / 无图论文场景 / rerun-skip 合法跳过" |
| 归类权威源 | "按 FIGURE_MANIFEST 的章节标题把图名归类(**权威, 优先于文件名前缀**)" |
| 页数预检 | "按竞赛页数语义做保守的正文字符预检" |
| LaTeX 文件名安全 | "把中文/空格/特殊字符替换成 ASCII 友好名字, 供 `includegraphics` 安全引用" |
| 上下文压缩 | "paper-figure 步骤运行时上下文累积到 **110K tokens**，导致 Claude 输出被截断" |
| 压缩预算 | 图片描述 ≤100 字/张、文档原文 ≤500 字/个 |
| 空工具调用恢复 | "压缩 CLAUDE.md 中的图片描述和冗余内容，减少 prompt 大小" |
| 幂等注入 | "通过 marker 检测是否已注入过…避免重复追加同一段提示导致上下文污染" |
| 返修预算 | 三类状态区分：`checker_unavailable` / 返修未结束 / 真实缺陷 |
| 中文/英文步骤 | "返回中文竞赛通用步骤列表" / "返回英文竞赛通用步骤列表" |

### 5.5 工作区上下文注入

`workflow_engine` 在工作区生成 **`CLAUDE.md`** 作为 CLI 的项目上下文，
并用 vision LLM 扫描工作区图片生成描述追加进去：

> "在工作区生成 CLAUDE.md，为 Claude CLI 提供项目上下文"
> "扫描工作区中的图片文件，用 vision LLM 描述内容，追加到 CLAUDE.md 正文中"

**标准产物名**（从前端端点字面量直接可见）：`ASSETS_INVENTORY.md`、`ASSETS_CONFLICTS.md`、`PAPER_PLAN.md`。

### 5.6 一处刻意的降级（值得借鉴的工程判断）

`tikz_vision_check.py` 的 docstring 完整记载了根因：旧逻辑"非 PASS 即 FAIL" + 主观评价项
→ **几何图必然被判失败**、每张烧满 2 轮重编，是"画完卡很久"的根因；
修复为只认正则 `^\s*ISSUE\s*\d*\s*[:：]`，把 vision 自检**降级为非阻塞加分项**。

### 5.7 ★ 数模竞赛业务特征（前端侧结构化恢复）

`03-frontend.md` 从 bundle 中恢复出完整的竞赛业务层，这是**蓝方自研增量的核心证据**：

| 特征 | 内容 |
|---|---|
| **赛题模板** | **22 个 `comp_*`**：`cumcm`（国赛）/ `huawei`（华为杯）/ `mcm` / `apmcm` / `mathorcup`… 含 `_en` 变体；另有 5 个学术 + 4 个科研模板 |
| **国赛专属合规门禁** | `w(e){return e==='comp_cumcm'}` —— 国赛场景**强制要求填写 1–5 条真实 AI 工具使用记录 + 参赛队人工核验确认**，否则不放行 |
| **图表规范** | **30 套配色** + **6 套版式**（含 SCI 投稿向 `framed_journal`）；配套 `/palette-preview`、`/style-preview` 服务端渲染预览 |
| **检查点类型** | 4 类：`approve` / `idea_select` / `feedback` / `assets_resolve` |
| **资产冲突** | `conflict_resolution_strategy` 机制 |
| **工件分类** | 8 分类 + **14 个论文文件名→中文映射**（`ASSETS_INVENTORY.md`、`ASSETS_CONFLICTS.md`、`PAPER_PLAN.md`、`paper/PAPER_IMPROVEMENT_LOG.md`、`main.{tex,pdf,docx}`、`ai工具使用详情.pdf` …）+ 优先级权重表 |
| **对话交互** | 4 档 `interaction_mode`：`auto` / `conversation` / `focused` / `full` |
| **操作类型** | 6 类 `operation_kind`：`run_step` / `patch` / `focused_run` / `research` / `validate` / `repair` |
| **进度阶段** | 10 个 `progress.phase` 中文标签 |
| **Skill 映射** | 23 个 Skill 的中文名映射 |

> **★ 国赛 AI 使用记录门禁**是最值得注意的一条：它对应**中国大学生数学建模竞赛自 2024 年起
> 要求申报 AI 使用情况**的规则。蓝方把它做成了**产品级的强制流程**（而非文档提醒），
> 这是一个极具体的、有真实赛事规则依据的差异化功能。**红方若要做数模产品，这是必备项。**

---

## 6. 商业化：许可证 / 计费 / 网关

### 6.1 信任链（已从本机完整解码）

`%APPDATA%\ModexData\...\client-config\intl.jws` 是一份 **EdDSA 签名的客户端配置**：

```json
// header
{ "alg": "EdDSA", "kid": "intl-license-2026-08-a", "typ": "MODEX-CLIENT-CONFIG" }
// payload
{ "activation_url": "https://license.mingheng.xin/register",
  "api_base_url":   "https://api.mhcode.ai/v1",
  "api_key_url":    "https://www.mhcode.ai/",
  "aud": "modex-client-config", "iss": "modex-license-v2",
  "edition": "intl", "gateway_profile": "intl-prod", "revision": 2,
  "iat": 1790857226, "nbf": 1790857226, "exp": 1791116426 }
```

> 【直接提取】`[证据: 现场解码 intl.jws, 3 段, 签名 86 字节]`

**设计要点**：**在线激活 + 签名下发配置**，且 `base_url` **不落库**——
每次由签名配置决定，使蓝方可远程切换网关而无需客户端发版。
（`model_presets` 存 `model_id`/`api_key`/`provider_id`，但注释明确 base_url 不由预设改写。）

### 6.2 构建期策略声明

```json
"cli_proxy_policy":    "loopback_scoped_token",
"provider_tls_policy": "system_pki_hostname_verification"
```

### 6.3 ★ CLI 网关：密钥隔离（最值得抄的设计）

`services/cli_gateway_proxy` 符号表揭示了完整实现：

- `CliProxySessionStore`: `create` / `authorize` / `authorize_target` / `bind_process` / `_digest`
- `bind_cli_proxy_process`、`_open_scoped_request`、`_authorize_account_target`
- `_wait_for_native_admission`、`_admission_retry_delay`、`_balance_retry_delay`
- `_redact_provider_error`、`_safe_error_body`（错误回显脱敏）

**意图**：CLI 子进程**拿不到真实 API Key**，只拿到绑定到本机 loopback 的**按会话作用域令牌**；
真实密钥只存在于后端内存。这是"把不可信子进程与长期凭证隔离"的标准范式，**红方应直接采用**。

### 6.4 数模竞赛定位的直接证据

前端 bundle 中硬编码了 **2 条全国大学生数学建模竞赛官网链接**：

- `https://www.mcm.edu.cn/html_cn/node/4cd596519c9eb9fbd866398f6df0caa3.html`
- `https://www.mcm.edu.cn/html_cn/node/fef94648f2836ab6cc81586f4c38512b.html`

另有 `openapi.alipay.com`（支付宝支付）、`bill.mingheng.xin`（计费）。
结合 `competition_zh.json` 的 "对标 cumcmthesis.cls"，**数模竞赛是本产品第一公民级的目标场景**。

### 6.5 单实例 / 多实例互斥（含一条发行情报）

`instance_guard` 中文串暴露了完整设计与一条**蓝方自身的发行信息**：

> 单实例锁只挡同一个 appId，**国内版 + 国际版是两个 appId，而它们默认共用
> `%APPDATA%\MHAgent` 这同一个数据目录**，所以这个竞态是真会发生的。

其他设计要点：
- 用**操作系统文件锁**（进程死亡时自动释放）而非 pid 轮询："崩溃、被强杀、断电都不会留下陈旧锁"
- Electron 父进程看护："Electron 一死就自杀，从根上消灭孤儿"
- 端口探测："只做 TCP 连通性，不关心是谁"
- 刻意不做超时锁："用户对'卡住了就重启一下'有预期，不能把人锁在门外"

---

## 7. 安全防护与红队评估

完整分析见 [`02-desktop-security.md`](02-desktop-security.md)（1402 行，含主控补充附录）。

### 7.1 防护体系总览

| 层次 | 机制 | 强度 |
|---|---|---|
| Electron fuses | **8 项全部按安全意图设置** + 精确位串断言 | **高** |
| asar 保护 | `EnableEmbeddedAsarIntegrityValidation` + `OnlyLoadAppFromAsar` | **高** |
| 渲染进程隔离 | `contextIsolation: true` / `nodeIntegration: false` / `sandbox: true` | **高** |
| preload 暴露面 | 12 个具名方法，**无通用 channel 透传** | **高** |
| 运行时完整性 | Ed25519 签名覆盖 **29,250 个文件** | **高** |
| 后端运行时守卫 | **拒绝带外导入**（实测撞到） | **高** |
| 加密 skill capsule | 全部 `.pyd` 检索 skill 名命中 0 | **高** |
| 发布工程 | 代码签名（Certum Authenticode）+ 增量安装 + 事务回滚 | 高 |
| Cython 编译 | 只提高门槛（字符串/符号仍可提取） | 中 |
| **Claude CLI 工具策略** | 黑名单 + 事后对账（补偿性控制） | **弱** |

### 7.2 启动状态机（实测数据）

从产品自身写入的 `logs/startup-latest.json` 还原的 **8 阶段编排**：

| # | phase | 中文文案 | 累计耗时 | **本阶段耗时** |
|---|---|---|---|---|
| 1 | `update_recovery` | 检查上次安装或更新是否完成 | 251 ms | 251 ms |
| 2 | `integrity` | 校验程序与内置运行环境，请稍候 | 255 ms | **879,403 ms（14.66 min）** |
| 3 | `storage` | 检查资料位置，保留已有工作区 | 879,658 ms | 3,619 ms |
| 4 | `runtime` | 检查工具可用性（不等待 LaTeX 在线安装） | 883,277 ms | 3,619 ms |
| 5 | `updates` | 检查更新信息 | 883,965 ms | 688 ms |
| 6 | `backend` | 正在启动本地服务，冷启动最多等待 3 分钟 | 911,978 ms | 28,013 ms |
| 7 | `frontend` | 本地服务已就绪，正在打开主界面 | 1,015,491 ms | 103,513 ms |
| 8 | `ready` | 主界面已打开 | **1,024,525 ms** | 9,034 ms |

> 【直接提取】`[证据: version=2.1.2, pid=8724]`
> **注意**：`elapsed_ms` 是**自启动起的累计值**，不是本阶段耗时
> （`startup-status.js:78` → `Date.now() - this.started`）。本阶段耗时 = 相邻两次 `set()` 之差。

**红方要点（★关键）**：总冷启动 **17.08 分钟**中，**14.66 分钟（86%）全部消耗在完整性校验上**。

这修正了一个容易犯的误读：从累计值表面看像是 `storage` 阶段占了 14.7 分钟，
但实际上 `main.js:1019` 是**先写 `integrity` 文案、再 `await` 校验本体**，
因此这段耗时归属 `integrity`；`storage` 实际只有 **3.6 秒**。
两条独立路径（累计差值 / 日志绝对时间戳 12:03:47.440Z → 12:18:26.843Z）互相印证。

⇒ **全量校验确实执行了**（有效吞吐 4273.9 MB ÷ 879.4 s = **4.86 MB/s**，
与"冷缓存 + 27,752 次独立 `open`"的预判吻合），**不是防线缺口**。
这也让可用性缺陷更加聚焦：瓶颈是**单一的、可优化的校验实现**，而非分散的资料扫描逻辑。

### 7.3 完整性体系（已实证）

| 项 | 值 |
|---|---|
| 清单分组 | `files` **1,498** + `runtime_files` **27,752** = **29,250** |
| 签名算法 | **Ed25519**（`key_id: intl-update-2026-08-a`） |
| 覆盖 | 含 `resources/app.asar` 自身（**自举式校验**） |
| `CRITICAL_RUNTIME_FILES` | 13 条，含 `python311._pth`（可注入 hook）、`libcrypto-3.dll`/`_ssl.pyd`（AES-GCM 真正落点） |
| 校验时机 | 启动时**恰好一次**，位于更新恢复之后、任何后端/前端代码启动之前 |
| 失败后果 | `failStartup` → 后端不启动、主界面不打开（**fail-closed**） |

**本次独立验证结果**：

- 逐文件 sha256 复算：**1498 / 1498 全部 MATCH**
- `runtime_files` 存在性与尺寸：**27,752 / 27,752 全部一致**
- **Ed25519 签名用 `release-trust.js` 内固化公钥独立验签：`true`**
- fuse wire 从 exe 内读出：`version=1 length=8 wire=01001101`，与代码内期望值一致
- `resources/app.asar` 单点校验：大小 889,727 字节、sha256 吻合

⇒ 该机制**真实生效**，且**本次分析对象是未被改动的原始安装**。

### 7.4 后端运行时守卫（实测）

```
RuntimeInspectionUnavailable: 完整性验证或运行时约束未通过，未执行任何能力；请使用官方安装器修复
```

> 【直接提取】`[证据: tools/route_probe.py, 23.7 s 后抛出]`

校验在**导入期**执行（而非请求期），不存在"先起来再验"的窗口——**位置选择正确**。

#### ⚠️ 但守卫的范围远比初判窄（后续修正）

**初判**：曾据此认为「动态分析路径被关闭」。
**实测修正**：守卫**只拦截 3 个模块**，其余 **159 / 162 可正常导入并内省**：

| 被拦截模块 | 原因 |
|---|---|
| `main` | 导入时执行完整性校验 |
| `routers.client_config` | 同 |
| `services.client_gateway_config` | 同 |

拦下时的中文原文：`网关验证组件完整性检查未通过；未执行该组件，请使用官方安装包修复`

**这带来本次分析最大的单项收获**——叶子模块内省恢复了后端的**完整接口规格**：

| 对象 | 数量 |
|---|---|
| 模块 docstring（**即设计文档**） | 158 个 / 35,819 字符 |
| 类 / 异常类（含错误码） | 422 / 132 |
| **带类型标注的可用签名** | **7,077** |
| 类方法 / 模块级函数 | 6,194 / 1,719 |
| dataclass 字段 | 330 |
| **Pydantic API 契约** | 6 个模型 / 33 个字段（类型+默认值齐全） |

**这直接改变了复现可行性**：从「照符号表猜测重写」变为「**照接口规格复现**」。
详见 [`13-reproduction-assessment.md`](13-reproduction-assessment.md) 与
[`12-backend-spec-recovered.md`](12-backend-spec-recovered.md)。

**教训**：拿一个被守卫拦下的样本（`main`）去推断整个防线的覆盖面，是**过强的归纳**。
应当逐个模块试，才能得到真实边界。

### 7.5 Electron 加固（fuse 实测）

| # | Fuse | 设置 | 含义 |
|---|---|---|---|
| 0 | `RunAsNode` | **false** | 阻止把 exe 当通用 Node 解释器 |
| 1 | `EnableCookieEncryption` | **true** | Cookie 加密 |
| 2 | `EnableNodeOptionsEnvironmentVariable` | **false** | 阻止 `NODE_OPTIONS` 注入 |
| 3 | `EnableNodeCliInspectArguments` | **false** | 阻止 `--inspect` 挂载 |
| 4 | `EnableEmbeddedAsarIntegrityValidation` | **true** | asar 被篡改则拒绝加载 |
| 5 | `OnlyLoadAppFromAsar` | **true** | 阻止替换为解包目录 |
| 6 | `LoadBrowserProcessSpecificV8Snapshot` | false | 未随包提供该文件 |
| 7 | `GrantFileProtocolExtraPrivileges` | **true** | 渲染进程仍以 `file://` 加载 |

位串 `01001101` 逐位吻合。且源码含 `strictlyRequireAllFuses: true` 与精确断言：

> // Electron 33 has eight V1 fuses. Keep this exact so an Electron upgrade that
> // adds a fuse fails the build until the new security decision is reviewed.

⇒ **升级 Electron 若新增 fuse，构建会直接失败，直到有人显式评审**。这是很高的供应链纪律。

### 7.6 ★ 红队情报：蓝方自己记录的已确认攻击面

**蓝方在 `chat_tool_policy` 的源码注释中，完整记录了 Phase 0 实测出的 Claude CLI 工具策略缺陷**：

| # | 蓝方原文 | 可利用性 |
|---|---|---|
| 1 | 「实测：请求 7 个白名单工具，CLI 实际给了 **27 个**」；「`--allowedTools` **不是**工具挂载白名单」 | **高** — 白名单语义不成立 |
| 2 | 「不加它时，【**工作区根目录的 `.mcp.json` 会被自动加载**】」；「我在工作区放了个假 MCP server，它连上了、工具进了主会话」 | **高** — 工作区正是用户上传文件落地处，投毒即可注入任意能力 |
| 3 | 「黑名单是穷举的，CLI 升级加了新工具就会【**无声漏进来**】」 | **中** — 版本升级即产生盲区 |
| 4 | 「那些工具能发飞书消息、能调外部 LLM、能读写文件，【**全在我们的闸外面**】」 | **高** — 数据外泄通道 |
| 5 | 「直调 skill，绕过提议卡片和串行队列」 | **中** — 绕过人工确认闸 |
| 6 | 「派子代理。实测子代理【会继承】禁用清单（写不出文件）」 | 低（对蓝方有利） |

蓝方的缓解是「每次起主会话都对账一次实际清单，发现白名单外的工具立刻告警」。

**红队评估**：这是一套**基于运行时对账的补偿性控制**，而非结构性隔离。
蓝方自己承认"黑名单挡不住（名字不可预知），全在审计闸外面"。
**根本原因**是主会话与不可信工作区共享同一文件系统命名空间。
结构性修复需要**把工作区挂载点与 MCP 配置发现根分离**，而非继续扩充黑名单。

> 本节全部【直接提取】自 `.pyd` 字符串表。仅做静态分析与评估，未实施任何攻击行为。

### 7.7 红队总评（反直觉的结论）

**蓝方在"传统桌面安全"上做得比"LLM 智能体安全"好得多。**

- 攻桌面壳（fuses / asar / 渲染隔离 / preload）**性价比极低**——
  8 个 fuse 全部正确设置、preload 无通用透传、完整性清单 29,250 文件经独立验签。
- 真正的薄弱面在 **Claude CLI 工具授权层**，而蓝方**自己在源码里承认了这一点**。

### 7.8 代码保护的元数据卫生失分

蓝方的**内容加密**做对了（capsule + 运行时守卫），但**元数据卫生**失分严重：

| 泄漏源 | 泄漏内容 |
|---|---|
| `.pyc` 的 `co_filename` | 开发机绝对路径 → 上游项目名 |
| 数据库文件名 `aris.db` | 上游项目简称 |
| 随包分发的 `templates/README.md` | 上游 `/skill-name` 引用与 workflow 编号 |
| 随包分发的明文提示词 | 同上开发路径（明文！） |
| 内置 `_modex-build-inputs.json` | **547 条源码路径 + SHA256**，等于完整架构地图 |

五者叠加，**直接暴露了血缘关系**。这是红方本次最大的情报收获。

### 7.9 ★ 子代理发现的四个架构级缺口

`02-desktop-security.md` 在深度回读中发现了四项**设计层面**（而非实现层面）的问题：

#### G1｜完整性是"启动时的一次性事件" ⇒ TOCTOU 窗口极大

- `verifyRuntimeTree` 全仓仅 **2 处引用**（定义 + `main.js:116`）——校验后**不持有文件句柄、不再复核**。
- ⇒ **TOCTOU 窗口 = 15 分钟校验期 + 整个运行期**。
- 加剧因素：脚本实测本机 ACL 显示 `resources/`、`resources/app/`、`resources/app.asar`
  对当前用户为 **FullControl**，而进程令牌是 Medium 完整性（**未提权**）；
  反观 `runtime/` 只有 `Users:(RX)`。
- **结构性动机**：更新机制**要求**用户可写 `resources/app`（`update-helper.js` 以用户权限的
  `node.exe` 落盘）——即**为了能自更新，必须把校验对象做成用户可写**。
- `【推测】` 该 ACL 是否普遍适用需在目标机复核（可能是本机自更新留下的痕迹）。

#### G7 + G13｜清单存在零覆盖盲区，且信任根是单密钥

| 未覆盖对象 | 风险 |
|---|---|
| `runtime/texlive/**` | 论文编译链（`.cls`/`.sty` 被替换可影响产出） |
| `runtime/draw.io/**` | 图表链 |
| **`miktex-setup.exe`** | **被主进程直接 `spawn` 执行**，却不在哈希清单内 |
| `resources/elevate.exe` | 提权辅助程序 |
| **Electron shell 本体** | `exe`/`dll`/`pak`/`icudtl.dat`/`v8_context_snapshot.bin`/`snapshot_blob.bin`/`locales` |

- 脚本实测这些关键词在清单中**命中 0**。
- 更关键：`assertPinnedUpdateConfig` 要求键集合**完全相等**且信任根为**单密钥**
  ⇒ **私钥一旦泄露即"轮换死锁"**（新公钥无法通过已失效的旧密钥下发）。

#### G3 + G15｜`--mh-capture` 是唯一跳过签名校验的启动路径

- `main.js:40-43` 在处理单实例锁 / 存储 / 完整性校验**之前**就 `return`。
- 该模式下截图窗口可导航任意 `url`/`file`、`out` 任意路径，并支持 `printToPDF`。
- ⇒ 产品在「**不校验**」与「**校验 15 分钟**」之间**缺少中间档**。

#### G4｜preload 配置合格，但信任锚语义弱

- 配置本身合格：9 个 `invoke` + 3 个 `send`、三隔离齐全、**9/9 均有 `assertTrustedRenderer`**。
- 但准入条件就是 `origin === http://127.0.0.1:<port>`，
  而该 origin **同时托管前端 bundle、后端 API 与（推断）用户产物预览**。
- **Electron 侧无 CSP 兜底**（后端有 `_desktop_content_security_policy`，
  但其指令串在全部 `.pyd` 字符串表零命中，**强度未评估，不作臆造**）。

### 7.10 已实证的正面保证（可直接引用）

子代理完成的独立验证中，以下几项**超出静态阅读**、属实测结论：

| 结论 | 验证方式 |
|---|---|
| 清单 1498 + 27,752 条与磁盘**完全一致（0 缺失 / 0 多余 / 0 哈希不符）** | 脚本逐文件复算 |
| **Ed25519 签名验签 = true** | 用 `release-trust.js` 固化公钥 + 复算 canonicalJson（5,001,244 字节） |
| fuse 实测线 `01001101`（哨兵偏移 158,719,472） | 从 exe 二进制读出并比对代码期望值 |
| **哈希链闭合**：清单中 `desktop/security/{release-trust,update-security,update-transaction}.js` 的 sha256 **等于** `build-inputs-paths.txt` 中同名源码哈希 | ⇒ **部署的更新器信任代码 = 被审计的源码** |
| Authenticode 强制 `Valid` + **必须有时间戳证书** + SHA-256 + Subject 校验 | 阅读发布校验逻辑 |
| **OS 级 `netstat` PID 归属核验通过后，才向后端发送控制令牌** | `backend-health.js:11-12,31-40` |
| journal / 备份 / 启动恢复的崩溃一致性 | `update-transaction.js` |

**评价**：第三项（哈希链闭合）尤其体现工程水准——它把"发布产物"与"审计源码"用哈希绑定，
使供应链审计结论可被机械验证。

---

## 8. 对 modemon 的复现与改进建议

### 8.1 复现路线（按性价比排序）

| 优先级 | 动作 | 依据 |
|---|---|---|
| **P0** | 取用**上游 ARIS** 的 83 个 skill 作为方法论骨架（**连同 9 个模板原样复用**） | §2.2、§2.3；上游为 AI 科研血统，未改写 |
| **P0** | 照抄 `schema.sql` 的 **16 条设计约束** | §4.2，明文可得，真实踩坑经验 |
| **P0** | **自建数模竞赛特化层**（`comp_*` 中英文双版本 + 竞赛封面 + 合规检查） | §2.3：上游**完全没有**竞赛支持 |
| **P1** | 复现**工作流引擎步骤 + 质量门**（图表健康检查静态/动态双轨、FIGURE_MANIFEST 权威归类、四种合法跳过、页数预检） | §5.4，规则语义已从中文串完整恢复 |
| **P1** | 复现**工作区 `CLAUDE.md` 上下文注入 + vision 图片描述** | §5.5，低成本高收益 |
| **P1** | 采用 **loopback 作用域令牌** 隔离 CLI 子进程与真实 API Key | §6.3 |
| **P1** | 复现**防幻觉机制**：程序拼表 + 数值从 `all_results.json` 读 + 去 AI 味约束 | §5.3，产品护城河 |
| **P2** | 中文排版规范：**从公开 `.cls` 反推**（不必逆向） | §5.2，`competition_zh.json` 自陈对标 `cumcmthesis.cls` |
| **P2** | 单实例互斥（OS 文件锁 + 父进程看护 + 端口探测） | §6.5 |
| **P3** | 商业化层（License / 计费 / 钱包）按需取舍 | §6.1 |

### 8.2 可以超越蓝方的四个差异点

1. **启动速度**：蓝方冷启动 **17.08 分钟**，其中 **14.66 分钟（86%）全耗在完整性校验**。
   这是最容易取得体验优势的地方，且问题很聚焦——**瓶颈是单一的校验实现**
   （27,752 次独立文件 `open`，实测有效吞吐仅 4.86 MB/s），而非分散的资料扫描逻辑。
   改为增量/异步扫描 + 按需加载 runtime，即可形成碾压式体验差距。
2. **MCP 攻击面**：蓝方靠事后对账补偿，且自认结构性不足。
   若从架构上把工作区与 MCP 配置发现根**隔离**，可结构性消除该面。
3. **安装体积**：7.16 GB 中 Python 环境占 4.24 GB。按需拉取可大幅降低分发成本。
4. **完整性校验策略**：蓝方确实**完整执行了** 29,250 文件的全量哈希（已实证，非假防线），
   但代价是**每次冷启动 14.66 分钟**。建议改为**分层信任**：
   全量校验可执行代码（`.pyd` / `.dll` / `.exe` / `app.asar`），
   运行时依赖（`site-packages` 的 26,678 个 `.py`、texlive、draw.io）改用包管理器指纹 +
   抽样校验。既保留安全语义，又消除 86% 的启动成本。

### 8.3 不建议照抄

- **加密 skill capsule**：成本高、损害可维护性与生态。除非同样要做闭源商业分发。
- **147 个发布/审计脚本**：双发行版 + 代码签名 + 增量安装约束下的产物，与 modemon 阶段不匹配。
- **Cython 编译全部后端**：并未真正保护逻辑（字符串与符号全泄漏），只提高门槛，
  却显著增加构建与调试成本。**真正起作用的是运行时守卫与 capsule 加密**。
- **全量 29,250 文件哈希清单**：与 17 分钟启动痛点直接相关。

### 8.4 从蓝方架构缺口直接转化出的设计建议

以下四项由 §7.9 的红队评估直接推导，是 modemon 可以"出生即优于蓝方"的地方：

| # | 蓝方的缺口 | modemon 应采取的方案 |
|---|---|---|
| 1 | **G1 TOCTOU**：完整性只在启动时校验一次，之后不持句柄、不复核 | 校验后**持有可执行文件句柄**（Windows 上以 `FILE_SHARE_READ` 打开并保持），或对关键入口做**运行期周期复核**；并避免"校验对象必须用户可写"这一自更新妥协——用**独立提权更新服务**替代以用户权限落盘 |
| 2 | **G7/G13 清单盲区**：texlive / draw.io / elevate.exe / Electron shell 本体零覆盖 | 清单覆盖**所有会被 `spawn` 或加载的对象**；尤其**任何被主进程直接执行的文件**必须在哈希范围内 |
| 3 | **G13 单密钥轮换死锁** | 信任根用**多密钥 + 版本化密钥集**，支持"用新密钥签发包含新公钥的配置"，使轮换不被旧密钥失效阻塞 |
| 4 | **G3/G15 启动档位缺失**：只有"不校验"（`--mh-capture`）与"校验 15 分钟"两档 | 提供**中间档**：分层校验（可执行代码全量、运行时依赖指纹+抽样），并让**旁路模式不可访问任意 URL/路径**（收窄 `--mh-capture` 的输入面） |

> 补充：G4 的信任锚问题（origin 既托管 API 又托管用户产物）建议用
> **不同端口或不同 origin** 分离"应用前端"与"用户产物预览"，使 preload 的
> `assertTrustedRenderer` 语义变强。

### 8.5 接口契约红线（复现时必须对齐，否则前后端对接会失败）

由 `03-frontend.md` 从前端侧恢复的**硬性契约**：

| # | 契约 | 说明 |
|---|---|---|
| 1 | **前端不发鉴权头** | 仅"GET 接入方式"时带 `X-Modex-Mode-Read: identity`；安全性依赖**本地回环 + Electron 端口白名单**（`http://127.0.0.1:{port}/*`、`ws://127.0.0.1:{port}/*`） |
| 2 | **错误响应结构** | `{detail: string \| {message, code}}` —— 两种形态前端都要能解析 |
| 3 | **检查点 resolve 回包** | 必须回 `{status: 'resolved'}` |
| 4 | **`/checkpoints/current` 回包** | 必须含 `remaining_seconds`，否则前端判定「后端仍是旧版检查点逻辑」 |
| 5 | **乐观并发** | `proposal_revision` / `state_revision` / `expected_revision` / `checkpoint_id` 不匹配即拒绝并触发重新同步 |
| 6 | **幂等键** | `turn_id`（聊天 outbox 重发）、`request_id`（生图）、`version_id`（编辑器撤回） |
| 7 | **编辑器 SSE 的 run id** | 从**响应头 `X-Editor-Run-Id`** 取，不在 body 里 |

> 第 1 条是**安全设计的直接推论**：既然前端不带凭证，那么后端的信任边界就完全
> 建立在"请求来自本机回环 + Origin 白名单"上。这解释了为什么 §7.9 G4 的
> **origin 分离**如此重要——它同时是可用性约束和安全边界。

---

## 9. 分析资产索引

工作区：`E:\02_Installers\DailyApps\Modex-MH-Agent-RE`

### 9.1 报告

| 文件 | 行数/体积 | 内容 |
|---|---|---|
| **`reports/ANALYSIS-主报告.md`** | — | **本报告（总纲）** |
| `reports/00-lineage.md` | 9.0 KB | 血缘鉴定 · **六层证据链** + 增量边界 |
| `reports/01-backend-api-and-data.md` | 19.4 KB | 后端架构 · 92 端点（子集）· 数据模型 · 16 条设计约束 |
| `reports/02-desktop-security.md` | **154.9 KB / 2531 行** | 桌面主进程 · 启动链路 · 更新 · 完整性 · Electron 加固 · 红队评估 · 含主控附录与勘误 |
| `reports/03-frontend.md` | **80.8 KB / 732 行** | 前端技术栈 · 路由 · chunk↔模块映射 · **142 端点** · **2 条实时通道** · store · 竞赛业务特征 |
| `reports/04-methodology.md` | **85.0 KB / 1107 行** | 方法论 · 中文排版 · 质量门 · **ARIS 差分** |
| `reports/06-runtime-db.md` | 7.2 KB | 运行时 `aris.db` 结构（只读） |
| `reports/07-surface-extract.md` | 15.0 KB | IPC 通道 · 模块符号表（确定性脚本） |
| `reports/08-route-probe.md` | 0.6 KB | 路由探测与**守卫拦截记录** |
| `reports/09-frontend-api-surface.md` | 4.3 KB | 前端 API 面（92 条子集；完整 142 条见 `03-frontend.md` §4） |
| `reports/10-integrity-verification.md` | 3.0 KB | 安装完整性实证校验 |
| **`reports/11-recoverability.md`** | — | 后端恢复度量化（含剔除解释器样板的修正记录） |
| **`reports/12-backend-spec-recovered.md`** | — | **★ 内省恢复的后端接口规格**（模块 docstring 样例） |
| **`reports/12-backend-spec.json`** | — | **★ 机器可读规格**：159 模块 × 类/方法/签名/字段/异常码 |
| **`reports/13-reproduction-assessment.md`** | — | **★ 复现可行性评估：能不能复现、还差什么、三条路线** |
| **`reports/14-workflow-engine-spec.md`** | — | 主线模块 `workflow_engine` 完整规格（9 类 / 56 方法 / 116 函数 / 89 docstring） |
| **`reports/15-workflow-engine-probe.md`** | — | 零参访问器求值（**恢复出美赛 8 步流水线真实数据**） |
| **`reports/16-workflow-engine-config.md`** | — | 参数化求值（**国赛 8 步 + 阈值 + 超时 + 页码规则**，67/67 成功） |
| **`reports/17-comp-pipeline-blueprint.md`** | — | **★★ 数模竞赛流水线实现蓝图（modemon 可直接照此实现）** |
| **`reports/18-api-contract.md`** | — | **★★ 权威 API 契约：205 条路由全表 + 40 个请求体模型字段 + 65 条端点文档** |
| **`reports/18-api-contract.json`** | — | **★ 机器可读权威契约**（含 Literal 枚举真值） |
| `reports/cjk-strings-from-pyd.md` | 69.2 KB | **1002 条高置信度中文串**（按 44 模块） |
| `reports/build-inputs-paths.txt` | 58.0 KB | **547 条源码路径 + SHA256**（蓝方的工程地图） |
| `reports/aris-skills-catalog.md` | 20.4 KB | 上游 ARIS 83 个 skill 官方目录 |
| `reports/_api-paths.txt` | 3.6 KB | 92 条端点原始清单（确定性提取） |

### 9.2 原始证据

| 路径 | 内容 |
|---|---|
| `asar/` | **Electron 明文 JS**（main / preload / updater / capture / 17 个 security 模块）**已用清单 SHA256 校验通过** |
| `pyc_dump/` | 52 个 `.pyc` 的反汇编 + 结构转储 + **泄漏的原始路径** |
| `strings/` | 11,246 条 `.pyd` 字符串（含完整 qualname 符号表） |
| **`beauty/`** | 26 个前端 chunk 的**美化产物**（`.pretty.js`，共约 2.5 MB，供定点阅读） |
| `upstream-ARIS-cache.json` | 上游元数据本地缓存（离线优先） |

### 9.3 可复现脚本

| 位置 | 脚本 | 作用 |
|---|---|---|
| `tools/`（主控） | `pyc_dump.py` | `.pyc` 反汇编 |
| | `strings_dump.py` / `strings_cjk.py` / `cjk_strings.py` | `.pyd` 字符串提取（含 CJK 高精度过滤） |
| | `extract_surface.py` | IPC 通道 + 模块符号表 |
| | `frontend_api_extract.py` | API 端点（**92 条子集**——只匹配 `/api/` 字面量，见 §3.5 方法学修正） |
| | `route_probe.py` | 路由探测（含**守卫拦截记录**） |
| | `verify_integrity.py` | 完整性实证校验 |
| | `db_inspect.py` | 运行时库只读检查 |
| | `aris_cache.py` / `lineage.py` | 上游缓存 + 血缘鉴定（离线优先） |
| `tools/_fx/`（子代理） | `verify-install-tree.js` | 1498 + 27,752 文件逐条哈希复算 |
| | `manifest-stats.js` | 清单结构与分布统计 |
| | `read-fuses.js` | 从 exe 二进制读出 fuse 线 |
| | `final-check.js` | 收尾一致性核对 |
| `tools/`（前端子代理） | `beautify.js` 等 | 括号感知的 bundle 美化与调用点提取 |

```powershell
$PY = 'E:\02_Installers\DailyApps\Modex-MH-Agent\runtime\python\python.exe'
$RE = 'E:\02_Installers\DailyApps\Modex-MH-Agent-RE'
$APP = 'E:\02_Installers\DailyApps\Modex-MH-Agent\resources\app'

& $PY "$RE\tools\pyc_dump.py"            $APP              "$RE\pyc_dump"   # .pyc 反汇编
& $PY "$RE\tools\strings_dump.py"        "$APP\backend"    "$RE\strings" 8  # .pyd 字符串
& $PY "$RE\tools\cjk_strings.py"         "$APP\backend"    "$RE\reports\cjk-strings-from-pyd.md"
& $PY "$RE\tools\extract_surface.py"                                        # IPC + 模块符号表
& $PY "$RE\tools\frontend_api_extract.py"                                   # API 面
& $PY "$RE\tools\route_probe.py"                                            # 路由探测(含守卫)
& $PY "$RE\tools\verify_integrity.py"                                       # 完整性实证
& $PY "$RE\tools\db_inspect.py"                                             # 数据模型(只读)
& $PY "$RE\tools\aris_cache.py"                                             # 上游缓存(仅首次联网)
& $PY "$RE\tools\lineage.py"                                                # 血缘鉴定
```

---

## 10. 方法与可信度声明

### 10.1 已完成的验证

| 验证项 | 结果 |
|---|---|
| asar 解包正确性 | 用蓝方自带 SHA256 逐个校验，7 个关键文件**全部 MATCH** |
| `.pyc` 可解析性 | 52 个文件全部成功 `marshal.loads`（Python 3.11.9 与产物 ABI 一致） |
| 运行时数据库 | 以 `mode=ro` **只读**打开，未做任何写入 |
| 安装完整性 | 1498/1498 应用文件 + 27,752/27,752 运行时文件**全部一致** |
| **Ed25519 签名独立验签** | **`true`**（用固化的公钥独立复算） |
| fuse 位串 | 从 exe 内读出 `01001101`，与代码期望值一致 |
| 目标完整性 | 全程未修改目标任何文件 |

### 10.2 证据分级

统一四档：`【直接提取】`（明文/精确命中）· `【反汇编推断】`（`.pyc` 字节码）·
`【推断】`（有明确依据）· `【推测】`（依据较弱）。

### 10.3 未获取 / 存疑事项（**明确声明，未作推测填充**）

| 事项 | 状态 |
|---|---|
| Modex 的 **skill 正文** | **未获取**——加密 capsule，全部 `.pyd` 检索命中 0 |
| 各端点的 **HTTP 方法**与请求/响应体 | 未获取——后端守卫阻断导入；bundle 中方法路径紧耦合 |
| ~~**WebSocket 协议**~~ | **已获取**——`03-frontend.md` §5 恢复出 11 种工作流事件 + 12 种聊天事件 + 13 种 run_event，以及 `ping`/`pong` 心跳与退避策略；后端 `.pyd` 侧事件字面量未落盘（Cython 内联常量），故以前端消费端为准 |
| ~~`integrity` 阶段是否真完成全量校验~~ | ~~存疑~~ → **已证伪并关闭**：全量校验**确实执行**（实测 4.86 MB/s，见 §7.2 勘误）。保留下划线以便读者不重复该误读 |
| `runtime-integrity-manifest.json` 逐条内容 | 仅统计规模与结构；已抽样校验 16/16（另有子代理全量 1498/1498 复核） |
| **后端 CSP 的实际指令串与强度** | **未获取**——全部 `.pyd` 字符串表零命中，无法评估（`02-desktop-security.md` §5.5） |
| **`--mh-capture` 旁路是否为核心设计意图** | 已确认它是**唯一跳过 Ed25519 校验的启动路径**；但其定位属【推测】 |
| **`resources/app` 的用户可写 ACL 是否普遍适用** | 本机实测为 FullControl，但**可能只是自更新留下的痕迹**，需在目标机复核（【推测】） |
| 中文竞赛正文字符预算的具体数值 | 仅见 `800（含图表），英文` 片段，中文侧数值未出现 |
| `docx_export.pyd` 渲染器内部实现 | 仅 1 条中文串，无法恢复 |
| 上游 **ARIS 的 LICENSE 条款** | **未核实**——复现前必须自行确认授权范围 |

### 10.5 ★ 勘误记录（保留而非静默改写）

本报告初版（及 `02-desktop-security.md` 附录 A）曾基于 `startup-latest.json` 中
`integrity` 的 `elapsed_ms = 255` 推断「该阶段仅 255 ms 完成、全量校验可能并未真正执行」。

**该推断错误，已撤回。** 根因是把**累计耗时**误当作**阶段耗时**
（`startup-status.js:78` → `elapsed_ms = Date.now() - this.started`），
且未注意 `main.js:1019` 是**先写文案、再 `await` 校验本体**。

- **发现者**：桌面安全子代理（回读源码时发现）
- **复核者**：主控（用日志绝对时间戳独立交叉验证通过）
- **影响范围**：§7.2 耗时归属、§8.2 建议 1 与 4、§10.3 存疑项 —— 均已修正
- **纠正后的结论**：全量校验**确实执行**（4.86 MB/s 与冷缓存预判吻合），
  且真实瓶颈更聚焦——**86% 的启动时间消耗在完整性校验**上

保留此记录而非静默改写，以便读者据此判断其余结论的可信度。

### 10.4 合规提醒

1. **上游 ARIS 的 LICENSE 条款必须先核实**，再决定能否将其 skill 用于 modemon；
2. 本文档包含对第三方商业软件的内部结构分析，**不应公开发布或用于商业用途**；
3. 报告中引用的蓝方源码注释属其著作权内容，引用仅限教学分析；
4. 全部分析为**只读静态逆向 + 只读取证**，未实施任何攻击、未修改目标、未绕过任何保护机制。
