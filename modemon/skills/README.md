# ARIS skill 骨架

本目录接入上游 **ARIS** 的 skill 骨架。

## 许可（必须随分发一起保留）

上游采用 **MIT License**：

```
MIT License

Copyright (c) 2026 wanshuiyin

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

完整文本：[`../LICENSE-ARIS.txt`](../LICENSE-ARIS.txt)

> **MIT 的唯一硬性条件就是上面两条**：保留版权声明、保留许可全文。
> 其余（使用、修改、合并、发布、分发、再授权、出售）均无限制。
> 因此**复现与二次开发在许可上是完全可行的**，只要连同
> `LICENSE-ARIS.txt` 一起分发，并在源码中标注来源。

## 来源与血缘

| 项 | 值 |
|---|---|
| 上游仓库 | [`wanshuiyin/Auto-claude-code-research-in-sleep`](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) |
| 项目名 | ARIS（Auto-Research-In-Sleep） |
| 默认分支 | `main` |
| 许可 | MIT（SPDX） |
| 版权 | `Copyright (c) 2026 wanshuiyin` |
| 顶层 skill 数 | **83** |
| 取得方式 | GitHub API：`/git/trees/main?recursive=1` |

上游自述：

> ARIS ⚔️ (Auto-Research-In-Sleep) — Lightweight Markdown-only skills for
> autonomous ML research: cross-model review loops, idea discovery, and
> experiment automation. No framework, no lock-in — works with Claude Code,
> Codex, OpenClaw, or any LLM agent.

「**No framework, no lock-in**」这点很重要：skill 只是 Markdown，
这正是它能被直接接入 modemon 的原因。

## SKILL.md 格式（实测上游）

```yaml
---
name: figure-spec
description: "Generate deterministic publication-quality diagrams from JSON. Use when user says 架构图…"
argument-hint: "[description-of-diagram]"
allowed-tools: Bash(*), Read, Write, Edit, mcp__codex__codex
---
# FigureSpec: Deterministic JSON → SVG Figure Generation

正文……（可用 $ARGUMENTS 引用调用参数）
```

## 目录内容

| 文件 | 说明 |
|---|---|
| `catalog.json` | 83 个 skill 的**名称 + 路径 + 体量**，含来源与许可声明 |
| `LICENSE-ARIS.txt` | MIT 许可全文（**必须随分发保留**） |
| `README.md` | 本文件 |

## 加载器

[`../backend/services/skill_loader.py`](../backend/services/skill_loader.py) 提供：

```python
from services import skill_loader as sl

cat = sl.load_catalog()                 # 扫描 skills/*/SKILL.md
spec = cat.get("figure-spec")           # 取单个 skill
spec.allowed_tools                      # ('Bash(*)', 'Read', 'Write', ...)
sl.prompt_for_skill(spec, argument="某系统架构")   # $ARGUMENTS 已替换
sl.tools_for_skill(spec)                # 交给 StepRunRequest.allowed_tools
cat.search("architecture")              # 按名称/描述检索
```

设计上刻意**不引入 YAML 依赖**：上游 frontmatter 是扁平的 `key: value`，
最小实现足够，且避免解析差异。

## 已接入什么、未接入什么

**已接入**：
- skill 的**结构契约**（frontmatter 字段、`$ARGUMENTS` 占位、工具约束）
- 83 个 skill 的**目录与元数据**（`catalog.json`）
- 许可合规（`LICENSE-ARIS.txt` + 源码内嵌全文 + 测试断言）

**尚未接入**（需要单独评估）：
- skill **正文本体**（83 份共约 1.5 MB 的 Markdown）——建议按需引入，
  而不是一次性全量复制，以便逐个审阅是否适合竞赛场景
- `mcp-servers/`（ARIS 原有 8 个 MCP 服务器）——modemon 已把评审收敛为
  一个可切换模型的直连客户端，功能上等价但机制不同
- `aris-monitor/`（桌面挂件）——modemon 用 `watchdog` + Electron 重写

## 复现建议

1. **先引入与竞赛流水线直接相关的**：`figure-spec`（确定性架构图，
   与 `paper-figure-drawio` 对位）、`experiment-audit`（结果诚实度审计）、
   `citation-audit`（引用审计）、`analyze-results`（结果分析）
2. `experiment-audit` 特别值得细读——它明确写了**防自我赦免**的约束：
   > Do not wrap this skill in `/loop`, `/schedule`… a loop that accepts its own
   > output to decide when to stop crosses into self-acquittal.

   这与 modemon 的「质量门 + 返修」是同一类工程关切。
3. 任何衍生修改都要连同 `LICENSE-ARIS.txt` 分发
