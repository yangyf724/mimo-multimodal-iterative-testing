#!/usr/bin/env python3
"""Bootstrap .bug-hunter state for mmit-hunter (Phase 0)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_STATE: dict[str, Any] = {
    "version": 1,
    "skill": "mmit-hunter",
    "phase": 3,
    "mode": "hunt-and-fix",
    "created_at": None,
    "updated_at": None,
    "run_count": 0,
    "quiet_streak": 0,
    "last_run_id": None,
    "last_strategy_set": [],
    "modalities_enabled": ["code", "web-visual"],
    "surfaces": {
        "web": {
            "base_url": "http://127.0.0.1:5173",
            "routes": ["/", "/about"],
            "viewports": ["375x812", "1440x900"],
            "auth": {"mode": "none"},
            "degrade_level": "L1",
            "route_discovery": {
                "enabled": True,
                "max_routes": 12,
                "sources": ["seed", "package.json", "sitemap", "html-links"],
                "last_run": None,
            },
        },
        "canvas": {"kind": "scene-json", "items": [], "export_target": None},
    },
    "ci": {
        "axe_backend": "auto",
        "baseline_lock": True,
        "fail_on_axe": False,
    },
    "export": {
        "path": "export/report.json",
        "schema_version": 1,
    },
    "fp": {
        "patterns_path": "fp_patterns.json",
        "default_match": "selector+rule+route",
    },
    "visual_oracle": {
        "min_contrast": 4.5,
        "large_text_min_contrast": 3.0,
        "touch_target_px": 44,
        "overflow_epsilon_px": 2,
        "font_too_small_px": 12,
        "allow_subjective": False,
        "fp_downweight_threshold": 0.7,
        "fp_calibration_runs": 1,
        "overlap_ratio": 0.2,
        "line_height_min_ratio": 1.2,
        "visual_diff_threshold": 0.01,
        "safe_inset_pct": 5.0,
        "z_order_min_coverage": 0.98,
        "low_res_max_ratio": 2.0,
        "aspect_distort_tol": 0.02,
        "ux_empty_state_attr": "data-empty-state",
        "vlm_min_agreement": 2,
    },
    "budget": {
        "max_runs": 20,
        "max_captures_per_run": 80,
        "max_wall_minutes": 180,
        "max_fix_failures": 5,
        "max_fixes_per_run": 5,
        "min_severity_for_fix": "medium",
        "max_local_attempts": 3,
        "lite_max_attempts": 2,
        "max_compose_escalations": 2,
        "max_local_edit_sites": 3,
        "max_lite_edit_sites": 6,
    },
    "fix_router": {
        "enabled": True,
        "escalations_used": 0,
        "max_compose_escalations": 2,
        "by_route": {
            "local": 0,
            "lite": 0,
            "compose": 0,
            "deferred": 0,
        },
    },
    "convergence": {
        "quiet_streak": 0,
        "required_quiet_streak": 2,
    },
    "concurrency": {
        "writer": "main-agent-only",
        "lock_file": ".bug-hunter/.lock",
        "subagent_write_roots": [
            "runs/*/captures/shard-*",
            "runs/*/findings/raw",
        ],
    },
    "stats": {
        "confirmed_total": 0,
        "rejected_total": 0,
        "fixed_total": 0,
        "deferred_total": 0,
        "findings_total": 0,
        "fp_rate_by_strategy": {},
    },
    "blind_spots": [],
    "last_round": None,
}

BUG_DIRS = (
    "bugs/confirmed",
    "bugs/fixed",
    "bugs/rejected",
    "bugs/deferred",
    "runs",
    "captures",
    "baselines/web",
)

LOCK_RETRY = 3


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class LockError(RuntimeError):
    pass


def acquire_lock(lock_path: Path) -> int:
    import time

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(LOCK_RETRY):
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()}\n{utc_now()}\n".encode("utf-8"))
            return fd
        except FileExistsError:
            if attempt == LOCK_RETRY - 1:
                raise LockError(
                    f"lock exists: {lock_path}. Another session may be running."
                ) from None
            time.sleep(0.05 * (attempt + 1))
            continue
    raise LockError("unreachable")


def release_lock(fd: int, lock_path: Path) -> None:
    try:
        os.close(fd)
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


def ensure_tree(root: Path) -> None:
    bh = root / ".bug-hunter"
    bh.mkdir(parents=True, exist_ok=True)
    for rel in BUG_DIRS:
        (bh / rel).mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")
    os.replace(tmp, path)


def merge_state(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge_state(out[key], value)
        else:
            out[key] = value
    return out


def init_state(
    root: Path,
    *,
    routes: list[str] | None = None,
    viewports: list[str] | None = None,
    base_url: str | None = None,
    mode: str | None = None,
    modalities: list[str] | None = None,
    quiet_streak: int | None = None,
    force: bool = False,
    canvas_items: list[str] | None = None,
    export_target: str | None = None,
) -> dict[str, Any]:
    ensure_tree(root)
    state_path = root / ".bug-hunter" / "state.json"
    fp_path = root / ".bug-hunter" / "fingerprints.json"
    lock_path = root / ".bug-hunter" / ".lock"

    fd = acquire_lock(lock_path)
    try:
        # Existence check must be under the lock to avoid concurrent first-init overwrite.
        if state_path.exists() and not force:
            raise FileExistsError(
                f"{state_path} already exists. Use --force to overwrite or resume via existing file."
            )

        now = utc_now()
        state = json.loads(json.dumps(DEFAULT_STATE))
        state["created_at"] = now
        state["updated_at"] = now

        patch: dict[str, Any] = {}
        web: dict[str, Any] = {}
        if routes:
            web["routes"] = routes
        if viewports:
            web["viewports"] = viewports
        if base_url:
            web["base_url"] = base_url
        if web:
            patch["surfaces"] = {"web": web}
        if mode:
            patch["mode"] = mode
        if modalities:
            patch["modalities_enabled"] = modalities
        if quiet_streak is not None:
            patch["convergence"] = {"quiet_streak": quiet_streak, "required_quiet_streak": 2}
            patch["quiet_streak"] = quiet_streak

        canvas_surface: dict[str, Any] = {}
        if canvas_items:
            items = []
            for path_str in canvas_items:
                pth = Path(path_str)
                items.append(
                    {
                        "id": pth.stem.replace(".scene", ""),
                        "kind": "scene-json",
                        "source": str(pth),
                    }
                )
            canvas_surface["items"] = items
            modalities_set = set(patch.get("modalities_enabled") or state.get("modalities_enabled") or [])
            modalities_set.add("canvas")
            patch["modalities_enabled"] = sorted(modalities_set)
        if export_target:
            canvas_surface["export_target"] = export_target
        if canvas_surface:
            patch["surfaces"] = merge_state(
                patch.get("surfaces") or {},
                {"canvas": canvas_surface},
            )

        if patch:
            state = merge_state(state, patch)

        save_json(state_path, state)
        if not fp_path.exists() or force:
            save_json(
                fp_path,
                {
                    "version": 1,
                    "updated_at": now,
                    "entries": {},
                },
            )
    finally:
        release_lock(fd, lock_path)
    return state


def resume_summary(root: Path) -> dict[str, Any]:
    state_path = root / ".bug-hunter" / "state.json"
    if not state_path.exists():
        return {"ok": False, "error": "state.json missing; run init_state first"}
    state = load_json(state_path)
    return {
        "ok": True,
        "run_count": state.get("run_count", 0),
        "quiet_streak": state.get("convergence", {}).get("quiet_streak", state.get("quiet_streak", 0)),
        "required_quiet_streak": state.get("convergence", {}).get("required_quiet_streak", 2),
        "degrade_level": state.get("surfaces", {}).get("web", {}).get("degrade_level", "L1"),
        "modalities_enabled": state.get("modalities_enabled", []),
        "last_strategy_set": state.get("last_strategy_set", []),
        "mode": state.get("mode"),
        "budget": state.get("budget") or {},
        "fix_router": state.get("fix_router") or {},
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Initialize mmit-hunter state")
    p.add_argument("--root", default=".", help="project root (default: cwd)")
    p.add_argument("--routes", nargs="*", help="web routes, e.g. / /about")
    p.add_argument("--viewports", nargs="*", help="viewports, e.g. 375x812 1440x900")
    p.add_argument("--base-url", dest="base_url", help="web base url")
    p.add_argument("--mode", choices=["hunt-only", "hunt-and-fix"], help="run mode")
    p.add_argument(
        "--modalities",
        nargs="*",
        choices=["code", "web-visual", "canvas"],
        help="enabled modalities",
    )
    p.add_argument("--quiet-streak", type=int, help="resume quiet_streak value")
    p.add_argument("--force", action="store_true", help="overwrite existing state.json")
    p.add_argument(
        "--resume-summary",
        action="store_true",
        help="print resume summary JSON from existing state.json",
    )
    p.add_argument(
        "--canvas-item",
        action="append",
        dest="canvas_items",
        help="repeatable path to canvas scene json / item file",
    )
    p.add_argument("--export-target", dest="export_target", help="canvas export target WxH")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()
    try:
        if args.resume_summary:
            print(json.dumps(resume_summary(root), ensure_ascii=False, indent=2))
            return 0
        state = init_state(
            root,
            routes=args.routes,
            viewports=args.viewports,
            base_url=args.base_url,
            mode=args.mode,
            modalities=args.modalities,
            quiet_streak=args.quiet_streak,
            force=args.force,
            canvas_items=args.canvas_items,
            export_target=args.export_target,
        )
        print(json.dumps({"ok": True, "root": str(root), "state": state}, ensure_ascii=False, indent=2))
        return 0
    except (FileExistsError, LockError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
