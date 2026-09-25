#!/usr/bin/env python3
"""Phase 2 fixture E2E (no browser): ux + canvas + vlm merge on acceptance-demo assets."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "mmit-hunter" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import canvas_probe  # noqa: E402
import capture_web  # noqa: E402
import hunt_round  # noqa: E402
import vlm_audit  # noqa: E402


def main() -> int:
    demo = ROOT / "examples" / "acceptance-demo"
    fixtures = ROOT / "tests" / "fixtures"
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        bh = root / ".bug-hunter"
        captures = bh / "runs" / "run-1" / "captures"
        captures.mkdir(parents=True)
        (bh / "runs" / "run-1" / "findings" / "raw").mkdir(parents=True)

        state = {
            "version": 1,
            "phase": 2,
            "modalities_enabled": ["code", "web-visual", "canvas"],
            "surfaces": {
                "web": {
                    "base_url": "http://127.0.0.1:5173",
                    "routes": ["/"],
                    "viewports": ["375x812"],
                    "degrade_level": "L3",
                },
                "canvas": {
                    "kind": "scene-json",
                    "export_target": "1080x1920",
                    "items": [
                        {
                            "id": "poster",
                            "source": str(demo / "canvas" / "poster.scene.json"),
                        }
                    ],
                },
            },
            "visual_oracle": {
                "overflow_epsilon_px": 2,
                "touch_target_px": 44,
                "overlap_ratio": 0.2,
                "safe_inset_pct": 5,
            },
            "convergence": {"quiet_streak": 0, "required_quiet_streak": 2},
        }
        (bh / "state.json").write_text(json.dumps(state), encoding="utf-8")
        (bh / "fingerprints.json").write_text(
            json.dumps({"version": 1, "entries": {}}), encoding="utf-8"
        )

        elements = {
            "route": "/",
            "viewport": "375x812",
            "elements": [
                {
                    "selector": "html",
                    "tag": "html",
                    "route": "/",
                    "viewport": "375x812",
                    "bbox": {"x": 0, "y": 0, "w": 375, "h": 812},
                    "scrollWidth": 420,
                    "clientWidth": 375,
                },
                {
                    "selector": "[data-testid=primary-cta]",
                    "tag": "button",
                    "route": "/",
                    "viewport": "375x812",
                    "interactive": True,
                    "bbox": {"x": 300, "y": 620, "w": 120, "h": 48},
                    "inViewport": True,
                    "text": "立即开始",
                },
                {
                    "selector": "[data-testid=dead-link]",
                    "tag": "a",
                    "route": "/",
                    "viewport": "375x812",
                    "href": "#",
                    "interactive": True,
                    "bbox": {"x": 8, "y": 100, "w": 64, "h": 20},
                    "inViewport": True,
                    "text": "占位死链",
                },
                {
                    "selector": "[data-testid=flow-submit]",
                    "tag": "button",
                    "type": "submit",
                    "route": "/",
                    "viewport": "375x812",
                    "interactive": True,
                    "bbox": {"x": 16, "y": 200, "w": 80, "h": 36},
                    "inViewport": True,
                    "text": "提交",
                },
                {
                    "selector": "[data-testid=empty-list]",
                    "tag": "ul",
                    "route": "/",
                    "viewport": "375x812",
                    "attrs": {"data-list-empty": "expected"},
                    "bbox": {"x": 0, "y": 260, "w": 300, "h": 48},
                    "inViewport": True,
                    "visible_child_count": 0,
                    "text": "",
                },
            ],
        }
        (captures / "home__375x812__elements.json").write_text(
            json.dumps(elements), encoding="utf-8"
        )
        manifest = capture_web.default_manifest(
            base_url="http://127.0.0.1:5173",
            routes=["/"],
            viewports=["375x812"],
            backend="python-playwright",
            items=[
                {
                    "route": "/",
                    "viewport": "375x812",
                    "stem": "home__375x812",
                    "status": "ok",
                    "elements_json": "home__375x812__elements.json",
                }
            ],
        )
        (captures / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")

        flows = demo / "flows"
        if not flows.exists():
            flows = demo / ".bug-hunter" / "flows"
        summary = hunt_round.run_hunt_round(
            root=root,
            run_id="run-1",
            skip_capture=True,
            captures=captures,
            flows=flows if flows.exists() else None,
        )
        print("=== hunt_round summary ===")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        rules = set((summary.get("by_rule") or {}).keys())
        required = {
            "overflow-x",
            "dead-link",
            "missing-feedback",
            "missing-empty-state",
            "ux-flow-step",
            "safe-area-violation",
            "export-mismatch",
            "low-res-asset",
        }
        missing = required - rules
        if missing:
            print(f"MISSING rules: {missing}", file=sys.stderr)
            return 1
        if summary.get("degrade_level") != "L4":
            print(f"expected L4, got {summary.get('degrade_level')}", file=sys.stderr)
            return 1

        # VLM merge against raw findings
        raw_dir = bh / "runs" / "run-1" / "findings" / "raw"
        view_a = fixtures / "vlm_view_a.json"
        view_b = fixtures / "vlm_view_b.json"
        consensus_path = bh / "runs" / "run-1" / "findings" / "vlm" / "consensus.json"
        import vlm_audit as va

        a = va.load_view(view_a)
        b = va.load_view(view_b)
        consensus = va.merge_views(a, b)
        raw = va.load_raw_findings(raw_dir)
        # Also include registered-looking findings from summary path: hunt wrote raw files
        cross = va.cross_check(consensus, raw)
        print(
            "=== vlm consensus ===",
            json.dumps(
                {
                    "consensus": len(consensus),
                    "standalone": len(cross["standalone"]),
                    "corroborated": cross["merged_into_machine"],
                },
                ensure_ascii=False,
            ),
        )
        if len(consensus) < 1:
            print("expected >=1 consensus", file=sys.stderr)
            return 1
        if cross["merged_into_machine"] < 1:
            print("expected CTA overflow to corroborate machine finding", file=sys.stderr)
            return 1

        # canvas probe standalone
        items = canvas_probe.load_items_from_path(demo / "canvas" / "poster.scene.json")
        cresult = canvas_probe.run_canvas_items(items, export_target="1080x1920")
        crules = {f["rule_id"] for f in cresult["findings"]}
        print("=== canvas rules ===", sorted(crules))
        if "safe-area-violation" not in crules or "export-mismatch" not in crules:
            return 1

        print("PHASE2 E2E OK")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
