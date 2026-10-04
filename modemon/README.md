# modemon（骨架）

数学建模竞赛智能体。本目录是对红蓝对抗中**蓝方产品（Modex-MH-Agent）逆向分析的可执行复现**。

---

## 一、这份骨架是怎么来的

| 内容 | 来源 | 性质 |
|---|---|---|
| 竞赛流水线（国赛/美赛 8 步、展示名、产出文件名） | 蓝方 `_comp_zh_steps()` / `_comp_en_steps()` **内省求值** | **真值** |
| 每步阈值（最小字节、静默超时、页码规则、字符预算） | 纯访问器求值 | **真值** |
| 数据结构字段（`StepDef` / `TemplateDef` / 各请求体模型） | 内省 + `model_fields` | **真值** |
| API 路径与请求契约（205 条路由、42 个请求体模型） | `APIRouter` 内省 | **真值** |
| 数据模型结构（11 张表 + 约束语义） | `schema.sql` 明文 + 设计注释 | **真值** |
| 算法实现（门控判定、返修状态机、模板动态重写） | — | **本项目自行编写** |

> **边界**：蓝方后端经 Cython 编译为原生机器码，**函数体不可恢复**。
> 逆向只提供了签名、docstring 与数据；**所有实现代码为本项目原创**。
> 完整证据链见上级目录 `../reports/`。

### 唯一的例外与合规说明

上游方法论骨架来自公开项目 [ARIS](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep)（**83 个顶层 skill**）。
**LICENSE 已核实：MIT License**（`Copyright (c) 2026 wanshuiyin`），
全文见本目录 [`LICENSE-ARIS.txt`](LICENSE-ARIS.txt)。

MIT 的唯一硬性条件就是**保留版权声明与许可全文**——两者都已内嵌到每个引用上游代码的模块
（`services/figure_spec.py`、`services/result_audit.py`、`services/skill_loader.py` 等），
并有测试断言防止被截断。其余（使用、修改、合并、发布、分发、再授权、出售）均无限制。

已引入的上游内容：
- `skills/figure-spec/`（正文 + `scripts/figure_renderer.py` 29.8 KB 确定性渲染器）
- `skills/experiment-audit/`（正文）
- `skills/catalog.json`（83 个 skill 的名称/路径/体量 + 来源与许可声明）

其余 81 个 skill **按需引入**，不做全量复制。

---

## 二、目录

```
modemon/backend/
├── main.py                      FastAPI 应用（模板/工作流/检查点/对话/设置/AI 申报）
├── models/schemas.py            Pydantic 模型（字段与枚举对齐恢复的契约）
├── services/
│   ├── workflow_engine.py       ★ 竞赛流水线 + 质量门（核心）
│   ├── workspace_guard.py       ★ 工作区守卫（.mcp.json 注入面）
│   ├── step_runner.py           ★ 门控 + 守卫 + 运行时 的编排
│   └── agent_runtime/           ★ 可插拔 agent 运行时
│       ├── base.py              能力声明 / RunSpec / 事件 / 结果
│       ├── claude_code.py       Claude Code 适配器（能力最全）
│       ├── deepseek_harness.py  DeepSeek Harness 适配器
│       └── echo.py              确定性测试替身
├── db/schema.sql                数据模型（含国赛 AI 申报表）
├── real_run_claude.py           真实端到端验证脚本（会调用模型）
└── tests/
    ├── test_workflow_engine.py  真值回归（75 项）
    ├── test_api.py              集成测试（71 项，真跑 HTTP 栈）
    └── test_agent_runtime.py    运行时层（78 项，确定性）
```

---

## 三、跑起来

```bash
cd modemon/backend
PY="E:/02_Installers/DailyApps/Modex-MH-Agent/runtime/python/python.exe"

# 测试（共 224 项）
"$PY" tests/test_workflow_engine.py     # 75 PASS
"$PY" tests/test_api.py                 # 71 PASS
"$PY" tests/test_agent_runtime.py       # 78 PASS

# 启动服务
"$PY" -m uvicorn main:app --host 127.0.0.1 --port 8770

# 真实端到端（会调用模型，默认限预算）
"$PY" real_run_claude.py --budget 0.40
```

---

## 四、已实现的主线

### 4.1 竞赛流水线（`services/workflow_engine.py`）

国赛（中文）与美赛（英文）**共用前 6 步，仅在第 7/8 步分叉**：

| # | 技能 | 国赛展示名 | 主产物 | 检查点 | 最小字节 | 静默超时 |
|---|---|---|---|---|---|---|
| 1 | `comp-prob-analysis` | 赛题分析 | `PROBLEM_ANALYSIS.md` | approve | 1,500 | 90 min |
| 2 | `comp-modeling` | 建模求解 | `MODELING_REPORT.md` | feedback | 2,000 | 90 min |
| 3 | `comp-code` | 编程实现 | `RESULTS.md` | approve | 1,000 | 90 min |
| 4 | `paper-figure` | 图表生成 | `figures/` | — | 500 | 90 min |
| 5 | `paper-figure-drawio` | 流程与架构图绘制 | `figures/` | — | 500 | 90 min |
| 6 | `comp-review` | 逻辑对抗复核 | `COMP_REVIEW.md` | — | 40 | 90 min |
| 7 | `comp-paper-{zh,en}` | 竞赛论文撰写 | `paper/main.tex` | approve | 10,000 | 45 min |
| 8 | `comp-compile-{zh,en}` | 编译与合规检查 | `paper/main.pdf` | — | 30,000 | 45 min |

**华为杯**通过 `paper_skill` 参数切换其专属技能，**不复制 DAG**。

### 4.2 质量门

- **主产物阈值**：低于阈值判「疑似未真实产出」。
- **`figures/` 目录型产物**：要求存在符合约定的 `fig_*` / `tikz_*` 图表文件
  （放无关文件骗不过检查）。
- **二级文件**：仅 `comp-code` 有强约束——必须同时产出入口代码
  与 `figures/all_results.json`（**防幻觉的数据锚点**：数值必须从它读，不由模型誊抄）。
- **空文件识别**：二级文件 > 50 字节，防占位。
- **页数预检**：仅 advisory。中文 ≈800 字/页、英文 ≈2200 字/页。国赛 30 / 华为杯 50 / 美赛 25。

### 4.3 三道后端硬闸

均在后端校验——**前端隐藏按钮挡不住双击、重发、直调接口**：

1. **提议确认**：`confirmed_at` 必须为空 + `revision` CAS 匹配。
2. **国赛 AI 申报**：`comp_cumcm` 必须已填 1–5 条真实 AI 使用记录**且**经参赛队核验确认，否则拒绝启动。
3. **仅对话模式**：`active_turn_mode='conversation'` 时拒绝产生执行提议；
   聚焦模式下后端**从库中读取** `focus_target` 并强制收紧 `execution_scope`
   （不信任 MCP 子进程传入的值——MCP 是独立进程，无法共享进程内状态）。

### 4.4 可插拔 agent 运行时（★ 相对蓝方的架构改进）

蓝方**硬绑定 Claude Code CLI**，后果写在他们自己的注释里：

> 【为什么要 audit()】黑名单是穷举的，CLI 升级加了新工具就会【无声漏进来】。
> 那些工具能发飞书消息、能调外部 LLM、能读写文件，【全在我们的闸外面】。

一旦运行时不可替换，所有约束只能**寄生在它的参数上**，厂商改语义即静默失效。

本层把运行时变成可插拔组件，并要求每个适配器**如实声明能力**：

| 能力 | Claude Code | DeepSeek Harness | Echo |
|---|---|---|---|
| 流式 | ✅ | ✅（stderr） | ✅ |
| 会话恢复 | ✅ | ❌ | ✅ |
| 思考强度 | ✅ 5 档 | ❌ | ❌ |
| 选模型 / 预算上限 | ✅ | ❌ | ❌ |
| 工具白/黑名单 | ✅ | ❌ | ❌ |
| **MCP 钉住** | ✅ `--strict-mcp-config` | ❌ | ❌ |
| 跳过环境自动发现 | ✅ `--bare` | ❌ | ❌ |

声明不支持时，上层可**拒绝执行**（严格模式）或**接受降级**——
无论哪种，`degraded` 都会如实记录。这是蓝方缺失的「对账」意识。

### 4.5 工作区守卫（★ 把蓝方的"检测"升级为"阻断"）

蓝方实测出的攻击面：

> 不加它时，【工作区根目录的 .mcp.json 会被自动加载】。
> 我在工作区放了个假 MCP server，它连上了、工具进了主会话。

蓝方的应对是「每次起主会话都对账一次实际清单」——**事后检测**。
本项目用**纵深两层**：

1. **能力层**：`--strict-mcp-config` 忽略一切环境 MCP 配置（事前阻断）；
2. **文件层**：`workspace_guard` 扫描工作区，把可被自动加载的配置
   **移动到工作区之外**的隔离区。

第 2 层**对所有运行时生效**，包括不具备 `mcp_pinning` 能力的那些。

### 4.6 人机协同闭环（WebSocket + 检查点）

**WS 只是通知，状态以 REST 为准。** 这条规则来自蓝方经验
（"WS 只是通知，断线/重启后仍应完整显示"），因此：

| 用途 | 通道 |
|---|---|
| 实时进度 | `ws://127.0.0.1:<port>/ws/{workflow_id}`，信封 `{type, workflow_id, ...}` |
| 心跳 | 客户端发文本 `ping` → 服务端回 `pong`（10s 服务端心跳） |
| **历史回放** | `GET /api/workflows/{id}/run-events`（**权威来源**） |
| 状态查询 | `GET /api/workflows/{id}` |

事件类型：`hello` / `step_started` / `run_event` / `checkpoint_created` /
`checkpoint_resolved` / `step_completed` / `step_failed` / `workflow_completed`。

### 4.7 ★ 执行必须后台化（实测教训）

实测中客户端在长步骤中途断开，FastAPI 会**取消请求协程**，
导致步骤永久停在 `running`（僵尸态，既没完成也没失败）。

因此：**长任务的执行周期不绑定在 HTTP 请求上。**

- `POST .../steps/{skill}/run` 与 `POST .../run` 一律返回 **202 + run_id**，执行在后台任务里；
- 进度由 WS 推送，权威状态走 REST 轮询；
- 后台任务用**独立数据库连接**（SQLite 连接不可跨任务共享）；
- 中断时会显式把步骤标记为 `failed` 并写明原因，**不留僵尸**；
- 配套 `POST /api/workflows/{id}/repair` 做僵尸自愈（对应蓝方的心跳修复机制）。

> 蓝方对此有同类机制：*"定期检查：如果数据库里工作流是 running 但没有对应的 task，自动修复。"*

### 4.8 运行事件落库与脱敏

只落**结构化、脱敏、可验证**的生命周期事件。蓝方写死的约束我们照做：

> 原始 stream-json、命令、Skill 内容、密钥和私有目录**永不进入这张表**。

| 处理 | 规则 |
|---|---|
| `LOG` / 思考过程 | **不落库**（过程草稿不是可验证事实） |
| 工具调用 | 只存**工具名**，`input` / `command` 一律不落库 |
| 凭据 | `sk-*` / `tp-*` / `Bearer *` / 32+ 位 hex → `«redacted»` |
| 工作区内绝对路径 | 改写为相对路径 |
| 工作区外绝对路径 | 只保留文件名 `«path:name»` |
| `session_id` | **不入事件表**——属 `chat_sessions.cli_session_id` 专用列，避免两个真相源 |
| 度量字段 | `cost_usd` / `tokens` / `exit_code` 保留（安全且有用） |

### 4.9 前端（无构建步骤）

`frontend/` 是单文件原生 HTML + ES module，由后端**同源托管**（`/` 与 `/static`）。
刻意不引入打包工具：骨架阶段用单文件前端即可形成闭环，
也让"后端同源托管"这一部署形态从第一天就被验证。

- 三栏：工作流列表 / 步骤与实时事件 / 控制台
- 步骤状态色点、检查点批准面板、WS 断线指数退避重连
- **运行时能力面板**：把各适配器「做不到什么」直接展示给用户，
  而不是让约束静默失效

### 4.10 成文链（docx / LaTeX）

竞赛论文的**实际交付物**。一条论文模型，两种导出，**共用同一套排版规格**。

| 模块 | 职责 |
|---|---|
| `typography.py` | 排版规格（**恢复真值**）+ 页数预算（**advisory**） |
| `paper_build.py` | 从工作区装配论文：章节 / **程序化表格** / 图表 / 参考文献 |
| `deai_lint.py` | 去 AI 味检查（可机械判定的部分**执行后强制检查**） |
| `latex_export.py` | LaTeX 生成（ctexart + booktabs） |
| `tex_runtime.py` | TeX 运行时探测（三态）与编译 |
| `docx_export.py` | DOCX 生成（python-docx + 规格驱动） |

#### 排版规格（恢复真值，对标公开的 `cumcmthesis.cls`）

```
A4 / 四边 2.5cm          SimHei + SimSun + Times New Roman + Consolas
正文 12pt / 1.5 倍 / 首行缩进 2 字符
标题 15 / 14 / 12 / 11pt，加粗，一级居中
三线表 1.5 - 0.75 - 1.5pt，表内 10.5pt
图宽上限 14cm            参考文献悬挂缩进 0.74cm / 10.5pt
```

> 规格自陈对标 `cumcmthesis.cls`，**因此这些数值可由公开来源反推，不需要逆向**。

#### ★ 程序化表格：绝不经过模型

蓝方验证过的做法，本项目照做：**表格由程序从 `figures/all_results.json` 生成**，
落成 `figures/TABLE_*.md`，数值逐字来自数据文件。

理由很直接：**模型誊抄数字会出错，而论文里的数字错了就是硬伤。**

#### 去 AI 味检查（恢复规则，强制而非提示）

| 规则 | 级别 |
|---|---|
| **`**标签：**` 的冒号必须写在 `**` 外**（复现材料标注为「最高频痕迹」） | error |
| 图题禁公式 | error |
| 图题 ≤ 15 汉字 | warn |
| 无自指表达（"作为一个AI"） | error |
| 无占位符残留（TODO/待补充） | error |

> 蓝方把这些写在**提示词**里让模型"尽量遵守"；本项目把可机械判定的部分做成 lint
> **在执行后强制检查**——写在提示里不等于一定做到。

#### 中文 Word 的三个坑（测试回读验证）

1. **东亚字体必须单独设 `w:eastAsia`**——只设 `run.font.name` 只作用于西文，中文仍是默认字体；
2. **首行缩进按「字符」而非磅**——用 `w:firstLineChars`（1/100 字符），写死磅值改字号后会错位；
3. **三线表靠边框控制**——上/下 1.5pt、表头下 0.75pt、中间无线。

#### TeX 运行时的真实约束（实测）

**随包 TeXLive 是未初始化的 MiKTeX**，直接编译会报：

```
It seems that this is a fresh TeX installation.
Please finish the setup before proceeding.
xelatex: major issue: So far, you have not checked for MiKTeX updates.
```

这印证了蓝方启动日志的「检查工具可用性（**不等待** LaTeX 在线安装）」，
以及 `latex:get-status` / `latex:install` 两个 IPC 的存在。

因此 `resolve_tex_runtime()` **如实报告三态**（`ready` / `fresh` / `missing`），
并把随包安装器的可用性一并暴露（对应蓝方的 `installerAvailable`）。
探测顺序：显式配置 → 系统 TeX → 随包 TeX（**优先复用系统已装且已初始化的**）。

相关 API：`GET /api/tex-runtime`、`GET /api/typography/{template}`、
`GET /api/paper/lint`、`POST /api/paper/export`。

### 4.11 其他

- 幂等：`turn_id` 去重（网络重试不会重复喂给主会话）。
- 检查点契约：`/checkpoints/current` 必带 `remaining_seconds`；
  `resolve` 回包必带 `status: 'resolved'`。
- 密钥不外泄：模型预设接口只回传 `has_api_key`，**绝不回传 `api_key`**。
- 提示中给出**工作区绝对路径**，并要求所有产出写在其中（实测：不给会被 agent 猜错路径）。
- 步骤记录**实际生效的模型**（取自模型流，而非请求参数）——预设可能被网关映射成别的模型。

---

## 五、与蓝方的刻意差异

| 项 | 蓝方 | modemon | 理由 |
|---|---|---|---|
| 响应模型 | 基本不声明（`response_model` 为 None/dict/list，内省真值 148/55/2） | **全部显式声明** | 前端可生成类型、契约自文档化、字段改名在开发期即暴露 |
| 门控返回值 | 布尔 | **结构化** `GateResult`（区分 `unavailable` / 真实缺陷） | 布尔无法表达「检查器坏了」，会把工具故障误判成产出不合格，触发无意义的修复循环 |
| AI 申报 | 前端流程 | **后端硬闸 + 独立表** | 可审计、可导出，且挡住直调接口 |
| 加密 capsule | 有（skill 会加密分发） | **无** | 成本高、损害可维护性与生态；本阶段不需要 |
| 发布工程 | 147 个脚本、双发行版、代码签名 | **无** | 与当前阶段不匹配 |

---

## 六、尚未实现与已知限制（明确声明）

| 项 | 原因 |
|---|---|
| 账号体系 / 计费钱包 / NewAPI 网关 | 商业设施，非当前目标（蓝方 205 端点中 58 个属此类） |
| CLI 网关代理（loopback 作用域令牌） | 需要先选定并固定 agent 运行时 |
| 内嵌 runtimes 的按需拉取 | 当前依赖本机已装的 Python/TeX；未做依赖自举 |
| 上游其余 81 个 skill 正文 | **按需引入**，不做全量复制（许可已核实为 MIT） |
| 模板矩阵的完整覆盖 | 当前 9 个模板名 / 2 套步骤序列；蓝方 30 个名 / 3 套序列。补齐计划见 `../reports/28-gap-closure-plan.md` |
| **多进程安全的广播** | **见下** |
| 前端为单文件原生实现 | 骨架阶段刻意不引入打包工具 |

> 已更新（此前声明已过时）：上游 LICENSE **已核实为 MIT** 并已合规接入两份 skill 正文；
> **完整 8 步流水线已跑通**（8/8 步、48 分钟、$6.00），详见 `../reports/23-full-pipeline.md`。

### 6.1 已知限制：WebSocket 广播是进程内单例

`services/broadcast.py` 的 `hub` 是**进程内单例**。当前骨架按单 worker 运行，
因此没有问题；但**一旦用多 worker（如 `uvicorn --workers 4`）启动，
跨 worker 的事件推送会丢失**——A worker 里产生的事件推不到连着 B worker 的客户端。

**注意**：这个限制**只影响实时性，不影响正确性**——
因为状态一律落库，前端重连后通过 `GET /run-events` 与
`GET /workflows/{id}` 就能完整还原。这正是「WS 只是通知，状态以 REST 为准」的价值。

生产化的三条可选修法（按成本排序）：

1. **DB 轮询兜底**（最小改动）：前端在 WS 静默超时后自动调一次 REST 补齐。
   对当前规模足够，且不引入新组件。
2. **单进程多协程**：用 `asyncio` 并发而非多进程；瓶颈在 I/O 的 agent 场景下通常可行。
3. **外部广播**：Redis Pub/Sub 或 Postgres `LISTEN/NOTIFY`，把 `BroadcastHub`
   的 `publish`/`subscribe` 换成外部实现。适合真正多副本部署。

---

## 七、验证状态

| 测试 | 结果 |
|---|---|
| `test_workflow_engine.py` | **75 PASS / 0 FAIL**（含 32 项与恢复真值的字段级比对） |
| `test_api.py` | **71 PASS / 0 FAIL**（真跑 HTTP 栈，覆盖 8 个场景） |
| `test_agent_runtime.py` | **80 PASS / 0 FAIL**（确定性，不发真实模型请求） |
| `test_collaboration.py` | **67 PASS / 0 FAIL**（WebSocket + 检查点 + 脱敏） |
| `test_typesetting.py` | **81 PASS / 0 FAIL**（排版规格 / 程序化表格 / 去AI味 / LaTeX / DOCX 回读） |
| **合计** | **374 项全通过** |
| **真实单步端到端** | ✅ 成功（§7.1） |
| **真实闭环（WS + 检查点）** | ✅ 成功（§7.3） |
| **真实成文链（PDF + DOCX）** | ✅ 成功（§7.4） |

### 7.1 真实端到端结果

`real_run_claude.py` 用本机 Claude Code 跑通 `comp-review` 步骤：

| 项 | 值 |
|---|---|
| 成功 | **True** |
| 三道质量门 | **全部通过** |
| 产物 | `COMP_REVIEW.md`（437 字节） |
| 耗时 / 花费 | 21.0 s / **$0.0325** |
| tokens in/out | 2338 / 623 |
| 能力降级 | 无 |
| 留档 | [`../reports/19-real-claude-run.md`](../reports/19-real-claude-run.md) |

### 7.2 测试与真实运行共同发现的 25 个缺陷（均已修复）

| # | 缺陷 | 发现方式 |
|---|---|---|
| 1 | `figures/` 目录只要非空即通过健康检查 → 放个无关文件就能骗过 | 单测 |
| 2 | 正文字符计数被 `split` 残留换行多算 1 | 单测 |
| 3 | `chat_messages` 漏建 `item_kind` 列；提议插入未提供 `content`（`NOT NULL` 违约） | 集成测试 |
| 4 | **`-p` 非交互模式默认拒绝写文件** → agent 干完活却落不了盘，质量门判「主产物缺失」 | **真实运行** |
| 5 | **`--mcp-config '{}'` 是非法配置**（须为 `{"mcpServers": {}}`）→ 表现为"权限问题"，实为 schema 不合法 | **真实运行** |
| 6 | 权限拒绝被当成致命错误 → 跳过了质量门，丢掉已完成的工作 | **真实运行** |
| 7 | **HTTP 请求取消导致步骤僵尸**：客户端中途断开 → 协程被取消 → 步骤永久停在 `running` | **真实闭环运行** |
| 8 | `\setlength{\parindent}{2}em` —— 单位跑到花括号外（f-string 括号错位），编译报 `Illegal unit of measure` | **真实编译** |
| 9 | Markdown `##` 被映射成 `\subsection`，而论文里 `##` 才该是顶层章节 | **真实编译产物检查** |
| 10 | **编译失败被误报为成功**：插图路径错误 → xelatex 中途报错 → 只输出前 2 页部分 PDF，而判据 `size > 0` 把它报成 `ok: True` | **看渲染结果** |
| 11 | **正文里的 Markdown 表格未转换** → 表格源码被当正文原样打印成 `\|符号\|含义\|` | **看渲染结果** |
| 12 | **图表中文全是方框** —— matplotlib 默认字体 DejaVu Sans 不含 CJK 字形 | **看渲染结果** |
| 13 | 图注直接用了文件路径 `figures/fig_scenarios.png` | **看渲染结果** |
| 14 | **CLI 沙箱拦截解释器执行**：`acceptEdits` 只自动批准**文件编辑**，不批准**命令执行**，导致求解类步骤反复试探 25 分钟仍无产物 | **真实流水线** |
| 15 | **asyncio 流读取上限 64 KiB**：agent 单行 JSON 超限 → `ValueError: chunk is longer than limit`，步骤直接中断 | **真实流水线** |
| 16 | **随包 MiKTeX 遮蔽系统 TeX**：工具目录一律前置 PATH，而随包的是**未初始化的 fresh install** | **真实流水线** |
| 17 | **模型名用了界面显示名**：`MiMo-V2.6-Pro` → `400 Unsupported model`；API 需要小写 ID `mimo-v2.6-pro[1M]` | **真实流水线** |
| 18 | **表题与表被拆开**：文末纯浮动体区块里 `[htbp]` 让标题落单、`[H]` 留出没有文字可填的空白 | **版面校验** |
| 19 | **结果表塞进全部 JSON 标量**（含 `meta.title`/`meta.python` 等内部字段），一张表撑爆两页，把表题挤到单独一页 | **版面校验** |
| 20 | **图注的强调符清理误删合法内容**：`X*`（最优值记号）被删成 `X` | **回归测试** |
| 21 | **SVG 被当插图 → 整份论文编译失败**：FigureSpec 同时产出 `X.png` 与 `X.svg`，**stem 相同**都被收作插图，而 `\includegraphics` 不支持 SVG（`Cannot determine size of graphic ... no BoundingBox`） | **端到端运行** |
| 22 | **同一份 spec 两个名字 → 重复 `\label`**：`architecture.spec.json` 与 `tikz_architecture.spec.json` **逐字节相同**（SHA256 一致） | **端到端运行** |
| 23 | **前向引用未解析（PDF 里出现 `??`）**：`\ref` 在前、`\label` 在后，**只编译一遍**解析不了 | **端到端运行** |
| 24 | **标题独占一页**：agent 把摘要写成**分节** → `doc.abstract` 为空 → 无条件 `\newpage` 让第 1 页只剩标题 | **版面校验** |
| 25 | **版面校验器自己漏报 `??`**：它查的是 `???`（三个问号），而 LaTeX 的未解析占位是 **`??`（两个）** | **自查发现** |

> 第 4~25 项**只有真实执行 / 真实编译 / 真实查看产物才会暴露**。
> 尤其第 10~13 项：**395 项测试全绿的情况下，看 4 张图 5 分钟就全找到了。**
> 第 14~17 项：**410 项测试全绿的情况下，跑一次真实流水线全暴露了。**
> 第 21~25 项：**1355 项测试全绿的情况下，跑一次端到端又暴露 5 个。**
>
> ⚠️ 第 25 项最值得警惕：**校验器自己也会错，而且它的错会让后续所有检查失真**——
> 修好它之后，它立刻抓出了第 23 项。校验链上任何一环失效，下游全部假绿。

### 7.2b 端到端回归测试（对应第 21~25 项）

新增 `tests/test_e2e_regressions.py`（21 项），每个用例都注明它对应哪个真实缺陷：

| 用例 | 关键断言 |
|---|---|
| `test_svg_not_includable` | 同 stem 只留一张且优先 png；**生成的 `.tex` 里无 `.svg`** |
| `test_duplicate_spec_dedup` | 内容相同的 spec 去重为 1 份；内容不同的全保留 |
| `test_forward_reference_needs_two_passes` | 默认 `runs=2`；两遍后无 `??`；**对照**：一遍确实留下 `??` |
| `test_no_title_only_page` | 有摘要保留 `\newpage`；**无摘要时标题后不断页** |
| `test_layout_verifier_catches_double_question` | **行为**：喂一份未解析引用的 PDF，校验器必须返回非 0 |

### 7.3 视觉校验（本轮新增的验证环节）

把生成的 PDF 渲染成图**实际看一遍**，是本轮最有价值的动作。

| 检查手段 | 发现不了 |
|---|---|
| 单元测试 | 渲染结果是否正确 |
| 编译返回码 | 内容是否被**静默截断** |
| 文件存在 + 尺寸 | 中文是否变成方框 |

因此新增：
- `render_paper_preview.py` —— 生成论文并渲染成页图，供直接查看
- `services/figure_style.py` —— 图表中文字体配置 + **缺字形自检**
  （`save_figure()` 用 `warnings` 捕获 `missing from font`，命中即抛错，
  **阻止"看起来成功、实际是方框"的图落盘**）

完整分析：[`../reports/22-visual-verification.md`](../reports/22-visual-verification.md)

### 7.4 真实闭环结果

`live_loop_check.py`：Claude Code + WebSocket + 检查点，全链路：

| 环节 | 结果 |
|---|---|
| 建工作流（启用检查点） | 8 步 |
| WS 连接 | ✅ 收到 `hello` 含 8 步快照 |
| 执行 `comp-prob-analysis` | POST → **202**（后台化），轮询至 `waiting_checkpoint` |
| 实时事件 | ✅ **26 条** WS 事件（tool 20 / progress 3 / started 2 / result 1） |
| 产物 | `PROBLEM_ANALYSIS.md` **6828 字节**（阈值 1500） |
| **检查点自动暂停** | 工作流 `paused`，`remaining_seconds=5400` |
| **人工批准** | → 工作流 `running`，步骤 `completed` |
| 事件回放（REST） | 26 条，全部可重放 |
| 僵尸 | 无 |

> 单步耗时 **227 秒**——这也印证了后台化的必要性：
> 若同步等待，客户端超时就会把它变成僵尸。

留档：[`../reports/20-live-loop.md`](../reports/20-live-loop.md)

### 7.5 真实成文链结果

`paper_chain_check.py`：仿真工作区 → 装配 → 导出 → 编译。

| 环节 | 结果 |
|---|---|
| TeX 运行时 | `ready`（复用系统 TeXLive；随包安装器可用性已检测） |
| 论文装配 | 6 章节 / **2 张程序化表** / 2 张图（含清单归类）/ 2 条参考文献 |
| **表格数值** | 逐字来自 `all_results.json`（`objective_value=1234.0` → `1234`） |
| 去 AI 味 | 抓到**故意植入**的 2 处违规：`**结论：**`（最高频痕迹）与「作为一个AI」 |
| **LaTeX** | ✅ `.tex` 4138 字节 → **`.pdf` 82392 字节 / 2 页** |
| **DOCX** | ✅ 38495 字节（2 表格 / 2 图 / 2 参考文献） |
| 页数预算 | advisory：上限 30，估算 0（正文偏短），未作门控 |

留档：[`../reports/21-typesetting-chain.md`](../reports/21-typesetting-chain.md)
