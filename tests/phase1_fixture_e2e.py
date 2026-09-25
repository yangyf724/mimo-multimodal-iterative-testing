"""Fixture-based Phase 1 E2E: simulate demo defects without a browser.

Run:  $env:MIMO_PYTHON tests/phase1_fixture_e2e.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mmit-hunter" / "scripts"))

import fix_gate as fg  # noqa: E402
import hunt_round as hr  # noqa: E402
import init_state as init_mod  # noqa: E402
import visual_diff as vd  # noqa: E402


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def home_375_elements():
    return [
        {
            "selector": "html",
            "route": "/",
            "viewport": "375x812",
            "scrollWidth": 420,
            "clientWidth": 375,
            "bbox": {"x": 0, "y": 0, "w": 375, "h": 812},
        },
        {
            "selector": "[data-testid=tiny-action]",
            "route": "/",
            "viewport": "375x812",
            "interactive": True,
            "bbox": {"x": 16, "y": 400, "w": 24, "h": 20},
            "text": "小目标",
        },
        {
            "selector": "[data-testid=overlap-a]",
            "route": "/",
            "viewport": "375x812",
            "interactive": True,
            "bbox": {"x": 0, "y": 500, "w": 120, "h": 48},
            "text": "A",
        },
        {
            "selector": "[data-testid=overlap-b]",
            "route": "/",
            "viewport": "375x812",
            "interactive": True,
            "bbox": {"x": 40, "y": 512, "w": 120, "h": 48},
            "text": "B",
        },
        {
            "selector": "[data-testid=zero-btn]",
            "route": "/",
            "viewport": "375x812",
            "interactive": True,
            "bbox": {"x": 0, "y": 600, "w": 0, "h": 0},
            "text": "hidden",
        },
    ]


def about_375_elements():
    return [
        {
            "selector": "html",
            "route": "/about",
            "viewport": "375x812",
            "scrollWidth": 375,
            "clientWidth": 375,
            "bbox": {"x": 0, "y": 0, "w": 375, "h": 812},
        },
        {
            "selector": "html",
            "tag": "html",
            "route": "/about",
            "viewport": "375x812",
            "computed": {"backgroundColor": "rgb(248, 250, 252)"},
            "depth": 0,
            "bbox": {"x": 0, "y": 0, "w": 375, "h": 812},
        },
        {
            "selector": ".low-contrast",
            "route": "/about",
            "viewport": "375x812",
            "text": "这段文字对比度刻意偏低，供 contrast 通道候选。",
            "bbox": {"x": 16, "y": 200, "w": 300, "h": 24},
            "depth": 2,
            "computed": {
                "color": "rgb(200, 208, 220)",
                "backgroundColor": "rgba(0, 0, 0, 0)",
                "fontSize": "16px",
                "lineHeight": "24px",
                "fontWeight": "400",
            },
        },
    ]


def home_1440_elements():
    return [
        {
            "selector": "html",
            "route": "/",
            "viewport": "1440x900",
            "scrollWidth": 1440,
            "clientWidth": 1440,
            "bbox": {"x": 0, "y": 0, "w": 1440, "h": 900},
        },
        {
            "selector": "[data-testid=overlap-a]",
            "route": "/",
            "viewport": "1440x900",
            "interactive": True,
            "bbox": {"x": 100, "y": 400, "w": 120, "h": 48},
            "text": "A",
        },
        {
            "selector": "[data-testid=overlap-b]",
            "route": "/",
            "viewport": "1440x900",
            "interactive": True,
            "bbox": {"x": 140, "y": 412, "w": 120, "h": 48},
            "text": "B",
        },
        {
            "selector": "[data-testid=zero-btn]",
            "route": "/",
            "viewport": "1440x900",
            "interactive": True,
            "bbox": {"x": 0, "y": 700, "w": 0, "h": 0},
            "text": "hidden",
        },
    ]


def about_1440_elements():
    return [
        {
            "selector": "html",
            "route": "/about",
            "viewport": "1440x900",
            "scrollWidth": 1440,
            "clientWidth": 1440,
            "bbox": {"x": 0, "y": 0, "w": 1440, "h": 900},
        },
        {
            "selector": "html",
            "tag": "html",
            "route": "/about",
            "viewport": "1440x900",
            "computed": {"backgroundColor": "rgb(248, 250, 252)"},
            "depth": 0,
            "bbox": {"x": 0, "y": 0, "w": 1440, "h": 900},
        },
        {
            "selector": ".low-contrast",
            "route": "/about",
            "viewport": "1440x900",
            "text": "这段文字对比度刻意偏低，供 contrast 通道候选。",
            "bbox": {"x": 100, "y": 200, "w": 400, "h": 24},
            "depth": 2,
            "computed": {
                "color": "rgb(200, 208, 220)",
                "backgroundColor": "rgba(0, 0, 0, 0)",
                "fontSize": "16px",
                "lineHeight": "24px",
                "fontWeight": "400",
            },
        },
    ]


def write_cell(captures: Path, stem: str, route: str, viewport: str, elements) -> dict:
    write_json(
        captures / f"{stem}__elements.json",
        {"route": route, "viewport": viewport, "elements": elements},
    )
    return {
        "route": route,
        "viewport": viewport,
        "stem": stem,
        "status": "ok",
        "elements_json": f"{stem}__elements.json",
        "viewport_png": None,
    }


def build_captures(captures: Path) -> None:
    items = [
        write_cell(captures, "home__375x812", "/", "375x812", home_375_elements()),
        write_cell(captures, "about__375x812", "/about", "375x812", about_375_elements()),
        write_cell(captures, "home__1440x900", "/", "1440x900", home_1440_elements()),
        write_cell(captures, "about__1440x900", "/about", "1440x900", about_1440_elements()),
    ]
    write_json(
        captures / "MANIFEST.json",
        {
            "version": 1,
            "base_url": "http://127.0.0.1:5173",
            "routes": ["/", "/about"],
            "viewports": ["375x812", "1440x900"],
            "backend": "fixtures",
            "items": items,
        },
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="ibh-phase1-e2e-") as td:
        root = Path(td)
        init_mod.init_state(
            root,
            routes=["/", "/about"],
            viewports=["375x812", "1440x900"],
            base_url="http://127.0.0.1:5173",
        )
        # Simulate L2 (captures exist)
        state_path = root / ".bug-hunter" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["surfaces"]["web"]["degrade_level"] = "L2"
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        captures = root / ".bug-hunter" / "runs" / "run-1" / "captures"
        build_captures(captures)

        summary1 = hr.run_hunt_round(
            root=root,
            run_id="run-1",
            skip_capture=True,
            captures=captures,
            write_candidates=True,
            dynamic_cmd=None,
        )
        print("=== run-1 ===")
        print(json.dumps(summary1, ensure_ascii=False, indent=2))

        required_rules = {
            "overflow-x",
            "touch-target",
            "overlap-interactive",
            "zero-size",
            "contrast-text",
        }
        found = set(summary1.get("by_rule") or {})
        missing = sorted(required_rules - found)
        assert not missing, f"missing rules: {missing}"

        # Viewport-specific fingerprints: overlap at 375 and 1440 are distinct.
        fp_path = root / ".bug-hunter" / "fingerprints.json"
        fps = json.loads(fp_path.read_text(encoding="utf-8"))
        overlap_vps = {
            e.get("viewport")
            for e in fps["entries"].values()
            if e.get("rule_id") == "overlap-interactive"
        }
        assert "375x812" in overlap_vps and "1440x900" in overlap_vps, overlap_vps

        # Second round: pure dedupe
        summary2 = hr.run_hunt_round(
            root=root, run_id="run-2", skip_capture=True, captures=captures
        )
        print("=== run-2 ===")
        print(json.dumps(summary2, ensure_ascii=False, indent=2))
        assert summary2["new_count"] == 0
        assert summary2["known_count"] == summary1["findings_total"]

        # Fix gate: simulate fixing overflow-x only (remove root overflow, keep other defects)
        fixed_captures = root / ".bug-hunter" / "runs" / "run-fix" / "captures"
        build_captures(fixed_captures)
        fixed_home = json.loads(
            (fixed_captures / "home__375x812__elements.json").read_text(encoding="utf-8")
        )
        for el in fixed_home["elements"]:
            if el.get("selector") == "html":
                el["scrollWidth"] = 375
        write_json(fixed_captures / "home__375x812__elements.json", fixed_home)

        # Register "known" set already includes pre-fix findings; new fingerprints in post-fix
        # should not include overflow-x@home@375. zero_new will flag NEW issues only.
        # Pre-seed fingerprints for remaining intentional defects so zero_new is clean
        # except we intentionally keep them as known from run-1.
        bug = {
            "id": "bug-overflow-home-375",
            "rule_id": "overflow-x",
            "location": {"route": "/", "viewport": "375x812", "selector": "html"},
            "run_id": "run-fix",
        }
        write_json(root / ".bug-hunter" / "bugs" / "confirmed" / "bug-overflow-home-375.json", bug)

        # Create dummy baselines with Pillow if available so pixel gate runs
        baseline_dir = root / ".bug-hunter" / "baselines" / "web"
        try:
            from PIL import Image

            baseline_dir.mkdir(parents=True, exist_ok=True)
            for stem in (
                "home__375x812",
                "about__375x812",
                "home__1440x900",
                "about__1440x900",
            ):
                Image.new("RGB", (8, 8), (240, 240, 240)).save(baseline_dir / f"{stem}.png")
            # current "captures" have no pngs — compare only matches viewport pngs; skip ok
        except ImportError:
            pass

        gate = fg.run_fix_gate(
            root=root,
            bug=bug,
            captures_dir=fixed_captures,
            baseline_dir=baseline_dir,
            regression_mode="matrix",
        )
        print("=== fix_gate ===")
        print(json.dumps(gate, ensure_ascii=False, indent=2))
        assert gate["checks"]["target_cleared"]["ok"], gate["checks"]["target_cleared"]
        # Remaining intentional defects are already known fingerprints → zero_new ok
        assert gate["checks"]["zero_new_layout"]["ok"], gate["checks"]["zero_new_layout"]
        assert gate["ok"], gate

        print("PHASE1_FIXTURE_E2E_OK")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
