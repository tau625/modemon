"""`/api/editor/{wf_id}/*` 域端点的集成测试（真跑 HTTP 栈）。

覆盖两件事：
  1. **功能真的能用**：文件 CRUD 往返、上传/下载、HTML 预览、编译产物、
     stats / mode / model-options——全部经 TestClient 走完整 FastAPI 栈
     （Pydantic 校验、依赖注入、错误处理器）。
  2. **路径穿越必须被拒**（本域的头号风险）。

第 2 部分是重点。每个反例都对应一种**真实可用的绕过手法**，并且断言分两层：
  - 状态码是 400/403（不是 200）；
  - **效果层**——工作区外的目标文件既没被读到（响应体里不含其内容），
    也没被写到（磁盘上不存在）。

只断言状态码是不够的：状态码对了但内容已经泄漏，测试照样"通过"。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import main as app_module  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from routers import editor as ed  # noqa: E402
from services import tex_runtime as tx  # noqa: E402

PASS = 0
FAIL = 0
FAILURES: list[str] = []

#: 工作区外的"机密"文件内容。任何一次泄漏都能靠它被检出。
OUTSIDE_SECRET = "OUTSIDE-SECRET-DO-NOT-LEAK-9f3a"

#: 路径穿越反例。分四类：POSIX 绝对、Windows 绝对/UNC、`..` 变体、内核特殊名。
TRAVERSAL_CASES = [
    "/etc/passwd",
    "/etc/shadow",
    "C:\\Windows\\win.ini",
    "C:/Windows/win.ini",
    "\\\\server\\share\\secret.txt",
    "//server/share/secret.txt",
    "../../etc/passwd",
    "../../../etc/passwd",
    "..\\..\\Windows\\win.ini",
    "..\\..\\..\\Windows\\System32\\drivers\\etc\\hosts",
    "paper/../../secret.txt",
    "a/../../b.txt",
    "sub/./../../x.txt",
    "NUL",
    "aux.txt",
    "com1",
    "trail. ",
    "\x00abc",
    "sub/\x01bad.txt",
]


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  %s" % name)
    else:
        FAIL += 1
        FAILURES.append(name)
        print("  FAIL  %s  %s" % (name, detail[:200]))


def new_client() -> tuple[TestClient, Path]:
    """每轮独立临时目录 + 独立 DB，互不污染。"""
    td = Path(tempfile.mkdtemp(prefix="modemon-editor-"))
    app_module.DB_PATH = td / "modemon.db"
    app_module.init_db()
    return TestClient(app_module.app), td


def make_wf(c: TestClient, ws: Path, *, template: str = "comp_cumcm",
            params: dict | None = None) -> str:
    """建工作流；`workspace_dir` 直接写库（等价于服务端配置了工作区根）。"""
    wf_id = c.post("/api/workflows",
                   json={"template": template, "title": "editor"}).json()["id"]
    con = app_module.get_db()
    try:
        con.execute("UPDATE workflows SET workspace_dir=?, params=? WHERE id=?",
                    (str(ws), json.dumps(params or {}), wf_id))
        con.commit()
    finally:
        con.close()
    return wf_id


def err_code(resp) -> str:
    detail = resp.json().get("detail")
    return detail.get("code", "") if isinstance(detail, dict) else ""


def miss_tex_runtime():
    """把 TeX 探测打成"不可用"，让编译用例**快且确定**。

    不这么做的话 `compile_tex` 会去 glob 并真实 probe 系统 TeX
    （本机 D:\\04_IDEs\\texlive 存在），单次用例可能跑几十秒。
    这里只替换运行时来源，`export_latex` 自身的逻辑照常执行。
    """
    return lambda **_kw: tx.TexRuntime(state="missing", note="test-stub")


# ---------------------------------------------------------------------------


def test_routes_registered() -> None:
    print("\n[1] 路由注册与未知工作流")
    paths = {p: sorted(v) for p, v in app_module.app.openapi()["paths"].items()
             if p.startswith("/api/editor")}
    expected = {
        "/api/editor/{wf_id}/files": ["get"],
        "/api/editor/{wf_id}/file": ["delete", "get", "put"],
        "/api/editor/{wf_id}/create-file": ["post"],
        "/api/editor/{wf_id}/upload": ["post"],
        "/api/editor/{wf_id}/download": ["get"],
        "/api/editor/{wf_id}/file-preview-html": ["get"],
        "/api/editor/{wf_id}/compile": ["post"],
        "/api/editor/{wf_id}/docx": ["get"],
        "/api/editor/{wf_id}/docx-status": ["get"],
        "/api/editor/{wf_id}/pdf": ["get"],
        "/api/editor/{wf_id}/stats": ["get"],
        "/api/editor/{wf_id}/mode": ["get"],
        "/api/editor/{wf_id}/model-options": ["get"],
    }
    check("13 条路径全部注册", set(expected) == set(paths),
          str(set(expected) ^ set(paths)))
    check("file 支持 GET/PUT/DELETE（15 个方法）",
          paths.get("/api/editor/{wf_id}/file") == ["delete", "get", "put"])

    c, td = new_client()
    r = c.get("/api/editor/deadbeef/files")
    check("未知工作流 -> 404 WORKFLOW_NOT_FOUND",
          r.status_code == 404 and err_code(r) == "WORKFLOW_NOT_FOUND", r.text[:160])
    check("未知工作流的错误体为 {detail:{message,code}}",
          isinstance(r.json().get("detail"), dict), r.text[:160])


def test_file_crud_roundtrip() -> None:
    print("\n[2] 文件 CRUD 往返")
    c, td = new_client()
    ws = td / "ws"
    ws.mkdir()
    wf = make_wf(c, ws)
    base = f"/api/editor/{wf}"

    r = c.get(f"{base}/files")
    check("GET files = 200 且工作区存在", r.status_code == 200 and r.json()["exists"] is True,
          r.text[:160])
    check("空工作区 count = 0", r.json()["count"] == 0)

    r = c.post(f"{base}/create-file", json={"path": "code/main.py", "content": "print(1)\n"})
    check("POST create-file = 201", r.status_code == 201, r.text[:160])
    sha1 = r.json()["sha256"]
    check("code/main.py 真的落盘", (ws / "code" / "main.py").read_text(encoding="utf-8") == "print(1)\n")

    r = c.get(f"{base}/files")
    names = {f["path"] for f in r.json()["files"]}
    check("文件树含 code/main.py 与 code 目录",
          {"code/main.py", "code"} <= names, str(sorted(names)))
    check("目录项 kind=dir", next(f for f in r.json()["files"] if f["path"] == "code")["kind"] == "dir")

    r = c.get(f"{base}/file", params={"path": "code/main.py"})
    body = r.json()
    check("GET file 内容一致", r.status_code == 200 and body["content"] == "print(1)\n",
          r.text[:160])
    check("GET file 回传 sha256（供乐观锁使用）", body["sha256"] == sha1)
    check("文本文件 binary=False", body["binary"] is False)

    r = c.put(f"{base}/file", json={"path": "code/main.py", "content": "print(2)\n",
                                    "expected_sha256": sha1})
    check("PUT file（sha256 匹配）= 200", r.status_code == 200, r.text[:160])
    sha2 = r.json()["sha256"]
    check("内容被更新", (ws / "code" / "main.py").read_text(encoding="utf-8") == "print(2)\n")

    r = c.put(f"{base}/file", json={"path": "code/main.py", "content": "stale\n",
                                    "expected_sha256": sha1})
    check("PUT file（sha256 过期）-> 409 FILE_CONFLICT",
          r.status_code == 409 and err_code(r) == "FILE_CONFLICT", r.text[:160])
    check("冲突时**未**覆盖磁盘内容",
          (ws / "code" / "main.py").read_text(encoding="utf-8") == "print(2)\n")

    r = c.put(f"{base}/file", json={"path": "code/main.py", "content": "x",
                                    "expected_sha256": sha2})
    check("用最新 sha256 再次保存 = 200", r.status_code == 200, r.text[:160])

    r = c.post(f"{base}/create-file", json={"path": "code/main.py", "content": "y"})
    check("重复创建 -> 409 FILE_EXISTS",
          r.status_code == 409 and err_code(r) == "FILE_EXISTS", r.text[:160])

    r = c.get(f"{base}/file", params={"path": "code/nope.py"})
    check("读不存在的文件 -> 404（不是 500）",
          r.status_code == 404 and err_code(r) == "FILE_NOT_FOUND", r.text[:160])

    r = c.get(f"{base}/file", params={"path": "code"})
    check("读目录 -> 400 PATH_IS_DIRECTORY", r.status_code == 400, r.text[:160])

    # 二进制文件不进 JSON
    (ws / "paper").mkdir()
    (ws / "paper" / "main.docx").write_bytes(b"PK\x03\x04\x00\x00binary")
    r = c.get(f"{base}/file", params={"path": "paper/main.docx"})
    check("二进制文件 binary=True 且 content=null",
          r.status_code == 200 and r.json()["binary"] is True and r.json()["content"] is None,
          r.text[:160])

    # 隐藏文件默认不列
    (ws / ".env").write_text("SECRET=1", encoding="utf-8")
    r = c.get(f"{base}/files")
    check("默认不列隐藏文件", all(not f["path"].startswith(".") for f in r.json()["files"]))
    r = c.get(f"{base}/files", params={"show_hidden": True})
    check("show_hidden=true 才列隐藏文件",
          any(f["path"] == ".env" for f in r.json()["files"]))

    r = c.delete(f"{base}/file", params={"path": "code/main.py"})
    check("DELETE file = 200", r.status_code == 200, r.text[:160])
    check("删除后磁盘上确实没了", not (ws / "code" / "main.py").exists())
    r = c.get(f"{base}/file", params={"path": "code/main.py"})
    check("删除后读 -> 404", r.status_code == 404)

    r = c.delete(f"{base}/file", params={"path": "code"})
    check("删空目录 = 200", r.status_code == 200 and r.json()["kind"] == "dir", r.text[:160])

    (ws / "code").mkdir()
    (ws / "code" / "a.py").write_text("x", encoding="utf-8")
    r = c.delete(f"{base}/file", params={"path": "code"})
    check("删非空目录 -> 409 DIRECTORY_NOT_EMPTY",
          r.status_code == 409 and err_code(r) == "DIRECTORY_NOT_EMPTY", r.text[:160])

    r = c.delete(f"{base}/file", params={"path": ""})
    check("删工作区根 -> 403 CANNOT_DELETE_ROOT",
          r.status_code == 403 and err_code(r) == "CANNOT_DELETE_ROOT", r.text[:160])
    check("工作区根仍在", ws.is_dir())


def test_path_traversal_rejected() -> None:
    print("\n[3] ★ 路径穿越必须被拒")
    c, td = new_client()
    ws = td / "ws"
    ws.mkdir()
    wf = make_wf(c, ws)
    base = f"/api/editor/{wf}"

    # 工作区**外**放一个机密文件与一个目标目录
    outside = td / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text(OUTSIDE_SECRET, encoding="utf-8")
    outside_evil = td / "evil.txt"

    # --- GET /file ---
    leaked = []
    for raw in TRAVERSAL_CASES:
        r = c.get(f"{base}/file", params={"path": raw})
        ok_status = r.status_code in (400, 403)
        if not ok_status or OUTSIDE_SECRET in r.text:
            leaked.append((raw, r.status_code, r.text[:80]))
    check("GET /file：19 个穿越反例全部 400/403 且无内容泄漏",
          not leaked, str(leaked))

    r = c.get(f"{base}/file", params={"path": "../../outside/secret.txt"})
    check("精确校验 ../../outside/secret.txt -> 403",
          r.status_code == 403 and err_code(r) == "PATH_OUTSIDE_WORKSPACE", r.text[:160])

    # --- GET /download ---
    bad = [raw for raw in TRAVERSAL_CASES
           if c.get(f"{base}/download", params={"path": raw}).status_code not in (400, 403)]
    check("GET /download：穿越反例全部 400/403", not bad, str(bad))

    # --- GET /file-preview-html（返回 text/html，泄漏即 XSS/信息泄露）---
    r = c.get(f"{base}/file-preview-html", params={"path": "../../outside/secret.txt"})
    check("GET /file-preview-html：穿越被拒且不泄漏",
          r.status_code in (400, 403) and OUTSIDE_SECRET not in r.text, r.text[:160])

    # --- GET /stats ---
    bad = [raw for raw in TRAVERSAL_CASES
           if c.get(f"{base}/stats", params={"path": raw}).status_code not in (400, 403)]
    check("GET /stats：穿越反例全部 400/403", not bad, str(bad))

    # --- PUT /file ---
    bad = []
    for raw in TRAVERSAL_CASES:
        r = c.put(f"{base}/file", json={"path": raw, "content": "pwned"})
        if r.status_code not in (400, 403):
            bad.append((raw, r.status_code))
    check("PUT /file：穿越反例全部 400/403", not bad, str(bad))
    check("穿越写**没有**在磁盘上产生文件", not outside_evil.exists())

    # --- POST /create-file ---
    r = c.post(f"{base}/create-file", json={"path": "../../evil.txt", "content": "pwned"})
    check("POST /create-file 穿越 -> 403",
          r.status_code == 403 and err_code(r) == "PATH_OUTSIDE_WORKSPACE", r.text[:160])
    check("穿越建文件**没有**落盘", not outside_evil.exists())

    # --- POST /upload（目标路径与上传文件名都是用户可控）---
    r = c.post(f"{base}/upload", params={"path": "../../evil2.txt"},
               files={"file": ("evil2.txt", b"pwned", "text/plain")})
    check("POST /upload 穿越目标路径 -> 403", r.status_code == 403, r.text[:160])
    check("上传穿越**没有**落盘", not (td / "evil2.txt").exists())

    r = c.post(f"{base}/upload",
               files={"file": ("../../../evil3.txt", b"pwned", "text/plain")})
    check("POST /upload 穿越**文件名** -> 403", r.status_code == 403, r.text[:160])
    check("按文件名穿越**没有**落盘", not (td.parent / "evil3.txt").exists())

    # --- DELETE /file ---
    r = c.delete(f"{base}/file", params={"path": "../../outside"})
    check("DELETE /file 穿越 -> 403", r.status_code == 403, r.text[:160])
    check("工作区外目录仍在", outside.is_dir() and secret.is_file())

    # --- 效果层：机密内容从未出现在任何响应里 ---
    probes = [
        ("get", f"{base}/file", {"params": {"path": "../outside/secret.txt"}}),
        ("get", f"{base}/download", {"params": {"path": "../outside/secret.txt"}}),
        ("get", f"{base}/file-preview-html", {"params": {"path": "../outside/secret.txt"}}),
        ("get", f"{base}/stats", {"params": {"path": "../outside/secret.txt"}}),
    ]
    leaked2 = [url for method, url, kw in probes
               if OUTSIDE_SECRET in getattr(c, method)(url, **kw).text]
    check("机密文件内容在任何探测响应中都不出现", not leaked2, str(leaked2))

    # --- 正常的相对路径仍然可用（不要为了安全把功能一起关掉）---
    r = c.post(f"{base}/create-file", json={"path": "paper/sections/s1.md", "content": "正文"})
    check("正常嵌套相对路径仍可写（未误杀）", r.status_code == 201, r.text[:160])


def make_escape_link(link: Path, target: Path) -> str:
    """建一个指向工作区外的目录链接；返回方式名，失败返回空串。

    先试 `os.symlink`（Windows 上需要开发者模式/管理员），失败退回
    **目录联接 junction**——`cmd /c mklink /J` 不需要任何特权，
    也是本机能跑通的那条路（实测 3.11 的 `is_symlink()` 对 junction 返回 False，
    所以这条用例同时覆盖了"重解析点识别"这个坑）。
    """
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
        return "symlink"
    except (OSError, NotImplementedError, AttributeError):
        pass
    import subprocess
    try:
        proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                              capture_output=True, timeout=20)
        if proc.returncode == 0 and link.exists():
            return "junction"
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


def test_symlink_escape_rejected() -> None:
    print("\n[4] ★ 符号链接 / 目录联接逃逸")
    c, td = new_client()
    ws = td / "ws"
    ws.mkdir()
    wf = make_wf(c, ws)
    base = f"/api/editor/{wf}"

    outside = td / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text(OUTSIDE_SECRET, encoding="utf-8")

    how = make_escape_link(ws / "link", outside)
    if not how:
        check("链接逃逸用例（跳过：本机既不能 symlink 也不能 mklink /J）", True,
              "skip: no link capability")
        return
    print("      （用 %s 构造逃逸链接）" % how)

    r = c.get(f"{base}/file", params={"path": "link/secret.txt"})
    check("经链接读工作区外文件 -> 403",
          r.status_code == 403 and err_code(r) == "PATH_OUTSIDE_WORKSPACE", r.text[:160])
    check("链接读取未泄漏内容", OUTSIDE_SECRET not in r.text)

    r = c.post(f"{base}/create-file", json={"path": "link/pwned.txt", "content": "x"})
    check("经链接写工作区外 -> 403", r.status_code == 403, r.text[:160])
    check("链接写未落盘", not (outside / "pwned.txt").exists())

    r = c.get(f"{base}/download", params={"path": "link/secret.txt"})
    check("经链接下载 -> 403", r.status_code == 403, r.text[:160])

    # ★ 文件树**不得递归**进链接：否则"文件树"就是对外部目录的枚举。
    r = c.get(f"{base}/files")
    files = r.json()["files"]
    entry = next((f for f in files if f["path"] == "link"), None)
    check("文件树把链接标为 symlink 且 escapes=true",
          entry is not None and entry["kind"] == "symlink" and entry["escapes"] is True,
          str(entry))
    check("★ 文件树不递归进链接（不含 link/ 下的任何路径）",
          all(not f["path"].startswith("link/") for f in files),
          str([f["path"] for f in files])[:200])
    check("外部目录的文件名未出现在文件树中",
          "secret.txt" not in json.dumps(files, ensure_ascii=False))


def test_upload_download_preview() -> None:
    print("\n[5] 上传 / 下载 / HTML 预览")
    c, td = new_client()
    ws = td / "ws"
    ws.mkdir()
    wf = make_wf(c, ws)
    base = f"/api/editor/{wf}"

    r = c.post(f"{base}/upload", params={"path": "data/in.csv"},
               files={"file": ("in.csv", b"x,y\n1,2\n", "text/csv")})
    check("POST upload = 201", r.status_code == 201, r.text[:160])
    check("上传内容落盘", (ws / "data" / "in.csv").read_bytes() == b"x,y\n1,2\n")
    check("上传回传 sha256 与字节数",
          len(r.json()["sha256"]) == 64 and r.json()["bytes"] == 8)

    r = c.post(f"{base}/upload", files={"file": ("auto.txt", b"auto-name", "text/plain")})
    check("省略 path 时用上传文件名", r.status_code == 201 and (ws / "auto.txt").is_file(),
          r.text[:160])

    r = c.get(f"{base}/download", params={"path": "data/in.csv"})
    check("GET download = 200 且内容一致",
          r.status_code == 200 and r.content == b"x,y\n1,2\n", r.text[:120])
    check("download 带 Content-Disposition",
          "in.csv" in r.headers.get("content-disposition", ""))

    r = c.get(f"{base}/download", params={"path": "nope.csv"})
    check("下载不存在 -> 404（不是 500）", r.status_code == 404, r.text[:160])

    # 体积闸：不设上限时一次请求就能把进程打死
    big = b"A" * (ed.MAX_WRITE_BYTES + 10)
    r = c.post(f"{base}/upload", params={"path": "big.bin"},
               files={"file": ("big.bin", big, "application/octet-stream")})
    check("★ 超过写入上限的上传 -> 413", r.status_code == 413, r.text[:120])
    check("被拒的上传未落盘", not (ws / "big.bin").exists())

    r = c.put(f"{base}/file", json={"path": "big2.txt", "content": "A" * 200})
    check("正常体积写入不误拒", r.status_code == 200, r.text[:120])

    # 大文本读取必须有界：否则 read_file / 预览就是 OOM 入口
    (ws / "huge.txt").write_text("B" * (ed.MAX_TEXT_BYTES + 4096), encoding="utf-8")
    r = c.get(f"{base}/file", params={"path": "huge.txt"})
    body = r.json()
    check("★ 大文件读取被截断且标记 truncated",
          r.status_code == 200 and body["truncated"] is True
          and len(body["content"]) <= ed.MAX_TEXT_BYTES, str(body)[:160])
    check("截断时 sha256 仍按**整文件**计算（CAS 才可信）",
          body["sha256"] == hashlib.sha256(
              ("B" * (ed.MAX_TEXT_BYTES + 4096)).encode()).hexdigest(), body["sha256"][:16])

    (ws / "evil.html").write_text("<script>alert(1)</script><b>x</b>", encoding="utf-8")
    r = c.get(f"{base}/file-preview-html", params={"path": "evil.html"})
    check("file-preview-html = 200", r.status_code == 200, r.text[:120])
    check("★ HTML 预览转义脚本（防工作区文件变成 XSS 载荷）",
          "<script>alert(1)</script>" not in r.text and "&lt;script&gt;" in r.text,
          r.text[:200])

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    (ws / "fig.png").write_bytes(png)
    r = c.get(f"{base}/file-preview-html", params={"path": "fig.png"})
    check("图片预览走 <img> 指向 download",
          r.status_code == 200 and "<img" in r.text and "download?path=fig.png" in r.text,
          r.text[:200])

    r = c.get(f"{base}/file-preview-html", params={"path": "missing.md"})
    check("预览不存在文件 -> 404（HTML 体，不抛异常）", r.status_code == 404)


def test_compile_artifacts() -> None:
    print("\n[6] 编译产物：compile / docx / docx-status / pdf / stats")
    c, td = new_client()
    ws = td / "ws"
    (ws / "paper" / "sections").mkdir(parents=True)
    (ws / "paper" / "sections" / "01.md").write_text(
        "# 问题重述\n" + "本节是正文内容。" * 400, encoding="utf-8")
    wf = make_wf(c, ws)
    base = f"/api/editor/{wf}"

    original = tx.resolve_tex_runtime
    tx.resolve_tex_runtime = miss_tex_runtime()
    try:
        r = c.post(f"{base}/compile", json={})
        body = r.json()
        check("POST compile = 200（编译失败不是 HTTP 错误）", r.status_code == 200, r.text[:200])
        check("mode = latex", body["mode"] == "latex", str(body.get("mode")))
        check("回传 current_file 指向 main.tex",
              str(body["current_file"]).replace("\\", "/").endswith("paper/main.tex"),
              str(body.get("current_file")))
        check("回传 compile_log（TeX 不可用时说明原因）",
              "TeX 运行时不可用" in body["compile_log"], body["compile_log"][:160])
        check("TeX 不可用时 ok = false（不伪装成功）", body["ok"] is False)
        check("★ .tex 仍然落盘（与 PDF 是否编出无关）", (ws / "paper" / "main.tex").is_file())

        # source_md 非空 → 先写入 paper/main.md
        r = c.post(f"{base}/compile", json={"source_md": "# 标题\n正文正文正文"})
        check("传 source_md 会先落盘 paper/main.md",
              r.status_code == 200 and (ws / "paper" / "main.md").read_text(
                  encoding="utf-8").startswith("# 标题"), r.text[:160])

        r = c.get(f"{base}/stats")
        st = r.json()
        check("GET stats = 200", r.status_code == 200, r.text[:200])
        check("stats 报出正文字符数 > 0", st["body_chars"] > 0, str(st))
        check("stats 含页数估算与上限（advisory）",
              st["estimated_pages"] >= 0 and st["page_limit"] == 30, str(st))

        r = c.get(f"{base}/stats", params={"path": "paper/main.tex"})
        check("stats?path= 返回单文件统计",
              r.status_code == 200 and r.json()["scope"] == "file"
              and r.json()["body_chars"] > 0, r.text[:160])

        r = c.get(f"{base}/stats", params={"path": "../../etc/passwd"})
        check("stats?path= 穿越 -> 403", r.status_code == 403, r.text[:160])

        r = c.get(f"{base}/docx")
        check("无 Word 产物 -> 404 DOCX_NOT_FOUND",
              r.status_code == 404 and err_code(r) == "DOCX_NOT_FOUND", r.text[:160])

        r = c.get(f"{base}/docx-status")
        check("docx-status 无产物时 available=false",
              r.status_code == 200 and r.json()["available"] is False, r.text[:160])

        r = c.get(f"{base}/pdf")
        check("无 PDF -> 404 PDF_NOT_FOUND", r.status_code == 404, r.text[:160])

        # 造一个 Word 产物（比所有正文都新）
        docx = ws / "paper" / "main.docx"
        docx.write_bytes(b"PK\x03\x04fake-docx")
        os.utime(docx, (2_000_000_000, 2_000_000_000))
        r = c.get(f"{base}/docx")
        check("有产物时 GET docx = 200", r.status_code == 200, r.text[:160])
        check("Word MIME 正确",
              "wordprocessingml" in r.headers.get("content-type", ""), r.headers.get("content-type"))

        r = c.get(f"{base}/docx-status")
        check("docx-status available=true / fresh=true",
              r.json()["available"] is True and r.json()["fresh"] is True, r.text[:200])

        # 正文比产物新 → 过期
        section = ws / "paper" / "sections" / "01.md"
        os.utime(section, (2_100_000_000, 2_100_000_000))
        r = c.get(f"{base}/docx-status")
        check("★ 新鲜度与可用性分开：正文更新后 fresh=false",
              r.json()["available"] is True and r.json()["fresh"] is False, r.text[:200])
        r = c.get(f"{base}/docx", params={"allow_stale": False})
        check("allow_stale=false 且过期 -> 409 ARTIFACT_STALE",
              r.status_code == 409 and err_code(r) == "ARTIFACT_STALE", r.text[:160])

        r = c.get(f"{base}/docx", params={"expected_sha256": "0" * 64})
        check("docx expected_sha256 不符 -> 409 FILE_CONFLICT",
              r.status_code == 409 and err_code(r) == "FILE_CONFLICT", r.text[:160])

        # 空工作区的编译：不崩、如实报失败
        wf2 = make_wf(c, td / "empty")
        r = c.post(f"/api/editor/{wf2}/compile", json={})
        check("空工作区 compile = 200 且 ok=false（不抛 500）",
              r.status_code == 200 and r.json()["ok"] is False, r.text[:200])
    finally:
        tx.resolve_tex_runtime = original


def test_mode_and_model_options() -> None:
    print("\n[7] mode / model-options")
    c, td = new_client()
    ws = td / "ws"
    ws.mkdir()
    wf = make_wf(c, ws)
    base = f"/api/editor/{wf}"

    r = c.get(f"{base}/mode")
    body = r.json()
    check("GET mode = 200", r.status_code == 200, r.text[:160])
    check("默认 mode = latex", body["mode"] == "latex", str(body))
    check("默认文件 = paper/main.tex", body["default_file"] == "paper/main.tex", str(body))
    check("含 supported_modes（前端据此渲染切换）",
          body["supported_modes"] == ["latex", "markdown"], str(body))

    wf_md = make_wf(c, ws, params={"docx_mode": True})
    r = c.get(f"/api/editor/{wf_md}/mode")
    check("params.docx_mode=true -> mode=markdown 且默认文件 main.md",
          r.json()["mode"] == "markdown" and r.json()["default_file"] == "paper/main.md",
          str(r.json()))

    wf_explicit = make_wf(c, ws, params={"editor_mode": "markdown"})
    r = c.get(f"/api/editor/{wf_explicit}/mode")
    check("params.editor_mode 优先", r.json()["mode"] == "markdown", str(r.json()))

    c.post("/api/settings/presets", json={
        "name": "编辑器模型", "model_id": "claude-opus-4-8",
        "api_key": "sk-secret", "context_mode": "200k"})

    r = c.get(f"{base}/model-options")
    body = r.json()
    check("GET model-options = 200", r.status_code == 200, r.text[:160])
    check("列出预设", body["count"] == 1 and body["presets"][0]["model_id"] == "claude-opus-4-8",
          str(body))
    check("★ 绝不回传 api_key 字段与密钥值",
          all("api_key" not in p for p in body["presets"])
          and "sk-secret" not in json.dumps(body, ensure_ascii=False),
          json.dumps(body, ensure_ascii=False)[:200])
    check("只回传 has_api_key", body["presets"][0]["has_api_key"] is True)


def test_default_workspace_dir() -> None:
    print("\n[8] workspace_dir 为空时的默认工作区")
    c, td = new_client()
    root = td / "wsroot"
    old = os.environ.get("MODEMON_WORKSPACES_DIR")
    os.environ["MODEMON_WORKSPACES_DIR"] = str(root)
    try:
        wf = c.post("/api/workflows", json={"template": "comp_mcm", "title": "t"}).json()["id"]
        r = c.get(f"/api/editor/{wf}/files")
        body = r.json()
        check("GET files = 200", r.status_code == 200, r.text[:160])
        check("默认根 = <root>/<wf_id>",
              Path(body["root"]) == (root / wf).resolve(), str(body["root"]))
        check("目录尚不存在时 exists=false（不报错）", body["exists"] is False)

        r = c.post(f"/api/editor/{wf}/create-file", json={"path": "a.txt", "content": "hi"})
        check("按需创建工作区并写入 = 201", r.status_code == 201, r.text[:160])
        check("文件真的落在默认根下", (root / wf / "a.txt").read_text(encoding="utf-8") == "hi")

        r = c.get(f"/api/editor/{wf}/files")
        check("复读文件树可见", [f["path"] for f in r.json()["files"]] == ["a.txt"], r.text[:160])
    finally:
        if old is None:
            os.environ.pop("MODEMON_WORKSPACES_DIR", None)
        else:
            os.environ["MODEMON_WORKSPACES_DIR"] = old


def test_guard_unit() -> None:
    """守卫的单元级断言：与 HTTP 层重复，但能定位失败到具体判据。"""
    print("\n[9] resolve_inside 单元判据")
    root = Path(tempfile.mkdtemp(prefix="modemon-guard-")).resolve()
    root.mkdir(exist_ok=True)
    nested = root / "a" / "b"
    nested.mkdir(parents=True)

    check("空路径 -> 根", ed.resolve_inside(root, "") == root)
    check("'.' -> 根", ed.resolve_inside(root, ".") == root)
    check("正常嵌套路径", ed.resolve_inside(root, "a/b/c.txt") == (nested / "c.txt"))
    check("反斜杠同样解析", ed.resolve_inside(root, "a\\b\\c.txt") == (nested / "c.txt"))

    rejected = 0
    for raw in TRAVERSAL_CASES:
        try:
            ed.resolve_inside(root, raw)
        except Exception:  # noqa: BLE001 —— HTTPException(400/403) 都算拒绝
            rejected += 1
    check("19 个反例全部被 resolve_inside 拒绝", rejected == len(TRAVERSAL_CASES),
          f"{rejected}/{len(TRAVERSAL_CASES)}")

    ok_cases = ["paper/main.tex", "figures/all_results.json", "code/main.py",
                "data/x y.csv", "中文章节.md", "a/b/c/d/e.txt"]
    bad = []
    for raw in ok_cases:
        try:
            ed.resolve_inside(root, raw)
        except Exception as exc:  # noqa: BLE001
            bad.append((raw, repr(exc)))
    check("正常路径无一被误杀", not bad, str(bad))

    check("is_within 正向", ed.is_within(root, nested) is True)
    check("is_within 反向", ed.is_within(root, root.parent) is False)


def main() -> int:
    print("=" * 74)
    print("modemon /api/editor/* 域端点测试（真跑 HTTP 栈 + 路径穿越对抗）")
    print("=" * 74)
    test_routes_registered()
    test_file_crud_roundtrip()
    test_path_traversal_rejected()
    test_symlink_escape_rejected()
    test_upload_download_preview()
    test_compile_artifacts()
    test_mode_and_model_options()
    test_default_workspace_dir()
    test_guard_unit()
    print("\n" + "=" * 74)
    print("PASS %d / FAIL %d" % (PASS, FAIL))
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print("  -", f)
    print("=" * 74)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
