#!/usr/bin/env python3
"""Decidable Fix Gate (DESIGN §6.3 / Phase 1)."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import contrast_probe  # noqa: E402
import fingerprint as fp  # noqa: E402
import layout_probe as lp  # noqa: E402
import visual_diff as vd  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class LockError(RuntimeError):
    pass


def acquire_lock(lock_path: Path) -> int:
    import time

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()}\n{utc_now()}\n".encode("utf-8"))
            return fd
        except FileExistsError as e:
            if attempt == 2:
                raise LockError(f"lock exists: {lock_path}") from e
            time.sleep(0.05 * (attempt + 1))
    raise LockError("unreachable")


def release_lock(fd: int, lock_path: Path) -> None:
    try:
        os.close(fd)
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


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


def load_bug(root: Path, bug_ref: str) -> dict[str, Any]:
    path = Path(bug_ref)
    if path.exists():
        return load_json(path)
    # search by id in confirmed/fixed/rejected/deferred
    bh = root / ".bug-hunter" / "bugs"
    for sub in ("confirmed", "fixed", "rejected", "deferred"):
        d = bh / sub
        if not d.exists():
            continue
        for p in d.glob("*.json"):
            data = load_json(p)
            if data.get("id") == bug_ref or p.stem == bug_ref:
                return data
    raise FileNotFoundError(f"bug not found: {bug_ref}")


def load_state(root: Path) -> dict[str, Any]:
    path = root / ".bug-hunter" / "state.json"
    if not path.exists():
        return {}
    return load_json(path)


def elements_from_capture_item(item: dict[str, Any], captures_dir: Path) -> list[dict[str, Any]] | None:
    name = item.get("elements_json")
    if not name:
        return None
    path = captures_dir / name
    if not path.exists():
        return None
    data = load_json(path)
    return data.get("elements") or []


def probe_cell(elements: list[dict[str, Any]], *, width: float, height: float, oracle: dict[str, Any]) -> list[dict[str, Any]]:
    layout = lp.run_layout_rules(
        elements,
        viewport_width=width,
        viewport_height=height,
        epsilon_px=float(oracle.get("overflow_epsilon_px", 2)),
        touch_target_px=float(oracle.get("touch_target_px", 44)),
        overlap_ratio=float(oracle.get("overlap_ratio", 0.2)),
    )
    contrast = contrast_probe.run_contrast_rules(
        elements,
        min_contrast=float(oracle.get("min_contrast", 4.5)),
        large_text_min_contrast=float(oracle.get("large_text_min_contrast", 3.0)),
        font_too_small_px=float(oracle.get("font_too_small_px", 12)),
        line_height_min_ratio=float(oracle.get("line_height_min_ratio", 1.2)),
    )
    for f in layout + contrast:
        if f.get("core_assertion_digest") and f.get("rule_id"):
            # fingerprint uses rule|digest text
            pass
    return layout + contrast


def parse_vp(viewport: str) -> tuple[float, float]:
    text = (viewport or "").strip().lower().replace(" ", "")
    if "x" in text:
        a, _, b = text.partition("x")
        try:
            return float(a), float(b)
        except ValueError:
            pass
    return 0.0, 0.0


def known_fingerprints(fp_path: Path) -> set[str]:
    if not fp_path.exists():
        return set()
    data = load_json(fp_path)
    return set((data.get("entries") or {}).keys())


def load_fix_verify(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return load_json(path)


def run_fix_gate(
    *,
    root: Path,
    bug: dict[str, Any],
    captures_dir: Path,
    baseline_dir: Path,
    test_cmd: str | None = None,
    regression_mode: str = "matrix",
    threshold: float = 0.01,
    fix_verify_path: Path | None = None,
) -> dict[str, Any]:
    state = load_state(root)
    oracle = state.get("visual_oracle") or {}
    fp_path = root / ".bug-hunter" / "fingerprints.json"
    known = known_fingerprints(fp_path)
    lock_path = root / ".bug-hunter" / ".lock"

    bug_id = bug.get("id") or "unknown"
    rule_id = bug.get("rule_id") or (bug.get("evidence") or {}).get("rule_id")
    loc = bug.get("location") or {}
    target_route = loc.get("route")
    target_viewport = loc.get("viewport")
    target_selector = loc.get("selector")

    manifest_path = captures_dir / "MANIFEST.json"
    if not manifest_path.exists():
        return {
            "ok": False,
            "bug_id": bug_id,
            "error": f"MANIFEST.json missing in {captures_dir}",
            "checks": {},
        }
    manifest = load_json(manifest_path)
    items = [i for i in (manifest.get("items") or []) if i.get("status") == "ok"]

    if regression_mode == "target-only":
        items = [
            i
            for i in items
            if i.get("route") == target_route and i.get("viewport") == target_viewport
        ]

    all_findings: list[dict[str, Any]] = []
    cell_findings: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        elements = elements_from_capture_item(item, captures_dir)
        if elements is None:
            continue
        w, h = parse_vp(item.get("viewport") or "")
        if w <= 0:
            web = (state.get("surfaces") or {}).get("web") or {}
            # fallback from viewport field
            pass
        findings = probe_cell(elements, width=w, height=h, oracle=oracle)
        key = f"{item.get('route')}@{item.get('viewport')}"
        cell_findings[key] = findings
        all_findings.extend(findings)

    # target_cleared: no finding with same rule_id at target route×viewport
    target_hits = []
    if rule_id:
        for f in all_findings:
            l = f.get("location") or {}
            if f.get("rule_id") != rule_id:
                continue
            if target_route and l.get("route") != target_route:
                continue
            if target_viewport and l.get("viewport") != target_viewport:
                continue
            if target_selector and l.get("selector") not in (target_selector, None) and target_selector not in str(
                l.get("selector")
            ):
                # keep hit if selector matches loosely; still count rule at location
                pass
            target_hits.append(f)

    target_cleared = {"ok": len(target_hits) == 0, "rule_id": rule_id, "remaining": len(target_hits)}
    if target_hits:
        target_cleared["examples"] = [
            {
                "rule_id": f.get("rule_id"),
                "selector": (f.get("location") or {}).get("selector"),
                "route": (f.get("location") or {}).get("route"),
                "viewport": (f.get("location") or {}).get("viewport"),
            }
            for f in target_hits[:5]
        ]

    # zero_new_layout: new fingerprints not previously known
    new_fps = []
    for f in all_findings:
        dig = f.get("core_assertion_digest")
        if not dig and f.get("rule_id"):
            f = dict(f)
            f["core_assertion_digest"] = f"{f['rule_id']}|{f.get('detected_by', 'probe')}"
        try:
            fingerprint = fp.fingerprint_from_finding(f)
        except Exception:
            continue
        f["fingerprint"] = fingerprint
        if fingerprint not in known:
            new_fps.append(
                {
                    "fingerprint": fingerprint,
                    "rule_id": f.get("rule_id"),
                    "route": (f.get("location") or {}).get("route"),
                    "viewport": (f.get("location") or {}).get("viewport"),
                    "selector": (f.get("location") or {}).get("selector"),
                }
            )

    zero_new = {"ok": len(new_fps) == 0, "new_fingerprints": new_fps}

    # pixel_gate
    verify = load_fix_verify(fix_verify_path) if fix_verify_path else {}
    intentional = bool(verify.get("intentional_visual_change"))
    intentional_cells = set(verify.get("intentional_cells") or [])
    approvals = vd.load_approvals(root)
    approved_stems = {a.get("stem") for a in approvals}

    diff = vd.compare_captures(captures_dir, baseline_dir, threshold=threshold)
    unexpected = []
    if diff.get("status") == "skipped":
        pixel_gate = {
            "ok": True,
            "skipped": True,
            "reason": diff.get("reason"),
            "unexpected_diffs": [],
        }
    else:
        for f in diff.get("findings") or []:
            l = f.get("location") or {}
            route = l.get("route")
            viewport = l.get("viewport")
            stem = None
            for item in items:
                if item.get("route") == route and item.get("viewport") == viewport:
                    stem = item.get("stem")
                    break
            is_target = route == target_route and viewport == target_viewport
            cell = f"{route}@{viewport}"
            allowed = is_target or intentional and cell in intentional_cells or (stem and stem in approved_stems)
            if not allowed:
                unexpected.append({"route": route, "viewport": viewport, "stem": stem})
        pixel_gate = {
            "ok": len(unexpected) == 0,
            "unexpected_diffs": unexpected,
            "diff_status": diff.get("status"),
            "intentional_visual_change": intentional,
        }

    # unit_green
    if test_cmd:
        try:
            proc = subprocess.run(test_cmd, shell=True, cwd=str(root), capture_output=True, text=True)
            unit = {
                "ok": proc.returncode == 0,
                "cmd": test_cmd,
                "exit_code": proc.returncode,
            }
            if proc.returncode != 0:
                unit["stderr_tail"] = (proc.stderr or "")[-500:]
        except Exception as e:  # noqa: BLE001
            unit = {"ok": False, "cmd": test_cmd, "error": str(e)}
    else:
        unit = {"ok": True, "cmd": None, "skipped": True}

    checks = {
        "target_cleared": target_cleared,
        "zero_new_layout": zero_new,
        "pixel_gate": pixel_gate,
        "unit_green": unit,
    }
    ok = all(c.get("ok") for c in checks.values())
    result = {
        "bug_id": bug_id,
        "ok": ok,
        "checks": checks,
        "intentional_visual_change": intentional,
        "regression_mode": regression_mode,
        "captures_dir": str(captures_dir),
        "at": utc_now(),
    }
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Decidable fix gate (Phase 1)")
    p.add_argument("--root", default=".")
    p.add_argument("--bug", required=True, help="bug json path or id")
    p.add_argument("--captures", required=True, help="post-fix captures dir with MANIFEST.json")
    p.add_argument("--baseline-dir", required=True)
    p.add_argument("--test-cmd", default=None)
    p.add_argument("--regression-mode", choices=["matrix", "target-only"], default="matrix")
    p.add_argument("--threshold", type=float, default=0.01)
    p.add_argument("--fix-verify", default=None, help="optional pre-existing fix-verify JSON with intentional flags")
    p.add_argument("--out", default=None, help="write result JSON path")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()
    captures = Path(args.captures).resolve()
    baseline_dir = Path(args.baseline_dir).resolve()
    fix_verify_path = Path(args.fix_verify).resolve() if args.fix_verify else None

    try:
        bug = load_bug(root, args.bug)
    except FileNotFoundError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2

    lock_path = root / ".bug-hunter" / ".lock"
    try:
        fd = acquire_lock(lock_path)
    except LockError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1

    try:
        result = run_fix_gate(
            root=root,
            bug=bug,
            captures_dir=captures,
            baseline_dir=baseline_dir,
            test_cmd=args.test_cmd,
            regression_mode=args.regression_mode,
            threshold=args.threshold,
            fix_verify_path=fix_verify_path,
        )
        # persist under runs if possible
        run_id = bug.get("run_id") or "run-fix"
        out_default = root / ".bug-hunter" / "runs" / str(run_id) / "fix-verify.json"
        out_path = Path(args.out).resolve() if args.out else out_default
        save_json(out_path, result)
        result["fix_verify_path"] = str(out_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    finally:
        release_lock(fd, lock_path)


if __name__ == "__main__":
    raise SystemExit(main())
