#!/usr/bin/env python3
"""Initialize .mit state for mmit-test."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mit_lib import (  # noqa: E402
    DECISIONS,
    PROD_ACCESS,
    ensure_mit,
    read_json,
    save_state,
    utc_now,
    write_json,
)

DEFAULT_STATE: dict[str, Any] = {
    "version": 1,
    "skill": "mmit-test",
    "mode": "test-and-fix",
    "created_at": None,
    "updated_at": None,
    "rc_n": 0,
    "rc_sha": None,
    "matrix_rev": None,
    "round": 0,
    "quiet_streak": 0,
    "open_defects": {"P0": 0, "P1": 0, "P2": 0, "P3": 0},
    "signals": {},
    "prod_access": "none",
    "prod_test_state": "missing",
    "decision": "in_progress",
    "blinds": [],
    "budget": {
        "max_rc_rounds": 5,
        "max_wall_clock_hours": 4,
        "max_fix_failures_per_defect": 2,
        "max_p0_fix_rounds": 3,
        "max_compose_escalations": 1,
    },
}


def build_state(
    mode: str = "test-and-fix",
    prod_access: str = "none",
    matrix_rev: str | None = None,
    resume: bool = False,
    resume_summary: str | None = None,
) -> dict[str, Any]:
    state = json_deepcopy(DEFAULT_STATE)
    state["created_at"] = utc_now()
    state["updated_at"] = state["created_at"]
    state["mode"] = mode
    if prod_access in PROD_ACCESS:
        state["prod_access"] = prod_access
    if matrix_rev:
        state["matrix_rev"] = matrix_rev
    if resume and resume_summary:
        state["resume_summary"] = resume_summary
        state["decision"] = "in_progress"
    return state


def json_deepcopy(obj: Any) -> Any:
    import json

    return json.loads(json.dumps(obj))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Initialize MMIT-Test state (.mit/state.json)")
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--mode", default="test-and-fix", choices=["test-and-fix", "test-only"])
    p.add_argument("--prod-access", default="none", choices=list(PROD_ACCESS))
    p.add_argument("--matrix-rev", default=None)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--resume-summary", default=None)
    p.add_argument("--force", action="store_true", help="overwrite existing state.json")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    mit = ensure_mit(root)
    state_path = mit / "state.json"
    if state_path.exists() and not args.force:
        if args.resume:
            state = read_json(state_path)
            state["decision"] = "in_progress"
            if args.resume_summary:
                state["resume_summary"] = args.resume_summary
            save_state(root, state)
            print(f"resumed state: {state_path} rc_n={state.get('rc_n')} decision={state.get('decision')}")
            return 0
        print(f"error: state exists: {state_path} (use --force or --resume)", file=sys.stderr)
        return 2

    matrix_rev = args.matrix_rev
    if matrix_rev is None:
        matrix_path = mit / "matrix.json"
        if matrix_path.exists():
            matrix_rev = read_json(matrix_path).get("matrix_rev")

    state = build_state(
        mode=args.mode,
        prod_access=args.prod_access,
        matrix_rev=matrix_rev,
        resume=args.resume,
        resume_summary=args.resume_summary,
    )
    save_state(root, state)
    print(f"state written: {state_path} mode={state['mode']} prod_access={state['prod_access']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
