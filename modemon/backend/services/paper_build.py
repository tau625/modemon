"""论文装配：从工作区产物构建可渲染的论文模型。

★ 防幻觉的核心设计（来自蓝方验证过的做法）
------------------------------------------
1. **表格绝不由模型誊抄**——一律由程序从 `figures/all_results.json` 生成。
   蓝方的做法是「程序生成 `figures/TABLE_*.md` 后由 shell 直接拼接」。
   理由很直接：模型誊抄数字会出错，而论文里的数字错了就是硬伤。
2. **数值只从机器可读结果读**——`all_results.json` 是数据真相源。
3. **图表按命名约定归类**——`fig_*` 为数据图、`tikz_*` 为架构图；
   `FIGURE_MANIFEST` 的章节标题优先于文件名前缀。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from . import typography as ty

#: 图表命名约定（内省真值）
FIGURE_RE = re.compile(r"^(fig_|tikz_)([A-Za-z0-9_]+)")
#: FIGURE_MANIFEST 条目：`- fig_xxx`
MANIFEST_ITEM_RE = re.compile(r"^[ \t]*-[ \t]+(fig_[A-Za-z0-9_]+|tikz_[A-Za-z0-9_]+)")
#: 章节标题
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
#: 引用标注 `\cite{...}` 或 `[@key]`
CITE_RE = re.compile(r"\\cite\{([^}]+)\}|\[@([A-Za-z0-9_\-:.,\s]+)\]")

FIGURE_EXTS = {".png", ".pdf", ".svg", ".jpg", ".jpeg", ".drawio"}

#: **能被 `\\includegraphics` 嵌入的格式**（按优先顺序）。
#:
#: ⚠️ 不含 `.svg` / `.drawio`：XeLaTeX 处理不了 SVG，
#: 会报 `Cannot determine size of graphic ... (no BoundingBox)` 并**整份论文编译失败**。
#: 实测踩过——FigureSpec 同时产出 PNG 与 SVG，两者 stem 相同都被收作插图。
LATEX_FIGURE_EXTS = (".png", ".jpg", ".jpeg", ".pdf")


# ---------------------------------------------------------------------------
# 数据真相源
# ---------------------------------------------------------------------------


@dataclass
class ResultsSource:
    """`figures/all_results.json` 的读取结果。

    该文件是**数值的唯一真相源**：论文里出现的任何数字都必须能追溯到它。
    """

    path: Path
    data: dict[str, Any] = field(default_factory=dict)
    ok: bool = False
    error: str = ""

    @property
    def scalars(self) -> dict[str, Any]:
        """扁平化后的「标量」项——可直接进结果表的那些。"""
        out: dict[str, Any] = {}

        def walk(prefix: str, node: Any, depth: int = 0) -> None:
            if depth > 6:
                return
            if isinstance(node, dict):
                for k, v in node.items():
                    walk(f"{prefix}.{k}" if prefix else str(k), v, depth + 1)
            elif isinstance(node, (list, tuple)):
                # 只取「标量列表」或「记录列表」的有限形态，避免表格失控
                if node and all(not isinstance(x, (dict, list)) for x in node):
                    out[prefix] = node
            elif isinstance(node, (int, float, bool, str)) or node is None:
                out[prefix] = node

        walk("", self.data)
        return out

    def records(self) -> list[dict[str, Any]]:
        """找出可成表的记录数组（list[dict]）。"""
        found: list[dict[str, Any]] = []

        def walk(node: Any, depth: int = 0) -> None:
            if depth > 4:
                return
            if isinstance(node, dict):
                for v in node.values():
                    walk(v, depth + 1)
            elif isinstance(node, list) and node and all(isinstance(x, dict) for x in node):
                found.append({"rows": node})

        walk(self.data)
        return found


def load_results(workspace: Path) -> ResultsSource:
    """读取 `figures/all_results.json`。"""
    p = Path(workspace) / "figures" / "all_results.json"
    if not p.is_file():
        return ResultsSource(path=p, ok=False, error="all_results.json 不存在")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return ResultsSource(path=p, ok=False, error=f"解析失败: {exc}")
    if not isinstance(data, dict):
        return ResultsSource(path=p, ok=False, error="顶层必须是对象")
    return ResultsSource(path=p, data=data, ok=True)


# ---------------------------------------------------------------------------
# 程序化表格（★ 绝不经过模型）
# ---------------------------------------------------------------------------


def format_value(v: Any) -> str:
    """把数值格式化为论文里可直接展示的形式。

    浮点统一保留有效位，避免出现 `0.30000000000000004` 这类机器噪声。
    """
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "是" if v else "否"
    if isinstance(v, float):
        if v != v:  # NaN
            return "—"
        if v == int(v) and abs(v) < 1e15:
            return str(int(v))
        return f"{v:.6g}"
    if isinstance(v, (list, tuple)):
        return ", ".join(format_value(x) for x in v)
    return str(v)


@dataclass
class TableSpec:
    """一张由程序生成的表。"""

    name: str                       # 逻辑名，如 `key_results`
    caption: str
    headers: list[str]
    rows: list[list[str]]
    source: str = ""                # 数据来源（便于溯源）

    def to_markdown(self) -> str:
        import html
        esc = lambda s: html.escape(str(s), quote=False).replace("|", "\\|")  # noqa: E731
        out = [f"**表 {self.name}：{self.caption}**", ""]
        out.append("| " + " | ".join(esc(h) for h in self.headers) + " |")
        out.append("|" + "|".join(["---"] * len(self.headers)) + "|")
        for r in self.rows:
            out.append("| " + " | ".join(esc(c) for c in r) + " |")
        out.append("")
        if self.source:
            out.append(f"*数据来源：`{self.source}`*")
            out.append("")
        return "\n".join(out)

    def to_inline_latex(self) -> str:
        """**非浮动**排版：`tabular` + `\\captionof`。

        为什么需要它：文末「结果数据表」这类**纯浮动体区块**里，
        用 `table` 浮动环境会出两种病：
          - `[htbp]`：标题落单——标题在文字流里，表却浮走了
          - `[H]`：留大块空白——空出的区域没有文字可填补
        改用 `\\captionof` 后完全不浮动，版面是确定的。
        """
        def esc(s: str) -> str:
            s = str(s)
            for a, b in (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"),
                         ("$", r"\$"), ("#", r"\#"), ("_", r"\_"),
                         ("{", r"\{"), ("}", r"\}")):
                s = s.replace(a, b)
            return s

        col = "l" + "c" * (max(len(self.headers), 1) - 1)
        # ⚠️ **表题在表格上方**：中文期刊/竞赛论文规范是「表题在上、图题在下」。
        #   视觉自检抓过这条：「表题均位于表格下方，不符合规范」。
        L = []
        if self.caption:
            L.append(f"\\captionof{{table}}{{{_tex_escape(self.caption)}}}")
            L.append(f"\\label{{tab:{self.name}}}")
        L += [r"\begin{center}", f"  \\begin{{tabular}}{{{col}}}", r"    \toprule",
              "    " + " & ".join(esc(h) for h in self.headers) + r" \\",
              r"    \midrule"]
        for r in self.rows:
            L.append("    " + " & ".join(esc(c) for c in r) + r" \\")
        L += [r"    \bottomrule", r"  \end{tabular}", r"\end{center}"]
        return "\n".join(L)

    def to_latex(self) -> str:
        def esc(s: str) -> str:
            s = str(s)
            for a, b in (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"),
                         ("$", r"\$"), ("#", r"\#"), ("_", r"\_"),
                         ("{", r"\{"), ("}", r"\}")):
                s = s.replace(a, b)
            return s

        col = "l" + "c" * (len(self.headers) - 1)
        out = [
            r"\begin{table}[htbp]", r"  \centering",
            f"  \\caption{{{esc(self.caption)}}}",
            f"  \\label{{tab:{self.name}}}",
            f"  \\begin{{tabular}}{{{col}}}", r"    \toprule",
            "    " + " & ".join(esc(h) for h in self.headers) + r" \\",
            r"    \midrule",
        ]
        for r in self.rows:
            out.append("    " + " & ".join(esc(c) for c in r) + r" \\")
        out += [r"    \bottomrule", r"  \end{tabular}", r"\end{table}"]
        return "\n".join(out)


#: **不该出现在论文表格里的字段**（运行时元数据 / 实现细节 / 输入数据，不是结果）。
#:
#: ⚠️ 实测教训：没有这层过滤时，`build_result_table` 会把
#: `meta.title` / `meta.generated_by` / `meta.python` / `meta.platform`
#: 等**内部字段**全部倒进"求解结果"表，一张表高过两页，
#: 结果表题被挤到单独一页、表格被拦腰劈开。这不是排版问题，是内容问题。
NOT_PAPER_FIELDS = (
    "meta", "generated_by", "tol", "platform", "python",
    "seed", "dpi", "font", "input_file", "results_source",
    "figure", "image", "style", "provenance", "ts", "timestamp",
    # 输入数据与中间量：属于"模型假设/符号说明"，不属于"求解结果"
    "data", "basis", "supply", "demand", "dc", "demand_points", "rows",
    # 矩阵/向量类中间量（位势、检验数、调运矩阵）应作为表/图的主体，
    # 不应压平成一列
    "x", "shipments", "potentials_u", "potentials_v", "reduced_costs_sigma",
    "shortage_by_demand",
)

#: 结果类字段的中文标签（恢复自产品的中文文案惯例）
FIELD_LABELS: dict[str, str] = {
    "objective": "目标值", "objective_value": "目标值", "cost": "成本",
    "optimal": "最优值", "optimum": "最优值", "value": "数值",
    "time_s": "耗时（秒）", "runtime_s": "耗时（秒）", "iterations": "迭代次数",
    "gap": "间隙", "status": "状态", "solver": "求解器", "model": "模型",
    "scenario": "场景", "case": "算例", "method": "方法", "accuracy": "准确率",
    "error": "误差", "rmse": "RMSE", "mae": "MAE", "r2": "R²",
    # 竞赛语义层常见结果字段
    "z0": "最优总成本", "z": "总成本", "total_cost": "总成本",
    "min_cost": "最小总成本", "best": "最优值",
    "supply_drop_tons": "供应下降（吨）",
    "shortage_gap_tons": "缺货缺口（吨）",
    "shortage": "缺货量", "shortage_tons": "缺货量（吨）",
    "total_supply": "供应总量", "total_demand": "需求总量",
    "dc2_fail_ratio": "DC2 故障降幅",
    "penalty_p": "缺货惩罚系数",
    "simplex_iterations": "单纯形迭代次数",
    "max_abs_diff": "最大绝对误差",
    "n": "样本数", "mean": "均值", "ci_low": "95% 下界", "ci_high": "95% 上界",
    # 记录表常见列
    "elapsed_s": "耗时/s", "elapsed_ms": "耗时/ms", "duration_s": "耗时/s",
    "n_vars": "变量数", "n_constraints": "约束数",
    "tons": "运量（吨）", "from": "起点", "to": "终点",
    "unit_cost": "单位运价", "amount": "数量",
    # 记录表里承载「条目名」的列：不能原样输出 `name`
    "name": "名称", "var": "变量", "variable": "变量", "symbol": "符号",
    "index": "序号", "id": "编号", "row": "行", "col": "列",
    # 竞赛结果里高频的变体字段
    # ⚠️ **不要**把 `desc`/`param` 这类**叙述性/输入性**字段登记进来：
    #   它们是"模型假设/说明"的素材，不是结果。登记了会把一句解释
    #   塞进「求解结果」表，把表撑到行数上限（实测：登记后 7 行涨到 18 行
    #   并触发截断）。`_keep` 只放行登记过的叶子，这里就是那道闸门。
    "obj": "目标值", "z_trans": "运输成本项", "z_by_p": "按惩罚系数取值",
    "delta_vs_base": "相对基准变化", "delta_pct": "变化率（%）",
    "feasible": "可行",
}

#: **分组路径的中文限定标签**——恢复被 `_label_for` 丢掉的**分组语义**。
#:
#: 为什么必须有：`_label_for` 原来只取路径最后一段，于是实测出现
#: 「求解结果」表里 **4 行都叫「总成本」**（`scenario1_basic.Z0` /
#: `scenario2.Z0` / `cost_change_summary.Z0` 折叠成同一标签），
#: 读者无法区分场景。标签必须保留分组，且**同表内唯一**。
GROUP_LABELS: dict[str, str] = {
    # 实测坏样本（`figures/all_results.json` 真实结构）
    "scenarios.s1_baseline": "情景 S1 原问题基准",
    "scenarios.s2a_shortage_p20": "情景 S2A 缺货惩罚 p=20",
    "scenarios.s2a_trans_only": "情景 S2A 仅运输成本",
    "scenarios.s2b_ext_1p5x": "情景 S2B 外部应急运力",
    "scenario1_basic": "情景1",
    "scenario1": "情景1",
    "scenario2": "情景2",
    "scenario2.caliber_a": "情景2 口径A",
    "scenario2.caliber_b": "情景2 口径B",
    "scenario2.marginal_dc2": "情景2 DC2 边际",
    "scenario2_penalty_sensitivity": "情景2 罚系数敏感性",
    "scenario3": "情景3",
    "scenario3.monte_carlo": "情景3 蒙特卡洛",
    "scenario3.global_scale": "情景3 全局缩放",
    "cost_change_summary": "成本变动汇总",
    "optimal_family": "最优解族",
    "iterations": "迭代",
    "timing_sec": "计时",
}

#: 分组路径**逐段**的常见词表（精确表未命中时的通用回退）。
#:
#: 未命中的段落**保留原文**——宁可留一句英文路径，也不丢掉分组信息
#: （丢分组就是本文档开头那个「4 行同名」缺陷的根因）。
GROUP_TOKENS: dict[str, str] = {
    "scenario": "情景", "scenarios": "情景", "case": "算例", "cases": "算例",
    "basic": "基础", "baseline": "基准", "shortage": "缺货", "penalty": "罚系数",
    "sensitivity": "敏感性", "monte": "蒙特卡洛", "carlo": "蒙特卡洛",
    "global": "全局", "scale": "缩放", "summary": "汇总", "change": "变动",
    "cost": "成本", "caliber": "口径", "trans": "运输", "ext": "外部",
    "marginal": "边际", "variables": "变量", "data": "数据", "iterations": "迭代",
}

#: 记录表里承载「变量/条目名」的列——这些列的值也要本地化，不能原样输出 `x11`。
VARIABLE_NAME_COLUMNS = ("name", "var", "variable", "key", "symbol", "变量", "名称")

#: 论文表格的合理行数上限。超出即截断并在表末注明——
#: 论文表不该无限膨胀；宁可少而清楚。
MAX_TABLE_ROWS = 18


def _column_label(col: str, values: Optional[Iterable[Any]] = None) -> str:
    """表格列名 → 可读标签。

    ⚠️ 未登记的列**不能原样输出**：`elapsed_s` 会渲染成转义后的下划线形式，
    视觉自检会报「表头含异常下划线」。所以兜底用「下划线转空格」的可读形式。

    `values`（可选）：该列的全部取值。当一列名叫 `name`/`var` 而取值
    **全是矩阵下标键**（`x11`/`x12`…）时，这列实际是「变量」列——
    此时返回「变量」而不是泛化的「名称」（实测缺陷：表头 `name` 直接进论文）。
    """
    low = str(col).lower()
    if values is not None and low in VARIABLE_NAME_COLUMNS:
        vals = [v for v in values if v is not None and str(v).strip() != ""]
        if vals and all(_is_indexed_key(v) for v in vals):
            return "变量"
    hit = FIELD_LABELS.get(low) or FIELD_LABELS.get(col)
    return hit if hit else str(col).replace("_", " ")


#: 矩阵下标键：`x11`（单数字下标）或带分隔符的 `x_1_10` / `x_1,10`。
#:
#: ⚠️ 不带分隔符时**只接受单数字下标**：`x1011` 无法判断是 (10,11) 还是 (1,011)，
#: 猜错就是把数字读错——论文里的数字错了是硬伤。多位数必须带分隔符。
_INDEXED_KEY_RE = re.compile(r"^([A-Za-z]{1,3})(\d)(\d)$|^([A-Za-z]{1,3})[_.,](\d+)[_.,](\d+)$")


def _is_indexed_key(value: Any) -> bool:
    """取值是否为矩阵下标键（`x11` / `x_1_10` / `c11`）。"""
    return bool(_INDEXED_KEY_RE.match(str(value).strip()))


def _value_label(value: Any) -> str:
    """把矩阵下标键变成可读标签：`x11` → `DC1→R1`。

    为什么必须做：实测「算例结果」表整列都是 `x11/x12/x21…`
    （3×4 运输问题），论文读者看不懂下标键。
    前缀语义：`x`→运量、`c`→单位运价；其余前缀也**不原样输出下标键**。
    """
    m = _INDEXED_KEY_RE.match(str(value).strip())
    if not m:
        return format_value(value)
    if m.group(1) is not None:
        prefix, i, j = m.group(1).lower(), m.group(2), m.group(3)
    else:
        prefix, i, j = m.group(4).lower(), m.group(5), m.group(6)
    pair = f"DC{int(i)}→R{int(j)}"
    if prefix == "x":
        return pair
    if prefix == "c":
        return f"{pair} 单位运价"
    return f"{pair}（{prefix}）"


def _segment_words(seg: str) -> str:
    """分组路径的**单段** → 中文词（未命中的词保留原文）。"""
    words: list[str] = []
    for tok in re.split(r"[_\s]+", seg):
        if not tok:
            continue
        low = tok.lower()
        if low in GROUP_TOKENS:
            words.append(GROUP_TOKENS[low])
            continue
        m = re.fullmatch(r"([A-Za-z]+)(\d+)", tok)
        if m and m.group(1).lower() in GROUP_TOKENS:
            words.append(f"{GROUP_TOKENS[m.group(1).lower()]}{m.group(2)}")
            continue
        words.append(tok)
    return " ".join(words)


def _group_prefix(group: str) -> str:
    """分组路径 → 中文限定前缀（`scenario1_basic` → `情景1`）。"""
    if not group:
        return ""
    hit = GROUP_LABELS.get(group.lower())
    if hit:
        return hit
    return " ".join(_segment_words(s) for s in group.split(".") if s)


def _label_for(key: str) -> str:
    """把 `scenario1_basic.Z0` 变成**带分组语义**的中文标签。

    查表必须**大小写不敏感**：字典里是小写 `z0`，而数据里常是 `Z0`。
    不做归一化就会直接显示 `scenario1_basic.Z0` 这种原始 key——实测过。

    ⚠️ **只取叶子是不够的**：实测「求解结果」表里 4 行都叫「总成本」
    （`scenario1_basic.Z0` / `scenario2.Z0` / `cost_change_summary.Z0` 折叠）。
    因此标签 = `分组前缀 + 叶子标签`，如 `情景1 最优总成本`。

    表内唯一性由 `unique_labels()` 保证——本函数只管单个 key。
    """
    parts = [p for p in str(key).split(".") if p]
    if not parts:
        return str(key)
    leaf = parts[-1]
    hit = FIELD_LABELS.get(leaf.lower())
    leaf_label = hit if hit else leaf.replace("_", " ")
    prefix = _group_prefix(".".join(parts[:-1]))
    return f"{prefix} {leaf_label}".strip()


def _qualified_label(key: str, group_raw: str) -> str:
    """去重兜底标签：保留中文前缀，再用**原始分组路径**限定。

    宁可留一句英文路径，也不让同一张表里出现两行同名——
    重名是硬伤，读者无法区分。
    """
    base = _label_for(key)
    return f"{base}（{group_raw}）" if group_raw else base


def unique_labels(keys: Iterable[str]) -> dict[str, str]:
    """把一组结果 key 映射成**表内唯一**的可读标签。

    三级策略：
      1. `_label_for` 的限定标签（正常路径，已带分组）；
      2. 仍冲突 → 追加原始分组路径（`情景1 最优总成本（scenario1）`）；
      3. 还冲突 → 追加序号（正常数据不会走到这里，纯兜底）。
    """
    out: dict[str, str] = {}
    seen: set[str] = set()
    for k in keys:
        parts = [p for p in str(k).split(".") if p]
        raw_group = ".".join(parts[:-1]) if len(parts) > 1 else ""
        cand = _label_for(k)
        if cand in seen:
            cand = _qualified_label(k, raw_group)
        n = 2
        while cand in seen:
            cand = f"{_qualified_label(k, raw_group)}#{n}"
            n += 1
        seen.add(cand)
        out[k] = cand
    return out


def table_label_duplicates(table: "TableSpec") -> list[str]:
    """返回一张表第一列里的**重复标签**（空列表 = 合法）。

    供测试与导出前自检共用：`duplicates == []` 是论文表的硬要求。
    """
    counts: dict[str, int] = {}
    for row in table.rows:
        if not row:
            continue
        counts[str(row[0])] = counts.get(str(row[0]), 0) + 1
    return sorted(lbl for lbl, n in counts.items() if n > 1 and lbl != "…")


def build_result_table(src: ResultsSource, *, name: str = "results",
                       caption: str = "求解结果",
                       max_rows: int = MAX_TABLE_ROWS) -> Optional[TableSpec]:
    """把 `all_results.json` 的标量项变成一张结果表（程序生成）。

    两个约束（都来自实测缺陷）：
      1. **剔除元数据**——`meta.*` 等内部字段不进论文表；
      2. **限行数**——超过 `max_rows` 就截断，避免一张表撑爆两页。
    """
    if not src.ok:
        return None
    scalars = src.scalars
    if not scalars:
        return None

    def _keep(k: str) -> bool:
        parts = [p.lower() for p in k.split(".")]
        if any(p in NOT_PAPER_FIELDS for p in parts):
            return False
        # 只要**结果类**叶子（目标值/成本/耗时/迭代/缺货等）
        leaf = parts[-1]
        return leaf in FIELD_LABELS

    kept = {k: v for k, v in scalars.items() if _keep(k)}
    if not kept:
        # 没有可识别的结果字段时，退回为"全部标量但排除元数据"
        kept = {k: v for k, v in scalars.items()
                if k.split(".")[0].lower() not in NOT_PAPER_FIELDS}
    if not kept:
        return None

    truncated = False
    if len(kept) > max_rows:
        # 优先保留"结果类"字段（目标值/耗时/迭代等），再按原顺序补齐
        def _prio(k: str) -> int:
            return 0 if k.split(".")[-1].lower() in FIELD_LABELS else 1

        ordered = sorted(kept.items(), key=lambda kv: (_prio(kv[0]),))
        kept = dict(ordered[:max_rows])
        truncated = True

    # ★ 标签**必须带分组且表内唯一**：实测同一张「求解结果」表出现 4 行「总成本」，
    #   读者无法区分场景。唯一性由 `unique_labels` 三级兜底保证。
    labels = unique_labels(kept.keys())
    rows = [[labels[k], format_value(v)] for k, v in kept.items()]
    if truncated:
        rows.append(["…", f"共 {len(scalars)} 项，已截断至 {max_rows} 项"])
    return TableSpec(name=name, caption=caption, headers=["指标", "数值"],
                     rows=rows, source=f"{src.path.name}")


def build_record_table(src: ResultsSource, index: int = 0, *,
                       name: str = "record_table",
                       caption: str = "算例结果") -> Optional[TableSpec]:
    """把记录数组变成一张表。列取所有行的并集，保持稳定顺序。"""
    recs = src.records()
    if not src.ok or index >= len(recs):
        return None
    # ⚠️ 行数必须按论文可读性裁剪：上限 200 是为"落盘 CSV"设的，
    #   直接进论文会让一张表撑爆几页、把标题挤到单独一页（实测过）。
    rows_in: list[dict[str, Any]] = recs[index]["rows"][:MAX_TABLE_ROWS]
    n_total = len(recs[index]["rows"])
    if not rows_in:
        return None
    cols: list[str] = []
    for r in rows_in:
        for k in r:
            if k not in cols:
                cols.append(k)
    # ★ 列名要本地化，且**变量名列的值也要本地化**：
    #   实测表头是 `name`、整列是 `x11/x12/x21…`（3×4 运输问题），
    #   论文里既不能出现 `name` 这种键，也不能出现 `x11` 这种下标键。
    headers = [_column_label(c, [r.get(c) for r in rows_in]) for c in cols]
    label_cols = {c for c in cols if str(c).lower() in VARIABLE_NAME_COLUMNS}
    rows = [
        [(_value_label(r.get(c)) if c in label_cols else format_value(r.get(c)))
         for c in cols]
        for r in rows_in
    ]
    if n_total > MAX_TABLE_ROWS:
        rows.append(["…"] + [f"共 {n_total} 行，已截断至 {MAX_TABLE_ROWS} 行"] + [""] * (len(cols) - 1))
    return TableSpec(name=name, caption=caption, headers=headers, rows=rows,
                     source=src.path.name)


def write_table_files(workspace: Path, tables: Iterable[TableSpec]) -> list[Path]:
    """把表写成 `figures/TABLE_*.md`。

    对齐蓝方做法：表格落成独立文件，再由主线拼接，
    这样**表格内容完全可追溯到数据文件**，且不经过模型生成。
    """
    out_dir = Path(workspace) / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for t in tables:
        p = out_dir / f"TABLE_{t.name}.md"
        p.write_text(t.to_markdown(), encoding="utf-8")
        written.append(p)
    return written


# ---------------------------------------------------------------------------
# 图表清单
# ---------------------------------------------------------------------------


def pretty_figure_name(stem: str) -> str:
    """把 `fig_scenarios` / `tikz_arch` 变成可读标签。

    图注默认值**不能是文件路径**——实测中曾输出
    `图 1  figures/fig_scenarios.png`，这对论文毫无意义。
    """
    s = stem
    for p in ("fig_", "tikz_"):
        if s.startswith(p):
            s = s[len(p):]
            break
    s = s.replace("_", " ").strip()
    return s or stem


@dataclass
class FigureRef:
    """一张图。"""

    path: str
    latex_name: str
    kind: str            # data | diagram
    caption: str = ""
    section: str = ""

    @property
    def display_caption(self) -> str:
        """图注的兜底：显式 caption → 可读名。

        ⚠️ **不要回退到清单的章节名**。实测里章节名是「结果与讨论」这种
        通用小标题，当图注用是**误导**——视觉自检直接判了：
        「图题为『图 1 结果与讨论』，与图内标题『不同算例的运输成本对比』不符」。
        文件名派生的标签至少与该图对应。
        """
        return self.caption or pretty_figure_name(Path(self.path).stem)

    def to_latex(self, width_cm: float = 14, *, height_cm: float = 9.5,
                 base_prefix: str = "") -> str:
        """生成 figure 环境。

        Args:
            width_cm: 图宽上限（cm）。
            height_cm: **图高上限**（配合 keepaspectratio 等比缩放）。
                必须有高度上限：只限宽时，长宽比大的图会顶穿正文区高度，
                浮动体无处安置，表现为**整页空白**（实测过）。
            base_prefix: 从 `.tex` 所在目录指向工作区根的前缀（如 `../`）。
                ⚠️ 必须给对：`\\includegraphics` 的路径**相对于 .tex 文件**，
                而图通常在工作区 `figures/`、`.tex` 在 `paper/`。
                曾漏掉这一点 → 编译在插图处中断 → 产出**截断的 PDF**。
        """
        return "\n".join([
            r"\begin{figure}[htbp]", r"  \centering",
            f"  \\includegraphics[width={width_cm}cm,height={height_cm}cm,"
            f"keepaspectratio]{{{base_prefix}{self.path}}}",
            f"  \\caption{{{_tex_escape(self.display_caption)}}}",
            f"  \\label{{fig:{self.latex_name}}}",
            r"\end{figure}",
        ])

    def to_inline_latex(self, width_cm: float = 14, *, height_cm: float = 9.5,
                        base_prefix: str = "") -> str:
        """**非浮动**排版：`center` + `\\captionof`。

        同 `TableSpec.to_inline_latex`：文末「图表」是纯浮动体区块，
        浮动环境会让标题落单或留白。这里不浮动，版面确定。
        """
        return "\n".join([
            r"\begin{center}",
            f"  \\includegraphics[width={width_cm}cm,height={height_cm}cm,"
            f"keepaspectratio]{{{base_prefix}{self.path}}}",
            r"\end{center}",
            f"\\captionof{{figure}}{{{_tex_escape(self.display_caption)}}}",
            f"\\label{{fig:{self.latex_name}}}",
        ])


def _tex_escape(s: str) -> str:
    for a, b in (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"),
                 ("$", r"\$"), ("#", r"\#"), ("_", r"\_")):
        s = s.replace(a, b)
    return s


def ascii_safe_name(stem: str) -> str:
    """把中文/空格/特殊字符替换成 ASCII 友好名字。

    理由（来自蓝方的 docstring）：
    「把中文/空格/特殊字符替换成 ASCII 友好名字, 供 LaTeX includegraphics 安全引用」。
    另外「如果转换后 stem 太短或全是数字, 用原名 hash 兜底唯一性」。
    """
    import hashlib
    out = re.sub(r"[^A-Za-z0-9_\-]", "", stem.replace(" ", "_"))
    out = re.sub(r"_{2,}", "_", out).strip("_")
    if len(out) < 3 or out.isdigit():
        out = f"fig_{hashlib.sha1(stem.encode('utf-8')).hexdigest()[:8]}"
    return out


def collect_figures(workspace: Path) -> list[FigureRef]:
    """扫描 `figures/` 并按命名约定归类。

    ⚠️ **同一张图会有多个格式**：FigureSpec 渲染链会同时产出
    `X.png`（供 LaTeX 嵌入）与 `X.svg`（可编辑的矢量原稿）。
    两者 stem 相同，都会被 `FIGURE_RE` 命中。

    实测缺陷：不处理就会把 `.svg` 也当成插图塞进 `doc.figures`，
    于是 XeLaTeX 报
    `! LaTeX Error: Cannot determine size of graphic in .../X.svg (no BoundingBox)`
    —— `\\includegraphics` **不支持 SVG**，整份论文编译失败。

    处理：**按 stem 去重并优先可嵌入的光栅格式**；
    纯 SVG/DrawIO（没有光栅孪生）不进 LaTeX，但仍在图上可查。
    """
    fig_dir = Path(workspace) / "figures"
    if not fig_dir.is_dir():
        return []

    # 先按 stem 归组，同组内挑优先格式
    by_stem: dict[str, list[Path]] = {}
    for p in sorted(fig_dir.iterdir()):
        if not p.is_file() or p.suffix.lower() not in FIGURE_EXTS:
            continue
        if not FIGURE_RE.match(p.stem):
            continue
        by_stem.setdefault(p.stem, []).append(p)

    out: list[FigureRef] = []
    for stem, paths in sorted(by_stem.items()):
        chosen = next((q for ext in LATEX_FIGURE_EXTS
                       for q in paths if q.suffix.lower() == ext), None)
        if chosen is None:
            continue          # 只有 SVG/DrawIO：不可嵌入，跳过
        kind = "diagram" if stem.startswith("tikz_") else "data"
        out.append(FigureRef(path=f"figures/{chosen.name}",
                             latex_name=ascii_safe_name(stem), kind=kind))
    return out


@dataclass
class ManifestEntry:
    name: str
    section: str = ""
    caption: str = ""


#: 表格行里的图名（可能带反引号与扩展名）
_TABLE_FIG_RE = re.compile(r"`?(fig_[A-Za-z0-9_]+|tikz_[A-Za-z0-9_]+)(?:\.[A-Za-z0-9]+)?`?")


def parse_figure_manifest(workspace: Path) -> list[ManifestEntry]:
    """解析 `figures/FIGURE_MANIFEST.md`。

    蓝方的规则：「按 FIGURE_MANIFEST 的章节标题把图名归类
    （**权威, 优先于文件名前缀**）」。因此清单里的章节归属优先。

    支持**两种格式**（实测 agent 会自己选一种）：

    1. 列表式：粗体章节标题下 `- fig_xxx`
    2. **表格式**（实测 agent 自己升级成了这个）：

           | 文件名 | 中文标题 | 数据来源 | 说明 |
           | `fig_transport_plan.png` | 情景1 最优调运方案 X*（吨） | `scenario1_basic.X` | ... |

    表格式的**第二列是中文图注**——不解析它，论文里就会出现
    「图 1 monte carlo」这种把内部文件名当图注的结果。
    """
    p = Path(workspace) / "figures" / "FIGURE_MANIFEST.md"
    if not p.is_file():
        return []
    entries: list[ManifestEntry] = []
    section = ""
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = line.rstrip()
        if not raw.strip():
            continue

        hm = HEADING_RE.match(raw)
        if hm:
            section = re.sub(r"[*_`]", "", hm.group(2)).strip()
            continue
        if raw.lstrip().startswith("**") and raw.rstrip().endswith("**"):
            section = re.sub(r"[*_`]", "", raw.strip()).strip("：: ")
            continue

        # ---- 表格行：| 文件名 | 中文标题 | … | ----
        if raw.strip().startswith("|"):
            if re.match(r"^\s*\|[\s:|-]+\|\s*$", raw):     # 分隔行
                continue
            cells = _split_table_row(raw)
            if not cells:
                continue
            m = _TABLE_FIG_RE.search(cells[0])
            if not m:
                continue
            caption = cells[1].strip() if len(cells) > 1 else ""
            # 只去掉 **成对的** Markdown 强调符与反引号。
            # ⚠️ 不能一刀切删 `*`：数学里的最优值记号 `X*` 会被误删
            #   （实测：「情景1 最优调运方案 X*」被删成「… X」）。
            caption = re.sub(r"\*\*([^*]+?)\*\*", r"\1", caption)
            caption = caption.replace("`", "").strip()
            # 表头行会被这里过滤掉：第一格不含 fig_/tikz_
            entries.append(ManifestEntry(name=m.group(1), section=section,
                                         caption=caption))
            continue

        # ---- 列表式：- fig_xxx ----
        m = MANIFEST_ITEM_RE.match(raw)
        if m:
            entries.append(ManifestEntry(name=m.group(1), section=section))
    return entries


def _split_table_row(line: str) -> list[str]:
    """拆一行 Markdown 表格。"""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    s = s.replace(r"\|", "\x00PIPE\x00")
    return [c.strip().replace("\x00PIPE\x00", "|") for c in s.split("|")]


# ---------------------------------------------------------------------------
# 论文模型
# ---------------------------------------------------------------------------


@dataclass
class Section:
    level: int
    title: str
    body: str = ""

    def to_latex(self) -> str:
        cmd = {1: "section", 2: "subsection", 3: "subsubsection"}.get(self.level, "paragraph")
        return f"\\{cmd}{{{_tex_escape(self.title)}}}\n\n{self.body}"


@dataclass
class PaperDoc:
    """一篇可渲染的论文。"""

    title: str = ""
    abstract: str = ""
    keywords: list[str] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    tables: list[TableSpec] = field(default_factory=list)
    figures: list[FigureRef] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    ai_disclosure: list[dict[str, Any]] = field(default_factory=list)
    template: str = "comp_zh"
    language: str = "zh"

    #: 正文来源。**这是引擎与 agent 之间的格式约定**的状态位：
    #:   `sections`     —— `paper/sections/*.md`（约定格式，引擎装配）
    #:   `main_md`      —— `paper/main.md`（兼容旧路径）
    #:   `prebuilt_tex` —— agent 直出的成品 `paper/main.tex`（引擎**只编译不重建**）
    #:   `none`         —— 未找到正文（导出量必须显式降级，不得报 ok）
    body_source: str = "none"
    #: 预编译路径下 agent 直出 `.tex` 的相对路径（如 `paper/main.tex`）。
    prebuilt_tex: str = ""
    #: 预编译路径下从 `.tex` 的 `document` 环境里抽出的正文文本。
    prebuilt_body: str = ""

    @property
    def body_text(self) -> str:
        """正文文本。

        ⚠️ **预编译路径必须回退到 `.tex` 的正文**：否则正文计数为 0，
        会把一篇 27.5 KB 的成品论文报成「空正文」——实测正是这个误判
        让导出产出 2 页桩 PDF 还回报 `ok: true`（P0）。
        """
        if self.sections:
            return "\n".join(s.body for s in self.sections)
        return self.prebuilt_body

    @property
    def is_prebuilt(self) -> bool:
        """是否走「agent 直出成品 → 引擎只编译不重建」路径。"""
        return self.body_source == "prebuilt_tex" and bool(self.prebuilt_tex)

    def budget(self) -> ty.PageBudget:
        return ty.page_budget(self.template, self.body_text, language=self.language)


#: 预编译路径下，从 `.tex` 里抽正文的边界（`document` 环境）。
_DOC_BEGIN_RE = re.compile(r"\\begin\{document\}")
_DOC_END_RE = re.compile(r"\\end\{document\}")


def extract_tex_body(tex_text: str) -> str:
    """从成品 `.tex` 里抽出 `document` 环境内的正文。

    只用于**计数与去 AI 味检查**——不解析、不改写，
    更不会拿它去重建 `.tex`（重建就等于覆盖 agent 的成品）。
    """
    m = _DOC_BEGIN_RE.search(tex_text)
    start = m.end() if m else 0
    e = _DOC_END_RE.search(tex_text, start)
    end = e.start() if e else len(tex_text)
    return tex_text[start:end].strip()


def _is_engine_generated(text: str) -> bool:
    """一份 `.tex` 是否由**本引擎**生成（看首行生成标记）。

    延迟导入 `latex_export`：它反向依赖本模块，模块级导入会成环。
    取不到标记函数时用同值常量兜底，保证判定不静默失效。
    """
    if not text.strip():
        return False
    try:
        from .latex_export import is_engine_generated  # noqa: PLC0415
        return is_engine_generated(text)
    except Exception:                                     # noqa: BLE001
        first = text.lstrip("\ufeff").splitlines()[0].strip()
        return first == "% modemon:generated-latex-export"


def detect_prebuilt_tex(workspace: Path) -> Optional[Path]:
    """检测 agent **直出**的成品 `paper/main.tex`。

    判据（缺一不可）：
      1. 文件存在且非空；
      2. **没有引擎生成标记**（有标记 = 引擎自己的产物，可安全重建）；
      3. 是**自洽可编译的完整文档**（有 `\\documentclass` 与 `document` 环境）。

    为什么不看文件大小：大小是脆弱阈值（1,845 B 的桩与 2,500 B 的短文
    无法用体量区分），而"有没有 `documentclass`、有没有被标记"是**结构事实**。
    """
    p = Path(workspace) / "paper" / "main.tex"
    if not p.is_file():
        return None
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if not text.strip() or _is_engine_generated(text):
        return None
    if "\\documentclass" not in text or not _DOC_BEGIN_RE.search(text):
        return None
    return p


def parse_markdown(text: str, *, start_level: int = 1) -> list[Section]:
    """把 Markdown 切成章节。

    **层级映射**：论文正文里 `#` 通常是文档标题，因此顶层章节从 `##` 开始。
    映射为 `level = clamp(len(#) - 1, 1, 3)`：
        `#`  → 1（若与文档标题重复，由调用方忽略）
        `##` → 1（\\section）
        `###` → 2（\\subsection）
        `####` → 3（\\subsubsection）

    只做章节切分，**不做复杂 Markdown 转换**——转换交给各导出器，
    这样同一份内容可以分别产出 docx 与 LaTeX 而语义一致。
    """
    sections: list[Section] = []
    cur: Optional[Section] = None
    buf: list[str] = []

    def flush() -> None:
        if cur is not None:
            cur.body = "\n".join(buf).strip()
            sections.append(cur)

    for line in text.splitlines():
        m = HEADING_RE.match(line)
        if m:
            flush()
            level = min(3, max(1, len(m.group(1)) - 1 + (start_level - 1)))
            cur = Section(level=level, title=m.group(2).strip())
            buf = []
        else:
            buf.append(line)
    flush()
    return sections


def build_paper(
    workspace: Path,
    *,
    template: str = "comp_zh",
    language: str = "zh",
    title: str = "",
    abstract: str = "",
    keywords: Optional[list[str]] = None,
) -> tuple[PaperDoc, list[str]]:
    """从工作区装配论文。

    正文来源优先级（**引擎与 agent 的格式约定**，与 `comp-paper-zh` 提示配套）：
      1. `paper/sections/*.md` 或 `*.tex` —— 约定格式，引擎按文件名装配
      2. `paper/main.md`（读到「## 附录」之前）—— 兼容旧路径
      3. agent 直出的成品 `paper/main.tex`（无引擎生成标记）
         —— 走「只编译不重建」，正文按该文件计数，**不覆盖、不重建**

    三种情形都记在 `doc.body_source`（`sections` / `main_md` / `prebuilt_tex`），
    下游导出据此决定"重新生成"还是"只编译"，避免把成品当空正文。

    Returns:
        (论文模型, 警告列表)
    """
    ws = Path(workspace)
    notes: list[str] = []
    doc = PaperDoc(title=title, abstract=abstract, template=template,
                   language=language, keywords=list(keywords or []))

    # --- 正文 ---
    # ★ **引擎侧格式约定**（与 `comp-paper-zh` 步骤提示配套）：
    #   1. `paper/sections/*.md`（约定格式：分节 Markdown，引擎装配）
    #   2. `paper/main.md`（兼容旧路径，读到「## 附录」之前）
    #   3. 以上都没有、但存在 agent **直出**的成品 `paper/main.tex`
    #      → 走「只编译不重建」路径，**不得**当作空正文
    # 实测背景：约定缺失时引擎读到 `body_chars=0`，把一篇 27.5 KB 的成品论文
    # 报成空正文，产出 2 页桩 PDF，并在导出时覆盖 agent 的 `.tex`（P0）。
    sec_dir = ws / "paper" / "sections"
    raw = ""
    if sec_dir.is_dir():
        parts = []
        for p in sorted(sec_dir.iterdir()):
            if p.suffix.lower() in (".md", ".markdown"):
                parts.append(p.read_text(encoding="utf-8", errors="replace"))
            elif p.suffix.lower() == ".tex":
                # .tex 视为已是 LaTeX，按原样保留为章节体
                parts.append(p.read_text(encoding="utf-8", errors="replace"))
        if parts:
            raw = "\n\n".join(parts)
            doc.body_source = "sections"
            notes.append(f"正文来自约定目录 `paper/sections/`：{len(parts)} 个分节文件")
    if not raw.strip():
        main_md = ws / "paper" / "main.md"
        if main_md.is_file():
            raw = main_md.read_text(encoding="utf-8", errors="replace")
            raw = raw.split("## 附录")[0]
            if raw.strip():
                doc.body_source = "main_md"
                notes.append("正文来自 `paper/main.md`（兼容路径；"
                             "约定格式是 `paper/sections/*.md`）")
    if not raw.strip():
        prebuilt = detect_prebuilt_tex(ws)
        if prebuilt:
            doc.body_source = "prebuilt_tex"
            doc.prebuilt_tex = "paper/main.tex"
            doc.prebuilt_body = extract_tex_body(
                prebuilt.read_text(encoding="utf-8", errors="replace"))
            notes.append(
                "检测到 agent 直出的成品 `paper/main.tex`（无引擎生成标记）"
                "→ 走「**只编译不重建**」路径：正文按该文件计数，"
                "不按 Markdown 重新装配，也不覆盖它")
        else:
            # 诊断价值：有 `main.tex` 却读不到正文时，必须说清**为什么**，
            # 否则现场会重复踩「导出报 2 页桩」的坑而找不到原因。
            stray = ws / "paper" / "main.tex"
            if stray.is_file():
                try:
                    txt = stray.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    txt = ""
                if txt.strip() and not _is_engine_generated(txt):
                    notes.append(
                        "`paper/main.tex` 存在，但**不是自洽可编译的完整文档**"
                        "（缺 `\\documentclass` 或 `document` 环境），"
                        "无法走「只编译不重建」；请把正文改写到 `paper/sections/*.md`")
            notes.append("未找到正文（paper/sections/*.md 或 paper/main.md）")

    doc.sections = parse_markdown(raw) if raw.strip() else []
    if not doc.title:
        # 从正文首个一级标题兜底
        h1 = next((s for s in doc.sections if s.level == 1), None)
        doc.title = h1.title if h1 else "数学建模竞赛论文"

    # --- 表格（程序生成，不经模型） ---
    src = load_results(ws)
    if not src.ok:
        notes.append(f"数据真相源不可用：{src.error}")
    else:
        t1 = build_result_table(src)
        if t1:
            doc.tables.append(t1)
        t2 = build_record_table(src)
        if t2:
            doc.tables.append(t2)
        if not doc.tables:
            notes.append("all_results.json 中未发现可成表的标量或记录数组")

    # --- 图表 ---
    doc.figures = collect_figures(ws)
    manifest = parse_figure_manifest(ws)
    if manifest:
        by_name = {m.name: m for m in manifest}
        for f in doc.figures:
            stem = Path(f.path).stem
            if stem in by_name:
                # 清单的章节归属**优先于**文件名前缀
                f.section = by_name[stem].section
                f.caption = by_name[stem].caption or f.caption
        notes.append(f"FIGURE_MANIFEST 提供 {len(manifest)} 条归类")

    # ★ 图注缺失要**显式告警**，不要悄悄编造一个英文名。
    #   视觉自检抓过这条：「图题为『图 1 scenarios』，使用英文单词
    #   且未对图表做完整中文描述，不符合中文论文图题规范」。
    #   编造一个像模像样的标题比留白更糟——它掩盖了缺失。
    for f in doc.figures:
        if not f.caption:
            notes.append(f"图 `{Path(f.path).name}` **缺少图注**"
                         f"（导出时使用占位名「{f.display_caption}」）；"
                         f"请在 FIGURE_MANIFEST.md 中补充中文图注")

    # --- 参考文献 ---
    bib = ws / "paper" / "references.md"
    if bib.is_file():
        for line in bib.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                doc.references.append(re.sub(r"^\s*[-*\d.\[\]]+\s*", "", s))
    return doc, notes


__all__ = [
    "ResultsSource", "TableSpec", "FigureRef", "ManifestEntry", "Section", "PaperDoc",
    "load_results", "build_result_table", "build_record_table", "write_table_files",
    "collect_figures", "parse_figure_manifest", "ascii_safe_name", "parse_markdown",
    "build_paper", "format_value", "FIGURE_RE", "MANIFEST_ITEM_RE", "pretty_figure_name",
    # 格式约定 + 标签唯一性（流 C）
    "detect_prebuilt_tex", "extract_tex_body", "unique_labels", "table_label_duplicates",
    "GROUP_LABELS", "GROUP_TOKENS", "VARIABLE_NAME_COLUMNS", "FIELD_LABELS",
]
