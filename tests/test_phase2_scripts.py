#!/usr/bin/env python3
"""Phase 2 unit tests: canvas_probe, ux_flow, vlm_audit, capture shards, hunt_round."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "mmit" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import canvas_probe  # noqa: E402
import capture_web  # noqa: E402
import hunt_round  # noqa: E402
import ux_flow  # noqa: E402
import vlm_audit  # noqa: E402


class TestCanvasProbe(unittest.TestCase):
    def _poster_item(self) -> dict:
        return canvas_probe.normalize_item(
            {
                "id": "poster",
                "export_size": "800x600",
                "spec": {"safe_inset_pct": 5, "export_target": "1080x1920"},
                "objects": [
                    {
                        "id": "title",
                        "type": "text",
                        "x": 10,
                        "y": 2,
                        "w": 300,
                        "h": 48,
                        "zIndex": 2,
                        "opacity": 1,
                    },
                    {
                        "id": "bg",
                        "type": "shape",
                        "x": 0,
                        "y": 0,
                        "w": 800,
                        "h": 600,
                        "zIndex": 3,
                        "opacity": 1,
                    },
                    {
                        "id": "cta",
                        "type": "cta",
                        "x": 40,
                        "y": 480,
                        "w": 120,
                        "h": 40,
                        "zIndex": 1,
                        "primary": True,
                        "opacity": 1,
                    },
                ],
                "assets": [
                    {
                        "id": "hero",
                        "display_w": 200,
                        "display_h": 200,
                        "pixel_w": 80,
                        "pixel_h": 120,
                    }
                ],
            }
        )

    def test_safe_area_violation(self):
        item = self._poster_item()
        findings = canvas_probe.check_safe_area(item)
        rules = {f["rule_id"] for f in findings}
        self.assertIn("safe-area-violation", rules)
        title_f = next(f for f in findings if f["location"].get("canvas_object_id") == "title")
        self.assertEqual(title_f["modality"], "canvas")
        self.assertEqual(title_f["evidence_level_target"], "L3")

    def test_safe_area_ok_when_inset_clear(self):
        item = self._poster_item()
        for obj in item["objects"]:
            if obj["id"] == "title":
                obj["y"] = 100
                obj["x"] = 100
        findings = canvas_probe.check_safe_area(item)
        self.assertEqual(findings, [])

    def test_export_mismatch(self):
        item = self._poster_item()
        findings = canvas_probe.check_export_mismatch(item, export_target="1080x1920")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "export-mismatch")

    def test_low_res_and_aspect(self):
        item = self._poster_item()
        low = canvas_probe.check_low_res_assets(item)
        aspect = canvas_probe.check_aspect_distort(item)
        self.assertEqual(len(low), 1)
        self.assertEqual(low[0]["category"], "canvas-asset")
        self.assertEqual(len(aspect), 1)

    def test_z_order_occlusion(self):
        item = canvas_probe.normalize_item(
            {
                "id": "cover",
                "export_size": "100x100",
                "objects": [
                    {"id": "label", "type": "text", "x": 0, "y": 0, "w": 100, "h": 100, "zIndex": 0, "opacity": 1},
                    {"id": "panel", "type": "shape", "x": 0, "y": 0, "w": 100, "h": 100, "zIndex": 5, "opacity": 1},
                ],
            }
        )
        findings = canvas_probe.check_z_order_occlusion(item)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["location"]["canvas_object_id"], "label")

    def test_hierarchy_flat_is_deferred(self):
        item = canvas_probe.normalize_item(
            {
                "id": "poster",
                "export_size": "800x600",
                "objects": [
                    {"id": "cta", "type": "cta", "x": 10, "y": 10, "w": 20, "h": 10, "zIndex": 1},
                    {"id": "banner", "type": "text", "x": 0, "y": 0, "w": 700, "h": 400, "zIndex": 0},
                ],
            }
        )
        findings = canvas_probe.check_hierarchy_flat(item)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["status"], "deferred")
        self.assertEqual(findings[0]["evidence_level_target"], "L2")

    def test_run_canvas_items_counts(self):
        item = self._poster_item()
        result = canvas_probe.run_canvas_items([item], export_target="1080x1920")
        rules = {f["rule_id"] for f in result["findings"]}
        self.assertIn("safe-area-violation", rules)
        self.assertIn("export-mismatch", rules)
        self.assertIn("low-res-asset", rules)

    def test_load_scene_file(self):
        scene = ROOT / "examples" / "acceptance-demo" / "canvas" / "poster.scene.json"
        items = canvas_probe.load_items_from_path(scene)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "poster")
        result = canvas_probe.run_canvas_items(items, export_target="1080x1920")
        self.assertGreaterEqual(len(result["findings"]), 3)


class TestUxFlow(unittest.TestCase):
    def _elements(self) -> list[dict]:
        return [
            {
                "selector": "a[data-testid=dead-link]",
                "tag": "a",
                "route": "/",
                "viewport": "375x812",
                "href": "#",
                "interactive": True,
                "bbox": {"x": 1, "y": 1, "w": 80, "h": 20},
                "inViewport": True,
                "text": "占位",
            },
            {
                "selector": "[data-testid=flow-submit]",
                "tag": "button",
                "type": "submit",
                "route": "/",
                "viewport": "375x812",
                "interactive": True,
                "bbox": {"x": 1, "y": 40, "w": 80, "h": 32},
                "inViewport": True,
                "text": "提交",
            },
            {
                "selector": "[data-testid=empty-list]",
                "tag": "ul",
                "route": "/",
                "viewport": "375x812",
                "attrs": {"data-list-empty": "expected"},
                "bbox": {"x": 0, "y": 80, "w": 200, "h": 48},
                "inViewport": True,
                "visible_child_count": 0,
                "text": "",
            },
        ]

    def test_dead_link(self):
        findings = ux_flow.check_dead_link(self._elements())
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "dead-link")

    def test_dead_link_ok_on_real_href(self):
        els = self._elements()
        els[0]["href"] = "/about"
        self.assertEqual(ux_flow.check_dead_link(els), [])

    def test_missing_feedback(self):
        findings = ux_flow.check_missing_feedback(self._elements())
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "missing-feedback")
        self.assertTrue(findings[0]["inferred_oracle"])

    def test_missing_feedback_ok_when_error_present(self):
        els = self._elements()
        els.append(
            {
                "selector": "[data-testid=flow-error]",
                "tag": "div",
                "role": "alert",
                "bbox": {"x": 0, "y": 10, "w": 10, "h": 10},
                "inViewport": True,
                "text": "err",
            }
        )
        self.assertEqual(ux_flow.check_missing_feedback(els), [])

    def test_missing_empty_state(self):
        findings = ux_flow.check_missing_empty_state(self._elements())
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "missing-empty-state")

    def test_flow_step_fail(self):
        elements = self._elements()
        flow = {
            "id": "empty-submit",
            "route": "/",
            "viewport": "375x812",
            "symbols": {"formValid": False},
            "steps": [
                {
                    "id": "submit-empty",
                    "action": "click",
                    "target": "[data-testid=flow-submit]",
                    "pre": {"formValid": False, "[data-testid=flow-submit].visible": True},
                    "post": {"[data-testid=flow-error].visible": True},
                }
            ],
            "inferred_oracle": True,
        }
        result = ux_flow.evaluate_flow(flow, elements)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(len(result["findings"]), 1)
        self.assertEqual(result["findings"][0]["rule_id"], "ux-flow-step")

    def test_flow_step_pass(self):
        elements = self._elements()
        elements.append(
            {
                "selector": "[data-testid=flow-error]",
                "tag": "div",
                "bbox": {"x": 0, "y": 10, "w": 40, "h": 20},
                "inViewport": True,
                "text": "错误",
            }
        )
        flow = {
            "id": "empty-submit",
            "route": "/",
            "viewport": "375x812",
            "symbols": {"formValid": False},
            "steps": [
                {
                    "id": "submit-empty",
                    "action": "click",
                    "target": "[data-testid=flow-submit]",
                    "pre": {"formValid": False},
                    "post": {"[data-testid=flow-error].visible": True},
                }
            ],
        }
        result = ux_flow.evaluate_flow(flow, elements)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["findings"], [])

    def test_flow_unavailable_when_missing_element(self):
        flow = {
            "id": "x",
            "route": "/",
            "viewport": "375x812",
            "symbols": {},
            "steps": [
                {
                    "id": "s1",
                    "action": "click",
                    "target": "[data-testid=nope]",
                    "pre": {},
                    "post": {"[data-testid=nope].visible": True},
                }
            ],
        }
        # missing element -> visible False -> fail (not unavailable)
        result = ux_flow.evaluate_flow(flow, [])
        self.assertEqual(result["status"], "fail")
        # unavailable symbol
        flow2 = {
            "id": "y",
            "route": "/",
            "viewport": "375x812",
            "symbols": {},
            "steps": [
                {
                    "id": "s1",
                    "action": "click",
                    "target": "btn",
                    "pre": {"unknownSymbol": True},
                    "post": {},
                }
            ],
        }
        result2 = ux_flow.evaluate_flow(flow2, [])
        self.assertTrue(result2["unavailable"])
        self.assertEqual(result2["status"], "unavailable")


class TestVlmAudit(unittest.TestCase):
    def test_merge_consensus(self):
        view_a = {
            "view": "A",
            "candidates": [
                {
                    "title": "主按钮被裁切",
                    "problem": "CTA 右缘超出视口",
                    "confidence": 0.8,
                    "location": {"route": "/", "viewport": "375x812", "selector": "[data-testid=primary-cta]"},
                },
                {
                    "title": "颜色不好看",
                    "problem": "审美",
                    "location": {"route": "/", "viewport": "375x812"},
                },
            ],
        }
        view_b = {
            "view": "B",
            "candidates": [
                {
                    "title": "primary CTA overflow",
                    "problem": "按钮溢出",
                    "confidence": 0.7,
                    "location": {"route": "/", "viewport": "375x812", "selector": "[data-testid=primary-cta]"},
                }
            ],
        }
        consensus = vlm_audit.merge_views(view_a, view_b)
        self.assertEqual(len(consensus), 1)
        self.assertEqual(consensus[0]["rule_id"], "vlm-consensus")
        self.assertTrue(consensus[0]["inferred_oracle"])

    def test_no_consensus_when_disjoint(self):
        view_a = {
            "view": "A",
            "candidates": [
                {"title": "a", "location": {"route": "/a", "viewport": "375x812", "selector": "#a"}}
            ],
        }
        view_b = {
            "view": "B",
            "candidates": [
                {"title": "b", "location": {"route": "/b", "viewport": "375x812", "selector": "#b"}}
            ],
        }
        self.assertEqual(vlm_audit.merge_views(view_a, view_b), [])

    def test_cross_check_no_double_count(self):
        consensus = [
            {
                "rule_id": "vlm-consensus",
                "title": "主按钮被裁切",
                "problem": "CTA 溢出",
                "location": {
                    "route": "/",
                    "viewport": "375x812",
                    "selector": "[data-testid=primary-cta]",
                    "bbox": {"x": 300, "y": 10, "w": 100, "h": 40},
                },
                "metrics": {"views": ["A", "B"], "confidence": 0.8},
            }
        ]
        raw = [
            {
                "rule_id": "overflow-x",
                "title": "CTA overflow",
                "location": {
                    "route": "/",
                    "viewport": "375x812",
                    "selector": "[data-testid=primary-cta]",
                    "bbox": {"x": 300, "y": 10, "w": 100, "h": 40},
                },
                "metrics": {},
            }
        ]
        cross = vlm_audit.cross_check(consensus, raw)
        self.assertEqual(len(cross["standalone"]), 0)
        self.assertEqual(cross["merged_into_machine"], 1)
        self.assertTrue(raw[0]["metrics"].get("vlm_corroboration"))

    def test_scaffold(self):
        a, b = vlm_audit.scaffold_views(
            screenshot="x.png", route="/", viewport="375x812"
        )
        self.assertEqual(a["view"], "A")
        self.assertEqual(b["view"], "B")
        self.assertEqual(a["candidates"], [])


class TestCaptureShard(unittest.TestCase):
    def test_parse_shard(self):
        self.assertEqual(capture_web.parse_shard("0/2"), (0, 2))
        self.assertIsNone(capture_web.parse_shard(None))
        with self.assertRaises(ValueError):
            capture_web.parse_shard("2/2")
        with self.assertRaises(ValueError):
            capture_web.parse_shard("a")

    def test_assign_shard_cells(self):
        cells = capture_web.expand_matrix(["/", "/about"], ["375x812", "1440x900"])
        self.assertEqual(len(cells), 4)
        s0 = capture_web.assign_shard_cells(cells, 0, 2)
        s1 = capture_web.assign_shard_cells(cells, 1, 2)
        self.assertEqual(len(s0), 2)
        self.assertEqual(len(s1), 2)
        keys0 = {(c["route"], c["viewport"]) for c in s0}
        keys1 = {(c["route"], c["viewport"]) for c in s1}
        self.assertEqual(keys0 & keys1, set())
        self.assertEqual(keys0 | keys1, {(c["route"], c["viewport"]) for c in cells})

    def test_merge_shard_manifests(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            captures = root / "captures"
            for idx, route in enumerate(["/", "/about"]):
                shard = captures / f"shard-{idx}"
                shard.mkdir(parents=True)
                elements = {
                    "route": route,
                    "viewport": "375x812",
                    "elements": [
                        {
                            "selector": "html",
                            "tag": "html",
                            "bbox": {"x": 0, "y": 0, "w": 375, "h": 812},
                            "scrollWidth": 400,
                            "clientWidth": 375,
                        }
                    ],
                }
                (shard / "home__375x812__elements.json").write_text(
                    json.dumps(elements), encoding="utf-8"
                )
                # empty png placeholder
                (shard / "home__375x812__viewport.png").write_bytes(b"\x89PNG\r\n\x1a\n")
                manifest = capture_web.default_manifest(
                    base_url="http://127.0.0.1:5173",
                    routes=[route],
                    viewports=["375x812"],
                    backend="python-playwright",
                    items=[
                        {
                            "route": route,
                            "viewport": "375x812",
                            "stem": "home__375x812",
                            "status": "ok",
                            "viewport_png": "home__375x812__viewport.png",
                            "elements_json": "home__375x812__elements.json",
                        }
                    ],
                )
                manifest["shard"] = {"index": idx, "total": 2}
                (shard / f"MANIFEST.shard-{idx}.json").write_text(
                    json.dumps(manifest), encoding="utf-8"
                )
            result = capture_web.merge_shard_manifests(captures)
            self.assertTrue(result["ok"])
            self.assertEqual(len(result["items"]), 2)
            self.assertTrue((captures / "MANIFEST.json").exists())
            # artifacts copied to root
            self.assertTrue((captures / "home__375x812__elements.json").exists())


class TestHuntRoundPhase2(unittest.TestCase):
    def _write_minimal_state(self, root: Path, canvas_items: list) -> None:
        bh = root / ".mmit"
        (bh / "runs" / "run-p2" / "captures").mkdir(parents=True)
        (bh / "runs" / "run-p2" / "findings" / "raw").mkdir(parents=True)
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
                "canvas": {"kind": "scene-json", "items": canvas_items},
            },
            "visual_oracle": {"overflow_epsilon_px": 2},
            "convergence": {"quiet_streak": 0, "required_quiet_streak": 2},
        }
        (bh / "state.json").write_text(json.dumps(state), encoding="utf-8")
        (bh / "fingerprints.json").write_text(
            json.dumps({"version": 1, "entries": {}}), encoding="utf-8"
        )
        captures = bh / "runs" / "run-p2" / "captures"
        elements = {
            "route": "/",
            "viewport": "375x812",
            "elements": [
                {
                    "selector": "html",
                    "tag": "html",
                    "bbox": {"x": 0, "y": 0, "w": 375, "h": 812},
                    "scrollWidth": 375,
                    "clientWidth": 375,
                    "route": "/",
                    "viewport": "375x812",
                }
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

    def test_stub_canvas_does_not_elevate_l4(self):
        """Critical fix: missing/unloadable canvas source must not fake L4/quiet."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_minimal_state(
                root,
                canvas_items=[{"id": "ghost", "source": "does/not/exist.scene.json"}],
            )
            summary = hunt_round.run_hunt_round(
                root=root,
                run_id="run-p2",
                skip_capture=True,
                captures=root / ".mmit" / "hunts" / "runs" / "run-p2" / "captures",
            )
            self.assertEqual(summary.get("degrade_level"), "L3")
            self.assertNotIn("canvas-safe", summary.get("strategies") or [])
            self.assertNotIn("canvas", summary.get("by_modality") or {})
            conv = summary.get("convergence") or {}
            # canvas modality enabled but not covered → must not quiet
            self.assertFalse(conv.get("quiet"))

    def test_z_order_union_not_sum(self):
        """Two 60% overlapping occluders on the same strip must not sum to 100%."""
        item = canvas_probe.normalize_item(
            {
                "id": "stack",
                "export_size": "100x100",
                "objects": [
                    {
                        "id": "label",
                        "type": "text",
                        "x": 0,
                        "y": 0,
                        "w": 100,
                        "h": 100,
                        "zIndex": 0,
                        "opacity": 1,
                    },
                    {
                        "id": "p1",
                        "type": "shape",
                        "x": 0,
                        "y": 0,
                        "w": 60,
                        "h": 100,
                        "zIndex": 5,
                        "opacity": 1,
                    },
                    {
                        "id": "p2",
                        "type": "shape",
                        "x": 0,
                        "y": 0,
                        "w": 60,
                        "h": 100,
                        "zIndex": 6,
                        "opacity": 1,
                    },
                ],
            }
        )
        findings = canvas_probe.check_z_order_occlusion(item, min_coverage=0.98)
        self.assertEqual(findings, [])

    def test_full_bleed_bg_no_safe_area(self):
        item = canvas_probe.normalize_item(
            {
                "id": "p",
                "export_size": "800x600",
                "objects": [
                    {"id": "bg", "type": "shape", "x": 0, "y": 0, "w": 800, "h": 600, "zIndex": 0},
                    {"id": "title", "type": "text", "x": 50, "y": 50, "w": 200, "h": 40, "zIndex": 1},
                ],
            }
        )
        findings = canvas_probe.check_safe_area(item)
        ids = {f["location"].get("canvas_object_id") for f in findings}
        self.assertNotIn("bg", ids)

    def test_ux_and_canvas_in_fixtures(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bh = root / ".mmit"
            (bh / "runs" / "run-p2" / "captures").mkdir(parents=True)
            (bh / "runs" / "run-p2" / "findings" / "raw").mkdir(parents=True)
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
                                "source": "canvas/poster.scene.json",
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
            # canvas source relative to root
            canvas_dir = root / "canvas"
            canvas_dir.mkdir()
            scene = {
                "id": "poster",
                "export_size": "800x600",
                "spec": {"safe_inset_pct": 5, "export_target": "1080x1920"},
                "objects": [
                    {
                        "id": "title",
                        "type": "text",
                        "x": 5,
                        "y": 2,
                        "w": 100,
                        "h": 20,
                        "zIndex": 1,
                        "opacity": 1,
                    }
                ],
                "assets": [
                    {
                        "id": "a",
                        "display_w": 100,
                        "display_h": 100,
                        "pixel_w": 40,
                        "pixel_h": 40,
                    }
                ],
            }
            (canvas_dir / "poster.scene.json").write_text(json.dumps(scene), encoding="utf-8")

            captures = bh / "runs" / "run-p2" / "captures"
            elements = {
                "route": "/",
                "viewport": "375x812",
                "elements": [
                    {
                        "selector": "html",
                        "tag": "html",
                        "bbox": {"x": 0, "y": 0, "w": 375, "h": 812},
                        "scrollWidth": 500,
                        "clientWidth": 375,
                        "route": "/",
                        "viewport": "375x812",
                    },
                    {
                        "selector": "a[data-testid=dead]",
                        "tag": "a",
                        "href": "#",
                        "route": "/",
                        "viewport": "375x812",
                        "bbox": {"x": 1, "y": 1, "w": 40, "h": 16},
                        "inViewport": True,
                        "text": "x",
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

            summary = hunt_round.run_hunt_round(
                root=root,
                run_id="run-p2",
                skip_capture=True,
                captures=captures,
            )
            by_rule = summary.get("by_rule") or {}
            self.assertIn("overflow-x", by_rule)
            self.assertIn("dead-link", by_rule)
            self.assertIn("safe-area-violation", by_rule)
            self.assertIn("low-res-asset", by_rule)
            self.assertEqual(summary.get("degrade_level"), "L4")
            self.assertEqual(summary.get("degrade_elevated_by"), "canvas-items")
            self.assertIn("ux-flow", summary.get("strategies") or [])
            self.assertIn("canvas-safe", summary.get("strategies") or [])
            self.assertIn("canvas", summary.get("by_modality") or {})


if __name__ == "__main__":
    unittest.main()
