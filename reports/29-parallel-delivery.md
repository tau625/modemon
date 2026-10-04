# 多 Agent 并行推进：执行记录与验收

> 目标：按 `28-gap-closure-plan.md` 用 5 条互不冲突的工作流并行推进。
> 结果：**5/5 交付，全量 1355 项测试 0 失败**（基线 591 项 → 增长 129%）。

---

## 1. 并行策略：按**写作用域**切分，而不是按任务类型

并行的唯一硬约束是**同一文件不能被两个 agent 同时改**。因此我先核对了每一项触及的文件，
再把"共享同一文件"的项归并到同一条流：

| 流 | 写作用域（独占） | 内容 |
|---|---|---|
| A | `latex_export.py` | P0 导出安全 + `\captionof`/表题字重/参考文献编号 |
| B | `workflow_engine.py` + 新建注册表 | 22 模板 + comp_stats + 华为杯 + 超时分级 |
| C | `paper_build.py` + `step_runner.py` | 格式约定 + 标签歧义 + 列名本地化 |
| D | `main.py` | 僵尸清理 + 日志归集 + 500 追查 |
| E | 全新文件 | ARIS `citation-audit` 接入 |

`workflow_service.py` 与 `models/schemas.py` **留给 Lead 统一改**（跨流接口点）。

**为什么这样切**：若按"任务类型"切（P0 一组、模板一组、排版一组），
A 与 C 会同时改 `latex_export.py`/`paper_build.py`，D 与 B 会同时改 `main.py`/`workflow_engine.py` —— 必然冲突。

---

## 2. 交付结果

| 流 | 新增测试 | 关键交付 |
|---|---|---|
| A | 50 | `EXPORT_MARKER` 生成标记 + `is_engine_generated()`；`_archive_existing_tex()`；空正文 `ok=False` 且**跳过编译**；`caption_inside_environment()`（幂等）；表题字重统一；`\item[{[i]}]` |
| B | 449 | 注册表 **35 个可解析值**（22 竞赛 + 5 学术 + 1 资产 + 2 ip + 5 兼容）；`coerce_value()` 对 `str`/`Enum`/`None`/数字**一律不抛异常**；`comp_stats_steps()` 5 步；华为杯**步骤级变体**（不复制 DAG） |
| C | 82 | `paper/sections/NN_章节名.md` 约定；`_label_for` 保留分组前缀 + 三级去重；`_value_label()` 把 `x11` 变 `DC1→R1`；`detect_prebuilt_tex()` 三段式 |
| D | 87 | 启动自愈 + 每 300s 定期回收（阈值 45 分钟 = 实测最长单步 24.5 min 的 1.8×）；日志落盘 `backend/logs/modemon.log`（midnight 轮转/保留 14 天）；导出 500 结构化兜底 |
| E | 96 | ARIS `citation-audit` 正文 31067 B（SHA256 钉死）+ `citation_audit.py` + 接线说明 |

**全量：16 个测试文件，1355 项，0 失败。**
基线 11 文件 591 项**逐项持平**（原有测试零改动）。

---

## 3. Lead 的集成工作（跨流接口点）

### 3.1 修掉"枚举挡住注册表"（关键）
流 B 交付了 35 个模板，但 **API 只认 9 个**：

```
S.TemplateType("comp_tianfu")  →  ValueError
POST /api/workflows {comp_tianfu}  →  422     ← 22 个新模板完全不可达
```

**改法（避免第二份真相源）**：不往枚举里硬编码 30 个成员（那正是流 B 反对的"抄两份必然漂移"），
而是把校验改走注册表：

| 位置 | 改动 |
|---|---|
| `models/schemas.py` | `template: TemplateType` → `template: str` + `field_validator` 调 `registry.is_known()` |
| `main.py` `/api/templates` | `for t in S.TemplateType` → `for value in we.registry.values()` |
| `main.py` `create_workflow` | `body.template.value` → `body.template`（3 处） |
| `main.py` `resolve_steps` | `S.TemplateType(template)` → `we.registry.is_known(template)` |
| `main.py` 响应构造 | `S.TemplateType(r["template"])` → `r["template"]`（2 处） |

**效果验证**：

```
/api/templates          → HTTP 200,  35 个模板（原 9 个）
POST comp_tianfu        → HTTP 201
POST comp_stats         → HTTP 201
POST bogus              → HTTP 422   ← 非法仍被拒（原契约保留）
resolve-steps 非法       → HTTP 404
comp_stats resolve-steps → HTTP 200, 5 步
```

### 3.2 引用审计接线（4 处）
`CITATION_AUDIT_SKILLS` 从模块导入（不另抄名单）+ `_CITATION_TASKS` 强引用 +
`_run_post_step_citation_audit`（异常分支也写库）+ 派发分支自动复用**两处**既有钩子调用点。
事件 kind = `citation_audit`。

### 3.3 补 `comp-data-analysis` 进 `POST_AUDIT_SKILLS`
流 B 新增 `comp_stats` 第 2 步的默认技能名是 `comp-data-analysis`（`comp-stats-code` 是 select 别名）。
漏掉它会让统计流的诚信审计不触发。

---

## 4. Lead 的最终验收（P0）

```
[1] 导出不得摧毁 agent 的成品 .tex
  PASS  **agent 成品仍在且逐字节未变**
      notes: 检测到 agent 直出的成品 paper/main.tex（无引擎生成标记）
             → 走「只编译不重建」路径
[2] 空正文导出不得报成功
  PASS  **ok is False**
  PASS  给出可读 error
[3] preamble 宏包不重复
  PASS  caption 只引入 1 次
PASS 4 / FAIL 0
```

**P0 数据丢失风险已消除**，且有回归测试钉死。

---

## 5. 过程中的三个真实教训

### 5.1 并行会让队友看到彼此的"在途状态"
多位队友报告过 `test_aris_integration` 3 失败、`test_figure_pipeline` 6 失败，
但我**最终复跑时都是 39/39 全过**——他们跑全量时读到了别人半成品。

**结论**：**最终验收必须等所有写者停下后由 Lead 做**，不能采信并行期的测试快照。

### 5.2 我自己的一个判断被队友正确纠正
我此前报告"`resolve_template("comp_tianfu")` 抛 `TypeError`"。
流 B 指出实测返回 8 步。复核确认：**是我探测代码的问题**——
该函数返回 `TemplateDef` 对象，而我写了 `len(steps)` → 才 TypeError。

**真实阻塞是 `S.TemplateType(...)` 的 `ValueError`**（API 入口），已修。

### 5.3 环境依赖缺失的误判
流 B 报过一次"16 文件 804 过 / 10 失败"，根因是 bundled Python 缺
`jsonschema`/`drawsvg`/`svgwrite`（`figure_renderer.py` 抛 ModuleNotFoundError），
**与任何人的模板改动无关**。补装依赖后全绿。

---

## 6. 遗留项（已记录，未做）

| 项 | 位置 | 说明 |
|---|---|---|
| 提示词与约定并存 | `step_runner.py` | `step.primary_output` 仍要求 `paper/main.tex`，与 C 的 sections 约定并存。门控已双向兼容，**只多耗 token，不误判** |
| 单步预算分级未接线 | `run_full_pipeline.py` | `tiered_inactivity_timeout()` 已提供，脚本仍用硬编码 `--step-deadline-min 40` |
| 前端多页面 | `frontend/` | 计划中列为"暂缓" |
| 账号/计费/网关 | — | 计划中列为"不做" |

---

## 7. 与蓝方的对齐度变化

| 维度 | 开工前 | 现在 |
|---|---|---|
| 模板名 | 9 / 30 = **30%** | **35 / 30 = 117%**（含 5 个兼容值） |
| 编排序列 | 2 / 3 = 67% | **3 / 3 = 100%**（补齐 `comp_stats`） |
| API 端点 | 25 / 143（核心面）= 17% | 25 / 143（**本轮的模板接线让 22 个新模板可达**，但没加端点） |
| 引用审计 | **0** | ✅ 已接入 |
| 导出安全 | ❌ **P0 数据丢失风险** | ✅ **已消除** |
| 竞赛主线能力点 | ~80% | **~90%** |
