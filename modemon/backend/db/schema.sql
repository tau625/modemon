-- modemon 数据模型
--
-- 结构参照对 Modex-MH-Agent 恢复的数据模型（11 张表，见 reports/01-backend-api-and-data.md），
-- 注释为本项目自行撰写，用于记录**每条约束背后的失败模式**。
--
-- 设计原则
-- --------
-- 1. 两套执行体系**物理隔离**：经典工作流（步骤顺序固定）与对话工作台（自由顺序）。
--    二者若混用同一张步骤表，健康检查会张冠李戴。
-- 2. 所有人工确认闸**必须落库**，不能只靠前端隐藏按钮。
-- 3. 所有跨进程可见的状态**必须落库**，WebSocket 只作通知。
-- 4. 原始模型流、密钥、Skill 正文、私有路径**永不入库**。

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ===========================================================================
-- 一、经典工作流（步骤顺序与模板强绑定）
-- ===========================================================================

CREATE TABLE IF NOT EXISTS workflows (
    id                 TEXT PRIMARY KEY,
    -- 竞赛/学术模板：comp_cumcm | comp_huawei | comp_mcm | ... | course_paper
    template           TEXT NOT NULL,
    title              TEXT NOT NULL,
    params             TEXT NOT NULL DEFAULT '{}',
    status             TEXT NOT NULL DEFAULT 'pending',
                       -- pending | running | paused | completed | failed
    current_step       TEXT,
    workspace_dir      TEXT,
    -- 0=连续执行 1=每步完成后暂停确认
    enable_checkpoints INTEGER NOT NULL DEFAULT 0,

    -- 自动恢复护栏必须跨重启持久化。
    -- 放在内存字典里的后果：后端崩溃重启后计数归零，于是一次崩溃引发无限自动重跑。
    -- 人工 start/resume/restart/rerun 会清零该计数；心跳与启动恢复只递增。
    auto_resume_count  INTEGER NOT NULL DEFAULT 0,
    auto_resume_last_at TIMESTAMP,

    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS workflow_steps (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id     TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    skill_name      TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    -- 与模板 sub_steps 的索引强绑定。因此**不允许**按自由对话顺序插入新行，
    -- 否则 step_order 与模板错位，expected_outputs 会张冠李戴。
    step_order      INTEGER NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
                    -- pending | running | waiting_checkpoint | completed | failed | skipped
    has_checkpoint  INTEGER NOT NULL DEFAULT 0,
    checkpoint_type TEXT,
    output_files    TEXT NOT NULL DEFAULT '[]',
    started_at      TIMESTAMP,
    completed_at    TIMESTAMP,
    error_message   TEXT,
    -- 该步实际生效的模型快照。预设后来被删改也不影响历史回看。
    model_used      TEXT,
    -- 仅本步骤的 CLI 会话 id；与主会话 session 是两个不同的东西，
    -- 混用会导致续接错对象。换 skill 时不续接。
    resume_session_id TEXT,
    resume_error_code TEXT,
    resume_strategy   TEXT       -- NULL | same_session | fresh_context
);
CREATE INDEX IF NOT EXISTS idx_steps_wf ON workflow_steps(workflow_id, step_order);

CREATE TABLE IF NOT EXISTS workflow_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    step_name   TEXT,
    level       TEXT NOT NULL DEFAULT 'info',   -- info | warn | error | progress
    message     TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_logs_wf ON workflow_logs(workflow_id, id);

CREATE TABLE IF NOT EXISTS checkpoints (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id     TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    step_name       TEXT NOT NULL,
    -- approve | idea_select | feedback | assets_resolve
    checkpoint_type TEXT NOT NULL,
    data            TEXT NOT NULL DEFAULT '{}',
    response        TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending | resolved
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at     TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ckpt_wf ON checkpoints(workflow_id, status);

-- ===========================================================================
-- 二、对话工作台（自由顺序，与 workflow_steps 完全隔离）
-- ===========================================================================

CREATE TABLE IF NOT EXISTS chat_sessions (
    id              TEXT PRIMARY KEY,
    workflow_id     TEXT NOT NULL,
    -- 主会话的 CLI session_id。进程被回收或崩溃后靠它 --resume 重建，
    -- 用户无需重新描述需求、上下文不丢。
    cli_session_id  TEXT,
    -- 当前轮次的约束。MCP 是独立进程，无法共享进程内 ContextVar，
    -- 因此必须落库，才能在回调时由后端硬性保证「仅对话不执行 / 聚焦任务不扩成完整步骤」。
    -- 一轮结束立即清空，不作跨轮状态。
    active_turn_mode   TEXT,
    active_focus_target TEXT,
    active_turn_id     TEXT,
    -- 客户端按 SDK 返回的每轮成本累加所得，**不是权威账单**。
    cost_usd           REAL NOT NULL DEFAULT 0,
    cost_report_count  INTEGER NOT NULL DEFAULT 0,
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_wf ON chat_sessions(workflow_id);

CREATE TABLE IF NOT EXISTS chat_messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL,
    role         TEXT NOT NULL,                 -- user | assistant | system

    -- 用户原话，唯一真相源。与整理后的 instruction 分开存，
    -- 才谈得上「冲突时以原话为准」；混成一列就无法区分优先级。
    content      TEXT NOT NULL,
    intent       TEXT,                          -- call_skill | chat | edit_file
    skill_name   TEXT,
    instruction  TEXT,                          -- 后端整理出的执行要点（参考值）

    -- 提议生成时上游产物的指纹。用户看卡片期间上游可能已被改动，
    -- 确认时比对可发现「卡片上写的基于 X@v1」已不成立。
    dep_fingerprint TEXT,
    -- NULL = 仍停在提议卡片未确认。执行前必须校验非空——
    -- **不能只靠前端隐藏按钮**：双击、网络重发、直接调接口都能绕过前端。
    confirmed_at    TIMESTAMP,
    -- 用户明确接受「缺少软依赖仍继续」。仅授权这一次执行；
    -- 硬依赖无论如何都必须继续拦截。
    force_confirmed INTEGER NOT NULL DEFAULT 0,

    status       TEXT NOT NULL DEFAULT 'done',
                 -- proposed | queued | running | done | failed | cancelled | interrupted
    error_message TEXT,

    -- 仅影响呈现的向后兼容语义，**不参与授权判断**。
    item_kind    TEXT,                          -- user_message | assistant_message | task | notice
    message_phase TEXT,                         -- commentary | final_answer

    -- 前端生成的幂等 turn id。响应丢失后重试时，
    -- 不能把同一句话再喂给长期主会话一次，否则提议与上下文都会重复。
    client_turn_id TEXT,
    turn_id        TEXT,

    -- 允许用户编辑提议。确认时带 revision 做 CAS，
    -- 防止「保存编辑」与「确认执行」并发导致跑了旧指令。
    proposal_revision INTEGER NOT NULL DEFAULT 1,
    state_revision    INTEGER NOT NULL DEFAULT 0,

    -- 每张执行卡片的不可变快照。工作流设置后续变化，
    -- 也不能让已排队的任务悄悄换模型、换强度或从「只做第一问」扩成完整步骤。
    execution_scope TEXT NOT NULL DEFAULT 'full',   -- full | focused
    focus_target    TEXT,
    operation_kind  TEXT NOT NULL DEFAULT 'run_step',
                    -- run_step | focused_run | research | patch | validate
    source_skill    TEXT,
    model_preset_id TEXT,
    effort          TEXT,
    model_used      TEXT,

    -- 提议卡片的派生信息也落库：WebSocket 只是通知，
    -- 断线或重启后仍应能完整还原卡片。
    outputs_json      TEXT NOT NULL DEFAULT '[]',
    missing_deps_json TEXT NOT NULL DEFAULT '[]',
    quality_json      TEXT NOT NULL DEFAULT '{}',

    -- 长日志不入库，只存短摘要与实际文件差异；完整流式日志仍只在内存，
    -- 避免数据库无限膨胀，同时刷新页面后不再看起来像卡死。
    progress_phase   TEXT,
    progress_message TEXT,
    result_summary   TEXT,
    result_outputs_json TEXT NOT NULL DEFAULT '[]',

    tokens_in    INTEGER,
    tokens_out   INTEGER,
    started_at   TIMESTAMP,
    last_progress_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_chat_msgs_session ON chat_messages(session_id, id);
CREATE INDEX IF NOT EXISTS idx_chat_msgs_status ON chat_messages(status);
-- 注意：唯一索引 idx_chat_msgs_client_turn 不在建表处创建。
-- CREATE TABLE IF NOT EXISTS 不会给**旧库**补列，老库执行到会先报
-- 「no such column」，导致其后的 ALTER TABLE 迁移永远没机会运行。
-- 该索引在逐列迁移完成后幂等创建（见 services/state_store.py）。

-- 结构化、脱敏、可验证的生命周期事件。
-- 原始模型流、命令行、Skill 正文、密钥与私有路径**永不进入该表**。
CREATE TABLE IF NOT EXISTS chat_run_events (
    event_id       TEXT PRIMARY KEY,
    workflow_id    TEXT NOT NULL,
    message_id     INTEGER NOT NULL,
    run_id         TEXT NOT NULL,
    sequence       INTEGER NOT NULL,
    kind           TEXT NOT NULL,
    state          TEXT NOT NULL,
    title          TEXT NOT NULL,
    safe_detail    TEXT NOT NULL DEFAULT '',
    public_artifact_path TEXT,
    started_at     TIMESTAMP NOT NULL,
    completed_at   TIMESTAMP,
    evidence_json  TEXT NOT NULL DEFAULT '{}',
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(message_id, run_id, sequence)
);
CREATE INDEX IF NOT EXISTS idx_run_events_msg ON chat_run_events(message_id, sequence);

-- 受保护任务完成后的「待同步事件」。
-- 不把几十分钟日志塞回主会话上下文，只在用户下次发言前注入一次短摘要；
-- 注入成功后才标记 consumed。
CREATE TABLE IF NOT EXISTS chat_context_events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        TEXT NOT NULL,
    workflow_id       TEXT NOT NULL,
    source_message_id INTEGER NOT NULL UNIQUE,
    event_type        TEXT NOT NULL,
    payload           TEXT NOT NULL,
    consumed_at       TIMESTAMP,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ctx_pending ON chat_context_events(session_id, consumed_at, id);

-- 对既有产物的**显式**验收。
-- 绝不从聚焦任务的回执数量推断验收结果——那会把「跑了 3 次」当成「已验收」。
CREATE TABLE IF NOT EXISTS chat_stage_receipts (
    workflow_id  TEXT NOT NULL,
    skill_name   TEXT NOT NULL,
    snapshot     TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    accepted_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workflow_id, skill_name)
);

-- ===========================================================================
-- 三、配置
-- ===========================================================================

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 模型预设 = { 名称 + 模型 id + API Key + 厂商 }。
-- **不存 base_url**：请求地址统一由签名下发的客户端配置决定，
-- 不由厂商或预设改写，避免「模型与 key 串用」。
CREATE TABLE IF NOT EXISTS model_presets (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    model_id    TEXT NOT NULL,
    api_key     TEXT NOT NULL DEFAULT '',
    provider_id TEXT NOT NULL DEFAULT '',
    context_mode TEXT,                 -- auto | 200k | 1m
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ===========================================================================
-- 四、国赛 AI 使用记录（强制申报）
-- ===========================================================================
-- 国赛自 2024 年起要求申报 AI 使用情况。蓝方将其做成**产品级强制流程**
-- （模板 comp_cumcm 命中时必须填写 1–5 条真实记录并完成参赛队核验）。
-- 这里显式建表，而不是塞进 settings 的 JSON 里，以便审计与导出。

CREATE TABLE IF NOT EXISTS ai_disclosures (
    workflow_id      TEXT PRIMARY KEY REFERENCES workflows(id) ON DELETE CASCADE,
    records_json     TEXT NOT NULL DEFAULT '[]',
    verified_by_team INTEGER NOT NULL DEFAULT 0,
    verified_by      TEXT,
    verified_at      TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
