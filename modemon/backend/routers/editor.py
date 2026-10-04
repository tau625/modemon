"""编辑器域路由：`/api/editor/{wf_id}/*`。

职责
----
手写编辑器（对应蓝方 `/workflow/:id/editor` 页面）的后端支撑面。本轮只落地
**文件读写 + 编译产物 + 编辑器元信息**三组能力，共 15 条路由：

  文件（8）  files / file(GET/PUT/DELETE) / create-file / upload / download /
             file-preview-html
  产物（5）  compile / docx / docx-status / pdf / stats
  元信息（2） mode / model-options

**未实现**的端点及理由见 `reports/` 中的流 F 报告；此处不硬凑数量。

头号风险：路径穿越
------------------
文件类接口的安全性**完全**取决于 `resolve_inside()`。所有用户可控路径都必须
经过它，任何一条绕过都等于把整个磁盘交出去。它针对四种真实手法：

  1. **绝对路径**：`/etc/passwd`、`C:\\Windows\\win.ini`、`\\\\host\\share`。
     ⚠️ 这不是"理论上会被前缀校验挡住"——`Path('C:/ws') / '/etc/passwd'`
     在 Windows 上求值为 `C:/etc/passwd`，**root 被整段丢掉**。必须前置拒绝。
  2. **`..` 组件**：编辑器没有合法用场景，出现即拒（不做"解析后仍在内则放行"）。
  3. **符号链接 / 目录联接逃逸**：`<root>/link -> C:\\Windows` 时 `link/win.ini`
     词法上在工作区内。靠 `resolve()` 展开真实路径 + 前缀校验兜底。
     ⚠️ Windows 上 `mklink /J` 建的 **junction 不需要管理员权限**，
     且 Python 3.11 的 `is_symlink()` 对它是 `False`——两处都要单独处理。
  4. **Windows 保留设备名 / 尾随点空格**（`CON`、`aux.txt`、`a. `）——
     会被内核按裸设备或截断名解释，绕过目录语义。

另有 `\\x00` 与控制字符、以及单次读写体积上限两道闸。

工作区根从哪来
--------------
**不由调用方指定**。`workflows.workspace_dir` 为空时回退到
`<backend>/workspaces/<wf_id>`（可用 `MODEMON_WORKSPACES_DIR` 覆盖根目录）。
刻意不提供 `?workspace=` 参数：那等于把安全边界交给 HTTP 调用方，
与 `workspace_guard.py` 的纵深防御思路相悖。
"""

from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import os
import re
import sqlite3
import stat
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from services import docx_export as dx
from services import latex_export as lx
from services import typography as ty
from services import workflow_engine as we

log = logging.getLogger("modemon.editor")

router = APIRouter(prefix="/api/editor/{wf_id}", tags=["editor"])

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACES_ROOT = BACKEND_ROOT / "workspaces"

#: 单文件读/写上限。编辑器是文本编辑器，不是文件传输器；
#: 不设上限时一个 500 MB 的二进制就能把进程打死。
MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_WRITE_BYTES = 8 * 1024 * 1024

#: 文件树一次最多返回多少条（防御工作区内海量文件）。
MAX_LIST_ENTRIES = 5000

#: 文件树里跳过的噪音目录（与 workspace_guard.SKIP_DIRS 同一口径）。
SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".venv", "venv"}

#: 本引擎在 latex_export / docx_export 里约定的论文产物位置。
PAPER_TEX = "paper/main.tex"
PAPER_MD = "paper/main.md"
PAPER_DOCX = "paper/main.docx"
PAPER_PDF = "paper/main.pdf"

#: 判定"产物是否过期"时纳入比较的正文来源。
FRESHNESS_SOURCES = ("paper/sections", PAPER_MD, PAPER_TEX)

_WIN_DRIVE = re.compile(r"^[A-Za-z]:")
_WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


# ---------------------------------------------------------------------------
# 依赖：数据库 / 工作流上下文
# ---------------------------------------------------------------------------


def db_dep() -> Generator[sqlite3.Connection, None, None]:
    """复用 main 的连接工厂。

    `routers/` 由 `main` 在导入期装载，模块顶层 import main 会成环，
    故与 `routers/ws.py` 保持同一手法：函数内延迟导入。
    """
    import main as app_module  # noqa: PLC0415

    con = app_module.get_db()
    try:
        yield con
    finally:
        con.close()


def fail(status: int, code: str, message: str) -> HTTPException:
    """结构化错误。

    `main._http_error_handler` 对 dict 形态的 detail 原样透传，前端因此拿到
    与全站一致的 `{detail: {message, code}}`；非 dict 才降级为 `{detail: str}`。
    """
    return HTTPException(status_code=status, detail={"message": message, "code": code})


@dataclass(frozen=True)
class EditorCtx:
    """一次编辑器请求的全部服务端上下文。"""

    wf_id: str
    template: str
    params: dict[str, Any] = field(default_factory=dict)
    root: Path = Path(".")

    @property
    def language(self) -> str:
        try:
            return we.resolve_template(self.template).lang or "zh"
        except Exception:  # noqa: BLE001 —— 语言解析失败不该让整个请求 500
            return "zh"

    @property
    def mode(self) -> str:
        for key in ("editor_mode", "mode"):
            value = str(self.params.get(key, "")).strip().lower()
            if value in ("latex", "markdown"):
                return value
        return "markdown" if self.params.get("docx_mode") else "latex"


def workspaces_root() -> Path:
    """工作区根目录（部署期可覆盖）。"""
    raw = (os.environ.get("MODEMON_WORKSPACES_DIR") or "").strip()
    return Path(raw) if raw else DEFAULT_WORKSPACES_ROOT


def editor_ctx(
    wf_id: str, con: sqlite3.Connection = Depends(db_dep)
) -> EditorCtx:
    """解析工作流 → 工作区根。

    根**只**来自服务端（库里 `workspace_dir`，或按 wf_id 派生的默认目录），
    调用方无法通过 HTTP 指定。`resolve()` 后即固定，后续所有路径都相对它校验。
    """
    row = con.execute(
        "SELECT id, template, params, workspace_dir FROM workflows WHERE id=?", (wf_id,)
    ).fetchone()
    if row is None:
        raise fail(404, "WORKFLOW_NOT_FOUND", f"工作流不存在: {wf_id}")

    raw_dir = (row["workspace_dir"] or "").strip()
    root = Path(raw_dir) if raw_dir else (workspaces_root() / wf_id)
    try:
        root = root.expanduser().resolve()
    except OSError as exc:  # 极端情况下 resolve 也可能失败（无权限/损坏路径）
        raise fail(400, "WORKSPACE_INVALID", f"工作区路径不可解析: {raw_dir!r} ({exc})") from None

    try:
        params = json.loads(row["params"] or "{}")
    except (ValueError, TypeError):
        params = {}
    if not isinstance(params, dict):
        params = {}

    return EditorCtx(wf_id=wf_id, template=row["template"], params=params, root=root)


# ---------------------------------------------------------------------------
# ★ 路径守卫（本模块的安全核心）
# ---------------------------------------------------------------------------


def is_within(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


#: Windows 重解析点属性（符号链接、目录联接 junction 都是）。
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def is_reparse_point(entry: os.DirEntry) -> bool:
    """目录联接（junction）与符号链接一样，都是指向别处的重解析点。

    ⚠️ **实测踩坑**：Python 3.11 的 `DirEntry.is_symlink()` 对 junction
    返回 `False`（`Path.is_junction()` 要到 3.12 才有）。只判 `is_symlink()`
    的话，`ws/link -> C:\\` 会被当成普通目录**递归进去**，于是"文件树"
    变成整棵系统盘的越界读取。

    `cmd /c mklink /J` 建联接**不需要管理员权限**，所以这不是理论风险。
    """
    try:
        st = entry.stat(follow_symlinks=False)
    except OSError:
        return False
    return bool(getattr(st, "st_file_attributes", 0) & _REPARSE_POINT)


def resolve_inside(root: Path, rel: Optional[str]) -> Path:
    """把调用方给的相对路径解析到 `root` 内；任何越界都抛 403/400。

    见模块 docstring「头号风险」一节：四类绕过各自有独立闸门，
    最后再用 `resolve()` 后的前缀校验兜底。**宁可多拒，不可漏放。**
    """
    raw = "" if rel is None else str(rel)
    if "\x00" in raw:
        raise fail(400, "PATH_INVALID", "路径含 NUL 字节")
    for ch in raw:
        if ord(ch) < 32:
            raise fail(400, "PATH_INVALID", f"路径含控制字符: {raw!r}")

    text = raw.strip()
    if text in ("", ".", "./", ".\\"):
        return root

    # 反斜杠同等对待：Windows 客户端会把 `..\\..\\` 原样送进来。
    norm = text.replace("\\", "/")
    if norm.startswith("/") or norm.startswith("//") or _WIN_DRIVE.match(text):
        raise fail(403, "PATH_OUTSIDE_WORKSPACE", f"拒绝绝对路径 / UNC 路径: {raw!r}")

    parts = [p for p in norm.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise fail(403, "PATH_OUTSIDE_WORKSPACE", f"拒绝上级目录引用: {raw!r}")
    for part in parts:
        if part.endswith(" ") or part.endswith("."):
            raise fail(400, "PATH_INVALID", f"非法文件名（尾随点/空格会被内核截断）: {part!r}")
        if part.split(".")[0].upper() in _WIN_RESERVED:
            raise fail(400, "PATH_INVALID", f"Windows 保留设备名: {part!r}")

    candidate = (root / Path(*parts)).resolve()
    if candidate != root and not is_within(root, candidate):
        # 词法上在内、`resolve()` 后在外 —— 只可能是符号链接逃逸。
        raise fail(403, "PATH_OUTSIDE_WORKSPACE", f"路径越界（疑似符号链接逃逸）: {raw!r}")
    return candidate


def _rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:  # pragma: no cover —— resolve_inside 已保证在内
        return path.name


def _sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


#: 流式读块大小（哈希大文件时用）。
_READ_CHUNK = 256 * 1024


def _sha256_file(path: Path) -> str:
    """流式哈希。

    不读整文件进内存：工作区里躺着的是**用户/agent 写的任意内容**，
    可能包含几百 MB 的 data/*.csv。`read_bytes()` 之后再算哈希会把
    "预览一个文件"变成一次 OOM。
    """
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_READ_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_head(path: Path, limit: int) -> tuple[bytes, int]:
    """只读前 `limit` 字节，返回 (内容, 文件总字节数)。内存占用 O(limit)。"""
    with path.open("rb") as fh:
        head = fh.read(limit)
    return head, path.stat().st_size


def _write_file(target: Path, payload: bytes) -> None:
    """落盘。

    非法路径（超长、含内核不接受的字符、父级是文件）在 Windows 上表现为
    `OSError`，那是**调用方的输入问题**（400），不是服务端故障（500）。
    """
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    except OSError as exc:
        raise fail(400, "PATH_INVALID", f"无法写入 {target.name!r}: {exc}") from None


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def _stat_of(path: Path) -> dict[str, Any]:
    st = path.stat()
    return {"bytes": st.st_size, "mtime": _iso(st.st_mtime)}


def _latest_mtime(paths: list[Path]) -> Optional[float]:
    newest: Optional[float] = None
    for p in paths:
        try:
            if p.is_file():
                m = p.stat().st_mtime
            elif p.is_dir():
                m = max((f.stat().st_mtime for f in p.rglob("*") if f.is_file()),
                        default=p.stat().st_mtime)
            else:
                continue
        except OSError:
            continue
        newest = m if newest is None else max(newest, m)
    return newest


# ---------------------------------------------------------------------------
# 请求体
# ---------------------------------------------------------------------------


class CreateFileBody(BaseModel):
    path: str
    content: str = ""


class SaveFileBody(BaseModel):
    path: str
    content: str
    expected_sha256: Optional[str] = None


class CompileBody(BaseModel):
    source_md: str = ""


# ---------------------------------------------------------------------------
# 一、文件操作（8）
# ---------------------------------------------------------------------------


@router.get("/files")
def list_files(
    ctx: EditorCtx = Depends(editor_ctx),
    show_hidden: bool = Query(False, description="是否列出点开头的文件"),
    view: str = Query("overview", description="overview | tree | flat（当前返回结构一致）"),
    collection: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=MAX_LIST_ENTRIES),
    query: Optional[str] = Query(None, description="按相对路径子串过滤"),
    snapshot: Optional[str] = Query(None),
    refresh: bool = Query(False),
) -> dict[str, Any]:
    """文件树。**调用最频繁**的编辑器端点。

    自己走 `os.scandir` 而不是 `rglob`：
      - `rglob` 会跟随目录符号链接（`scandir().is_dir()` 默认跟随），
        一旦工作区里有指向 `C:\\` 的链接，整棵系统树都会被列出来；
      - 这里 `follow_symlinks=False`，符号链接 / junction **只列举、不进入**。
    """
    root = ctx.root
    exists = root.is_dir()
    entries: list[dict[str, Any]] = []
    truncated = False

    if exists:
        stack: list[Path] = [root]
        needle = (query or "").strip().lower()
        while stack:
            current = stack.pop()
            try:
                children = sorted(os.scandir(current), key=lambda e: e.name)
            except OSError as exc:
                log.warning("editor: 目录不可读 %s (%s)", current, exc)
                continue
            for entry in children:
                name = entry.name
                if not show_hidden and name.startswith("."):
                    continue
                try:
                    is_link = entry.is_symlink() or is_reparse_point(entry)
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                # 普通目录才允许跳过噪音目录；链接一律不递归（见下）
                if is_dir and not is_link and name in SKIP_DIRS:
                    continue

                path = Path(entry.path)
                rel = _rel(root, path)
                if needle and needle not in rel.lower():
                    continue
                if len(entries) >= limit:
                    truncated = True
                    break

                item: dict[str, Any] = {
                    "path": rel,
                    "name": name,
                    "ext": path.suffix.lower(),
                }
                if is_link:
                    # 明确标注且**不递归**：工作区里的链接是逃逸载体，不是内容。
                    try:
                        target = os.readlink(entry.path)
                    except OSError:
                        target = ""
                    item.update({"kind": "symlink", "target": target,
                                 "escapes": not is_within(root, path.resolve())})
                elif is_dir:
                    item["kind"] = "dir"
                    stack.append(path)
                else:
                    item["kind"] = "file"
                    try:
                        item.update(_stat_of(path))
                    except OSError:
                        item["kind"] = "unreadable"
                entries.append(item)
            if truncated:
                break

    entries.sort(key=lambda e: (e["path"].count("/"), e["path"]))
    page = entries[offset:offset + limit]

    return {
        "workflow_id": ctx.wf_id,
        "root": str(root),
        "view": view,
        "collection": collection,
        "snapshot": snapshot,
        "refresh": refresh,
        "exists": exists,
        "files": page,
        "count": len(page),
        "total": len(entries),
        "truncated": truncated,
    }


@router.get("/file")
def read_file(
    ctx: EditorCtx = Depends(editor_ctx),
    path: str = Query(..., description="工作区内相对路径"),
) -> dict[str, Any]:
    """读单文件。

    二进制文件不塞进 JSON：返回 `binary: true` 且 `content` 为 null，
    由前端改走 `GET /download`。把 .docx 的 base64 塞进 JSON 正是蓝方
    专门做 `file-preview-html` 想绕开的问题（见报告 18 该端点的说明）。
    """
    target = resolve_inside(ctx.root, path)
    if not target.exists():
        raise fail(404, "FILE_NOT_FOUND", f"文件不存在: {path}")
    if target.is_dir():
        raise fail(400, "PATH_IS_DIRECTORY", f"该路径是目录: {path}")

    data, size = _read_head(target, MAX_TEXT_BYTES)
    sha = _sha256_file(target)
    truncated = size > MAX_TEXT_BYTES

    binary = b"\x00" in data[:8192]
    content: Optional[str] = None
    encoding = "utf-8"
    if not binary:
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content = data.decode("gbk")
                encoding = "gbk"
            except UnicodeDecodeError:
                binary, content = True, None

    info = _stat_of(target)
    return {
        "workflow_id": ctx.wf_id,
        "path": _rel(ctx.root, target),
        "content": content,
        "binary": binary,
        "encoding": encoding,
        "sha256": sha,
        "truncated": truncated,
        "bytes": info["bytes"],
        "mtime": info["mtime"],
    }


@router.put("/file")
def save_file(
    ctx: EditorCtx = Depends(editor_ctx),
    body: SaveFileBody = Body(...),
) -> dict[str, Any]:
    """保存文件（覆盖写）。父目录不存在则创建。

    `expected_sha256` 是**乐观锁**：带上它表示"我改的是这个版本"。
    与库中版本不符 → 409，而不是默默覆盖——编辑器场景下静默覆盖就是丢稿。
    """
    target = resolve_inside(ctx.root, body.path)
    if target == ctx.root or target.is_dir():
        raise fail(400, "PATH_IS_DIRECTORY", f"不能写入目录: {body.path}")

    payload = body.content.encode("utf-8")
    if len(payload) > MAX_WRITE_BYTES:
        raise fail(413, "FILE_TOO_LARGE",
                   f"内容超过 {MAX_WRITE_BYTES} 字节上限（{len(payload)}）")

    if body.expected_sha256:
        if not target.is_file():
            raise fail(409, "FILE_CONFLICT",
                       f"文件不存在，与 expected_sha256 不符: {body.path}")
        current = _sha256_file(target)
        if current != body.expected_sha256:
            raise fail(409, "FILE_CONFLICT",
                       f"文件已被其他写入修改（当前 {current[:12]}…）: {body.path}")

    _write_file(target, payload)
    return {"ok": True, "workflow_id": ctx.wf_id, "path": _rel(ctx.root, target),
            "sha256": _sha256_of(payload), "bytes": len(payload)}


@router.post("/create-file", status_code=201)
def create_file(
    ctx: EditorCtx = Depends(editor_ctx),
    body: CreateFileBody = Body(...),
) -> dict[str, Any]:
    """新建文件。已存在 → 409（改内容请走 PUT /file）。"""
    target = resolve_inside(ctx.root, body.path)
    if target == ctx.root or target.is_dir():
        raise fail(400, "PATH_IS_DIRECTORY", f"不能创建为目录: {body.path}")
    if target.exists():
        raise fail(409, "FILE_EXISTS", f"文件已存在: {body.path}")

    payload = body.content.encode("utf-8")
    if len(payload) > MAX_WRITE_BYTES:
        raise fail(413, "FILE_TOO_LARGE", f"内容超过 {MAX_WRITE_BYTES} 字节上限")

    _write_file(target, payload)
    return {"ok": True, "workflow_id": ctx.wf_id, "path": _rel(ctx.root, target),
            "sha256": _sha256_of(payload), "bytes": len(payload)}


@router.delete("/file")
def delete_file(
    ctx: EditorCtx = Depends(editor_ctx),
    path: str = Query(...),
) -> dict[str, Any]:
    """删除文件或**空**目录。工作区根自身不可删。"""
    target = resolve_inside(ctx.root, path)
    if target == ctx.root:
        raise fail(403, "CANNOT_DELETE_ROOT", "不允许删除工作区根目录")
    if not target.exists():
        raise fail(404, "FILE_NOT_FOUND", f"文件不存在: {path}")

    if target.is_dir():
        try:
            target.rmdir()
        except OSError:
            raise fail(409, "DIRECTORY_NOT_EMPTY", f"目录非空，拒绝删除: {path}") from None
        return {"ok": True, "path": _rel(ctx.root, target), "kind": "dir"}

    target.unlink()
    return {"ok": True, "path": _rel(ctx.root, target), "kind": "file"}


@router.post("/upload", status_code=201)
def upload_file(
    ctx: EditorCtx = Depends(editor_ctx),
    file: UploadFile = File(...),
    path: Optional[str] = Query(None, description="目标相对路径；省略则用上传文件名"),
) -> dict[str, Any]:
    """上传文件。目标路径与文件名**都**过守卫（文件名同样是用户可控输入）。"""
    raw_name = (file.filename or "").strip()
    rel = (path or "").strip() or raw_name
    if not rel:
        raise fail(400, "PATH_REQUIRED", "缺少目标路径，且上传未带文件名")

    target = resolve_inside(ctx.root, rel)
    if target == ctx.root or target.is_dir():
        raise fail(400, "PATH_IS_DIRECTORY", f"不能写入目录: {rel}")

    # 只读上限 + 1 字节，超限即拒：`file.file.read()` 无参数会把整个上传体
    # 拉进内存（Starlette 只把 **临时存储** 落在磁盘，读取仍是全量）。
    data = file.file.read(MAX_WRITE_BYTES + 1)
    if len(data) > MAX_WRITE_BYTES:
        raise fail(413, "FILE_TOO_LARGE", f"上传超过 {MAX_WRITE_BYTES} 字节上限")

    _write_file(target, data)
    return {"ok": True, "workflow_id": ctx.wf_id, "path": _rel(ctx.root, target),
            "bytes": len(data), "sha256": _sha256_of(data)}


@router.get("/download")
def download_file(
    ctx: EditorCtx = Depends(editor_ctx),
    path: str = Query(...),
) -> FileResponse:
    """下载文件（浏览器另存）。"""
    target = resolve_inside(ctx.root, path)
    if not target.exists():
        raise fail(404, "FILE_NOT_FOUND", f"文件不存在: {path}")
    if target.is_dir():
        raise fail(400, "PATH_IS_DIRECTORY", f"该路径是目录: {path}")
    media = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(str(target), media_type=media, filename=target.name)


@router.get("/file-preview-html", response_class=HTMLResponse)
def file_preview_html(
    ctx: EditorCtx = Depends(editor_ctx),
    path: str = Query(...),
    expected_sha256: Optional[str] = Query(None),
) -> HTMLResponse:
    """HTML 预览（iframe 可直接 `src=` 加载）。

    ★ **所有注入 HTML 的内容都必须转义**。这个端点的返回体是
    `text/html`，不转义就等于把工作区文件变成 XSS 载荷——而工作区里
    的文件恰恰是 agent 与用户上传写的，完全不可信。

    二进制（图像）走 `<img>` 指向 `/download`，同样对 path 做 URL 编码。
    """
    target = resolve_inside(ctx.root, path)
    rel = _rel(ctx.root, target)
    if not target.exists():
        body = f"<p>文件不存在：{_esc(rel)}</p>"
        return HTMLResponse(_page(rel, body), status_code=404)
    if target.is_dir():
        return HTMLResponse(_page(rel, f"<p>{_esc(rel)} 是目录。</p>"))

    data, size = _read_head(target, MAX_TEXT_BYTES)
    sha = _sha256_file(target)
    warn = ""
    if expected_sha256 and expected_sha256 != sha:
        warn = (f"<p class='warn'>文件已变更：期望 {_esc(expected_sha256[:12])}…，"
                f"实际 {_esc(sha[:12])}…</p>")

    ext = target.suffix.lower()
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"):
        url = f"/api/editor/{ctx.wf_id}/download?path={quote_url(rel)}"
        inner = f"<img src=\"{url}\" alt=\"{_esc(rel)}\">"
    elif ext == ".pdf":
        url = f"/api/editor/{ctx.wf_id}/download?path={quote_url(rel)}"
        inner = f"<iframe src=\"{url}\"></iframe>"
    elif ext in (".docx", ".xlsx", ".pptx", ".zip"):
        url = f"/api/editor/{ctx.wf_id}/download?path={quote_url(rel)}"
        inner = (f"<p>二进制文件（{_esc(ext)}）无法内联预览。</p>"
                 f"<p><a href=\"{url}\">下载 {_esc(target.name)}</a></p>")
    else:
        text = data.decode("utf-8", "replace")
        tail = "\n\n…（已截断）" if size > MAX_TEXT_BYTES else ""
        inner = f"<pre>{_esc(text + tail)}</pre>"

    return HTMLResponse(_page(rel, warn + inner))


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;"))


def quote_url(text: str) -> str:
    from urllib.parse import quote  # noqa: PLC0415

    return quote(text, safe="")


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{_esc(title)}</title>"
        "<style>body{font:13px/1.6 ui-monospace,Consolas,monospace;margin:0;padding:12px}"
        "pre{white-space:pre-wrap;word-break:break-word;margin:0}"
        "img,iframe{max-width:100%;border:0}"
        ".warn{color:#b45309}</style></head><body>"
        f"{body}</body></html>"
    )


# ---------------------------------------------------------------------------
# 二、编译产物（5）
# ---------------------------------------------------------------------------


@router.post("/compile")
def compile_paper(
    ctx: EditorCtx = Depends(editor_ctx),
    body: Optional[CompileBody] = Body(None),
) -> dict[str, Any]:
    """编译论文。

    **不重写排版逻辑**：latex 模式直接调 `latex_export.export_latex`，
    markdown 模式调 `docx_export.export_docx`——两者的 P0 保护
    （不覆盖 agent 产物、空正文不算成功）都在服务层，这里只做转发与包装。

    失败语义：编译失败**不是** HTTP 错误，而是 `ok: false` + `compile_log`。
    把"TeX 没装"报成 500 会让前端无法区分"服务坏了"与"环境缺依赖"。
    """
    source_md = (body.source_md if body else "") or ""
    if source_md.strip():
        target = resolve_inside(ctx.root, PAPER_MD)
        _write_file(target, source_md.encode("utf-8"))

    ctx.root.mkdir(parents=True, exist_ok=True)
    request_id = uuid.uuid4().hex
    mode = ctx.mode

    try:
        if mode == "markdown":
            result: dict[str, Any] = dx.export_docx(
                ctx.root, template=ctx.template, title=ctx.wf_id)
        else:
            export = lx.export_latex(
                ctx.root, template=ctx.template, language=ctx.language, compile_pdf=True)
            result = export.as_dict()
    except Exception as exc:  # noqa: BLE001 —— 结构化错误，日志留现场
        log.exception("编辑器编译失败 wf=%s mode=%s", ctx.wf_id[:12], mode)
        raise fail(500, "COMPILE_FAILED",
                   f"编译失败：{type(exc).__name__}: {exc}") from exc

    ok = bool(result.get("ok"))
    compile_log = (result.get("compile_error") or result.get("log_tail") or "")
    if ok and not compile_log:
        compile_log = f"{mode} 导出完成"
    current_file = result.get("tex") or result.get("docx") or (
        str(ctx.root / PAPER_MD) if mode == "markdown" else str(ctx.root / PAPER_TEX))

    return {
        "ok": ok,
        "workflow_id": ctx.wf_id,
        "mode": mode,
        "request_id": request_id,
        "message": "导出完成" if ok else (result.get("error") or "编译失败"),
        "current_file": current_file,
        "compile_log": compile_log,
        "result": result,
    }


@router.get("/docx")
def get_docx(
    ctx: EditorCtx = Depends(editor_ctx),
    allow_stale: bool = Query(True, description="为 false 时，过期产物返回 409"),
    expected_sha256: Optional[str] = Query(None),
) -> FileResponse:
    """下载 Word 产物（`paper/main.docx`）。"""
    target = resolve_inside(ctx.root, PAPER_DOCX)
    if not target.is_file():
        raise fail(404, "DOCX_NOT_FOUND",
                   "尚无 Word 产物；请先调用 POST /api/editor/{wf}/compile")

    status = _artifact_status(ctx.root, target)
    if expected_sha256 and expected_sha256 != status["sha256"]:
        raise fail(409, "FILE_CONFLICT",
                   f"Word 产物已更新（当前 {status['sha256'][:12]}…）")
    if not allow_stale and not status["fresh"]:
        raise fail(409, "ARTIFACT_STALE",
                   "Word 产物已过期（正文比产物新）；请重新编译或加 allow_stale=true")

    return FileResponse(
        str(target), filename=target.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@router.get("/docx-status")
def docx_status(ctx: EditorCtx = Depends(editor_ctx)) -> dict[str, Any]:
    """Word 产物状态：**可用性与新鲜度分开报**。

    蓝方注释原话是 "Expose freshness separately from availability"——
    只回一个 `exists` 会让前端把"有旧产物"当成"可以下载最新版"。
    """
    target = resolve_inside(ctx.root, PAPER_DOCX)
    if not target.is_file():
        return {"workflow_id": ctx.wf_id, "available": False, "fresh": False,
                "path": PAPER_DOCX, "reason": "尚未导出 Word 产物",
                "bytes": 0, "mtime": None, "sha256": None,
                "source_latest_mtime": None}
    status = _artifact_status(ctx.root, target)
    status.update({"workflow_id": ctx.wf_id, "available": True, "path": PAPER_DOCX})
    return status


@router.get("/pdf")
def get_pdf(ctx: EditorCtx = Depends(editor_ctx)) -> FileResponse:
    """下载 PDF 产物（`paper/main.pdf`）。"""
    target = resolve_inside(ctx.root, PAPER_PDF)
    if not target.is_file():
        raise fail(404, "PDF_NOT_FOUND",
                   "尚无 PDF 产物；请先编译（需可用的 TeX 运行时）")
    return FileResponse(str(target), filename=target.name, media_type="application/pdf")


@router.get("/stats")
def get_stats(
    ctx: EditorCtx = Depends(editor_ctx),
    path: Optional[str] = Query(None, description="传则统计该文件；不传则统计全文"),
) -> dict[str, Any]:
    """字数统计与页数估算（LaTeX / Markdown 双模式）。

    字符数与页数口径**全部复用服务层**（`workflow_engine.paper_body_chars`
    / `typography.CHARS_PER_PAGE_*`），不在这里另立一份——两套口径必然漂移。
    """
    if path:
        target = resolve_inside(ctx.root, path)
        if not target.exists():
            raise fail(404, "FILE_NOT_FOUND", f"文件不存在: {path}")
        if target.is_dir():
            raise fail(400, "PATH_IS_DIRECTORY", f"该路径是目录: {path}")
        head, _size = _read_head(target, MAX_TEXT_BYTES)
        text = head.decode("utf-8", "replace")
        return {
            "workflow_id": ctx.wf_id, "path": _rel(ctx.root, target), "scope": "file",
            "body_chars": ty.count_body_chars(text, language=ctx.language),
            "lines": text.count("\n") + (1 if text else 0),
            "bytes": target.stat().st_size,
        }

    pages, chars = we.check_paper_body_pages(ctx.root, language=ctx.language)
    per_page = ty.CHARS_PER_PAGE_ZH if ctx.language == "zh" else ty.CHARS_PER_PAGE_EN
    limit = ty.PAGE_LIMIT.get(ctx.template)
    pdf = resolve_inside(ctx.root, PAPER_PDF)
    return {
        "workflow_id": ctx.wf_id, "scope": "paper", "mode": ctx.mode,
        "template": ctx.template,
        "body_chars": chars,
        "estimated_pages": pages,
        "chars_per_page": per_page,
        "page_limit": limit,
        "over_limit": bool(limit) and pages > limit,  # type: ignore[operator]
        "advisory": True,
        "pdf_pages": _pdf_pages(pdf) if pdf.is_file() else None,
    }


def _artifact_status(root: Path, artifact: Path) -> dict[str, Any]:
    """产物的新鲜度：产物 mtime vs 所有正文来源的最新 mtime。"""
    st = artifact.stat()
    sources = [root / s for s in FRESHNESS_SOURCES]
    source_mtime = _latest_mtime(sources)
    fresh = source_mtime is None or st.st_mtime >= source_mtime
    return {
        "fresh": fresh,
        "bytes": st.st_size,
        "mtime": _iso(st.st_mtime),
        "sha256": _sha256_file(artifact),
        "source_latest_mtime": _iso(source_mtime) if source_mtime else None,
        "reason": "" if fresh else "正文比产物新，产物已过期",
    }


def _pdf_pages(pdf: Path) -> Optional[int]:
    try:
        import fitz  # type: ignore

        with fitz.open(str(pdf)) as doc:
            return int(doc.page_count)
    except Exception:  # noqa: BLE001 —— 数不出页数不影响统计主体
        return None


# ---------------------------------------------------------------------------
# 三、编辑器元信息（2）
# ---------------------------------------------------------------------------


@router.get("/mode")
def get_mode(ctx: EditorCtx = Depends(editor_ctx)) -> dict[str, Any]:
    """编辑器模式：`latex` | `markdown`（决定默认打开的文件与"编译"行为）。

    判据优先级：工作流 `params.editor_mode` → `params.mode` → `params.docx_mode`
    → 默认 `latex`。前端据此选默认文件（`main.tex` 还是 `main.md`）。
    """
    mode = ctx.mode
    default_file = PAPER_MD if mode == "markdown" else PAPER_TEX
    exists = resolve_inside(ctx.root, default_file).is_file()
    return {
        "workflow_id": ctx.wf_id,
        "mode": mode,
        "template": ctx.template,
        "language": ctx.language,
        "default_file": default_file,
        "default_file_exists": exists,
        "supported_modes": ["latex", "markdown"],
    }


@router.get("/model-options")
def model_options(
    ctx: EditorCtx = Depends(editor_ctx),
    con: sqlite3.Connection = Depends(db_dep),
) -> dict[str, Any]:
    """可选模型列表。**绝不回传 api_key**（与 `/api/settings/presets` 同一纪律）。"""
    presets = [
        {
            "id": r["id"], "name": r["name"], "model_id": r["model_id"],
            "provider_id": r["provider_id"], "context_mode": r["context_mode"],
            "has_api_key": bool(r["api_key"]),
        }
        for r in con.execute("SELECT * FROM model_presets ORDER BY created_at").fetchall()
    ]
    row = con.execute(
        "SELECT value FROM settings WHERE key IN ('editor_ai_preset_id', 'default_preset_id')"
        " ORDER BY key='editor_ai_preset_id' DESC LIMIT 1").fetchone()
    default_id = row["value"] if row else None
    if default_id and not any(p["id"] == default_id for p in presets):
        default_id = None
    return {
        "workflow_id": ctx.wf_id,
        "presets": presets,
        "default_preset_id": default_id,
        "count": len(presets),
    }


__all__ = ["router", "EditorCtx", "resolve_inside", "is_within", "editor_ctx"]
