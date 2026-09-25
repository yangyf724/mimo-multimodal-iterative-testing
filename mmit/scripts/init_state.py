#!/usr/bin/env python3
"""Initialize .mmit state for unified MMIT skill (flat union of hunt + release)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mmit_lib import (  # noqa: E402
    DEPTHS,
    PROD_ACCESS,
    acquire_lock,
    ensure_hunts,
    ensure_mit,
    ensure_tests,
    read_json,
    release_lock,
    save_state,
    utc_now,
    write_json,
)

STATE_VERSION = 2


class LockError(RuntimeError):
    pass


DEFAULT_STATE: dict[str, Any] = {
    "version": STATE_VERSION,
    "skill": "mmit",
    "depth": "hunt",
    "phase": 3,
    "mode": "hunt-and-fix",
    "created_at": None,
    "updated_at": None,
    "run_count": 0,
    "round": 0,
    "quiet_streak": 0,
    "convergence": {"quiet_streak": 0, "required_quiet_streak": 2},
    "last_run_id": None,
    "last_strategy_set": [],
    "last_round": None,
    "converged": False,
    "resume_summary": None,
    "decision": "in_progress",
    "blind_spots": [],
    "blinds": [],
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
    "fix_router": {
        "enabled": True,
        "escalations_used": 0,
        "max_compose_escalations": 2,
        "by_route": {"local": 0, "lite": 0, "compose": 0, "deferred": 0},
    },
    "stats": {},
    "rc_n": 0,
    "rc_sha": None,
    "matrix_rev": None,
    "open_defects": {"P0": 0, "P1": 0, "P2": 0, "P3": 0},
    "signals": {},
    "prod_access": "none",
    "prod_test_state": "missing",
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
        "required_quiet_streak": 2,
        "max_rc_rounds": 5,
        "max_wall_clock_hours": 4,
        "max_fix_failures_per_defect": 2,
        "max_p0_fix_rounds": 3,
    },
}


def json_deepcopy(obj: Any) -> Any:
    return json.loads(json.dumps(obj))


def merge_state(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge_state(out[k], v)
        else:
            out[k] = v
    return out


def ensure_tree(root: Path) -> None:
    mit = ensure_mit(root)
    for sub in (
        "bugs",
        "bugs/confirmed",
        "bugs/rejected",
        "bugs/deferred",
        "flows",
        "baselines",
    ):
        (mit / sub).mkdir(parents=True, exist_ok=True)
    ensure_hunts(root)
    ensure_tests(root)
    (mit / "deliverables").mkdir(parents=True, exist_ok=True)
    (mit / "escalation").mkdir(parents=True, exist_ok=True)


def build_state(
    depth: str = "hunt",
    mode: str | None = None,
    prod_access: str = "none",
    matrix_rev: str | None = None,
    resume: bool = False,
    resume_summary: str | None = None,
) -> dict[str, Any]:
    state = json_deepcopy(DEFAULT_STATE)
    now = utc_now()
    state["created_at"] = now
    state["updated_at"] = now
    if depth in DEPTHS:
        state["depth"] = depth
    if mode:
        state["mode"] = mode
    elif depth == "release":
        state["mode"] = "test-and-fix"
    else:
        state["mode"] = "hunt-and-fix"
    if prod_access in PROD_ACCESS:
        state["prod_access"] = prod_access
    if matrix_rev:
        state["matrix_rev"] = matrix_rev
    if resume and resume_summary:
        state["resume_summary"] = resume_summary
        state["decision"] = "in_progress"
    return state


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
    depth: str = "hunt",
    prod_access: str = "none",
) -> dict[str, Any]:
    ensure_tree(root)
    state_path = root / ".mmit" / "state.json"
    fp_path = root / ".mmit" / "fingerprints.json"
    lock_path = root / ".mmit" / ".lock"

    try:
        fd = acquire_lock(lock_path)
    except RuntimeError as e:
        raise LockError(str(e)) from e
    try:
        if state_path.exists() and not force:
            raise FileExistsError(
                f"{state_path} already exists. Use --force to overwrite or resume via existing file."
            )

        state = build_state(depth=depth, mode=mode, prod_access=prod_access)

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
            patch["surfaces"] = merge_state(patch.get("surfaces") or {}, {"canvas": canvas_surface})

        if patch:
            state = merge_state(state, patch)

        write_json(state_path, state)
        if not fp_path.exists() or force:
            write_json(
                fp_path,
                {
                    "version": 1,
                    "updated_at": state["updated_at"],
                    "entries": {},
                },
            )
    finally:
        release_lock(fd, lock_path)
    return state


def resume_summary(root: Path) -> dict[str, Any]:
    state_path = root / ".mmit" / "state.json"
    if not state_path.exists():
        return {"ok": False, "error": "state.json missing; run init_state first"}
    state = read_json(state_path) or {}
    return {
        "ok": True,
        "depth": state.get("depth"),
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
    p = argparse.ArgumentParser(description="Initialize MMIT state (.mmit/state.json)")
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--depth", choices=list(DEPTHS), default="hunt")
    p.add_argument("--mode", default=None)
    p.add_argument("--routes", nargs="*", help="web routes, e.g. / /about")
    p.add_argument("--viewports", nargs="*", help="viewports, e.g. 375x812 1440x900")
    p.add_argument("--base-url", dest="base_url")
    p.add_argument("--modalities", nargs="*")
    p.add_argument("--canvas-items", nargs="*")
    p.add_argument("--export-target", dest="export_target")
    p.add_argument("--prod-access", default="none", choices=list(PROD_ACCESS))
    p.add_argument("--matrix-rev", default=None)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--resume-summary", default=None)
    p.add_argument("--force", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    if args.resume and not args.force:
        ensure_tree(root)
        summary = resume_summary(root)
        print(json.dumps(summary, ensure_ascii=False))
        return 0 if summary.get("ok") else 1

    state = init_state(
        root,
        routes=args.routes,
        viewports=args.viewports,
        base_url=args.base_url,
        mode=args.mode,
        modalities=args.modalities,
        quiet_streak=None,
        force=args.force,
        canvas_items=args.canvas_items,
        export_target=args.export_target,
        depth=args.depth,
        prod_access=args.prod_access,
    )
    print(f"state written: {root / '.mmit' / 'state.json'} depth={state['depth']} mode={state['mode']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
