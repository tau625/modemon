# `services.workflow_engine` 配置数据恢复（参数化探测）

**原理**：`_comp_zh_steps(first_skill='comp-prob-analysis', paper_skill='comp-paper-zh')`
的默认参数可见，等价零参可调；一旦拿到技能名，一整族**纯访问器**即可求值。

**只调用白名单内的无副作用访问器**（未调用任何写文件 / 启动进程 / 网络函数）。

| 结果 | 数量 |
|---|---|
| 成功调用 | **67** |
| 失败调用 | 0 |

## 发现的技能名（10）

`comp-code`, `comp-compile-en`, `comp-compile-zh`, `comp-modeling`, `comp-paper-en`, `comp-paper-zh`, `comp-prob-analysis`, `comp-review`, `paper-figure`, `paper-figure-drawio`

## ★ 中文竞赛步骤列表 `_comp_zh_steps()`

```
["StepDef(skill_name='comp-prob-analysis', display_name='赛题分析', output_files=['PROBLEM_ANALYSIS.md'], primary_output='PROBLEM_ANALYSIS.md', has_checkpoint=True, checkpoint_type='approve')", "StepDef(skill_name='comp-modeling', display_name='建模求解', output_files=['MODELING_REPORT.md'], primary_output='MODELING_REPORT.md', has_checkpoint=True, checkpoint_type='feedback')", "StepDef(skill_name='comp-code', display_name='编程实现', output_files=['code/main.py', 'RESULTS.md'], primary_output='RESULTS.md', has_checkpoint=True, checkpoint_type='approve')", "StepDef(skill_name='paper-figure', display_name='图表生成', output_files=['figures/latex_includes.tex'], primary_output='figures/', has_checkpoint=False, checkpoint_type=None)", "StepDef(skill_name='paper-figure-drawio', display_name='流程与架构图绘制', output_files=['figures/latex_includes.tex'], primary_output='figures/', has_checkpoint=False, checkpoint_type=None)", "StepDef(skill_name='comp-review', display_name='逻辑对抗复核', output_files=['COMP_REVIEW.md'], primary_output='COMP_REVIEW.md', has_checkpoint=False, checkpoint_type=None)", "StepDef(skill_name='comp-paper-zh', display_name='竞赛论文撰写', output_files=['paper/main.tex'], primary_output='paper/main.tex', has_checkpoint=True, checkpoint_type='approve')", "StepDef(skill_name='comp-compile-zh', display_name='编译与合规检查', output_files=['paper/main.pdf'], primary_output='paper/main.pdf', has_checkpoint=False, checkpoint_type=None)"]
```

## 逐技能配置数据

### `_min_size_for`

| skill | 值 |
|---|---|
| `comp-code')` | `1000` |
| `comp-compile-en')` | `30000` |
| `comp-compile-zh')` | `30000` |
| `comp-modeling')` | `2000` |
| `comp-paper-en')` | `10000` |
| `comp-paper-zh')` | `10000` |
| `comp-prob-analysis')` | `1500` |
| `comp-review')` | `40` |
| `paper-figure')` | `500` |
| `paper-figure-drawio')` | `500` |

### `_required_companions_for`

| skill | 值 |
|---|---|
| `comp-code')` | `["code/main.py", "figures/all_results.json"]` |
| `comp-compile-en')` | `[]` |
| `comp-compile-zh')` | `[]` |
| `comp-modeling')` | `[]` |
| `comp-paper-en')` | `[]` |
| `comp-paper-zh')` | `[]` |
| `comp-prob-analysis')` | `[]` |
| `comp-review')` | `[]` |
| `paper-figure')` | `[]` |
| `paper-figure-drawio')` | `[]` |

### `_step_inactivity_timeout`

| skill | 值 |
|---|---|
| `comp-code')` | `5400` |
| `comp-compile-en')` | `2700` |
| `comp-compile-zh')` | `2700` |
| `comp-modeling')` | `5400` |
| `comp-paper-en')` | `2700` |
| `comp-paper-zh')` | `2700` |
| `comp-prob-analysis')` | `5400` |
| `comp-review')` | `5400` |
| `paper-figure')` | `5400` |
| `paper-figure-drawio')` | `5400` |

### `_skill_template_dependencies`

| skill | 值 |
|---|---|
| `comp-code')` | `[]` |
| `comp-compile-en')` | `[]` |
| `comp-compile-zh')` | `[]` |
| `comp-modeling')` | `[]` |
| `comp-paper-en')` | `[]` |
| `comp-paper-zh')` | `[]` |
| `comp-prob-analysis')` | `[]` |
| `comp-review')` | `[]` |
| `paper-figure')` | `[]` |
| `paper-figure-drawio')` | `[]` |

### `_compute_health_blocks`

| skill | 值 |
|---|---|
| `comp-code')` | `false` |
| `comp-compile-en')` | `false` |
| `comp-compile-zh')` | `false` |
| `comp-modeling')` | `false` |
| `comp-paper-en')` | `false` |
| `comp-paper-zh')` | `false` |
| `comp-prob-analysis')` | `false` |
| `comp-review')` | `false` |
| `paper-figure')` | `false` |
| `paper-figure-drawio')` | `false` |

## 竞赛页码规则 `_resolve_competition_page_rule`

| template | 返回值 |
|---|---|
| `comp_apmcm` | `[25, "advisory_max"]` |
| `comp_cumcm` | `[30, "advisory_max"]` |
| `comp_en` | `[null, "advisory_max"]` |
| `comp_huawei` | `[50, "advisory_max"]` |
| `comp_mathorcup` | `[30, "advisory_max"]` |
| `comp_mcm` | `[25, "advisory_max"]` |
| `comp_zh` | `[null, "advisory_max"]` |
| `course_paper` | `[null, "advisory_max"]` |
| `thesis_proposal` | `[null, "advisory_max"]` |

## 默认思考强度 `_resolve_step_effort({}, skill)`

- `comp-code` → `<_cython_3_2_5.coroutine object at 0x00000260434A6C20>`
- `comp-compile-en` → `<_cython_3_2_5.coroutine object at 0x00000260434A6CB0>`
- `comp-compile-zh` → `<_cython_3_2_5.coroutine object at 0x00000260434A6D40>`
- `comp-modeling` → `<_cython_3_2_5.coroutine object at 0x00000260434A6DD0>`
- `comp-paper-en` → `<_cython_3_2_5.coroutine object at 0x00000260434A6E60>`
- `comp-paper-zh` → `<_cython_3_2_5.coroutine object at 0x00000260434A6EF0>`

