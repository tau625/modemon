# 项目进度与决策记录

最后更新：2026-10-01

## 一句话状态

**离线端到端已跑通并通过测试**（9/9），真实模型运行待填入 API Key。

## 里程碑

| 里程碑 | 状态 | 验证方式 |
|---|---|---|
| M0 骨架：provider / Skill 引擎 / 状态机 / CLI | ✅ 完成 | `mma doctor`、`mma skills` 正常 |
| M1 对抗评审回路：执行 → 评审 → 修订 → 复评 | ✅ 完成 | 离线运行中评分 7.5（需改）→ 修订 → 9.2（通过） |
| M2 求解真实执行：代码抽取 → 沙箱运行 → 数值回流 | ✅ 完成 | `solve/main.py` 真实运行，`RESULT_JSON` 落盘（峰值 15.3641 @ 6.5h） |
| M3 图表 + 论文 + 编译 | ✅ 完成 | matplotlib 真实出图；`xelatex` 编译成功；**编译失败自动回修闭环已实现并测试**（坏论文 → 回修 → 出 PDF） |
| M3b 数值溯源门禁 | ✅ 完成 | `mma check` / 流水线末尾自动执行；实测准确标出 mock 大纲里编造的 "12.3"（真实值 15.3641） |
| M4 检查点 / 单步重跑 / 实时推送 | ✅ 完成 | ✅ WebSocket 实时事件推送（`mma serve` + 浏览器监控页）；✅ 人工检查点（`--checkpoint <环节>`，暂停后可「继续 / 重跑本环节 / 中止」，非交互环境自动跳过）；✅ 状态落盘与 `resume` 续跑 |
| M4b 赛题文件解析 | ✅ 完成 | `.txt/.md/.pdf/.docx` 统一读成纯文本（PDF 用 pypdf，Word 用 python-docx；扫描件给出明确提示） |
| M5 竞赛 Profile 与编译合规检查 | ✅ 完成 | Profile（页数/语言/必备章节）+ `mma check` 合规检查：必备章节、摘要、页数、图片文件存在性、图表引用、参考文献、**占位符残留** |

## 关键决策

1. **不基于上游闭源软件**。`N-allpass/modex-mh-agent` 仓库只有文档（无源码、无许可证），
   成品为闭源 Electron 应用。本工程只参考其**公开文档描述的架构**，代码全部原创。详见 `docs/CREDITS.md`。
2. **国赛排版自写**。`cumcmthesis` 官方仓库无许可证文件 → 不拷贝其 `.cls`；改用自写 `ctexart` preamble。
   美赛可用 `mcmthesis`（LPPL 1.3c，TeX Live 自带）。
3. **模型已切到小米 MiMo**（用户指定）：执行者 `mimo-v2.6-flash`、评审者 `mimo-v2.6-pro`，
   端点 `https://token-plan-cn.xiaomimimo.com/v1`（OpenAI 兼容，已实测 `/v1/models` 与 `json_object`）。
   两模型默认开启思考模式，**思考 token 计入 `max_tokens`**（实测 "收到" 两字用掉 9~17 个思考 token）。
   DeepSeek 旧名 `deepseek-chat` / `deepseek-reasoner` 已于 2026-07-24 停用，配置中不使用。
4. **数值唯一来源是真实执行**。所有脚本在 `runs/<id>/` 下真实运行，`RESULT_JSON` 单行汇总被
   解析后注入下游上下文；论文里的数字只能取自这里。
5. **工作目录约定**：生成脚本的相对路径以**运行根目录**为基准（`results/`、`figures/`、`paper/` 都在其下）。
6. **产物全留痕**：每轮的提示词（`prompts/`）、模型原始回复（`logs/`）、评审 JSON、执行日志、评分曲线全部落盘。

## 性能实测（小米 MiMo，2026-10-01）

思考模式是**耗时主因**，实测数据：

| 调用 | 耗时 | 输出 tokens | 其中思考 |
|---|---|---|---|
| 执行者 · 赛题解析（第 0 轮） | 289.4s | 12,082 | 绝大部分 |
| 评审者 · 赛题解析（第 1 轮） | 332.2s | 12,377 | 绝大部分 |
| 执行者 · 赛题解析（修订 1） | 193.7s | 13,227 | 绝大部分 |
| 执行者 · 连通测试（关闭思考） | 2.1s | 5 | 0 |

**结论**：单环节约 5~9 分钟，6 个环节整跑约 40~70 分钟。控制手段（已实现）：

1. `extra_body={"thinking":{"type":"disabled"}}` 是**唯一真正生效**的关闭方式；
   `reasoning_effort="low"` 与顶层 `enable_thinking=False` 均无效（实测对比见 `scripts/probe_thinking.py`）。
2. 命令行：`mma run ... --thinking off`（全局关闭）或 `--thinking on`（强制开启）。
3. 配置：`configs/pipeline.yaml` 支持**按环节**设置，例如 `figures` 已设为 `thinking: "off"`
   （纯绘图任务，无质量损失）；也可在 `configs/default.yaml` 的模型级设置。
4. 注意 YAML 1.1 会把 `off` 解析成布尔值，配置里请写成 `"off"`；代码侧已做布尔归一化兼容。

## 稳健性（真实故障驱动，2026-10-01）

| 故障 | 现象 | 处理 |
|---|---|---|
| 思考吃光输出预算 | 评审模型 `reasoning_content` 4.4 万字符、正文为空 → 抛错炸掉整条长跑 | provider 自动关思考重试；评审失败不中断；环节失败可 `resume` |
| 门禁自证 | `provenance_check.json` 被自己当作证据，匹配率虚高到 100% | 排除门禁自身产物，修后为诚实的 50% |
| 成本重复计价 | 缓存命中的输入 token 又被按未命中计价（$10.01 vs $0.01） | 计算 `miss = prompt_tokens - cache_hit` |
| YAML 布尔陷阱 | `thinking: off` 被解析成 `False` 导致配置校验失败 | 配置加引号 + 代码侧布尔归一化 |
| 评审无跨轮记忆 | 每轮重新挑一批新问题，分数永不收敛 | 评审提示词注入上一轮必改项并要求先核对 |
| 求解前按"数值无出处"扣分 | 该阶段尚无运行结果，被系统性误伤 | 数值口径分阶段（求解前/求解后） |

## 目录结构

```
configs/       default.yaml（模型与服务商）· pipeline.yaml（流水线）· competitions/（竞赛 Profile）
skills/        7 个 SKILL.md：赛题解析/建模设计/求解实现/图表/论文大纲/论文成文/对抗评审
src/modemon/       config · providers · skills · execution · review · workflow · artifacts · events · cli
runs/          运行产物（含 report.json 状态、prompts、logs、results、figures、paper）
tests/         9 项回归测试
docs/          CREDITS.md（许可证合规）· PROGRESS.md（本文件）
```

## 常用命令

```powershell
cd E:\Projects\Modemon
$py = .venv\Scripts\python.exe

& $py -m modemon doctor                                  # 环境自检
& $py -m modemon skills                                  # 列出 Skill
& $py -m modemon run -p examples\problem.txt --provider mock   # 离线跑通（不花钱）
& $py -m modemon run -p examples\problem.txt --competition cumcm   # 真实调用
& $py -m modemon runs                                    # 历史运行
& $py -m modemon show <run_id>                           # 查看评审轨迹与产物
& $py -m modemon resume <run_id>                         # 断点续跑
& $py -m pytest -q                                   # 回归测试
```

## 下一步（按优先级）

1. **真实运行收尾**：等 `real-example-01` 跑完 → `mma compile --repair` → `mma check` → 人工看论文质量。
2. **检查点与实时推送**：关键决策点暂停等待人工确认；FastAPI + WebSocket 推送进度。
3. **赛题文件解析**：支持 PDF / Word 赛题上传自动转文本。
4. **合规检查**：页数、字数、必备章节、图表编号、参考文献完整性。
5. **评审校准**：实测评审偏严（8.2 → 8.1 仍未过 8.5 线），需要按环节调整权重与通过线，
   或引入"评审分歧度"信号；也可让评审者换用另一家模型做交叉验证。

## 已知限制

- 赛题输入目前仅支持纯文本（`.txt` / `.md`）。
- 修订轮次会覆盖同名产物文件，不保留上一轮版本（可后续改为按轮次存档）。
- 评审者默认与执行者同厂商（DeepSeek 两代模型）；换成 ModelScope / 硅基流动的免费模型即可实现真·跨厂商对抗。
- 生成的论文**必须人工复核**，数据、引用与结论请自行核实。
