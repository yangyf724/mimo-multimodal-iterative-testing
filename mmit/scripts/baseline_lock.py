#!/usr/bin/env python3
"""Baseline screenshot lock / verify (Phase 3)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def relative_files(baseline_dir: Path) -> list[Path]:
    if not baseline_dir.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(baseline_dir.rglob("*")):
        if p.is_file() and p.name != "lock.json" and p.suffix.lower() == ".png":
            out.append(p)
    return out


def snapshot(baseline_dir: Path, lock_path: Path) -> dict[str, Any]:
    files = relative_files(baseline_dir)
    mapping = {str(p.relative_to(baseline_dir)).replace("\\", "/"): sha256_file(p) for p in files}
    data = {
        "version": 1,
        "algorithm": "sha256",
        "created_at": utc_now(),
        "files": mapping,
    }
    save_json(lock_path, data)
    return {"lock": str(lock_path), "count": len(mapping), "files": mapping}


def load_approvals(path: Path | None) -> list[dict[str, Any]]:
    if not path or not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _approval_allows(
    approvals: list[dict[str, Any]],
    rel: str,
    current_hash: str | None,
) -> bool:
    """Approve drift only when the approval matches this file AND current sha256.

    Spec §4.2: intentional change requires approvals.jsonl entry whose sha256
    equals the **current** file hash. Path/route matching alone is not enough —
    otherwise one historical approval permanently unlocks the baseline.
    """
    if not current_hash:
        return False
    stem = Path(rel).stem
    for row in approvals:
        if row.get("sha256") != current_hash:
            continue
        # Same hash — still require identity of the file/route when provided.
        if row.get("file") == rel or row.get("path") == rel:
            return True
        r = (row.get("route") or "").strip()
        v = (row.get("viewport") or "").strip()
        if r and v:
            slug_route = r.strip("/").replace("/", "-") or "home"
            if stem == f"{slug_route}__{v}" or stem.endswith(f"__{v}"):
                return True
        if not r and not v and not row.get("file") and not row.get("path"):
            # hash-only approval applies to whatever file currently has that hash
            return True
    return False


def verify(
    baseline_dir: Path,
    lock_path: Path,
    *,
    approvals_path: Path | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    if not lock_path.exists():
        return {
            "ok": False,
            "status": "no-lock",
            "detail": f"lock missing: {lock_path}",
            "drifted": [],
            "missing": [],
            "unlocked_files": [],
        }
    lock = load_json(lock_path)
    locked: dict[str, str] = lock.get("files") or {}
    approvals = load_approvals(approvals_path)

    drifted: list[dict[str, Any]] = []
    missing: list[str] = []
    ok_files = 0
    for rel, expected in locked.items():
        path = baseline_dir / rel
        if not path.exists():
            missing.append(rel)
            continue
        current = sha256_file(path)
        if current == expected:
            ok_files += 1
            continue
        allowed = _approval_allows(approvals, rel, current)
        if allowed:
            ok_files += 1
            continue
        drifted.append({"file": rel, "expected": expected, "current": current})

    unlocked = []
    locked_keys = set(locked)
    for path in relative_files(baseline_dir):
        rel = str(path.relative_to(baseline_dir)).replace("\\", "/")
        if rel not in locked_keys:
            unlocked.append(rel)

    ok = not drifted and not missing and (not strict or not unlocked)
    status = "ok" if ok else "drift"
    if missing and not drifted:
        status = "missing"
    if strict and unlocked and not drifted and not missing:
        status = "unlocked-strict"
        ok = False
    return {
        "ok": ok,
        "status": status,
        "ok_files": ok_files,
        "drifted": drifted,
        "missing": missing,
        "unlocked_files": unlocked,
        "approvals_count": len(approvals),
    }


def default_paths(root: Path) -> tuple[Path, Path, Path]:
    bh = root / ".mmit" / "baselines"
    return bh, bh / "lock.json", bh / "approvals.jsonl"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Baseline lock snapshot/verify")
    p.add_argument("--root", default=None, help="project root (uses .mmit/baselines)")
    p.add_argument("--baseline-dir", default=None)
    p.add_argument("--lock", default=None)
    p.add_argument("--approvals", default=None)
    p.add_argument("--strict", action="store_true")
    sub = p.add_mutually_exclusive_group(required=True)
    sub.add_argument("--snapshot", action="store_true")
    sub.add_argument("--verify", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.baseline_dir and args.lock:
        baseline_dir = Path(args.baseline_dir).resolve()
        lock_path = Path(args.lock).resolve()
        approvals = Path(args.approvals).resolve() if args.approvals else baseline_dir / "approvals.jsonl"
    elif args.root:
        baseline_dir, lock_path, approvals = default_paths(Path(args.root).resolve())
        if args.approvals:
            approvals = Path(args.approvals)
    else:
        print(json.dumps({"error": "pass --root or --baseline-dir+--lock"}, ensure_ascii=False))
        return 2

    if args.snapshot:
        if not baseline_dir.is_dir():
            print(json.dumps({"error": f"baseline dir missing: {baseline_dir}"}, ensure_ascii=False))
            return 1
        result = snapshot(baseline_dir, lock_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    result = verify(
        baseline_dir,
        lock_path,
        approvals_path=approvals,
        strict=args.strict,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("status") == "no-lock":
        return 2
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
