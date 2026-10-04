#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recover the authoritative API contract by introspecting the FastAPI routers.

FastAPI's APIRouter keeps every route as an APIRoute object carrying path,
methods, response_model, status_code, docstring and a `dependant` describing
query/path/body parameters. That is the ground-truth API contract -- far more
reliable than reverse-engineering it from a minified bundle.

Runs one subprocess per router module so a guarded/broken module cannot kill
the sweep. Writes reports/18-api-contract.md + 18-api-contract.json
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
name = MODULE_NAME
m = __import__(name, fromlist=["*"])
out = {"module": name}


def typename(x):
    try:
        if x is None:
            return None
        if isinstance(x, type):
            return x.__name__
        return getattr(x, "__name__", None) or repr(x)[:60]
    except Exception:
        return "?"


def model_fields(cls):
    mf = getattr(cls, "model_fields", None)
    if not mf:
        return None
    d = {}
    for k, v in mf.items():
        try:
            d[k] = {"type": str(v.annotation)[:80], "required": v.is_required(),
                    "default": (None if v.is_required() else repr(v.default)[:60])}
        except Exception:
            d[k] = {"type": "?", "required": "?", "default": "?"}
    return d


routers = []
for n, o in vars(m).items():
    if type(o).__name__ == "APIRouter":
        routers.append((n, o))
out["router_objects"] = [n for n, _ in routers]

routes = []
for rn, r in routers:
    for rt in getattr(r, "routes", []):
        e = {"router": rn}
        for attr in ("path", "name", "summary", "status_code"):
            try:
                v = getattr(rt, attr, None)
                e[attr] = v if isinstance(v, (str, int, type(None))) else str(v)
            except Exception:
                e[attr] = None
        try:
            e["methods"] = sorted(getattr(rt, "methods", None) or [])
        except Exception:
            e["methods"] = []
        try:
            e["response_model"] = typename(getattr(rt, "response_model", None))
            fields = model_fields(getattr(rt, "response_model", None))
            if fields:
                e["response_fields"] = fields
        except Exception:
            e["response_model"] = None
        try:
            e["doc"] = (inspect.getdoc(rt.endpoint) or "")[:900] if getattr(rt, "endpoint", None) else ""
        except Exception:
            e["doc"] = ""
        # dependant: query/path/body params
        try:
            dep = getattr(rt, "dependant", None)
            if dep is not None:
                qp, pp, bp = [], [], []
                for p in getattr(dep, "query_params", []) or []:
                    qp.append({"name": p.name, "type": typename(p.type_),
                               "required": p.required,
                               "default": None if p.required else repr(p.default)[:40]})
                for p in getattr(dep, "path_params", []) or []:
                    pp.append({"name": p.name, "type": typename(p.type_)})
                for p in getattr(dep, "body_params", []) or []:
                    bp.append({"name": p.name, "type": typename(p.type_),
                               "fields": model_fields(p.type_)})
                e["query"] = qp
                e["path_params"] = pp
                e["body"] = bp
        except Exception as exc:
            e["dep_error"] = str(exc)[:120]
        routes.append(e)
out["routes"] = routes
sys.stdout.write(json.dumps(out, ensure_ascii=False, default=repr))
'''.replace("BACKEND_PATH", repr(BACKEND))


def main():
    files = sorted(f for f in os.listdir(os.path.join(BACKEND, "routers"))
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
                "module": mod, "error": p.stderr.decode("utf-8", "replace")[-250:]}
        except subprocess.TimeoutExpired:
            results[mod] = {"module": mod, "error": "timeout"}
        st = "ERR" if "error" in results[mod] else "OK %d routes" % len(results[mod].get("routes", []))
        print("  %-34s %s" % (mod, st))

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=1)

    ok = {m: v for m, v in results.items() if "error" not in v}
    failed = {m: v["error"] for m, v in results.items() if "error" in v}
    all_routes = [r for v in ok.values() for r in v.get("routes", [])]
    n_resp = sum(1 for r in all_routes if r.get("response_fields"))
    n_body = sum(1 for r in all_routes if r.get("body"))
    n_doc = sum(1 for r in all_routes if r.get("doc", "").strip())
    methods = {}
    for r in all_routes:
        for mm in r.get("methods", []):
            methods[mm] = methods.get(mm, 0) + 1

    L = []
    L.append("# 权威 API 契约（路由模块内省）")
    L.append("")
    L.append("**方法**：FastAPI 的 `APIRouter` 对象保存每条路由的 `APIRoute`，")
    L.append("其中含 `path` / `methods` / `response_model` / `status_code` / `dependant`。")
    L.append("这是**权威契约**，比从 minified bundle 反推可靠。")
    L.append("")
    L.append("| 指标 | 值 |")
    L.append("|---|---|")
    L.append("| 路由模块 | %d（成功 %d，失败 %d） |" % (len(mods), len(ok), len(failed)))
    L.append("| **路由总数** | **%d** |" % len(all_routes))
    L.append("| 带 **response_model 字段**的 | **%d** |" % n_resp)
    L.append("| 带 **请求体模型**的 | **%d** |" % n_body)
    L.append("| 有 docstring 的 | %d |" % n_doc)
    L.append("")
    L.append("方法分布：" + ", ".join("`%s`=%d" % (k, v) for k, v in sorted(methods.items(), key=lambda x: -x[1])))
    L.append("")
    if failed:
        L.append("## 失败模块（%d）" % len(failed))
        L.append("")
        for m, e in sorted(failed.items()):
            L.append("- `%s` — %s" % (m, e.strip()[:150]))
        L.append("")

    L.append("## 路由全表")
    L.append("")
    L.append("| 方法 | 路径 | 端点 | response_model | 请求体 | 参数 |")
    L.append("|---|---|---|---|---|---|")
    for r in sorted(all_routes, key=lambda x: (x.get("path") or "", x.get("name") or "")):
        mm = ",".join(r.get("methods") or []) or "-"
        body = ", ".join(b["name"] + (":" + b["type"] if b.get("type") else "")
                         for b in (r.get("body") or [])) or "-"
        params = ", ".join(p["name"] for p in (r.get("query") or [])) or "-"
        L.append("| %s | `%s` | `%s` | `%s` | %s | %s |" % (
            mm, r.get("path"), r.get("name"), r.get("response_model") or "-", body, params))
    L.append("")

    L.append("## 响应模型字段（完整契约）")
    L.append("")
    seen = set()
    for r in all_routes:
        rm = r.get("response_model")
        if not rm or rm in seen or not r.get("response_fields"):
            continue
        seen.add(rm)
        L.append("### `%s`" % rm)
        L.append("")
        L.append("| 字段 | 类型 | 必填 | 默认 |")
        L.append("|---|---|---|---|")
        for k, v in r["response_fields"].items():
            L.append("| `%s` | `%s` | %s | %s |" % (k, v["type"], "是" if v["required"] else "", v["default"] or ""))
        L.append("")

    L.append("## 请求体模型字段")
    L.append("")
    seenb = set()
    for r in all_routes:
        for b in (r.get("body") or []):
            key = b.get("type")
            if not key or key in seenb or not b.get("fields"):
                continue
            seenb.add(key)
            L.append("### `%s`" % key)
            L.append("")
            L.append("| 字段 | 类型 | 必填 | 默认 |")
            L.append("|---|---|---|---|")
            for k, v in b["fields"].items():
                L.append("| `%s` | `%s` | %s | %s |" % (k, v["type"], "是" if v["required"] else "", v["default"] or ""))
            L.append("")

    L.append("## 有说明文档的端点")
    L.append("")
    for r in sorted(all_routes, key=lambda x: x.get("path") or ""):
        if r.get("doc", "").strip():
            L.append("### `%s` %s" % (",".join(r.get("methods") or []), r.get("path")))
            L.append("")
            L.append("```")
            L.append(r["doc"].strip()[:1200])
            L.append("```")
            L.append("")

    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")

    print()
    print("ROUTES   : %d" % len(all_routes))
    print("resp mdl : %d" % n_resp)
    print("req body : %d" % n_body)
    print("doc'd    : %d" % n_doc)
    print("written ->", OUT_MD)


if __name__ == "__main__":
    main()
