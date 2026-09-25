#!/usr/bin/env python3
"""Single-round hunt orchestration (Phase 1): capture → probes → register → summarize."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import capture_web  # noqa: E402
import canvas_probe  # noqa: E402
import converge_check as cc  # noqa: E402
import contrast_probe  # noqa: E402
import fingerprint as fp  # noqa: E402
import fp_feedback as fpf  # noqa: E402
import layout_probe as lp  # noqa: E402
import ux_flow  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    import os

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def parse_vp(label: str | None) -> tuple[float, float]:
    text = (label or "").strip().lower().replace(" ", "")
    if "x" in text:
        a, _, b = text.partition("x")
        try:
            return float(a), float(b)
        except ValueError:
            pass
    return 0.0, 0.0


def probe_manifest_cells(
    captures_dir: Path,
    *,
    oracle: dict[str, Any],
) -> list[dict[str, Any]]:
    manifest_path = captures_dir / "MANIFEST.json"
    if not manifest_path.exists():
        return []
    manifest = load_json(manifest_path)
    findings: list[dict[str, Any]] = []
    for item in manifest.get("items") or []:
        if item.get("status") != "ok":
            continue
        elements_name = item.get("elements_json")
        if not elements_name:
            continue
        elements_path = captures_dir / elements_name
        if not elements_path.exists():
            continue
        payload = load_json(elements_path)
        elements = payload.get("elements") or []
        w, h = parse_vp(item.get("viewport") or payload.get("viewport"))
        route = item.get("route") or payload.get("route")
        viewport = item.get("viewport") or payload.get("viewport")
        for el in elements:
            el.setdefault("route", route)
            el.setdefault("viewport", viewport)
        layout = lp.run_layout_rules(
            elements,
            viewport_width=w,
            viewport_height=h,
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
        cell_findings = layout + contrast
        raw_name = f"{item.get('stem') or capture_web.route_slug(str(route))}__findings.json"
        save_json(
            captures_dir.parent / "findings" / "raw" / raw_name,
            {"route": route, "viewport": viewport, "findings": cell_findings},
        )
        findings.extend(cell_findings)
    return findings


def run_dynamic(cmd: str, *, root: Path) -> list[dict[str, Any]]:
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as e:  # noqa: BLE001
        return [
            {
                "rule_id": "dynamic-fail",
                "modality": "code",
                "category": "logic",
                "severity": "high",
                "title": f"Dynamic command crashed: {cmd}",
                "statement": str(e),
                "location": {"file": cmd, "viewport": "n/a"},
                "metrics": {"cmd": cmd},
                "evidence_level_target": "L3",
                "detected_by": "dynamic",
                "core_assertion_digest": "dynamic|command-crash",
            }
        ]
    if proc.returncode == 0:
        return []
    tail = ((proc.stderr or "") + "\n" + (proc.stdout or ""))[-800:]
    return [
        {
            "rule_id": "dynamic-fail",
            "modality": "code",
            "category": "logic",
            "severity": "high",
            "title": f"Dynamic test/command failed: {cmd}",
            "statement": f"exit={proc.returncode}",
            "location": {"file": cmd, "viewport": "n/a"},
            "metrics": {"cmd": cmd, "exit_code": proc.returncode, "output_tail": tail},
            "evidence_level_target": "L3",
            "detected_by": "dynamic",
            "core_assertion_digest": "dynamic|command-fail",
        }
    ]


def summarize(findings: list[dict[str, Any]], reg: dict[str, Any]) -> dict[str, Any]:
    by_rule: dict[str, int] = {}
    by_viewport: dict[str, int] = {}
    by_modality: dict[str, int] = {}
    for f in findings:
        rule = f.get("rule_id") or "unknown"
        by_rule[rule] = by_rule.get(rule, 0) + 1
        vp = (f.get("location") or {}).get("viewport") or "n/a"
        by_viewport[str(vp)] = by_viewport.get(str(vp), 0) + 1
        mod = f.get("modality") or "unknown"
        by_modality[mod] = by_modality.get(mod, 0) + 1
    return {
        "findings_total": len(findings),
        "new_count": reg.get("new_count", 0),
        "known_count": reg.get("known_count", 0),
        "duplicate_rate": reg.get("duplicate_rate", 0.0),
        "by_rule": by_rule,
        "by_viewport": by_viewport,
        "by_modality": by_modality,
    }


def load_state(root: Path) -> dict[str, Any]:
    path = root / ".bug-hunter" / "state.json"
    if not path.exists():
        return {}
    return load_json(path)


def run_hunt_round(
    *,
    root: Path,
    run_id: str,
    skip_capture: bool = False,
    captures: Path | None = None,
    dynamic_cmd: str | None = None,
    write_candidates: bool = False,
    strategies: list[str] | None = None,
    flows: Path | None = None,
    canvas_items: Path | None = None,
    fp_patterns: Path | None = None,
) -> dict[str, Any]:
    state = load_state(root)
    web = (state.get("surfaces") or {}).get("web") or {}
    oracle = state.get("visual_oracle") or {}
    degrade = web.get("degrade_level") or "L1"
    previous_quiet = int(
        (state.get("convergence") or {}).get("quiet_streak", state.get("quiet_streak", 0))
    )
    required_quiet = int((state.get("convergence") or {}).get("required_quiet_streak", 2))
    modalities = state.get("modalities_enabled") or ["code", "web-visual"]

    captures_dir = captures or (root / ".bug-hunter" / "runs" / run_id / "captures")
    findings: list[dict[str, Any]] = []
    used_strategies: list[str] = list(strategies or [])
    capture_result = None

    web_probe_allowed = cc.degrade_allows_strategy(degrade, "layout-geom")

    if not skip_capture and web_probe_allowed:
        capture_result = capture_web.run_capture(
            root=root,
            base_url=web.get("base_url"),
            routes=web.get("routes"),
            viewports=web.get("viewports"),
            out=captures_dir,
            run_id=run_id,
            timeout_ms=20000,
        )
        if capture_result.get("backend") == "unavailable":
            degrade = "L1"
            web_probe_allowed = False

    # Probe existing captures only when MANIFEST actually has successful cells
    # (fixtures / resume / L2+). An empty or unavailable-backend MANIFEST must
    # not credit web strategies or elevate degrade — that would false-quiet.
    manifest_path = captures_dir / "MANIFEST.json"
    usable_manifest = False
    if manifest_path.exists():
        try:
            manifest_data = load_json(manifest_path)
        except Exception:
            manifest_data = {}
        backend = manifest_data.get("backend")
        ok_items = [
            i
            for i in (manifest_data.get("items") or [])
            if i.get("status") == "ok" and i.get("elements_json")
        ]
        usable_manifest = backend != "unavailable" and bool(ok_items)

    if usable_manifest:
        if "layout-geom" not in used_strategies:
            used_strategies.append("layout-geom")
        if "contrast-type" not in used_strategies:
            used_strategies.append("contrast-type")
        if "responsive-matrix" not in used_strategies:
            used_strategies.append("responsive-matrix")
        cell_findings = probe_manifest_cells(captures_dir, oracle=oracle)
        findings.extend(cell_findings)
        # Consuming real capture cells implies web-visual was exercised this round.
        if degrade in ("L0", "L1"):
            degrade = "L2"
        # Phase 2: static ux rules (+ optional symbolic flows) whenever cells exist.
        # L4 always credits ux-flow; L2/L3 credit when flows were supplied or findings exist
        # (converge_check still withholds quiet credit for L4-only ids below L4).
        ux_result = ux_flow.run_ux_on_manifest(
            manifest_path=manifest_path,
            flows_dir=flows,
            oracle=oracle,
        )
        ux_findings = ux_result.get("findings") or []
        findings.extend(ux_findings)
        # Persist raw ux findings so vlm_audit cross-check can corroborate them
        if ux_findings:
            save_json(
                captures_dir.parent / "findings" / "raw" / "ux-flow__manifest.json",
                {"findings": ux_findings, "flows": ux_result.get("flows")},
            )
        if (
            cc.degrade_allows_strategy(degrade, "ux-flow")
            or flows is not None
            or ux_findings
        ):
            if "ux-flow" not in used_strategies:
                used_strategies.append("ux-flow")

    # Phase 2: canvas probe when items available and degrade allows
    canvas_cfg = (state.get("surfaces") or {}).get("canvas") or {}
    canvas_items_path = canvas_items
    raw_canvas_items = canvas_cfg.get("items") or []
    canvas_findings: list[dict[str, Any]] = []
    canvas_scanned = False
    canvas_unavailable: list[dict[str, Any]] = []

    def _item_is_scannable(item: dict[str, Any]) -> bool:
        """True only when the item has real geometry/assets to probe."""
        return bool(item.get("objects") or item.get("assets"))

    if canvas_items_path is None and raw_canvas_items:
        loaded: list[dict[str, Any]] = []
        for item in raw_canvas_items:
            if not isinstance(item, dict):
                continue
            src = item.get("source")
            if src:
                src_path = Path(src)
                if not src_path.is_absolute():
                    src_path = root / src
                if src_path.exists():
                    loaded_from = canvas_probe.load_items_from_path(src_path)
                    if loaded_from:
                        merged = loaded_from[0]
                        merged["id"] = item.get("id") or merged.get("id")
                        merged["export_target"] = (
                            item.get("export_target")
                            or canvas_cfg.get("export_target")
                            or merged.get("export_target")
                        )
                        if _item_is_scannable(merged):
                            loaded.append(merged)
                        else:
                            canvas_unavailable.append(
                                {"canvas_id": merged.get("id"), "reason": "source-has-no-objects-or-assets"}
                            )
                        continue
                canvas_unavailable.append(
                    {"canvas_id": item.get("id"), "reason": "source-missing", "source": str(src)}
                )
                continue
            # Inline objects/assets without source
            normalized = canvas_probe.normalize_item(item)
            if _item_is_scannable(normalized):
                loaded.append(normalized)
            else:
                canvas_unavailable.append(
                    {"canvas_id": normalized.get("id"), "reason": "no-objects-or-assets"}
                )
        # Only credit canvas scan when at least one item is actually probeable
        scannable = [i for i in loaded if _item_is_scannable(i)]
        if scannable:
            canvas_scanned = True
            if "canvas" not in modalities:
                modalities = list(modalities) + ["canvas"]
            canvas_result = canvas_probe.run_canvas_items(
                scannable,
                export_target=canvas_cfg.get("export_target"),
                oracle=oracle,
            )
            canvas_findings = canvas_result.get("findings") or []
    elif canvas_items_path is not None:
        items = canvas_probe.load_items_from_path(Path(canvas_items_path))
        scannable = [i for i in items if _item_is_scannable(i)]
        for i in items:
            if not _item_is_scannable(i):
                canvas_unavailable.append(
                    {"canvas_id": i.get("id"), "reason": "no-objects-or-assets"}
                )
        if scannable:
            canvas_scanned = True
            if "canvas" not in modalities:
                modalities = list(modalities) + ["canvas"]
            canvas_result = canvas_probe.run_canvas_items(
                scannable,
                export_target=canvas_cfg.get("export_target"),
                oracle=oracle,
            )
            canvas_findings = canvas_result.get("findings") or []

    canvas_elevated = None
    if canvas_scanned:
        findings.extend(canvas_findings)
        if canvas_findings:
            save_json(
                root / ".bug-hunter" / "runs" / run_id / "findings" / "raw" / "canvas__items.json",
                {"findings": canvas_findings, "unavailable": canvas_unavailable},
            )
        # L4 = L3 + canvas. Elevate only when at least one item was actually probed.
        if degrade == "L3":
            degrade = "L4"
            canvas_elevated = "canvas-items"
        if cc.degrade_allows_strategy(degrade, "canvas-safe"):
            for sid in ("canvas-safe", "canvas-asset"):
                if sid not in used_strategies:
                    used_strategies.append(sid)
    elif canvas_unavailable:
        save_json(
            root / ".bug-hunter" / "runs" / run_id / "findings" / "raw" / "canvas__unavailable.json",
            {"unavailable": canvas_unavailable},
        )

    if dynamic_cmd:
        if "dynamic" not in used_strategies:
            used_strategies.append("dynamic")
        findings.extend(run_dynamic(dynamic_cmd, root=root))

    if not used_strategies:
        used_strategies = ["static"]

    # Phase 3: apply FP whitelist before registration (suppressed still register).
    patterns_path = fp_patterns or (root / ".bug-hunter" / "fp_patterns.json")
    suppressed_hits: list[dict[str, Any]] = []
    if patterns_path.exists():
        try:
            fp_store = fpf.load_patterns(patterns_path)
            findings, suppressed_hits = fpf.apply_patterns(findings, fp_store)
        except Exception as e:  # noqa: BLE001 — surface pattern corruption, do not silent-skip
            suppressed_hits = []
            save_json(
                root / ".bug-hunter" / "runs" / run_id / "findings" / "fp-apply-error.json",
                {"error": str(e), "patterns_path": str(patterns_path)},
            )

    fp_path = root / ".bug-hunter" / "fingerprints.json"
    reg = fp.register_fingerprints(findings, fp_path=fp_path, run_id=run_id, now=utc_now())
    # new_count excludes suppressed so they cannot inflate discovery.
    new_count = sum(1 for item in reg.get("new") or [] if item.get("status") != "suppressed")
    known_count = sum(1 for item in reg.get("known") or [] if item.get("status") != "suppressed")
    reg = dict(reg)
    reg["new_count"] = new_count
    reg["known_count"] = known_count
    reg["duplicate_rate"] = (
        (reg.get("known_count", 0) + len([i for i in reg.get("known") or [] if i.get("status") == "suppressed"]))
        / len(findings)
        if findings
        else 0.0
    )

    if write_candidates:
        cand_dir = root / ".bug-hunter" / "runs" / run_id / "findings" / "candidates"
        cand_dir.mkdir(parents=True, exist_ok=True)
        for item in reg.get("new") or []:
            save_json(cand_dir / f"{item.get('fingerprint')}.json", item)

    new_confirmed = 0  # hunt_round never confirms; agent does
    conv = cc.evaluate_round(
        strategies=used_strategies,
        degrade_level=degrade,
        modalities_enabled=modalities,
        new_confirmed=new_confirmed,
        new_regressions=[],
        previous_quiet_streak=previous_quiet,
        required_quiet_streak=required_quiet,
    )

    summary = summarize(findings, reg)
    summary.update(
        {
            "run_id": run_id,
            "degrade_level": degrade,
            "strategies": used_strategies,
            "convergence": conv,
            "capture_backend": (capture_result or {}).get("backend"),
            "captured_at": utc_now(),
            "phase": 3,
            "suppressed_count": len(suppressed_hits),
            "suppressed": suppressed_hits,
        }
    )
    if canvas_elevated:
        summary["degrade_elevated_by"] = canvas_elevated
    save_json(root / ".bug-hunter" / "runs" / run_id / "summary.json", summary)
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run one hunt round (capture→probe→register)")
    p.add_argument("--root", default=".")
    p.add_argument("--run-id", default="run-1")
    p.add_argument("--skip-capture", action="store_true")
    p.add_argument("--captures", default=None)
    p.add_argument("--dynamic-cmd", default=None)
    p.add_argument("--write-candidates", action="store_true")
    p.add_argument("--flows", help="directory of ux-flow JSON files")
    p.add_argument("--canvas-items", dest="canvas_items", help="canvas items JSON file or dir")
    p.add_argument(
        "--fp-patterns",
        dest="fp_patterns",
        default=None,
        help="FP whitelist JSON (default .bug-hunter/fp_patterns.json)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()
    captures = Path(args.captures).resolve() if args.captures else None
    summary = run_hunt_round(
        root=root,
        run_id=args.run_id,
        skip_capture=args.skip_capture,
        captures=captures,
        dynamic_cmd=args.dynamic_cmd,
        write_candidates=args.write_candidates,
        flows=Path(args.flows).resolve() if args.flows else None,
        canvas_items=Path(args.canvas_items).resolve() if args.canvas_items else None,
        fp_patterns=Path(args.fp_patterns).resolve() if args.fp_patterns else None,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
