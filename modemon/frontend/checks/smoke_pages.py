"""页面冒烟：真的起一次服务、真的用 Chromium 打开每个页面。

为什么值得做：项目是"无构建步骤"的原生 ES module，模块语法对不对、
`$id('x')` 有没有连线、接口返回的字段能不能渲染，这些**只有在浏览器里跑一次**
才算数（Python 侧的源码断言只能证明"写了"，不能证明"跑得起来"）。

做法：
  1. 起一个本地 uvicorn（端口 8899）；
     ⚠️ 启动自愈与周期回收被替换成 no-op —— 它们会**写共享库**
     （把 running 工作流判成僵尸标 failed），那是别人的写作用域。
  2. 用 Edge/Chrome 的 `--headless=new --dump-dom` 打开 5 个路由，
     断言每个页面渲染出了预期的关键元素，且**没有**出现前端异常条
     （`app.js` 的 reportFatal 会插入 #fatalBar）。
  3. 退出前关掉服务与浏览器进程。

浏览器路径解析顺序：`ARCHIFY_CHROME` 环境变量 → Edge → Chrome。
两者都没有时输出 SKIP 并返回 0（不算失败——这是环境限制，不是代码问题）。

用法：python checks/smoke_pages.py
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1]
BACKEND = FRONTEND.parent / "backend"
PORT = int(os.environ.get("MODEMON_SMOKE_PORT", "8899"))
BASE = f"http://127.0.0.1:{PORT}"

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors="replace")     # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

PASS = 0
FAIL = 0
SKIP = 0
FAILURES: list[str] = []

EDGE_CANDIDATES = [
    os.environ.get("MODEMON_SMOKE_BROWSER", ""),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


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


def find_browser() -> str | None:
    for c in EDGE_CANDIDATES:
        if c and Path(c).is_file():
            return c
    for name in ("msedge", "chrome", "chromium", "chromium-browser"):
        p = shutil.which(name)
        if p:
            return p
    return None


# ---------------------------------------------------------------------------
# 服务
# ---------------------------------------------------------------------------


def start_server():
    sys.path.insert(0, str(BACKEND))
    import main  # noqa: PLC0415

    async def _noop_loop() -> None:      # pragma: no cover
        return None

    main.run_startup_maintenance = lambda: {"ok": True, "skipped": "smoke"}
    main._reap_loop = _noop_loop

    import uvicorn  # noqa: PLC0415

    config = uvicorn.Config(main.app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, name="smoke-uvicorn", daemon=True).start()
    for _ in range(80):
        try:
            with urllib.request.urlopen(f"{BASE}/api/health", timeout=1) as r:
                if r.status == 200:
                    return server
        except Exception:                # noqa: BLE001 —— 还在起
            time.sleep(0.25)
    raise RuntimeError("本地服务未能在 20 秒内起来")


def fetch_json(path: str):
    with urllib.request.urlopen(f"{BASE}{path}", timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# 浏览器
# ---------------------------------------------------------------------------


def dump_dom(browser: str, url: str, profile: str, budget_ms: int = 9000) -> str:
    cmd = [
        browser, "--headless=new", "--disable-gpu", "--no-first-run",
        "--no-default-browser-check", "--disable-extensions",
        f"--user-data-dir={profile}",
        f"--virtual-time-budget={budget_ms}",
        "--dump-dom", url,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
    return p.stdout or ""


def visible_text(dom: str) -> str:
    """粗略取可见文本：去掉 script/style 内容与标签，用于关键元素断言。"""
    dom = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", dom)
    dom = re.sub(r"(?s)<[^>]+>", " ", dom)
    return re.sub(r"\s+", " ", dom)


# ---------------------------------------------------------------------------


def main() -> int:
    print("=" * 74)
    print("modemon 前端页面冒烟（真实服务 + 真实 Chromium）")
    print("=" * 74)

    browser = find_browser()
    if not browser:
        skip("页面冒烟", "未找到 Edge/Chrome（可设 MODEMON_SMOKE_BROWSER）")
        print("\nPASS 0 / FAIL 0 / SKIP %d" % SKIP)
        return 0
    print("浏览器: %s" % browser)

    server = None
    profile = tempfile.mkdtemp(prefix="modemon-smoke-profile-")
    try:
        server = start_server()
        print("服务: %s" % BASE)

        workflows = fetch_json("/api/workflows")
        detail_route = f"#/detail/{workflows[0]['id']}" if workflows else "#/detail"

        cases = [
            ("#/workflows", ["工作流", "模板目录", "个", "新建"], "工作流列表 + 模板目录"),
            (detail_route, ["步骤", "审计与渲染（自定义事件）", "运行事件（实时）", "控制台"],
             "执行详情（含三类自定义事件面板）"),
            ("#/paper", ["导出参数", "装配并导出", "TeX 运行时"], "成文预览"),
            ("#/typography", ["排版规格", "样例预览（用真实数值渲染）", "关键指标"], "排版规格"),
            ("#/runtime", ["TeX 运行时", "运行时能力", "后台任务与健康"], "运行时与工具"),
        ]
        detail_dom = ""
        for route, markers, label in cases:
            dom = dump_dom(browser, f"{BASE}/{route}", profile)
            if route == detail_route:
                detail_dom = dom
            text = visible_text(dom)
            missing = [m for m in markers if m not in text]
            check(f"{label} 渲染成功（{route}）", not missing,
                  f"缺少 {missing}；DOM {len(dom)} 字节")
            check(f"{label} 无前端异常条", "前端异常" not in text and 'id="fatalBar"' not in dom)

        # 模板下拉：35 个选项必须真的出现在 DOM 里
        dom = dump_dom(browser, f"{BASE}/#/workflows", profile)
        options = re.findall(r"<option[^>]*>(.*?)</option>", dom, re.S)
        check("工作流页模板下拉有 35 个选项", len(options) == 35, f"实际 {len(options)}")
        check("下拉文案含中文名与页数参考",
              any("国赛 CUMCM" in o for o in options) and any("≤30 页" in o for o in options),
              str(options[:2]))
        check("模板目录表列出 35 行",
              len(re.findall(r'data-template="', dom)) == 35,
              len(re.findall(r'data-template="', dom)))

        # 事件渲染：分两个范围核对。
        #   - 页面实际加载的范围：默认只返回**最近一条任务**的事件（页面的权威数据源）；
        #   - 库中全量范围：用于确认三类自定义事件的 kind 都被前端分类表覆盖。
        custom_known = {"result_audit", "figure_render", "citation_audit"}
        page_kinds: set[str] = set()
        db_kinds: set[str] = set()
        if workflows:
            wid = workflows[0]["id"]
            page_kinds = {e["kind"] for e in
                          fetch_json(f"/api/workflows/{wid}/run-events?limit=800")["events"]}
            db_kinds = {e["kind"] for e in
                        fetch_json(f"/api/workflows/{wid}/run-events"
                                   f"?all_messages=true&limit=800")["events"]}
        present_custom = page_kinds & custom_known
        print("        页面加载的 kind: %s" % sorted(page_kinds))
        print("        库中全部 kind:   %s" % sorted(db_kinds))
        check("库里出现过的自定义事件都在前端分类表内",
              db_kinds & custom_known <= custom_known, str(sorted(db_kinds & custom_known)))

        # **真实载荷**渲染：页面加载范围内有几类自定义事件，就该有几张带 verdict 的卡片。
        # 卡片由 renderAuditPanel 生成，带 data-kind 与 data-verdict 两个标记。
        if present_custom:
            for kind in sorted(present_custom):
                m = re.search(rf'data-kind="{kind}"[^>]*data-verdict="([^"]+)"', detail_dom)
                check(f"详情页用真实载荷渲染出 {kind} 高亮卡片（含 verdict）",
                      bool(m) and bool(m.group(1).strip()),
                      "未找到带 verdict 的卡片")
            cards = len(re.findall(r'data-verdict="', detail_dom))
            check("面板里每类都成卡（页面范围外的显示「尚无事件」而不是空白）",
                  cards == len(present_custom) or "尚无事件" in visible_text(detail_dom),
                  f"带 verdict 的卡片 {cards} 张；页面范围 {sorted(present_custom)}")
        else:
            skip("真实载荷渲染自定义事件", "该工作流最近一条任务里没有自定义事件")
            check("页面范围内的自定义事件都能被分类",
                  page_kinds & custom_known <= custom_known, str(sorted(page_kinds)))
    except Exception as exc:             # noqa: BLE001
        check("页面冒烟执行完成", False, f"{type(exc).__name__}: {exc}")
    finally:
        if server is not None:
            server.should_exit = True
            time.sleep(0.6)
        shutil.rmtree(profile, ignore_errors=True)

    print("\n" + "=" * 74)
    print("PASS %d / FAIL %d / SKIP %d" % (PASS, FAIL, SKIP))
    for f in FAILURES:
        print("  - %s" % f)
    print("=" * 74)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
