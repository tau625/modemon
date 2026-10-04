# 数模竞赛流水线实现蓝图

> 用途：**modemon 可直接照着实现**的竞赛工作流规格。
> 来源：`services.workflow_engine` 的内省 + 纯访问器求值（**真实数据，非推测**）
> 证据：`12-backend-spec.json` · `14-workflow-engine-spec.md` · `15-workflow-engine-probe.md` · `16-workflow-engine-config.md`

---

## 0. 这份蓝图是怎么来的

三层递进，每层都是**实测**而非推断：

| 层 | 手段 | 得到什么 |
|---|---|---|
| 1 | 符号表提取 | 116 个函数名 |
| 2 | 模块内省 | 116 个**带类型标注的签名** + 9 个类 + 89 条 docstring |
| 3 | **纯访问器求值** | **真实数据**——步骤定义、阈值、超时、页码规则 |

第 3 层是关键：`_comp_zh_steps(first_skill='comp-prob-analysis', paper_skill='comp-paper-zh')`
的**默认参数可见**，因此等价零参可调；而 `StepDef` 是 `dataclass`，
返回的对象可直接读出全部字段。**67/67 次访问器调用成功。**

> **边界声明**：函数体实现（门控算法本身）仍不可恢复。
> 本蓝图给出的是**契约与数据**，算法需自行实现。

---

## 1. 核心数据结构（已完整恢复）

```python
@dataclass
class StepDef:
    skill_name:     str                 # 技能标识，如 'comp-modeling'
    display_name:   str                 # 展示名（中文/英文两套）
    output_files:   List[str]           # 声明产出
    primary_output: Optional[str] = None   # 主产物（用于健康检查）
    has_checkpoint: bool = False        # 是否有检查点
    checkpoint_type: Optional[str] = None  # approve | feedback | ...

@dataclass
class TemplateDef:
    pipeline_skill: str                 # 流水线技能名
    display_name:   str
    sub_steps:      List[StepDef]       # 步骤序列
```

> 【直接提取】`[证据: 12-backend-spec.json → services.workflow_engine.classes]`

**关键设计**：`TemplateDef.sub_steps` 是**步骤的唯一真相源**，
创建工作流与运行时都用它，以确保「模板的 sub_steps」与「数据库中的 step list」一致
（docstring 原文：*确保 tmpl.sub_steps 与数据库中的 step list 完全一致*）。

---

## 2. ★ 国赛流水线（中文，`_comp_zh_steps()` 实测返回）

| # | `skill_name` | 展示名 | 声明产出 | 主产物 | 检查点 | 主产物最小字节 | 静默超时 |
|---|---|---|---|---|---|---|---|
| 1 | `comp-prob-analysis` | **赛题分析** | `PROBLEM_ANALYSIS.md` | 同左 | **approve** | 1,500 | 5400 s |
| 2 | `comp-modeling` | **建模求解** | `MODELING_REPORT.md` | 同左 | **feedback** | 2,000 | 5400 s |
| 3 | `comp-code` | **编程实现** | `code/main.py`、`RESULTS.md` | `RESULTS.md` | **approve** | 1,000 | 5400 s |
| 4 | `paper-figure` | **图表生成** | `figures/latex_includes.tex` | `figures/` | — | 500 | 5400 s |
| 5 | `paper-figure-drawio` | **流程与架构图绘制** | `figures/latex_includes.tex` | `figures/` | — | 500 | 5400 s |
| 6 | `comp-review` | **逻辑对抗复核** | `COMP_REVIEW.md` | 同左 | — | 40 | 5400 s |
| 7 | `comp-paper-zh` | **竞赛论文撰写** | `paper/main.tex` | 同左 | **approve** | 10,000 | 2700 s |
| 8 | `comp-compile-zh` | **编译与合规检查** | `paper/main.pdf` | 同左 | — | 30,000 | 2700 s |

## 3. 美赛流水线（英文，`_comp_en_steps()` 实测返回）

结构**完全一致**，仅第 7/8 步替换为英文技能：

| # | `skill_name` | 展示名 | 主产物 | 最小字节 |
|---|---|---|---|---|
| 1 | `comp-prob-analysis` | Problem Analysis | `PROBLEM_ANALYSIS.md` | 1,500 |
| 2 | `comp-modeling` | Modeling & Solution | `MODELING_REPORT.md` | 2,000 |
| 3 | `comp-code` | Programming | `RESULTS.md` | 1,000 |
| 4 | `paper-figure` | Figure Generation | `figures/` | 500 |
| 5 | `paper-figure-drawio` | Flow & Architecture Diagrams | `figures/` | 500 |
| 6 | `comp-review` | Logic Adversarial Review | `COMP_REVIEW.md` | 40 |
| 7 | `comp-paper-en` | Paper Writing (English) | `paper/main.tex` | 10,000 |
| 8 | `comp-compile-en` | Compile & Compliance Check | `paper/main.pdf` | 30,000 |

> **★ 复现要点**：中英文流水线**共用前 6 步**，只在「论文撰写 + 编译」分叉。
> 这是很经济的架构——modemon 应当照抄这个分叉点。

### 3.1 华为杯是刻意的例外（docstring 全文已恢复）

`_comp_zh_steps` 的 docstring 原文：

> 返回中文竞赛通用步骤列表。
>
> Most Chinese competitions share the same writing contract. **Huawei Cup is
> the deliberate exception: it has its own graduate-level mechanism and
> solver-depth Skill, so callers can select it without duplicating the DAG.**

**解读**：
- 华为杯有**自己的研究生级机制**与**求解深度技能**；
- 通过 `paper_skill` 参数切换（默认 `'comp-paper-zh'`，华为杯传自己的），
  **而不是复制一份 DAG** —— 这是很克制的设计：**用参数分叉，不用模板分叉**。
- 页码上限 **50 页**（其余中文赛事 30 页）也印证其特殊性。

> **★ modemon 复现要点**：`_comp_zh_steps(first_skill='comp-prob-analysis', paper_skill='comp-paper-zh')`
> 这两个参数就是**竞赛变体的注入点**。要支持新赛事，只需提供新的 `paper_skill`，
> 前 6 步完全复用。

---

## 4. 已恢复的全部 10 个技能

`comp-code` · `comp-compile-en` · `comp-compile-zh` · `comp-modeling` ·
`comp-paper-en` · `comp-paper-zh` · `comp-prob-analysis` · `comp-review` ·
`paper-figure` · `paper-figure-drawio`

## 5. 逐技能契约（完整实测值）

### 5.1 主产物最小字节阈值 `_min_size_for(skill)`

| skill | 阈值 | 语义 |
|---|---|---|
| `comp-compile-*` | **30,000** | 编译产物（PDF）体量最大 |
| `comp-paper-*` | **10,000** | 论文正文 |
| `comp-modeling` | 2,000 | 建模报告 |
| `comp-prob-analysis` | 1,500 | 赛题分析 |
| `comp-code` | 1,000 | 结果文件 |
| `paper-figure*` | 500 | LaTeX 图表引入文件 |
| `comp-review` | 40 | 对抗复核报告（只需结论） |

> **用途**：作为「步骤是否摸鱼」的硬门。低于阈值 ⇒ 判定步骤未真实产出 ⇒ 触发修复。
> 默认值为 `100`（docstring 说明），上表是竞赛模板的覆盖值。

### 5.2 必须存在的二级文件 `_required_companions_for(skill)`

| skill | 要求 |
|---|---|
| `comp-code` | **`["code/main.py", "figures/all_results.json"]`** |
| 其余 9 个 | `[]` |

> **这是竞赛流水线里唯一有二级文件强约束的步骤**——即「编程实现」必须同时产出
> **入口代码**与**机器可读的原始结果**。后者正是防幻觉机制的数据源
> （见主报告 §5.3：数值必须从 `all_results.json` 读取）。

`_check_step_companions` 的校验规则（docstring 原文）：
- 文件存在
- **文件大小 > 50 字节**（防空文件占位）

### 5.3 静默超时 `_step_inactivity_timeout(skill)`

| 分组 | 超时 | 语义 |
|---|---|---|
| 创作型（分析/建模/编程/图表/复核） | **5400 s（90 min）** | 需要长时静默推理 |
| 成文型（论文/编译） | **2700 s（45 min）** | docstring：*Competition manuscript and compile steps should continu…* |

**设计意图**（docstring 原文）：*Bound silent model calls without shortening any visible work.*
⇒ 超时只约束**静默**（无输出）时长，不限制**可见工作**时长。

### 5.4 模板依赖 `_skill_template_dependencies(skill)`

10 个技能**全部为 `[]`** ⇒ 竞赛流水线的技能**不依赖外部模板树**。
（对比：`materialize_skill_templates` 存在，说明其他模板类型会用到。）

### 5.5 计算产物门 `_compute_health_blocks(skill, health_ok=True)`

10 个技能在 `health_ok=True` 时**全部返回 `False`**（不阻断）。
docstring：*Edits alone never substitute for mandatory computation outputs.*
⇒ 该门只在健康检查失败时才阻断。

---

## 6. ★ 竞赛页码规则 `_resolve_competition_page_rule(template)` 实测

| 模板 | 页数上限 | 模式 |
|---|---|---|
| `comp_cumcm`（国赛） | **30** | `advisory_max` |
| `comp_huawei`（华为杯） | **50** | `advisory_max` |
| `comp_mcm`（美赛） | **25** | `advisory_max` |
| `comp_apmcm` | **25** | `advisory_max` |
| `comp_mathorcup` | **30** | `advisory_max` |
| `comp_zh` / `comp_en` / `course_paper` / `thesis_proposal` | `null` | `advisory_max` |

> **★ 关键设计**：全部为 `advisory_max`。docstring 原文：
> *Every competition uses `advisory_max` locally: **the value is visible to the
> user but never becomes a generation, expansion, or compression gate.***
> ⇒ 页数上限**仅对用户可见**，**绝不**用作生成 / 扩展 / 压缩的门控。
> 这避免了因页数判定错误而误杀合规论文——是一个很成熟的取舍。

### 6.2 资源跳过规则 `_should_skip_step_by_assets`（docstring 全文）

仅对 `paper_from_assets` 模板生效，依据 `_assets_index.json`：

```
决策规则:
- paper-analysis:      如果用户已传 code + results, 跳过(不要重跑覆盖)
- paper-figure:        如果用户已传 figures 且没有 missing 标识缺图, 跳过
- paper-figure-drawio: 如果 figures/ 中已有 fig_roadmap.* 或不在 missing_assets
                       中提到 roadmap, 跳过
```

> **★ 两个可复用的命名约定**：`fig_roadmap.*` 是架构图的约定文件名；
> `missing_assets` 是"缺什么"的清单字段。
> 「不重跑覆盖用户已有产出」是这条规则的核心动机。

### 6.1 正文字符预算（此前标为"未获取"，现已恢复）

`_check_paper_body_pages` 的 docstring 给出了具体算法：

```
按竞赛页数语义做保守的正文字符预检。
正文定义：
  - LaTeX 模式：paper/sections/*.tex 总字符数
  - Word 模式：paper/main.md 中「## 附录」之前的部分
  - 中文 chars_per_page ≈ 800（含图表），英文 ≈ 2200
```

⇒ **国赛 30 页 ≈ 24,000 中文字符**；美赛 25 页 ≈ 55,000 英文字符。
**这是可直接落地的数值。**

---

## 7. 常量与约定（模块级实测）

| 常量 | 值 | 用途 |
|---|---|---|
| `AI_DISCLOSURE_PDF_NAME` | **`'AI工具使用详情.pdf'`** | 国赛 AI 使用申报文件的**确切文件名** |
| `CORE_FAILURE` | `'[CORE_ARTIFACT] '` | 核心产物失败标记前缀 |
| `ADVISORY_REPAIR_PREFIX` | `'[OPTIONAL_OPTIMIZATION]'` | 建议性（非阻塞）修复标记 |
| `COMPACT_INDEX_MAX_CHARS` | `6000` | 紧凑索引字符上限 |
| `_MANIFEST_ITEM_RE` | `^[ \t]*-[ \t]+(fig_[A-Za-z0-9_]+|tikz_[A-Za-z0-9_]+)` | **FIGURE_MANIFEST 解析正则**：图表条目必须以 `fig_` 或 `tikz_` 前缀 |

> **★ 两条直接可用的约定**：
> 1. AI 申报文件名就是 `AI工具使用详情.pdf`（对应主报告 §5.7 的国赛门禁）。
> 2. 图表命名规范：**`fig_*`（数据图）/ `tikz_*`（架构图）**，
>    且 manifest 条目形如 `- fig_xxx`。这就是 `_is_drawio_fig`、
>    `_classify_manifest_by_sections` 的解析基础。

## 8. 异常体系（8 个，含错误码）

| 异常 | 构造签名 |
|---|---|
| `StepExecutionFailed` | `()` |
| `StepCheckPending` | `(reason, *, unavailable=False)` |
| `StepRepairInterrupted` | `(reason, *, unavailable=False, safe_to_recheck=False)` |
| `RepairStopped` | `(reason, *, unavailable=False, safe_to_recheck=False)` |
| `ProtectedContentUnavailable` | `(message, *, code='SKILL_CONTENT_UNAVAILABLE')` |
| `AccessModeError` | `(code, status=409)` |
| `AccountError` | `(code, status=400, retry_after=0)` |
| `_DocxPrecheckFailure` | `(reason, *, repairable)` |

> **设计要点**：`StepCheckPending` / `StepRepairInterrupted` / `RepairStopped`
> 三者都带 `unavailable` 与 `safe_to_recheck` 标志——
> 这正是主报告 §5.4 提到的「返修预算三类状态区分」：
> **检查器不可用 / 返修未结束 / 真实缺陷**，必须分开处理，否则会把「工具坏了」误判成「论文有错」。

---

## 9. 质量门（从 docstring 恢复的规则）

| 门 | 函数 | 规则 |
|---|---|---|
| 图表健康（动态） | `_check_figures_step_health` | 基于**本步骤文件增量**；`ok=True` 的四种合法情形：真实新增图 / 用户禁用 / 无图论文场景 / rerun-skip |
| 图表健康（静态） | `_check_figures_step_health_static` | 不依赖 `files_created`；用于**崩溃恢复 / waiting_checkpoint**；退化为「`figures/` 下是否存在该步骤应有的图类」 |
| PDF 视觉门 | `_check_figure_pdf_quality` | **确定性** PDF 视觉检查；原文：*The model saying that a chart "looks fine" is not evidence.* |
| 数据图质量 | `_check_data_figure_quality` | 先查**源文本预算**，再查用户可见的 PDF |
| 二级文件 | `_check_step_companions` | 存在 + 大小 > 50 字节 |
| 页数预检 | `_check_paper_body_pages` | 见 §6.1 |
| 资源跳过 | `_should_skip_step_by_assets` | 基于 `_assets_index.json`；已传 code+results 时跳过 analysis，**不重跑覆盖** |
| 返修循环 | `recover_checked_step` | 每次定向修复后**重查全部**门；`max_repairs=3`、`max_local_rechecks=2`、`max_advisory_repairs=1` |

---

## 10. 对 modemon 的实现建议

### 10.1 可直接照抄（真值已知）

1. **`StepDef` / `TemplateDef` 数据结构**——字段与语义完整。
2. **国赛/美赛两条流水线的步骤序列与技能名**——含中英文展示名。
3. **中英文在「论文撰写 + 编译」分叉、前 6 步共用**的架构。
4. **所有阈值**：主产物最小字节、静默超时、页码上限、字符预算。
5. **命名约定**：`fig_*` / `tikz_*`、`AI工具使用详情.pdf`、`[CORE_ARTIFACT]` 前缀。
6. **异常三态分类**（不可用 / 未结束 / 真缺陷）。
7. **`comp-code` 的双产出约束**（入口代码 + `all_results.json`）——防幻觉的数据锚点。

### 10.2 需要自行实现（函数体不可恢复）

1. 各健康检查的**判定算法**（规则已知，实现要写）。
2. `recover_checked_step` 的**返修状态机**（预算参数已知）。
3. `_resolve_template` 的**动态重写逻辑**（中文替换 / docx 模式 / format-profile 插入）。
4. `_should_skip_step_by_assets` 的**具体跳过规则**（docstring 只给了两条示例）。

### 10.3 与主报告其他部分的衔接

| 需要的东西 | 在哪里 |
|---|---|
| 数据库表结构（承载 `StepDef`） | [`01-backend-api-and-data.md`](01-backend-api-and-data.md) §4 |
| 国赛 AI 使用记录门禁 | 主报告 §5.7 |
| 防幻觉机制（程序拼表 + `all_results.json`） | [`04-methodology.md`](04-methodology.md) §5.3 |
| 中文排版规范 | [`04-methodology.md`](04-methodology.md) |
| 前端如何展示这些步骤（23 个 Skill 中文名映射） | [`03-frontend.md`](03-frontend.md) |

---

## 11. 方法说明与局限

**为什么能拿到真实数据**：
- `_comp_zh_steps` 的**默认参数在签名中可见** ⇒ 无需构造参数即可调用；
- `StepDef` 是 `dataclass` ⇒ 返回对象字段可直读；
- `_min_size_for` 等是**纯访问器** ⇒ 无副作用，可安全求值。

**只调用了白名单内的无副作用函数**，未调用任何写文件、启动进程或网络的函数
（如 `_write_step_handoff`、`run_single_step`、`materialize_skill_templates` 均未触碰）。

**明确未获取**：
- 门控算法的**具体实现**；
- `_resolve_step_effort` 的返回值（该函数是协程，本次调用未 await，仅得到协程对象）；
- `comp_huawei` 与通用中文竞赛的**具体写作契约差异**（docstring 被截断）。
