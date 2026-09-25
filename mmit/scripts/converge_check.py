#!/usr/bin/env python3
"""Convergence check per DESIGN §6.2 quiet four conditions."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Strategy id -> modality it covers
STRATEGY_MODALITY: dict[str, str] = {
    "static": "code",
    "dynamic": "code",
    "generate": "code",
    "structural": "code",
    "speculative": "code",
    "meta-test": "code",
    "capture-baseline": "web-visual",
    "layout-geom": "web-visual",
    "visual-diff": "web-visual",
    "a11y-axe": "web-visual",
    "contrast-type": "web-visual",
    "responsive-matrix": "web-visual",
    "ux-flow": "web-visual",
    "canvas-safe": "canvas",
    "canvas-asset": "canvas",
    "vlm-audit": "web-visual",
}


def degrade_allows_strategy(degrade: str, strategy_id: str) -> bool:
    code = {
        "static",
        "dynamic",
        "generate",
        "structural",
        "speculative",
        "meta-test",
    }
    l2 = code | {"capture-baseline", "layout-geom", "contrast-type", "responsive-matrix"}
    l3 = l2 | {"a11y-axe"}
    l4 = l3 | {"canvas-safe", "canvas-asset", "vlm-audit", "ux-flow"}
    allowed = {
        "L0": set(),
        "L1": code,
        "L2": l2,
        "L3": l3,
        "L4": l4,
    }.get(degrade, code)
    return strategy_id in allowed


def covered_modalities(strategies: list[str], degrade: str) -> set[str]:
    mods: set[str] = set()
    for sid in strategies:
        if not degrade_allows_strategy(degrade, sid):
            continue
        mod = STRATEGY_MODALITY.get(sid)
        if mod:
            mods.add(mod)
    return mods


def available_modalities(modalities_enabled: list[str], degrade: str) -> set[str]:
    enabled = set(modalities_enabled)
    if degrade in ("L0",):
        return set()
    if degrade == "L1":
        return enabled & {"code"}
    if degrade in ("L2", "L3"):
        return enabled & {"code", "web-visual"}
    # L4
    return enabled


def evaluate_round(
    *,
    strategies: list[str],
    degrade_level: str,
    modalities_enabled: list[str],
    new_confirmed: int,
    new_regressions: list[str] | int | None,
    previous_quiet_streak: int,
    required_quiet_streak: int,
) -> dict[str, Any]:
    reasons: list[str] = []
    regressions: list[str]
    if new_regressions is None:
        regressions = []
    elif isinstance(new_regressions, int):
        regressions = [f"regression_count={new_regressions}"] if new_regressions else []
    else:
        regressions = list(new_regressions)

    ok = True

    if not strategies:
        ok = False
        reasons.append("no strategies executed this round")
    else:
        allowed = [s for s in strategies if degrade_allows_strategy(degrade_level, s)]
        if not allowed:
            ok = False
            reasons.append(
                f"none of strategies {strategies} allowed at degrade {degrade_level}"
            )

    need = available_modalities(modalities_enabled, degrade_level)
    got = covered_modalities(strategies, degrade_level)
    missing = sorted(need - got)
    if need and missing:
        ok = False
        reasons.append(
            f"missing modality coverage at {degrade_level}: {missing} "
            f"(need {sorted(need)}, got {sorted(got)})"
        )

    if new_confirmed > 0:
        ok = False
        reasons.append(f"new confirmed bugs: {new_confirmed}")

    if regressions:
        ok = False
        reasons.append(f"new regressions: {regressions}")

    if ok:
        reasons.append("quiet four conditions satisfied")

    quiet_streak = previous_quiet_streak + 1 if ok else 0
    converged = quiet_streak >= required_quiet_streak

    return {
        "quiet": ok,
        "quiet_streak": quiet_streak,
        "required_quiet_streak": required_quiet_streak,
        "converged": converged,
        "degrade_level": degrade_level,
        "strategies": strategies,
        "modalities_needed": sorted(need),
        "modalities_covered": sorted(got),
        "reasons": reasons,
    }


def evaluate_from_state(state: dict[str, Any], last_round: dict[str, Any]) -> dict[str, Any]:
    conv = state.get("convergence") or {}
    previous = int(conv.get("quiet_streak", state.get("quiet_streak", 0)) or 0)
    required = int(conv.get("required_quiet_streak", 2) or 2)
    web = (state.get("surfaces") or {}).get("web") or {}
    return evaluate_round(
        strategies=list(last_round.get("strategies") or state.get("last_strategy_set") or []),
        degrade_level=str(last_round.get("degrade_level") or web.get("degrade_level") or "L1"),
        modalities_enabled=list(state.get("modalities_enabled") or ["code", "web-visual"]),
        new_confirmed=int(last_round.get("new_confirmed") or 0),
        new_regressions=last_round.get("new_regressions"),
        previous_quiet_streak=previous,
        required_quiet_streak=required,
    )


def apply_result_to_state(state: dict[str, Any], result: dict[str, Any], last_round: dict[str, Any] | None = None) -> dict[str, Any]:
    state = json.loads(json.dumps(state))
    state.setdefault("convergence", {})
    state["convergence"]["quiet_streak"] = result["quiet_streak"]
    state["convergence"]["required_quiet_streak"] = result["required_quiet_streak"]
    state["quiet_streak"] = result["quiet_streak"]
    if last_round is not None:
        state["last_round"] = last_round
    state["converged"] = result["converged"]
    # three-state gate: allow when converged; deny while quiet fails; escalate left to escalate.py
    if result.get("converged"):
        state["decision"] = "allow"
    elif state.get("decision") != "escalated":
        state["decision"] = "deny"
    return state


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate quiet/convergence")
    p.add_argument("--root", default=".", help="project root with .mmit/state.json")
    p.add_argument(
        "--stdin",
        action="store_true",
        help="read {state, last_round} or a round payload from stdin instead of files",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.stdin:
        payload = json.load(sys.stdin)
        if "state" in payload:
            result = evaluate_from_state(payload["state"], payload.get("last_round") or {})
        else:
            conv_prev = int(payload.get("previous_quiet_streak", 0) or 0)
            result = evaluate_round(
                strategies=list(payload.get("strategies") or []),
                degrade_level=str(payload.get("degrade_level") or "L1"),
                modalities_enabled=list(payload.get("modalities_enabled") or ["code", "web-visual"]),
                new_confirmed=int(payload.get("new_confirmed") or 0),
                new_regressions=payload.get("new_regressions"),
                previous_quiet_streak=conv_prev,
                required_quiet_streak=int(payload.get("required_quiet_streak") or 2),
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    root = Path(args.root).resolve()
    state_path = root / ".mmit" / "state.json"
    if not state_path.exists():
        print(json.dumps({"ok": False, "error": f"missing {state_path}"}), file=sys.stderr)
        return 1
    with state_path.open("r", encoding="utf-8-sig") as f:
        state = json.load(f)
    last_round = state.get("last_round") or {
        "strategies": state.get("last_strategy_set") or [],
        "degrade_level": state.get("surfaces", {}).get("web", {}).get("degrade_level"),
        "new_confirmed": 0,
        "new_regressions": [],
    }
    result = evaluate_from_state(state, last_round)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
