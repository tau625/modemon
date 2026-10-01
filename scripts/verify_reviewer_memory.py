"""用真实模型验证"评审跨轮记忆"是否真的减少重复挑刺。

做法：拿真实运行里同一个产物，分别用两种提示词让评审者打分——
  A 组：不带上一轮结论（旧行为）
  B 组：带上上一轮结论与总分（新行为）
比较两组的 must_fix 数量，以及 B 组是否复述已修复项（用关键词重合度粗估）。

用法：.venv\\Scripts\\python.exe scripts\\verify_reviewer_memory.py [run_id]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from modemon.config import load_config  # noqa: E402
from modemon.providers import build_provider  # noqa: E402
from modemon.review import parse_review  # noqa: E402
from modemon.skills import load_skill  # noqa: E402

RUN_ID = sys.argv[1] if len(sys.argv) > 1 else "real-example-01"
STAGE_ID = "modeling_design"
WORD_RE = re.compile(r"[A-Za-z_]{3,}|[\u4e00-\u9fff]{2,}")


def tokens(text: str) -> set[str]:
    return set(WORD_RE.findall(text))


def overlap(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    run_root = root / "runs" / RUN_ID
    cfg = load_config(root=root)

    artifact_path = run_root / "artifacts" / "02_modeling_design.md"
    previous_path = run_root / "logs" / f"review_{STAGE_ID}_round1_raw.json"
    if not artifact_path.exists() or not previous_path.exists():
        print(f"缺少素材：{artifact_path} 或 {previous_path}")
        return 1

    artifact = artifact_path.read_text(encoding="utf-8")
    previous = parse_review(previous_path.read_text(encoding="utf-8"), stage=STAGE_ID)
    print(f"素材：{artifact_path.name}（{len(artifact)} 字符）")
    print(f"上一轮真实评审：{previous.total}/10，必改 {len(previous.must_fix)} 条")
    for item in previous.must_fix:
        print("   -", item[:80])

    skill = load_skill("review", cfg.skills_dir)
    provider = build_provider(cfg.models["reviewer"], cfg.provider_cfg("reviewer"),
                              retry=1, timeout=cfg.run.request_timeout_s)

    def ask(label: str, prev_items: list[str], prev_total: float | None):
        prompt = skill.render(
            stage_title="建模设计",
            stage_id=STAGE_ID,
            competition=json.dumps(cfg.competition, ensure_ascii=False),
            artifact=artifact[:20000],
            context="（本次验证只看产物本身，上下文从略）",
            pass_score=cfg.run.pass_score,
            number_policy=__import__("mma.review", fromlist=["number_policy"]).number_policy(True),
            previous_must_fix=prev_items,
            previous_total=prev_total,
        )
        print(f"\n[{label}] 调用 {provider.model}…")
        resp = provider.complete(
            [{"role": "user", "content": prompt}],
            meta={"role": "reviewer", "stage_id": STAGE_ID, "round": 1},
        )
        review = parse_review(resp.text, stage=STAGE_ID, model=resp.model)
        print(f"[{label}] 总分 {review.total}，必改 {len(review.must_fix)} 条，"
              f"高严重度 {len(review.blockers)} 条")
        for item in review.must_fix:
            print("   *", item[:90])
        return review

    group_a = ask("A 不带上一轮", [], None)
    group_b = ask("B 带上一轮", previous.must_fix, previous.total)

    repeats = 0
    for item in group_b.must_fix:
        if any(overlap(item, old) >= 0.35 for old in previous.must_fix):
            repeats += 1

    a_repeats = sum(
        1 for item in group_a.must_fix if any(overlap(item, old) >= 0.35 for old in previous.must_fix)
    )

    acknowledged = sum(1 for s in group_b.strong_points if "已修" in s or "已解决" in s or "fixed" in s.lower())

    summary = {
        "artifact": artifact_path.name,
        "previous_total": previous.total,
        "previous_must_fix": len(previous.must_fix),
        "group_a": {
            "total": group_a.total,
            "must_fix": len(group_a.must_fix),
            "repeat_of_previous": a_repeats,
            "items": group_a.must_fix,
        },
        "group_b": {
            "total": group_b.total,
            "must_fix": len(group_b.must_fix),
            "repeat_of_previous": repeats,
            "acknowledged_fixed": acknowledged,
            "items": group_b.must_fix,
            "strong_points": group_b.strong_points,
        },
    }

    out = run_root / "experiments"
    out.mkdir(parents=True, exist_ok=True)
    target = out / "reviewer_memory_check.json"
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"A 组（无记忆）：必改 {len(group_a.must_fix)} 条，其中复述上一轮 {a_repeats} 条")
    print(f"B 组（有记忆）：必改 {len(group_b.must_fix)} 条，其中复述上一轮 {repeats} 条，"
          f"明确标注已修复 {acknowledged} 处")
    print(f"结论：{'记忆机制有效（复述减少）' if repeats <= a_repeats else '记忆机制未见效'}")
    print("明细已写入:", target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
