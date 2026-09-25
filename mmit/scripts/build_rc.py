#!/usr/bin/env python3
"""Build release candidate metadata (RC) for MMIT-Test."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mmit_lib import ensure_mit, ensure_tests, load_state, save_state, sha256_file, utc_now, write_json  # noqa: E402


def hash_tree(root: Path, exclude: set[str] | None = None) -> str:
    exclude = exclude or {".git", ".mmit", ".mit", ".mmit", "node_modules", "__pycache__", ".venv", ".worktrees"}
    h = hashlib.sha256()
    files: list[Path] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in exclude for part in rel.parts):
            continue
        files.append(p)
    for p in files:
        rel = p.relative_to(root).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def git_head(root: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def build_rc(root: Path, rc_ref: str | None = None) -> dict[str, Any]:
    state = load_state(root)
    rc_n = int(state.get("rc_n") or 0) + 1
    rc_sha = hash_tree(root)
    meta = {
        "rc_id": f"RC-{rc_n}",
        "rc_n": rc_n,
        "rc_sha": rc_sha,
        "rc_ref": rc_ref or git_head(root) or "working-tree",
        "built_at": utc_now(),
        "root": str(root.resolve()),
        "matrix_rev": state.get("matrix_rev"),
        "git_head": git_head(root),
    }
    return meta


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build RC metadata and lock rc_sha")
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--rc-ref", default=None)
    p.add_argument("--out", type=Path, default=None)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    tests = ensure_tests(root)
    mit = ensure_mit(root)
    artifacts = tests / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    try:
        meta = build_rc(root, args.rc_ref)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    out = args.out or (artifacts / f"{meta['rc_id']}.meta.json")
    write_json(out, meta)

    state = load_state(root)
    state["rc_n"] = meta["rc_n"]
    state["rc_sha"] = meta["rc_sha"]
    state["round"] = int(state.get("round") or 0) + 1
    save_state(root, state)

    runs_dir = tests / "runs" / meta["rc_id"]
    runs_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("captures", "findings", "probes", "logs"):
        (runs_dir / sub).mkdir(exist_ok=True)

    print(f"RC built: {meta['rc_id']} rc_sha={meta['rc_sha'][:12]}… -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
