# Modex-MH-Agent 领域方法论与中文排版规范（逆向分析报告）

> 分析对象：`E:\02_Installers\DailyApps\Modex-MH-Agent`（AI 数学建模竞赛智能体）
> 分析范围：A 组流程模板 9 个 / B 组生成提示词 8 个 / C 组中文排版规范 13 个 / D 组明文 Python 工具 7 个 / E 组已提取引擎规则 / F 组上游 ARIS 对照基线 / **G 组前端构建产物（模板注册表）** / **H 组 `tools\docx-cn-engine\` 明文渲染引擎**
> 标注约定：`【直接提取】`= 原文可读且直接引用；`【推断】`= 由多处原文交叉支持的合理结论；`【推测】`= 证据不足的判断。无法读取的一律写"未获取"。
>
> **第二版修订说明（本次）**：
> 1. **新增第 3 章「工作流模板体系」**——从 G 组前端注册表恢复**全部 30 个内置模板**（22 竞赛 `comp_*` + 5 学术 + 1 资产 + 2 软著/专利）及其步骤编排、页数语义、华为杯例外、CUMCM 的 AI 使用声明合规校验。原第 3–6 章顺延为第 4–7 章。
> 2. **新增第 4.7 节**——更正前次"docx 渲染器内部实现未获取"的**判断错误**：渲染器是 `tools\docx-cn-engine\` 下的**明文 Node.js 源码**，已可通读。
> 3. **新增第 6.1b 节**——补强 ARIS 血缘证据（`arxiv_fetch.py` 的 User-Agent 仍指向上游仓库、`config.py` 自陈 `aris.db` 与 capsule 分发方式），并给出 ARIS 的 83 skill + MCP 服务器清单。

---

## 1. 产品定位与目标用户

### 1.1 从模板反推的产品定位

A 组模板位于 `resources\app\templates\`，其 `README.md` 明确给出模板与工作流的对应关系：

| 模板 | 对应工作流 | 用途（原文） |
|---|---|---|
| `RESEARCH_BRIEF_TEMPLATE.md` | Workflow 1 | "Detailed research direction as document input" |
| `RESEARCH_CONTRACT_TEMPLATE.md` | Workflow 1 | "Define problem boundaries, non-goals, timeline before starting" |
| `EXPERIMENT_PLAN_TEMPLATE.md` | Workflow 1.5 | "Claim-driven experiment roadmap with run order and budgets" |
| `NARRATIVE_REPORT_TEMPLATE.md` | Workflow 3 | "Research narrative with claims, experiments, results" |
| `PAPER_PLAN_TEMPLATE.md` | Workflow 3 | "Pre-made outline to skip planning phase" |

`【直接提取】[证据: templates\README.md:7-13]`

`README.md:15-21` 另列出 "Compact Mode Templates (`— compact: true`)" 三件套，并给出写入者与用途：

> | `IDEA_CANDIDATES_TEMPLATE.md` | `/idea-discovery` | Top 3-5 surviving ideas (lean, not full 12-idea report) |
> | `EXPERIMENT_LOG_TEMPLATE.md` | `/experiment-bridge` | Structured experiment record (results + reproduction commands) |
> | `FINDINGS_TEMPLATE.md` | `/auto-review-loop` | One-line-per-finding discovery log (anomalies, decisions) |

`【直接提取】[证据: templates\README.md:19-21]`

### 1.2 关键发现：模板层是"AI 科研自动化"血统，而非数模竞赛血统

模板正文中出现的目标场景全部指向机器学习顶会科研流程，而非数学建模竞赛：

- `RESEARCH_BRIEF_TEMPLATE.md:9-10`：`**Field**: [e.g., NLP, CV, RL]`、`**Sub-area**: [e.g., discrete diffusion models]`
- `RESEARCH_BRIEF_TEMPLATE.md:16-18`：`**Compute**: [e.g., 8x RTX 3090, 100 GPU-hours]`、`**Target venue**: [e.g., NeurIPS 2026]`
- `PAPER_PLAN_TEMPLATE.md:7`：`- **Venue**: [ICLR / NeurIPS / ICML]`
- `EXPERIMENT_LOG_TEMPLATE.md:39-41`：`### WandB` / `Run URL` / `Run ID`
- `EXPERIMENT_PLAN_TEMPLATE.md:47`：`- **Hardware**: [e.g., 4x RTX 3090]`

`【直接提取】[证据: 上列各行]`

`【推断】` A 组模板整体是从上游 AI-research-agent 血脉直接继承的英文科研模板：其术语体系（claim / ablation / baseline reproduction / GPU-hours / wandb / NeurIPS）与数学建模竞赛（CUMCM/MCM/Huawei 杯）的交付物要求（中文论文、摘要页、附录代码、结果验证）几乎没有交集。这构成第 6 节 ARIS 差分中"直接继承"一侧的核心证据。

### 1.3 目标交付物

模板中明确描述的最终交付物是论文：

- `PAPER_PLAN_TEMPLATE.md:16-36` 给出章节规划：`### 1. Introduction (~1.5 pages)` … `### 5. Conclusion (~0.5 pages)`，并含 `## Figure Plan` 表格（`Fig 1 Architecture / Fig 2 Bar chart / Table 1 Comparison`）`[证据: PAPER_PLAN_TEMPLATE.md:38-43]`
- `NARRATIVE_REPORT_TEMPLATE.md:45-49`：`## Proposed Title`、`## Target Venue`

`【直接提取】[证据: PAPER_PLAN_TEMPLATE.md:38-43；NARRATIVE_REPORT_TEMPLATE.md:45-49]`

`【推断】` 模板层的交付物定义是"英文 ML 论文"；而产品实际面向的中文竞赛论文交付能力，主要由 C 组排版规范与 B 组生成提示词承担（见第 4 节）。

### 1.4 面向赛事（由 C 组封面规范反推）

C 组 `docx_style_profiles\covers\` 目录下存在的封面规范文件，是判断目标赛事最直接的证据：

- `covers\cumcm.json`（2136 B）—— 中国大学生数学建模竞赛
- `covers\huawei.json`（1728 B）—— 华为杯（中国研究生数学建模竞赛）
- `covers\mcm.json`（1198 B）—— MCM/ICM 美赛
- `covers\default_zh.json` / `covers\default_en.json`

`【直接提取】[证据: 目录列表 E:\02_Installers\DailyApps\Modex-MH-Agent\resources\app\tools\docx_style_profiles\covers\]`
`【推断】` 目标赛事至少覆盖 CUMCM（国赛）、华为杯（研赛）、MCM/ICM（美赛）三类。详细封面字段见第 4.5 节。

---

## 2. 全流程方法论（A 组模板 + B 组提示词串联）

### 2.0 流水线总览

`【推断】` 由 A 组模板的"Workflow 1 / 1.5 / 3"编号与 B 组提示词的"写作步骤 / paper-figure 步骤 / docx-export 步骤"命名交叉推断，Modex 的主干流水线为：

```
读题/立项 → 选题定标 → 实验规划 → 执行与记录 → 发现沉淀 → 叙事成文 → 图表生成 → 论文写作 → docx 合规导出
 Workflow1   Idea       Workflow1.5   Experiment   Findings    Narrative   paper-figure  main.md    docx-precheck
              Candidates                Log                                            /TABLE_*.md  docx-export
```

各阶段的输入/输出/质量门如下。


### 2.1 阶段一：读题 / 立项（Workflow 1）

- **输入**：`RESEARCH_BRIEF_TEMPLATE.md`（"Detailed research direction as document input"）`[证据: templates\README.md:9]`
- **模板要求的字段**：Problem Statement / Background（Field、Sub-area、Key papers、What I already tried、What didn't work）/ Constraints（Compute、Timeline、Target venue）/ What I'm Looking For / Domain Knowledge / Non-Goals / Existing Results `[证据: RESEARCH_BRIEF_TEMPLATE.md:5-33]`
- **边界契约**：`RESEARCH_CONTRACT_TEMPLATE.md` —— "Define problem boundaries, non-goals, timeline before starting" `[证据: templates\README.md:10]`
- **输出**：`RESEARCH_BRIEF.md` → 后续产出 `RESEARCH_CONTRACT.md`

**关键约束（原文引用，护城河）**：

> **Why this file exists:** After brainstorming, `IDEA_REPORT.md` contains many candidate ideas. Keeping all of them in context pollutes the LLM's working memory and degrades output quality. This contract extracts *only the active idea* into a standalone document, so new sessions and post-compaction recovery load focused context instead of the entire idea pool.

`【直接提取】[证据: RESEARCH_CONTRACT_TEMPLATE.md:5]`

`【推断】` 这是一条**上下文工程**约束而非领域约束：产品把"会话恢复/压缩后重载"作为一等公民，用"契约文件只装活跃想法"来控制 token 污染。同一思想在 `NARRATIVE_REPORT_TEMPLATE.md` 与 `FINDINGS_TEMPLATE.md` 中重复出现（见 2.4）。

- **质量门（本阶段）**：Non-Goals 必须填写（用于排除跑偏方向）；Constraints 必须显式给出算力/时间/目标 venue。`【直接提取】[证据: RESEARCH_BRIEF_TEMPLATE.md:15-18, 29-30]`


### 2.2 阶段二：选题定标（Idea Discovery，compact 模式）

- **输入**：`RESEARCH_BRIEF.md`
- **输出**：`IDEA_CANDIDATES.md` —— 由 `/idea-discovery` 写入，定位为 "Top 3-5 surviving ideas (lean, not full 12-idea report)" `[证据: templates\README.md:19]`
- **模板显式区分两个文件**：

> Unlike `IDEA_REPORT.md` (raw brainstorm output with all 8-12 ideas), this file only contains ideas that are worth pursuing — filtered, scored, and ready to be selected.

`【直接提取】[证据: IDEA_CANDIDATES_TEMPLATE.md:3]`

**候选条目质量门**：每个候选必须带 `Novelty score: X/10`、`Reviewer assessment`（strength + risk）、`Pilot result: POSITIVE/NEGATIVE/NOT TESTED`、`Estimated effort`、`Why not selected first` `[证据: IDEA_CANDIDATES_TEMPLATE.md:14-19]`

**失败回退语义（重要）**：

> When the current idea fails (result-to-claim negative, or pivot needed), pick the next candidate from here instead of re-running the entire idea discovery pipeline.

`【直接提取】[证据: IDEA_CANDIDATES_TEMPLATE.md:5]`

另有 `## Killed Ideas`（记录 kill reason / kill date / source，避免重探索死路）与 `## Idea Switch Log`（Date/From/To/Reason 表格）`[证据: IDEA_CANDIDATES_TEMPLATE.md:32-47]`

`【推断】` "Killed Ideas + Switch Log" 是防止 LLM 在多轮里反复回到已被否决方向的**反退化机制**。


### 2.3 阶段三：实验规划（Workflow 1.5，claim-driven）

- **输入**：`EXPERIMENT_PLAN_TEMPLATE.md` → 保存为 `refine-logs/EXPERIMENT_PLAN.md` `[证据: EXPERIMENT_PLAN_TEMPLATE.md:3]`
- **核心结构**：`## Claim Map` 表 + `## Experiment Blocks` + `## Run Order` + `## Compute Budget` + `## Risks`

**Claim Map 表头（原文）**：

> | Claim | Why It Matters | Minimum Convincing Evidence | Linked Blocks |

`【直接提取】[证据: EXPERIMENT_PLAN_TEMPLATE.md:10]`

**每个 Block 的必填字段**：Claim tested / Dataset / Compared systems / Metrics / Setup details / **Success criterion** / **Failure interpretation** / **Priority** `[证据: EXPERIMENT_PLAN_TEMPLATE.md:17-34]`

**质量门（本阶段，三条硬约束）**：
1. 每个实验块必须绑定 claim（`- **Claim tested**: C1`），无 claim 的实验不允许存在 `[证据: EXPERIMENT_PLAN_TEMPLATE.md:18]`
2. 必须有量化成功判据，例如 `- **Success criterion**: [e.g., "> 2% accuracy over baseline"]` `[证据: EXPERIMENT_PLAN_TEMPLATE.md:23]`；消融块同理 `- **Success criterion**: [Each component contributes > 0.5%]` `[证据: EXPERIMENT_PLAN_TEMPLATE.md:30]`
3. 必须有**阴性结果解释**：`- **Failure interpretation**: [If negative, what does it mean?]` `[证据: EXPERIMENT_PLAN_TEMPLATE.md:24]`
4. 优先级二值化：`- **Priority**: MUST-RUN` / `- **Priority**: NICE-TO-HAVE` `[证据: EXPERIMENT_PLAN_TEMPLATE.md:25,35]`

**Run Order 决策门（原文表）**：

> | M0: Sanity | Pipeline works | 1 quick run | Loss decreases? | ~0.5h |
> | M1: Baselines | Reproduce baselines | Block 3 | Numbers match? | ~4h |
> | M2: Main | Full method | Block 1 | Meets criterion? | ~8h |
> | M3: Ablation | Components | Block 2 | Each matters? | ~6h |

`【直接提取】[证据: EXPERIMENT_PLAN_TEMPLATE.md:40-43]`

`【推断】` 这里的 "Decision Gate" 列就是**执行期质量门**的落地形式：每个里程碑先跑低成本 sanity，再复现基线，数值对不上就不往下走。


### 2.4 阶段四：执行与记录（Experiment Bridge）

- **输入**：`EXPERIMENT_PLAN.md` → 执行 → `EXPERIMENT_LOG.md`（由 `/experiment-bridge` 写入）`[证据: templates\README.md:20]`
- **双文件分工（原文，值得整段引用）**：

> **How it differs from EXPERIMENT_TRACKER.md:** The tracker (in `refine-logs/`) is an execution checklist (TODO → RUNNING → DONE). This log is a permanent record with full results, configs, and reproduction commands. The tracker tells you what's left to do; the log tells you what was done and what it showed.

`【直接提取】[证据: EXPERIMENT_LOG_TEMPLATE.md:5]`

**写入时机铁律**：

> **Update rule:** Write an entry immediately after each experiment completes. Do not batch entries or wait until "later."

`【直接提取】[证据: EXPERIMENT_LOG_TEMPLATE.md:7]`

**每条记录必含**：Date / Idea / Goal / Setup（Method、Dataset、Baseline、Hardware、Config）/ Results 表 / **Verdict（Supports claim? Yes/Partially/No + Key takeaway）** / **Reproduction（可执行 bash 命令）** / WandB `[证据: EXPERIMENT_LOG_TEMPLATE.md:9-41]`

`【推断】` "Reproduction 必须给出可直接跑的命令" 是**可复现性质量门**；"Verdict 必须回填 Yes/Partially/No" 把结果强行回链到 claim。


### 2.5 阶段五：发现沉淀（Auto Review Loop → Findings）

- **输出**：`FINDINGS.md`（由 `/auto-review-loop` 写入），"One-line-per-finding discovery log (anomalies, decisions)" `[证据: templates\README.md:21]`
- **存在理由（原文）**：

> **Why this file exists:** Experiments produce discoveries that are critical for future decisions but don't belong in formal experiment reports. Without a central log, these get lost between sessions — and the next session repeats the same mistakes or misses important signals.

`【直接提取】[证据: FINDINGS_TEMPLATE.md:5]`

- **双栏结构**：`# Research Findings`（方法级洞察，含 Hypothesis / Implication）与 `# Engineering Findings`（基础设施与调试教训，含 Problem and root cause / Fix applied）`[证据: FINDINGS_TEMPLATE.md:9-52]`
- **读取时机**：`Read on every session recovery, so keep entries concise.` `[证据: FINDINGS_TEMPLATE.md:3]`

**模板给出的 3 个示范条目（原文节选）**：

> - Our proposed attention mechanism shows no improvement on CIFAR-10 (acc 93.1 vs baseline 93.0) but +2.3% on ImageNet
> - Hypothesis: the module needs sufficient spatial diversity to capture meaningful patterns; small-resolution inputs don't provide this
> - Implication: restrict claims to medium/large-scale datasets

`【直接提取】[证据: FINDINGS_TEMPLATE.md:18-20]`

> - Paper reports 95.5 on dataset-X; we get 93.2 with their official code
> - Root cause: different data preprocessing (center crop vs resize-then-crop)
> - Decision: use our preprocessing for fair comparison, document in paper

`【直接提取】[证据: FINDINGS_TEMPLATE.md:46-48]`

`【推断】` 第三条示范是"基线复现差距必须溯源并在论文中声明"的方法论立场——属于学术诚信约束，而非排版约束。


### 2.6 阶段六：叙事成文（Workflow 3）

- **两条入口**，二选一：
  - `NARRATIVE_REPORT_TEMPLATE.md` → `/paper-writing "NARRATIVE_REPORT.md"` `[证据: NARRATIVE_REPORT_TEMPLATE.md:3]`
  - `PAPER_PLAN_TEMPLATE.md` → `/paper-writing "PAPER_PLAN.md"`，用途是 "Pre-made outline to skip planning phase" `[证据: templates\README.md:13]`
- **叙事模板必填**：Core Story（2-3 段：problem, approach, key finding, contribution）/ Claims / Experiments（Setup + 每实验表格 + **Interpretation**）/ Figures / **Known Weaknesses** / Related Work / Proposed Title / Target Venue `[证据: NARRATIVE_REPORT_TEMPLATE.md:5-49]`
- **Claims-Evidence 矩阵（论文计划的护城河）**：

> | # | Claim | Evidence | Section |
> | C1 | [Main claim] | [Table 1, Exp A] | §3 |

`【直接提取】[证据: PAPER_PLAN_TEMPLATE.md:11-13]`

`【推断】` 该矩阵强制"每个 claim 必须有 artifact（表/图/实验）支撑并落到具体章节"，是从 claim 到论文结构的可追溯链。

- **质量门**：`## Known Weaknesses` 为必填段（要求主动自曝局限）`[证据: NARRATIVE_REPORT_TEMPLATE.md:37-39]`


### 2.7 阶段七：图表生成（paper-figure 步骤）

B 组 5 个提示词全部服务于这一阶段，且**按输出格式分叉**（Word 模式 vs LaTeX 模式）：

| 提示词 | 触发场景 | 核心约束 |
|---|---|---|
| `course_docx_png_only.md` | Word 导出工作流 | "**所有图表只输出 PNG，不要输出 PDF**" `[证据: :4-5]` |
| `course_docx_table_md.md` | Word 导出工作流 | "**所有结果表格必须输出为 `.md`，不要再生成 `.tex`**" `[证据: :4]` |
| `course_docx_drawio_png.md` | Word 导出工作流 | DrawIO 仅导 PNG + 自动裁白边 `[证据: :3]` |
| `paper_figure_lang_zh.md` | 中文论文 | 图表标注全部中文 `[证据: :3-11]` |
| `nature_figure_lang.md` | `figure_style=nature` | "使用 Nature 配色风格但**图表标签必须用中文**" `[证据: :3-4]` |

**关键约束（原文引用）**：

> **为什么这条铁律重要**：写作步骤会直接 `cat figures/TABLE_xxx.md >> paper/main.md`，完全跳过「从 JSON 抠数字到 Markdown 表格」这一步，从源头杜绝 AI 编造/记错表格数字。

`【直接提取】[证据: course_docx_table_md.md:6]`

> 表格里的所有数值**必须**从 `figures/all_results.json` / `figures/*.json` / `RESULTS.md` 读取，禁止凭记忆填

`【直接提取】[证据: course_docx_table_md.md:37]`

`【推断】` 这是**防幻觉的核心机制**：表格不做"LLM 誊抄"，而是程序生成 `.md` 后由 shell `cat` 直接拼进正文，LLM 只负责写解读文字。这是 Modex 相对通用写作 agent 的实质性工程增量。

**图片清晰度质量门**：每张 PNG 应 ≥ 50KB，< 30KB 判为可能模糊需提高 DPI 重出 `[证据: course_docx_png_only.md:51；course_docx_drawio_png.md:81]`；DPI 约定 350（含中文小字时，"250 以下会糊"）`[证据: course_docx_png_only.md:20]`，DrawIO `--scale 4` 约 384 DPI 防中文糊 `[证据: course_docx_drawio_png.md:10]`。

**残留物质量门**：`figures/` 不允许残留 `fig_*.pdf` / `tikz_*.pdf` / `TABLE_*.tex`，残留数 > 0 即 ❌ 必须修复 `[证据: course_docx_png_only.md:44-45；course_docx_table_md.md:47-48]`。

**TikZ 多页处理**：多页 PDF 必须拆页转多张 PNG（`tikz_diagrams_1.png, _2.png ...`）供正文分别引用 `[证据: course_docx_png_only.md:29-39]`，且"不能因为转了 PNG 却没在正文引用而丢图" `[证据: course_docx_png_only.md:56]`。


### 2.8 阶段八：论文写作（docx-export 前置）

- **输入**：`figures/*.md` + `figures/*.png` + `figures/all_results.json` + `RESULTS.md`
- **输出**：`paper/main.md`（唯一主文件）
- **写作模式硬切换（原文）**：

> ## ⛔ 写作模式：Markdown（不要写 LaTeX）
> 本工作流最终导出 Word（.docx），由后续 docx-export 步骤把 `paper/main.md` 自动转成 .docx。
> **字号、字体、页边距、行距等格式由引擎按工作流 profile 自动应用，你只需要写好 markdown 内容**。

`【直接提取】[证据: docx_write_markdown.md:3-6]`

> - **必须产出 `paper/main.md`**（一个完整的 Markdown 文件，不是多个 .tex sections）
> - **禁止使用 `\documentclass`、`\begin{document}`、`\section{}` 等 LaTeX 命令**

`【直接提取】[证据: docx_write_markdown.md:9-10]`

- **职责分离声明（重要）**：

> ⛔ **章节内容、章节深度、字数分配、用几张图几张表完全由你根据论文实际内容决定**，
> 不要为了模仿某个骨架而强行填空章节。本 prompt 只约束"格式（结构性）"，不约束"内容"。

`【直接提取】[证据: docx_write_markdown.md:99-100]`

`【推断】` 产品刻意把"排版约束"与"内容生成"解耦：提示词只管结构合法性，字号/字体/行距交给 docx_style_profiles（第 4 节）。这是可解释、可测试的设计。

- **用户上传模板的最高优先级**：

> ## ⛔ 用户已上传 LaTeX 模板套件（最高优先级）
> - `.cls/.sty` 文件 → 不要修改，编译时会自动加载
> - 不要重写或替换为默认竞赛模板

`【直接提取】[证据: user_template_latex.md:3-11]`

- **补充：用户模板的插槽变量**为 `{{ bundle_lines }}` 与 `{{ cls_hint }}` `[证据: user_template_latex.md:5-6]`；`docx_write_markdown.md` 另含插槽 `{{ figures_block }}`（"figures/ 中已有的图（必须全部嵌入 paper/main.md）"）`[证据: docx_write_markdown.md:93-94]`。


### 2.9 阶段九：合规与导出（docx-precheck / docx-format-check / docx-export）

三个校验步骤的名字直接出现在提示词中：
- `docx-precheck` 自动把 PDF 转 PNG `[证据: academic_docx_traps.md:51]`
- `docx-format-check` / `docx-export` 是陷阱清单的兜底关卡：

> **问题必须就地修复，不要让它流到 docx-format-check / docx-export 步骤。**

`【直接提取】[证据: academic_docx_traps.md:100]`

`academic_docx_traps.md` 强制"写完后自检"并给出可执行脚本 `[证据: academic_docx_traps.md:88-99]`：

```bash
TARGET={{ target_md }}
n=$(grep -c '^```' "$TARGET" 2>/dev/null || echo 0)
[ $((n % 2)) -ne 0 ] && echo "❌ 代码块标记不平衡（共 $n 个）"
grep -nE '\$\$\s*[（][0-9]+[）]' "$TARGET" && echo '⚠ 公式编号用了全角括号'
grep -nE '<img\s' "$TARGET" && echo '⚠ 出现 HTML img 标签'
grep -nE '<(div|span|table|tr|td)\b' "$TARGET" && echo '⚠ 出现 HTML 标签'
grep -nE '\*\*[^*]+[：:]\*\*' "$TARGET" && echo '⚠ 检测到 **标签：** 写法（冒号在加粗里），改成 **标签**：'
```

`【直接提取】[证据: academic_docx_traps.md:91-98]`

**六类渲染陷阱（A–F，原文分类）** `[证据: academic_docx_traps.md:4,17,42,48,54,70,76]`：
A. 代码块（≥3 行必须 fenced，禁止单反引号串接，` ``` ` 必须成对）
B. 公式与编号（禁止裸 LaTeX、禁止多公式同一对 `$$`、每个块公式必须 `\tag{n}` 连续编号、编号必须半角 `(1)`、禁止 `\begin{equation}`）
C. 三线表（必须有 `|---|---|` 分隔行、列数对齐、cell 内 `|` 转义为 `\|`、禁止 HTML 表格）
D. 图片（仅 Markdown 语法、仅 `.png`、题注带「图 X：」前缀）
E. Markdown 噪声（禁止整段加粗、禁止 HTML 块、禁止 `&nbsp;` 实体、禁止残留 `\\`）
F. 「标签+冒号+内容」冒号必须在 `**` 外

**F 条的动机（原文，中文 AI 痕迹识别）**：

> 把冒号写进 `**` 内是中文 AI 写作最高频的痕迹之一，渲染到 Word 后会留下两颗孤立 `*`（视觉上像 `**` 字符），非常 AI。

`【直接提取】[证据: academic_docx_traps.md:85]`

> 把冒号写进 `**` 内是中文 AI 写作最常见痕迹，docx 渲染时会因正则匹配失败留下两颗孤立 `*`，
> 在 Word 里显示为视觉上像点点的 `**` 字符——非常"AI"。

`【直接提取】[证据: docx_write_markdown.md:39-40]`

`【推断】` 整个第九阶段的方法论目标不是"格式正确"，而是**去 AI 味**（消除可被评审察觉的机器生成痕迹）。这构成产品护城河的第二条主线。


---

## 3. 工作流模板体系

> 本节为补齐项：前次分析未覆盖内置工作流模板的**完整清单与步骤编排**。证据来源为前端已构建产物（明文、可直接读）与 `.pyd` 字符串表。
>
> **关于行号**：`resources\app\dist\assets\*.js` 是 Vite 压缩产物，单行长度可达数十万字符（`Dashboard-2mxANXyi.js` 全文仅 1 行）。因此本节对前端文件按**变量名 + 字符偏移**定位，不引行号；对 `.pyd` 字符串表与明文 Markdown 仍引行号。

### 3.1 模板清单的权威来源：前端注册表（比 `schema.sql` 注释完整）

`schema.sql:3` 只给了省略式注释（`idea_discovery | experiment_bridge | ... | comp_* ...`），而**完整清单**在前端构建产物里以注册表数组形式存在：

`【直接提取】[证据: dist\assets\NewWorkflow-Ld6TEJjT.js，变量 Te，字符偏移 ≈39900–42800；Oe / ke / Ae 紧随其后]`

该注册表每条记录的字段为 `{value, icon, label, desc, time, lang, pages, stars, group}`，其中 `desc` 即**步骤编排的紧凑表达**、`pages` 即**页数语义**、`group` 为 `zh`/`en` 分组。另一份图标/中文名映射表在 `Dashboard-2mxANXyi.js`（变量 `u`/`d`，单行压缩文件）。

产品把模板分成**三个互斥产品面**（前端顶部页签）`【直接提取】[证据: NewWorkflow-Ld6TEJjT.js，字符偏移 ≈65400 附近的页签分支 academic / competition / from_assets]`：

| 产品面 | 页签 | 含义 | 模板数 |
|---|---|---|---|
| `academic` | 📝 学术写作 | 通用学术 / 竞赛之外的论文类写作 | 5（+ `paper_writing` 的多个内部分支） |
| `competition` | 🏆 竞赛工作流 | 数模/统计类竞赛全流程 | 22 |
| `from_assets` | 📝 从已有资料写论文 | 已有代码/数据/图/结果 → 反推成文 | 1（`paper_from_assets`） |

另有 `ip` 产品面 2 个模板（软著 / 专利，见 3.8）。

`【推断】` 这是一个比 `schema.sql` 注释更准确的产品结构：`schema.sql:3` 把 `comp_*` 与其他模板平铺罗列，实际产品把它们**按用户意图分区**，且 `full_pipeline` / `paper_writing_zh` 属学术面而非竞赛面。

### 3.2 竞赛模板族 `comp_*`（22 个，数模竞赛特化的主体）

`【直接提取】[证据: NewWorkflow-Ld6TEJjT.js，变量 Te，字符偏移 ≈39900–42800]`

| # | `value` | `label` | 赛期 | lang | pages | stars |
|---|---|---|---|---|---|---|
| 1 | `comp_tianfu` | 天府杯 | 3月 | zh | 30 | 4 |
| 2 | `comp_certcup` | 认证杯 | 4-5月 | zh | 35 | 3 |
| 3 | `comp_mathorcup` | MathorCup | 4月 | zh | 30 | 4 |
| 4 | `comp_teddy` | 泰迪杯 | 4月 | zh | 40 | 3 |
| 5 | `comp_huadong` | 华东杯 | 4-5月 | zh | 30 | 2 |
| 6 | `comp_huazhong` | 华中杯 | 4-5月 | zh | 30 | 2 |
| 7 | `comp_wuyi` | 五一杯 | 5月 | zh | 30 | 3 |
| 8 | `comp_zhongqing` | 中青杯 | 5月 | zh | 30 | 3 |
| 9 | `comp_yangtze` | 长三角 | 5月 | zh | 30 | 2 |
| 10 | `comp_stats` | 统计建模大赛 | 5月 | zh | 30 | 3 |
| 11 | `comp_shuwei` | 数维杯 | 5月 | zh | 30 | 3 |
| 12 | `comp_diangong` | 电工杯 | 5-6月 | zh | 30 | 4 |
| 13 | `comp_liaoning` | 辽宁省/东三省 | 6月 | zh | 30 | 2 |
| 14 | `comp_apmcm_zh` | 亚太赛中文 (APMCM) | 6月 | zh | 25 | 3 |
| 15 | `comp_shenzhen` | 深圳杯 | 7-9月 | zh | 30 | 4 |
| 16 | `comp_huashu` | 华数杯 | 8月 | zh | 30 | 3 |
| 17 | **`comp_cumcm`** | **国赛 (CUMCM)** | 9月 | zh | 30 | **5** |
| 18 | **`comp_huawei`** | **华为杯** | 9月 | zh | **50** | **5** |
| 19 | **`comp_mcm`** | **美赛 (MCM/ICM)** | 2月 | **en** | 25 | **5** |
| 20 | `comp_shuwei_en` | 数维杯国际赛 | 11月 | en | 25 | 3 |
| 21 | `comp_apmcm` | 亚太 (APMCM) | 11月 | en | 25 | 3 |
| 22 | `comp_certcup_en` | 小美赛 (认证杯国际) | 12月 | en | 25 | 3 |

**六阶段编排（18 个中文竞赛共用同一 `desc`）** `【直接提取】`：

> `赛题分析 → 建模 → 编程 → 图表 → 论文 → 编译`

英文竞赛（`comp_mcm` / `comp_shuwei_en` / `comp_apmcm` / `comp_certcup_en`）`desc` 为逐词对应的：

> `Analysis → Modeling → Code → Figures → Paper → Compile`

`comp_stats`（统计建模大赛）是**唯一编排例外** `【直接提取】`：

> `选题规划 → 数据采集分析 → 图表 → 论文 → 编译`

`【推断】` 该六阶段与"读题拆解 → 建模 → 求解 → 编程 → 图表 → 论文成文 → 合规检查"一致，说明 `desc` 字段是**产品对自身方法论的官方自我描述**，是本报告第 2 节流水线的权威锚点。`comp_stats` 的差异说明蓝方认识到"统计建模大赛重数据采集"这一赛事差异。

### 3.3 步骤编排的内部实现与中英文双轨

六阶段 `desc` 不是文案，而是对应引擎里的**两套硬编码步骤表**：

`【直接提取】[证据: strings\services__workflow_engine.cp311-win_amd64.pyd.strings.txt:1154-1157]`

```
_comp_zh_steps      ← workflow_engine._comp_zh_steps
_comp_en_steps      ← workflow_engine._comp_en_steps
```

并有配套常量 `_comp_en_templates` `[证据: 同文件:1391]`。

`【推断】` 结合 3.2 的 `lang` 字段（zh 18 / en 4）与 `covers\` 的中英文兜底封面，可确认：**中文竞赛走 `_comp_zh_steps`，英文竞赛走 `_comp_en_steps`**，两套步骤在"图表/成文"阶段分化（中文走 Word/docx，英文走 LaTeX/PDF，见第 4 节）。

**步骤命名的跨语言统一**：引擎质量门里出现的步骤名（`paper-analysis` / `paper-figure` / `paper-figure-drawio` / `paper-plan` / `nature-figure` / `experiment-bridge` / `assets-inventory` / `docx-export`）在两种 lang 下**同名**，仅编排组合与输出契约不同 `【推断】[证据: strings\_merged_strings.txt:10802-10813, 10877-10881, 10977-10995]`。

**流水线的图/表产物契约**（`FIGURE_MANIFEST` 机制）`【直接提取】[证据: strings\_merged_strings.txt:10797-10813]`：

```
FIGURE_MANIFEST
    manifest
(paper-plan/SKILL.md
        **
matplotlib gen_fig_*.py
paper-figure
 .png/.pdf
        **DrawIO
paper-figure-drawio
 .drawio + .png/.pdf
        **TikZ
paper-figure
 tikz_*.pdf

 data_figs   (paper-figure
 DrawIO/HTML
 + TikZ
 drawio_figs (paper-figure-drawio/-html
```

`【推断】` 这段被 Cython 字符串压缩截断，但足以证明：`paper-plan` 阶段产出的 `SKILL.md` 清单会写入 `<!-- BEGIN FIGURE_MANIFEST -->` 块，后续 `paper-figure`（matplotlib/TikZ）与 `paper-figure-drawio`（DrawIO/HTML）按此清单**分工产出**，引擎再按 `data_figs` / `drawio_figs` 两类回收到健康检查。这与 2.7 节的 `figures/TABLE_*.md`、`figures/fig_*.png`、`tikz_*.pdf` 命名约定互相印证。

**自动恢复白名单也按步骤给出**（`AUTO-RECOVER`）`【直接提取】[证据: strings\_merged_strings.txt:10976-10995]`：

```
 AUTO-RECOVER
        - paper-figure / nature-figure / experiment-bridge:
 paper-figure-drawio
: figures/
        - paper-figure-drawio:
(drawio
 skip_figures/skip_drawio:
        - PAPER_PLAN.md
 paper_from_assets
 _assets_index.json
    - paper-analysis:
 code + results,
    - paper-figure:
 figures
 missing
    - paper-figure-drawio:
 fig_roadmap.*
 missing_assets
 roadmap,
```

`【推断】` 可读出：`paper-figure` / `nature-figure` / `experiment-bridge` 支持在 `PAPER_PLAN.md` 声明"无图"时合法跳过（`skip_figures` / `skip_drawio` 开关）；`paper-analysis` 依赖"代码 + 结果"；`paper-figure-drawio` 依赖 `fig_roadmap.*`，缺失时进入 `missing_assets`（缺资产）而非直接判失败。

### 3.4 `paper_from_assets`：资产盘点与缺口自动补全

`from_assets` 产品面只有一个模板 `【直接提取】[证据: NewWorkflow-Ld6TEJjT.js，变量 ke]`：

> `{value: paper_from_assets, icon: 📝, label: 从已有资料写论文, desc: 已有代码/数据/图/结果 → 智能盘点资产 → 缺什么自动补什么 → 生成完整论文, time: ~30-60 分钟}`

引擎侧对应 `assets-inventory` 步骤与 `_assets_index.json` 索引文件 `【直接提取】[证据: strings\_merged_strings.txt:10877-10879, 10892-10894]`。

**资产类型 → 归置目录的映射规则**（对复现极有价值，近乎完整规格）`【直接提取】[证据: strings\_merged_strings.txt:11009-11018]`：

```
paper_from_assets
    assets-inventory skill
    - user_data/*.py / *.ipynb / *.zip
    - user_data/*.csv / *.xlsx / *.tsv / *.json
 data/ (
 results.json)
    - user_data/*.png / *.jpg / *.jpeg / *.svg
 figures/user_fig_*
    - user_data/*.tex / *.cls / *.sty / *.docx / *.dotx
 _user_templates/
```

盘点结果结构 `【直接提取】[证据: strings\services__workflow_engine...strings.txt:1898-1911]`：

```python
{
    "has_problem": bool, "has_code": bool, "has_data": bool,
    "has_figures": bool, "has_results": bool, "has_templates": bool,
    "missing_assets": [str, ...],
    "conflicts": [{"type": str, "severity": str, "files": [...]}, ...],
    "conflict_count": int, "high_severity_count": int,
}
```

并有 `_should_skip_step_by_assets` 依资产情况**跳过不必要步骤** `[证据: 同文件，函数名列表]`。

`【推断】` 这是 ARIS 完全没有的能力：ARIS 的起点是"一句话研究方向"（`RESEARCH_BRIEF_TEMPLATE.md`），而 Modex 增加了"用户已有一堆半成品 → 反向补齐成完整论文"的入口。这对数模竞赛真实场景（队伍已有模型代码与结果，只差成文与排版）高度契合，属**面向真实工作流的自研增补**。

### 3.5 页数语义：`advisory_max`（页数只提示、不阻断）

每个竞赛模板带 `pages` 字段（国赛 30 / 华为杯 50 / 美赛 25 / 泰迪杯 40 …），引擎侧对应：

`【直接提取】[证据: strings\services__workflow_engine...strings.txt:1974-1976]`

> Return the final-submission page reference for one competition.
>     Every competition uses ``advisory_max`` locally: the value is visible to the
>     user but never becomes a generation, expansion, or compression gate.

`【推断】` 这是一个明确的产品判断：**页数上限不作为生成/扩写/压缩的硬闸**，只作提示。原因可推知——各赛事页数规则逐年会变，且"为凑页数而注水"比"短而实"更伤质量。复现时应保留这一语义，不要实现成硬性字数门。

### 3.6 华为杯是唯一"机制不同"的竞赛（重要差分）

`【直接提取】[证据: strings\services__workflow_engine...strings.txt:1978-1980]`

> Most Chinese competitions share the same writing contract.  Huawei Cup is
>     the deliberate exception: it has its own graduate-level mechanism and
>     solver-depth Skill, so callers can select it without duplicating the DAG.

`【推断】` 三点结论：
1. 中文竞赛**共用同一套撰写契约**（同一 `_comp_zh_steps` + `competition_zh` profile）；
2. **华为杯（研究生赛）是唯一例外**，有独立的"研究生级机制 + 求解深度 skill"；
3. 该例外通过**步骤级选择（select）**实现，而非复制一份 DAG —— 这是对"DAG 复用"的显式工程约束。

与之呼应的是华为杯的**签名模板包** `【直接提取】[证据: strings\_merged_strings.txt:6453-6456]`：

> Install the authenticated template tree required by ``skill_name``.
>     Template ownership is explicit.  In particular, the Huawei writer uses
>     the signed ``comp-paper-zh/templates/huawei`` bundle; it must never silently
>     fall back to a generic ``ctexart`` document when that bundle is missing.

`【推断】` 由此确定两条内部标识符：skill 包名 **`comp-paper-zh`**，其下有 **`templates/huawei`** 子包；且产品对"华为杯模板缺失"选择 **fail-closed**（宁可失败也不静默降级为通用 `ctexart`）。另一条日志样例 `'abc123_comp-paper-zh'` 印证该命名 `[证据: strings\_merged_strings.txt:6412]`。

同时存在 skill 标识符 **`comp-code`**（编程步骤）`【直接提取】[证据: tools\skill_instruction_guard.py:166]`：

```python
if (manifest.get('skill') == 'comp-code'
        and name in ('Bash', 'Agent', 'Task')
        and inp.get('run_in_background')):
```

`【推断】` 综合 `comp-paper-zh` 与 `comp-code` 两个标识符：`comp_*` 工作流模板在引擎内部被拆成**若干 `comp-*` 命名的 skill 包**（至少"成文"与"编程"两类），模板名与 skill 包名不是一一对应，而是"模板 = skill 序列"。这与 `schema.sql:18-35` 的 `workflow_steps.skill_name` + `step_order` 结构一致。

### 3.7 学术写作模板族（5 + 内部分支）

`【直接提取】[证据: NewWorkflow-Ld6TEJjT.js，变量 Oe]`

| `value` | label | 步骤编排（原文 `desc`） | 预估耗时 |
|---|---|---|---|
| `paper_writing` | 论文写作 | 通用学术 / Nature 顶刊 / 人文社科 — 卡片内切换分支，各有专属规划与撰写 skill | ~30-120 分钟 |
| `thesis_proposal` | 开题报告 | 文献调研 → 开题撰写 → 技术路线 → Word导出 | ~30-60 分钟 |
| `literature_review` | 文献综述 | 文献检索 → **真实性验证** → 主题聚类 → 综述撰写 → Word导出 | ~30-60 分钟 |
| `course_paper` | 课程论文 | 大纲规划 → [可选: 数据分析+图表] → 撰写嵌入图 → 审查 → Word导出 | ~25-50 分钟 |
| `course_report` | 课程报告 | 事实提取+大纲 → [可选: 数据分析+图表] → [可选: 架构图] → 撰写嵌入图 → 审查 → Word导出 | ~25-50 分钟 |

**注**：`schema.sql:3` 里出现的 `humanities_paper` **不是独立模板**，而是 `paper_writing` 卡片内的一个分支（原文 `人文社科 — 卡片内切换分支`）。

`paper_writing` 的分支由 `paper_type` 参数选择 `【直接提取】[证据: NewWorkflow-Ld6TEJjT.js，变量 je]`：

```
academic_zh 学术论文（中文） / academic_en 学术论文（英文） /
competition 竞赛论文（数模/认证杯等） / course 课程论文 / 课程报告 /
nature Nature / SCI 期刊风格
```

另有 `nature_writing` 出现在"论文类模板"判定函数中 `【直接提取】[证据: Dashboard-2mxANXyi.js，单行压缩文件]`：

```javascript
p = e => ["thesis_proposal","literature_review","course_paper","course_report",
          "paper_writing","paper_writing_zh","nature_writing"].includes(e)
```

`【推断】` 该函数即"是否需要走 Word/论文导出链路"的判定；`comp_*` 由另一谓词 `f = e => e.startsWith("comp_")` 单独判定。

参数联动：学位类型给默认页数 `bachelor 25 / master 55 / journal 15`；顶会给默认页数 `ICLR 9 / NeurIPS 9 / ICML 8` `【直接提取】[证据: 变量 Ee / De]`。学科选项 `cs / humanities / economics / engineering`，人文社科下再分 10 个子领域（`literature / history / philosophy / sociology / communication / cultural_studies / education / law / art / politics`）`【直接提取】[证据: 变量 Me / Ne]`。

### 3.8 商业化增补：软著与专利产品面（`ip`）

`【直接提取】[证据: NewWorkflow-Ld6TEJjT.js，变量 Ae]`

| `value` | label | 步骤编排（原文 `desc`） |
|---|---|---|
| `copyright_material` | 生成软著申请资料 | 一句话描述软件 → AI 撰写业务理解/合成示例源码/申请表/操作手册 → 正式 Word/TXT |
| `patent_disclosure` | 生成专利交底书 | 一句话描述技术 → AI 撰写背景/技术方案(含 mermaid 框图流程图)/保护点 → 渲染图示导出 Word |

`【推断】` 这两个模板**完全在 ARIS 的方法论范围之外**（ARIS 的 `patent-*` skill 面向"专利检索/新颖性/审查意见"，而非"生成交底书"；软著在中国以外无对应制度）。它们是**纯商业化的中文本地化产品**，且复用同一套 Word/mermaid 渲染链路 —— 说明蓝方把排版引擎做成了**跨产品的通用能力**，而非仅为竞赛服务。这从工程上反证了排版引擎是核心资产。

### 3.9 竞赛合规：CUMCM 的 AI 使用声明（2025+ 新规）

前端对 `comp_cumcm` 有**单独特判** `【直接提取】[证据: NewWorkflow-Ld6TEJjT.js，字符偏移 ≈11734 附近]`：

```javascript
function w(e){ return e === `comp_cumcm` }
```

该分支绑定了较严格的"AI 使用记录"表单校验，原文错误文案 `【直接提取】`：

> `请先确认所填 AI 使用记录真实、完整，并已由参赛队人工核验`
> `请填写 1–5 条真实 AI 工具记录`
> `请为第 N 条记录选择实际使用的国产 AI 工具`
> `请填写第 N 条记录的真实模型版本或型号（1–80 个字符）`
> `第 N 条记录的模型不属于所选国产工具`

`【推断】` 这是**响应全国大学生数学建模竞赛"AI 使用声明"要求**的合规功能（申报所用 AI 工具与模型，且限定国产工具）。校验包含：条数 1–5、供应商必选且在白名单内、模型名需匹配该供应商的 `modelPattern`、长度 1–80、禁止控制字符。提交参数为 `ai_disclosure: used|none` 与 `ai_disclosure_details: {confirmed_truthful, records[]}` `[证据: 同文件，字符偏移 ≈65400 附近的参数组装分支]`。

`【推断】` 这是**赛事规则驱动的自研增补**，ARIS 无任何对应物，是产品"合规检查"能力的直接证据。`schema.sql` 无此表，说明 AI 使用记录随工作流 `params` JSON 走，不单独建表 `【推断】`。

### 3.10 模板参数面（创建工作流请求可观测的完整参数）

除模板 `value` 外，创建请求还携带大量行为开关 `【直接提取】[证据: NewWorkflow-Ld6TEJjT.js，字符偏移 ≈65400 附近的 n={...} 组装分支]`：

| 参数 | 取值/语义 |
|---|---|
| `skip_improvement_loop` | 跳过改进循环 |
| `data_fig_vision` / `skip_diagram_vision` | 数据图 / 结构图视觉自检开关 |
| `flow_per_problem` | 按问题分节（多问题竞赛） |
| `ai_disclosure` / `ai_disclosure_details` | 见 3.9 |
| `data_fig_palette` / `data_fig_colors` / `data_fig_style` / `data_fig_style_custom` | 配色与版式（`random` 或自定义色系数组） |
| `figure_style` | `default` / `nature` / 6 套版式之一 |
| `flowchart_engine` / `diagram_style` | `html` 等 + 图风格 |
| `language` / `max_pages` / `output_format` / `paper_type` / `column_layout` | 语言 / 页数 / 输出格式 / 论文类型 / 分栏 |
| `step_models` / `step_efforts` / `model_preset_id` / `effort` | **按步骤**指定模型与推理强度 |
| `project_type` / `tech_frontend` / `tech_backend` / `tech_db` / `tech_lang` / `design_style` | 代码类模板（`dev-code`）的技术栈 |
| `software_name` / `software_version` / `case_name` | 软著 / 专利模板的元信息 |
| `custom_requirements` | 用户自定义要求，原文提示「这段要求会被注入到所有写作步骤的 prompt, Claude 会全程遵守」 |
| `problem_statement` | 赛题原文（会落盘为 `user_data/PROBLEM_STATEMENT.md`） |

`step_models` / `step_efforts` 与 `schema.sql:64-66`（"角色(executor/reviewer/editor_ai)与工作流每步通过引用 preset id 来复用同一组模型+key"）完全对应；引擎侧的解析优先级为 `params.step_models[skill] > params.model_preset_id` 与 `params.step_efforts[skill] > params.effort` `【直接提取】[证据: strings\services__workflow_engine...strings.txt:1856, 1918-1921]`。

**数据图"防雷同"机制**（与第 5 节视觉质量门互锁）`【直接提取】[证据: NewWorkflow-Ld6TEJjT.js，字符偏移 ≈34000–36000]`：

> 每篇论文按各自 ID 自动从下面 6 套版式里选一套（边框/刻度/网格/线宽），**同一篇内统一、不同篇各不相同**，配色也独立随机，最大程度降低雷同。

6 套版式为 `clean_open` / `framed_journal` / `soft_grid` / `minimal_bare` / `bold_edge` / `crisp_dark`；配色默认 5 色 `["#4477AA","#EE6677","#228833","#CCBB44","#AA3377"]`。另有 `style_preview` 与 `/api/style-preview?frame=&grid=&lw=&font=&legend=&bg=` 做**真实 matplotlib 渲染预览**（提示词自陈"此预览与出图跑同一份代码"）`[证据: 同文件 + 后端模块 services__style_preview / services__palette_preview / routers__style_preview / routers__palette_preview]`。

`【推断】` 该机制针对数模竞赛的**论文雷同判定**风险，属竞赛特化自研增补；同时说明视觉风格参数必须**在渲染时与预览时完全一致**（靠共用同一份绘图代码保证）。

**引擎侧的 CLAUDE.md 注入**：中文表格规则与计划指引是通过往 `CLAUDE.md` 追加带标记的块实现的 `【直接提取】[证据: strings\services__workflow_engine...strings.txt:1938-1943]`：

```python
with open(claude_md, "a") as f: f.write(text)
        _inject_once(claude_md, "INJECT_PLAN_GUIDANCE", notes_text)
"INJECT_DOCX_TABLE_RULES"
```

`【推断】` 这说明 Modex 保留了 ARIS 的 `CLAUDE.md` 机制作为"步骤内追加约束"的通道，把中文 docx 表格铁律（第 4.6 节）在**运行时**注入，而不是只靠 skill 正文里的静态提示词。

### 3.11 本节证据强度自评

| 结论 | 强度 | 依据 |
|---|---|---|
| 内置模板共 30 个（22 竞赛 + 5 学术 + 1 资产 + 2 软著/专利），另有 `paper_writing` 内部分支 | **强**（前端注册表逐条读取） | 3.1–3.4、3.7、3.8 |
| 中文竞赛统一六阶段编排 | **强**（`desc` 字段直接读取） | 3.2 |
| 存在 `_comp_zh_steps` / `_comp_en_steps` 双轨步骤表 | **强**（符号名）／步骤**内容未获取** | 3.3 |
| 华为杯是唯一机制不同的中文竞赛 | **强**（引擎 docstring 原文） | 3.6 |
| 页数上限为 `advisory_max`，不阻断生成 | **强**（引擎 docstring 原文） | 3.5 |
| CUMCM 专有 AI 使用声明合规校验 | **强**（前端校验文案 + 参数名） | 3.9 |
| `comp_*` 模板由 `comp-paper-zh` / `comp-code` 等 skill 包组合而成 | **中**（【推断】，两标识符 + 表结构互证） | 3.6 |
| `paper_from_assets` 的资产归置规则 | **强**（引擎字符串原文） | 3.4 |
| `step_models` / `step_efforts` 支持按步骤配模型 | **强**（前端参数 + 引擎解析优先级） | 3.10 |

**未获取项（诚实声明）**：`_comp_zh_steps()` / `_comp_en_steps()` 返回的**步骤清单全文与每步 `expected_outputs`** 未获取——它们是 Cython 编译函数，字符串表中只有函数名；`tmpl.sub_steps` 的实际内容随**加密 skill capsule** 分发（见 6.1）。本节的编排结论来自前端 `desc` 文案 + 引擎符号名 + `FIGURE_MANIFEST` / `AUTO-RECOVER` 片段的三方交叉，未作推测性填充。

---

## 4. 中文论文排版引擎

### 4.1 体系总览：13 个 JSON 分两层

C 组的三层结构 `【直接提取】[证据: 目录 E:\...\resources\app\tools\docx_style_profiles\]`：

| 层 | 文件 | 作用对象 |
|---|---|---|
| **正文样式 profile**（9 个） | `competition_zh.json`、`competition_en.json`、`default_cn_thesis.json`、`literature_review.json`、`course_paper.json`、`course_report.json`、`thesis_proposal.json`、`reference_paper_general.json` | 字号/字体/行距/边距/表格/公式/参考文献 |
| **封面 cover**（5 个，`covers\`） | `cumcm.json`、`huawei.json`、`mcm.json`、`default_zh.json`、`default_en.json` | 承诺书 + 标题页布局 |
| **写作契约**（B 组） | `docx_write_markdown.md`、`academic_docx_traps.md` | Markdown 结构合法性 |

`【推断】` profile 与 cover 正交组合：`competition_zh`（正文）+ `covers\cumcm`（封面）即为国赛论文的一整套排版。

### 4.2 核心规范：`competition_zh.json`（竞赛中文，必读）

`profile_name` 直白声明血缘：

> "profile_name": "数学建模竞赛中文论文样式（对标 cumcmthesis.cls）"

`【直接提取】[证据: docx_style_profiles\competition_zh.json:2]`

**完整参数表（逐项直接提取）**：

| 维度 | 参数 | 值 | 行号 |
|---|---|---|---|
| 页面 | size | `A4` | :4 |
| 页面 | margin_top/bottom/left/right_cm | 全部 `2.5` | :5-8 |
| 字体 | chinese_heading | `SimHei`（黑体） | :11 |
| 字体 | chinese_body | `SimSun`（宋体） | :12 |
| 字体 | latin | `Times New Roman` | :13 |
| 字体 | monospace | `Consolas` | :14 |
| 标题 | level1_pt / level2_pt / level3_pt / level4_pt | `15 / 14 / 12 / 11` | :17-20 |
| 标题 | bold | `true` | :21 |
| 标题 | level1_alignment | `center` | :22 |
| 标题 | level2/3_alignment | `left` | :23-24 |
| 标题 | level1/2/3_page_break_before | 全部 `false` | :25-27 |
| 正文 | font_size_pt | `12` | :30 |
| 正文 | line_spacing | `1.5` | :31 |
| 正文 | first_line_indent_chars | `2` | :32 |
| 正文 | space_before_pt / space_after_pt | `0 / 0` | :33-34 |
| 大标题 | font_size_pt / bold / alignment / font_family | `18` / `true` / `center` / `SimHei` | :37-40 |
| 大标题 | line_spacing / space_before_pt / space_after_pt | `1.15 / 12 / 6` | :41-43 |
| 表格 | top_border_pt / header_border_pt / bottom_border_pt | `1.5 / 0.75 / 1.5` | :46-48 |
| 表格 | font_size_pt / header_bold / cell_alignment | `10.5` / `true` / `center` | :49-51 |
| 参考文献 | hanging_indent_cm / font_size_pt / numbering_style | `0.74` / `10.5` / `bracket` | :54-56 |
| 图片 | max_width_cm / alignment | `14` / `center` | :59-60 |
| 代码块 | font_size_pt / line_spacing / background_color | `9` / `1.0` / `F5F5F5` | :63-65 |
| 摘要 | label_size_pt / body_size_pt / label_bold / label_alignment | `14` / `12` / `true` / `center` | :68-71 |
| 关键词 | label_size_pt / label_bold / font | `12` / `true` / `SimHei` | :74-76 |

`【直接提取】[证据: competition_zh.json:4-76，逐行如表中标注]`

**三线表参数解读**：`1.5 / 0.75 / 1.5`（pt）正是标准三线表"粗-细-粗"border 规格，与 B 组要求表格必有 `|---|---|` 分隔行形成"结构 + 渲染"双重保障 `【推断】`。

**参考文献 `numbering_style: "bracket"`** 对应提示词 `[1] 作者. 题名[J]. 期刊, 年, 卷(期): 页码.` 的著录格式 `[证据: docx_write_markdown.md:90]` `【直接提取】`。

### 4.3 profile 家族差异矩阵

`【直接提取】[证据: 各 JSON 对应行]`

| profile | 声明用途 | 一级标题 pt | 正文 pt | 行距 | 首页分页 | 图片最大宽 | 特殊 |
|---|---|---|---|---|---|---|---|
| `competition_zh` | 数学建模竞赛中文论文（对标 cumcmthesis.cls） | 15（centered） | 12 | 1.5 | 否 | 14 cm | 有 abstract/keywords 段 |
| `competition_en` | MCM/ICM 英文竞赛论文 | 14（**left**） | **11** | **1.15** | 否 | 14 cm | 首行缩进 **0**；title 用 Times New Roman 16pt |
| `default_cn_thesis` | 中文学术论文默认样式 | **18** | 12 | 1.5 | **是** | 14 cm | 无 abstract/keywords |
| `literature_review` | 文献综述样式 | 16 | 12 | 1.5 | 是 | 14 cm | — |
| `course_paper` | 课程论文样式 | 16 | 12 | **1.25** | 否 | **13 cm** | — |
| `course_report` | 课程报告样式 | 16（**left**） | 12 | **1.25** | 否 | **13 cm** | 代码块底色 `F2F2F2`（其余为 `F5F5F5`） |
| `thesis_proposal` | 开题报告样式（对标研究生院规范） | 16 | 12 | 1.5 | 否 | 14 cm | **margin_left_cm 3.0**（其余 2.5） |
| `reference_paper_general` | `general_paper_reference` | 14 | 12 | **1.28** | — | 14 cm | 带 `color_rgb` 与 `_derivation_note` |

`【直接提取】[证据: competition_zh.json:17,30,31; competition_en.json:17,30,31,32,22,40; default_cn_thesis.json:17,24; literature_review.json:17; course_paper.json:17,30,55; course_report.json:21,30,61; thesis_proposal.json:7,17; reference_paper_general.json:27,42,81]`

`【推断】` 全部中文 profile 共用同一"骨架常量"：A4 + 2.5 cm 四边距 + SimHei 标题 / SimSun 正文 / Times New Roman 西文 + 三线表 `1.5/0.75/1.5` + 参考文献悬挂缩进 `0.74 cm` + 图片居中。差异只落在**级别字号、行距、分页、图宽**四个维度上。`【推断】` 这意味着引擎的渲染逻辑是共享的，profile 是纯数据。

**英文 profile 的关键差异** `【推断】`：`competition_en` 把首行缩进设为 `0`、行距压到 `1.15`、正文降到 `11pt`、一级标题改左对齐——这是 MCM/ICM 英文论文的排版惯例，与中文竞赛相反。说明产品对"中文论文"和"英文论文"做了显式分离，不是简单复用。

### 4.4 封面规范：承诺书与标题页

**国赛 CUMCM** `【直接提取】[证据: covers\cumcm.json:2,5,9-21,24-33]`：

> "_comment": "国赛 CUMCM 封面布局（对标 cumcmthesis.cls 的承诺书风格 + 标题）"
> "title": "承诺书",  "title_size_pt": 18,  "title_alignment": "center"

承诺书正文逐字内嵌（`body_text`）：

> 我们仔细阅读了《全国大学生数学建模竞赛章程》和《全国大学生数学建模竞赛参赛规则》，完全明白在竞赛开始后参赛队员不能以任何方式（包括电话、电子邮件、网上咨询等）与队外的任何人（包括指导教师）研究、讨论与赛题有关的问题。
> 我们以中国大学生名誉和诚信郑重承诺，严格遵守竞赛规则，以保证竞赛的公正、公平性。如有违反竞赛规则的行为，我们将受到严肃处理。
> 我们授权全国大学生数学建模竞赛组委会，可将我们的论文以任何形式进行公开展示（包括进行网上公示，在书籍、期刊和其他媒体进行正式或非正式发表等）。

`【直接提取】[证据: covers\cumcm.json:9]`

表单字段（`form_fields`，`form_underline_size_pt: 14`）：题号（`从A/B/C/D中选择一项填写`）/ 报名号 / 学校全名 / 队员 1-3（打印并签名）/ 指导教师或指导教师组负责人 / 声明行（`key: null`，即纯文本行）/ 日期（`"format": "{year}年{month}月{day}日"`）`[证据: covers\cumcm.json:11-21]`

标题页：`title_size_pt: 22`、`title_font: SimHei`、`subtitle_text: "题目"`、`subtitle_size_pt: 16` `[证据: covers\cumcm.json:26-31]`

`【推断】` 承诺书原文硬编码在 JSON 里，说明产品把"合规文本不得改写"当作硬约束——LLM 无法篡改承诺书内容。

**华为杯（研赛）** `【直接提取】[证据: covers\huawei.json:2,5,9,11-19,25-27,32-44]`：

> "_comment": "华为杯研究生数学建模封面布局（对标 gmcmthesis.cls）"
> "title": "参赛承诺书"

承诺书正文：`我们认真阅读了《华为杯》第X届中国研究生数学建模竞赛章程和参赛规则，承诺严格遵守，并保证以诚信原则参赛，所提交论文为我们的原创工作，未抄袭、剽窃他人成果。` `[证据: covers\huawei.json:9]`

字段含 `指导教师` 与 `日期` `[证据: covers\huawei.json:17-18]`（CUMCM 无独立"日期"以外差异；华为杯多"指导教师"作为常规字段）。

**华为杯特有：信息以二列表格呈现** `【直接提取】[证据: covers\huawei.json:33]`：

> "_comment": "华为杯特色：信息以二列表格呈现"
> "border_style": "Xhline", "size_pt": 14, "bold": true

`【推断】` `border_style: "Xhline"` 是 LaTeX `booktabs` 的 `\Xhline` 方言（源自 `gmcmthesis.cls`），说明这个 JSON schema 是从 LaTeX 类文件反向映射来的，而非为 Word 原生设计。

另含 `show_logo: true` / `logo_path: "logo.pdf"` / `show_decoration: true` / `decoration_path: "title.pdf"` `[证据: covers\huawei.json:24-27]` —— 封面需要外部 logo 与装饰图资源。

**MCM/ICM 美赛** `【直接提取】[证据: covers\mcm.json:2,7-13,15-24]`：

> "_comment": "MCM/ICM 美赛封面布局（无承诺书，COMAP 风格）"
> {"text": "For office use only", "alignment": "left", "size_pt": 10},
> {"text": "T1 ________________", ...}

`form_block` 含 `"Team Control Number"` 标题与 `Team Control Number:` / `Problem Chosen:` 两个字段（14pt，bold）；`year_line.text_template` 为 `"{year}\nMathematical Contest in Modeling (MCM/ICM)\nSummary Sheet"` `[证据: covers\mcm.json:19-24]`。

`【推断】` 美赛用 `Summary Sheet` 概念（对应中文赛制的"摘要页"），且 `preface: null`（无承诺书），确认产品对不同赛事的合规差异做了建模。

**兜底封面**：`covers\default_zh.json` 自述 `"通用中文竞赛封面（无 LaTeX 模板对照时的兜底）"`，`"preface": null`，`info_lines` 为 题号/参赛队号/学校/队员/指导教师/日期 六行 `[证据: covers\default_zh.json:2,4,11-18]`。`covers\default_en.json` 为 `"通用英文竞赛封面"`，六行 `Problem/Team #/Affiliation/Members/Advisor/Date` `[证据: covers\default_en.json:2,11-15]`。

### 4.5 从参考论文反推排版：`derive_reference_from_docx.py`

**工具定位（原文 docstring）** `【直接提取】[证据: derive_reference_from_docx.py:2-17]`：

> 从一份完整的 .docx 论文派生通用参考资料（不是模板，不是 profile）。
>
> 输入：一份完整的论文 .docx（如外部提供的优质参考论文）
> 输出：
>   1. reference_paper_general.json — 结构化样式参考（字号/字体/对齐/颜色/边距/行距/首行缩进）
>   2. reference_structure_general.md — 人类可读 + LLM 友好的「格式自检对照表」
>
> 派生时做"通用化"：
>   - 字号、字体、颜色、对齐、边距、行距、首行缩进 → 保留（通用规范）
>   - 章节大纲 → 抽取通用骨架（去掉具体题目/问题/内容），归一为 "标题/摘要/关键词/正文章节/参考文献/附录"
>   - 题注格式 → 抽取范式（"图 X：xxx" / "表 X：xxx" 等）
>   - 公式编号格式 → 抽取范式（(N) / \tag{} / X.Y 等）
>   - Bold 使用模式 → 抽取通用规则（关键词标签加粗、章节标题加粗、首行术语加粗）

**四段式提取流水线** `【直接提取】[证据: derive_reference_from_docx.py:101,113,149,199,213,241,263]`：

1. **页面布局**（:101-111）：从 `doc.sections[0]` 读 `page_width/height` 与四边距，EMU → cm（`_emu_to_cm`：`emu / 360000`，:44-46）
2. **样式属性**（:113-147）：只关心 `Heading 1-6 / Title / Normal / Caption / Subtitle`（:120-125），读 `font.name/size/bold/italic/color.rgb` 与段落 `alignment/line_spacing/first_line_indent/space_before/space_after`
3. **实测段落级 run 属性**（:149-197）—— 这是最关键的工程决策，源码注释原文：

> # ========== 3. 实测段落级 run 属性（fallback：很多模板的样式只是占位，真实属性在 run 上） ==========
> # 思路：扫描所有段落，按 style 分组，统计 run 的实际字号/字体/颜色/加粗的"众数"

`【直接提取】[证据: derive_reference_from_docx.py:149-150]`

实现上对每个 style 名维护四个 `Counter`（`size_pt` / `font_name` / `color` / `bold_ratio`），取 `most_common(1)[0][0]` 作为众数（:186-197）。`【推断】` 这是对 Word 文档"样式定义与实际渲染不一致"这一真实工程问题的针对性解法——大量中文模板的 `Normal` 样式是空壳，真实字号写在每个 run 上。

`build_general_profile` 中优先级明确为**实测众数 > style 定义 > 硬编码 fallback** `【直接提取】[证据: derive_reference_from_docx.py:361-381]`：

```python
def _style_size(name: str, fallback: float) -> float:
    # 优先实测的众数，其次 styles
    if name in measured and "size_pt_mode" in measured[name]:
        return measured[name]["size_pt_mode"]
    if name in styles and styles[name].get("size_pt"):
        return styles[name]["size_pt"]
    return fallback
```

4. **章节大纲通用化**（:199-211, 292-332）：`_genericize_outline` 用 `SLOT_RULES` 把竞赛章节正则映射到通用槽位 `【直接提取】[证据: derive_reference_from_docx.py:299-311]`：

```python
SLOT_RULES = [
    (r"摘\s*要|Abstract", "abstract"),
    (r"关键词|Keywords", "keywords"),
    (r"^问题重述|^引言|^Introduction|^绪论|^一、|^1\s+(?:引言|背景|绪论)", "intro"),
    (r"^问题分析|^背景分析|^二、", "analysis"),
    (r"^.{0,4}假设|^.{0,4}符号说明|^术语|^Notation|^三、", "assumptions"),
    (r"^模型(?:建立|构建)|^方法|^Method|^理论|^四、", "methodology"),
    (r"^(?:模型)?求解|^计算结果|^实验结果|^数值结果|^Results|^五、", "experiments"),
    (r"^结论|^总结|^Conclusion", "conclusion"),
    (r"^参考文献|^References|^Bibliography", "references"),
    (r"^附录|^Appendix", "appendix"),
    (r"^致谢|^Acknowledg", "acknowledgement"),
]
```

规则细节：`第一个 H1 视为「论文题目」（slot=title），不参与槽位匹配`（:296-297），且"**H2 级别才尝试匹配槽位（深层级一律 section）**"（:322）`【直接提取】`。

`【推断】` 这组规则是**数模竞赛特化**的直接证据：`问题重述 / 问题分析 / 模型假设与符号说明 / 模型建立 / 求解结果 / 附录` 这套槽位正是国赛论文的标准骨架，通用 ML 论文不会有"问题重述"。

5. **题注与公式编号范式**（:213-239）：
   - 题注识别 `_is_caption_text` 走启发式而非依赖 `style.caption`（:63）：匹配 `^(?:图|表|Figure|Fig\.?|Table|Tab\.?)\s*[\dA-Za-z]...` （:68-71）
   - 脱敏 `_generalize_caption`：保留"前缀 + 编号 + 分隔符"，正文替换为 `" ……（具体说明文字）"`（:335-348）
   - 公式编号风格三选一：`trailing_paren`（`$$ ... $$ (1)`）/ `inline_tag`（`\tag{1}`）/ `standalone_paren`（独立成行的 `(N)`）`[证据: :79-90, 219-229]`
6. **加粗使用模式**（:241-261）：只收集长度 < 30 且有结构特征的 bold run，正则限定为标签词与章节序号 `【直接提取】[证据: derive_reference_from_docx.py:248-251]`：

```python
m_label = re.match(
    r"^(关键词|Key\s*words|Keywords|假设|引理|定理|命题|证明|算法|步骤|备注|注)([一二三四五六七八九十\d]*)\s*[：:]?\s*$",
    t,
)
```
输出形如 `关键词：（结构化标签）`、`第X章（章节序号）`（:255, 259）。

7. **表格使用**（:263-273）：统计 `len(doc.tables)`，并采样首表 `row_count / col_count / has_header_style`。

**产物的自我定位（关键，勿误读）**：

> "此 profile 派生自一份完整论文样本，仅作为 LLM 自检对照参考使用。不参与渲染、不当模板。具体的字号字体由参考论文实测得出，章节大纲与具体内容已被剥离，保留通用骨架。"

`【直接提取】[证据: reference_paper_general.json:81；同一段字符串亦生成于 derive_reference_from_docx.py:460-464]`

生成的 Markdown 对照表标题为 `# 论文 Markdown 格式自检对照表（通用参考）`，并声明 `此文件仅作为 docx-format-check 步骤的**自检对照参考**，不参与渲染、不当模板` `[证据: derive_reference_from_docx.py:527-531]`。

`【推断】` 这是产品设计上的一条清晰边界：**参考论文派生结果不进入渲染管线**，只作为 LLM 自检的"参照物"。真正的渲染参数永远来自固定 profile（3.2/3.3）。这避免了"参考论文格式污染输出"的风险，也说明 `reference_paper_general.json` 与实际导出效果无直接因果关系。

对照表内含"标题层级与字号"表与铁律 `【直接提取】[证据: derive_reference_from_docx.py:546-554]`：

> ⛔ **铁律：标题必须用 `#` 开头**，禁止用 `- 章节名`（list 项）伪装标题，否则 docx 引擎会渲染成"• 章节名"。

以及骨架警告 `⛔ **不要照搬"问题一/问题二"等竞赛特定章节**` `[证据: derive_reference_from_docx.py:564]`。

**章节骨架输出的去重策略** `【直接提取】[证据: derive_reference_from_docx.py:478-494]`：非 section 槽位只保留首次出现；section 槽位不去重但"限制每级最多展示 2 条作为示意"。骨架最多输出 25 行（:561），槽位中文标签表见 :497-511（`title→论文题目`、`assumptions→模型假设与符号说明`、`methodology→模型建立` 等）。

### 4.6 写作契约：`docx_write_markdown.md` 与 `academic_docx_traps.md`

两份提示词是"Markdown → docx"的**唯一合法输入约定**。要点已逐条列于第 2.8 / 2.9 节，此处只归纳其规范体系：

| 维度 | 契约要点 | 证据 |
|---|---|---|
| 标题 | `#` 题目（唯一）、`## 摘要`、`## 一、章节名`、`### 1.1`、`#### 1.1.1`；标题禁用 `- ` 列表项 | `docx_write_markdown.md:13-21` |
| 关键词 | `**关键词**：xxx`，冒号必须在 `**` 外 | `docx_write_markdown.md:24-28` |
| 公式 | 行内单 `$`、块级 `$$` 独占行、编号 `\tag{n}` 同行、按序连续编号、半角括号 | `docx_write_markdown.md:48-51`；`academic_docx_traps.md:22-33` |
| 表格 | 直接 `cat figures/TABLE_*.md >> paper/main.md`，禁止手抄数字 | `docx_write_markdown.md:54-58`；`course_docx_table_md.md:6,37` |
| 图片 | `![图 X 说明](figures/fig_xxx.png)`，必须 PNG | `docx_write_markdown.md:61-62` |
| 图题 | **≤ 15 个中文字符 / ≤ 10 个英文词**；**禁止公式**；编号与标题用空格分隔（非冒号）；详细说明移到正文 | `docx_write_markdown.md:66-71`；`academic_docx_traps.md:56-61` |
| 参考文献 | 上标 `[1] [2,3] [4-6]`；著录 `[1] 作者. 题名[J]. 期刊, 年, 卷(期): 页码.`；禁用 `\cite{}` | `docx_write_markdown.md:89-91` |
| 代码 | ≥3 行必须 fenced，` ``` ` 成对，禁止行内单反引号串接 | `academic_docx_traps.md:5-15` |
| 噪声 | 禁整段加粗、禁 HTML 块、禁 `&nbsp;`、禁残留 `\\` | `academic_docx_traps.md:71-74` |

**图题禁令的机理（原文，去 AI 味的关键论述）** `【直接提取】[证据: academic_docx_traps.md:63-65]`：

> **为什么 Markdown 模式特别敏感？**
> LaTeX 的 `\caption{}` 会自动渲染 `$Q_t$` 为公式（PDF 能看见 Q 下标 t）；但 Word 引擎对图题（alt 文字）走纯文本路径，
> `$Q_t$` 会**原样显示成 `$Q_t$` 字符串**。所以图题里**绝对不要写公式**——把变量描述移到正文：

长度限制的对照示例 `[证据: academic_docx_traps.md:58]`：✅ `残差诊断四联图` / ❌ `Wiener 过程模型残差诊断。(a) Q-Q 图...(b) 残差 vs 拟合值...`；✅ `图 4-11 残差诊断` / ❌ `图 4-11：残差诊断` `[证据: academic_docx_traps.md:61]`

`【推断】` 图题"≤15 汉字 + 禁公式 + 禁冒号"三件套是**为 Word 纯文本渲染路径专门设计**的，LaTeX 模式无此必要。这证明产品同时维护 PDF(LaTeX) 与 Word(Markdown) 两条成文路径，且 Word 路径的约束更严。

**明确的职责边界** `【直接提取】[证据: docx_write_markdown.md:6, 99-100]`：`字号、字体、页边距、行距等格式由引擎按工作流 profile 自动应用，你只需要写好 markdown 内容`；`本 prompt 只约束"格式（结构性）"，不约束"内容"`。

**内容层面的唯一约束**：`每个 figures/TABLE_*.md 都要嵌入正文，一张都不能漏` `[证据: docx_write_markdown.md:58]`、`figures/ 中已有的图（必须全部嵌入 paper/main.md）` `[证据: docx_write_markdown.md:93-94]`。

### 4.7 渲染引擎实现：**明文可读**（修正前次"未获取"的判断）

> ⚠️ **重要修正**：前次报告 7.2 节与 6.3 节把"docx 渲染器内部实现"列为**未获取**，依据是 `docx_export.cp311-win_amd64.pyd` 只泄漏极少量中文串。本次复核发现该判断**有误**：真正的 Markdown→docx 渲染器是 `resources\app\tools\docx-cn-engine\` 下的**明文 Node.js 源码**（非编译产物），可直接通读。这是本产品**可复现价值最高、且技术门槛最容易被低估**的工程资产。

**引擎构成（明文，逐文件）** `【直接提取】[证据: resources\app\tools\docx-cn-engine\ 目录]`：

| 文件 | 规模 | 职责（原文自述） |
|---|---|---|
| `md_to_docx.js` | 57,358 B / 1,366 行 | **主渲染器**：Markdown → .docx |
| `new_doc.js` | 39,052 B | 早期/模板化生成器（含 STYLES / NUMBERING 配置、目录 TOC、自动编号） |
| `mathml-to-docx.js` | 9,576 B | MathML → docx Math 子节点转换 |
| `latex_to_omml.js` | 3,144 B | LaTeX 批量 → OMML XML 片段 |
| `omml_helper.pyc` | 10,092 B | Python 侧 OMML 辅助（**仅此文件是编译产物**） |
| `package.json` | 106 B | 依赖：`docx ^9.6.1`、`fast-xml-parser ^5.7.3`、`temml ^0.13.2` |

`【直接提取】[证据: docx-cn-engine\package.json:2-6]`

**公式链路（原文注释逐字）** `【直接提取】[证据: docx-cn-engine\latex_to_omml.js:1-10]`：

> `latex_to_omml.js — 批量把 LaTeX 公式转成 OMML(<m:oMath>) XML 片段`
> `复用竞赛公式链：temml(LaTeX→MathML) → mathmlToDocxChildren(→docx Math) →`
> `打包成一个临时 docx → 解 zip 取 word/document.xml → 顺序抽出每个 <m:oMath>。`

实现三步（`:29-47`）：① `temml.renderToString(latex, {displayMode, throwOnError:false})` → ② `mathmlToDocxChildren(mathml)` → ③ `Packer.toBuffer` 打出临时 docx，用 `JSZip` 解包读 `word/document.xml`，再用正则 `/<m:oMath\b[\s\S]*?<\/m:oMath>/g` **按顺序抽回每个 OMML 片段**（`:41-47`）。

**失败回退策略** `【直接提取】[证据: latex_to_omml.js:34-38]`：

```javascript
} catch (e) {
    // 落到下面回退
}
return new DocxMath({ children: [new MathRun(latex)] });
```

`【推断】` 公式转换失败时**回退为原文文本**（`MathRun(latex)`），不抛错、不中断文档生成——这是"宁可显示 LaTeX 源码也不丢公式"的取舍，与 4.6 节"图题禁公式"的动机一致（都承认 Word 路径对 LaTeX 的支持有限）。

**"一行一公式独占段落"的顺序保证** `【直接提取】[证据: latex_to_omml.js:61-64]`：

> `// 每条公式独占一个段落，保证 document.xml 里 <m:oMath> 顺序 == 输入顺序`

`【推断】` 这是一个**易被忽略但关键**的实现约束：OMML 抽取靠**位置索引**回填，因此必须保证"输入顺序 == 输出顺序"，否则公式会串位。复现时必须照此实现。

**主渲染器要点** `【直接提取】[证据: docx-cn-engine\md_to_docx.js，行号如下]`：

| 能力 | 实现位置 | 说明 |
|---|---|---|
| 默认 profile 常量 | :85-94 | 与 C 组 JSON **同构**（`page/fonts/body/headings/table/references/abstract/keywords/code_block`），证明 JSON 就是喂给它的 |
| `loadProfile` + `deepMerge` | :140-161 | 读 `--profile <json>` 后**深合并**覆盖默认值；缺 key 时回落默认 |
| CLI 参数 | :164-179 | `--source <md> --output <docx> [--workspace <dir>] [--profile <json>]` |
| 首行缩进换算 | :137 | `chars × sizePt × 20`（twips），即"2 字符"随字号缩放 |
| 摘要标题 | :777-778 | 注释原文：`摘要标题（居中、加粗，对标 cumcmthesis.cls：\zihao{4}\bfseries 摘要）` |
| 关键词段落 | :796-797 | 黑体加粗标签 + 正文内容 |
| 摘要内自动分段 | :897-900 | 处理"AI 把'针对问题一…针对问题二…'写在同一段"的违规，仅在摘要区生效 |
| 摘要正文加粗解析 | :318-341 | 与 Python 侧 `_add_runs_with_inline_bold` **对齐**（同样的 `.+?` 非贪婪切分） |
| 块级公式闭合判定 | :1010-1031 | `isBlockEndLine` / `extractTailLabel` 模块级函数；漏写结尾 `$$` 会被识别 |
| 公式编号提取 | :987-1020 | 注释原文：`尾巴用 (.*)$ 兜住而不限定编号形态`；旧版写死 `/\(\d+(?:\.\d+)?\)/` |
| 三线表 | :451-514 | `threeLineTable(headers, rows)`；cell 内 `$...$` 走 `parseInlineWithMath` 渲成 OMML |
| 中文弯引号 | :183-199 | ASCII 直引号→中文弯引号，**启发式**：引号内或外侧 80 字符内有中文才转，避免改到代码/英文 |
| 图片尺寸分档 | :649-659 | 注释原文：`按长宽比给"宽度上限"分档，【四档完全对齐 PDF 侧 fig_include_size.py】`；`r≤0.80 横图→0.85`、`0.80<r≤1.20 近方→0.70` |
| 双栏支持 | :123-134, :1265 | `profile.page.columns>=2` 时正文分栏；表宽/图宽锁到单栏栏宽 |
| 自检入口 | :1300-1305 | `selfTest()`，注释原文：`改动 isBlockEndLine / extractTailLabel 后必跑，防判据退化` |
| 原子写出 | :1289 | 先写 `.<uuid>.tmp` 再改名，避免半成品 docx |

`【推断】` 由 :104 的注释 `⛔ v1.4.3 修复：旧公式 mul * baseSize * 20 在 baseSize≠12 时把"倍数"算成绝对 twip` 可确认：该引擎**有独立版本号与修复历史**，是长期演进的**核心自研资产**，而非一次性脚本。

**图片尺寸与 PDF 侧对齐** `【直接提取】[证据: md_to_docx.js:649-659]` 说明存在一条隐含要求：**Word 路径与 LaTeX/PDF 路径的图宽分档规则必须一致**（`fig_include_size.py` 是 PDF 侧对应实现）。`【推断】` 这进一步证明产品维护双成文路径且刻意保持视觉一致。

**`new_doc.js` 的差异定位** `【直接提取】[证据: docx-cn-engine\new_doc.js:56-63, 396-432, 509-513]`：它使用 Word **原生域代码**做自动编号——`SequentialIdentifier`、`TableOfContents`、`PageBreak`，并有 `buildNumberingConfig(chapterCount)` 与按章重置的 `sections_c1/c2/...`。图题/表题用 `SEQ` 域自动编号（`:397-403`），参考文献注释自陈 `Helper: reference entry (GB/T 7714-2015)`（`:509-511`）。

`【推断】` `new_doc.js` 与 `md_to_docx.js` 的定位差异是：前者是**人工编辑的模板骨架**（内容段 `const CONTENT = [...]` 需手改，`:781-785` 注释 `██  CONTENT SECTION — Edit below this line`），后者是**由 AI 生成 Markdown 驱动的自动渲染器**。产品最终走的是后者；前者保留了 Word 原生自动编号/TOC 的实现参考，**对复现"目录与自动编号"功能有直接参考价值**。

**三线表 border 实现** `【直接提取】[证据: new_doc.js:56-58, 426-432]`：`THICK = {style: SINGLE, size: 12}` 标注为 `1.5 pt`；正文行边框必须设为 `NONE`（不能只是细线），仅保留表头上下线 + 末行下线。`【推断】` 这与 `competition_zh.json` 的 `top_border_pt:1.5 / header_border_pt:0.75 / bottom_border_pt:1.5` 完全对应，**数值来源与渲染实现互证**。

**能力边界（明文可查）**：
- 不支持 LaTeX 环境：`docx_write_markdown.md:10` 禁 `\documentclass`/`\begin{document}`/`\section{}`；`academic_docx_traps.md:37` 明言"docx 引擎不解析 LaTeX 环境"。
- 不支持 HTML：`academic_docx_traps.md:46,50,72` 禁 `<table>`/`<img>`/`<div>`。
- 不支持 PDF 图片：`course_docx_png_only.md:4` 明言"Word 不能嵌入 PDF"，须先转 PNG。
- 不支持表格 LaTeX：`course_docx_table_md.md:34-35` 禁 `\begin{table}`/`\toprule`/`\input{}`。
- 图题走**纯文本路径**：`academic_docx_traps.md:63-65` 说明 alt 文字不解析 `$...$`。
- `\\`/HTML 实体等 Markdown 噪声需上层拦截（`academic_docx_traps.md:71-74`）。

`【推断】` 这些边界**不是引擎的实现缺陷，而是被显式写进提示词的契约**——即产品选择"约束输入端"而非"增强渲染端"。对复现的含义：**只要遵守 4.6 节契约，`docx-cn-engine` 可近乎原样复用**；反之若让 AI 自由写 LaTeX，引擎不负责兜底。

`【推断】` **对红方的复现价值评估**：本节是全报告**投入产出比最高**的部分——`docx-cn-engine` 是明文、无混淆、依赖仅 3 个公开 npm 包（`docx` / `temml` / `fast-xml-parser`），且已包含 OMML 公式、三线表、中文弯引号、双栏、图片分档、摘要特殊路径等完整中文排版逻辑。配合 4.2–4.4 节的 13 个 profile JSON（纯数据），可**不经逆向**重建中文论文 Word 生成能力。前次报告因误判"渲染器未获取"而把此项列为最大工作量，应据本节**下调优先级/工作量估计**。

---

## 5. 质量门与自动校验

### 5.1 引擎层质量门（E 组 `workflow_engine` 中文串）

E 组已提取的 `workflow_engine.cp311-win_amd64.pyd` 共 81 条中文串，其中大量直接描述质量门语义。以下为**直接引用**（原文为准，未改写）：

**图表健康检查：静态版 / 动态版双轨** `【直接提取】[证据: cjk-strings-from-pyd.md:1007, 1009, 1043, 992-993]`：

| 条目 | 原文 |
|---|---|
| 静态版 | `图表步骤健康检查(静态版, 不依赖 files_created)。` |
| 动态版 | `对图表步骤做严格健康检查(动态版, 基于本步骤的文件增量)。` |
| 静态版退化口径 | `退化为「figures/ 下当前是否存在该步骤应有的图类」。` |
| 合法跳过例外 1 | `例外: figures/ 已有该步骤应有的「数据类」图 + 本步骤未新增任何文件` |
| 合法跳过例外 2 | `例外同上: figures/ 已有架构图 + 本步骤无新增` |

`【推断】` 双轨设计的动因是**崩溃恢复与 waiting_checkpoint 场景拿不到增量**——原文另有 `用于崩溃恢复 / waiting_checkpoint 等无法获取增量的场景。` `[证据: :1029]`。即：有增量时用严格动态判据防止"空跑冒充完成"，无增量时退化为静态存在性判据以免误杀。

**合法跳过语义（`ok=True` 的三种来源）** `【直接提取】[证据: cjk-strings-from-pyd.md:979, 1005, 1034]`：

> `ok=True: 步骤产出健康(有真实新增图 / 用户禁用 / 无图论文场景 / rerun-skip 合法跳过)`
> `合法跳过`
> `视为 rerun 时 SKILL 的「恢复检查」让 Claude 合法跳过, 放行`

`【推断】` 这是产品一个重要设计立场：**"跳过"是一个合法的成功态**，而非失败。四种合法来源为：真实新增、用户禁用、无图论文场景、rerun-skip。

**FIGURE_MANIFEST 权威归类** `【直接提取】[证据: cjk-strings-from-pyd.md:1018, 1004, 984, 996, 1013]`：

> `按 FIGURE_MANIFEST 的章节标题把图名归类(权威, 优先于文件名前缀)。`
> `只认 ** 粗体章节标题里的关键词, 不看图名前缀`
> `「关键词在中间」的架构图会误判, 仅作兜底)`
> `分类优先级:`
> `归属按「哪个步骤产出」决定, 与健康检查的步骤对账口径一致:`

`【推断】` 归类优先级链为：**FIGURE_MANIFEST 章节标题 > 文件名前缀**。源码注释明确承认文件名前缀法有已知缺陷（"关键词在中间"的架构图会误判），因此降级为兜底。同时"归属按哪个步骤产出决定"确保**健康检查与归属判定使用同一口径**，避免两套逻辑互相打架。

**产出计数口径** `【直接提取】[证据: cjk-strings-from-pyd.md:1024, 978, 970]`：

> `检查 names 中有多少个图已经实际产出 (任意 .png/.pdf/.drawio 都算)。`
> `Returns: (产出数, 缺失的名字列表)`
> `- 文件大小 > 50 字节 (防空文件占位)`

`【推断】` "任意 `.png/.pdf/.drawio` 都算"说明健康检查对**产出格式宽容**（Word 模式本应只留 PNG，但引擎层不因此判失败），而"50 字节防占位"是对空文件的防御。

**页数预检** `【直接提取】[证据: cjk-strings-from-pyd.md:1019, 1026, 976]`：

> `按竞赛页数语义做保守的正文字符预检。`
> `正文定义:`
> `- 800（含图表），英文`
> `- (纯文字综述/思辨论文场景)。`

`【推断】` `800（含图表），英文` 与 `(纯文字综述/思辨论文场景)` 是同一组字面量参数的两半：中文竞赛论文的页数语义换算为**正文字符预算**，且按"是否纯文字综述"区分下限。`【推断】` 关键的"保守"二字说明预检刻意设成**宁可漏报不可误报**，因为误判会触发无意义的自动返修。

**上下文压缩（防止输出被截断）** `【直接提取】[证据: cjk-strings-from-pyd.md:1031, 1003, 994, 972-973, 990]`：

> `空工具调用智能恢复：压缩 CLAUDE.md 中的图片描述和冗余内容，减少 prompt 大小。`
> `压缩策略：`
> `典型场景：paper-figure 步骤运行时上下文累积到 110K tokens，导致 Claude 输出被截断。`
> `1. 图片描述截断为摘要（每张图最多 100 字）`
> `2. 文档原文截断（每个文档最多 500 字）`
> `优先读取关键类型文件（md/tex/bib），并做字符预算。`

`【推断】` 这是一条**可量化**的上下文预算规则：图片描述 ≤100 字/张、文档原文 ≤500 字/个、触发阈值约 110K tokens。触发信号是"空工具调用"，说明产品把"模型输出被截断"识别为一个可观测的失败模式并给出确定性修复动作。

**其他相关质量门** `【直接提取】[证据: cjk-strings-from-pyd.md:1017, 1040, 1042, 991, 1033, 1001, 989, 1032, 1046]`：

| 原文 | 含义推断 |
|---|---|
| `把中文/空格/特殊字符替换成 ASCII 友好名字, 供 LaTeX includegraphics 安全引用。` | 图文件名规范化，避免 LaTeX 引用失败 |
| `返回中文竞赛通用步骤列表。` / `返回英文竞赛通用步骤列表。` | 中英文竞赛各有一套步骤模板 |
| `但万一 Claude 漏了某些文件, 这里做引擎层兜底, 确保:` | 引擎层兜底，不依赖模型自觉 |
| `获取该 skill 必须存在的二级文件列表.` | skill 完整性校验（配套 `skill_instruction_guard.py`，见 4.4） |
| `单个文件提取失败不应该让整个 workflow 失败.` | 故障隔离原则 |
| `任何异常都吞掉返回空串，绝不因为「记个快照」把执行搞崩。` | 观测代码不得影响主流程 |
| `绝不因为「设个思考强度」把执行搞崩` | 同上 |
| `避免重复追加同一段提示导致上下文污染。` | marker 去重注入 |

`【推断】` 上表前四条构成产品的"**引擎可靠性哲学**"：把模型的自觉当作不可依赖项，所有关键不变量在引擎层重新校验；同时所有非核心功能（快照、effort 解析）必须**失败静默**，绝不连带主流程崩溃。

### 5.2 暂停语义与恢复

`【直接提取】[证据: cjk-strings-from-pyd.md:1023, 1028, 1025, 977]`：

> `标记用户要求暂停。pause 接口调用，步骤循环每步开头检查。`
> `清除暂停标记。`
> `检查点续跑）都必须调用，否则工作流会在下一步立刻自杀、再也起不来。`
> `BaseException，一旦在这里被吞掉，用户点暂停就对整个 vision 阶段失效了。`

`【推断】` 最后一条是**反向约束**：通用的"异常一律吞掉"原则在此处被明确豁免——暂停信号必须能穿透 `BaseException`，否则暂停功能形同虚设。这体现了产品对"哪类错误可以吞、哪类绝对不能吞"有明确分级。

### 5.3 跨模型对抗式评审：`reviewer_client.py`

**工具定位（原文 docstring 首行）** `【直接提取】[证据: reviewer_client.py:2]`：

> `"""reviewer_client.py — 调用外部 LLM 进行评审（替代 Codex MCP）`

`【直接提取】[证据: reviewer_client.py:24, 135, 4-7]`：

> `    # 添加 system prompt`
> `    python reviewer_client.py --system "你是一个资深ML审稿人" --prompt "..."`
> `    REVIEWER_MODEL_ID   — 模型名，如 gpt-4o（可选，默认 gpt-4o）`
> `    OPENAI_API_KEY      — API Key（必填）`

**机制要点**：

| 机制 | 实现 | 证据 |
|---|---|---|
| 独立模型通道 | 走 OpenAI 兼容 Chat Completions，默认模型 `gpt-4o`，与环境变量 `REVIEWER_MODEL_ID` 解耦 | `:36-38, 135` |
| 多轮评审上下文持久化 | `--thread-file review_thread.json`，`load_thread` / `save_thread` 读写 JSON 数组，assistant 回复也回写 | `:20-21, 106-120, 181-183` |
| system prompt 仅在新会话注入 | `if not messages and args.system:` —— 已有历史时不重复注入 | `:166-168` |
| 三种 prompt 输入源 | `--prompt` / `--prompt-file` / stdin（`not sys.stdin.isatty()`） | `:144-153` |
| 超时 | 默认 `600` 秒 | `:37, 129` |
| TLS 强化 | `ctx.check_hostname = True`、`CERT_REQUIRED`、`minimum_version = TLSv1_2` | `:80-82` |
| Gateway 验签 | `from trusted_gateway_config import verified_tls_context` | `:31, 79` |
| 凭据分级路由 | `mxtp_` / `mxcp_` 前缀 → `local_model_proxy_url`；否则 → `api_url`，并尝试 `backend_loopback_url` | `:39-53` |
| 失败即退出 | 无 key / prompt 空 / API 异常均 `sys.exit(1)` 并输出中文错误 | `:137-140, 155-157, 176-178` |

`【推断】` "**替代 Codex MCP**"（:2）与"**跨模型**"两点结合，说明设计意图是让评审者与写作者使用**不同厂商/不同模型**，构成真正的对抗式评审而非自我复核。`REVIEWER_MODEL_ID` 环境变量令模型可替换，`--thread-file` 使"第一轮评审 → 修改 → 根据修改重新评审"成为标准工作流（:20-21 的用法示例即为此）。

**`paper_submission_contract` 中的返修预算教训** `【直接提取】[证据: cjk-strings-from-pyd.md:855-861]`：

> `也不能并进 ``checker_unavailable``：那个判定被多处用来决定"要不要返修"，`
> `修复：返修执行未成功"，模型无从下手，剩余返修预算白烧。契约里写明这是"未完成的`
> `操作"，不是"论文没通过检查"的证据。`
> `放宽它会把真实缺陷的自动返修一起压成 0 次（函数注释里记着这个教训）。`
> `诊断里只有"返修进程没正常结束"，没有任何内容问题。`
> `这种情形不能当成内容诊断发给模型`

`【推断】` 这揭示了一个**返修（auto-repair）预算**机制：论文校验失败后进入自动返修，返修次数有限（"剩余返修预算"）。核心教训是必须区分三类状态：① 检查器不可用（`checker_unavailable`）② 返修进程未正常结束 ③ 论文确实有内容缺陷。把 ②③ 混为一谈会"白烧预算"或"把真实缺陷的返修压成 0 次"。这是一条用真实事故换来的质量门设计规则。

### 5.4 TikZ 图视觉自检：`tikz_vision_check.py`

**机制（原文 docstring）** `【直接提取】[证据: tikz_vision_check.py:2, 11-14]`：

> `"""TikZ 图视觉自检 — 调 vision LLM 检查 TikZ 编译结果是否有重叠/截断等问题。`
> `退出码:`
> `  0 = 通过（PASS）`
> `  1 = 有问题（输出具体问题描述）`
> `  2 = API 不可用（未配置 key 或调用失败）`

**7 项检查提示词（原文）** `【直接提取】[证据: tikz_vision_check.py:29-43]`：

> 1. 文字是否被截断、重叠或超出节点边框？
> 2. 连线上的标注文字是否跟节点重叠或被遮挡？
> 3. 节点间距是否均匀，有没有挤在一起的？
> 4. 有没有大片空白区域（布局不紧凑）？
> 5. 箭头方向是否合理，有没有连线穿过节点？
> 6. 对齐是否整齐：本应竖直成一列的节点有没有明显左右错开？本应水平成一行的节点有没有明显上下参差？连线是否明显歪斜、没接在节点中央？并列节点大小是否明显不一？（只报肉眼一眼可见的错位，不必追究几像素的细微差别）
> 7. 整体是否美观、专业、适合放在学术论文中？
>
> 如果全部没问题，只回答一个词：PASS
> 如果有问题，逐条列出每个问题的具体位置和描述，格式：
> ISSUE 1: [位置] [问题描述]

`【直接提取】[证据: tikz_vision_check.py:39-42]`

**判决口径（本文件最有价值的一段工程教训）** `【直接提取】[证据: tikz_vision_check.py:46-61]`：

> `def _verdict(reply: str) -> int:`
> `    """把 vision 回复映射成退出码。对齐 drawio_vision 的口径：`
> `    vision 是「加分项」不是「硬门槛」——只在出现结构化 `ISSUE n:` 标记时才判 FAIL，`
> `    泛泛评论 / 无法解析 / 空回复一律放行(0)。`
> `    ⛔ 旧逻辑是「首行非纯 PASS 即 FAIL」，配合提示词里的主观项(大片空白/是否美观)，`
> `       几何图永远被挑出至少一条 → 每张烧满 2 轮重编，是「画完卡很久」的 vision 侧根因。`
> `    """`
> `    if not reply or not reply.strip():`
> `        return 0`
> `    if re.search(r"(?mi)^\s*ISSUE\s*\d*\s*[:：]", reply):`
> `        ...`
> `    return 0  # 含 PASS / 泛泛肯定 / 无法解析 → 保守放行，不阻塞`

`【推断】` 这里记录了一个完整的**失败模式 → 根因 → 修复**闭环：主观评价项（"大片空白""是否美观"）与"非 PASS 即 FAIL"的严格判决组合，导致几何图**必然**被判失败并触发 2 轮重新编译，表现为"画完卡很久"。修复方式是**只认结构化标记**（正则 `^\s*ISSUE\s*\d*\s*[:：]`），其余一律放行。这是"把主观 LLM 评审降级为非阻塞加分项"的典型工程取舍。

**图片体积防御** `【直接提取】[证据: tikz_vision_check.py:65-68]`：

> `"""读取图片→(base64, mime)。超过阈值时用 PIL 等比压缩，避免超 vision API 单图限制；`
> `PIL 缺失或压缩失败则回退原图。返回 None 表示无法读取（调用方据此跳过）。"""`
> `_MAX_IMG_BYTES = 3_500_000`

`【推断】` 注释给出换算依据："vision API 单图通常限制 ~5MB；base64 放大约 33%，原图阈值留到 3.5MB"。`返回 None 表示无法读取（调用方据此跳过）` 再次体现"校验失败不得阻塞主流程"原则。

**凭据优先级** `【直接提取】[证据: tikz_vision_check.py:7-9]`：`EDITOR_AI_API_KEY + EDITOR_AI_BASE_URL`（editor_ai 配置）优先，回退 `OPENAI_API_KEY + OPENAI_BASE_URL`（reviewer 配置）。

### 5.5 AI 生图的排版权重：`gpt_image.py`

中文生图提示词前缀（原文） `【直接提取】[证据: gpt_image.py:51-55]`：

> `ZH_LANG_PREFIX = (`
> `    "生成一张科研级别的学术论文插图。"`
> `    "字体不要出现乱码，确保生成简体中文可适配。"`
> `    "数学变量保持拉丁字母。\n\n"`

统一风格后缀与安全约束（原文）`【直接提取】[证据: gpt_image.py:65-72]`：

> `"\n\n图表上方不需要标题。白色背景，无水印无签名无装饰边框。"`
> `"配色自由搭配，丰富专业。4K分辨率。"`
> `"\n不要生成真人面孔或肖像照片，需要人物时用抽象图标代替。"`

`【推断】` "数学变量保持拉丁字母" 与 `paper_figure_lang_zh.md:10`（`只有变量符号、SI 单位、专有英文术语保留英文`）完全一致——**排版语言规则贯穿"程序化绘图"与"AI 生图"两条路径**，是统一的规范而非局部约定。

`build_prompt` 拼装顺序为 `prefix + user_prompt + UNIFIED_STYLE_SUFFIX + SAFETY_SUFFIX` `[证据: gpt_image.py:81]`，即模型只需写核心场景描述 `[证据: gpt_image.py:76]`。

### 5.6 文献检索的查证机制：`scholar_fetch.py`（仅结构）

`【直接提取】[证据: scholar_fetch.py:40-42, 52-53]`：`_USER_AGENT = "MHAgent-ScholarFetch/1.0 (academic research tool)"`、`_TIMEOUT = 15`、`_RATE_DELAY = 0.3  # 请求间隔（秒），避免被限流`、`_MAX_RETRIES = 3`、`_RETRY_DELAY = 1.0`。

**五源结构**（37 个函数中的检索后端）`【直接提取】[证据: scholar_fetch.py: 函数行号]`：

| 后端 | 函数 | 行号 |
|---|---|---|
| AMiner（主，中文） | `aminer_search` → `_aminer_free_search` / `_aminer_search_pro` / `_aminer_qa_search` / `_aminer_paper_detail` | :128/:189/:286/:348/:402 |
| Semantic Scholar | `semantic_scholar_search` / `semantic_scholar_by_id` | :469/:521 |
| CrossRef | `crossref_bibtex_by_doi` / `crossref_search` | :577/:592 |
| OpenAlex | `openalex_search` | :651 |
| DBLP | `dblp_search` / `dblp_bibtex` / `dblp_search_bibtex` | :707/:759/:779 |

**中文/英文分流 + 四级 fallback（原文 docstring）** `【直接提取】[证据: scholar_fetch.py:1011-1022]`：

> `"""智能获取 BibTeX：搜索论文 + 四级 fallback 获取 BibTeX。`
> `搜索策略：`
> `- 中文 query → AMiner 优先（中文学术最准），Semantic Scholar 补充`
> `- 英文 query → Semantic Scholar 优先（英文覆盖广），AMiner 补充`
> `- 两者结果合并去重（按 DOI 或标题相似度去重）`
> `- 内置 3 次重试机制`
> `BibTeX 获取优先级：DBLP → CrossRef DOI → 自动生成`
> `默认返回 10 篇论文。`

**中文兜底路径** `【直接提取】[证据: scholar_fetch.py:1034-1036]`：

> `# ⛔ AMiner 全失败兜底: CrossRef 也支持中文搜索 (修复 bug: AMiner 有时返空 / 网关挂)`

**去重口径** `【直接提取】[证据: scholar_fetch.py:1061-1063]`：`# 去重：按 DOI 或标题前 30 字符`，实现上分别构造 `existing_dois`（小写）与 `existing_titles`（前 30 字符小写）两个集合 `[证据: :1062-1063]`。

另有标题匹配打分与标签函数：`_compute_match_score`（:851）、`_match_label`（:920）、`_make_citation_key`（:821）、`_escape_bibtex`（:930）、`_generate_bibtex_from_metadata`（:939）。

`【推断】` `_compute_match_score` + `_match_label` 的存在说明产品对"检索结果是否真的是目标文献"做了**相似度把关**，而非直接把第一条当答案。这是防止 LLM 引用不存在的文献（幻觉引用）的机制性防线。

### 5.7 训练/下载看门狗：`watchdog.py`（与竞赛流程弱相关）

`【直接提取】[证据: watchdog.py:43-46]`：`DEFAULT_BASE = "/tmp/MH Agent-watchdog"`、`DEFAULT_INTERVAL = 60`、`SLOW_SPEED_THRESHOLD = 1 * 1024 * 1024  # 1 MB/s`、`GPU_IDLE_THRESHOLD = 5  # percent`。

函数集：`register_task` / `unregister_task` / `session_alive`（默认 `session_type="screen"`）/ `get_gpu_util` / `get_path_size` / `write_status` / `check_download` / `check_training` / `write_summary` / `run_watchdog` `[证据: watchdog.py:60-238]`。

`【推断】` 该工具面向 GPU 训练与大数据下载场景（`/tmp` 路径 + `screen` 会话），属 A 组模板同源的"ML 科研"血统，与数模竞赛主流程弱相关。`【推断】` 这也侧面印证了第 6 节的差分结论：产品保留了上游科研 agent 的基础设施，另加竞赛特化层。

### 5.8 skill 完整性守卫：`skill_instruction_guard.py`

**拦截的三类问题** `【直接提取】[证据: skill_instruction_guard.py:156-171, 177-179, 191-202]`：

1. **越权编辑（editor scope）**：`check_editor_scope(event, manifest)`，先于其他检查执行 `[:160-162]`
2. **危险运行命令**：`check_runtime_command(event)` `[:163-165]`
3. **`comp-code` 步骤禁止后台执行**（原文）`[:166-171]`：

> `return ('本步骤必须收齐计算结果后才能结束。请前台执行并设置合理超时；'`
> `        '若工具自动转后台，用 TaskOutput 等待最终退出状态与结果落盘，'`
> `        '不要再次启动同一个计算或结束回合等待唤醒。')`

4. **版本一致性守卫（原文）** `[:177-179]`：

> `reason = ('检测到非本轮版本的 Skill/运行材料。只使用本轮已注入的规则；'`
> `          '共享工具与参考资料请读取工作区 _utils/、_references/、_templates/。'`
> `          '不得搜索临时目录或旧安装目录中的替代 Skill。')`

触发条件包括：`Glob/Grep` 搜索 `skill.md` 且路径不是工作区 `[:185-187]`；`Bash` 命令中出现 `mh-cn` 路径段 `[:191-192]`；以及路径含 `skill.md` / `/skills/` / `_utils/` / `_references/` / `_templates/` 且不在本轮 manifest 中 `[:199-202]`。

`【推断】` 这条守卫的动机是**防止旧版本 skill 被复用**：工作区里存在 `_utils/`、`_references/`、`_templates/` 三个共享目录（与模板 `templates/` 对应），而 skill 本体必须来自本轮注入。`mh-cn` 是上游 skill 目录名 `【推测】`（证据仅为该字面量，未见目录本体）。


### 5.9 参赛精简导出（提交物边界）

`【直接提取】[证据: cjk-strings-from-pyd.md:1082, 1084, 1066, 1053]`：

> `构建导出 zip 文件（同步，在线程池中调用）。clean=True 为参赛精简版。`
> `精简导出：白名单式判断。先过通用规则（跳隐藏/缓存/日志等），再只放白名单顶层。`
> `判断文件是否应该包含在导出 zip 中。`
> `user_data 里的赛题原文（评委已有、非提交物）：赛题 PDF、提取文本、A/B/C 题文档。`

`【推断】` 最后一条是竞赛特化的**提交物边界判定**：`user_data/` 中的赛题原文（PDF、提取文本、A/B/C 题文档）被明确归类为"**评委已有、非提交物**"，因此不进入参赛导出包。这与 `skill_instruction_guard.py:172` 使用 `manifest['workspace']` 作为唯一可信根、以及 `cjk-strings-from-pyd.md:553-554`（`（user_data/ 在同一棵树下）`）形成一致的工作区布局认知。

`【推断】` 导出策略为**两段式白名单**：先过滤隐藏/缓存/日志类（通用规则），再只保留白名单顶层。这比"黑名单排除"更安全，与 5.1 节"黑名单不可穷举"的审计哲学（`cjk-strings-from-pyd.md:517`）一致——产品在多处统一采用了**白名单优先**。

---

## 6. ★ 上游 ARIS 差分

> 前置说明：血缘结论已在 F 组 `00-lineage.md` 完成论证（`.pyc` 原始路径 `D:\项目\Auto-claude-code-research-in-sleep-main\desktop\_tmp_backend`、运行时数据库名 `aris.db`、workflow 模板名与 ARIS skill 名机械对应）。**本节不重复论证血缘，只做方法论/skill 体系层面的差分**。上游仓库：https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep `[证据: 00-lineage.md:110]`；skill 总数 **83** `[证据: 00-lineage.md:112]`；分 10 个目录组 `[证据: aris-skills-catalog.md:21,44,62,74,82,99,114,134,148,167]`。

本节新增一条血缘旁证（本次分析新发现，F 组未记录）：

> `DRAWIO=$(command -v draw.io 2>/dev/null || echo 'D:/项目/Auto-claude-code-research-in-sleep-main/desktop/runtime/draw.io/draw.io.exe')`

`【直接提取】[证据: backend\services\prompts\course_docx_drawio_png.md:6]`

`【推断】` 这是**部署期明文分发文件**（非编译产物）中残留的上游原始绝对路径，与 `00-lineage.md` 证据 1 的 `.pyc` 路径前缀完全一致。相比 `.pyc`，明文 `.md` 更难辩解为"编译环境残留"，是更直接的证据。

### 6.1 (a) 直接继承 / 改名沿用

| # | Modex 产物 | ARIS 对应 | 关系 | 证据 |
|---|---|---|---|---|
| 1 | `templates/RESEARCH_BRIEF_TEMPLATE.md` | `/idea-discovery`（Workflow 1） | 直接继承（含非连续编号 1/1.5/2/3） | `00-lineage.md:89-104`；`aris-skills-catalog.md:28` |
| 2 | `templates/EXPERIMENT_PLAN_TEMPLATE.md` | `/experiment-bridge`（Workflow 1.5） | 直接继承 | `00-lineage.md:90`；`aris-skills-catalog.md:30` |
| 3 | `templates/NARRATIVE_REPORT_TEMPLATE.md` | `/paper-writing`（Workflow 3） | 直接继承 | `00-lineage.md:91`；`aris-skills-catalog.md:34` |
| 4 | `templates/IDEA_CANDIDATES_TEMPLATE.md` | `/idea-discovery` 产出物 | 直接继承 | `00-lineage.md:92` |
| 5 | `templates/EXPERIMENT_LOG_TEMPLATE.md` | `/experiment-bridge` 产出物 | 直接继承 | `00-lineage.md:93` |
| 6 | `templates/FINDINGS_TEMPLATE.md` | `/auto-review-loop` 产出物 | 直接继承 | `00-lineage.md:94` |
| 7 | `RESEARCH_CONTRACT_TEMPLATE.md`、`PAPER_PLAN_TEMPLATE.md` | `/paper-plan`（outline + claims-evidence matrix） | 沿袭（"claims-evidence matrix" 概念逐字对应） | `aris-skills-catalog.md:120` |
| 8 | `reviewer_client.py` | `/auto-review-loop-llm`（any OpenAI-compatible LLM via `llm-chat` MCP） | **改造沿用**：把 MCP 路径改为直连 HTTP | `reviewer_client.py:2`；`aris-skills-catalog.md:32` |
| 9 | `scholar_fetch.py` | `/research-lit`（multi-source + cross-source dedup） | 沿袭设计，实现为单一 Python 工具 | `aris-skills-catalog.md:50` |
| 10 | `watchdog.py` | `/monitor-experiment`（"Monitor running experiments, check progress, collect results"）、`/training-check`（"Periodically poll W&B metrics during training — catch NaN, loss divergence, idle GPUs early"） | 沿袭（工程化为 watchdog 脚本：`check_download` / `check_training` / `GPU_IDLE_THRESHOLD`） | `aris-skills-catalog.md:90, 96`；`watchdog.py:46,146,188` |
| 11 | `skill_instruction_guard.py`（版本一致性守卫） | `/meta-apply`（privileged landing gate，"read-only producer ≠ privileged applier"） | 概念沿袭（读→写权限分离） | `aris-skills-catalog.md:42` |

**关于第 8 条的深入对照（本次分析的核心增量判断）**：

Modex `reviewer_client.py:2` 自述 `调用外部 LLM 进行评审（替代 Codex MCP）`。而 ARIS 恰好提供**三个同族变体** `[证据: aris-skills-catalog.md:31-33]`：

| ARIS skill | 评审者通道 |
|---|---|
| `/auto-review-loop` | "uses Codex MCP reviewer" |
| `/auto-review-loop-llm` | "uses any OpenAI-compatible LLM via `llm-chat` MCP server" |
| `/auto-review-loop-minimax` | "Workflow 2 variant pinned to MiniMax API" |

`【直接提取】[证据: aris-skills-catalog.md:31-33]`

`【推断】` Modex 把 ARIS 的**三个 auto-review-loop 变体收敛为一个可切换模型的客户端**：`REVIEWER_MODEL_ID`（默认 `gpt-4o`）承担了 ARIS 中"三个独立 skill 目录"的职责，`--thread-file` 承担多轮评审循环。这解释了 `00-lineage.md:64` 为何把 `auto_review` 判为"族系沿袭"而非"直接沿袭"——蓝方做的是**三合一收敛**，不是照搬某一个。

**关于第 9 条的差分**：

ARIS `/research-lit` 的源清单为 `Zotero / Obsidian / local PDFs / web / arXiv / S2 / DeepXiv / Exa / Gemini / OpenAlex with cross-source dedup` `【直接提取】[证据: aris-skills-catalog.md:50]`。

Modex `scholar_fetch.py` 的源为 AMiner / Semantic Scholar / CrossRef / OpenAlex / DBLP `[证据: scholar_fetch.py:128,469,592,651,707]`。

`【推断】` 交集为 Semantic Scholar + OpenAlex；**Modex 独有的增补是 AMiner（中文源）+ DBLP（BibTeX 权威源）+ CrossRef**，而 ARIS 独有的 Zotero / Obsidian / local PDFs / DeepXiv / Exa / Gemini 在 Modex 该工具中**未见**（可能在加密 capsule 内的其他工具中，`【推测】`）。`BibTeX 获取优先级：DBLP → CrossRef DOI → 自动生成` `[证据: scholar_fetch.py:1019]` 是针对"防幻觉引用"的增补设计。

**ARIS 侧已存在的 CJK 能力（勿误判为蓝方原创）**：ARIS `/figure-spec` 的描述为 `Deterministic JSON → SVG renderer for architecture / workflow / pipeline / audit-cascade diagrams. Shape-aware edge clipping, self-loops, **CJK width estimation**` `【直接提取】[证据: aris-skills-catalog.md:123]`。

`【推断】` 上游已具备 CJK 宽度估算（用于图表排版），因此"中文排版"这一能力在 ARIS 中**不是空白**，但是在**论文正文 Word 排版**方向上确实是空白（见 5.2）。

**ARIS 的 venue 覆盖不含中文赛事（关键反证）**：ARIS `/paper-write` 支持 `ICLR / NeurIPS / ICML / IEEE / ACL / AAAI / CVPR / ACM MM` `[证据: aris-skills-catalog.md:121]`；`/writing-systems-papers` 面向 `OSDI / SOSP / ASPLOS / NSDI / EuroSys` `[证据: :131]`；`/grant-proposal` 覆盖 NSF / NSFC / KAKENHI / ERC / DFG `[证据: :132]`；`/paper-compile` 是 `Compile LaTeX paper to PDF` `[证据: :128]`；`/overleaf-sync` 为 LaTeX 同步。

`【推断】` **83 个 ARIS skill 中没有任何一个面向 CUMCM / MCM / 华为杯，也没有任何 Word/docx 成文链路**。这是 5.2 全部增补项的最强支撑。

### 6.1b 补强证据：上游身份字符串与 MCP 服务器清单（本次新增）

前次分析列出的血缘证据（`.pyc` 原始路径、`aris.db`）之外，本次又取得**两条更硬的证据**，且补全了 ARIS 的 skill/MCP 清单。

**证据 1：`arxiv_fetch.py` 的 docstring 与 User-Agent 里仍写着上游仓库地址** `【直接提取】[证据: pyc_dump\_index.json:5008, 5011]`

```
"CLI helper for searching and downloading arXiv papers.\n\nUsed by the ``arxiv``
 skill (skills/arxiv/SKILL.md).\n\nCommands\n--------\nsearch    Search arXiv and
 print results as JSON.\ndownload  Download a paper PDF by arXiv ID.\n..."
"arxiv-skill/1.0 (github.com/wanshuiyin/Auto-claude-code-research-in-sleep)"
```

`【推断】` 这条是本报告**最强的单点血缘证据**：
- docstring 自陈该工具"被 `arxiv` skill 使用"，且路径写作 `skills/arxiv/SKILL.md` —— 即 ARIS 的 Markdown-only skill 目录结构；
- **HTTP User-Agent 直接把 `github.com/wanshuiyin/Auto-claude-code-research-in-sleep` 发给 arXiv 服务器**，即上游身份在**运行时对外可见**，不是编译残留。若不复现这一字符串，任何"独立自研"的说法都难以成立。

**证据 2：`config.py` 的部署结构 docstring 自陈 skill 分发方式** `【直接提取】[证据: pyc_dump\_index.json:87]`

```
install_dir/
├── resources/app/          ← Electron asar 解压后的应用目录
│   ├── main.js
│   ├── backend/            ← Python 后端
│   ├── dist/               ← 前端构建产物
│   ├── tools/              ← 工具目录
│   └── templates/          ← 模板目录
│   （正式包不含 skills/；受保护 Skill 从签名 Capsule 获取）
...
用户数据目录（%APPDATA%/MHAgent/）：
    ├── db/aris.db
    └── workspaces/
```

`【推断】` 三个可直接用于复现的结论：
1. **正式安装包不含 `skills/` 目录**——已由本次实测确认：全盘检索本机安装目录，除 `runtime\python\Lib\site-packages\fastapi\.agents\skills\`（第三方库自带）外**没有任何 `SKILL.md`**。方法论本体 100% 走网络下发的**加密 capsule**。
2. 数据库文件名仍为 **`aris.db`**——品牌改名（ARIS → MH Agent / Modex）未覆盖到数据层，是又一处改名遗留。
3. `templates/` 是**唯一随包分发的明文方法论目录**——这正是本报告第 1、2 节的证据基座，也解释了为何模板是英文 ML 科研语境（原样继承）而其余中文层都在 capsule 里。

**证据 3：ARIS 的完整 skill 清单与 MCP 服务器清单（可用于对齐差分基线）** `【直接提取】[证据: reports\upstream-ARIS-cache.json，`fetched_at: 2026-10-01T20:57:52+0800`，`repo: wanshuiyin/Auto-claude-code-research-in-sleep`]`

该缓存给出 **83 个 skill** 名（与 `delta-aris-vs-modex.md:7` 一致），并额外给出 **Python 路径清单**，其中 MCP 服务器部分是理解 Modex 改造方向的关键：

```
mcp-servers/claude-review/server.py      mcp-servers/codex-exec/server.py
mcp-servers/codex-image2/server.py       mcp-servers/gemini-review/server.py
mcp-servers/llm-chat/server.py           mcp-servers/minimax-chat/server.py
mcp-servers/manual-review/server.py      mcp-servers/feishu-bridge/server.py
aris-monitor/focus.py  aris-monitor/scanner.py  aris-monitor/ticker.py  aris-monitor/widget.py
```

`【推断】` 三条对应关系由此坐实：
- ARIS 的评审能力原为 **8 个 MCP 服务器进程**（codex-exec / claude-review / gemini-review / llm-chat / minimax-chat / manual-review …）。Modex `reviewer_client.py:2` 自述"**替代 Codex MCP**"正是指把 `mcp-servers/codex-exec` 换成直连 HTTP 的自有客户端——5.1 节第 8 条的"改造沿用"判断得到 MCP 侧的直接支撑。
- Modex 中保留的 `generate_codex_claude_review_overrides.py` 文件名（`codex` + `claude` + `review`）与 ARIS 的 `codex-exec` / `claude-review` 两个 MCP 服务器同源 `【推断】[证据: pyc_dump\_index.json 的 orig_source_path 清单]`。
- ARIS 的 `aris-monitor/*.py`（focus/scanner/ticker/widget，即桌面挂件式监控）在 Modex 中**未保留**，取而代之的是 `watchdog.py`（服务端守护进程，见 5.7 节）与 Electron 前端——印证"上游的桌面监控能力被重写为商业产品形态" `【推断】`。

`【推断】` 综上，本次可把 5.1 节的措辞从"机械对应"升级为：**Modex 是 ARIS 的一个"产品化分叉"——方法论骨架、模板、工具脚本、MCP 设计均源自 ARIS；蓝方的工作集中在竞赛语义、中文 Word 排版、引擎质量门与商业化（账号/计费/胶囊分发/桌面壳）**。同时须重申：**83 个 ARIS skill 名在 Modex 编译产物中命中 0**，说明蓝方刻意做了**标识符改名**以切断可追溯性——但 `arxiv_fetch.py` 的 User-Agent 与 `config.py` 的 `aris.db` 两处遗漏了。

### 6.2 (b) 蓝方自研增补

#### B-1 数模竞赛特化（骨架层）

| 增补项 | 证据 |
|---|---|
| `comp_*` workflow 模板族 + `_comp_zh_steps()` / `_comp_en_steps()`（国赛中文 / 美赛英文两套步骤） | `00-lineage.md:59, 71-72` |
| `competition_zh.json` / `competition_en.json` 两套竞赛正文规范 | `docx_style_profiles\` |
| `covers\cumcm.json` / `huawei.json` / `mcm.json` 三赛事封面 + 中英文兜底封面 | `covers\` |
| 竞赛章节槽位规则（问题重述 / 问题分析 / 模型假设与符号说明 / 模型建立 / 求解结果 / 附录 / 致谢） | `derive_reference_from_docx.py:299-311, 497-511` |
| 竞赛页数语义的正文字符预检（保守） | `cjk-strings-from-pyd.md:1019` |
| `paper_submission_contract.py`（提交契约 + 返修预算语义） | `cjk-strings-from-pyd.md:853-861` |
| **参赛精简导出**（`clean=True` 白名单式导出） | `cjk-strings-from-pyd.md:1082, 1084` |
| 承诺书正文硬编码（国赛 / 华为杯），LLM 不可改写 | `covers\cumcm.json:9`；`covers\huawei.json:9` |
| 华为杯特有二列表格封面 + `Xhline` 边框 | `covers\huawei.json:33-44` |
| MCM/ICM `Summary Sheet` + `For office use only` 栏 | `covers\mcm.json:7-24` |
| `templates\` 中 `EXPERIMENT_PLAN` 等的 GPU/venue 语境被保留但新增中文竞赛 profile 覆盖 | 对比 `templates\*`（英文 ML）与 `docx_style_profiles\competition_zh.json` |

`【推断】` 蓝方在竞赛特化上的做法是**保留上游英文科研模板不动，另起一套旁路**（`comp_*` + `covers\` + `competition_*.json`），而非改写上游模板。对复现的含义：上游模板可原样取用，竞赛层必须自建。

#### B-2 中文排版（本次分析的主体增量）

13 个 `docx_style_profiles\*.json` + `derive_reference_from_docx.py` **在 ARIS 83 skill 中无任何对应物**（`delta-aris-vs-modex.md:9` 报告 83/83 skill 名在 Modex `.pyd` 中命中 0，反向亦无 "docx"/"style_profile" 类 skill）。

| 增补项 | 规模/内容 | 证据 |
|---|---|---|
| 8 个正文样式 profile | A4 / 2.5cm 边距 / SimHei+SimSun+Times New Roman / 三线表 1.5-0.75-1.5pt / 悬挂缩进 0.74cm | `docx_style_profiles\*.json` |
| 5 个封面规范 | 承诺书 + 标题页 + 表单字段 + logo/装饰资源 | `covers\*.json` |
| 从参考论文反推排版 | 四段式提取 + run 级众数实测 + 大纲通用化 + 题注/公式/加粗范式抽取 | `derive_reference_from_docx.py:2-17, 149-150, 299-311` |
| 中文写作契约 | 标题/关键词/公式/表格/图题/参考文献全套 Markdown 规则 | `docx_write_markdown.md:3-100` |
| docx 渲染陷阱清单（A–F 六类） | 含可执行的 grep 自检脚本 | `academic_docx_traps.md:4-99` |
| 图表中文语言规则 | axis/legend/annotate/caption 全中文，仅变量与 SI 单位保留英文 | `paper_figure_lang_zh.md:3-11`；`nature_figure_lang.md:3-8` |
| AI 生图中文适配 | "字体不要出现乱码，确保生成简体中文可适配" + "数学变量保持拉丁字母" | `gpt_image.py:51-55` |
| 图题去 AI 味铁律 | ≤15 中文字符 / ≤10 英文词、禁公式、空格代替冒号 | `docx_write_markdown.md:66-71`；`academic_docx_traps.md:56-61` |

`【推断】` `profile_name` 里"**对标 cumcmthesis.cls**"（`competition_zh.json:2`）与"**对标 gmcmthesis.cls**"（`covers\huawei.json:2`）是蓝方自陈的设计来源：这些 JSON 是把**公开 LaTeX 类文件**的参数翻译成 Word 渲染参数的结果。`border_style: "Xhline"`（`covers\huawei.json:41`）这一 LaTeX `booktabs` 方言直接暴露了翻译来源 `【推断】`。

#### B-3 docx / LaTeX 成文链路（护城河主体）

| 增补项 | ARIS 对应状态 | 证据 |
|---|---|---|
| **Word(.docx) 成文全链路**：Markdown → profile 套用 → .docx | ARIS 只有 `paper-compile`（LaTeX → PDF） | `aris-skills-catalog.md:128`；`docx_write_markdown.md:5-6` |
| `docx-export` / `docx-precheck` / `docx-format-check` 三步校验 | 无 | `academic_docx_traps.md:51,100`；`docx_tool_loader.py` 相关串 `cjk-strings-from-pyd.md:612-617` |
| **双模式分叉**（PDF/LaTeX 模式 vs Word/Markdown 模式），Word 模式约束更严 | 无（单一 LaTeX 路径） | `docx_write_markdown.md:3-10`；`course_docx_png_only.md:3-5`；`course_docx_table_md.md:3-4` |
| 用户上传 LaTeX 模板套件（`.tex/.cls/.sty/.bib`，最高优先级，不得替换） | 无（有 `/overleaf-sync` 但非模板套件注入） | `user_template_latex.md:3-11`；`aris-skills-catalog.md` 无对应项 |
| 图表仅在 Word 模式导 PNG + 350 DPI + 自动裁白边 + ≥50KB 清晰度门 | 无 | `course_docx_png_only.md:20,51`；`course_docx_drawio_png.md:10,35-59,81` |
| 表格"程序生成 .md，shell 直拼，禁止 LLM 誊抄数字" | 无（ARIS 为 LaTeX 表格） | `course_docx_table_md.md:6,37` |
| 参考论文派生"不进渲染管线，仅作 LLM 自检对照" | 无 | `reference_paper_general.json:81`；`derive_reference_from_docx.py:527-531` |
| 预览=实际出图（`style_preview` 加载真 `plot_utils`，不自行实现版式） | 无 | `cjk-strings-from-pyd.md:936-941` |

#### B-4 引擎层工程质量门（ARIS 为 markdown instruction，Modex 为编译进引擎的硬约束）

| 增补项 | 证据 |
|---|---|
| 图表健康检查静态版 / 动态版双轨 | `cjk-strings-from-pyd.md:1007, 1009, 1043` |
| FIGURE_MANIFEST 权威归类（优先于文件名前缀） | `cjk-strings-from-pyd.md:1018, 1004, 984, 1013` |
| 合法跳过语义（4 种 `ok=True` 来源） | `cjk-strings-from-pyd.md:979, 992-993, 1005, 1034` |
| 上下文压缩预算（图片 ≤100 字、文档 ≤500 字、~110K tokens 阈值） | `cjk-strings-from-pyd.md:972-973, 994, 1031` |
| 返修预算与三类状态区分（checker_unavailable / 返修未结束 / 真实内容缺陷） | `cjk-strings-from-pyd.md:855-861` |
| 引擎层兜底（"万一 Claude 漏了某些文件"） | `cjk-strings-from-pyd.md:991` |
| vision 自检降级为非阻塞加分项（只认 `ISSUE n:` 结构化标记） | `tikz_vision_check.py:46-61` |
| 工作区工具策略审计（黑名单不可穷举 → 每次起主会话对账实际工具清单） | `cjk-strings-from-pyd.md:517, 536, 540-542, 550-552` |
| skill 版本一致性守卫（禁止引用旧安装目录的替代 Skill） | `skill_instruction_guard.py:177-179, 191-192` |

`【推断】` 第 8 条是**安全性增补**：原文自陈 `【为什么要 audit()】黑名单是穷举的，CLI 升级加了新工具就会【无声漏进来】`、`实测：请求 7 个白名单工具，CLI 实际给了 27 个`、`实测（Phase 0）：不加它时，【工作区根目录的 .mcp.json 会被自动加载】` `[证据: cjk-strings-from-pyd.md:517, 535, 534]`。这与 ARIS 作为"用户自用的开源 skill 集"的威胁模型不同——Modex 是**多用户商业产品**，必须防止用户上传的 `.mcp.json` 或赛题原文被外发 `[证据: cjk-strings-from-pyd.md:547, 553-554]`。这属于商业化带来的增补，而非方法论增补。

### 6.3 差分结论

`【推断】` 汇总成一句话：**Modex 的方法论骨架继承自 ARIS（Workflow 1/1.5/2/3 的模板与 skill 名机械对应），蓝方的实质增量集中在三处——数模竞赛语义层、中文 Word 排版链路、以及把"软约束（markdown prompt）"编译成"硬约束（引擎质量门）"。** 上游 83 个 skill 中，`research-lit`、`auto-review-loop-llm`、`monitor-experiment`、`paper-plan`、`figure-spec` 等都能在 Modex 中找到改造后的对应实现；而 `docx_style_profiles`、`covers`、`docx_write_markdown`、`derive_reference_from_docx`、`paper_submission_contract` 在 ARIS 侧**完全无对应**。

`【直接提取】`（关键限制，直接引用勿再论证）：

> - 红方无法从本机安装包中直接提取 Modex 的 skill 正文；
> - 但**可以直接从开源上游 ARIS 取得同源的方法论骨架**，这是成本最低的复现路径；
> - 蓝方相对上游的增量主要在**工程化**（桌面壳、FastAPI 服务、工作流引擎、
>   中文 docx/LaTeX 排版、多模型账号与计费、加密 capsule 分发），而非方法论原创。

`[证据: 00-lineage.md:136-139]`

---

## 7. 对复现的建议

### 7.1 可直接从 ARIS 公开上游取用

| 项 | 理由 | 注意 |
|---|---|---|
| A 组 6 个 workflow 模板（BRIEF / CONTRACT / EXPERIMENT_PLAN / EXPERIMENT_LOG / FINDINGS / IDEA_CANDIDATES / NARRATIVE_REPORT / PAPER_PLAN） | 与 ARIS Workflow 1/1.5/2/3 逐字对应，非蓝方原创 | 需核实许可证 |
| `idea_discovery` / `experiment_bridge` / `auto_review` / `paper_writing` 四个 workflow 编排 | `00-lineage.md:63-64` 判为"直接沿袭/族系沿袭" | 同上 |
| 跨模型对抗式评审的**设计**（reviewer 用独立模型、多轮 thread、system prompt 仅首轮注入） | ARIS `/research-review`、`/kill-argument`、`/auto-review-loop-llm` 已给出模式 | 实现可自写，不必逆向 `reviewer_client.py` |
| 多源文献检索 + 跨源去重 + BibTeX 优先链 | ARIS `/research-lit`、`/semantic-scholar`、`/openalex` 等已有 skill 定义 | Modex 的 AMiner/DBLP 增补需自加 |
| LaTeX/PDF 成文链路（paper-plan → paper-figure → paper-write → paper-compile） | ARIS 完整覆盖 `aris-skills-catalog.md:114-132` | 若复现目标含中文竞赛，此链路**不充分**，需换 Word 路径或自建中文 `.cls` |
| 图表/示意图生成（mermaid / figure-spec / illustration） | ARIS 已有，且 `figure-spec` 自带 CJK 宽度估算 | — |
| 证据审计族（experiment-audit / paper-claim-audit / citation-audit / integrity-forensics） | ARIS 覆盖度高于 Modex 可见部分 | 这些是提升论文可信度的低成本高收益项，建议直接取用 |

`【推断】` 前两项的许可证问题必须先解决：`00-lineage.md:111` 明确提示"**复现前必须自行核实授权条款**"。

### 7.2 必须自研（ARIS 无对应物）

按"缺失程度 + 工作量"排序：

1. **Word/docx 渲染引擎**（最高优先级，也是最大工作量）
   - 输入 Markdown + profile JSON → 输出 .docx，需支持：标题层级映射、三线表、`\tag{}` 公式、图题纯文本路径、代码块底色、悬挂缩进参考文献
   - ~~`【推断】` 渲染逻辑本身是编译产物：`docx_export.cp311-win_amd64.pyd` 仅泄漏 1 条中文串（`按优先级解析源 Markdown 文件。`）`[证据: cjk-strings-from-pyd.md:610]`，`docx_tool_loader` 仅 4 条 `[证据: :612-617]`。**渲染器内部实现未获取**，只能依据 13 个 profile JSON 的 schema 与 B 组契约反推。~~
   - ⚠️ **本行结论已于本次更正，请以第 4.7 节为准**：上述判断**不成立**。`docx_export.cp311-win_amd64.pyd` 只是**编排层**（调用方）；真正做渲染的是 **明文** `resources\app\tools\docx-cn-engine\md_to_docx.js`（1,366 行）+ `mathml-to-docx.js` + `latex_to_omml.js`，依赖仅 `docx` / `temml` / `fast-xml-parser` 三个公开 npm 包 `[证据: 第 4.7 节]`。
   - `【推断】` 因此"Word/docx 渲染引擎"**不应列为必须自研项**，而应列为**可直接移植项**：核心算法与数据结构均已明文可读（OMML 抽取顺序保证、三线表 NONE 边框、首行缩进 `chars×pt×20`、图片四档宽度、中文弯引号启发式、摘要特殊路径）。剩余少量自研工作仅是**与工作流引擎对接的编排**（profile 选择与传参）。
   - 可复用上游：`python-docx`（Modex 自己也用，见 `derive_reference_from_docx.py:30`）

2. **13 个中文排版 profile 的数据**
   - 好消息：**参数来源是公开的**——`competition_zh.json:2` 自陈对标 `cumcmthesis.cls`，`covers\huawei.json:2` 自陈对标 `gmcmthesis.cls`。这两个 LaTeX 类文件是公开的，可直接从中提取字号/行距/边距/三线表规格。
   - `【推断】` 因此 profile 数据**不需要逆向**，只需按 `competition_zh.json` 的 JSON schema（`page/fonts/headings/body/title/table/references/image/code_block/abstract/keywords`）填充。

3. **封面规范的数据（承诺书全文与表单字段）**
   - `covers\cumcm.json:9` 与 `covers\huawei.json:9` 的承诺书正文来自竞赛官方章程与参赛规则，属**公开规则文本**，可直接从赛事官网取得；表单字段名可从 `covers\*.json` 的 `form_fields` 结构照抄。
   - `【推断】` 这一项是纯数据录入工作，无技术壁垒，但**必须逐字准确**（法律/合规文本）。

4. **从参考论文反推排版的工具**（`derive_reference_from_docx.py` 类功能）
   - 若需要"用户上传参考论文 → 自动对标格式"能力，需自研。核心技术点已在本报告 4.5 节完整给出，可直接照此实现：
     - run 级众数实测优先于样式定义（`derive_reference_from_docx.py:149-150, 186-197, 361-381`）
     - 四段式提取（页面 / 样式 / run 实测 / 大纲通用化 / 题注与公式范式 / 加粗模式 / 表格）
     - 竞赛槽位正则表（`derive_reference_from_docx.py:299-311`）
   - `【推断】` 该工具的**设计意图**比实现更重要：产物明确"不参与渲染、不当模板"，只作 LLM 自检对照 `[证据: reference_paper_general.json:81]`。复现时若让派生 profile 直接驱动渲染，会引入"格式随参考论文漂移"的缺陷。

5. **中文写作契约提示词**（`docx_write_markdown.md` + `academic_docx_traps.md`）
   - 内容已在本报告 2.8/2.9/4.4 节逐条摘录，可直接据此重写，无需逆向。
   - 高价值可复用资产：`academic_docx_traps.md:91-98` 的 6 行 grep 自检脚本可直接照搬。

6. **引擎层质量门**（5.1 节全部条目）
   - `【推断】` 这部分是 Modex 相对 ARIS 最实质的工程增量，但**每条规则的语义都已由 E 组中文串给出**（静态/动态双版、FIGURE_MANIFEST 优先级、4 种合法跳过、压缩预算数值、返修三类状态）。可据语义自行实现。
   - 优先级建议：合法跳过语义 > 图表健康检查 > 上下文压缩 > 返修预算 > 工具策略审计（后者是商业化需求，复现可缓）。

7. **赛题/资产安全边界**（`skill_instruction_guard.py` 类）
   - `【推断】` 若复现目标是自用，可省略；若对外提供多用户服务，则 5.8 节的三类拦截必须实现。

### 7.3 未获取 / 不可获取项（诚实声明）

| 项 | 状态 | 依据 |
|---|---|---|
| Modex 的 skill 正文（方法论本体） | **未获取**，被封装为加密 skill capsule（`capsule` 出现 93 次、`skill_crypto` 49 次，83 个 ARIS skill 名命中 0） | `00-lineage.md:121-133` |
| ~~docx 渲染引擎内部实现~~ | ⚠️ **本行已作废（判断有误）**：渲染器为**明文** `docx-cn-engine\md_to_docx.js` 等 4 个 JS 文件，**已获取**，详见第 4.7 节 | 前次依据 `cjk-strings-from-pyd.md:608-610` 判断，仅覆盖编排层 `docx_export.pyd`，漏查 `tools\docx-cn-engine\` |
| `new_doc.js`（Word 原生域代码自动编号/目录版）是否仍在产品链路中使用 | **未确定**：文件随包分发，但主链路证据指向 `md_to_docx.js` | 第 4.7 节 |
| `docx_style_profiles` 的字号取值论证过程（为何 15pt 而非 16pt） | **未获取**，仅有最终数值 | `competition_zh.json` 无溯源字段 |
| `_comp_zh_steps()` / `_comp_en_steps()` 返回的中英文竞赛步骤清单全文 | **未获取**，仅知函数存在与语义 | `00-lineage.md:71-72`；`cjk-strings-from-pyd.md:1040, 1042` |
| 图表健康检查的具体判据阈值 | **部分获取**：知有静态/动态双版与 4 种合法跳过，未见阈值数值 | `cjk-strings-from-pyd.md:1007, 1009` |
| `workflow_engine` 中"800（含图表），英文"的完整上下文 | **部分获取**，中文字符预算数值未在 E 组出现 | `cjk-strings-from-pyd.md:976, 1019` |
| `_fx` 目录内容 | 未纳入本次范围 | 任务限定 |

`【推测】` 关于"中文竞赛正文预检"的字符预算：E 组出现 `800（含图表），英文` 与 `(纯文字综述/思辨论文场景)` 两个片段，但中文侧的具体数值未出现。若需精确复现，建议以 CUMCM 官方页数要求（一般 20-25 页正文含图表）自行标定，不宜猜测 Modex 的原始数值。

---

## 附：本报告的证据强度自评

| 结论 | 强度 | 依据 |
|---|---|---|
| 模板层为英文 ML 科研血统，非数模竞赛血统 | 强（【直接提取】逐行引用） | 第 1.2 节 |
| 全流程为 9 阶段，每阶段有明确质量门 | 中（阶段划分为【推断】，质量门为【直接提取】） | 第 2 节 |
| 13 个 profile 共用骨架、差异仅在 4 个维度 | 强（逐项对比 13 个 JSON） | 第 4.3 节 |
| `derive_reference` 产物不进渲染管线 | 强（源码注释 + JSON 字段双证） | 第 4.5 节 |
| 图表健康检查为静态/动态双轨 | 中（仅中文串片段，无代码） | 第 5.1 节 |
| vision 自检被降级为非阻塞加分项 | 强（源码 docstring 完整记载根因） | 第 5.4 节 |
| Modex 收敛了 ARIS 三个 auto-review 变体 | 中（【推断】，两侧证据齐全但无直接对应声明） | 第 6.1 节 |
| 排版参数可从公开 `.cls` 反推 | 中（【推断】，依据 profile 自陈的"对标"关系） | 第 7.2 节 |
| **内置模板共 30 个，中文竞赛统一六阶段编排** | **强**（前端注册表逐条读取） | 第 3.1–3.2 节 |
| **华为杯是唯一机制不同的中文竞赛** | **强**（引擎 docstring 原文） | 第 3.6 节 |
| **CUMCM 专有 AI 使用声明合规校验** | **强**（前端校验文案 + 参数名） | 第 3.9 节 |
| **docx 渲染引擎为明文可读、可直接移植** | **强**（4 个 JS 源文件 + 3 个公开 npm 依赖） | 第 4.7 节 |
| **ARIS 血缘：上游 URL 仍在运行时 User-Agent 中** | **强**（`arxiv_fetch.py` 字符串，对外可见） | 第 6.1b 节 |
| **正式包不含 `skills/`，方法论本体走加密 capsule** | **强**（`config.py` docstring + 全盘检索无 `SKILL.md`） | 第 6.1b 节 |
| `comp_*` 模板由 `comp-paper-zh` / `comp-code` 等 skill 包组合而成 | 中（【推断】） | 第 3.6 节 |
| `_comp_zh_steps` / `_comp_en_steps` 的步骤清单全文 | **未获取**（Cython 函数名可见，内容随 capsule） | 第 3.3、3.11 节 |
| Modex 的 skill 正文（方法论本体） | **未获取**（加密 capsule；83 个 ARIS skill 名命中 0） | 第 6.1b、7.3 节 |

---

*报告结束（第二版）。全文结论均标注证据来源与强度；未获取项已在第 3.11、7.3 节列明，未作推测性填充。本次修订另更正了第一版关于"docx 渲染器未获取"的判断错误（见第 4.7 节）。*
