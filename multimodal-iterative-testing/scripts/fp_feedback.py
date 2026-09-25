#!/usr/bin/env python3
"""False-positive pattern library and whitelist (Phase 3)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOCK_RETRY = 3
LOCK_SLEEP_S = 0.05

MATCH_MODES = {"exact", "selector+rule+route", "rule+route", "digest"}


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


def acquire_lock(lock_path: Path) -> int:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    last_err: Exception | None = None
    for attempt in range(LOCK_RETRY):
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()}\n{utc_now()}\n".encode("utf-8"))
            return fd
        except FileExistsError as e:
            last_err = e
            if attempt < LOCK_RETRY - 1:
                time.sleep(LOCK_SLEEP_S * (attempt + 1))
                continue
            raise RuntimeError(f"lock exists: {lock_path}") from e
    raise RuntimeError(f"lock acquire failed: {last_err}")


def release_lock(fd: int, lock_path: Path) -> None:
    try:
        os.close(fd)
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


def default_patterns_path(root: Path) -> Path:
    return root / ".bug-hunter" / "fp_patterns.json"


def empty_store() -> dict[str, Any]:
    return {"version": 1, "updated_at": None, "patterns": []}


def load_patterns(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_store()
    data = load_json(path)
    data.setdefault("patterns", [])
    return data


def save_patterns(path: Path, data: dict[str, Any]) -> None:
    data["updated_at"] = utc_now()
    save_json(path, data)


def _norm_sel(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def finding_fields(finding: dict[str, Any]) -> dict[str, str]:
    loc = finding.get("location") or {}
    evidence = finding.get("evidence") or {}
    digest = (
        finding.get("core_assertion_digest")
        or evidence.get("core_assertion_digest")
        or ""
    )
    rule_id = finding.get("rule_id") or evidence.get("rule_id") or ""
    selector = loc.get("selector") or loc.get("canvas_object_id") or loc.get("symbol") or ""
    return {
        "modality": str(finding.get("modality") or ""),
        "category": str(finding.get("category") or ""),
        "rule_id": str(rule_id or ""),
        "route": str(loc.get("route") or loc.get("file") or ""),
        "viewport": str(loc.get("viewport") or ""),
        "selector": _norm_sel(str(selector or "")),
        "digest": str(digest or ""),
    }


def pattern_matches(pattern: dict[str, Any], finding: dict[str, Any]) -> bool:
    f = finding_fields(finding)
    mode = pattern.get("match") or "selector+rule+route"
    if mode == "digest":
        return bool(pattern.get("core_assertion_digest")) and (
            f["digest"] == pattern.get("core_assertion_digest")
        )
    if pattern.get("rule_id") and f["rule_id"] != pattern.get("rule_id"):
        return False
    if pattern.get("modality") and f["modality"] != pattern.get("modality"):
        return False
    if pattern.get("category") and f["category"] != pattern.get("category"):
        return False
    if mode == "exact":
        if (pattern.get("route") or "") != f["route"]:
            return False
        if (pattern.get("viewport") or "") != f["viewport"]:
            return False
        if _norm_sel(pattern.get("selector_pattern") or "") != f["selector"]:
            return False
        return True
    if mode == "selector+rule+route":
        if (pattern.get("route") or "") != f["route"]:
            return False
        sel_pat = _norm_sel(pattern.get("selector_pattern") or "")
        if not sel_pat:
            return False
        if sel_pat != f["selector"]:
            return False
        return True
    if mode == "rule+route":
        return (pattern.get("route") or "") == f["route"] and bool(pattern.get("rule_id"))
    return False


def find_match(store: dict[str, Any], finding: dict[str, Any]) -> dict[str, Any] | None:
    for pattern in store.get("patterns") or []:
        if pattern_matches(pattern, finding):
            return pattern
    return None


def mark_suppressed(finding: dict[str, Any], pattern: dict[str, Any]) -> dict[str, Any]:
    item = dict(finding)
    item["status"] = "suppressed"
    item["suppressed_by"] = pattern.get("id")
    item["suppressed_reason"] = pattern.get("reason")
    return item


def apply_patterns(
    findings: list[dict[str, Any]],
    store: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (marked_findings, suppressed_pattern_hits)."""
    marked: list[dict[str, Any]] = []
    hits: list[dict[str, Any]] = []
    for finding in findings:
        if finding.get("status") == "suppressed":
            marked.append(finding)
            continue
        pattern = find_match(store, finding)
        if pattern:
            marked.append(mark_suppressed(finding, pattern))
            hits.append(
                {
                    "pattern_id": pattern.get("id"),
                    "rule_id": finding.get("rule_id"),
                    "fingerprint_hint": finding.get("fingerprint"),
                }
            )
        else:
            marked.append(finding)
    return marked, hits


def apply_patterns_path(
    findings: list[dict[str, Any]],
    patterns_path: Path | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load patterns from path (if present) and apply. Missing file → no-op."""
    if not patterns_path or not Path(patterns_path).exists():
        return findings, []
    store = load_patterns(Path(patterns_path))
    return apply_patterns(findings, store)


def _next_id(store: dict[str, Any]) -> str:
    n = 1
    existing = {p.get("id") for p in store.get("patterns") or []}
    while f"fp-{n:04d}" in existing:
        n += 1
    return f"fp-{n:04d}"


def add_pattern(store: dict[str, Any], pattern: dict[str, Any]) -> dict[str, Any]:
    item = dict(pattern)
    item.setdefault("id", _next_id(store))
    item.setdefault("created_at", utc_now())
    item.setdefault("match", "selector+rule+route")
    if item["match"] not in MATCH_MODES:
        raise ValueError(f"invalid match mode: {item['match']}")
    store.setdefault("patterns", []).append(item)
    return item


def pattern_from_bug(bug: dict[str, Any], *, match: str = "selector+rule+route") -> dict[str, Any]:
    f = finding_fields(bug)
    effective = match
    if match in ("exact", "selector+rule+route") and not f["selector"]:
        effective = "rule+route"
    if match == "digest" and not f["digest"]:
        effective = "rule+route"
    return {
        "modality": f["modality"],
        "category": f["category"],
        "rule_id": f["rule_id"],
        "route": f["route"],
        "viewport": f["viewport"] if effective == "exact" else None,
        "selector_pattern": f["selector"] if effective in ("exact", "selector+rule+route") else None,
        "core_assertion_digest": f["digest"] if effective == "digest" else None,
        "reason": bug.get("reject_reason")
        or bug.get("reason")
        or (bug.get("evidence") or {}).get("reject_reason")
        or "absorbed-from-rejected",
        "source_bug_id": bug.get("id"),
        "match": effective,
    }


def agents_snippet(store: dict[str, Any]) -> str:
    patterns = store.get("patterns") or []
    lines = [
        "# iterative-bug-hunter FP whitelist (generated)",
        "",
        "Do **not** auto-edit this project's AGENTS.md from this snippet without review.",
        "",
        f"- Patterns file: `.bug-hunter/fp_patterns.json` ({len(patterns)} pattern(s))",
        "- Findings matching a pattern are marked `status: suppressed` and must not",
        "  be treated as new confirmed bugs in the same hunt session.",
        "- Re-check `fp_feedback.py list` before expanding suppressions.",
        "",
    ]
    if patterns:
        lines.append("## Known patterns")
        lines.append("")
        for p in patterns:
            sel = p.get("selector_pattern") or "-"
            lines.append(
                f"- `{p.get('id')}` — {p.get('rule_id')} @ `{p.get('route')}` "
                f"[{p.get('match')}] selector={sel} — {p.get('reason') or ''}"
            )
        lines.append("")
    return "\n".join(lines)


def remove_pattern(store: dict[str, Any], pattern_id: str) -> bool:
    before = len(store.get("patterns") or [])
    store["patterns"] = [p for p in (store.get("patterns") or []) if p.get("id") != pattern_id]
    return len(store["patterns"]) != before


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="FP pattern library")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name in ("list", "check"):
        sp = sub.add_parser(name)
        sp.add_argument("--root", default=".")
        sp.add_argument("--patterns", dest="patterns", default=None)
        if name == "check":
            sp.add_argument("--finding", required=True)

    absorb = sub.add_parser("absorb")
    absorb.add_argument("--root", default=".")
    absorb.add_argument("--patterns", dest="patterns", default=None)
    absorb.add_argument("--bug", required=True)
    absorb.add_argument("--match", default="selector+rule+route")

    add = sub.add_parser("add")
    add.add_argument("--root", default=".")
    add.add_argument("--patterns", dest="patterns", default=None)
    add.add_argument("--rule-id", required=True)
    add.add_argument("--route", required=True)
    add.add_argument("--selector", default=None)
    add.add_argument("--modality", default="web-visual")
    add.add_argument("--category", default=None)
    add.add_argument("--reason", default="manual-whitelist")
    add.add_argument("--match", default="selector+rule+route")
    add.add_argument("--viewport", default=None)
    add.add_argument("--digest", default=None)

    rm = sub.add_parser("remove")
    rm.add_argument("--root", default=".")
    rm.add_argument("--patterns", dest="patterns", default=None)
    rm.add_argument("--id", required=True)

    snip = sub.add_parser("agents-snippet")
    snip.add_argument("--root", default=".")
    snip.add_argument("--patterns", dest="patterns", default=None)
    snip.add_argument("--out", default="AGENTS.bug-hunter.snippet.md")

    apply_p = sub.add_parser("apply")
    apply_p.add_argument("--root", default=".")
    apply_p.add_argument("--patterns", dest="patterns", default=None)
    apply_p.add_argument("--findings", required=True, help="findings JSON file")
    apply_p.add_argument("--out", default=None)

    return p.parse_args(argv)


def _path_from_args(args: argparse.Namespace) -> Path:
    if getattr(args, "patterns", None):
        return Path(args.patterns)
    return default_patterns_path(Path(args.root).resolve())


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    path = _path_from_args(args)
    root = Path(args.root).resolve()

    if args.cmd == "list":
        store = load_patterns(path)
        print(json.dumps(store, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "check":
        store = load_patterns(path)
        finding = load_json(Path(args.finding))
        pattern = find_match(store, finding)
        print(json.dumps({"matched": bool(pattern), "pattern": pattern}, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "absorb":
        bug = load_json(Path(args.bug))
        lock = path.parent / ".lock"
        fd = acquire_lock(lock)
        try:
            store = load_patterns(path)
            item = add_pattern(store, pattern_from_bug(bug, match=args.match))
            save_patterns(path, store)
        finally:
            release_lock(fd, lock)
        print(json.dumps(item, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "add":
        pattern = {
            "modality": args.modality,
            "category": args.category,
            "rule_id": args.rule_id,
            "route": args.route,
            "viewport": args.viewport,
            "selector_pattern": args.selector,
            "core_assertion_digest": args.digest,
            "reason": args.reason,
            "source_bug_id": None,
            "match": args.match,
        }
        lock = path.parent / ".lock"
        fd = acquire_lock(lock)
        try:
            store = load_patterns(path)
            item = add_pattern(store, pattern)
            save_patterns(path, store)
        finally:
            release_lock(fd, lock)
        print(json.dumps(item, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "remove":
        lock = path.parent / ".lock"
        fd = acquire_lock(lock)
        try:
            store = load_patterns(path)
            ok = remove_pattern(store, args.id)
            if ok:
                save_patterns(path, store)
        finally:
            release_lock(fd, lock)
        print(json.dumps({"removed": ok, "id": args.id}, ensure_ascii=False, indent=2))
        return 0 if ok else 1

    if args.cmd == "agents-snippet":
        store = load_patterns(path)
        text = agents_snippet(store)
        out = Path(args.out)
        if not out.is_absolute():
            out = root / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(json.dumps({"out": str(out), "patterns": len(store.get("patterns") or [])}, ensure_ascii=False))
        return 0

    if args.cmd == "apply":
        store = load_patterns(path)
        payload = load_json(Path(args.findings))
        findings = payload if isinstance(payload, list) else payload.get("findings", [])
        marked, hits = apply_patterns(findings, store)
        out = {"findings": marked, "suppressed_hits": hits, "suppressed_count": len(hits)}
        if args.out:
            save_json(Path(args.out), out)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
