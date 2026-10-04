# 复现可行性评估

> 问题：**现在能复现这个蓝方软件吗？如果不行，还差什么？**
> 结论日期：2026-10-01　|　证据基础：本次全部分析产物

---

## 0. 直接回答

**不能整体复现为「字节级克隆」。但可复现的程度远高于常规逆向的预期——
差距不在「看不懂」，而在「要重写的代码量」和「三块结构性拿不到的东西」。**

一句话概括：**规格（specification）基本拿到了，实现（implementation）要从零写。**

| 层 | 可复现度 | 说明 |
|---|---|---|
| Electron 桌面主进程 | **100% 源码** | asar 里是**明文 JavaScript**，可直接读取/改写/复用 |
| 模板 / 提示词 / 排版规范 | **100%** | 均为明文（9 模板 + 8 提示词 + 13 样式 JSON） |
| 数据库模型 | **100%** | `schema.sql` 明文 254 行 + 16 条设计约束 |
| 后端**接口规格** | **约 90%** | 159/162 模块可导入内省 → 7,077 个带类型标注的签名 |
| 后端**实现逻辑** | **0%** | Cython 编译为原生机器码，**函数体不可恢复** |
| 前端**结构** | 约 70% | 路由/store/端点/技术栈已恢复；源码为 minified，需重写 |
| **Skill 语料（方法论本体）** | **0%（本机）** | **加密 capsule**，全部 `.pyd` 检索命中 0 |
| 服务端（License/网关/计费） | **0%** | 不在本机，属远程服务 |

---

## 1. ★ 本轮的突破：后端可以逐模块内省

**先前的误判**：我曾因导入顶层 `main` 被守卫拒绝（`RuntimeInspectionUnavailable`），
判断「后端动态分析路径被关闭」。

**实际情况**：**守卫只拦截 3 个模块**，其余 **159/162 可正常导入并内省**：

| 被拦截的模块 | 原因 |
|---|---|
| `main` | 导入时执行完整性校验 |
| `routers.client_config` | 同 |
| `services.client_gateway_config` | 同 |

被拦时的原文：
> `RuntimeInspectionUnavailable: 网关验证组件完整性检查未通过；未执行该组件，请使用官方安装包修复`

### 1.1 内省能拿到什么

| 对象 | 结果 |
|---|---|
| 可导入模块 | **159 / 162** |
| 模块 docstring | **158 个，共 35,819 字符**（本项目 docstring **就是设计文档**） |
| 类 | **422** |
| 异常类（含 `code` 错误码默认值） | **132** |
| dataclass 字段（名/类型/默认值） | **330** |
| 类方法 | **6,194** |
| 模块级函数 | **1,719** |
| **带类型标注的可用签名** | **7,077** |
| 有 docstring 的函数 / 方法 | 795 / 1,284 |
| 模块级常量（含正则） | 271 |

> 产物：[`12-backend-spec-recovered.md`](12-backend-spec-recovered.md) · 机器可读：[`12-backend-spec.json`](12-backend-spec.json)

### 1.2 恢复质量样例（真实提取）

**模块 docstring 即架构文档**——`config` 的 docstring 直接画出目录结构：

```
MH Agent 路径配置 — 同时支持开发模式和桌面打包模式。
...
    resources/app/          ← Electron asar 解压后的应用目录
    ...（正式包不含 skills/；受保护 Skill 从签名 Capsule 获取）
用户数据目录（%APPDATA%/MHAgent/）：db/aris.db 、workspaces/
```

**函数签名带完整类型标注与行为描述**：

```python
_package_key_id(edition: 'str', skill_id: 'str', content_version: 'str',
                product: 'str', key_version: 'int') -> 'str'

_check_figures_step_health(workspace: 'Path', skill_name: 'str',
                           files_created: 'Optional[List[str]]' = None) -> 'tuple'
    """对图表步骤做严格健康检查(动态版, 基于本步骤的文件增量)。
    返回 (ok, reason)；ok=True: 有真实新增图 / 用户禁用 / 无图论文场景 / rerun-skip 合法跳过；
    ok=False: 步骤摸鱼了, 应触发 AUTO-RECOVERY"""

_check_figure_pdf_quality(...)
    """Run the deterministic PDF visual gate for the requested figure subset.
    The model saying that a chart "looks fine" is not evidence."""
```

**API 请求/响应契约已完整恢复**（Pydantic `model_fields`）：

```python
WorkflowCreate(template: TemplateType, title: str, params: Dict,
               enable_checkpoints: bool = False)
CheckpointResponse(action: Literal['approve','select',...],
                   checkpoint_id: Optional[str] = None, data: Dict = {})
StepInfo(skill_name, display_name, step_order, status=StepStatus.PENDING,
         has_checkpoint=False, checkpoint_type=None, output_files=[], ...)
```

**并且意外找回了此前列为「未获取」的数值**：

> `_check_paper_body_pages(...)` docstring：
> **中文 `chars_per_page ≈ 800`（含图表），英文 ≈ 2200**

### 1.3 这意味着什么

先前评估是「照符号表猜测重写」；现在变成「**照接口规格复现**」——
每个函数**叫什么、收什么类型、返回什么、干什么用**都清楚，**只有怎么算出来的不知道**。

---

## 2. 结构性拿不到的四样东西

### 2.1 函数体实现（最大工作量，但**不是**情报缺口）

- Cython 编译为**原生 x64 机器码**，7,077 个签名的**函数体全部不可恢复**。
- 反编译 Cython 产物的 `.pyd` 在实践中不可行（C 中间层已丢失，只剩机器码）。
- ⇒ 后端 166 个模块的**逻辑必须自己写**。

**量级估算**：约 7,900 个函数/方法（含大量 Pydantic 生成方法与 getter，实际需要手写的核心逻辑
估计在千级）。这是一个**多人月级**的工程，不是一次逆向能产出的。

### 2.2 Skill 语料（方法论本体）—— **加密 capsule**

- 全部 `.pyd` 检索 83 个 ARIS skill 名 → **命中 0**；`capsule` 出现 93 次。
- `config` 的 docstring 亦明说：**「正式包不含 skills/；受保护 Skill 从签名 Capsule 获取」**。
- ⇒ 蓝方**有意**不随包分发方法论正文。这是有效的保护。

**替代路径**：上游 **ARIS 是公开的**（83 个 skill 全文在 GitHub）。
但按 `04-methodology.md` 的差分结论：**上游是 AI 科研血统，没有数模竞赛层、没有 docx 成文链路**
⇒ 竞赛层与中文成文必须自建。

### 2.3 Claude Code CLI（智能体运行时，专有）

- `runtime/node/node_modules/@anthropic-ai/claude-code/bin/claude.exe`，**243 MB 单文件**。
- 这是 Anthropic 的**专有 CLI**，其行为（工具集、`--allowedTools` 语义、子代理继承规则）
  是 Modex 架构的一部分。**不能复制，只能授权使用或替换。**

**替换代价**：整个「对话工作台 + 提议卡片 + 工具策略审计 + 串行队列」都是围绕它建的。
若换成自研 agent runtime，`chat_tool_policy`（40 条中文策略注释）那一整套都要重新设计。

### 2.4 服务端（License / 网关 / 计费）

- `license.mingheng.xin`（EdDSA 配置下发）、`api.mhcode.ai/v1`（模型网关）、
  `bill.mingheng.xin`、`openapi.alipay.com`。
- 客户端侧的信任链我能完整描述（见主报告 §6），但**服务端实现不在本机**。
- ⇒ 若 modemon 要商业化，这部分是**自建**而非复现。

---

## 3. 还差什么（可执行清单）

| # | 缺口 | 现状 | 补齐方式 | 量级 |
|---|---|---|---|---|
| 1 | 后端 166 模块的**实现逻辑** | 只有规格（7,077 签名 + docstring） | **照规格重写** | ★★★ 多人月 |
| 2 | **Skill 语料** | 0（加密 capsule） | 用上游 ARIS 骨架 + 自建竞赛层 | ★★ 人月 |
| 3 | **Agent 运行时** | 依赖专有 Claude CLI | 授权使用，或自研替代（连带动摇 chat 策略层） | ★★★ 取决于路线 |
| 4 | 前端**源码** | minified；结构已知 | 按路由/store/端点重写 | ★★ 人月 |
| 5 | 服务端（License/网关/计费） | 0 | 自建 | ★★ 视商业需求 |
| 6 | 3 个被守卫模块（`main` 等） | 不可导入 | 从符号表 + 路由 + 数据模型反推 | ★ 小 |
| 7 | 中文排版 `.cls` 规范 | 参数已恢复 | **从公开 `cumcmthesis.cls` / `gmcmthesis.cls` 反推** | ★ 小 |
| 8 | docx 渲染器内部实现 | 未获取（`docx_export.pyd` 仅 1 条中文串） | 自研或改用 python-docx / docx-cn-engine 思路 | ★★ 中 |

---

## 4. 三条可选路线（按目标分）

| 目标 | 可行性 | 说明 |
|---|---|---|
| **A. 字节级克隆** | ❌ **不可行** | 函数体 + skill 正文 + 服务端三重缺失 |
| **B. 功能等价的自研产品** | ✅ **可行** | 以本报告为规格书自研；上游 ARIS 供方法论；这是我认为可完成的一条 |
| **C. 部分复用 + 快速原型** | ✅ **最容易** | 直接复用 Electron 主进程明文 JS + 模板/提示词/样式 JSON + DB schema；后端只实现你真正需要的子集（如工作流引擎 + docx 导出），跳过账号/计费/CLI 网关 |

**我的建议**：从 **C** 起步，把 B 作为演进目标。
理由：`resources/app` 的 Electron 主进程是**完整明文源码**，
加上模板/提示词/样式/schema，已经足以搭出一个能跑的骨架；
后端只需实现「工作流引擎 + 技能编排 + docx/LaTeX 导出」这条主线，
而**跳过**账号体系、计费钱包、NewAPI 网关、加密 capsule 这些商业化设施。

---

## 5. 明确的能力边界声明

为避免误导，以下是我**做不到**的，不做任何模糊化：

1. **不能还原任何函数体的算法实现**（Cython 机器码）。
2. **不能解密 skill capsule**（无密钥；且本次分析未尝试任何破解）。
3. **不能绕过运行期守卫**（未尝试；仅记录其行为）。
4. **不能验证未运行过的行为**——所有动态结论都来自「导入内省」与「日志读取」，
   未实际跑通业务流程。
5. **不能给出精确工作量估计**——第 3 节的数量级是粗略判断，非工程评估。

---

## 6. 本轮新增产物

| 文件 | 内容 |
|---|---|
| [`12-backend-spec-recovered.md`](12-backend-spec-recovered.md) | 内省恢复的规格摘要 + 模块 docstring 样例 |
| [`12-backend-spec.json`](12-backend-spec.json) | **机器可读的完整规格**（159 模块 × 类/方法/签名/字段/异常码） |
| `tools/introspect_backend.py` | 内省脚本（分批子进程，可复现） |
| [`11-recoverability.md`](11-recoverability.md) | 恢复度量化（含剔除解释器样板的修正记录） |
