# Modex-MH-Agent 与上游 ARIS 的血缘鉴定

## 结论

**Modex-MH-Agent 是从开源项目 ARIS 的源码包衍生开发而来**，随后被改造为
闭源商业化的桌面产品（Electron + Cython 编译保护）。证据分四层，见下。

## 证据 1：编译产物里的原始源码路径（最硬的证据）

Python `.pyc` 的 code object 保存 `co_filename`，即编译时机器上的**原始绝对路径**。
Modex 的 `.pyc` 全部指向同一个目录：

```
D:\项目\Auto-claude-code-research-in-sleep-main\desktop\_tmp_backend\...
D:\项目\Auto-claude-code-research-in-sleep-main\desktop\_tmp_tools\...
```

`-main` 后缀正是 GitHub 仓库 zip 包解压后的默认目录名。

涉及文件（共 52 个 .pyc 泄漏了该路径）：

- `D:\项目\Auto-claude-code-research-in-sleep-main\desktop\_tmp_backend\config.py`
- `D:\项目\Auto-claude-code-research-in-sleep-main\desktop\_tmp_backend\models\__init__.py`
- `D:\项目\Auto-claude-code-research-in-sleep-main\desktop\_tmp_backend\models\schemas.py`
- `D:\项目\Auto-claude-code-research-in-sleep-main\desktop\_tmp_backend\routers\__init__.py`
- `D:\项目\Auto-claude-code-research-in-sleep-main\desktop\_tmp_backend\services\__init__.py`
- `D:\项目\Auto-claude-code-research-in-sleep-main\desktop\_tmp_backend\services\_preview_proxy.py`
- `D:\项目\Auto-claude-code-research-in-sleep-main\desktop\_tmp_backend\services\paper_source_scope.py`
- `D:\项目\Auto-claude-code-research-in-sleep-main\desktop\_tmp_backend\services\prompts\__init__.py`
- …（其余 44 条同前缀，完整列表见 `pyc_dump/_index.json`）

## 证据 2：运行时数据库文件名

安装后实际使用的 SQLite 数据库名为 **`aris.db`**：

```
C:\Users\SAKE\AppData\Roaming\ModexData\library-aJL7Wi\db\aris.db
```

且其表结构（11 张表）与 `resources/app/backend/db/schema.sql` 完全一致。
一个纯自研产品不会把数据库命名为另一个项目的名字。

## 证据 3：工作流模板名与上游 skill 名同源

`schema.sql` 中 `workflows.template` 的枚举值（蓝方自述）：

| Modex workflow 模板 | ARIS 对应 skill | 关系 |
|---|---|---|
| `idea_discovery` | `/idea-discovery` | **直接沿袭** |
| `experiment_bridge` | `/experiment-bridge` | **直接沿袭** |
| `auto_review` | `/auto-review-loop`, `/auto-review-loop-llm`, `/auto-review-loop-minimax` | 族系沿袭 |
| `paper_writing` | `/paper-writing` | **直接沿袭** |
| `full_pipeline` | — | **蓝方新增** |
| `thesis_proposal` | — | **蓝方新增** |
| `literature_review` | — | **蓝方新增** |
| `course_paper` | — | **蓝方新增** |
| `course_report` | — | **蓝方新增** |
| `humanities_paper` | — | **蓝方新增** |
| `comp_* ...` | — | **蓝方新增** |

对应关系是机械的：ARIS 用连字符的 skill 目录名，Modex 改成下划线作为内部模板标识符。

- **直接沿袭**（3 个）：`idea_discovery`, `experiment_bridge`, `paper_writing`
- **族系沿袭**（1 个）：`auto_review`
- **蓝方新增**（7 个）：`full_pipeline`, `thesis_proposal`, `literature_review`, `course_paper`, `course_report`, `humanities_paper`, `comp_* ...`

这组分类就是红方要复现的**增量边界**：

- 「直接沿袭」部分 → **直接从 ARIS 公开上游取用**，无需逆向；
- 「蓝方新增」部分 → 需要自行设计，其中 `comp_*` 是数学建模竞赛特化模板
  （`workflow_engine` 内可见 `_comp_zh_steps` / `_comp_en_steps`，即国赛中文 / 美赛英文两套步骤，
  由 `_comp_zh_steps()` / `_comp_en_steps()` 返回「中文/英文竞赛通用步骤列表」）。

## 证据 4：模块划分与命名沿革

- ARIS 仓库顶层结构：`skills/`、`commands/`、`tools/`、`mcp-servers/`、`docs/`
- Modex 开发结构：`desktop/_tmp_backend`、`desktop/_tmp_tools`（见证据 1），
  打包后为 `web/backend` + `tools/`，并新增 `web/frontend`(React) 与 `desktop/`(Electron)。

上游 ARIS 的 Python 工具共 130 个；Modex 打包的 `tools/` 共 43 个。

## 证据 5：随产品分发的模板 README 原样保留了上游的 skill 引用

`resources/app/templates/README.md` 是随安装包分发的用户文档，其内容逐字对应
上游 ARIS 的 workflow 编号体系与 `/skill-name` 调用语法：

| Modex `templates/README.md` 原文 | ARIS `SKILLS_CATALOG.md` 定义 |
|---|---|
| `RESEARCH_BRIEF_TEMPLATE.md` → **Workflow 1** | `/idea-discovery` = **Workflow 1** |
| `EXPERIMENT_PLAN_TEMPLATE.md` → **Workflow 1.5** | `/experiment-bridge` = **Workflow 1.5** |
| `NARRATIVE_REPORT_TEMPLATE.md` → **Workflow 3** | `/paper-writing` = **Workflow 3** |
| `IDEA_CANDIDATES_TEMPLATE.md` ← 由 `/idea-discovery` 产出 | `/idea-discovery` |
| `EXPERIMENT_LOG_TEMPLATE.md` ← 由 `/experiment-bridge` 产出 | `/experiment-bridge` |
| `FINDINGS_TEMPLATE.md` ← 由 `/auto-review-loop` 产出 | `/auto-review-loop` |

README 中甚至保留了原汁原味的调用示例：

```bash
cp templates/EXPERIMENT_PLAN_TEMPLATE.md refine-logs/EXPERIMENT_PLAN.md
/experiment-bridge
```

ARIS 的 skill 编号并非连续（1 / 1.5 / 2 / 3 / 4 / 5 / 6 / M）。
Modex 的模板 README 复用了**同一套非连续编号**——这不是巧合，而是同源的确证。

> 【直接提取】`[证据: resources/app/templates/README.md 第 9-21 行]`

## 证据 6：随包分发的**明文提示词**残留开发机绝对路径

证据 1 依赖 `.pyc`（可能被辩解为「编译环境残留」）。但同一条路径也出现在
**明文 Markdown 提示词**中，而该文件是随安装包分发的产品内容：

```bash
# resources/app/backend/services/prompts/course_docx_drawio_png.md:6
DRAWIO=$(command -v draw.io 2>/dev/null || echo 'D:/项目/Auto-claude-code-research-in-sleep-main/desktop/runtime/draw.io/draw.io.exe')
```

前缀 `D:/项目/Auto-claude-code-research-in-sleep-main/desktop/` 与证据 1 的
`.pyc` 路径**逐字一致**。明文源码比字节码更难辩解为环境残留。

> 【直接提取】`[证据: 全安装目录明文文件检索，命中 1 处]`

## 上游 ARIS 概览（用于复现时直接取用）

- 仓库：https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep
- 许可证：见仓库 `LICENSE`（**复现前必须自行核实授权条款**）
- skill 总数：**83**
- 分组目录（`docs/SKILLS_CATALOG.md` 已完整保存到 `aris-skills-catalog.md`）

ARIS 全部 skill：

`ablation-planner`, `alphaxiv`, `analyze-results`, `arxiv`, `auto-paper-improvement-loop`, `auto-review-loop`, `auto-review-loop-llm`, `auto-review-loop-minimax`, `citation-audit`, `claims-drafting`, `comm-lit-review`, `deepxiv`, `dse-loop`, `embodiment-description`, `exa-search`, `experiment-audit`, `experiment-bridge`, `experiment-plan`, `experiment-queue`, `feishu-notify`, `figure-description`, `figure-spec`, `formula-derivation`, `gemini-search`, `grant-proposal`, `idea-creator`, `idea-discovery`, `idea-discovery-robot`, `integrity-forensics`, `interview-cheatsheet`, `invention-structuring`, `jurisdiction-format`, `kill-argument`, `mermaid-diagram`, `meta-apply`, `meta-optimize`, `monitor-experiment`, `novelty-check`, `openalex`, `overleaf-sync`, `paper-claim-audit`, `paper-compile`, `paper-figure`, `paper-illustration`, `paper-illustration-image2`, `paper-plan`, `paper-poster`, `paper-poster-html`, `paper-slides`, `paper-talk`, `paper-write`, `paper-writing`, `patent-novelty-check`, `patent-pipeline`, `patent-review`, `pixel-art`, `prior-art-search`, `proof-checker`, `proof-orchestrator`, `proof-writer`, `qzcli`, `rebuttal`, `render-html`, `research-implement-feature`, `research-lit`, `research-pipeline`, `research-refine`, `research-refine-pipeline`, `research-review`, `research-wiki`, `resubmit-pipeline`, `result-to-claim`, `run-experiment`, `semantic-scholar`, `serverless-modal`, `slides-polish`, `specification-writing`, `system-profile`, `training-check`, `vast-gpu`, `web-debug-search`, `wiki-enrich`, `writing-systems-papers`

## 重要限制：Modex 的 skill 语料**不在**编译产物里

在 Modex 全部 `.pyd` 的字符串表中检索 83 个 ARIS skill 名，**命中 0 个**；
`SKILL.md` 仅作为**字面引用**出现 1 次，而 `capsule` 出现 93 次、`skill_crypto` 出现 49 次。

结合 `web/backend/services/` 下的模块构成：

- `services/skill_capsule.py`
- `services/skill_crypto.py`
- `services/capsule_io.py`
- `services/skill_provenance.py`
- `services/skill_source.py`
- `services/skill_runtime_policy.py`

可判定：**蓝方把 skill 语料（即方法论本体）封装成了加密的 skill capsule**，
运行时装载而非随包明文分发。因此：

- 红方无法从本机安装包中直接提取 Modex 的 skill 正文；
- 但**可以直接从开源上游 ARIS 取得同源的方法论骨架**，这是成本最低的复现路径；
- 蓝方相对上游的增量主要在**工程化**（桌面壳、FastAPI 服务、工作流引擎、
  中文 docx/LaTeX 排版、多模型账号与计费、加密 capsule 分发），而非方法论原创。

