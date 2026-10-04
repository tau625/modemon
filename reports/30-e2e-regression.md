# 完整流水线端到端回归（并行工作之后）

> 目的：验证并行交付的新能力在**真实运行**中都生效，并检查有无回归。
> 结果：**8/8 步完成**（49.2 分钟 / $5.18），三条钩子全部生效，
> 同时**暴露出 5 个只有真跑才能发现的新缺陷**（已修 4 个）。

---

## 1. 运行结果

| 步骤 | 状态 | 耗时 | 花费 |
|---|---|---|---|
| 1 comp-prob-analysis | ✅ | 89.6s | $0.107 |
| 2 comp-modeling | ✅ | 717.6s | $0.281 |
| 3 comp-code | ✅ | 222.1s | $0.487 |
| 4 paper-figure | ✅ | 127.2s | $0.314 |
| 5 paper-figure-drawio | ✅ | 276.6s | $0.511 |
| 6 comp-review | ✅ | 241.8s | $0.427 |
| 7 comp-paper-zh | ✅ | 1242.6s | $4.68 |
| 8 comp-compile-zh | ✅ | 36.6s | $0.070 |
| **合计** | **8/8** | **49.2 分钟** | **$5.18** |

---

## 2. ★ 三条后台钩子**全部生效**（首次）

```
[result_audit]  结果诚信审计：pass @10:44:17
    verdict=pass  ok=True  triggered_by=comp-code
    note: exit=0 subtype=success is_error=False 输出 7280 字符

[figure_render] FigureSpec 渲染：2 张 @10:37:37
    -> figures/architecture.spec.json     → architecture.png (108 KB)
    -> figures/tikz_architecture.spec.json → tikz_architecture.png

[citation_audit] （comp-review 触发，事件已落库）
```

**这是首次三条钩子在同一次运行中全部触发并落库**——
此前 `result_audit` 因"检查点路径提前 return"从未执行（见 `26-project-review-gaps.md`）。

工作区也因此出现 `.aris/traces/experiment-audit/2026-10-04_run01/`
（agent 按 `experiment-audit` skill 约定写的审计轨迹）。

---

## 3. ★ `paper/sections` 约定生效

agent 按新约定写了 **10 个分节**，命名完全合规：

```
paper/sections/00_摘要.md              1868 B
               01_问题重述.md          1105 B
               02_问题分析.md          1750 B
               03_模型假设与符号说明.md  2285 B
               04_模型建立.md          3208 B
               05_模型求解与结果.md     2362 B
               06_灵敏度与稳定性分析.md  5165 B
               07_模型评价与推广.md     2271 B
               08_结论.md              1496 B
               09_参考文献.md           525 B
```

**P0 导出安全也生效**：工作区同时存在
- `paper/main.agent.tex`（29,664 B）—— **agent 直出成品，被完整保留**
- `paper/main.tex`（27,921 B）—— 引擎装配版

导出返回里明确说明：
> 「`paper/main.tex` 已存在且非本引擎生成（首行无生成标记），已改名保留为 `paper/main.agent.tex`；本次导出未覆盖该文件」

---

## 4. 本轮暴露的 5 个新缺陷（只有真跑才能发现）

### 4.1 ★ SVG 被当插图 → 整份论文编译失败
**症状**：
```
! LaTeX Error: Cannot determine size of graphic in
    ../figures/tikz_architecture.svg (no BoundingBox).
l.311 ...tratio]{../figures/tikz_architecture.svg}
```
**根因**：`FIGURE_RE` 只匹配**文件名主干**，而 FigureSpec 渲染链会同时产出
`X.png`（嵌 LaTeX 用）与 `X.svg`（可编辑矢量原稿）——**两者 stem 相同，都被收作插图**。
`\includegraphics` **不支持 SVG**。

**修复**：新增 `LATEX_FIGURE_EXTS = (".png",".jpg",".jpeg",".pdf")`；
按 stem 去重并**优先可嵌入的光栅格式**，纯 SVG/DrawIO 不进 LaTeX。
效果：`doc.figures` 8 → **7**，重复 `latex_name` 消除。

### 4.2 同一份 spec 被写了两个名字 → 重复 `\label`
**症状**：`\label{fig:tikz_architecture}` 在 `.tex` 里出现 **2 次**。
**根因**：`architecture.spec.json` 与 `tikz_architecture.spec.json`
**逐字节相同**（SHA256 一致），agent 用两个名字写了同一份内容。
**修复**：`find_specs()` 按**内容哈希去重**（保留名字最短的那个）。效果：2 → **1**。

### 4.3 ★ 前向引用未解析（PDF 里出现 `??`）
**症状**：正文「三情景汇总结果见 **??**。」；
日志 `LaTeX Warning: Reference 'tab:results' on page 2 undefined`。
**根因**：`compile_tex` 默认 `runs=2` 是对的，但**最后那次编译只跑了 1 遍**——
`\ref{tab:results}` 在 L64，而 `\label{tab:results}` 在 L225（前向），一遍编译解析不了。
**修复**：重新导出（2 遍）。效果：`??` 从 **2 处 → 0 处**，日志无 undefined。

### 4.4 标题独占一页（版面校验报「近乎空白页」）
**症状**：第 1 页只有标题（15 字符），摘要跑到第 2 页。
**根因**：`build_document` 无条件在标题区后加 `\newpage`；
而 agent 把摘要写成**分节**（`00_摘要.md`）→ `doc.abstract` 为空 → 第 1 页只剩标题。
**修复**：**无摘要时不断页**，让首个分节自然接在标题下（也符合竞赛惯例）。
效果：第 1 页 15 → **1324 字符**（标题+摘要同页），无空白页。

### 4.5 我方版面校验器**漏报 `??`**（自查发现）
**症状**：校验器报「无未解析交叉引用」，而 PDF 里明明有 `??`。
**根因**：正则查 `???`（三个问号），而 LaTeX 的未解析引用占位是 **`??`（两个）**。
**修复**：改为查 `??` 并**打印上下文**。修完后立刻抓出了 4.3。

> 这条值得单独记：**校验器本身也会有 bug，而且它的 bug 会让后续所有检查失真**。

---

## 5. 最终产物

```
paper/main.pdf          13 页（引擎装配版，编译成功）
paper/main.agent.tex    29,664 B（agent 成品，完整保留）
paper/main.docx         47,627 B
paper/sections/*.md     10 个分节
figures/                7 张图 + 2 份 spec + manifest + latex_includes.tex
figures/all_results.json 8,998 B（数据真相源）
```

版面校验：**无空白页 / 无未解析引用**（2 条 WARN：末页图表、1 处孤立标题）。

---

## 6. 全量测试

**16 个测试文件，1355 项，0 失败。**

修完 4.1–4.4 后复跑，无回归。

---

## 7. 已固化为回归测试

新增 `tests/test_e2e_regressions.py`（**21 项**），每个用例都注明它对应哪个真实缺陷：

| 用例 | 断言什么 | 防止什么 |
|---|---|---|
| `test_svg_not_includable` | `LATEX_FIGURE_EXTS` 不含 svg/drawio；同 stem 只留一张且优先 png；**生成的 .tex 里无 `.svg`** | 4.1 编译整体失败 |
| `test_duplicate_spec_dedup` | 内容相同的 spec 去重为 1 份；内容不同的全保留 | 4.2 重复 `\label` |
| `test_forward_reference_needs_two_passes` | `compile_tex` 默认 `runs=2`；**两遍后 PDF 无 `??`**；**对照**：一遍确实留下 `??` | 4.3 未解析引用 |
| `test_no_title_only_page` | 有摘要保留 `\newpage`；**无摘要时标题后不断页** | 4.4 标题独占页 |
| `test_layout_verifier_catches_double_question` | 校验器源码覆盖 `??`；**行为**：喂一份未解析引用的 PDF，必须返回非 0 | 4.5 校验器漏报 |

### 写这些测试时踩的两个坑（记下来避免重犯）
1. **对照用例必须用全新目录**：我起初在同一目录先跑两遍再跑一遍，`.aux` 已被填好，单遍也"解析成功"，对照失效。
2. **`fitz` 文档必须 `close()`**：否则占住 PDF 文件，`TemporaryDirectory` 清理时 `PermissionError`。

### 校验器自身的定位
`verify_layout.py` 现在只查 `??`（不再重复匹配 `???`）——`???` 也含 `??`，
两条规则并存是冗余，且会让"只查 ?? "这类断言失效。

---

## 8. 修复后的第二次完整运行（验证修复效果）

| 项 | 第一次（有缺陷） | 第二次（修复后） |
|---|---|---|
| 步骤 | 8/8 | **8/8** |
| 耗时 / 花费 | 49.2 分钟 / $5.18 | 76.4 分钟 / $9.13 |
| 页数 | 13 | **19** |
| **编译** | ❌ `Cannot determine size of graphic ... .svg` | ✅ **成功** |
| **`.tex` 里的 `.svg`** | 有（致编译失败） | ✅ **无** |
| **重复 `\label`** | 1 组 | ✅ **无**（31 个 label 全唯一） |
| **PDF 里的 `??`** | 2 处 | ✅ **0 处** |
| **第 1 页** | 15 字符（近乎空白） | ✅ **1355 字符**（标题+摘要同页） |
| 版面校验 | FAIL 1 + WARN 2 | ✅ **PASS（全部通过）** |

### 三条钩子（第二次运行）

```
[result_audit]   结果诚信审计：skipped @15:26:28
    note: 审计超时，跳过（不阻塞）            ← 正确降级，未假报 pass
[figure_render]  FigureSpec 渲染：1 张 @15:14:44
    -> figures/architecture.spec.json → architecture.png (76 KB)
                                              ← **去重生效**（第一次是 2 张）
```

工作区里 `architecture.spec.json` 与 `tikz_architecture.spec.json` 仍在，
但引擎只渲染了 **1 张**——内容哈希去重按预期工作。

### 最终论文（19 页）

| 页 | 内容 |
|---|---|
| 1 | 标题 + 摘要（1355 字符） |
| 2–3 | 问题分析、**表 1 单位运价矩阵** |
| 4 | **图 1 求解流程与系统架构**（FigureSpec 渲染，多层流程图） |
| 5–9 | 符号说明、模型建立、求解结果与最优性证明 |
| 10–11 | **图 2 最优调运方案热力图**、表 7 灵敏度 |
| 12–15 | 稳定性分析、**图 4 最优性保持区间**、**表 11 蒙特卡洛** |
| 16–19 | **表 12/13**、模型评价、结论 |

**程序化表格与图注全部正常**：`表 1`–`表 13`、`图 1`/`图 2`/`图 4`
（图注是完整中文描述，不再是文件名）。

---

## 9. 结论

**并行交付的新能力全部在真实运行中生效**：
- 三条钩子（诚信审计 / 图渲染 / 引用审计）✅
- `paper/sections` 约定 ✅
- P0 导出安全（agent 成品保留）✅
- 22 个新模板（本轮用的是默认 `comp_cumcm`，模板可达性已在 API 层单独验证）✅

**但这轮再次印证了那条规律**：1355 项全绿，仍有 **5 个缺陷只有真跑才暴露**——
其中 4.1（SVG 致编译失败）和 4.3（前向引用）是**功能性错误**，
单测与静态检查都看不出，必须**编译真实文档并查看渲染结果**。

而 4.5 更值得警惕：**我自己的校验器有 bug，且它的 bug 掩盖了 4.3**。
