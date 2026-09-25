#!/usr/bin/env python3
"""Run frozen matrix items for one RC (MMIT-Test).

Evidence rules:
- dry-run never counts as PASS
- missing/unwired probes are blind_spot (required) or unavailable (optional), never PASS
- dirty data_mask report refuses to run (hard gate)
- probe stdout/stderr must look like a real check, not --help / trivial exit 0
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mmit_lib import (  # noqa: E402
    blind_spot,
    ensure_mit,
    ensure_tests,
    load_state,
    read_json,
    save_state,
    utc_now,
    write_json,
)

# Patterns that indicate a probe was not a real check.
FAKE_PROBE_PATTERNS = [
    re.compile(r"--help"),
    re.compile(r"^usage:", re.I),
    re.compile(r"show this help message", re.I),
]


def sanitize_id(value: str, kind: str = "id") -> str:
    """Allow only safe path segments (no separators / traversal)."""
    if not value or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}", value):
        raise ValueError(f"invalid {kind}: {value!r}")
    if ".." in value:
        raise ValueError(f"invalid {kind}: {value!r}")
    return value


def code_probe_cmd(root: Path) -> list[str]:
    """Prefer project-native test runner; fall back to unittest."""
    pkg = root / "package.json"
    if pkg.exists():
        try:
            data = read_json(pkg)
            scripts = (data.get("scripts") or {}).get("test", "")
            if "node --test" in scripts or scripts.strip().startswith("node"):
                return ["node", "--test", "tests/"]
            if "pytest" in scripts or "unittest" in scripts:
                return [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"]
        except Exception:
            pass
    return [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"]


# Real probe wiring. Probes must exercise the surface; --help is forbidden.
PROBE_COMMANDS: dict[str, list[str]] = {
    "code": [],  # resolved per-root via code_probe_cmd
    # layout_probe needs elements.json; without a capture we mark blind_spot rather than fake pass.
    "web": [],
    "api": [sys.executable, "{script_dir}/api_contract_check.py", "--root", "{root}"],
    "canvas": [sys.executable, "{script_dir}/canvas_probe.py", "--root", "{root}"],
    "cli": [],
}


def resolve_cmd(template: list[str], script_dir: Path, root: Path) -> list[str]:
    return [
        part.replace("{script_dir}", str(script_dir)).replace("{root}", str(root))
        for part in template
    ]


def looks_fake(cmd: list[str], stdout: str, stderr: str) -> str | None:
    joined = " ".join(cmd)
    for pat in FAKE_PROBE_PATTERNS:
        if pat.search(joined):
            return f"probe command looks like help/stub: {joined}"
    blob = f"{stdout}\n{stderr}"
    # Help-text markers are decisive regardless of other tokens (avoid "ok" bypass).
    if re.search(r"show this help message", blob, re.I) or re.search(r"^usage:", blob, re.I | re.M):
        return "probe output looks like help text, not a real check"
    if "exit(0)" in joined and ("-c" in cmd or "--help" in cmd):
        return "trivial always-green stub"
    return None


def run_item(
    root: Path,
    script_dir: Path,
    item: dict[str, Any],
    rc_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    modality = item["modality"]
    mark = item["mark"]
    result: dict[str, Any] = {
        "modality": modality,
        "mark": mark,
        "started_at": utc_now(),
        "status": "pending",
        "exit_code": None,
        "evidence": [],
        "notes": "",
    }
    if mark == "n/a":
        result["status"] = "excluded"
        result["finished_at"] = utc_now()
        return result

    if dry_run:
        result["status"] = "dry_run"
        result["notes"] = "dry-run: probe not executed (not PASS)"
        result["finished_at"] = utc_now()
        return result

    if modality == "code":
        template = code_probe_cmd(root)
    else:
        template = PROBE_COMMANDS.get(modality) or []

    if not template:
        result["status"] = "blind_spot" if mark == "required" else "unavailable"
        result["notes"] = (
            "required modality has no real executable probe; recorded as blind spot (not PASS)"
            if mark == "required"
            else "no probe wired"
        )
        result["finished_at"] = utc_now()
        return result

    cmd = resolve_cmd(template, script_dir, root)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
        result["exit_code"] = proc.returncode
        log_dir = ensure_tests(root) / "runs" / rc_id / "logs"
        log_path = log_dir / f"{modality}.log"
        log_path.write_text(
            f"$ {' '.join(cmd)}\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}\n",
            encoding="utf-8",
        )
        result["evidence"].append(str(log_path.relative_to(root)))
        fake = looks_fake(cmd, proc.stdout, proc.stderr)
        if fake:
            result["status"] = "blind_spot" if mark == "required" else "unavailable"
            result["notes"] = fake
        elif proc.returncode == 0:
            result["status"] = "pass"
        else:
            result["status"] = "fail"
            result["notes"] = f"probe exit {proc.returncode}"
    except (OSError, subprocess.TimeoutExpired) as e:
        result["status"] = "blind_spot" if mark == "required" else "unavailable"
        result["notes"] = f"probe error: {e}"
    result["finished_at"] = utc_now()
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Execute frozen matrix for current RC")
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--rc-id", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--only", default=None, help="run a single modality")
    p.add_argument("--skip-mask-gate", action="store_true", help="debug only: skip dirty-mask refusal")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    script_dir = Path(__file__).resolve().parent
    tests = ensure_tests(root)
    mit = ensure_mit(root)

    # Hard gate: dirty mask refuses to run (design §7.5 / DoD §17.2)
    mask_path = tests / "data_mask_report.json"
    if not args.skip_mask_gate:
        if mask_path.exists():
            mask = read_json(mask_path)
            if not mask.get("clean", False):
                print(f"error: data mask not clean ({mask.get('count')} findings); refuse to run", file=sys.stderr)
                return 3
        else:
            print("error: data_mask_report.json missing; run data_mask.py first (hard gate)", file=sys.stderr)
            return 3

    matrix_path = tests / "matrix.json"
    if not matrix_path.exists():
        print(f"error: matrix not found: {matrix_path}", file=sys.stderr)
        return 2
    matrix = read_json(matrix_path)
    if not matrix.get("frozen"):
        print("error: matrix not frozen; run matrix_build.py --freeze first", file=sys.stderr)
        return 2

    try:
        state = load_state(root)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.rc_id:
        try:
            rc_id = sanitize_id(args.rc_id, "rc_id")
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
    else:
        rc_id = f"RC-{state.get('rc_n', 1)}"

    results = []
    for item in matrix.get("items", []):
        if args.only and item["modality"] != args.only:
            continue
        res = run_item(root, script_dir, item, rc_id, dry_run=args.dry_run)
        results.append(res)
        if res["status"] == "blind_spot":
            blind_spot(state, f"{rc_id}:{item['modality']}", res.get("notes") or "required probe unavailable")

    out_dir = tests / "runs" / rc_id / "findings"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "matrix_results.json"
    write_json(
        out_path,
        {
            "rc_id": rc_id,
            "rc_sha": state.get("rc_sha"),
            "matrix_rev": matrix.get("matrix_rev"),
            "results": results,
        },
    )

    status_map = {
        "pass": "done",
        "fail": "failed",
        "blind_spot": "blind_spot",
        "unavailable": "degraded",
        "excluded": "excluded",
        "dry_run": "dry_run",
    }
    by_mod = {r["modality"]: r for r in results}
    for item in matrix.get("items", []):
        if item["modality"] in by_mod and item["mark"] != "n/a":
            st = by_mod[item["modality"]]["status"]
            item["status"] = status_map.get(st, item["status"])
    write_json(matrix_path, matrix)
    save_state(root, state)

    summary = {
        "rc_id": rc_id,
        "pass": sum(1 for r in results if r["status"] == "pass"),
        "fail": sum(1 for r in results if r["status"] == "fail"),
        "blind_spot": sum(1 for r in results if r["status"] == "blind_spot"),
        "unavailable": sum(1 for r in results if r["status"] == "unavailable"),
        "dry_run": sum(1 for r in results if r["status"] == "dry_run"),
        "excluded": sum(1 for r in results if r["status"] == "excluded"),
    }
    print(f"matrix run: {json.dumps(summary, ensure_ascii=False)}")
    print(f"results: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
