#!/usr/bin/env python3
"""Decidable Fix Gate for MMIT-Test (four conditions + mandatory regression)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mit_lib import ensure_mit, read_json, utc_now, write_json  # noqa: E402


def evaluate_fix_gate(
    target_cleared: bool,
    zero_new_high: bool,
    non_target_stable: bool,
    regression_green: bool,
) -> dict[str, Any]:
    checks = {
        "target_cleared": bool(target_cleared),
        "zero_new_high": bool(zero_new_high),
        "non_target_stable": bool(non_target_stable),
        "regression_green": bool(regression_green),
    }
    passed = all(checks.values())
    return {
        "passed": passed,
        "checks": checks,
        "failed_checks": [k for k, v in checks.items() if not v],
        "evaluated_at": utc_now(),
    }


def sanitize_id(value: str, kind: str = "id") -> str:
    import re

    if not value or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}", value):
        raise ValueError(f"invalid {kind}: {value!r}")
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate Fix Gate (MMIT-Test)")
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--defect-id", required=True)
    p.add_argument("--target-cleared", action="store_true", help="same defect/path no longer hits")
    p.add_argument("--zero-new-high", action="store_true", help="no new P0/P1")
    p.add_argument("--non-target-stable", action="store_true", help="non-target surfaces stable")
    p.add_argument("--regression-green", action="store_true", help="regression tests exit 0")
    p.add_argument("--no-regression", action="store_true", help="explicitly mark no regression provided (always fails)")
    p.add_argument("--out", type=Path, default=None)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    try:
        defect_id = sanitize_id(args.defect_id, "defect_id")
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if args.no_regression:
        result = evaluate_fix_gate(
            target_cleared=args.target_cleared,
            zero_new_high=args.zero_new_high,
            non_target_stable=args.non_target_stable,
            regression_green=False,
        )
        result["note"] = "no regression test provided — cannot mark fixed"
    else:
        result = evaluate_fix_gate(
            target_cleared=args.target_cleared,
            zero_new_high=args.zero_new_high,
            non_target_stable=args.non_target_stable,
            regression_green=args.regression_green,
        )
    result["defect_id"] = defect_id
    out = args.out or (ensure_mit(root) / "defects" / f"{defect_id}.fix_gate.json")
    write_json(out, result)
    status = "PASS" if result["passed"] else "FAIL"
    print(f"fix_gate {status} defect={defect_id} failed={result['failed_checks']}")
    print(f"written: {out}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
