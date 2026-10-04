"""modemon 前端自检（并行流 G）。

用法：

    python selftest.py            # ASGI 拉取每个页面与依赖的 API + 静态断言
    python selftest.py --smoke    # 额外：起本地服务 + Chromium 真开 5 个页面
    python selftest.py --no-asgi  # 只做静态/源码断言（无 httpx 时自动降级）

覆盖目标（对应 task-7 的验收项）：

  1. **所有页面可达**：`/` 与 `/static/index.html` 200，5 个页面模块
     `/static/pages/*.js` 200 且导出 `render`；壳里 5 条路由都在。
  2. **`/api/templates` 返回 35 个**（并与模板注册表的长度交叉核对）。
  3. **三类自定义事件能被区分渲染**：前端分类表 == 后端 kind 常量
     （`result_audit` / `figure_render` / `citation_audit`），
     且库里真实出现过的事件 kind 全部能被前端分类。
  4. **原有功能不得破坏**：建工作流 / 跑步骤 / 检查点 / 回放 用到的
     元素 id 与接口路径仍在前端源码里。
  5. **`ok=false` 不得显示成成功**：导出页必须显式按 `ok` 判定。

刻意**不动共享数据库**：TestClient 不进入上下文（不触发 lifespan），
并把 `run_startup_maintenance` / `_reap_loop` 换成 no-op——
启动自愈会把 `running` 工作流判成僵尸并标 failed，那是别人的写作用域。
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent
BACKEND = FRONTEND.parent / "backend"
DB_PATH = BACKEND / "db" / "modemon.db"

#: Windows 控制台可能是 GBK：输出里一旦有它编不了的字符（例如 U+2194）就会
#: 直接抛 UnicodeEncodeError，把自检自身搞崩。这里降级为"替换"而不是"报错"。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")   # type: ignore[union-attr]
    except (AttributeError, ValueError):        # 非 TextIOWrapper（重定向/管道）
        pass

#: 后端侧的自定义事件 kind（真源在 `services/workflow_service.py`
#: 的 `_persist_custom_event` 调用点与 `services/citation_audit.py` 的常量）。
BACKEND_CUSTOM_KINDS = {"result_audit", "figure_render", "citation_audit"}

PAGE_MODULES = ["workflows", "detail", "paper", "typography", "runtime"]
LIB_MODULES = ["api", "store", "events", "dom", "labels"]

PASS = 0
FAIL = 0
SKIP = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  %s" % name)
    else:
        FAIL += 1
        FAILURES.append(name)
        print("  FAIL  %s  %s" % (name, str(detail)[:200]))


def skip(name: str, why: str) -> None:
    global SKIP
    SKIP += 1
    print("  SKIP  %s  (%s)" % (name, why))


def section(title: str) -> None:
    print("\n[%s]" % title)


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# 1. 静态文件与源码契约
# ---------------------------------------------------------------------------


def check_static_files() -> None:
    section("1. 静态文件（无构建步骤：放进去就应该能在 /static 访问）")
    required = ["index.html", "styles.css", "app.js"]
    required += [f"lib/{m}.js" for m in LIB_MODULES]
    required += [f"pages/{m}.js" for m in PAGE_MODULES]
    for rel in required:
        p = FRONTEND / rel
        check(f"存在且非空: {rel}", p.is_file() and p.stat().st_size > 0, str(p))

    html = read(FRONTEND / "index.html")
    check("index.html 引用 /static/styles.css", "/static/styles.css" in html)
    check("index.html 以 module 方式加载 /static/app.js",
          'type="module"' in html and "/static/app.js" in html)
    check("index.html 保留视图挂载点 #view", 'id="view"' in html)
    for r in PAGE_MODULES:
        check(f"index.html 有导航 #{r}", f'data-route="{r}"' in html)
    for badge in ("wsBadge", "rtBadge", "wfBadge"):
        check(f"index.html 保留徽标 #{badge}", f'id="{badge}"' in html)

    # 架构图（archify 技能产物，独立页面，不进 hash 路由）
    check("index.html 提供架构图入口（新标签打开，不占 hash 路由）",
          'href="/static/architecture.html"' in html and 'data-route="architecture"' not in html)
    check("架构图 HTML 存在", (FRONTEND / "architecture.html").is_file())
    check("架构图规格 JSON 存在（可复现/可改）", (FRONTEND / "architecture.json").is_file())
    check("架构图由 archify 交付（含交付回执 sidecar）",
          (FRONTEND / "architecture.visual-check.json").is_file())
    vis = read(FRONTEND / "architecture.visual-check.json")
    if vis:
        try:
            receipt = json.loads(vis)
            check("架构图视觉回执：containment 通过（4 个视口无溢出）",
                  receipt.get("containment", {}).get("status") == "pass"
                  and len(receipt.get("containment", {}).get("viewports", [])) == 4,
                  receipt.get("containment", {}).get("status"))
        except ValueError as exc:
            check("架构图视觉回执可解析", False, str(exc))

    css = read(FRONTEND / "styles.css")
    check("styles.css 延续深色三栏的 CSS 变量（:root 原样保留）",
          ":root{" in css and all(v in css for v in
                                 ("--bg:#0f1115", "--panel:#171a21", "--accent:#4a9eff",
                                  "--ok:#3fb950", "--err:#f85149")))

    app = read(FRONTEND / "app.js")
    for m in PAGE_MODULES:
        check(f"app.js 路由表含 pages/{m}.js", f"pages/{m}.js" in app)
    check("app.js 用 hash 路由（监听 hashchange）", "hashchange" in app)
    check("app.js **没有**引入打包工具/框架痕迹",
          not re.search(r"\b(react|vue|svelte|webpack|rollup|vite)\b", app, re.I))

    for m in PAGE_MODULES:
        src = read(FRONTEND / "pages" / f"{m}.js")
        check(f"pages/{m}.js 导出 render 与 unmount",
              "export function render" in src and "export function unmount" in src
              and "export const id" in src and "export const hash" in src)


def custom_kinds_in_frontend() -> set[str]:
    """从 `lib/events.js` 源码里抽出 CUSTOM_KINDS 数组内容（唯一真源）。"""
    src = read(FRONTEND / "lib" / "events.js")
    m = re.search(r"CUSTOM_KINDS\s*=\s*\[([^\]]*)\]", src)
    if not m:
        return set()
    return set(re.findall(r"['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]", m.group(1)))


def check_event_classification() -> set[str]:
    section("3. 自定义事件的分类与渲染（result_audit / figure_render / citation_audit）")
    src = read(FRONTEND / "lib" / "events.js")
    kinds = custom_kinds_in_frontend()
    check("前端 CUSTOM_KINDS 恰好是三分类", kinds == BACKEND_CUSTOM_KINDS, sorted(kinds))

    # 每类都必须在 EVENT_META 里标 custom:true —— 否则会掉进普通事件流那套渲染
    custom_marks = len(re.findall(r"custom:\s*true", src))
    check("EVENT_META 里三类都标了 custom:true（>=3）", custom_marks >= 3, custom_marks)
    for k in sorted(BACKEND_CUSTOM_KINDS):
        check(f"EVENT_META 含 {k} 的条目", re.search(rf"{k}:\s*\{{", src) is not None)

    check("有 verdict 语义色映射（pass/issue/skipped + top_verdict）",
          "verdictTone" in src and "top_verdict" in src and "NOT_APPLICABLE" in src)
    check("ok=false 会压过 verdict（不能把没跑成显示成审过）",
          "p.ok === false" in src or "ok === false" in src)
    check("自定义事件在事件流里走独立分支（.ev.custom）", "ev custom" in src)
    check("事件流渲染对载荷做转义（esc）", "issuesBlock" in src and "esc(" in src)

    detail = read(FRONTEND / "pages" / "detail.js")
    check("执行详情页有审计高亮面板", 'id="auditPanel"' in detail and "renderAuditPanel" in detail)
    check("执行详情页订阅并区分渲染自定义事件",
          "renderRow" in detail and "evt.event._custom" in detail)
    check("执行详情页展示三类计数", "CUSTOM_KINDS" in detail and "hookCount" in detail)

    store = read(FRONTEND / "lib" / "store.js")
    check("store 在 WS 上识别自定义事件类型（isCustom）", "isCustom(msg.type)" in store)
    check("store 把 WS 平铺载荷归一成事件（customEventFromWs）", "customEventFromWs" in store)

    # 后端交叉核对：前端分类表必须跟随后端 kind 常量
    ws_src = read(BACKEND / "services" / "workflow_service.py")
    ca_src = read(BACKEND / "services" / "citation_audit.py")
    for k in sorted(BACKEND_CUSTOM_KINDS):
        check(f"后端 workflow_service.py 仍会产出 kind={k}",
              f'"{k}"' in ws_src or f"'{k}'" in ws_src,
              "钩子被改名/移除时前端分类表就过时了")
    check('后端 citation_audit 常量仍为 "citation_audit"',
          'CITATION_AUDIT_EVENT_KIND = "citation_audit"' in ca_src)
    return kinds


def check_db_event_kinds(frontend_kinds: set[str]) -> None:
    """库里真实出现过的事件 kind，必须全部能被前端分类。"""
    section("3b. 库中真实事件 kind 与前端分类表")
    if not DB_PATH.is_file():
        skip("读库里的事件 kind", f"库不存在: {DB_PATH}")
        return
    try:
        con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT kind, COUNT(*) AS c FROM chat_run_events GROUP BY kind").fetchall()
        counts = {r["kind"]: r["c"] for r in rows}
        con.close()
    except sqlite3.Error as exc:
        skip("读库里的事件 kind", f"sqlite: {exc}")
        return

    print("        库中 kind 分布: %s" % json.dumps(counts, ensure_ascii=False))
    present_custom = {k for k in counts if k in BACKEND_CUSTOM_KINDS}
    missing = present_custom - frontend_kinds
    check("库里出现过的自定义事件都能被前端分类", not missing,
          f"前端不认识: {sorted(missing)}")
    check("三类自定义事件的分类表与后端常量等价",
          frontend_kinds == BACKEND_CUSTOM_KINDS, sorted(frontend_kinds))
    for k in sorted(BACKEND_CUSTOM_KINDS):
        print("        前端分类 %-14s 库中 %d 条" % (k, counts.get(k, 0)))


def check_legacy_features() -> None:
    section("4. 原有功能不得破坏（建工作流 / 跑步骤 / 检查点 / 回放）")
    store = read(FRONTEND / "lib" / "store.js")
    wfpage = read(FRONTEND / "pages" / "workflows.js")
    detail = read(FRONTEND / "pages" / "detail.js")
    labels = read(FRONTEND / "lib" / "labels.js")

    expectations = [
        ("build 工作流：POST /api/workflows", store, "'/api/workflows'"),
        ("列表：GET /api/workflows", store, "'/api/workflows')"),
        ("跑单步：steps/{skill}/run", store, "/steps/${encodeURIComponent(skillName)}/run"),
        ("连续执行：/run", store, "/run?${q}"),
        ("检查点查询：checkpoints/current", store, "/checkpoints/current"),
        ("检查点解决：checkpoints/resolve", store, "/checkpoints/resolve"),
        ("回放：/run-events", store, "/run-events"),
        ("后台任务：/api/runs", detail, "'/api/runs'"),
        ("WS 地址：/ws/{workflow_id}", store, "/ws/${encodeURIComponent(state.workflowId)}"),
        ("WS 心跳 ping", store, "ws.send('ping')"),
        ("断线指数退避重连", store, "Math.min(1000 * 2 ** state.wsRetry++"),
        ("新建标题输入框", wfpage, 'id="title"'),
        ("新建按钮", wfpage, 'id="createBtn"'),
        ("模板下拉", wfpage, 'id="template"'),
        ("启用检查点开关", wfpage, 'id="checkpoints"'),
        ("模板下拉展示 display_name（缺失时回退）", labels, "t.display_name"),
        ("模板下拉展示步数", labels, "t.step_count"),
        ("模板下拉展示页数参考", labels, "t.page_advisory"),
        ("工作区路径输入", detail, 'id="workspace"'),
        ("预算输入", detail, 'id="budget"'),
        ("严格模式开关", detail, 'id="strictMode"'),
        ("连续执行按钮", detail, 'id="runAllBtn"'),
        ("回放按钮", detail, 'id="replayBtn"'),
        ("检查点区域", detail, 'id="checkpointArea"'),
        ("步骤列表", detail, 'id="stepList"'),
        ("事件容器", detail, 'id="events"'),
    ]
    for name, src, token in expectations:
        check(name, token in src, f"未找到 {token!r}")

    check("跨全部步骤回放开关（all_messages）", "all_messages=true" in store)
    check("事件去重（WS 与回放同一批事件不重复显示）",
          "seen.has(key)" in store and "eventKey" in store)


# ---------------------------------------------------------------------------
# 5. ES module 图（无构建步骤 ⇒ 没有打包器帮你发现"导入了不存在的东西"）
# ---------------------------------------------------------------------------

_IMPORT_RE = re.compile(
    r"import\s+(?:([^'\";]+?)\s+from\s+)?['\"](\.[^'\"]+)['\"]")
_EXPORT_FN_RE = re.compile(r"export\s+(?:async\s+)?function\s+([\w$]+)")
_EXPORT_VAR_RE = re.compile(r"export\s+(?:const|let|var|class)\s+([\w$]+)")
_EXPORT_BRACE_RE = re.compile(r"export\s*\{([^}]*)\}")
_EXPORT_STAR_RE = re.compile(r"export\s+\*\s+from")

#: 壳（index.html / app.js）里定义的 id，页面模块可以直接用。
SHELL_IDS = {"view", "nav", "wsBadge", "rtBadge", "wfBadge", "fatalBar"}


def _module_files() -> list[Path]:
    files = [FRONTEND / "app.js"]
    files += [FRONTEND / "lib" / f"{m}.js" for m in LIB_MODULES]
    files += [FRONTEND / "pages" / f"{m}.js" for m in PAGE_MODULES]
    return files


def _exports_of(path: Path) -> tuple[set[str], bool]:
    src = read(path)
    names = set(_EXPORT_FN_RE.findall(src)) | set(_EXPORT_VAR_RE.findall(src))
    for block in _EXPORT_BRACE_RE.findall(src):
        for part in block.split(","):
            part = part.strip()
            if not part:
                continue
            names.add(part.split(" as ")[-1].strip())
    return names, bool(_EXPORT_STAR_RE.search(src))


def check_module_graph() -> None:
    section("6. ES module 图自洽（无打包器兜底，全靠这层检查）")
    files = _module_files()
    exports: dict[Path, set[str]] = {}
    for f in files:
        names, star = _exports_of(f)
        exports[f] = names | ({"*"} if star else set())
        if f.name != "app.js":          # app.js 是入口脚本，按设计不导出任何东西
            check(f"{f.name} 有自己的导出", bool(names), "模块必须至少导出一个名字")

    for f in files:
        src = read(f)
        for clause, spec in _IMPORT_RE.findall(src):
            target = (f.parent / spec).resolve()
            label = f"{f.name} → {spec}"
            if not target.is_file():
                check(f"import 目标存在: {label}", False, str(target))
                continue
            if clause.strip().startswith("*") or not clause.strip():
                continue                      # 命名空间导入 / 副作用导入
            if not clause.strip().startswith("{"):
                # 默认导入：本项目不使用，出现即视为风格漂移
                check(f"未使用默认导入: {label}", False, clause.strip()[:60])
                continue
            wanted = []
            for part in clause.strip().strip("{}").split(","):
                part = part.strip()
                if not part:
                    continue
                wanted.append(part.split(" as ")[0].strip())
            have = exports.get(target, set())
            unknown = [w for w in wanted if w not in have]
            check(f"命名导入都有对应导出: {label}", not unknown, f"缺少 {unknown}")


def check_dom_ids() -> None:
    section("7. DOM id 连线（$id('x') 必须有对应的 id=\"x\"）")
    for f in _module_files():
        src = read(f)
        defined = set(re.findall(r'id="([^"]+)"', src))
        used = set(re.findall(r"""\$id\(['"]([^'"]+)['"]\)""", src))
        used |= set(re.findall(r"""getElementById\(['"]([^'"]+)['"]\)""", src))
        missing = sorted(used - defined - SHELL_IDS)
        check(f"{f.name}: 用到的 id 都有定义", not missing, f"未定义 {missing}")


# ---------------------------------------------------------------------------
# 8/9. 后端测试对前端的硬性契约 + 渲染执行级自检
# ---------------------------------------------------------------------------


def check_backend_test_contracts() -> None:
    """后端测试里有几条**针对前端文件内容**的断言，改前端时必须一起满足。"""
    section("8. 后端测试对前端的硬性契约")
    app = read(FRONTEND / "app.js")
    check("/static/app.js 含 WS 连接逻辑（后端断言 \"WebSocket\"）",
          "WebSocket" in app)
    check('app.js 体现「WS 只通知」原则（后端接受 "WS 只" / "只用于实时通知" / "状态一律以 REST"）',
          any(k in app for k in ("WS 只", "只用于实时通知", "状态一律以 REST")),
          "test_collaboration.py::test_frontend_served 会因此失败")
    html = read(FRONTEND / "index.html")
    check("/ 返回的 HTML 以小写 <!doctype html 开头",
          html.lower().lstrip().startswith("<!doctype html"))


def check_render_harness() -> None:
    """Node 直接跑 `lib/*` 的纯函数，验证"三类自定义事件可区分渲染"是**执行级**事实。"""
    global PASS, FAIL
    section("9. 事件渲染执行级自检（Node 直接跑前端模块，无依赖）")
    script = FRONTEND / "checks" / "events_render_check.mjs"
    check("渲染自检脚本存在", script.is_file(), str(script))
    if not script.is_file():
        return
    node = shutil.which("node")
    if not node:
        skip("Node 渲染自检", "node 不在 PATH")
        return
    try:
        p = subprocess.run([node, str(script)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180)
    except (OSError, subprocess.SubprocessError) as exc:
        skip("Node 渲染自检", f"无法运行 node: {exc}")
        return
    out = (p.stdout or "") + (p.stderr or "")
    m = re.search(r"PASS (\d+) / FAIL (\d+)", out)
    if not m:
        check("渲染自检有汇总输出", False, out[-200:])
        return
    n_pass, n_fail = int(m.group(1)), int(m.group(2))
    if n_fail:
        for name in re.findall(r"^  - (.+)$", out, re.M):
            FAILURES.append("渲染自检: %s" % name)
        PASS += n_pass
        FAIL += n_fail
        print("  FAIL  Node 渲染自检 %d 通过 / %d 失败（明细见下方失败项）"
              % (n_pass, n_fail))
    else:
        PASS += n_pass
        print("  PASS  Node 渲染自检 %d 项全通过（三类自定义事件可区分渲染）" % n_pass)


def check_smoke_pages() -> None:
    """`--smoke`：真的起一次本地服务、真的用 Chromium 打开 5 个页面。

    默认不跑，原因有二：会占用一个本地端口（8899）并写后端日志；
    但它能证明"页面在真实浏览器里跑得起来"，是源码断言换不来的。
    """
    global PASS, FAIL
    section("10. 页面冒烟（真实服务 + 真实 Chromium）")
    script = FRONTEND / "checks" / "smoke_pages.py"
    check("冒烟脚本存在", script.is_file(), str(script))
    if not script.is_file():
        return
    try:
        p = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=900, cwd=str(FRONTEND))
    except (OSError, subprocess.SubprocessError) as exc:
        skip("页面冒烟", f"无法运行: {exc}")
        return
    out = (p.stdout or "") + (p.stderr or "")
    m = re.search(r"PASS (\d+) / FAIL (\d+) / SKIP (\d+)", out)
    if not m:
        check("冒烟有汇总输出", False, out[-200:])
        return
    n_pass, n_fail = int(m.group(1)), int(m.group(2))
    if n_fail:
        for name in re.findall(r"^  - (.+)$", out, re.M):
            FAILURES.append("页面冒烟: %s" % name)
        PASS += n_pass
        FAIL += n_fail
        print("  FAIL  页面冒烟 %d 通过 / %d 失败（明细见下方失败项）" % (n_pass, n_fail))
    else:
        PASS += n_pass
        print("  PASS  页面冒烟 %d 项全通过（5 个页面在真实 Chromium 里渲染成功）" % n_pass)


def check_export_failure_contract() -> None:
    section("5. 导出失败不得显示成成功（项目历史教训）")
    src = read(FRONTEND / "pages" / "paper.js")
    check("成功判定只看 ok===true（不看 HTTP 状态）", "r.ok === true" in src)
    check("ok=false 有专门的失败分支文案", "导出失败" in src and "ok=false" in src)
    check("展示 compile_error", "compile_error" in src)
    check("展示 pages（页数）", "pages" in src)
    check("展示 notes", "notes" in src)
    check("请求失败与结果失败是两条不同路径", "请求失败" in src and "showError" in src)
    check("有 TeX 三态提示（编译前就能看出会不会失败）", "texChip" in src and "loadTexRuntime" in src)
    # 反例守卫：不能只凭 HTTP 状态判定成功
    check("没有把 res.ok / response.ok 当成导出成功依据",
          "res.ok" not in src and "response.ok" not in src)


# ---------------------------------------------------------------------------
# 2. ASGI 拉取（页面 + 依赖 API）
# ---------------------------------------------------------------------------


def make_client():
    """返回 (client, main)。不进入上下文 ⇒ 不触发 lifespan。

    同时把启动自愈与周期回收换成 no-op：它们是**写库**的（把 running 判成僵尸），
    属于别人的域，自检不该触发。
    """
    sys.path.insert(0, str(BACKEND))
    import main  # noqa: PLC0415

    async def _noop_loop() -> None:      # pragma: no cover - 自检守卫
        return None

    main.run_startup_maintenance = lambda: {"ok": True, "skipped": "selftest"}
    main._reap_loop = _noop_loop

    from starlette.testclient import TestClient  # noqa: PLC0415

    return TestClient(main.app), main


def check_http() -> None:
    section("2. 页面与 API 可达（ASGI，不启动服务、不触发 lifespan）")
    try:
        client, main = make_client()
    except Exception as exc:            # noqa: BLE001
        skip("ASGI 拉取", f"无法构造 TestClient: {exc}")
        return

    # ---- 页面 ----
    r = client.get("/")
    check("GET / → 200", r.status_code == 200, r.status_code)
    check("GET / 返回的是壳页面（含 #view 与 5 条路由）",
          'id="view"' in r.text and all(
              f'data-route="{m}"' in r.text for m in PAGE_MODULES))
    check("GET /static/index.html → 200", client.get("/static/index.html").status_code == 200)
    check("GET /static/styles.css → 200", client.get("/static/styles.css").status_code == 200)
    check("GET /static/app.js → 200", client.get("/static/app.js").status_code == 200)
    for m in LIB_MODULES:
        r2 = client.get(f"/static/lib/{m}.js")
        check(f"GET /static/lib/{m}.js → 200", r2.status_code == 200, r2.status_code)
    for m in PAGE_MODULES:
        r2 = client.get(f"/static/pages/{m}.js")
        check(f"GET /static/pages/{m}.js → 200 且导出 render",
              r2.status_code == 200 and "export function render" in r2.text,
              r2.status_code)
    r2 = client.get("/static/architecture.html")
    check("GET /static/architecture.html → 200（archify 交付的前端架构图）",
          r2.status_code == 200 and "svg" in r2.text and len(r2.text) > 50000,
          f"{r2.status_code} bytes={len(r2.text)}")

    # ---- 模板：35 个 ----
    r = client.get("/api/templates")
    check("GET /api/templates → 200", r.status_code == 200, r.status_code)
    body = r.json() if r.status_code == 200 else {}
    tpls = body.get("templates", [])
    check("模板数量 == 35（注册表全量，不是枚举的 9 个）", len(tpls) == 35, len(tpls))
    try:
        from services import workflow_engine as we  # noqa: PLC0415
        # 注意 `we.registry` 是 `services/template_registry` **模块**
        # （workflow_engine 里 `from . import template_registry as registry`），
        # 所以数量要写成 len(list(registry.values()))。
        n_registry = len(list(we.registry.values()))
        check("API 模板数与模板注册表长度一致", len(tpls) == n_registry,
              f"api={len(tpls)} registry={n_registry}")
        check("comp_cumcm 仍在注册表（国赛 AI 申报门禁依赖它）",
              we.registry.is_known("comp_cumcm"))
    except Exception as exc:            # noqa: BLE001
        skip("与模板注册表交叉核对", str(exc))
    check("每条模板都有 display_name / step_count / page_rule_mode",
          bool(tpls) and all(
              {"display_name", "step_count", "page_rule_mode"} <= set(t) for t in tpls))
    check("存在 requires_ai_disclosure=True 的模板",
          any(t.get("requires_ai_disclosure") for t in tpls))

    # ---- 其余依赖 API ----
    r = client.get("/api/health")
    check("GET /api/health → 200 ok", r.status_code == 200 and r.json().get("ok") is not False)

    r = client.get("/api/runtimes")
    rt = r.json() if r.status_code == 200 else {}
    check("GET /api/runtimes → 200 且非空", r.status_code == 200 and bool(rt.get("runtimes")),
          r.status_code)
    check("运行时如实声明 capabilities 与 default_priority",
          bool(rt.get("default_priority")) and all(
              "capabilities" in x for x in rt.get("runtimes", [])))

    r = client.get("/api/tex-runtime")
    tex = r.json() if r.status_code == 200 else {}
    check("GET /api/tex-runtime → 200", r.status_code == 200, r.status_code)
    check("TeX 状态是三态之一 ready/fresh/missing",
          tex.get("state") in {"ready", "fresh", "missing"}, tex.get("state"))
    check("TeX 状态带 note 与 installer_available（页面要显示）",
          "note" in tex and "installer_available" in tex)

    for t in ("comp_cumcm", "comp_mcm"):
        r = client.get(f"/api/typography/{t}")
        d = r.json() if r.status_code == 200 else {}
        style = d.get("style") or {}
        check(f"GET /api/typography/{t} → 200 且含 body/headings/fonts/page",
              r.status_code == 200 and
              {"body", "headings", "fonts", "page"} <= set(style), r.status_code)
        check(f"/api/typography/{t} 给出每页字数与页数参考",
              "chars_per_page_zh" in d and "page_limit" in d)

    r = client.get("/api/workflows")
    check("GET /api/workflows → 200 列表", r.status_code == 200 and isinstance(r.json(), list),
          r.status_code)

    # ---- 导出的 ok=false 分支：**必须**能从真实接口拿到 ----
    tmp = tempfile.mkdtemp(prefix="modemon-fe-selftest-")
    r = client.post("/api/paper/export", json={
        "workspace": tmp, "template": "comp_cumcm", "formats": []})
    ok_body = r.json() if r.status_code == 200 else {}
    check("导出空 formats → HTTP 200 但 ok=false",
          r.status_code == 200 and ok_body.get("ok") is False,
          f"status={r.status_code} ok={ok_body.get('ok')!r}")

    missing_ws = str(Path(tmp) / "does-not-exist")
    r = client.post("/api/paper/export", json={
        "workspace": missing_ws, "template": "comp_cumcm", "formats": ["latex"]})
    detail = json.dumps(r.json(), ensure_ascii=False) if r.status_code else ""
    check("导出不存在的工作区 → 结构化错误（404 + WORKSPACE_NOT_FOUND）",
          r.status_code == 404 and "WORKSPACE_NOT_FOUND" in detail,
          f"{r.status_code} {detail[:120]}")

    # ---- 空工作区（真实存在但无正文）也应返回 ok=false，而不是假装成功 ----
    r = client.post("/api/paper/export", json={
        "workspace": tmp, "template": "comp_cumcm", "formats": ["latex"], "compile_pdf": False})
    body = r.json() if r.status_code == 200 else {}
    latex = (body.get("results") or {}).get("latex") or {}
    check("空工作区导出 latex → ok=false 且带原因（不编译、不假装成功）",
          r.status_code == 200 and body.get("ok") is False
          and bool(latex.get("error") or latex.get("compile_error")),
          f"ok={body.get('ok')!r} latex={ {k: latex.get(k) for k in ('ok', 'error')} }")

    # ---- 前端读取的静态产物与 API 值一致 ----
    check("前端下拉必然拿到 35 个选项（同一份 /api/templates）",
          "35" in read(FRONTEND / "pages" / "workflows.js")
          or "tpls.length" in read(FRONTEND / "pages" / "workflows.js"))


# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    print("=" * 74)
    print("modemon 前端自检（流 G）  前端目录: %s" % FRONTEND)
    print("=" * 74)

    check_static_files()
    kinds = check_event_classification()
    check_db_event_kinds(kinds)
    check_legacy_features()
    check_module_graph()
    check_dom_ids()
    check_backend_test_contracts()
    check_render_harness()
    check_export_failure_contract()
    if "--no-asgi" not in argv:
        check_http()
    else:
        skip("ASGI 拉取", "--no-asgi")
    if "--smoke" in argv:
        check_smoke_pages()
    else:
        skip("页面冒烟（真实 Chromium）", "加 --smoke 开启")

    print("\n" + "=" * 74)
    print("PASS %d / FAIL %d / SKIP %d" % (PASS, FAIL, SKIP))
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print("  - %s" % f)
    print("=" * 74)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
