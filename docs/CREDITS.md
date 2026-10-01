# 素材来源与许可证合规说明

核查日期：2026-10-01。本工程为**从零原创实现**，以下记录"能用什么、不能用什么"及依据，避免日后踩许可证的坑。

## 一、明确**未使用**的闭源资产

| 对象 | 状态 | 本工程的处理 |
|---|---|---|
| Modex · MH Agent（`N-allpass/modex-mh-agent`） | 仓库仅含 `.gitignore`/`README.md`/`assets/`（无源码，`license` 字段为 null），页脚标注"保留所有权利"；软件本体为闭源 Electron 应用（`resources/app/**` 为 `.pyc`） | **仅参考其公开文档描述的架构思想**；不复制其代码、Skill 文案、界面与品牌资源 |
| `jihe520/Modemon` | **无 LICENSE**（`/license` 404） | 只借鉴思路，不抄代码 |
| `SakanaAI/AI-Scientist` | 非 OSI 许可（禁止未显著声明地生成/传播论文手稿） | **不使用** |
| `latexstudio/CUMCMThesis`（国赛模板） | 官方仓库**无许可证文件**，`/license` 404，不在 CTAN；网传 LPPL 出自第三方 fork | **不拷贝其 `.cls`/`.sty`**；国赛排版自行编写 |
| DeepSeek 官方文档的模型旧名 `deepseek-chat` / `deepseek-reasoner` | 2026-04-24 公告、2026-07-24 停用 | 配置中不使用旧名 |

## 二、可复用的开源素材（均可商用/修改，需保留原作者版权声明）

| 项目 | 许可证 | 用途 | 地址 |
|---|---|---|---|
| Auto-claude-code-research-in-sleep（ARIS） | MIT | 自动化科研工作流理念、跨模型评审回路设计 | https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep |
| PaperSpine | MIT | 论文全流程编排思路 | https://github.com/WUBING2023/PaperSpine |
| ChineseResearchLaTeX | MIT | 中文科研 LaTeX 模板与工具链 | https://github.com/huangwb8/ChineseResearchLaTeX |
| scientific-agent-skills | MIT | 科研 Skill 集（注意其内置数据源可能另有条款） | https://github.com/K-Dense-AI/scientific-agent-skills |
| humanities-thesis-skill | MIT | 评审规则与反幻觉护栏设计 | https://github.com/ganzhi-black/humanities-thesis-skill |
| lunwen-skill | MIT | 中文论文初稿组织方式 | https://github.com/Doryoku1223/lunwen-skill |
| mcmthesis | LPPL 1.3c | 美赛 LaTeX 模板（TeX Live 自带，改动后须改名） | https://ctan.org/pkg/mcmthesis |
| mathodology | MIT | 数模竞赛 Skill 组织方式 | https://github.com/sweetcornna/mathodology |
| Y-love-han/math-modeling-skill | MIT | "证据优先 + 状态机 + 哈希账本" 的门禁设计 | https://github.com/Y-love-han/math-modeling-skill |
| OpenHands / MetaGPT / gpt-researcher / paper-qa / AgentLaboratory | MIT / MIT / Apache-2.0 / Apache-2.0 / MIT | 执行体、多智能体 SOP、调研、带引用 RAG 等参考 | 见各自仓库 |

> 若后续直接复用上述任一项目的代码或提示词，**必须**在本文件与 `NOTICE` 中保留其版权与许可证全文。

## 三、DeepSeek API 事实（2026-10-01 快照）

| 项 | 值 |
|---|---|
| OpenAI 兼容 base_url | `https://api.deepseek.com` |
| 现行模型名 | `deepseek-flash`（V4.1-Flash）、`deepseek-v4-pro`（V4-Pro-0813） |
| 旧名 `deepseek-chat` / `deepseek-reasoner` | 2026-07-24 起停用，**不要再用** |
| 上下文 / 最大输出 | 1M tokens / 384K tokens |
| JSON 输出 | 支持：`response_format={"type":"json_object"}`，且提示词中必须出现 "json" |
| 工具调用 | 支持；`strict` 模式为 Beta，需 `base_url=.../beta` |
| 思考模式 | 默认开启，`reasoning_effort` 可选 low / high / max |
| 价格（每 1M tokens，flash） | 输入缓存命中 低谷 $0.003 / 高峰 $0.006；未命中 低谷 $0.15 / 高峰 $0.30；输出 低谷 $0.60 / 高峰 $1.20 |
| 高峰时段 | UTC 周一至周五 01:00–04:00 与 06:00–10:00；低谷价为其一半（中国法定节假日全天低谷） |
| 免费评审者渠道 | ModelScope 推理 API（`https://api-inference.modelscope.cn/v1`，每日总量约 2000 次）；硅基流动部分小模型免费。额度为第三方快照，上线前需自查 |

**省钱建议**：批量跑在低谷时段可省一半；评审者先用免费通道，确认流水线稳定后再考虑 `deepseek-v4-pro`。

## 四、学术诚信

本工具是辅助工具。生成的论文、数据与引用**必须人工复核**；参加竞赛与投稿论文须遵守相应学术规范，最终责任在使用者本人。
