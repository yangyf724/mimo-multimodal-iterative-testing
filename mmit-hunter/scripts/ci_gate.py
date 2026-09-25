#!/usr/bin/env python3
"""CI orchestration for mmit-hunter (Phase 3)."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


SCRIPTS = Path(__file__).resolve().parent


def _run(cmd: list[str], *, cwd: Path, timeout: int = 180) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        detail = (proc.stdout or "")[-400:]
        if proc.returncode != 0:
            detail = ((proc.stderr or "")[-200:] + "\n" + detail).strip()
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "detail": detail,
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "returncode": -1, "detail": str(e)}


def run_ci(
    *,
    root: Path,
    skip_e2e: bool = False,
    skip_axe: bool = True,
    demo_root: Path | None = None,
    second_root: Path | None = None,
    python: str | None = None,
) -> dict[str, Any]:
    py = python or sys.executable
    steps: list[dict[str, Any]] = []

    def add(name: str, result: dict[str, Any], *, optional: bool = False) -> None:
        steps.append(
            {
                "name": name,
                "status": "PASS" if result.get("ok") else ("SKIP" if optional and result.get("skip") else "FAIL"),
                "detail": result.get("detail") or result.get("status") or "",
                "returncode": result.get("returncode"),
            }
        )

    # 1. unittest
    add(
        "unittest",
        _run([py, "-m", "unittest", "discover", "-s", "tests"], cwd=root, timeout=180),
    )

    # 2. fixture E2E
    if not skip_e2e:
        for script_name in ("phase1_fixture_e2e.py", "phase2_fixture_e2e.py"):
            script = root / "tests" / script_name
            if script.exists():
                add(f"e2e:{script_name}", _run([py, str(script)], cwd=root, timeout=120))

    # 3. baseline lock (optional if no lock)
    bl = SCRIPTS / "baseline_lock.py"
    demo = demo_root or (root / "examples" / "acceptance-demo")
    lock = demo / ".bug-hunter" / "baselines" / "lock.json"
    if lock.exists():
        add(
            "baseline_lock",
            _run([py, str(bl), "--root", str(demo), "--verify"], cwd=root),
        )
    else:
        steps.append(
            {
                "name": "baseline_lock",
                "status": "SKIP",
                "detail": f"no lock at {lock}",
            }
        )

    # 4. export smoke — always validate a synthetic export schema when no project state
    er = SCRIPTS / "export_report.py"
    target = second_root or demo
    if (target / ".bug-hunter" / "state.json").exists():
        add(
            "export_report",
            _run([py, str(er), "--root", str(target)], cwd=root),
        )
    else:
        # Always-on schema gate: build/validate from empty tree (must be schema-valid).
        add(
            "export_report",
            _run([py, str(er), "--root", str(root / ".ci-tmp" / "empty-export")], cwd=root),
        )

    # 5. optional axe
    if not skip_axe:
        ag = SCRIPTS / "axe_gate.py"
        second = second_root or (root / "examples" / "second-project")
        html = second / "public" / "index.html"
        if html.exists():
            add(
                "axe_gate",
                _run(
                    [
                        py,
                        str(ag),
                        "--html-file",
                        str(html),
                        "--out",
                        str(root / ".ci-tmp" / "axe"),
                        "--fail-on",
                        "violations",
                    ],
                    cwd=root,
                ),
            )
        else:
            steps.append({"name": "axe_gate", "status": "SKIP", "detail": "no second-project html"})
    else:
        steps.append({"name": "axe_gate", "status": "SKIP", "detail": "axe disabled (default)"})

    ok = all(s["status"] in ("PASS", "SKIP") for s in steps)
    return {
        "ok": ok,
        "generated_at": utc_now(),
        "root": str(root),
        "steps": steps,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run CI gate steps")
    p.add_argument("--root", default=".")
    p.add_argument("--skip-e2e", action="store_true")
    p.add_argument(
        "--with-axe",
        action="store_true",
        help="enable axe_gate step (default: disabled — axe is optional)",
    )
    p.add_argument("--demo-root", default=None)
    p.add_argument("--second-root", default=None)
    p.add_argument("--out", default=None)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()
    report = run_ci(
        root=root,
        skip_e2e=args.skip_e2e,
        skip_axe=not args.with_axe,
        demo_root=Path(args.demo_root).resolve() if args.demo_root else None,
        second_root=Path(args.second_root).resolve() if args.second_root else None,
    )
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
