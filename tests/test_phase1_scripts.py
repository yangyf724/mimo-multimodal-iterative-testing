import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mmit" / "scripts"))

import capture_web as cw  # noqa: E402
import contrast_probe as cp  # noqa: E402
import fix_gate as fg  # noqa: E402
import hunt_round as hr  # noqa: E402
import init_state as init_mod  # noqa: E402
import layout_probe as lp  # noqa: E402
import visual_diff as vd  # noqa: E402


class TestCaptureHelpers(unittest.TestCase):
    def test_route_slug(self):
        self.assertEqual(cw.route_slug("/"), "home")
        self.assertEqual(cw.route_slug("/about"), "about")
        self.assertEqual(cw.route_slug("/users/list"), "users-list")

    def test_parse_viewport(self):
        self.assertEqual(cw.parse_viewport("375x812"), (375, 812))
        self.assertEqual(cw.parse_viewport(" 1440 x 900 "), (1440, 900))
        with self.assertRaises(ValueError):
            cw.parse_viewport("wide")

    def test_expand_matrix(self):
        cells = cw.expand_matrix(["/", "/about"], ["375x812", "1440x900"])
        self.assertEqual(len(cells), 4)
        self.assertEqual(cells[0]["stem"], "home__375x812")
        self.assertEqual(cells[3]["viewport"], "1440x900")

    def test_normalize_element_schema(self):
        raw = {
            "selector": "button",
            "tag": "button",
            "interactive": True,
            "bbox": {"x": 1, "y": 2, "w": 3, "h": 4},
            "computed": {"color": "rgb(0,0,0)"},
            "text": "hi",
        }
        el = cw.normalize_element(raw, route="/", viewport="375x812")
        self.assertEqual(el["route"], "/")
        self.assertEqual(el["viewport"], "375x812")
        self.assertEqual(el["bbox"]["w"], 3.0)
        self.assertTrue(el["interactive"])

    def test_manifest_unavailable_backend(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".mmit").mkdir()
            (root / ".mmit" / "state.json").write_text(
                json.dumps(
                    {
                        "surfaces": {
                            "web": {
                                "base_url": "http://127.0.0.1:5173",
                                "routes": ["/"],
                                "viewports": ["375x812"],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            result = cw.run_capture(
                root=root,
                base_url=None,
                routes=None,
                viewports=None,
                out=root / "captures",
                run_id="run-1",
                timeout_ms=1000,
                backend_force="unavailable",
            )
            self.assertEqual(result["exit"], cw.EXIT_NO_BROWSER)
            self.assertEqual(result["backend"], "unavailable")
            manifest = json.loads((root / "captures" / "MANIFEST.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["backend"], "unavailable")
            self.assertIn("error", manifest)


class TestLayoutPhase1(unittest.TestCase):
    def test_touch_target(self):
        elements = [
            {
                "selector": "[data-testid=tiny]",
                "route": "/",
                "viewport": "375x812",
                "interactive": True,
                "bbox": {"x": 10, "y": 10, "w": 24, "h": 20},
                "text": "x",
            }
        ]
        findings = lp.check_touch_target(elements, touch_target_px=44)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "touch-target")
        self.assertEqual(findings[0]["core_assertion_digest"], "touch-target|below-min")

    def test_touch_target_ok(self):
        elements = [
            {
                "selector": "button",
                "interactive": True,
                "bbox": {"x": 0, "y": 0, "w": 120, "h": 48},
            }
        ]
        self.assertEqual(lp.check_touch_target(elements), [])

    def test_overlap_interactive(self):
        elements = [
            {
                "selector": "[data-testid=a]",
                "route": "/",
                "viewport": "1440x900",
                "interactive": True,
                "bbox": {"x": 0, "y": 0, "w": 120, "h": 48},
            },
            {
                "selector": "[data-testid=b]",
                "route": "/",
                "viewport": "1440x900",
                "interactive": True,
                "bbox": {"x": 40, "y": 12, "w": 120, "h": 48},
            },
        ]
        findings = lp.check_overlap_interactive(elements, overlap_ratio=0.2)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "overlap-interactive")
        self.assertGreater(findings[0]["metrics"]["overlap_ratio"], 0.2)

    def test_overlap_no_false_positive(self):
        elements = [
            {
                "selector": "a",
                "interactive": True,
                "bbox": {"x": 0, "y": 0, "w": 10, "h": 10},
            },
            {
                "selector": "b",
                "interactive": True,
                "bbox": {"x": 100, "y": 0, "w": 10, "h": 10},
            },
        ]
        self.assertEqual(lp.check_overlap_interactive(elements), [])

    def test_zero_size(self):
        elements = [
            {
                "selector": "[data-testid=zero]",
                "interactive": True,
                "bbox": {"x": 0, "y": 0, "w": 0, "h": 0},
                "text": "hidden",
            }
        ]
        findings = lp.check_zero_size(elements)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "zero-size")

    def test_off_canvas(self):
        elements = [
            {
                "selector": "[data-testid=far]",
                "interactive": True,
                "bbox": {"x": 2000, "y": 10, "w": 40, "h": 20},
            }
        ]
        findings = lp.check_off_canvas(elements, viewport_width=375, viewport_height=812)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "off-canvas")

    def test_text_clip_skips_ellipsis(self):
        elements = [
            {
                "selector": "p",
                "text": "hello world this is long",
                "scrollWidth": 200,
                "clientWidth": 100,
                "text_overflow": "ellipsis",
            }
        ]
        self.assertEqual(lp.check_text_clip(elements), [])

    def test_text_clip_fires(self):
        elements = [
            {
                "selector": "p",
                "route": "/",
                "viewport": "375x812",
                "text": "hello world",
                "scrollWidth": 200,
                "clientWidth": 100,
                "text_overflow": "visible",
            }
        ]
        findings = lp.check_text_clip(elements)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "text-clip")

    def test_run_layout_rules_filter(self):
        elements = [
            {
                "selector": "button",
                "interactive": True,
                "bbox": {"x": 0, "y": 0, "w": 20, "h": 20},
                "text": "x",
            }
        ]
        findings = lp.run_layout_rules(
            elements, viewport_width=375, viewport_height=812, rules=["touch-target"]
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "touch-target")

    def test_overflow_x_still_works(self):
        elements = [
            {
                "selector": "html",
                "scrollWidth": 420,
                "clientWidth": 375,
                "bbox": {"x": 0, "y": 0, "w": 375, "h": 812},
            }
        ]
        findings = lp.check_overflow_x(elements, viewport_width=375)
        self.assertEqual(findings[0]["rule_id"], "overflow-x")


class TestContrastProbe(unittest.TestCase):
    def test_parse_color(self):
        self.assertEqual(cp.parse_css_color("rgb(150, 150, 150)"), (150.0, 150.0, 150.0, 1.0))
        self.assertEqual(cp.parse_css_color("rgba(0,0,0,0.5)")[3], 0.5)
        self.assertIsNone(cp.parse_css_color("transparent"))

    def test_contrast_ratio_known(self):
        # white vs black = 21
        ratio = cp.contrast_ratio((255, 255, 255), (0, 0, 0))
        self.assertAlmostEqual(ratio, 21.0, places=1)

    def test_low_contrast_finding(self):
        elements = [
            {
                "selector": "html",
                "tag": "html",
                "computed": {"backgroundColor": "rgb(248, 250, 252)"},
                "depth": 0,
            },
            {
                "selector": ".low-contrast",
                "route": "/about",
                "viewport": "375x812",
                "text": "这段文字对比度刻意偏低",
                "bbox": {"x": 0, "y": 0, "w": 300, "h": 20},
                "depth": 2,
                "computed": {
                    "color": "rgb(200, 208, 220)",
                    "backgroundColor": "rgba(0,0,0,0)",
                    "fontSize": "16px",
                    "lineHeight": "24px",
                    "fontWeight": "400",
                },
            },
        ]
        findings = cp.check_contrast_text(elements, min_contrast=4.5)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "contrast-text")
        self.assertLess(findings[0]["metrics"]["contrast_ratio"], 4.5)
        self.assertEqual(findings[0]["core_assertion_digest"], "contrast-text|below-min")

    def test_large_text_threshold(self):
        elements = [
            {
                "selector": "html",
                "computed": {"backgroundColor": "rgb(255,255,255)"},
                "depth": 0,
            },
            {
                "selector": "h1",
                "text": "Title",
                "bbox": {"x": 0, "y": 0, "w": 200, "h": 40},
                "depth": 1,
                "computed": {
                    "color": "rgb(100,100,100)",
                    "backgroundColor": "rgba(0,0,0,0)",
                    "fontSize": "28px",
                    "fontWeight": "700",
                },
            },
        ]
        # #646464 on white is ~5.9 — passes normal too; craft failing large but not huge
        elements[1]["computed"]["color"] = "rgb(140,140,140)"
        findings = cp.check_contrast_text(elements, min_contrast=4.5, large_text_min_contrast=3.0)
        self.assertEqual(findings, [])

    def test_font_too_small(self):
        elements = [
            {
                "selector": "span",
                "text": "tiny",
                "bbox": {"x": 0, "y": 0, "w": 50, "h": 10},
                "computed": {"fontSize": "10px"},
            }
        ]
        findings = cp.check_font_too_small(elements, font_too_small_px=12)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "font-too-small")

    def test_line_height_tight(self):
        elements = [
            {
                "selector": "p",
                "text": "line one\nline two",
                "computed": {"fontSize": "16px", "lineHeight": "16px"},
            }
        ]
        findings = cp.check_line_height_tight(elements, min_ratio=1.2)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "line-height-tight")


class TestVisualDiff(unittest.TestCase):
    def _make_png(self, path: Path, color=(255, 0, 0), size=(20, 10)):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")
        img = Image.new("RGB", size, color)
        img.save(path)

    def test_snapshot_and_compare_same(self):
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            self.skipTest("Pillow not available")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            captures = root / "captures"
            baselines = root / "baselines"
            captures.mkdir()
            self._make_png(captures / "home__375x812__viewport.png", (10, 20, 30))
            snap = vd.snapshot_baselines(captures, baselines)
            self.assertEqual(len(snap["created"]), 1)
            result = vd.compare_captures(captures, baselines, threshold=0.01)
            self.assertTrue(result["ok"])
            self.assertEqual(result["status"], "ok")

    def test_compare_detects_change(self):
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            self.skipTest("Pillow not available")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            captures = root / "captures"
            baselines = root / "baselines"
            captures.mkdir()
            self._make_png(captures / "home__375x812__viewport.png", (10, 20, 30))
            vd.snapshot_baselines(captures, baselines)
            self._make_png(captures / "home__375x812__viewport.png", (200, 10, 10))
            result = vd.compare_captures(captures, baselines, threshold=0.01)
            self.assertFalse(result["ok"])
            self.assertEqual(result["findings"][0]["rule_id"], "visual-diff")

    def test_size_mismatch(self):
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            self.skipTest("Pillow not available")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            captures = root / "captures"
            baselines = root / "baselines"
            captures.mkdir()
            self._make_png(captures / "home__375x812__viewport.png", (0, 0, 0), size=(10, 10))
            vd.snapshot_baselines(captures, baselines)
            self._make_png(captures / "home__375x812__viewport.png", (0, 0, 0), size=(20, 10))
            result = vd.compare_captures(captures, baselines, threshold=0.01)
            self.assertEqual(result["results"][0]["reason"], "size-mismatch")

    def test_approve_intentional(self):
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            self.skipTest("Pillow not available")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            captures = root / "captures"
            baselines = root / "baselines"
            captures.mkdir()
            self._make_png(captures / "home__375x812__viewport.png", (1, 2, 3))
            result = vd.approve_intentional(
                captures, baselines, root, route="/", viewport="375x812", reason="btn resize"
            )
            self.assertTrue(result["ok"])
            self.assertEqual(len(result["approved"]), 1)
            self.assertTrue((baselines / "home__375x812.png").exists())
            approvals = vd.load_approvals(root)
            self.assertEqual(len(approvals), 1)


class TestFixGate(unittest.TestCase):
    def _write_elements(self, path: Path, elements, route="/", viewport="375x812"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"route": route, "viewport": viewport, "elements": elements}),
            encoding="utf-8",
        )

    def test_target_cleared_and_zero_new(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bh = root / ".mmit"
            bh.mkdir()
            init_mod.init_state(root, routes=["/"], viewports=["375x812"])
            captures = root / "captures"
            captures.mkdir()
            # post-fix: clean page
            self._write_elements(
                captures / "home__375x812__elements.json",
                [
                    {
                        "selector": "html",
                        "scrollWidth": 375,
                        "clientWidth": 375,
                        "bbox": {"x": 0, "y": 0, "w": 375, "h": 812},
                    },
                    {
                        "selector": "button",
                        "interactive": True,
                        "bbox": {"x": 10, "y": 10, "w": 120, "h": 48},
                        "text": "ok",
                    },
                ],
            )
            (captures / "MANIFEST.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "route": "/",
                                "viewport": "375x812",
                                "stem": "home__375x812",
                                "status": "ok",
                                "elements_json": "home__375x812__elements.json",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            bug = {
                "id": "bug-0001",
                "rule_id": "overflow-x",
                "location": {"route": "/", "viewport": "375x812", "selector": "html"},
                "run_id": "run-fix",
            }
            result = fg.run_fix_gate(
                root=root,
                bug=bug,
                captures_dir=captures,
                baseline_dir=root / "baselines",
                regression_mode="matrix",
            )
            self.assertTrue(result["checks"]["target_cleared"]["ok"])
            self.assertTrue(result["checks"]["zero_new_layout"]["ok"])
            self.assertTrue(result["ok"])

    def test_target_not_cleared(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_mod.init_state(root, routes=["/"], viewports=["375x812"])
            captures = root / "captures"
            captures.mkdir()
            self._write_elements(
                captures / "home__375x812__elements.json",
                [
                    {
                        "selector": "html",
                        "route": "/",
                        "viewport": "375x812",
                        "scrollWidth": 420,
                        "clientWidth": 375,
                        "bbox": {"x": 0, "y": 0, "w": 375, "h": 812},
                    }
                ],
            )
            (captures / "MANIFEST.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "route": "/",
                                "viewport": "375x812",
                                "stem": "home__375x812",
                                "status": "ok",
                                "elements_json": "home__375x812__elements.json",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            bug = {
                "id": "bug-0001",
                "rule_id": "overflow-x",
                "location": {"route": "/", "viewport": "375x812"},
            }
            result = fg.run_fix_gate(
                root=root,
                bug=bug,
                captures_dir=captures,
                baseline_dir=root / "baselines",
            )
            self.assertFalse(result["checks"]["target_cleared"]["ok"])
            self.assertFalse(result["ok"])

    def test_missing_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_mod.init_state(root)
            bug = {"id": "x", "rule_id": "overflow-x", "location": {}}
            result = fg.run_fix_gate(
                root=root,
                bug=bug,
                captures_dir=root / "nope",
                baseline_dir=root / "baselines",
            )
            self.assertFalse(result["ok"])


class TestHuntRound(unittest.TestCase):
    def test_skip_capture_with_fixtures(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_mod.init_state(root, routes=["/"], viewports=["375x812"])
            captures = root / ".mmit" / "hunts" / "runs" / "run-1" / "captures"
            captures.mkdir(parents=True)
            (captures / "home__375x812__elements.json").write_text(
                json.dumps(
                    {
                        "route": "/",
                        "viewport": "375x812",
                        "elements": [
                            {
                                "selector": "html",
                                "route": "/",
                                "viewport": "375x812",
                                "scrollWidth": 420,
                                "clientWidth": 375,
                                "bbox": {"x": 0, "y": 0, "w": 375, "h": 812},
                            },
                            {
                                "selector": "[data-testid=tiny]",
                                "route": "/",
                                "viewport": "375x812",
                                "interactive": True,
                                "bbox": {"x": 1, "y": 1, "w": 20, "h": 16},
                                "text": "t",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (captures / "MANIFEST.json").write_text(
                json.dumps(
                    {
                        "backend": "fixtures",
                        "items": [
                            {
                                "route": "/",
                                "viewport": "375x812",
                                "stem": "home__375x812",
                                "status": "ok",
                                "elements_json": "home__375x812__elements.json",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            summary = hr.run_hunt_round(
                root=root,
                run_id="run-1",
                skip_capture=True,
                captures=captures,
                write_candidates=True,
            )
            self.assertGreaterEqual(summary["findings_total"], 2)
            self.assertIn("overflow-x", summary["by_rule"])
            self.assertIn("touch-target", summary["by_rule"])
            self.assertEqual(summary["new_count"], summary["findings_total"])
            self.assertTrue((root / ".mmit" / "hunts" / "runs" / "run-1" / "summary.json").exists())
            # second round should dedupe
            summary2 = hr.run_hunt_round(
                root=root, run_id="run-2", skip_capture=True, captures=captures
            )
            self.assertEqual(summary2["new_count"], 0)
            self.assertEqual(summary2["known_count"], summary["findings_total"])

    def test_dynamic_fail_finding(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_mod.init_state(root)
            cmd = f'"{sys.executable}" -c "raise SystemExit(1)"'
            findings = hr.run_dynamic(cmd, root=root)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["modality"], "code")


class TestInitStatePhase1(unittest.TestCase):
    def test_phase1_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = init_mod.init_state(root)
            self.assertGreaterEqual(state["phase"], 1)
            oracle = state["visual_oracle"]
            self.assertIn("overlap_ratio", oracle)
            self.assertIn("visual_diff_threshold", oracle)
            self.assertIn("line_height_min_ratio", oracle)
            # Phase 2 defaults retained
            self.assertIn("safe_inset_pct", oracle)
            self.assertEqual(state["surfaces"]["canvas"]["kind"], "scene-json")


class TestReviewCriticals(unittest.TestCase):
    """Regression tests for independent-review critical findings."""

    def test_interactive_selectors_exclude_data_testid(self):
        self.assertNotIn("[data-testid]", cw.INTERACTIVE_SELECTORS)

    def test_container_with_testid_not_interactive_in_layout_overlap(self):
        # overlap-stage (container) + two buttons: only A~B should fire.
        elements = [
            {
                "selector": "[data-testid=overlap-stage]",
                "route": "/",
                "viewport": "1440x900",
                "interactive": False,
                "bbox": {"x": 0, "y": 0, "w": 200, "h": 80},
            },
            {
                "selector": "[data-testid=a]",
                "route": "/",
                "viewport": "1440x900",
                "interactive": True,
                "bbox": {"x": 0, "y": 0, "w": 120, "h": 48},
            },
            {
                "selector": "[data-testid=b]",
                "route": "/",
                "viewport": "1440x900",
                "interactive": True,
                "bbox": {"x": 40, "y": 12, "w": 120, "h": 48},
            },
        ]
        findings = lp.check_overlap_interactive(elements, overlap_ratio=0.2)
        self.assertEqual(len(findings), 1)
        self.assertIn("a", findings[0]["metrics"]["selectors"][0] + findings[0]["metrics"]["selectors"][1])

    def test_body_root_not_double_counted_on_right_overflow(self):
        elements = [
            {
                "selector": "html",
                "route": "/",
                "viewport": "375x812",
                "scrollWidth": 400,
                "clientWidth": 375,
                "bbox": {"x": 0, "y": 0, "w": 400, "h": 812},
            },
            {
                "selector": "body",
                "route": "/",
                "viewport": "375x812",
                "scrollWidth": 400,
                "clientWidth": 375,
                "bbox": {"x": 0, "y": 0, "w": 400, "h": 812},
            },
        ]
        findings = lp.check_overflow_x(elements, viewport_width=375)
        html_body = [
            f for f in findings if f["location"]["selector"] in ("html", "body")
        ]
        # Only one page-level finding; body must not add a second right-overflow.
        self.assertEqual(len(html_body), 1)

    def test_contrast_prefers_nearest_ancestor_background(self):
        elements = [
            {
                "selector": "html",
                "tag": "html",
                "depth": 0,
                "computed": {"backgroundColor": "rgb(255,255,255)"},
            },
            {
                "selector": "body",
                "tag": "body",
                "depth": 1,
                "computed": {"backgroundColor": "rgb(255,255,255)"},
            },
            {
                "selector": ".parent-red",
                "depth": 3,
                "computed": {"backgroundColor": "rgb(220,0,0)"},
            },
            {
                "selector": ".child-text",
                "route": "/",
                "viewport": "375x812",
                "depth": 5,
                "text": "hello",
                "bbox": {"x": 0, "y": 0, "w": 100, "h": 20},
                "computed": {
                    "color": "rgb(255,255,255)",
                    "backgroundColor": "rgba(0,0,0,0)",
                    "fontSize": "16px",
                    "lineHeight": "24px",
                    "fontWeight": "400",
                },
            },
        ]
        bg, assumed = cp.resolve_background(elements[3], elements)
        self.assertFalse(assumed)
        # Nearest opaque ancestor is parent-red, not body/html white.
        self.assertEqual(bg, (220.0, 0.0, 0.0))

    def test_empty_unavailable_manifest_does_not_false_quiet(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_mod.init_state(root, routes=["/"], viewports=["375x812"])
            captures = root / ".mmit" / "hunts" / "runs" / "run-1" / "captures"
            captures.mkdir(parents=True)
            (captures / "MANIFEST.json").write_text(
                json.dumps(
                    {
                        "backend": "unavailable",
                        "items": [],
                        "error": "No Playwright backend",
                    }
                ),
                encoding="utf-8",
            )
            summary = hr.run_hunt_round(
                root=root,
                run_id="run-1",
                skip_capture=True,
                captures=captures,
                dynamic_cmd=f'"{sys.executable}" -c "raise SystemExit(0)"',
            )
            # Must not credit web strategies from an empty unavailable manifest.
            self.assertNotIn("layout-geom", summary["strategies"])
            self.assertNotIn("contrast-type", summary["strategies"])
            self.assertNotEqual(summary["degrade_level"], "L2")
            # At L1 only code is required; quiet with dynamic-only is legitimate.
            # The false-quiet bug was elevating to L2 and claiming web coverage.
            self.assertEqual(summary["degrade_level"], "L1")
            self.assertIn("dynamic", summary["strategies"])

    def test_depth_preserved_in_normalize_element(self):
        el = cw.normalize_element(
            {"selector": "p", "depth": 4, "bbox": {"x": 0, "y": 0, "w": 1, "h": 1}},
            route="/",
            viewport="375x812",
        )
        self.assertEqual(el["depth"], 4)

    def test_capture_source_has_depth_of(self):
        # Guard: both Node runner and Python evaluate must compute real depth.
        src = Path(cw.__file__).read_text(encoding="utf-8")
        self.assertGreaterEqual(src.count("depthOf"), 2)
        self.assertNotIn('"depth": 0,\n                          inViewport', src)


if __name__ == "__main__":
    unittest.main()
