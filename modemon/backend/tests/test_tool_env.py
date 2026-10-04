"""工具环境准备测试。

重点回归：**随包工具不得遮蔽系统里更好的工具**。

实测缺陷：曾把所有随包目录一律插到 PATH 最前，结果随包的
**未初始化 MiKTeX** 遮蔽了系统已装的 TeXLive —— agent 第 8 步编译必然失败，
而报错表现是"找不到宏包/需要先 setup"，很难第一时间联想到 PATH 顺序。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from services import tex_runtime as tx  # noqa: E402
from services import tool_env as te  # noqa: E402

PASS = 0
FAIL = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  %s" % name)
    else:
        FAIL += 1
        FAILURES.append(name)
        print("  FAIL  %s  %s" % (name, detail))


def test_env_prepared() -> None:
    print("\n[1] 子进程环境准备")
    env, rep = te.prepare_child_env()
    d = rep.as_dict()

    check("返回 env 与报告", isinstance(env, dict) and isinstance(d, dict))
    check("PATH 被写入", "PATH" in env and env["PATH"], "PATH 缺失")
    check("UTF-8 已设置（避免中文乱码）",
          env.get("PYTHONIOENCODING") == "utf-8" and env.get("PYTHONUTF8") == "1")
    check("关闭交互式分页", env.get("PAGER") == "cat" and env.get("GIT_PAGER") == "cat")

    # 只增不改：原有 PATH 项必须仍在
    orig = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    now = env["PATH"].split(os.pathsep)
    missing = [p for p in orig if p not in now]
    check("**原有 PATH 项一个都没丢**", not missing, str(missing[:3]))


def test_bundled_python_takes_precedence() -> None:
    print("\n[2] 随包 Python 必须前置（科学计算环境）")
    env, rep = te.prepare_child_env()
    found = rep.as_dict()["tools"]
    py = found.get("python") or ""
    check("python 解析到随包运行时",
          "Modex-MH-Agent" in py and "runtime" in py, py)
    check("随包 python 确实存在", Path(py).is_file() if py else False, py)

    # 随包目录必须排在 PATH 靠前位置
    parts = env["PATH"].split(os.pathsep)
    idx = next((i for i, p in enumerate(parts) if p == str(te.MH_ROOT / "runtime" / "python")), -1)
    check("随包 python 目录在 PATH 中且靠前", 0 <= idx <= 2, f"index={idx}")


def test_tex_not_shadowed_by_fresh_miktex() -> None:
    print("\n[3] ★ TeX 不得被未初始化的随包 MiKTeX 遮蔽")
    env, rep = te.prepare_child_env()
    d = rep.as_dict()
    found = d["tools"]
    xe = found.get("xelatex") or ""

    # 真正的判据：解析出来的 xelatex 必须是**能编译的**那个
    rt = tx.resolve_tex_runtime(probe=True)
    if not rt.ready:
        print("      (本机无可用 TeX，跳过)")
        check("无可用 TeX 时给出警告", bool(d["warnings"]) or rt.state in ("fresh", "missing"),
              str(d["warnings"]))
        return

    check("**xelatex 解析到探测通过的那个**",
          Path(xe).resolve() == Path(rt.xelatex).resolve() if xe else False,
          f"got={xe}\n      want={rt.xelatex}")
    check("不是随包那个未初始化的 MiKTeX",
          "runtime\\texlive" not in xe and "runtime/texlive" not in xe, xe)
    check("TeX 来源已记录", bool(d["tex_source"]), str(d))

    # 该 xelatex 必须真的能编译（这是最终判据）
    from pathlib import Path as _P
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        t = _P(td) / "p.tex"
        t.write_text("\\documentclass{article}\\usepackage{xeCJK}\n"
                     "\\begin{document}探\\end{document}\n", encoding="utf-8")
        res = tx.compile_tex(t, runtime=rt, runs=1)
    check("**该 xelatex 确实能编译中文**", res.ok, res.error)


def test_env_override() -> None:
    print("\n[4] 不污染用户环境变量")
    base = {"PATH": "C:\\only", "FOO": "bar"}
    env, rep = te.prepare_child_env(base)
    check("保留调用方传入的变量", env.get("FOO") == "bar")
    check("原有 PATH 项保留", env["PATH"].startswith("C:\\only") or "C:\\only" in env["PATH"])
    check("不引入未请求的变量", "SURPRISE" not in env)


def main() -> int:
    print("=" * 74)
    print("modemon 工具环境测试（★ 随包工具不得遮蔽系统工具）")
    print("=" * 74)
    test_env_prepared()
    test_bundled_python_takes_precedence()
    test_tex_not_shadowed_by_fresh_miktex()
    test_env_override()
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
