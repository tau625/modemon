# `services.workflow_engine` 实现规格

> 产品主线模块（Cython 编译前 **3.1 MB**，后端最大）。
> 规格由内省恢复：**签名与 docstring 是真实的，函数体不可恢复**。

## 模块 docstring

```
工作流 DAG 编排引擎 — 逐步调用子 Skill，支持暂停/恢复 [v3-drawio-slim]
```

## 模块级常量（5）

| 名称 | 值 |
|---|---|
| `ADVISORY_REPAIR_PREFIX` | `'[OPTIONAL_OPTIMIZATION]'` |
| `AI_DISCLOSURE_PDF_NAME` | `'AI工具使用详情.pdf'` |
| `COMPACT_INDEX_MAX_CHARS` | `6000` |
| `CORE_FAILURE` | `'[CORE_ARTIFACT] '` |
| `_MANIFEST_ITEM_RE` | `re:^[ \t]*-[ \t]+(fig_[A-Za-z0-9_]+\|tikz_[A-Za-z0-9_]+)` |

## 异常类型（8）

### `AccessModeError`

- 基类：`ValueError`
- 构造签名：`(code, status=409)`

```
Inappropriate argument value (of correct type).
```

### `AccountError`

- 基类：`Exception`
- 构造签名：`(code: 'str', status: 'int' = 400, retry_after: 'int' = 0)`

```
Common base class for all non-exit exceptions.
```

### `ProtectedContentUnavailable`

- 基类：`SkillCryptoError`
- 构造签名：`(message: 'str', *, code: 'str' = 'SKILL_CONTENT_UNAVAILABLE')`

```
A protected task cannot continue, but the desktop process remains healthy.
```

### `RepairStopped`

- 基类：`StepCheckPending`
- 构造签名：`(reason: 'str', *, unavailable: 'bool' = False, safe_to_recheck: 'bool' = False)`

```
A runner failure with explicit evidence whether all work has stopped.
```

### `StepCheckPending`

- 基类：`RecoveryExhausted`
- 构造签名：`(reason: 'str', *, unavailable: 'bool' = False)`

```
Recovery stopped safely, but neither execution nor quality has passed.
```

### `StepExecutionFailed`

- 基类：`RuntimeError`

```
A repair/continuation did not finish; its files cannot prove success.
```

### `StepRepairInterrupted`

- 基类：`StepExecutionFailed`, `RepairStopped`
- 构造签名：`(reason: 'str', *, unavailable: 'bool' = False, safe_to_recheck: 'bool' = False)`

```
Unsafe/incomplete repair: retain receipts, do not blindly replay.
```

### `_DocxPrecheckFailure`

- 基类：`RuntimeError`
- 构造签名：`(reason: 'str', *, repairable: 'bool')`

```
Unspecified run-time error.
```

## 类（9）

### `Any`

- 基类：`object`
- 构造签名：`(*args, **kwargs)`

### `CheckIssue`

- 基类：`object`
- 构造签名：`(reason: 'str', repairable: 'bool' = True, severity: "Literal['error', 'warning']" = 'error') -> None`
- **字段**：

  | 字段 | 类型 | 默认值 |
  |---|---|---|
  | `reason` | `str` | `<dataclasses._MISSING_TYPE object at 0x000001B8C96` |
  | `repairable` | `bool` | `True` |
  | `severity` | `Literal['error', 'warning']` | `'error'` |

```
CheckIssue(reason: 'str', repairable: 'bool' = True, severity: "Literal['error', 'warning']" = 'error')
```

- **方法（1）**：

  - `__init__(self, reason: 'str', repairable: 'bool' = True, severity: "Literal['error', 'warning']" = 'error') -> None`
    > Initialize self.  See help(type(self)) for accurate signature.

### `ContextVar`

- 基类：`object`

- **方法（3）**：

  - `get`
    > Return a value for the context variable for the current context.
    > 
    > If there is no value for the variable in the current context, the method will:
    > * return the value of the default argument of the method, if provided; or
    > * return the default value for the context variable, if it was created
    > with one; or
    > * raise a LookupError.
  - `reset(self, token, /)`
    > Reset the context variable.
    > 
    > The variable is reset to the value it had before the `ContextVar.set()` that
    > created the token was used.
  - `set(self, value, /)`
    > Call to set a new value for the context variable in the current context.
    > 
    > The required value argument is the new value for the context variable.
    > 
    > Returns a Token object that can be used to restore the variable to its previous
    > value via the `ContextVar.reset()` method.

### `Path`

- 基类：`PurePath`
- 构造签名：`(*args, **kwargs)`

- **方法（41）**：

  - `_make_child_relpath(self, part)`
  - `_scandir(self)`
  - `absolute(self)`
  - `chmod(self, mode, *, follow_symlinks=True)`
  - `cwd`
  - `exists(self)`
  - `expanduser(self)`
  - `glob(self, pattern)`
  - `group(self)`
  - `hardlink_to(self, target)`
  - `home`
  - `is_block_device(self)`
  - `is_char_device(self)`
  - `is_dir(self)`
  - `is_fifo(self)`
  - `is_file(self)`
  - `is_mount(self)`
  - `is_socket(self)`
  - `is_symlink(self)`
  - `iterdir(self)`
  - `lchmod(self, mode)`
  - `link_to(self, target)`
  - `lstat(self)`
  - `mkdir(self, mode=511, parents=False, exist_ok=False)`
  - `open(self, mode='r', buffering=-1, encoding=None, errors=None, newline=None)`
  - `owner(self)`
  - `read_bytes(self)`
  - `read_text(self, encoding=None, errors=None)`
  - `readlink(self)`
  - `rename(self, target)`
  - `replace(self, target)`
  - `resolve(self, strict=False)`
  - `rglob(self, pattern)`
  - `rmdir(self)`
  - `samefile(self, other_path)`
  - `stat(self, *, follow_symlinks=True)`
  - `symlink_to(self, target, target_is_directory=False)`
  - `touch(self, mode=438, exist_ok=True)`
  - `unlink(self, missing_ok=False)`
  - `write_bytes(self, data)`
  - `write_text(self, data, encoding=None, errors=None, newline=None)`

### `StepDef`

- 基类：`object`
- 构造签名：`(skill_name: 'str', display_name: 'str', output_files: 'List[str]' = <factory>, primary_output: 'Optional[str]' = None, has_checkpoint: 'bool' = False, checkpoint_type: 'Optional[str]' = None) -> None`
- **字段**：

  | 字段 | 类型 | 默认值 |
  |---|---|---|
  | `skill_name` | `str` | `<dataclasses._MISSING_TYPE object at 0x000001B8C96` |
  | `display_name` | `str` | `<dataclasses._MISSING_TYPE object at 0x000001B8C96` |
  | `output_files` | `List[str]` | `<dataclasses._MISSING_TYPE object at 0x000001B8C96` |
  | `primary_output` | `Optional[str]` | `None` |
  | `has_checkpoint` | `bool` | `False` |
  | `checkpoint_type` | `Optional[str]` | `None` |

```
StepDef(skill_name: 'str', display_name: 'str', output_files: 'List[str]' = <factory>, primary_output: 'Optional[str]' = None, has_checkpoint: 'bool' = False, checkpoint_type: 'Optional[str]' = None)
```

- **方法（1）**：

  - `__init__(self, skill_name: 'str', display_name: 'str', output_files: 'List[str]' = <factory>, primary_output: 'Optional[str]' = None, has_checkpoint: 'bool' = False, checkpoint_type: 'Optional[str]' = None) -> None`
    > Initialize self.  See help(type(self)) for accurate signature.

### `StepStatus`

- 基类：`str`, `Enum`
- 构造签名：`(value, names=None, *, module=None, qualname=None, type=None, start=1, boundary=None)`

```
str(object='') -> str
str(bytes_or_buffer[, encoding[, errors]]) -> str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to sys.getdefaultencoding().
errors defaults to 'strict'.
```

- **方法（3）**：

  - `_generate_next_value_(name, start, count, last_values)`
  - `_new_member_(*args, **kwargs)`
    > Create and return a new object.  See help(type) for accurate signature.
  - `_value_repr_(self, /)`
    > Return repr(self).

### `TemplateDef`

- 基类：`object`
- 构造签名：`(pipeline_skill: 'str', display_name: 'str', sub_steps: 'List[StepDef]') -> None`
- **字段**：

  | 字段 | 类型 | 默认值 |
  |---|---|---|
  | `pipeline_skill` | `str` | `<dataclasses._MISSING_TYPE object at 0x000001B8C96` |
  | `display_name` | `str` | `<dataclasses._MISSING_TYPE object at 0x000001B8C96` |
  | `sub_steps` | `List[StepDef]` | `<dataclasses._MISSING_TYPE object at 0x000001B8C96` |

```
TemplateDef(pipeline_skill: 'str', display_name: 'str', sub_steps: 'List[StepDef]')
```

- **方法（1）**：

  - `__init__(self, pipeline_skill: 'str', display_name: 'str', sub_steps: 'List[StepDef]') -> None`
    > Initialize self.  See help(type(self)) for accurate signature.

### `TemplateType`

- 基类：`str`, `Enum`
- 构造签名：`(value, names=None, *, module=None, qualname=None, type=None, start=1, boundary=None)`

```
str(object='') -> str
str(bytes_or_buffer[, encoding[, errors]]) -> str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to sys.getdefaultencoding().
errors defaults to 'strict'.
```

- **方法（3）**：

  - `_generate_next_value_(name, start, count, last_values)`
  - `_new_member_(*args, **kwargs)`
    > Create and return a new object.  See help(type) for accurate signature.
  - `_value_repr_(self, /)`
    > Return repr(self).

### `WorkflowStatus`

- 基类：`str`, `Enum`
- 构造签名：`(value, names=None, *, module=None, qualname=None, type=None, start=1, boundary=None)`

```
str(object='') -> str
str(bytes_or_buffer[, encoding[, errors]]) -> str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to sys.getdefaultencoding().
errors defaults to 'strict'.
```

- **方法（3）**：

  - `_generate_next_value_(name, start, count, last_values)`
  - `_new_member_(*args, **kwargs)`
    > Create and return a new object.  See help(type) for accurate signature.
  - `_value_repr_(self, /)`
    > Return repr(self).

## 模块级函数（116）

- 有 docstring：**89**；仅有签名：27

### 有行为描述的（按名称排序）

#### `_actual_model_id(step_model: 'Optional[Dict]') -> 'str'`

```
解析某步「真实生效」的 executor model_id，用于落库快照（前端历史回看）。
step_model 指定了 model_id → 用它；否则回退全局 executor 角色的最终 model_id。
任何异常都吞掉返回空串，绝不因为「记个快照」把执行搞崩。
```

#### `_artifact_progress_signature(workspace: 'Path', candidates: 'List[str]') -> 'tuple'`

```
Return a content signature for declared artifacts only.

Diagnostic reports and logs are deliberately excluded: rewriting a check
report is not progress toward a missing paper, result file, or figure.
Timestamps are deliberately excluded too: an agent that rewrites identical
content has made no repair progress and must not earn another paid retry.
```

#### `_await_recovery(invocation, *, timeout)`

```
An outer deadline must preserve the same recovery classification.

wait_for cancels and joins the child. _run_recovery_skill cancels its own
CLI before propagating that cancellation, so no duplicate job is started.
```

#### `_build_context_summary(workspace: 'Path', files: 'List[str]', max_chars: 'int' = 12000) -> 'str'`

```
读取工作区已有文件的内容摘要，供给 Claude 参考。
优先读取关键类型文件（md/tex/bib），并做字符预算。
```

#### `_check_data_figure_quality(workspace: 'Path', candidates: 'Optional[List[str]]' = None, *, _checker_root: 'Optional[Path]' = None) -> 'Tuple[bool, str]'`

```
Check source text budget first, then the PDFs that users will see.
```

#### `_check_figure_pdf_quality(workspace: 'Path', candidates: 'Optional[List[str]]' = None, *, _checker_root: 'Optional[Path]' = None) -> 'Tuple[bool, str]'`

```
Run the deterministic PDF visual gate for the requested figure subset.

The model saying that a chart "looks fine" is not evidence.  This guard
inspects the files that actually landed in ``figures/`` and runs locally,
so it adds no model calls or token cost.  ``candidates`` may contain source
names, PNG paths or PDF paths; only corresponding existing PDFs are passed
to the checker.  A PNG-only Word workflow is therefore left compatible.
```

#### `_check_figures_step_health(workspace: 'Path', skill_name: 'str', files_created: 'Optional[List[str]]', files_modified: 'Optional[List[str]]', params: 'Dict[str, Any]') -> 'Tuple[bool, str]'`

```
对图表步骤做严格健康检查(动态版, 基于本步骤的文件增量)。

Returns: (ok, reason)
    ok=True: 步骤产出健康(有真实新增图 / 用户禁用 / 无图论文场景 / rerun-skip 合法跳过)
    ok=False: 步骤摸鱼了, 应触发 AUTO-RECOVER

判定规则:
    - paper-figure / nature-figure / experiment-bridge: 必须有「数据类」新增图
      (排除 drawio/tikz 前缀, 因为那些是 paper-figure-drawio 的产出)
      ⛔ 例外: figures/ 已有该步骤应有的「数据类」图 + 本步骤未新增任何文件
              → 视为 rerun 时 SKILL 的「恢复检查」让 Claude 合法跳过, 放行
    - paper-figure-drawio: 必须有「架构图类」新增图(drawio 前缀或 tikz_)
      ⛔ 例外同上: figures/ 已有架构图 + 本步骤无新增 → 合法跳过
    - 用户开关 skip_figures/skip_drawio: 直接放行(理论上前置已跳过, 防御性)
    - PAPER_PLAN.md 声明无图表: 放行(纯文字论文场景)
```

#### `_check_figures_step_health_static(workspace: 'Path', skill_name: 'str', params: 'Dict[str, Any]') -> 'Tuple[bool, str]'`

```
图表步骤健康检查(静态版, 不依赖 files_created)。

用于崩溃恢复 / waiting_checkpoint 等无法获取增量的场景。
退化为「figures/ 下当前是否存在该步骤应有的图类」。
```

#### `_check_paper_body_pages(workspace: 'Path', skill_name: 'str', max_pages: 'Optional[int]', page_policy: 'str' = 'advisory_max') -> 'tuple'`

```
按竞赛页数语义做保守的正文字符预检。

正文定义：
- LaTeX 模式：`paper/sections/*.tex` 总字符数
- Word 模式：`paper/main.md` 中"## 附录"之前的部分
- 中文 chars_per_page ≈ 800（含图表），英文 ≈ 2200

Returns: (ok: bool, reason: str)
```

#### `_check_step_companions(workspace: 'Path', skill_name: 'str') -> 'tuple'`

```
检查二级文件是否齐全. 返回 (ok: bool, missing: List[str]).

每个文件要求:
    - 文件存在
    - 文件大小 > 50 字节 (防空文件占位)
```

#### `_classify_manifest_by_sections(block: 'str') -> 'Tuple[List[str], List[str]]'`

```
按 FIGURE_MANIFEST 的章节标题把图名归类(权威, 优先于文件名前缀)。

manifest 三章节标题形如(paper-plan/SKILL.md 约定):
    **数据图（matplotlib gen_fig_*.py，paper-figure 产出 .png/.pdf）：**
    **DrawIO 流程/架构图（paper-figure-drawio 产出 .drawio + .png/.pdf）：**
    **TikZ 图（paper-figure 产出 tikz_*.pdf）：**

归属按「哪个步骤产出」决定, 与健康检查的步骤对账口径一致:
    · 数据图章节              → data_figs   (paper-figure 产出)
    · DrawIO/HTML 章节 + TikZ 章节 → drawio_figs (paper-figure-drawio/-html 产出)

⛔ 只认 ** 粗体章节标题里的关键词, 不看图名前缀 —— 这样
   fig_data_pipeline/fig_model_arch 这类「关键词在中间」的架构图不会被误判。

识别不到规范章节结构(无章节标题, 或有图名落在任何章节之前)时返回 ([], []),
交由调用方 fallback 到前缀分类。
```

#### `_comp_en_steps()`

```
返回英文竞赛通用步骤列表。
```

#### `_comp_zh_steps(first_skill='comp-prob-analysis', paper_skill='comp-paper-zh')`

```
返回中文竞赛通用步骤列表。

Most Chinese competitions share the same writing contract.  Huawei Cup is
the deliberate exception: it has its own graduate-level mechanism and
solver-depth Skill, so callers can select it without duplicating the DAG.
```

#### `_compress_claude_md(workspace: 'Path')`

```
空工具调用智能恢复：压缩 CLAUDE.md 中的图片描述和冗余内容，减少 prompt 大小。

典型场景：paper-figure 步骤运行时上下文累积到 110K tokens，导致 Claude 输出被截断。
压缩策略：
1. 图片描述截断为摘要（每张图最多 100 字）
2. 文档原文截断（每个文档最多 500 字）
3. 删除重复的规则段落
```

#### `_compute_health_blocks(skill_name: 'str', health_ok: 'bool') -> 'bool'`

```
Edits alone never substitute for mandatory computation outputs.
```

#### `_count_existing_figs_for(workspace: 'Path', names: 'List[str]') -> 'Tuple[int, List[str]]'`

```
检查 names 中有多少个图已经实际产出 (任意 .png/.pdf/.drawio 都算)。

Returns: (产出数, 缺失的名字列表)
```

#### `_describe_workspace_images(workspace: 'Path', content: 'str', workflow_id: 'str | None' = None) -> 'str'`

```
扫描工作区中的图片文件，用 vision LLM 描述内容，追加到 CLAUDE.md 正文中。

workflow_id 可选：传了就把识别进度推到前端日志区（这一步也跑在步骤循环之前，
不推就是一段静默）。不传则退化成原行为，不影响其它调用方。
```

#### `_detect_grad_project_type(workspace: 'Path') -> 'str'`

```
从工作区 CLAUDE.md 读「一句话生成项目」的 project_type。
读不到默认 fullstack。CLAUDE.md 里 params 段会写 `- project_type: xxx`。
```

#### `_extract_pdf_with_vision(workspace: 'Path', workflow_id: 'str', progress_callback: 'Optional[Callable[[str], Awaitable[None]]]' = None)`

```
Bounded, source-versioned OCR; partial results are never called complete.
```

#### `_generate_claude_md(workspace: 'Path', title: 'str', template: 'str', params: 'dict')`

```
在工作区生成 CLAUDE.md，为 Claude CLI 提供项目上下文。
```

#### `_has_vision_extraction(pdf_file: 'Path') -> 'bool'`

```
Whether this exact workspace PDF already has a usable vision transcript.
```

#### `_health_requires_repair(workspace, skill_name, primary, health_ok, reason, quality_failure, files_created=(), files_modified=()) -> 'bool'`

```
Never let auxiliary changes override deterministic missing artifacts.

Retain the prior advisory treatment of size/page heuristics; they are not
authority to rewrite a correct manuscript. Explicit figure, computation,
companion, checker and submission failures cannot be converted to success.
```

#### `_inject_once(claude_md: 'Path', marker: 'str', content: 'str') -> 'bool'`

```
幂等地把 content 追加到 CLAUDE.md。

通过 marker 检测是否已注入过。重跑步骤、心跳自愈、崩溃恢复等场景下
避免重复追加同一段提示导致上下文污染。

用法（替代 with open(claude_md, "a") as f: f.write(text)）：
    _inject_once(claude_md, "INJECT_PLAN_GUIDANCE", notes_text)

Args:
    claude_md: CLAUDE.md 文件路径
    marker: 唯一标识（建议大写 + 下划线，如 "INJECT_DOCX_TABLE_RULES"）
    content: 要追加的内容（marker 会自动包装在 HTML 注释里）

Returns:
    True 表示真的写入了；False 表示已存在 marker，跳过。
```

#### `_is_drawio_fig(rel_path: 'str') -> 'bool'`

```
判断 figures/ 下的文件路径是否属于 drawio/tikz 架构图类。
```

#### `_mark_active_step_failed(db, workflow_id: 'str', exc: 'BaseException') -> 'tuple[list[str], str]'`

```
Atomically terminate the workflow and every active step.

Runner setup can fail before a Claude subprocess exists (for example a
Capsule/runtime mismatch).  Historically the outer exception handler only
marked ``workflows`` failed, leaving ``workflow_steps`` permanently
``running`` with no durable reason.  Keep both tables and the audit log in a
single transaction so the UI can never observe that split-brain terminal
state after the commit.
```

#### `_mark_workflow_preparing(db, log_db, workflow_id: 'str') -> 'None'`

```
Expose real pre-step work during start and crash recovery.

``init_db`` first normalizes interrupted workflows to ``paused``.  The
recreated task can then spend minutes extracting documents or calling
Vision before a Skill starts.  Persisting this state immediately prevents
the dashboard and durable log from presenting that live work as idle.
```

#### `_min_size_for(skill_name: 'str', primary_output: 'Optional[str]' = None) -> 'int'`

```
获取该 skill 的 primary_output 最低字节阈值, 默认 100。

primary_output: 该步骤实际的主产物路径。docx 模式下改进循环的产物是
`paper/main.md`(Markdown), 而非默认的 50KB PDF, 用 PDF 阈值会误判失败,
因此对 markdown 产物使用更合理的下限。
```

#### `_needs_pdf_vision(pdf_file: 'Path', *, now: 'Optional[float]' = None) -> 'bool'`

```
Return false for a good cache or a recent transient all-page failure.

Successful OCR is reused indefinitely while its transcript exists.  A full
fallback is retried after a short cooldown, and replacing the source PDF
invalidates the cooldown immediately through the source signature.
```

#### `_notify_vision(workflow_id: 'str', text: 'str') -> 'None'`

```
推一条预处理进度到前端日志区。

⛔ 只吞 Exception，不能写成 except BaseException / 裸 except：CancelledError 继承自
BaseException，一旦在这里被吞掉，用户点暂停就对整个 vision 阶段失效了。
推送失败本身无所谓 —— 前端还有 5~8 秒轮询兜底。
```

#### `_paper_submission_report(result: 'object', workspace: 'Path', skill_name: 'str')`

```
Prefer the gate run inside ClaudeRunner's authenticated utility scope.
```

#### `_pause_for_access_mode(db, workflow_id: 'str', exc: 'AccessModeError | AccountError') -> 'None'`

```
Startup recovery must not relabel unavailable billing as model failure.
```

#### `_pause_for_check(db, workflow_id: 'str', exc: 'StepCheckPending') -> 'None'`

```
Commit step/workflow/diagnostic together before broadcasting a pause.
```

#### `_pause_for_protected_content(db, workflow_id: 'str', exc: 'ProtectedContentUnavailable', *, log_db=None) -> 'None'`

```
Persist a safe Skill/License preparation diagnostic before pausing.

Packaged clients used to clear ``error_message`` here and only emit the
``workflow_license_required`` event.  Re-opening the workflow therefore
showed a blank pending card, and clicking Continue immediately hit the
same Capsule/License condition again.  Keep the pause fail-closed, but
make the reason durable and actionable.  No plaintext Skill or provider
credential is copied into the workflow record.
```

#### `_pdf_vision_state_path(pdf_file: 'Path') -> 'Path'`

```
Internal retry ledger; deliberately excluded from public artifacts.
```

#### `_pdf_vision_targets(workspace: 'Path') -> 'list[Path]'`

```
Return the deterministic PDF set shared by automatic and chat modes.

The explicitly selected problem statement is always included.  A small
number of ordinary PDF attachments are also included, matching the legacy
automatic-workflow policy without letting a large reference library trigger
unbounded vision calls.
```

#### `_pfa_safety_copy_assets(workspace: 'Path') -> 'dict'`

```
paper_from_assets 兜底: 把 user_data/ 里的资产复制到工作目录的标准位置。

assets-inventory skill 的 SKILL.md 里会要求 Claude 自己复制文件,
但万一 Claude 漏了某些文件, 这里做引擎层兜底, 确保:
- user_data/*.py / *.ipynb / *.zip → code/
- user_data/*.csv / *.xlsx / *.tsv / *.json → data/ (排除 results.json)
- user_data/*.png / *.jpg / *.jpeg / *.svg → figures/user_fig_*
- user_data/*.tex / *.cls / *.sty / *.docx / *.dotx → _user_templates/

返回复制统计 dict, 用于注入提示。

幂等: 同名文件已存在则跳过。
```

#### `_plan_says_no_figures(workspace: 'Path') -> 'bool'`

```
检查 PAPER_PLAN.md / PROBLEM_ANALYSIS.md / TOPIC_PLAN.md 是否声明本论文无图表
(纯文字综述/思辨论文场景)。
```

#### `_post_edit_issues(workspace, skill_name, primary, template, params, changed, *, progress, cancelled)`

```
Same current-output gates after required or optional edits in both entries.
```

#### `_prepare_paper_data_checklist(workspace: 'Path', mode: 'str') -> 'int'`

```
Build the deterministic evidence checklist before the writing call.
```

#### `_primary_output_health(workspace: 'Path', skill_name: 'str', primary: 'Optional[str]') -> 'tuple[bool, str]'`

```
Same artifact/type checks on first execution, retry and checkpoint edits.
```

#### `_primary_output_size(workspace: 'Path', skill_name: 'str', primary_path: 'Path') -> 'int'`

```
Return meaningful source size for a possibly split LaTeX manuscript.

``paper/main.tex`` is often only an assembly file whose real content lives
under ``paper/sections``.  Measuring the root alone falsely classified a
complete split manuscript as an empty shell and launched paid retries.
```

#### `_process_retry_policy(result: 'Optional[dict]', *, allow_unfinished_turn: 'bool' = True) -> 'tuple[str, int]'`

```
Classify a failed runner result and return ``(kind, retry_budget)``.

The budget is the number of *additional* model processes allowed.  It does
not weaken any output gate: after the budget is exhausted the step fails
visibly instead of repeatedly submitting an identical request.
```

#### `_public_workflow_error(exc: 'BaseException') -> 'str'`

```
Return a bounded diagnostic safe to persist and show in the client.
```

#### `_read_assets_index(workspace: 'Path') -> 'dict'`

```
读取 assets-inventory 步骤产出的 _assets_index.json。

paper_from_assets 工作流用这个 index 决定后续 paper-analysis/paper-figure/
paper-figure-drawio 是否要跑。如果文件不存在或解析失败, 返回安全的默认值
(所有 has_* 都为 False, 这样后续步骤会按"全自动模式"跑)。

Returns:
    dict, 形如:
    {
        "has_problem": bool,
        "has_code": bool,
        "has_data": bool,
        "has_figures": bool,
        "has_results": bool,
        "has_templates": bool,
        "missing_assets": [str, ...],
        "conflicts": [{"type": str, "severity": str, "files": [...]}, ...],
        "conflict_count": int,
        "high_severity_count": int,
    }
```

#### `_read_figure_manifest(workspace: 'Path') -> 'Tuple[List[str], List[str]]'`

```
从 PROBLEM_ANALYSIS.md / PAPER_PLAN.md / MODELING_REPORT.md 读
<!-- BEGIN FIGURE_MANIFEST --> 区块, 提取规划的图表名字。

Returns: (data_figs, drawio_figs)
    - data_figs:    数据图章节 (paper-figure 应产出)
    - drawio_figs:  DrawIO/HTML 章节 + TikZ 章节 (paper-figure-drawio/-html 应产出)
    - 找不到 manifest 时返回 ([], [])

分类优先级:
    1. 按 manifest 三章节标题归类(权威) —— 见 _classify_manifest_by_sections
    2. 无规范章节结构时 fallback 到文件名前缀分类(旧逻辑, 对
       「关键词在中间」的架构图会误判, 仅作兜底)
```

#### `_record_pdf_vision_attempt(pdf_file: 'Path', status: 'str', *, attempted_at: 'Optional[float]' = None) -> 'None'`

```
Atomically retain only bounded retry metadata, never OCR text or secrets.
```

#### `_record_step_progress(db, workflow_id: 'str', skill_name: 'str', message: 'str', *, phase: 'Optional[str]' = None, level: 'str' = 'info') -> 'None'`

```
Persist and broadcast a user-readable long-running phase boundary.

Raw runner output can be sparse while a model is reading files or a local
command is executing.  These bounded messages survive reconnects and make
every additional paid model pass explicit without exposing prompts,
commands, keys, or hidden reasoning.
```

#### `_recovery_outputs_pass(workspace, skill_name, primary, template, params, *, progress, cancelled)`

```
A later completed step is not evidence that these current files passed.

Reuse the normal current-artifact checks, including stale PDF repair. This
path never invokes a model and advisory-only issues do not force a rerun.
Missing evidence returns to the normal bounded repair path, not success.
```

#### `_required_companions_for(skill_name: 'str', workspace: 'Optional[Path]' = None) -> 'List[str]'`

```
获取该 skill 必须存在的二级文件列表.

dev-code 特殊: 必需文件按项目类型区分 (纯前端/CLI/脚本没有 code/backend/main.py,
强制要求会误判失败)。全栈才要后端入口, 其余只要 code/ 下有主入口 + RUN.md。
```

#### `_resolve_competition_page_rule(template: 'str', params: 'Optional[dict]') -> 'tuple'`

```
Return the final-submission page reference for one competition.

Every competition uses ``advisory_max`` locally: the value is visible to the
user but never becomes a generation, expansion, or compression gate.
```

#### `_resolve_step_effort(params: 'Optional[Dict]', skill_name: 'str') -> 'str'`

```
解析工作流某步应使用的思考强度（Claude CLI `--effort`）。

取值优先级（与 _resolve_step_model 同一条链）：
  params.step_efforts[skill] > params.effort（整个工作流统一）
  > 全局设置 default_effort > ""（不传 flag，等价于 API 默认 high）

查库异常 / 脏值 / params 为 None → 一律返回 ""，执行时不带该参数。
绝不因为「设个思考强度」把执行搞崩 —— 与 _resolve_step_model 的容错口径一致。
```

#### `_resolve_step_model(params: 'Optional[Dict]', skill_name: 'str') -> 'Optional[Dict]'`

```
解析工作流某步应覆盖的 executor 模型 {model_id, api_key}。
取值优先级：params.step_models[skill] > params.model_preset_id（整个工作流统一）> None（回退角色默认/全局）。
显式选择的预设失效时暂停；只有未选择预设才返回 None。
```

#### `_resolve_template(template: 'str', params: 'dict', workspace: 'Path') -> "'TemplateDef'"`

```
根据 params 动态重写 template 的 sub_steps（中文替换 / docx 模式 / format-profile 插入）。

创建工作流时和运行时都用这个函数，确保 tmpl.sub_steps 与数据库中的 step list 完全一致，
避免 step_index 错位导致 expected_outputs 张冠李戴。
```

#### `_run_native_docx_precheck(source: 'Path', workspace: 'Path', word_count=None)`

```
Check current source before EVERY conversion; diagnostics stay external.
```

#### `_run_recovery_skill(db, owner_workflow_id: 'str', visible_skill: 'str', **kwargs) -> 'dict'`

```
Safe retries for *repair* calls too, not only the initial main call.
```

#### `_scan_workspace(workspace: 'Path') -> 'List[str]'`

```
扫描工作区，返回非隐藏文件列表，排除 CLAUDE.md 等系统文件。
```

#### `_serialize_workspace(func)`

```
Background writers wait their turn instead of failing a workflow.
```

#### `_should_skip_step_by_assets(workspace: 'Path', skill_name: 'str', template: 'str') -> 'tuple[bool, str]'`

```
对 paper_from_assets 工作流, 根据 _assets_index.json 决定是否跳过当前步骤。

决策规则:
- paper-analysis: 如果用户已传 code + results, 跳过(不要重跑覆盖)
- paper-figure: 如果用户已传 figures 且没有 missing 标识缺图, 跳过
- paper-figure-drawio: 如果 figures/ 中已有 fig_roadmap.* 或不在 missing_assets 中提到 roadmap, 跳过

Args:
    workspace: 工作区路径
    skill_name: 当前 step 的 skill 名
    template: 工作流模板名(只对 paper_from_assets 生效)

Returns:
    (should_skip, reason): 是否跳过, 跳过原因
```

#### `_step_data_problem(workspace: 'Path', skill_name: 'str', template: 'str', params: 'dict') -> 'str'`

```
Single-step delivery must not skip deterministic data errors.

Missing model self-attestation alone is not a broken artifact. Only an
explicit fatal, or inability to perform the required check, blocks here.
```

#### `_step_inactivity_timeout(skill_name: 'str') -> 'int'`

```
Bound silent model calls without shortening any visible work.

Competition manuscript and compile steps should continuously emit tool or
compiler events.  Forty-five silent minutes indicates a stalled provider
request, not productive writing; other legacy steps keep the conservative
ninety-minute allowance.
```

#### `_template_step_for(tmpl: "'TemplateDef'", skill: 'str', params: 'dict') -> "'StepDef | None'"`

```
Bind output/quality contracts by identity, never a stale ordinal.

Imported/custom workflows can omit or insert steps. Using step_order as
an index into today's template attaches another Skill's output contract.
```

#### `_wait_for_extracts(workspace: 'Path', timeout_sec: 'int' = 300, poll_interval: 'float' = 1.0) -> 'None'`

```
等待 user_data 目录所有 PDF/DOCX 异步提取完成 (done 或 failed).

异步提取由 services/extract_worker.schedule_extract 排队,
状态记录在 user_data/.extract_status.json.

超时 (默认 5 分钟) 也直接返回, 不阻塞 workflow 启动 —
单个文件提取失败不应该让整个 workflow 失败.
```

#### `_write_step_handoff(workspace: 'Path', workflow_id: 'str', skill_name: 'str', outputs: 'List[str]') -> 'Path'`

```
Atomically record artifact evidence used by the next Skill/new session.
```

#### `check_exported_docx_submission_contract(workspace: 'Path', docx_path: 'Path', skill_name: 'str', *, checker_root: 'Path | None' = None, write_reports: 'bool' = True) -> 'PaperSubmissionContractReport'`

```
Validate the final Word artifact, using real pagination when possible.
```

#### `check_paper_modeling_quality(workspace: 'Path', skill_name: 'str', *, write_report: 'bool' = True) -> 'ModelingQualityReport'`

```
Compare upstream formulation depth with the completed paper.

Detect definite structural omissions. A passing result does not certify the
derivation: the writer must still compare each mechanism chain against its
actual formulation and solver, as described in the shared paper contract.
```

#### `check_paper_submission_contract(workspace: 'Path', skill_name: 'str', *, require_compiled: 'bool | None' = None, checker_root: 'Path | None' = None, write_reports: 'bool' = True, final_source: 'bool' = False) -> 'PaperSubmissionContractReport'`

```
Check the phase-appropriate paper submission contract.

LaTeX writing steps run only deterministic source checks: no directory or
forced body page break, numbered display math, and the abstract's source
structure/content contract.  The final compiler step owns rendered-page,
style, AI-language and report/PDF snapshot checks. Word has a later native
export step too: that step requests final_source before accepting delivery.
```

#### `clear_pause_request(workflow_id: 'str') -> 'None'`

```
清除暂停标记。⛔ 所有启动路径（start/resume/restart/rerun/心跳复活/重启恢复/
检查点续跑）都必须调用，否则工作流会在下一步立刻自杀、再也起不来。
```

#### `context_overflow_action(result: 'Mapping[str, object] | None', attempt: 'int') -> 'str | None'`

```
Return the only safe retry decision for an Autocompact rapid refill.

A context overflow is deterministic for the same fixed prompt. Retrying it
through a generic eight-attempt loop only repeats the cost. The caller may
rebuild a compact prompt once; if that compact attempt also trips the
breaker it must stop and surface an actionable error.
```

#### `core_file_problem(workspace: 'Path', skill: 'str', path: 'Path') -> 'str'`

```
Return a proven core defect (or unavailable check), never a size hint.
```

#### `effective_skill_name(skill: 'str', params: 'dict') -> 'str'`

```
The same trusted variant mapping must serve planning and execution.
```

#### `finish_local_operation(operation: 'Callable[[], object]')`

```
Keep the workspace lock until a non-cancellable worker stops writing.

Cancelling asyncio.to_thread does not stop the thread. Deferring the
cancellation prevents pause/restart from launching a second export while
the first converter is still writing the same file.
```

#### `format_workspace_index(files: 'Iterable[object]', *, max_chars: 'int' = 12000, max_visible_files: 'int' = 160) -> 'str'`

```
Return a deterministic, strictly bounded model-facing file index.

Small workspaces retain their complete file list.  Large raw-data trees are
represented by exact counts, extension distributions and deterministic
first/middle/last examples.  The summary is only a prompt optimisation: it
never changes the caller's complete list or the files on disk.
```

#### `materialize_skill_templates(skill_name: 'str', skill_package: 'Path', workspace_path: 'Path', *, template_skill_name: 'Optional[str]' = None, progress: 'Optional[Callable[[str], Awaitable[None]]]' = None) -> 'bool'`

```
Install the authenticated template tree required by ``skill_name``.

Template ownership is explicit.  In particular, the Huawei writer uses
the signed ``comp-paper-zh/templates/huawei`` bundle; it must never silently
fall back to a generic ``ctexart`` document when that bundle is missing.
The same helper is used by the workflow pre-copy stage and by the runner so
the first writing step sees exactly the tree that the CLI sees.
```

#### `normalize_ai_disclosure(params: 'dict', *, strict: 'bool' = True) -> 'dict | None'`

```
Return a canonical disclosure payload or ``None`` when disabled.

``strict=False`` is used only while reopening legacy workflows.  It still
never invents missing facts; instead it returns an explicit invalid marker
which makes the paper step stop and request a fresh, truthful declaration.
```

#### `payer_task(identity)`

```
Create a durable task context; nested tools inherit the outer task.

Identity receives bound function arguments. Scope creation is I/O-free;
capture happens at the first model boundary, inside the caller's own safe
pause/error handling. Context follows asyncio tasks and asyncio.to_thread.
```

#### `pending_check_state(step: 'dict') -> 'dict[str, str]'`

```
Durable pause metadata in the existing diagnostic column (old DB safe).

It is not a successful-execution receipt. Continuing still evaluates the
current step and all its checks; no existing file is treated as approval.
```

#### `protected_content_error(exc: 'Exception') -> 'ProtectedContentUnavailable'`

```
Expose a bounded error code and action, never raw remote error text.
```

#### `recover_checked_step(*, check: 'Callable[[], Awaitable[list[CheckIssue]]]', repair: 'Callable[[str, int], Awaitable[None]]', snapshot: 'Callable[[], object]', progress: 'Callable[[str, str], Awaitable[None]]', cancelled: 'Callable[[], bool]', max_repairs: 'int' = 3, max_local_rechecks: 'int' = 2, max_advisory_repairs: 'int' = 1) -> 'int'`

```
Recheck *all* gates after each targeted repair; return actual repairs.

Cancellation, unavailable checkers and unsafe runner failures propagate.
A first unchanged repair gets one fresh diagnostic attempt; a second
unchanged repair stops. A changed reason is progress even without edits.
Advisory-only findings get a separate best-effort budget, never consume
hard repair attempts and never prevent completion on their own. Any hard
defect introduced by optimization must pass the same checks again.
Unresolved blocking issues never become successful execution.
```

#### `repair_attempt_prompt(reason: 'str', attempt: 'int') -> 'str'`

```
A further repair must investigate current evidence, not replay prose.
```

#### `report_from_runner_result(result: 'object', skill_name: 'str') -> 'PaperSubmissionContractReport | None'`

```
Read a trusted runner-side report and reject inconsistent payloads.
```

#### `request_pause(workflow_id: 'str') -> 'None'`

```
标记用户要求暂停。pause 接口调用，步骤循环每步开头检查。
```

#### `require_execution_mode()`

```
Admit only explicitly wired account execution; never resolve a Key.
```

#### `retry_unavailable_check(check)`

```
One retry of an idempotent tuple/report check, never a workflow step.

Resolve/materialize tools again to recover stale paths and transient file
locks. Content failures are returned immediately to focused repair. Keep
this at the outer check boundary, not around every nested subprocess.
```

#### `run_single_step(workflow_id: str, skill_name: str)`

```
单独执行工作流中的单个步骤。
```

#### `run_workflow(workflow_id: str, *, _only_native_skill: str | None = None)`

```
逐步执行子步骤。支持从暂停处恢复（跳过已完成步骤）。
```

#### `submission_advisories(report: 'object')`

```
Preserve explicit advisory severity; never downgrade an error by text.
```

#### `submission_repair_prompt(reason: 'str', skill_name: 'str') -> 'str'`

```
One phase-aware repair contract for automatic and collaborative runs.
```

#### `unfinished_sections(workspace: 'Path') -> 'list[str]'`

```
Only empty/explicitly unfinished active chapters warrant continuation.

Short valid chapters and unused drafts are not incomplete work. Before
main.tex exists, the current plan can still identify missing draft files.
Missing inputs in an assembled paper remain the compiler's responsibility.
```

#### `update_workflow(db: 'aiosqlite.Connection', wf_id: 'str', **fields) -> 'None'`

```
更新工作流字段，带重试逻辑应对并发锁竞争。
```

### 仅有签名（27）

```python
_compute_repair_prompt(reason: 'str') -> 'str'
_create_new_workflow(template: 'str', title: 'str', params: 'dict', enable_checkpoints: 'bool' = False) -> 'str'
_docx_advisories(report, plan_skills)
_docx_repair_skill(plan_skills, reason: 'str' = '') -> 'Optional[str]'
_figure_repair_prompt(workspace: 'Path', skill_name: 'str', reason: 'str') -> 'str'
_focused_quality_repair_prompt(reason: 'str', skill_name: 'str') -> 'str'
_load_pdf_vision_state(pdf_file: 'Path') -> 'dict'
_notify(workflow_id: 'str', event: 'dict', *, db=None)
_paper_data_mode(skill_name: 'str', template: 'str', params: 'Optional[dict]') -> 'str'
_pdf_vision_signature(pdf_file: 'Path') -> 'str'
_present_checkpoint(db, workflow_id: 'str', payload: 'dict') -> 'dict'
_recovery_failure_message(reason: 'str', attempts: 'int', quality: 'bool', stalled: 'bool') -> 'str'
_repair_docx_source(db, workflow_id, visible_skill, plan_skills, workspace, params, title, source, reason, attempt)
_repair_progress_candidates(skill_name: 'str', expected: 'List[str]', primary: 'str', workspace: 'Path | None' = None) -> 'List[str]'
_require_successful_skill_result(result: 'object', phase: 'str') -> 'None'
_skill_template_dependencies(skill_name: 'str') -> 'tuple[str, ...]'
checker_environment() -> 'dict[str, str]'
checker_unavailable(detail: 'str') -> 'bool'
create_new_workflow(template: 'str', title: 'str', params: 'dict', enable_checkpoints: 'bool' = False) -> 'str'
create_workflow(db: 'aiosqlite.Connection', wf: 'dict') -> 'None'
get_db() -> 'aiosqlite.Connection'
is_pause_requested(workflow_id: 'str') -> 'bool'
licensed_plan_skills(skills: 'list[str]', params: 'dict') -> 'list[str]'
materialize_ai_disclosure_manifest(workspace: 'Path', params: 'dict', *, strict: 'bool' = True) -> 'dict | None'
prepare_task_payers()
set_broadcast(fn)
step_recovery_state(workflow_id: 'str', skill_name: 'str') -> 'dict[str, str]'
```

## 可安全试探调用的零参函数（候选 23）

- `_await_recovery(invocation, *, timeout)`
- `_comp_en_steps()`
- `_comp_zh_steps(first_skill='comp-prob-analysis', paper_skill='comp-paper-zh')`
- `_compress_claude_md(workspace: 'Path')`
- `_docx_advisories(report, plan_skills)`
- `_extract_pdf_with_vision(workspace: 'Path', workflow_id: 'str', progress_callback: 'Optional[Callable[[str], Awaitable[None]]]' = None)`
- `_generate_claude_md(workspace: 'Path', title: 'str', template: 'str', params: 'dict')`
- `_notify(workflow_id: 'str', event: 'dict', *, db=None)`
- `_paper_submission_report(result: 'object', workspace: 'Path', skill_name: 'str')`
- `_post_edit_issues(workspace, skill_name, primary, template, params, changed, *, progress, cancelled)`
- `_recovery_outputs_pass(workspace, skill_name, primary, template, params, *, progress, cancelled)`
- `_repair_docx_source(db, workflow_id, visible_skill, plan_skills, workspace, params, title, source, reason, attempt)`
- `_run_native_docx_precheck(source: 'Path', workspace: 'Path', word_count=None)`
- `_serialize_workspace(func)`
- `finish_local_operation(operation: 'Callable[[], object]')`
- `payer_task(identity)`
- `prepare_task_payers()`
- `require_execution_mode()`
- `retry_unavailable_check(check)`
- `run_single_step(workflow_id: str, skill_name: str)`
- `run_workflow(workflow_id: str, *, _only_native_skill: str | None = None)`
- `set_broadcast(fn)`
- `submission_advisories(report: 'object')`

