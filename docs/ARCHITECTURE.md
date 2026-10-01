# 架构说明

面向"读懂 + 改造"：本文说明这套智能体怎么跑起来、每个模块负责什么、想加功能该动哪里。

## 一、三条铁律

设计上所有取舍都服从这三条：

1. **数值只能来自真实执行。** 模型产出代码 → 沙箱真实运行 → 解析 `RESULT_JSON` → 才允许进入下游上下文。
   论文里出现的每个数字都必须能在 `results/` 找到出处，由 `provenance` 模块强制核对。
2. **产出必须被人看懂、被人复核。** 每轮的提示词、模型原始回复、评审 JSON、执行日志、评分轨迹全部落盘到
   `runs/<run_id>/`，任何结论都能追溯到证据。
3. **质量门禁由程序判定，不由模型自评。** 是否达标由引擎按"总分 ≥ 通过线 且 无高严重度问题"裁定
   （`review.is_passing`），模型只能给建议。

## 二、数据流

```
                  ┌──────────────────────────────────────────────┐
赛题(.txt/.md/    │  ingest.load_problem_text                    │
 .pdf/.docx) ───▶ └──────────────────────────────────────────────┘
                                │
                                ▼
        ┌───────────────────────────────────────────────────────┐
        │  workflow.Engine                                       │
        │                                                        │
        │   for stage in pipeline.yaml:                          │
        │     ┌─ skills.load_skill(stage.skill) ─┐               │
        │     │  渲染 Jinja2 提示词模板            │               │
        │     └───────────────┬──────────────────┘               │
        │                     ▼                                  │
        │        providers.executor (mimo-v2.6-flash)            │
        │                     │                                  │
        │        ┌────────────┴────────────┐                     │
        │        │ kind=text → 写 Markdown │                     │
        │        │ kind=code → 抽文件+真实运行│  execution         │
        │        └────────────┬────────────┘                     │
        │                     ▼                                  │
        │        对抗评审回路（最多 N 轮）                          │
        │          review 解析 JSON → is_passing? ──否──▶ 修订     │
        │                     │是                                │
        │                     ▼                                  │
        │         state 落盘 report.json（可断点续跑）              │
        └───────────────────────────────────────────────────────┘
                                │
                                ▼
        ┌───────────────────────────────────────────────────────┐
        │  收尾门禁（三步串行）                                    │
        │   1. latex.compile_tex      → 失败则把报错回灌自动回修    │
        │   2. provenance.check       → 数字能否溯源               │
        │   3. compliance.check       → 页数/章节/图表/占位符       │
        │   4. report.write_report    → 生成 REPORT.md 复盘        │
        └───────────────────────────────────────────────────────┘
```

## 三、模块职责

| 模块 | 职责 | 关键点 |
|---|---|---|
| `config.py` | 三层配置合并：`default.yaml` + `pipeline.yaml` + `competitions/*.yaml`，再叠加 CLI 与环境变量 | 密钥只从 `.env` 读，绝不进配置 |
| `ingest.py` | 赛题文件 → 纯文本 | PDF 走 pypdf、Word 走 python-docx；扫描件明确报错 |
| `providers.py` | OpenAI 兼容客户端 + 离线 Mock | 一个角色绑一个模型；服务端不认的参数自动剔除后重试；思考模式开关 |
| `skills.py` | `SKILL.md` 的 front-matter 解析 + Jinja2 渲染 | 加能力 = 加一个 Markdown 文件，不用改代码 |
| `execution.py` | 抽取代码块 → 按 `# file:` 落盘 → 真实运行 → 解析 `RESULT_JSON` | 路径穿越防护；入口脚本优先执行；日志全留 |
| `review.py` | 评审 JSON 解析（容错）、加权总分、必改项渲染、通过判定 | 分阶段数值口径；跨轮记忆；判定权在引擎 |
| `workflow.py` | 状态机：串环节、跑回路、检查点、落盘、收尾门禁 | `report.json` 即状态，支持 `resume` |
| `latex.py` | 编译与报错定位 | 编译前删旧 PDF，避免把上次的 PDF 误判为成功 |
| `provenance.py` | 论文数字 ↔ 真实结果的交叉核对 | 剔除排版参数；门禁自身产物不得作为证据 |
| `compliance.py` | 竞赛硬性要求检查 | 页数、必备章节、图片存在性、占位符残留 |
| `report.py` | 生成复盘 Markdown | 人读的入口 |
| `web.py` | FastAPI + WebSocket 实时事件推送 | 只读 `report.json` 与 `events.jsonl`，无额外状态 |
| `events.py` | 事件总线：打屏 + JSONL + 订阅 | WebSocket 与日志共用同一事件流 |

## 四、一次运行的生命周期

```
mma run -p 赛题.pdf --checkpoint modeling_design
  │
  ├─ load_config()                  读三层配置、注入 .env 密钥
  ├─ ingest.load_problem_text()     赛题 → 文本
  ├─ RunDir(runs/<时间戳>-<slug>/)  建目录骨架
  ├─ Engine.run_pipeline()
  │    ├─ 写 artifacts/00_problem.md
  │    ├─ 逐环节：渲染提示词 → 执行者 → 落盘 → 真实运行（如需）→ 对抗评审
  │    │          每环节末尾保存 report.json（可中断、可续跑）
  │    ├─ 检查点环节：暂停等待 c/r/q
  │    ├─ latex.compile_tex()       编译，失败则回修（≤ max_compile_rounds）
  │    ├─ provenance.check()        数值溯源
  │    ├─ compliance.check()        合规
  │    └─ report.write_report()     生成 REPORT.md
  └─ 汇总表 + 用量
```

## 五、产物约定

```
runs/<run_id>/
├── report.json          运行状态（唯一事实来源，resume 依赖它）
├── REPORT.md            复盘报告（人读）
├── artifacts/           00_problem.md、01_problem_analysis.md、02_modeling_design.md …
├── prompts/             每轮实际发给模型的完整提示词
├── logs/                模型原始回复（含评审 JSON）
├── solve/ figures/ appendix/   模型生成的代码（路径由 `# file:` 标记决定）
├── results/             真实运行结果（RESULT_JSON、csv、执行日志、门禁报告）
├── paper/               论文 .tex 与编译出的 .pdf
└── experiments/         专项验证产物（如评审记忆对照实验）
```

生成代码的**工作目录是运行根目录**，所以 `results/`、`figures/` 都是相对它而言。

## 六、扩展点

| 想做的事 | 怎么做 |
|---|---|
| 加一个能力环节 | 新建 `skills/<名字>/SKILL.md`，在 `configs/pipeline.yaml` 加一段（指定 `skill`、`kind`、`review`、`execute`） |
| 改某个环节的产出标准 | 直接改对应 `SKILL.md` 的正文——它就是提示词 |
| 加一门竞赛 | 在 `configs/competitions/` 加一个 yaml（页数、语言、必备章节），`--competition <id>` 即可 |
| 换模型 / 真·跨厂商对抗 | 改 `configs/default.yaml` 的 `models.*.provider` 与 `model`；端点在 `providers` 段预置 |
| 调评审严格度 | `run.pass_score`（通过线）、`run.require_no_blockers`（有高严重度问题是否一票否决） |
| 省钱提速 | `--thinking off` 全局关思考，或在 `pipeline.yaml` 按环节设 `thinking: "off"` |
| 换成别的产物形态 | `kind: code` 的环节按 `# file:` 落盘任意文件类型（我们已用于 .tex 与 .py） |
| 接 Web UI | `mma serve` 已提供 `/api/runs`、`/api/runs/{id}`、`/ws/runs/{id}`，前端可自由重写 |

## 七、被真实运行验证过的坑（改代码前值得读）

1. **`thinking: off` 在 YAML 里会被解析成布尔 `False`。** 配置里必须写 `"off"`；代码侧已做布尔归一化。
2. **思考 token 计入 `max_tokens`。** 给思考型模型留足额度，否则正文会被思考吃光。
3. **`reasoning_effort=low` 与顶层 `enable_thinking=False` 对小米 MiMo 无效**，
   真正生效的是 `extra_body={"thinking":{"type":"disabled"}}`（见 `scripts/probe_thinking.py`）。
4. **评审若没有跨轮记忆，就会每轮重新挑一批新问题，分数永远不收敛。**
   因此评审提示词会带上上一轮的必改项并要求先核对（见 `scripts/verify_reviewer_memory.py` 的对照实验）。
5. **求解执行之前的环节不该按"数值必须有运行结果出处"扣分**——那时根本还没有运行结果。
6. **门禁产物不能作为自己的证据**，否则数字能自证（`provenance` 已排除）。
7. **编译前必须删掉旧 PDF**，否则编译失败时会把上一次的 PDF 当成本次成功。
8. **思考型模型可能"只有思考、没有正文"。** 实测发生过：评审模型思考 4.4 万字符，把 `max_tokens`
   预算全部吃光，`content` 为空——若不处理会直接抛错并**炸掉整条一小时的长跑**。现在有三层防护：
   ① `providers` 检测到该情形自动关闭思考重试一次；② 单个环节评审失败只标记 `review_failed`，不中断流水线；
   ③ 任一环节抛异常时保存进度并提示 `mma resume`。另外评审者的 `max_tokens` 已提到 32000。
9. **成本估算别漏算缓存。** 命中缓存的输入 token 必须从"未命中"里扣掉，否则会重复计价
   （曾经的 bug：命中 100 万 token 被算成 $10.01，实际 $0.01）。

## 八、已知限制

- 修订轮次会覆盖同名产物，不保留上一轮版本（可按轮次归档改进）。
- 论文目前由单个环节一次性产出，未做分章节生成；长论文可改为逐章生成 + 局部评审。
- 参考文献是模型手工列出的 `thebibliography`，**没有做真实检索**，存在编造风险，必须人工核对。
- 检查点只支持命令行交互；Web 端的人工确认尚未实现。
