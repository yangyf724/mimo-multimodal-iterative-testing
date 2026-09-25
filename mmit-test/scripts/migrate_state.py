#!/usr/bin/env python3
"""Migrate .bug-hunter/state.json to .mit/state.json (MMIT → MMIT-Test)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mit_lib import ensure_mit, read_json, save_state, utc_now, write_json  # noqa: E402


def migrate(old: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    return {
        "version": 1,
        "skill": "mmit-test",
        "mode": "test-and-fix" if old.get("mode") == "hunt-and-fix" else "test-only",
        "created_at": old.get("created_at") or now,
        "updated_at": now,
        "rc_n": 0,
        "rc_sha": None,
        "matrix_rev": None,
        "round": old.get("run_count", 0),
        "quiet_streak": old.get("quiet_streak", 0),
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
        "migrated_from": {
            "path": str(old.get("_source_path", ".bug-hunter/state.json")),
            "skill": old.get("skill", "mmit-hunter"),
            "run_count": old.get("run_count"),
            "modalities_enabled": old.get("modalities_enabled"),
            "migrated_at": now,
        },
        "resume_summary": (
            f"migrated from MMIT run_count={old.get('run_count')} quiet_streak={old.get('quiet_streak')}"
        ),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Migrate MMIT .bug-hunter state to MIT .mit state")
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--src", type=Path, default=None)
    p.add_argument("--force", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    src = args.src or (root / ".bug-hunter" / "state.json")
    if not src.exists():
        print(f"error: source state not found: {src}", file=sys.stderr)
        return 2
    old = read_json(src)
    old["_source_path"] = str(src)
    mit = ensure_mit(root)
    dest = mit / "state.json"
    if dest.exists() and not args.force:
        print(f"error: dest exists: {dest} (use --force)", file=sys.stderr)
        return 2
    state = migrate(old)
    save_state(root, state)
    # also keep a copy of the original mapping for audit
    write_json(mit / "migrate_audit.json", {"from": str(src), "to": str(dest), "at": utc_now(), "mapped": state["migrated_from"]})
    print(f"migrated: {src} -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
