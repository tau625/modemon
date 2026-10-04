# ARIS(上游) vs Modex(蓝方) skill 标识符差分

ARIS 仓库: https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep

## ARIS 全部 skill (83)

`ablation-planner`, `alphaxiv`, `analyze-results`, `arxiv`, `auto-paper-improvement-loop`, `auto-review-loop`, `auto-review-loop-llm`, `auto-review-loop-minimax`, `citation-audit`, `claims-drafting`, `comm-lit-review`, `deepxiv`, `dse-loop`, `embodiment-description`, `exa-search`, `experiment-audit`, `experiment-bridge`, `experiment-plan`, `experiment-queue`, `feishu-notify`, `figure-description`, `figure-spec`, `formula-derivation`, `gemini-search`, `grant-proposal`, `idea-creator`, `idea-discovery`, `idea-discovery-robot`, `integrity-forensics`, `interview-cheatsheet`, `invention-structuring`, `jurisdiction-format`, `kill-argument`, `mermaid-diagram`, `meta-apply`, `meta-optimize`, `monitor-experiment`, `novelty-check`, `openalex`, `overleaf-sync`, `paper-claim-audit`, `paper-compile`, `paper-figure`, `paper-illustration`, `paper-illustration-image2`, `paper-plan`, `paper-poster`, `paper-poster-html`, `paper-slides`, `paper-talk`, `paper-write`, `paper-writing`, `patent-novelty-check`, `patent-pipeline`, `patent-review`, `pixel-art`, `prior-art-search`, `proof-checker`, `proof-orchestrator`, `proof-writer`, `qzcli`, `rebuttal`, `render-html`, `research-implement-feature`, `research-lit`, `research-pipeline`, `research-refine`, `research-refine-pipeline`, `research-review`, `research-wiki`, `resubmit-pipeline`, `result-to-claim`, `run-experiment`, `semantic-scholar`, `serverless-modal`, `slides-polish`, `specification-writing`, `system-profile`, `training-check`, `vast-gpu`, `web-debug-search`, `wiki-enrich`, `writing-systems-papers`

## 在 Modex 的 .pyd 字符串表中直接命中 (0/83)

> 命中 = 该 skill 名（`-`→`_`）作为标识符出现在 Modex 编译产物里，
> 说明该 skill 名被蓝方沿用为内部标识符（强同源证据）。


## 未在 Modex 字符串表中命中 (83)

- `ablation-planner`
- `alphaxiv`
- `analyze-results`
- `arxiv`
- `auto-paper-improvement-loop`
- `auto-review-loop`
- `auto-review-loop-llm`
- `auto-review-loop-minimax`
- `citation-audit`
- `claims-drafting`
- `comm-lit-review`
- `deepxiv`
- `dse-loop`
- `embodiment-description`
- `exa-search`
- `experiment-audit`
- `experiment-bridge`
- `experiment-plan`
- `experiment-queue`
- `feishu-notify`
- `figure-description`
- `figure-spec`
- `formula-derivation`
- `gemini-search`
- `grant-proposal`
- `idea-creator`
- `idea-discovery`
- `idea-discovery-robot`
- `integrity-forensics`
- `interview-cheatsheet`
- `invention-structuring`
- `jurisdiction-format`
- `kill-argument`
- `mermaid-diagram`
- `meta-apply`
- `meta-optimize`
- `monitor-experiment`
- `novelty-check`
- `openalex`
- `overleaf-sync`
- `paper-claim-audit`
- `paper-compile`
- `paper-figure`
- `paper-illustration`
- `paper-illustration-image2`
- `paper-plan`
- `paper-poster`
- `paper-poster-html`
- `paper-slides`
- `paper-talk`
- `paper-write`
- `paper-writing`
- `patent-novelty-check`
- `patent-pipeline`
- `patent-review`
- `pixel-art`
- `prior-art-search`
- `proof-checker`
- `proof-orchestrator`
- `proof-writer`
- `qzcli`
- `rebuttal`
- `render-html`
- `research-implement-feature`
- `research-lit`
- `research-pipeline`
- `research-refine`
- `research-refine-pipeline`
- `research-review`
- `research-wiki`
- `resubmit-pipeline`
- `result-to-claim`
- `run-experiment`
- `semantic-scholar`
- `serverless-modal`
- `slides-polish`
- `specification-writing`
- `system-profile`
- `training-check`
- `vast-gpu`
- `web-debug-search`
- `wiki-enrich`
- `writing-systems-papers`

## Modex schema.sql 声明的 workflow 模板

`idea_discovery | experiment_bridge | auto_review | paper_writing | full_pipeline | thesis_proposal | literature_review | course_paper | course_report | humanities_paper | comp_* ...`

