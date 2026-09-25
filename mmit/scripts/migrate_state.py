#!/usr/bin/env python3
"""Migrate legacy hunter/test state into unified .mmit/state.json."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from init_state import build_state, merge_state  # noqa: E402
from mmit_lib import ensure_mit, read_json, save_state, utc_now, write_json  # noqa: E402


def map_hunter_state(old: dict[str, Any]) -> dict[str, Any]:
    state = build_state(depth="hunt", mode=old.get("mode") or "hunt-and-fix")
    state["created_at"] = old.get("created_at") or state["created_at"]
    mapped_keys = set()
    for key in (
        "run_count",
        "quiet_streak",
        "last_run_id",
        "last_strategy_set",
        "last_round",
        "converged",
        "phase",
        "modalities_enabled",
        "surfaces",
        "visual_oracle",
        "ci",
        "export",
        "fp",
        "fix_router",
        "budget",
        "stats",
        "blind_spots",
        "mode",
    ):
        if key in old and old[key] is not None:
            state[key] = old[key]
            mapped_keys.add(key)
    if isinstance(old.get("convergence"), dict):
        state["convergence"] = old["convergence"]
        mapped_keys.add("convergence")
    if "run_count" in old:
        state["round"] = old.get("run_count") or 0
        mapped_keys.add("round")
    state["_mapped_keys"] = sorted(mapped_keys)
    state["migrated_from"] = {"kind": "mmit-hunter", "keys": sorted(old.keys())}
    return state


def map_test_state(old: dict[str, Any]) -> dict[str, Any]:
    state = build_state(
        depth="release",
        mode=old.get("mode") or "test-and-fix",
        prod_access=old.get("prod_access") or "none",
    )
    state["created_at"] = old.get("created_at") or state["created_at"]
    mapped_keys = set()
    for key in (
        "quiet_streak",
        "decision",
        "blinds",
        "blind_spots",
        "rc_n",
        "rc_sha",
        "matrix_rev",
        "open_defects",
        "signals",
        "prod_access",
        "prod_test_state",
        "budget",
        "mode",
        "round",
    ):
        if key in old and old[key] is not None:
            state[key] = old[key]
            mapped_keys.add(key)
    for key in ("surfaces", "visual_oracle", "modalities_enabled", "fix_router"):
        if key in old and old[key] is not None:
            state[key] = old[key]
            mapped_keys.add(key)
    state["_mapped_keys"] = sorted(mapped_keys)
    state["migrated_from"] = {"kind": "mmit-test", "keys": sorted(old.keys())}
    return state


def detect_kind(old: dict[str, Any]) -> str:
    skill = str(old.get("skill") or "")
    if "test" in skill or "rc_n" in old or "matrix_rev" in old:
        return "mmit-test"
    if "hunter" in skill or "surfaces" in old or "modalities_enabled" in old:
        return "mmit-hunter"
    if "version" in old and old.get("skill") == "mmit":
        return "mmit"
    return "unknown"


def migrate_one(src: Path, root: Path, force: bool = False) -> dict[str, Any]:
    """Map a single legacy file to a unified state dict (does not save)."""
    old = read_json(src)
    if not isinstance(old, dict):
        raise SystemExit(f"invalid state json: {src}")
    kind = detect_kind(old)
    if kind == "mmit" and not force:
        state = dict(old)
        state.setdefault("migrated_from", {"kind": "mmit", "path": str(src)})
    elif kind == "mmit-test":
        state = map_test_state(old)
    elif kind == "mmit-hunter":
        state = map_hunter_state(old)
    else:
        state = map_hunter_state(old)
        state["migrated_from"] = {"kind": kind, "path": str(src)}
    state["migrated_at"] = utc_now()
    return state


def merge_migrated(base: dict[str, Any], incoming: dict[str, Any], kind: str) -> dict[str, Any]:
    """Merge only keys the source actually provided; never clobber with defaults."""
    out = dict(base or {})
    mapped = set(incoming.get("_mapped_keys") or [])
    src_meta = out.get("migrated_from")
    for key, val in incoming.items():
        if key in {"migrated_from", "migrated_at", "_mapped_keys"}:
            continue
        if key not in mapped:
            # default from build_state — only fill if base missing
            if key not in out or out.get(key) is None:
                out[key] = val
            continue
        if val is None:
            out.setdefault(key, val)
            continue
        if key == "budget" and isinstance(val, dict) and isinstance(out.get("budget"), dict):
            merged = dict(out["budget"])
            merged.update(val)
            out["budget"] = merged
            continue
        if key == "visual_oracle" and isinstance(val, dict) and isinstance(out.get("visual_oracle"), dict):
            merged = dict(out["visual_oracle"])
            merged.update(val)
            out["visual_oracle"] = merged
            continue
        if key == "open_defects" and isinstance(val, dict) and isinstance(out.get("open_defects"), dict):
            merged = dict(out["open_defects"])
            merged.update({k: v for k, v in val.items() if v})
            out["open_defects"] = merged
            continue
        if key == "surfaces" and isinstance(val, dict) and isinstance(out.get("surfaces"), dict):
            out["surfaces"] = merge_state(out["surfaces"], val)
            continue
        out[key] = val
    kinds = []
    if isinstance(src_meta, dict):
        if isinstance(src_meta.get("kind"), str):
            kinds.append(src_meta)
        kinds.extend(src_meta.get("sources") or [])
    kinds.append(incoming.get("migrated_from") or {"kind": kind})
    out["migrated_from"] = {"kind": "mmit-merged", "sources": kinds}
    out["migrated_at"] = utc_now()
    out.pop("_mapped_keys", None)
    return out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Migrate .bug-hunter/ or .mmit/ state into .mmit/")
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--from-hunter", action="store_true", help="migrate .bug-hunter/state.json")
    p.add_argument("--from-test", action="store_true", help="migrate .mmit/state.json")
    p.add_argument("--src", type=Path, default=None, help="explicit state.json path")
    p.add_argument("--force", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    ensure_mit(root)
    sources: list[Path] = []
    if args.src:
        sources.append(args.src)
    else:
        if args.from_hunter or not args.from_test:
            hp = root / ".bug-hunter" / "state.json"
            if hp.exists():
                sources.append(hp)
        if args.from_test or not args.from_hunter:
            tp = root / ".mit" / "state.json"
            if tp.exists():
                sources.append(tp)
    if not sources:
        print("no legacy state.json found (.bug-hunter/ or .mmit/)")
        return 1

    order = sorted(sources, key=lambda p: (0 if ".mit" in p.parts else 1, p.as_posix()))
    state: dict[str, Any] = {}
    for src in order:
        mapped = migrate_one(src, root, force=args.force)
        kind = detect_kind(read_json(src) or {})
        state = merge_migrated(state, mapped, kind)
        print(f"mapped: {src}")
    if not state:
        print("nothing mapped")
        return 1
    save_state(root, state)
    dest = root / ".mmit" / "state.json"
    print(f"migrated: {len(order)} source(s) -> {dest}")
    write_json(
        root / ".mmit" / "migrate_audit.json",
        {
            "sources": [str(s) for s in order],
            "to": str(dest),
            "at": utc_now(),
            "final_kind": detect_kind(state),
            "migrated_from": state.get("migrated_from"),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
