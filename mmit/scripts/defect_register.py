#!/usr/bin/env python3
"""Defect register with P0–P3 severity for MMIT-Test.

Rule: status=fixed requires a regression reference AND a passing fix_gate result
unless --force-fixed is explicitly provided for tooling (still recorded).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mmit_lib import DEFECT_LEVELS, ensure_mit, ensure_tests, load_state, read_json, save_state, utc_now, write_json  # noqa: E402


def sanitize_id(value: str, kind: str = "id") -> str:
    if not value or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}", value):
        raise ValueError(f"invalid {kind}: {value!r}")
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Register/update a defect (P0–P3)")
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--id", required=True)
    p.add_argument("--title", default="")
    p.add_argument("--modality", default="code")
    p.add_argument("--level", default="P2", choices=list(DEFECT_LEVELS))
    p.add_argument("--status", default="open", choices=["open", "confirmed", "deferred", "fixed", "rejected"])
    p.add_argument("--regression", default=None, help="path/id of regression test")
    p.add_argument("--notes", default="")
    p.add_argument("--force-fixed", action="store_true", help="allow fixed without gate (audited)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    try:
        defect_id = sanitize_id(args.id, "defect_id")
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    tests = ensure_tests(root)
    mit = ensure_mit(root)
    gate_path = tests / "defects" / f"{defect_id}.fix_gate.json"

    if args.status == "fixed":
        if not args.regression and not args.force_fixed:
            print("error: cannot mark fixed without --regression (design: 无回归不得 fixed)", file=sys.stderr)
            return 2
        if not args.force_fixed:
            if not gate_path.exists():
                print(f"error: missing fix_gate result: {gate_path}; run fix_gate.py first", file=sys.stderr)
                return 2
            gate = read_json(gate_path)
            if not gate.get("passed"):
                print("error: fix_gate did not pass; cannot mark fixed", file=sys.stderr)
                return 2

    defect = {
        "id": defect_id,
        "title": args.title or defect_id,
        "modality": args.modality,
        "level": args.level,
        "status": args.status,
        "regression": args.regression,
        "notes": args.notes,
        "updated_at": utc_now(),
        "rc_id": None,
        "force_fixed": bool(args.force_fixed and args.status == "fixed"),
    }
    try:
        state = load_state(root)
        defect["rc_id"] = f"RC-{state.get('rc_n', 0)}"
    except FileNotFoundError:
        state = None

    out = tests / "defects" / f"{defect_id}.json"
    write_json(out, defect)

    if state is not None:
        counts = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
        for p in (tests / "defects").glob("*.json"):
            if p.name.endswith(".fix_gate.json"):
                continue
            try:
                d = read_json(p)
            except Exception:
                continue
            if d.get("status") in {"open", "confirmed"} and d.get("level") in counts:
                counts[d["level"]] += 1
        state["open_defects"] = counts
        save_state(root, state)

    print(f"defect written: {out} level={args.level} status={args.status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
