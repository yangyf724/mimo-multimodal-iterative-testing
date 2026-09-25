#!/usr/bin/env python3
"""Assemble adjudication_signals.json for MMIT-Test."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mmit_lib import ensure_tests, ensure_mit, load_state, read_json, save_state, utc_now, write_json  # noqa: E402


def _load(root: Path, name: str) -> Any:
    p = ensure_tests(root) / name if name.endswith(".json") and name != "state.json" else ensure_mit(root) / name
    return read_json(p) if p.exists() else {}


def build_signals(root: Path) -> dict[str, Any]:
    state = _load(root, "state.json") or load_state(root)
    matrix = _load(root, "matrix.json")
    mask = _load(root, "data_mask_report.json")
    devices = _load(root, "device_probe.json")
    prod = _load(root, "prod_test_results.json")
    rc_id = f"RC-{state.get('rc_n', 0)}"
    results_path = ensure_tests(root) / "runs" / rc_id / "findings" / "matrix_results.json"
    results = read_json(results_path) if results_path.exists() else {"results": []}

    required = [i for i in matrix.get("items", []) if i.get("mark") == "required"]
    optional = [i for i in matrix.get("items", []) if i.get("mark") == "optional"]
    required_total = max(len(required), 1)
    by_mod = {r["modality"]: r for r in results.get("results", [])}

    required_pass = 0
    required_gaps: list[str] = []
    optional_degraded: list[str] = []
    for item in required:
        st = by_mod.get(item["modality"], {}).get("status")
        if st == "pass":
            required_pass += 1
        elif st == "fail":
            required_gaps.append(f"{item['modality']}:fail")
        else:
            required_gaps.append(f"{item['modality']}:{st or 'pending'}")
    for item in optional:
        st = by_mod.get(item["modality"], {}).get("status")
        if st not in {"pass", None} and item["modality"] in by_mod:
            optional_degraded.append(f"{item['modality']}:{st}")

    open_def = state.get("open_defects", {})
    # regression_green: true only if no open P0/P1 and at least one fixed defect carries regression, or no defects at all
    defects_dir = ensure_tests(root) / "defects"
    has_open_high = int(open_def.get("P0", 0)) > 0 or int(open_def.get("P1", 0)) > 0
    fixed_without_reg = []
    fixed_without_gate = []
    if defects_dir.is_dir():
        for p in defects_dir.glob("*.json"):
            if p.name.endswith(".fix_gate.json"):
                continue
            try:
                d = read_json(p)
            except Exception:
                continue
            if d.get("status") != "fixed":
                continue
            if not d.get("regression"):
                fixed_without_reg.append(d.get("id"))
            elif d.get("force_fixed"):
                fixed_without_gate.append(d.get("id"))
            else:
                gate_path = defects_dir / f"{d.get('id')}.fix_gate.json"
                if not gate_path.exists() or not read_json(gate_path).get("passed"):
                    fixed_without_gate.append(d.get("id"))
    regression_green = (not has_open_high) and (not fixed_without_reg) and (not fixed_without_gate)

    prod_available = bool(prod.get("available"))
    coverage = round(required_pass / required_total, 3) if required else 0.0
    # artifact_ready: rc exists AND no open P0 AND required coverage complete (no gaps)
    artifact_ready = (
        state.get("rc_sha") is not None
        and int(open_def.get("P0", 0)) == 0
        and coverage >= 1.0
        and not required_gaps
    )
    exposure_ready = (
        artifact_ready
        and prod_available
        and int(open_def.get("P1", 0)) == 0
        and bool(prod.get("critical_path_pass"))
    )

    signals = {
        "rc_id": rc_id,
        "rc_sha": state.get("rc_sha"),
        "matrix_rev": state.get("matrix_rev"),
        "generated_at": utc_now(),
        "signals": {
            "build_ok": state.get("rc_sha") is not None,
            "matrix_required_coverage": coverage,
            "required_gaps": required_gaps,
            "optional_degraded": optional_degraded,
            "open_p0": int(open_def.get("P0", 0)),
            "open_p1": int(open_def.get("P1", 0)),
            "open_p2": int(open_def.get("P2", 0)),
            "p2_user_accepted": False,
            "regression_green": regression_green,
            "fixed_without_regression": fixed_without_reg,
            "fixed_without_gate": fixed_without_gate,
            "device_coverage": devices.get("coverage", 0.0),
            "device_all_sim": devices.get("all_sim", True),
            "data_mask_clean": bool(mask.get("clean", False)),
            "release_layers": {
                "artifact_ready": artifact_ready,
                "exposure_ready": exposure_ready,
                "exposure_constraint": (
                    "none" if exposure_ready else "no_prod_or_coverage_gap_conditional_only"
                ),
            },
            "prod_test": {
                "available": prod_available,
                "mode": prod.get("mode"),
                "slis": prod.get("slis", []),
                "critical_path_pass": prod.get("critical_path_pass"),
            },
            "oracle_quality": {"k": 0, "agreement_rate": None, "fp_rate_estimate": None},
            "contract_breaking_unreviewed": False,
            "blind_spots": [b.get("id") for b in state.get("blinds", [])],
            "quiet_streak": state.get("quiet_streak", 0),
        },
    }
    return signals


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Assemble adjudication_signals.json")
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--out", type=Path, default=None)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    signals = build_signals(root)
    out = args.out or (ensure_mit(root) / "deliverables" / "adjudication_signals.json")
    write_json(out, signals)
    try:
        state = load_state(root)
        state["signals"] = signals["signals"]
        save_state(root, state)
    except FileNotFoundError:
        pass
    print(f"adjudication_signals written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
