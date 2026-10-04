# 完整 8 步流水线：工程发现与缺陷记录

> 这是"跑完整 8 步国赛流水线"过程中的**工程侧产出**。
> 逐步结果见 [`23-full-pipeline.md`](23-full-pipeline.md)（由脚本自动生成）。

---

## 0. 一句话

**一条真实流水线暴露了 6 个 mock 永远测不出的缺陷。**
其中 3 个是致命阻塞（步骤直接跑不出产物），3 个是可靠性缺陷。

---

## 1. 六个缺陷

| # | 缺陷 | 症状 | 根因 | 修复 |
|---|---|---|---|---|
| 1 | **CLI 沙箱拦截解释器执行** | `comp-code` 反复试探 25 分钟仍无产物；agent 自述 *"The sandbox gates interpreter execution"* | `--permission-mode acceptEdits` **只自动批准文件编辑，不批准命令执行** | 求解类步骤改用 `bypassPermissions`（已对照实验确认） |
| 2 | **asyncio 流读取上限 64 KiB** | 步骤抛 `ValueError: Separator is found, but chunk is longer than limit` 直接中断 | `create_subprocess_exec` 默认 `limit=64KiB`，而 agent 单行 JSON 很容易超过 | 两个适配器都设 `limit=32MiB` |
| 3 | **随包 MiKTeX 遮蔽系统 TeX** | 第 8 步找不到可用的 `xelatex` | 工具环境把随包目录一律插到 PATH **最前**，而随包 MiKTeX 是**未初始化的 fresh install** | 随包工具改**追加**兜底；只有探测通过的 `xelatex` 才**前置** |
| 4 | `_advance_or_finish` 漏 `await` | 全部步骤完成后工作流仍停在 `running` | 协程未 await（由 `RuntimeWarning` 暴露） | 补 `await` |
| 5 | **模型名用了界面显示名** | 8 步全部秒失败：`API Error: 400 Unsupported model MiMo-V2.6-Pro` | 传的是 UI 标签，**API 需要小写 ID** `mimo-v2.6-pro[1M]` | 改用真实 ID，并做成 `MODEMON_MODEL_CHAIN` 可配置 |
| 6 | **静默超时过长（2700s）** | 卡住的步骤要等 45 分钟才被判超时，期间流水线完全停滞 | 静默上限不该长于"人能接受的无进展时间" | 收敛到 600s，让卡住能被及时发现并交给返修/重试 |

> 缺陷 1、2、3、5 都是"看起来能跑，实际跑不出东西"，**只有真实执行才会暴露**。

---

## 2. 补上的两项能力

### 2.1 模型链回退（按用户要求）

额度耗尽/过载时在两个模型间自动切换：

- **调用内切换**：Claude Code 的 `--fallback-model`（同一进程内自动降级，最省上下文）
- **调用间切换**：整条链都失败时，上层换下一个模型重试

```python
DEFAULT_MODEL_CHAIN = ("mimo-v2.6-pro[1M]", "mimo-v2.6-flash[1M]")  # 可用环境变量覆盖
RETRYABLE_CODES = {"QUOTA_OR_OVERLOAD", "MAX_BUDGET_USD", "NONZERO_EXIT"}
```

同时把 CLI 的 `result.subtype` 与 `api_error_status` 暴露为精确错误码——
原先一律报 `NONZERO_EXIT`，**"预算触顶"和"程序崩溃"分不开**。

### 2.2 修复循环（对齐蓝方设计）

**这是本轮最重要的能力补齐。** 原先质量门失败 → 步骤直接判死；
实测中 agent 会漏掉约定产物（如 `comp-code` 少写 `figures/all_results.json`），
一旦判死整条流水线就断了。

蓝方的 `recover_checked_step(max_repairs=3, max_local_rechecks=2, max_advisory_repairs=1)`
正是解决这个问题的。现已实现等价机制：门控失败 → 生成**针对性的返修指令**
（明确列出缺哪个文件、要求多少字节）→ 重跑，最多 3 轮。

---

## 3. 真实成本与耗时（实测，非估算）

**这是我此前估计错误的地方，必须更正。**

| 步骤 | 状态 | 耗时 | 花费 |
|---|---|---|---|
| 1 comp-prob-analysis | ✅ completed | 61s | $0.096 |
| 2 comp-modeling | ✅ completed | 126s | $0.196 |
| 3 comp-code | ✅ completed | 327s | $0.758 |
| 4 paper-figure | ✅ completed | 157s | $0.260 |
| 5 paper-figure-drawio | ❌ 静默超时 | 662s | — |
| 6 comp-review | ✅ completed | 682s | $0.709 |
| 7 comp-paper-zh | （见逐步报告） | — | — |
| 8 comp-compile-zh | （见逐步报告） | — | — |

**关键更正**：我最初估"单步 ~$0.03、全程 $0.5–2"，依据是一次 2338 token 的简单步骤。
真实流水线步骤是 **agentic 循环**，反复累积上下文，单步实测 **$0.1–0.8**，
**单次 CLI 调用的固定开销就有约 $0.10**（Claude Code 系统提示约 15K tokens）。

> 一次 `say OK` 的对话实测花费 **$0.10–0.12**——这就是固定开销的基线。

**时间**：前 7 步累计约 34 分钟。**这是比预算更真实的约束**——
若按比赛时间（数天）衡量完全够用，但单步动辄 5–11 分钟意味着
**"人不在场时的自动化"才是这个产品的真正价值**（正如蓝方宣传的
"让 AI 在你睡觉时做科研"）。

---

## 4. 一个仍然存在的问题：步骤 5 反复静默超时

`paper-figure-drawio` 两次都以 `INACTIVITY_TIMEOUT` 失败。
推测原因：该步骤要画 TikZ/DrawIO 架构图，需要 `draw.io` 或 TeX 图形链，
而这些工具的探测/调用可能很慢或不可用，agent 陷入长时间等待。

**待查**：这是"工具不可用"还是"agent 策略问题"。
按我的三态分类，它应当被归为 **`unavailable`（检查器/工具不可用）**，
而不是简单的失败——当前实现只记了 `INACTIVITY_TIMEOUT`，没有进一步区分。

---

## 5. 结论：mock 测试的边界在哪里

本轮 410 项单元/集成测试**全部通过**，但它们**一个都没能提前发现这 6 个缺陷**。原因很直接：

| 测试手段 | 能覆盖 | 覆盖不到 |
|---|---|---|
| 单元测试（Echo 替身） | 编排逻辑、门控、状态机 | **真实 CLI 的行为**：权限语义、输出规模、沙箱 |
| 契约测试 | 参数构造正确 | **参数是否真的被接受**（模型名、MCP 配置 schema） |
| 编译/运行成功 | 退出码 | **产物内容是否正确** |

**必须真跑一次**，且必须**看产物**（这已在上轮由视觉校验证明）。
本轮的 6 个缺陷全部来自真实执行；上轮的 4 个缺陷全部来自真实查看。
