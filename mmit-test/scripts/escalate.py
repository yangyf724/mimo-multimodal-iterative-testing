#!/usr/bin/env python3
"""Assemble escalation package for MMIT-Test."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mit_lib import ensure_mit, load_state, read_json, save_state, utc_now  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build .mit/escalation/ package")
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--reason", required=True)
    p.add_argument("--next-action", action="append", default=[], dest="next_actions")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    mit = ensure_mit(root)
    esc = mit / "escalation"
    esc.mkdir(parents=True, exist_ok=True)

    state = load_state(root)
    state["decision"] = "escalated"
    save_state(root, state)

    (esc / "REASON.md").write_text(
        "# Escalation Reason\n\n"
        f"- at: {utc_now()}\n"
        f"- reason: {args.reason}\n"
        f"- rc: RC-{state.get('rc_n')} sha={state.get('rc_sha')}\n"
        f"- open_defects: {json.dumps(state.get('open_defects', {}), ensure_ascii=False)}\n"
        f"- blinds: {json.dumps(state.get('blinds', []), ensure_ascii=False)}\n",
        encoding="utf-8",
    )

    # copy deliverables if present
    deliv = mit / "deliverables"
    for name in (
        "TEST_REPORT.md",
        "adjudication_signals.json",
        "PROD_RESULTS_MISSING.md",
        "RELEASE_DECISION.md",
        "EVIDENCE_INDEX.md",
    ):
        src = deliv / name
        if src.exists():
            shutil.copy2(src, esc / name)
    if (deliv / "evidence").is_dir():
        shutil.copytree(deliv / "evidence", esc / "evidence", dirs_exist_ok=True)
    prod = mit / "prod_test_results.json"
    if prod.exists():
        shutil.copy2(prod, esc / "prod_test_results.json")

    open_defects = []
    defects_dir = mit / "defects"
    if defects_dir.is_dir():
        for p in defects_dir.glob("*.json"):
            if p.name.endswith(".fix_gate.json"):
                continue
            try:
                d = read_json(p)
                if d.get("status") in {"open", "confirmed", "deferred"} or d.get("level") in {"P0", "P1"}:
                    open_defects.append(d)
            except (json.JSONDecodeError, OSError):
                continue
    from mit_lib import write_json

    write_json(esc / "defects_open.json", open_defects)
    env = mit / "env_manifest.json"
    if env.exists():
        shutil.copy2(env, esc / "env_manifest.json")

    actions = args.next_actions or [
        "确认生产访问授权级别",
        "复核开放 P0/P1 与证据包",
        "决定是否条件放量或拒绝发布",
    ]
    (esc / "next_actions.md").write_text(
        "# Next Actions\n\n" + "\n".join(f"{i+1}. {a}" for i, a in enumerate(actions)) + "\n",
        encoding="utf-8",
    )
    print(f"escalation package written: {esc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
