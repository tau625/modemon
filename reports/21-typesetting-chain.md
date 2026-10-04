# 成文链真实验证：LaTeX 导出与编译

> 由 `paper_chain_check.py` 生成。数据源为仿真工作区，**不代表真实竞赛结果**。

## TeX 运行时

```json
{
 "state": "ready",
 "xelatex": "D:\\04_IDEs\\texlive\\2026\\bin\\windows\\xelatex.exe",
 "latexmk": "D:\\04_IDEs\\texlive\\2026\\bin\\windows\\latexmk.exe",
 "root": "D:\\04_IDEs\\texlive\\2026\\bin\\windows",
 "installer_available": true,
 "note": "来源：system",
 "warnings": []
}
```

> **实测约束**：随包 TeXLive 是**未初始化的 MiKTeX**，直接编译会报
> `fresh TeX installation / Please finish the setup`。
> 这印证了蓝方启动日志的「检查工具可用性（不等待 LaTeX 在线安装）」
> 以及其 `latex:get-status` / `latex:install` 两个 IPC 的存在。
> 本次验证**复用系统已装的 TeXLive**，未改动目标安装目录。

## 排版规格（恢复真值）

- 规格名：`competition_zh`（来源 `builtin`）
- 字体：{'chinese_heading': 'SimHei', 'chinese_body': 'SimSun', 'latin': 'Times New Roman', 'monospace': 'Consolas'}
- 正文：12pt / 1.5 倍行距 / 首行缩进 2 字符
- 页边距：2.5cm（四边）
- 标题：一至四级 15/14/12/11pt，加粗，一级居中
- 三线表：1.5-0.75-1.5pt，表内 10.5pt
- 图宽上限：14cm
- 参考文献：悬挂缩进 0.74cm，10.5pt

## 程序化表格（★ 绝不经过模型）

从 `figures/all_results.json` 生成 **2** 张表：

### `TABLE_results.md`（6 行）

```markdown
**表 results：求解结果**

| 指标 | 数值 |
|---|---|
| 目标值 | 1234 |
| 状态 | optimal |
| 求解器 | HiGHS |
| 迭代次数 | 7 |
| 耗时（秒） | 0.03125 |
| 间隙 | 0 |

*数据来源：`all_results.json`*

```

### `TABLE_record_table.md`（3 行）

```markdown
**表 record_table：算例结果**

| 算例 | 目标值 | 耗时（秒） |
|---|---|---|
| 基准 | 1234 | 0.031 |
| 运价+10% | 1357.4 | 0.028 |
| 需求+5% | 1295.7 | 0.033 |

*数据来源：`all_results.json`*

```

> 设计要点（来自蓝方验证过的做法）：**表格不做模型誊抄**，
> 一律由程序从数据真相源生成——模型誊抄数字会出错，而论文里的数字错了就是硬伤。

### 生成的 LaTeX 表（节选）

```latex
\begin{table}[htbp]
  \centering
  \caption{求解结果}
  \label{tab:results}
  \begin{tabular}{lc}
    \toprule
    指标 & 数值 \\
    \midrule
    目标值 & 1234 \\
    状态 & optimal \\
    求解器 & HiGHS \\
    迭代次数 & 7 \\
    耗时（秒） & 0.03125 \\
    间隙 & 0 \\
    \bottomrule
  \end{tabular}
\end{table}
```

## 去 AI 味检查

- 通过：**False**（errors 2 / warns 0）

| 规则 | 级别 | 说明 |
|---|---|---|
| `bold_colon_inside` | error | 冒号写在了加粗标记内：`**结论：**` → 应改为 `**结论****：` |
| `self_reference` | error | 正文出现自指表达（AI/语言模型），论文中不应出现 |

> 检出样例是**故意植入**的：`**结论：**`（冒号写在加粗标记内，
> 复现材料标注这是「最高频痕迹」）与「作为一个AI」自指表达。

## 导出与编译结果

| 项 | 值 |
|---|---|
| 导出成功 | **True** |
| `.tex` | `C:\Users\SAKE\AppData\Local\Temp\modemon-paper-zo4p1xc_\ws\paper\main.tex`（4138 字节） |
| `.pdf` | `C:\Users\SAKE\AppData\Local\Temp\modemon-paper-zo4p1xc_\ws\paper\main.pdf`（82392 字节） |
| **实测页数** | **2** |
| 页数预算（advisory） | {"template": "comp_cumcm", "limit": 30, "mode": "advisory_max", "body_chars": 402, "language": "zh", "chars_per_page": 800, "estimated_pages": 0, "over_limit": false, "over_by": 0, "advisory": true} |
| 编译错误 | `无` |
| 耗时 | 2.6s |

## DOCX 导出（同一论文模型，同一排版规格）

| 项 | 值 |
|---|---|
| 导出成功 | **True** |
| 文件 | `C:\Users\SAKE\AppData\Local\Temp\modemon-paper-zo4p1xc_\ws\paper\main.docx`（38495 字节） |
| 表格 / 图 / 参考文献 | 2 / 2 / 2 |

### 中文 Word 的三个坑（已处理，并由测试回读验证）

1. **东亚字体必须单独设 `w:eastAsia`**——只设 `run.font.name` 只作用于西文。
2. **首行缩进要按「字符」而非磅**——用 `w:firstLineChars`（1/100 字符单位），
   才能随字号自适应；写死磅值在改字号后会错位。
3. **三线表靠边框控制**——上/下粗 1.5pt、表头下细 0.75pt、中间无线。

## 编译日志尾部

```
LaTeX Font Warning: Font shape `TU/SimHei(0)/b/n' undefined
(Font)              using `TU/SimHei(0)/m/n' instead on input line 32.

[1]

LaTeX Font Warning: Font shape `TU/SimSun(1)/b/n' undefined
(Font)              using `TU/SimSun(1)/m/n' instead on input line 47.

(d:/04_IDEs/texlive/2026/texmf-dist/tex/latex/amsfonts/umsa.fd)
(d:/04_IDEs/texlive/2026/texmf-dist/tex/latex/amsfonts/umsb.fd)

LaTeX Font Warning: Font shape `TU/SimSun(1)/m/sl' undefined
(Font)              using `TU/SimSun(1)/m/n' instead on input line 84.

[2]

LaTeX Warning: File `figures/fig_result.png' not found on input line 123.

! Unable to load picture or PDF file 'figures/fig_result.png'.
<to be read again> 
                   }
l.123 ...ics[width=14.0cm]{figures/fig_result.png}
                                                  
Output written on main.pdf (2 pages).
Transcript written on main.log.
```

## 生成的 .tex（节选）

```latex
% !TEX program = xelatex
\documentclass[12pt,a4paper]{ctexart}
\usepackage{geometry}
\geometry{top=2.5cm,bottom=2.5cm,left=2.5cm,right=2.5cm}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{array}
\usepackage{caption}
\usepackage{longtable}
\usepackage{amsmath,amssymb}
\usepackage{setspace}
\usepackage[hidelinks]{hyperref}
\usepackage{enumitem}
\usepackage{xcolor}

% ---- 字体（取自排版规格）----
\setCJKmainfont{SimSun}
\setCJKfamilyfont{hei}{SimHei}
\setmainfont{Times New Roman}
\setmonofont{Consolas}
\newcommand{\hei}{\CJKfamily{hei}}

% ---- 版式（行距为近似映射，见 _spacing_command）----
\onehalfspacing
\setlength{\parindent}{2em}
\setlength{\parskip}{0pt}
\captionsetup{font=small,labelsep=quad}

\begin{document}

\begin{center}
  {\hei\fontsize{18}{24}\selectfont \textbf{基于线性规划的运输成本优化模型}}
\end{center}
\vspace{6pt}

\begin{center}
  {\hei\fontsize{14}{20}\selectfont \textbf{摘要}}
\end{center}
\vspace{4pt}

本文针对运输成本最小化问题建立线性规划模型，求得最优调运方案与最小总成本。

\noindent{\hei\fontsize{12}{16}\selectfont\textbf{关键词}}\quad 运输问题；线性规划；灵敏度分析

\newpage

\section{问题重述}
某物流公司拥有 3 个仓库与 4 个配送点，单位运价矩阵已知，
需要在满足各配送点需求的前提下最小化总运输成本。

\section{问题分析}
该问题属于经典的运输问题，可建模为线性规划。
决策变量为各仓库到各配送点的运量，目标函数为总运价，约束为供需平衡。

\section{模型假设}
\begin{itemize}
  \item 各仓库供给量已知且固定
  \item 运输成本与运量严格成正比，无固定成本
  \item 不考虑运输时间与损耗
\end{itemize}

\section{模型建立}
设 $x_{ij}$ 表示从仓库 $i$ 运往配送点 $j$ 的运量，
$c_{ij}$ 为单位运价。则模型为

$$\min \sum_{i=1}^{3}\sum_{j=1}^{4} c_{ij} x_{ij}$$

约束条件为各仓库供给上限与各配送点需求下限。

\section{求解结果}
采用线性规划求解器求得最优调运方案，最优总成本见表 1。

\textbf{求解环境}：Python 3.11 + 线性规划求解器，迭代次数与耗时见结果表。

\section{灵敏度分析}
当单位运价整体上浮 10\% 时，最优调运方案保持不变，
说明该方案对运价扰动具有稳定性。

\section{讨论}
\textbf{结论：} 模型有效。

作为一个AI，我认为该方案合理。

\section*{结果数据表}
\addcontentsline{toc}{section}{结果数据表}
\begin{table}[htbp]
  \centering
  \caption{求解结果}
  \label{tab:results}
  \begin{tabular}{lc}
    \toprule
    指标 & 数值 \\
    \midrule
    目标值 & 1234 \\
    状态 & optimal \\
    求解器 & HiGHS \\
    迭代次数 & 7 \\
    耗时（秒） & 0.03125 \\
    间隙 & 0 \\
    \bottomrule
  \end{tabular}
\end{table}

\begin{table}[htbp]
  \centering
  \caption{算例结果}
  \label{tab:record_table}
  \begin{tabular}{lcc}
    \toprule
    算例 & 目标值 & 耗时（秒） \\
    \midrule
    基准 & 1234 & 0.031 \\
    运价+10\% & 1357.4 & 0.028 \\
    需求+5\% & 1295.7 & 0.033 \\
    \bottomrule
  \end{tabular}
\end{table}

\section*{图表}
\addcontentsline{toc}{section}{图表}
\begin{figure}[htbp]
  \centering
  \includegraphics[width=14.0cm]{figures/fig_result.png}
  \caption{figures/fig\_result.png}
  \label{fig:fig_result}
\end{figure}

\begin{figure}[htbp]
  \centering
  \includegraphics[width=14.0cm]{figures/tikz_arch.drawio}
  \caption{figures/tikz\_arch.drawio}
  \label{fig:tikz_arch}
\end{figure}

\section*{参考文献}
\addcontentsline{toc}{section}{参考文献}
\begin{list}{}{\setlength{\leftmargin}{0.74cm}\setlength{\itemindent}{-0.74cm}\fontsize{10.5}{13.5}\selectfont}
  \item[1] 姜启源. 数学模型（第五版）. 高等教育出版社, 2018.
  \item[2] Dantzig G B. Linear Programming and Extensions. Princeton, 1963.
\end{list}

\end{document}
```
