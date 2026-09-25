#!/usr/bin/env python3
"""Production-side test probe for MMIT-Test (E2). Writes results or explicit missing declaration."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mit_lib import ensure_mit, read_json, utc_now, write_json  # noqa: E402


def build_prod_results(root: Path) -> dict[str, Any]:
    state_path = ensure_mit(root) / "state.json"
    state = read_json(state_path) if state_path.exists() else {}
    prod_access = state.get("prod_access", "none")
    base = {
        "version": 1,
        "generated_at": utc_now(),
        "prod_access": prod_access,
        "rc_id": f"RC-{state.get('rc_n', 0)}",
        "rc_sha": state.get("rc_sha"),
    }
    if prod_access == "none":
        return {
            **base,
            "available": False,
            "mode": "none",
            "missing_declaration": {
                "reason": "prod_access=none — no authorized production probe",
                "impact": "PRD missing; unconditional Allow is forbidden",
                "recommended": "conditional Allow (exposure constraint) or Deny/Escalate",
            },
            "critical_path_pass": None,
            "slis": [],
        }
    # Authorized modes still cannot hit real prod from this workspace — declare probe attempt + limitation.
    return {
        **base,
        "available": False,
        "mode": prod_access,
        "missing_declaration": {
            "reason": f"prod_access={prod_access} authorized but no live production endpoint configured in this workspace",
            "impact": "PRD incomplete; treat as conservative",
            "recommended": "configure synthetic probes against prod/qualified traffic plane",
        },
        "critical_path_pass": None,
        "slis": ["http_5xx_rate", "p95_latency", "journey_success"],
        "protocol": "canary_vs_control" if prod_access == "canary" else "synthetic_readonly",
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Prod test probe (E2) or missing declaration")
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--out", type=Path, default=None)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    results = build_prod_results(root)
    out = args.out or (ensure_mit(root) / "prod_test_results.json")
    write_json(out, results)
    # also write a human missing note when unavailable
    if not results.get("available"):
        note = ensure_mit(root) / "deliverables" / "PROD_RESULTS_MISSING.md"
        note.parent.mkdir(parents=True, exist_ok=True)
        md = results.get("missing_declaration", {})
        note.write_text(
            "\n".join(
                [
                    "# 真实生产环境测试结果缺失",
                    "",
                    f"- prod_access: `{results.get('prod_access')}`",
                    f"- reason: {md.get('reason')}",
                    f"- impact: {md.get('impact')}",
                    f"- recommended: {md.get('recommended')}",
                    "",
                    "裁决时 PRD 缺失 → 禁止无条件 Allow。",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        print(f"prod results MISSING -> {out} + {note}")
    else:
        print(f"prod results written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
