#!/usr/bin/env python3
"""Export machine-readable hunt report JSON (Phase 3)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

REQUIRED_TOP = (
    "schema_version",
    "exported_at",
    "skill",
    "scope",
    "convergence",
    "counts",
    "bugs",
    "fingerprints",
    "blind_spots",
    "runs",
)

REQUIRED_SCOPE = ("modalities_enabled", "routes", "viewports")
REQUIRED_COUNTS = ("confirmed", "rejected", "fixed", "deferred", "findings_total")
REQUIRED_CONV = ("run_count", "quiet_streak", "required_quiet_streak", "converged")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def iter_bug_files(bh: Path) -> list[Path]:
    out: list[Path] = []
    for sub in ("confirmed", "fixed", "rejected", "deferred"):
        d = bh / "bugs" / sub
        if d.is_dir():
            out.extend(sorted(d.glob("*.json")))
    return out


def slim_bug(bug: dict[str, Any], status_dir: str) -> dict[str, Any]:
    loc = bug.get("location") or {}
    evidence = bug.get("evidence") or {}
    attempts = bug.get("fix_attempts") or {}
    slim: dict[str, Any] = {
        "id": bug.get("id"),
        "status": bug.get("status") or status_dir,
        "modality": bug.get("modality"),
        "category": bug.get("category"),
        "severity": bug.get("severity"),
        "title": bug.get("title"),
        "rule_id": bug.get("rule_id") or evidence.get("rule_id"),
        "fingerprint": bug.get("fingerprint"),
        "location": {
            "surface": loc.get("surface"),
            "route": loc.get("route"),
            "file": loc.get("file"),
            "viewport": loc.get("viewport"),
            "selector": loc.get("selector"),
        },
    }
    if bug.get("fix_route") is not None:
        slim["fix_route"] = bug.get("fix_route")
    if bug.get("fix_reason_codes") is not None:
        slim["fix_reason_codes"] = bug.get("fix_reason_codes")
    if attempts:
        slim["fix_attempts"] = {
            "local": attempts.get("local", 0),
            "lite": attempts.get("lite", 0),
            "diminishing": bool(attempts.get("diminishing", False)),
        }
    if bug.get("packet_path") is not None:
        slim["packet_path"] = bug.get("packet_path")
    return slim


def collect_runs(bh: Path) -> list[dict[str, Any]]:
    runs_dir = bh / "runs"
    out: list[dict[str, Any]] = []
    if not runs_dir.is_dir():
        return out
    for run_path in sorted(runs_dir.iterdir()):
        summary_path = run_path / "summary.json"
        if not summary_path.exists():
            continue
        try:
            summary = load_json(summary_path)
        except Exception:
            continue
        out.append(
            {
                "id": summary.get("run_id") or run_path.name,
                "new_count": summary.get("new_count"),
                "known_count": summary.get("known_count"),
                "suppressed_count": summary.get("suppressed_count", 0),
                "findings_total": summary.get("findings_total"),
                "strategies": summary.get("strategies") or [],
                "degrade_level": summary.get("degrade_level"),
                "by_modality": summary.get("by_modality") or {},
                "by_rule": summary.get("by_rule") or {},
            }
        )
    return out


def build_export(root: Path) -> dict[str, Any]:
    bh = root / ".mmit"
    state: dict[str, Any] = {}
    if (bh / "state.json").exists():
        state = load_json(bh / "state.json")
    web = (state.get("surfaces") or {}).get("web") or {}
    conv = state.get("convergence") or {}
    stats = state.get("stats") or {}
    fp_store: dict[str, Any] = {"entries": {}}
    if (bh / "fingerprints.json").exists():
        fp_store = load_json(bh / "fingerprints.json")
    entries = fp_store.get("entries") or {}

    bugs: list[dict[str, Any]] = []
    counts = {"confirmed": 0, "rejected": 0, "fixed": 0, "deferred": 0}
    by_modality: dict[str, int] = {}
    by_rule: dict[str, int] = {}
    for bug_path in iter_bug_files(bh):
        status_dir = bug_path.parent.name
        try:
            bug = load_json(bug_path)
        except Exception:
            continue
        slim = slim_bug(bug, status_dir)
        bugs.append(slim)
        key = status_dir if status_dir in counts else "confirmed"
        counts[key] = counts.get(key, 0) + 1
        mod = slim.get("modality") or "unknown"
        by_modality[mod] = by_modality.get(mod, 0) + 1
        rule = slim.get("rule_id") or "unknown"
        by_rule[rule] = by_rule.get(rule, 0) + 1

    fp_by_status: dict[str, int] = {}
    for entry in entries.values():
        st = str(entry.get("status") or "candidate")
        fp_by_status[st] = fp_by_status.get(st, 0) + 1

    patterns_path = bh / "fp_patterns.json"
    fp_patterns = {"count": 0, "ids": []}
    if patterns_path.exists():
        try:
            pstore = load_json(patterns_path)
            pats = pstore.get("patterns") or []
            fp_patterns = {"count": len(pats), "ids": [p.get("id") for p in pats]}
        except Exception:
            pass

    suppressed_from_runs = sum(int(r.get("suppressed_count") or 0) for r in collect_runs(bh))

    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": utc_now(),
        "skill": "mmit",
        "phase": state.get("phase", 3),
        "scope": {
            "mode": state.get("mode"),
            "modalities_enabled": state.get("modalities_enabled") or [],
            "base_url": web.get("base_url"),
            "routes": web.get("routes") or [],
            "viewports": web.get("viewports") or [],
            "degrade_level": web.get("degrade_level"),
        },
        "convergence": {
            "run_count": state.get("run_count", 0),
            "quiet_streak": conv.get("quiet_streak", state.get("quiet_streak", 0)),
            "required_quiet_streak": conv.get("required_quiet_streak", 2),
            "converged": bool(conv.get("converged", False)),
        },
        "counts": {
            "confirmed": counts.get("confirmed", 0),
            "rejected": counts.get("rejected", 0),
            "fixed": counts.get("fixed", 0),
            "deferred": counts.get("deferred", 0),
            "findings_total": stats.get("findings_total", 0),
            "suppressed": suppressed_from_runs,
            "by_modality": by_modality,
            "by_rule": by_rule,
        },
        "bugs": bugs,
        "fingerprints": {
            "total": len(entries),
            "by_status": fp_by_status,
        },
        "blind_spots": state.get("blind_spots") or [],
        "runs": collect_runs(bh),
        "fp_patterns": fp_patterns,
        "report_md_path": "REPORT.md",
        "notes": [],
        "budget": state.get("budget") or {},
        "fix_router": state.get("fix_router") or {},
    }


def validate_export(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["export-not-object"]
    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        errors.append(f"unsupported-schema_version:{version!r}")
        return errors
    for key in REQUIRED_TOP:
        if key not in data:
            errors.append(f"missing:{key}")
    scope = data.get("scope")
    if not isinstance(scope, dict):
        errors.append("scope-not-object")
    else:
        for key in REQUIRED_SCOPE:
            if key not in scope:
                errors.append(f"missing:scope.{key}")
    conv = data.get("convergence")
    if not isinstance(conv, dict):
        errors.append("convergence-not-object")
    else:
        for key in REQUIRED_CONV:
            if key not in conv:
                errors.append(f"missing:convergence.{key}")
    counts = data.get("counts")
    if not isinstance(counts, dict):
        errors.append("counts-not-object")
    else:
        for key in REQUIRED_COUNTS:
            if key not in counts:
                errors.append(f"missing:counts.{key}")
    if not isinstance(data.get("bugs"), list):
        errors.append("bugs-not-list")
    if not isinstance(data.get("blind_spots"), list):
        errors.append("blind_spots-not-list")
    if not isinstance(data.get("runs"), list):
        errors.append("runs-not-list")
    fps = data.get("fingerprints")
    if not isinstance(fps, dict) or "total" not in fps:
        errors.append("fingerprints-invalid")
    return errors


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export machine-readable report JSON")
    p.add_argument("--root", default=".")
    p.add_argument("--out", default=None, help="output path (default .mmit/export/report.json)")
    p.add_argument("--validate", dest="validate", default=None, help="validate an existing export file")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.validate:
        path = Path(args.validate)
        if not path.exists():
            print(json.dumps({"ok": False, "errors": ["file-missing"]}, ensure_ascii=False))
            return 1
        try:
            data = load_json(path)
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"ok": False, "errors": [f"invalid-json:{e}"]}, ensure_ascii=False))
            return 1
        errors = validate_export(data)
        print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False, indent=2))
        if not errors:
            return 0
        if any(str(e).startswith("unsupported-schema_version") for e in errors):
            return 3
        return 1

    root = Path(args.root).resolve()
    data = build_export(root)
    errors = validate_export(data)
    out = Path(args.out) if args.out else (root / ".mmit" / "export" / "report.json")
    if not out.is_absolute():
        out = root / out
    save_json(out, data)
    print(
        json.dumps(
            {
                "ok": not errors,
                "out": str(out),
                "errors": errors,
                "bugs": len(data.get("bugs") or []),
                "schema_version": data.get("schema_version"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
