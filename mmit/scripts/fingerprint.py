#!/usr/bin/env python3
"""Fingerprint findings for mmit (DESIGN §3.2)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

ALLOWED_MODALITIES = {"code", "web-visual", "canvas"}

LOCK_RETRY = 3
LOCK_SLEEP_S = 0.05


def acquire_lock(lock_path: Path) -> int:
    import os
    import time
    from datetime import datetime, timezone

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    last_err: Exception | None = None
    for attempt in range(LOCK_RETRY):
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            os.write(fd, f"{os.getpid()}\n{stamp}\n".encode("utf-8"))
            return fd
        except FileExistsError as e:
            last_err = e
            if attempt < LOCK_RETRY - 1:
                time.sleep(LOCK_SLEEP_S * (attempt + 1))
                continue
            raise RuntimeError(
                f"lock exists: {lock_path}. Another session may be writing fingerprints.json."
            ) from e
    raise RuntimeError(f"lock acquire failed: {last_err}")


def release_lock(fd: int, lock_path: Path) -> None:
    import os

    try:
        os.close(fd)
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass

_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9/:._\-#@\[\]=]+")


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").strip().lower()
    text = _WS_RE.sub(" ", text)
    text = _NON_ALNUM_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def normalize_route_or_file(value: str) -> str:
    text = (value or "").strip().replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    if len(text) > 1:
        text = text.rstrip("/")
    return normalize_text(text)


def normalize_viewport(value: str) -> str:
    text = (value or "").strip().lower().replace(" ", "")
    text = text.replace("*", "x").replace("×", "x")
    m = re.match(r"^(\d+)x(\d+)$", text)
    if m:
        return f"{int(m.group(1))}x{int(m.group(2))}"
    return text or "unknown"


def normalize_element_ref(value: str) -> str:
    return normalize_text(value) or "-"


def assertion_digest(statement: str, *, max_len: int = 120) -> str:
    text = normalize_text(statement)
    if len(text) > max_len:
        text = text[:max_len]
    return text or "-"


def compute_fingerprint(
    *,
    modality: str,
    route_or_file: str,
    viewport: str,
    category: str,
    element_ref: str,
    assertion: str,
) -> str:
    if modality not in ALLOWED_MODALITIES:
        raise ValueError(f"modality must be one of {sorted(ALLOWED_MODALITIES)}, got {modality!r}")
    parts = [
        modality,
        normalize_route_or_file(route_or_file),
        normalize_viewport(viewport),
        normalize_text(category) or "-",
        normalize_element_ref(element_ref),
        assertion_digest(assertion),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def fingerprint_from_finding(finding: dict[str, Any]) -> str:
    loc = finding.get("location") or {}
    route = loc.get("route") or loc.get("file") or finding.get("route_or_file") or ""
    viewport = loc.get("viewport") or finding.get("viewport") or "n/a"
    element = loc.get("selector") or loc.get("canvas_object_id") or loc.get("symbol") or finding.get("element_ref") or ""
    assertion = (
        finding.get("core_assertion_digest")
        or finding.get("statement")
        or finding.get("assertion")
        or ""
    )
    # Coarse rule identity only — avoid folding exact pixel metrics into the
    # hash so 1px capture noise does not mint a new fingerprint.
    rule_id = finding.get("rule_id") or (finding.get("evidence") or {}).get("rule_id") or ""
    if rule_id:
        assertion = f"{rule_id}|{normalize_text(assertion)[:80]}"
    return compute_fingerprint(
        modality=finding["modality"],
        route_or_file=str(route),
        viewport=str(viewport),
        category=str(finding.get("category") or "-"),
        element_ref=str(element),
        assertion=str(assertion),
    )


def load_fingerprints(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "entries": {}}
    with path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    data.setdefault("entries", {})
    return data


def save_fingerprints(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def register_fingerprints(
    findings: list[dict[str, Any]],
    *,
    fp_path: Path,
    run_id: str,
    now: str,
) -> dict[str, Any]:
    """Register findings; returns {new: [...], known: [...]} with fingerprints attached."""
    lock_path = fp_path.parent / ".lock"
    fd = acquire_lock(lock_path)
    try:
        store = load_fingerprints(fp_path)
        entries = store["entries"]
        new_items: list[dict[str, Any]] = []
        known_items: list[dict[str, Any]] = []

        for finding in findings:
            fp = finding.get("fingerprint") or fingerprint_from_finding(finding)
            item = dict(finding)
            item["fingerprint"] = fp
            if fp in entries:
                entry = entries[fp]
                entry["last_seen"] = now
                entry["runs"] = entry.get("runs", [])
                if run_id and run_id not in entry["runs"]:
                    entry["runs"].append(run_id)
                entry["status"] = finding.get("status") or entry.get("status") or "candidate"
                known_items.append(item)
            else:
                entries[fp] = {
                    "fingerprint": fp,
                    "modality": item.get("modality"),
                    "category": item.get("category"),
                    "status": item.get("status") or "candidate",
                    "title": item.get("title"),
                    "rule_id": item.get("rule_id")
                    or (item.get("evidence") or {}).get("rule_id"),
                    "route_or_file": (item.get("location") or {}).get("route")
                    or (item.get("location") or {}).get("file")
                    or "",
                    "viewport": (item.get("location") or {}).get("viewport") or "",
                    "first_seen": now,
                    "last_seen": now,
                    "runs": [run_id] if run_id else [],
                }
                new_items.append(item)

        store["updated_at"] = now
        save_fingerprints(fp_path, store)
    finally:
        release_lock(fd, lock_path)
    return {
        "new": new_items,
        "known": known_items,
        "new_count": len(new_items),
        "known_count": len(known_items),
        "duplicate_rate": (
            len(known_items) / len(findings) if findings else 0.0
        ),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compute or register finding fingerprints")
    p.add_argument("--root", default=".", help="project root containing .mmit/")
    p.add_argument(
        "--compute",
        action="store_true",
        help="read findings JSON from stdin and print fingerprints",
    )
    p.add_argument(
        "--register",
        action="store_true",
        help="register findings JSON from stdin into fingerprints.json",
    )
    p.add_argument("--run-id", default="", help="run id for register mode")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()
    payload = json.load(sys.stdin)

    if args.compute:
        findings = payload if isinstance(payload, list) else payload.get("findings", [])
        out = []
        for f in findings:
            fp = fingerprint_from_finding(f)
            out.append({"fingerprint": fp, "title": f.get("title"), "modality": f.get("modality")})
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if args.register:
        findings = payload if isinstance(payload, list) else payload.get("findings", [])
        fp_path = root / ".mmit" / "fingerprints.json"
        result = register_fingerprints(findings, fp_path=fp_path, run_id=args.run_id, now=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    # default: compute one finding from flags-style JSON on stdin
    if isinstance(payload, dict) and "modality" in payload:
        print(fingerprint_from_finding(payload))
        return 0
    print(json.dumps({"error": "pass --compute or --register, or a single finding object"}, ensure_ascii=False), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
