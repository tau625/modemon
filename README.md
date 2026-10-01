# Modemon · 模灵

**一个替你跑数模的守护进程** —— 从赛题到竞赛级论文全自动；评审对抗、编译自修、数字必须有出处。

面向**数学建模竞赛**（国赛 CUMCM / 美赛 MCM-ICM）与科研写作流程的**自研**智能体框架。

> ⚠️ 本工程为**从零原创实现**。架构思路参考公开文档（如 Modex · MH Agent 的公开说明），
> 但**不包含、不复制任何闭源产品的代码、Skill 文案、界面或品牌资源**。
> 所有可复用素材均来自各自持有开源许可证的项目（见 `docs/CREDITS.md`）。

## 核心设计

1. **跨模型对抗评审** —— 执行者产出，评审者挑错，两个角色可绑定**不同厂商**的模型，避免单模型自我博弈的系统性盲区。
2. **Skill 即 Markdown** —— 每个能力是 `skills/<name>/SKILL.md`：YAML front-matter 声明元信息，正文即提示词模板。可自由增删、混搭、串联。
3. **数值必须来自真实执行** —— 论文里的每个数字都必须由沙箱里**真实运行的 Python** 产生并落盘，
   禁止模型口头编造数据。这是本工程可信度的底线。
4. **工作流可中断可恢复** —— 状态落盘为 `runs/<run_id>/report.json`，支持单步重跑、断点续跑、关键检查点人工确认。
5. **产物全留痕** —— 每轮的提示词、模型原始回复、评分曲线、执行日志、生成代码全部留档，便于复现与调优。

## 流水线

```
赛题解析 → 建模设计 → 求解实现(真实运行) → 图表生成 → 论文大纲 → 论文成文 → 编译合规检查
   ↑____________对抗评审回路（打分 / 问题清单 / 必改项 / 评分曲线）____________↓
```

## 快速开始

```powershell
# 1. 依赖（已用 uv 建好 .venv）
uv pip install --python .venv\Scripts\python.exe -e ".[dev,solve]"

# 2. 配置 Key
copy .env.example .env    # 然后填入 XIAOMI_API_KEY

# 3. 连通自检（用本项目自己的 provider 层各发一次最小请求）
.venv\Scripts\python.exe scripts\probe_api.py

# 4. 自检
.venv\Scripts\modemon.exe doctor

# 5. 离线跑通全流程（不消耗额度，验证管道）
.venv\Scripts\modemon.exe run --problem examples/problem.txt --provider mock

# 6. 真实运行
.venv\Scripts\modemon.exe run --problem examples/problem.txt --competition cumcm

# 7. 关键环节人工把关（可选）：在建模设计完成后暂停，可确认 / 重跑 / 中止
.venv\Scripts\modemon.exe run -p examples/problem.txt --checkpoint modeling_design --checkpoint paper_writing

# 8. 看实时进度（浏览器打开 http://127.0.0.1:8765）
.venv\Scripts\modemon.exe serve
```

> 赛题支持 `.txt / .md / .pdf / .docx`；PDF 需要文本层（扫描件请先 OCR）。

## 当前模型配置

| 角色 | 服务商 | 模型 | 说明 |
|---|---|---|---|
| 执行者 | 小米 MiMo | `mimo-v2.6-flash` | 建模、写代码、写论文 |
| 评审者 | 小米 MiMo | `mimo-v2.6-pro` | 独立挑错、打分、给必改项 |

- 端点：`https://token-plan-cn.xiaomimimo.com/v1`（OpenAI 兼容；另有 `/anthropic` 格式端点）
- 密钥只放 `.env` 的 `XIAOMI_API_KEY`，**不写入任何配置或产物**
- 两个模型默认开启思考模式，**思考 token 计入 `max_tokens` 预算**，配置里已留足额度
- 想换真·跨厂商对抗：改 `configs/default.yaml` 的 `models.reviewer.provider`（已预置 deepseek / modelscope / siliconflow 端点）

## 命令

| 命令 | 说明 |
|---|---|
| `mma doctor` | 检查 Python / LaTeX / API Key / 依赖 |
| `scripts/probe_api.py` | 模型连通自检（不打印密钥） |
| `mma skills` | 列出所有 Skill 及其元信息 |
| `mma run` | 执行一次完整流水线 |
| `mma runs` | 列出历史运行 |
| `mma show <run_id>` | 查看产物与评分曲线 |
| `mma resume <run_id>` | 从上次中断处续跑 |
| `mma rerun <run_id> <环节>` | 只重跑某个环节（调完 Skill 后几分钟验证效果） |
| `mma compile <run_id> [--repair]` | 编译论文；`--repair` 时失败自动回修 |
| `mma check <run_id>` | 数值溯源 + 竞赛合规双门禁（`--min-ratio` 可设拦截线） |
| `mma report <run_id>` | 生成 Markdown 复盘报告（环节轨迹 / 门禁结论 / 产物清单） |
| `mma serve` | 启动进度监控服务（WebSocket 实时推送事件流） |

## 文档

- [实操手册](docs/GUIDE.md) —— 从拿到赛题到验收 PDF 的完整流程、真实耗时用量、迭代方法、故障排查
- [架构说明](docs/ARCHITECTURE.md) —— 模块职责、数据流、扩展点、被真实运行验证过的坑
- [项目进度](docs/PROGRESS.md) —— 里程碑、性能实测、下一步
- [素材来源与许可证](docs/CREDITS.md) —— 哪些开源素材可用、哪些不能用及依据

## 目录

```
configs/          运行配置、流水线定义、竞赛 Profile
skills/           每个能力一个 SKILL.md
src/modemon/          核心实现（provider / skill 引擎 / 工作流 / 评审 / 执行沙箱）
runs/             运行产物（已 gitignore）
docs/             设计文档与素材来源说明
```

## 合规与学术诚信

- 本工具是**辅助工具**，生成内容必须人工复核；论文数据、引用、结论在使用前请自行核实。
- 参加竞赛、投稿论文请遵守相应的学术诚信规范与参赛规则，**最终责任在使用者本人**。
- 上游闭源软件仅作为**架构思路参照**，未使用其任何代码或文案资源。
