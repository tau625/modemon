# 实操手册

从「拿到赛题」到「拿到可编译论文」的完整操作流程，含真实运行的耗时与用量参考。

## 一、准备

```powershell
cd E:\Projects\Modemon
$py = .venv\Scripts\python.exe

# 1) 依赖（已装可跳过）
uv pip install --python $py -e ".[dev,solve]" --index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 2) 密钥：复制后填入你自己的 Key（.env 已被 gitignore，不会进版本库）
copy .env.example .env
notepad .env

# 3) 连通自检（不打印密钥）
& $py scripts\probe_api.py

# 4) 环境自检：依赖、LaTeX、Key、Skill、流水线
& $py -m modemon doctor
```

自检里如果显示 `xelatex 未找到`，论文就无法编译——请确认 TeX Live 已加入 PATH。

## 二、准备赛题

`--problem` 直接支持四种格式：`.txt / .md / .pdf / .docx`。

- PDF **必须有文本层**；扫描件会明确报错（需先 OCR）。
- 官方赛题的 Word/PDF 直接丢进去即可，不需要手工转文本。
- 建议同时把附件数据放到工程里，供求解代码读取（代码工作目录是 `runs/<run_id>/`，
  相对路径要相应调整，或让代码自行生成数据）。

## 三、开跑

```powershell
# 先离线跑一遍，确认管道通畅、不花钱
& $py -m modemon run -p 赛题.pdf --provider mock

# 真实运行
& $py -m modemon run -p 赛题.pdf --competition cumcm

# 关键环节人工把关
& $py -m modemon run -p 赛题.pdf --checkpoint modeling_design --checkpoint paper_writing

# 另开一个窗口看实时进度（浏览器打开 http://127.0.0.1:8765）
& $py -m modemon serve
```

### 真实参考数据（国赛 20 页规模，mimo-v2.6-flash 执行 + mimo-v2.6-pro 评审）

| 环节 | 耗时 | 说明 |
|---|---|---|
| 赛题解析 | ~19 min | 2 轮评审（8.2 → 8.1，未过线） |
| 建模设计 | ~18 min | 2 轮评审（8.3 → 7.7，未过线） |
| 求解实现 | ~15 min | 真实跑通 4 个脚本，评审 8.6 **通过** |
| 图表生成 | ~5 min | 一次产出 5 张 300 dpi 真图 |
| 论文大纲 | ~10 min | 评审 8.5 **通过** |
| 论文成文 | ~10–20 min | 单次生成完整 LaTeX |
| **合计** | **约 80–95 分钟** | 17+ 次调用，输入 ~27 万 / 输出 ~22 万 tokens |

> 耗时主要来自**思考模式**。想大幅提速：`--thinking off`，或在 `configs/pipeline.yaml`
> 给机械环节（如 `figures`）单独设 `thinking: "off"`。

## 四、运行后验收（务必按顺序）

```powershell
$run = "<run_id>"

# 1) 编译（--repair：失败时把报错回灌给执行者自动回修）
& $py -m modemon compile $run --repair

# 2) 双门禁：数值溯源 + 竞赛合规
& $py -m modemon check $run

# 3) 复盘报告（环节轨迹 / 门禁结论 / 产物清单）
& $py -m modemon report $run

# 4) 查看产物与评分轨迹
& $py -m modemon show $run
```

**人工复核清单**（自动化只能兜住机检项）：

- [ ] `runs/<id>/paper/main.pdf` 打开看排版：图表位置、公式编号、参考文献是否规范
- [ ] 摘要是否每一问都给出了**方法 + 具体数值结论**
- [ ] `mma check` 列出的**未匹配数字**逐个人工确认有无依据
- [ ] 参考文献是否真实存在（本工程**未做文献检索**，这是已知风险）
- [ ] 图表是否有遮挡、字体是否乱码、页数是否超限
- [ ] 结论与 `results/*.json` 的数值是否一致

## 五、迭代：改一版、几分钟验证

改完 Skill 或提示词后**不要重跑整条流水线**：

```powershell
# 只重跑论文成文（下游自动作废）
& $py -m modemon rerun $run paper_writing

# 只重跑图表，保留后面的产物
& $py -m modemon rerun $run figures --keep-downstream

# 从中断处续跑
& $py -m modemon resume $run
```

调优的三个抓手：

| 抓手 | 位置 | 影响 |
|---|---|---|
| 产出标准 | `skills/<环节>/SKILL.md` 正文 | 直接就是提示词，改完 `rerun` 那一环 |
| 评审严格度 | `run.pass_score`、`run.require_no_blockers` | 通过线 / 是否一票否决 |
| 评审口径 | `skills/review/SKILL.md` 的红线与数值规则 | 决定什么算"硬伤" |

## 六、常见问题

| 现象 | 原因与处理 |
|---|---|
| 报错「模型返回空内容（reasoning_content 长度 …）」 | 思考 token 吃光输出预算。已自动关思考重试；仍失败就调大对应角色的 `max_tokens` |
| 论文被截断（缺 `\end{document}`） | 长文环节的思考 token 挤占正文预算。已默认给 `paper_writing` 设 `thinking: "off"` 与 64000 上限；合规检查会拦住截断产物 |
| 单次调用超过 10 分钟没动静 | 非流式接口看不到中间进度属正常；`mma serve` 的监控页也只能看到调用开始/结束事件 |
| 成本显示 `$0.0000` | `pricing` 段落里没填该模型的单价——只统计 tokens，不编造金额 |
| 控制台中文乱码 | 终端编码问题，执行 `chcp 65001`；日志文件里是正常的 |
| 编译失败且回修无效 | 看 `results/compile.log` 的错误摘要；常见是图片路径或未装宏包 |
| 某环节一直「未达标」 | 看 `REPORT.md` 里最后一轮的必改项，多数是真问题；确认无误可调低 `pass_score` |
| 评审每轮都在挑新问题 | 检查提示词里是否带上了上一轮必改项（两段式核对机制） |
| 生成的代码跑不起来 | 看 `results/logs/*.log`；`mma rerun <run> solve_code` 可只重跑求解 |
| 想要更省钱 | 在低谷时段跑（UTC 高峰外）；`--thinking off`；评审者换免费额度渠道 |

## 七、学术诚信

本工具是**辅助工具**。生成的论文、数据与引用**必须人工复核**；参加竞赛或投稿请遵守相应的学术规范，
对最终成果负责的是使用者本人。建议在竞赛规则允许的范围内使用，并如实说明工具的使用情况。
