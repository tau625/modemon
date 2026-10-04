#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recover the authoritative API contract by introspecting the FastAPI routers.

Corrected for Pydantic v2 / modern FastAPI attribute layout:
  - request body   -> APIRoute.body_field.field_info.annotation
  - response model  -> APIRoute.response_field.field_info.annotation
  - query/path/header params -> Dependant.*_params[i].field_info.annotation

Writes reports/18-api-contract.md + 18-api-contract.json
"""
import json
import os
import subprocess

BACKEND = r"E:\02_Installers\DailyApps\Modex-MH-Agent\resources\app\backend"
PY = r"E:\02_Installers\DailyApps\Modex-MH-Agent\runtime\python\python.exe"
RE = r"E:\02_Installers\DailyApps\Modex-MH-Agent-RE"
OUT_MD = os.path.join(RE, "reports", "18-api-contract.md")
OUT_JSON = os.path.join(RE, "reports", "18-api-contract.json")

WORKER = '''
import json, sys, inspect
sys.path.insert(0, BACKEND_PATH)
m = __import__(MODULE_NAME, fromlist=["*"])
out = {"module": MODULE_NAME}


def typename(x):
    if x is None:
        return None
    if isinstance(x, type):
        return x.__name__
    s = str(x)
    return getattr(x, "__name__", None) or (s[:70] if s else None)


def ann(obj):
    """annotation of a ModelField / Param, tolerant across versions."""
    fi = getattr(obj, "field_info", None)
    if fi is not None:
        a = getattr(fi, "annotation", None)
        if a is not None:
            return a
    for a_name in ("type_", "annotation", "type"):
        a = getattr(obj, a_name, None)
        if a is not None:
            return a
    return None


def fields_of(cls):
    mf = getattr(cls, "model_fields", None)
    if not mf:
        return None
    d = {}
    for k, v in mf.items():
        try:
            d[k] = {"type": str(getattr(v, "annotation", "?"))[:200],
                    "required": bool(v.is_required()),
                    "default": (None if v.is_required() else repr(v.default)[:60])}
        except Exception:
            d[k] = {"type": "?", "required": "?", "default": "?"}
    return d


def params_of(dep, attr):
    rows = []
    for p in getattr(dep, attr, None) or []:
        try:
            a = ann(p)
            rows.append({"name": getattr(p, "name", "?"),
                         "type": typename(a),
                         "required": bool(getattr(p, "required", False)),
                         "default": (None if getattr(p, "required", False)
                                     else repr(getattr(p, "default", None))[:50]),
                         "fields": fields_of(a) if isinstance(a, type) else None})
        except Exception:
            pass
    return rows


routers = [(n, o) for n, o in vars(m).items() if type(o).__name__ == "APIRouter"]
out["router_objects"] = [n for n, _ in routers]

routes = []
for rn, r in routers:
    for rt in getattr(r, "routes", []):
        e = {"router": rn, "path": getattr(rt, "path", None),
             "name": getattr(rt, "name", None),
             "status_code": getattr(rt, "status_code", None),
             "tags": list(getattr(rt, "tags", []) or []),
             "methods": sorted(getattr(rt, "methods", None) or [])}
        try:
            e["doc"] = (inspect.getdoc(rt.endpoint) or "")[:1200]
        except Exception:
            e["doc"] = ""
        # response model
        try:
            rf = getattr(rt, "response_field", None)
            a = ann(rf) if rf is not None else None
            e["response_model"] = typename(a)
            e["response_fields"] = fields_of(a) if isinstance(a, type) else None
        except Exception:
            e["response_model"] = None
            e["response_fields"] = None
        # request body
        try:
            bf = getattr(rt, "body_field", None)
            a = ann(bf) if bf is not None else None
            e["body_model"] = typename(a)
            e["body_fields"] = fields_of(a) if isinstance(a, type) else None
        except Exception:
            e["body_model"] = None
            e["body_fields"] = None
        # params
        try:
            dep = getattr(rt, "dependant", None)
            e["query"] = params_of(dep, "query_params") if dep else []
            e["path_params"] = params_of(dep, "path_params") if dep else []
            e["headers"] = params_of(dep, "header_params") if dep else []
        except Exception:
            e["query"] = []
            e["path_params"] = []
            e["headers"] = []
        routes.append(e)
out["routes"] = routes
sys.stdout.write(json.dumps(out, ensure_ascii=False, default=repr))
'''.replace("BACKEND_PATH", repr(BACKEND))


def main():
    rdir = os.path.join(BACKEND, "routers")
    files = sorted(f for f in os.listdir(rdir)
                   if f.endswith((".pyd", ".pyc")) and not f.startswith("__"))
    mods = ["routers." + f.split(".")[0] for f in files]
    print("router modules:", len(mods))

    results = {}
    for mod in mods:
        src = WORKER.replace("MODULE_NAME", repr(mod))
        try:
            p = subprocess.run([PY, "-c", src], capture_output=True, timeout=120, cwd=BACKEND)
            out = p.stdout.decode("utf-8", "replace").strip()
            results[mod] = json.loads(out) if out.startswith("{") else {
                "module": mod, "error": p.stderr.decode("utf-8", "replace")[-220:]}
        except subprocess.TimeoutExpired:
            results[mod] = {"module": mod, "error": "timeout"}

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=1)

    ok = {m: v for m, v in results.items() if "error" not in v}
    failed = {m: v["error"] for m, v in results.items() if "error" in v}
    all_routes = [r for v in ok.values() for r in v.get("routes", [])]
    n_resp = sum(1 for r in all_routes if r.get("response_fields"))
    n_body = sum(1 for r in all_routes if r.get("body_fields"))
    n_bodyname = sum(1 for r in all_routes if r.get("body_model"))
    n_doc = sum(1 for r in all_routes if (r.get("doc") or "").strip())
    methods = {}
    for r in all_routes:
        for mm in r.get("methods", []):
            methods[mm] = methods.get(mm, 0) + 1

    L = []
    L.append("# 权威 API 契约（路由模块内省）")
    L.append("")
    L.append("**方法**：FastAPI 的 `APIRouter` 保存每条 `APIRoute`，其中含")
    L.append("`path` / `methods` / `status_code` / `body_field` / `response_field` / `dependant`。")
    L.append("这是**权威契约**，比从 minified bundle 反推可靠。")
    L.append("")
    L.append("| 指标 | 值 |")
    L.append("|---|---|")
    L.append("| 路由模块 | %d（成功 %d，失败 %d） |" % (len(mods), len(ok), len(failed)))
    L.append("| **路由总数** | **%d** |" % len(all_routes))
    L.append("| 带**请求体模型**的 | **%d** |" % n_bodyname)
    L.append("| 请求体模型**字段已展开**的 | **%d** |" % n_body)
    L.append("| 带**响应模型字段**的 | **%d** |" % n_resp)
    L.append("| 有端点 docstring 的 | %d |" % n_doc)
    L.append("")
    L.append("方法分布：" + ", ".join("`%s`=%d" % (k, v) for k, v in sorted(methods.items(), key=lambda x: -x[1])))
    L.append("")
    if failed:
        L.append("## 失败模块（%d）" % len(failed))
        L.append("")
        for m, e in sorted(failed.items()):
            L.append("- `%s` — %s" % (m, e.strip()[:150]))
        L.append("")

    L.append("## 路由全表（%d 条）" % len(all_routes))
    L.append("")
    L.append("| 方法 | 路径 | 状态码 | 端点 | 请求体 | 响应模型 |")
    L.append("|---|---|---|---|---|---|")
    for r in sorted(all_routes, key=lambda x: (x.get("path") or "", x.get("name") or "")):
        mm = ",".join(r.get("methods") or []) or "-"
        L.append("| %s | `%s` | %s | `%s` | %s | %s |" % (
            mm, r.get("path"), r.get("status_code") or "-", r.get("name"),
            ("`%s`" % r["body_model"]) if r.get("body_model") else "-",
            ("`%s`" % r["response_model"]) if r.get("response_model") else "-"))
    L.append("")

    L.append("## ★ 请求体模型字段（完整契约，去重）")
    L.append("")
    seen = set()
    for r in sorted(all_routes, key=lambda x: x.get("path") or ""):
        bm = r.get("body_model")
        if not bm or bm in seen or not r.get("body_fields"):
            continue
        seen.add(bm)
        L.append("### `%s`  ← `%s` %s" % (bm, ",".join(r.get("methods") or []), r.get("path")))
        L.append("")
        L.append("| 字段 | 类型 | 必填 | 默认 |")
        L.append("|---|---|---|---|")
        for k, v in r["body_fields"].items():
            L.append("| `%s` | `%s` | %s | %s |" % (k, v["type"], "是" if v["required"] else "", v["default"] or ""))
        L.append("")

    L.append("## 响应模型字段（去重）")
    L.append("")
    seenr = set()
    for r in sorted(all_routes, key=lambda x: x.get("path") or ""):
        rm = r.get("response_model")
        if not rm or rm in seenr or not r.get("response_fields"):
            continue
        seenr.add(rm)
        L.append("### `%s`  ← `%s` %s" % (rm, ",".join(r.get("methods") or []), r.get("path")))
        L.append("")
        L.append("| 字段 | 类型 | 必填 | 默认 |")
        L.append("|---|---|---|---|")
        for k, v in r["response_fields"].items():
            L.append("| `%s` | `%s` | %s | %s |" % (k, v["type"], "是" if v["required"] else "", v["default"] or ""))
        L.append("")

    L.append("## 查询参数（有 query 参数的路由）")
    L.append("")
    L.append("| 路径 | 方法 | query 参数 |")
    L.append("|---|---|---|")
    for r in sorted(all_routes, key=lambda x: x.get("path") or ""):
        q = r.get("query") or []
        if q:
            L.append("| `%s` | %s | %s |" % (
                r.get("path"), ",".join(r.get("methods") or []),
                ", ".join("%s%s" % (p["name"], "" if p["required"] else "?") for p in q)))
    L.append("")

    L.append("## 有说明文档的端点（%d）" % n_doc)
    L.append("")
    for r in sorted(all_routes, key=lambda x: x.get("path") or ""):
        d = (r.get("doc") or "").strip()
        if d:
            L.append("### `%s` %s" % (",".join(r.get("methods") or []), r.get("path")))
            L.append("")
            L.append("```")
            L.append(d[:1000])
            L.append("```")
            L.append("")

    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")

    print()
    print("ROUTES    : %d" % len(all_routes))
    print("body model: %d (expanded %d)" % (n_bodyname, n_body))
    print("resp model: %d" % n_resp)
    print("doc'd     : %d" % n_doc)
    print("written ->", OUT_MD)


if __name__ == "__main__":
    main()
