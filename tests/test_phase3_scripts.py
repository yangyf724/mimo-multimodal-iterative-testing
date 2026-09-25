#!/usr/bin/env python3
"""Phase 3 unit tests — stdlib only, no browser/node required."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "mmit-hunter" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import axe_gate  # noqa: E402
import baseline_lock  # noqa: E402
import discover_routes as dr  # noqa: E402
import export_report  # noqa: E402
import fp_feedback as fpf  # noqa: E402


SAMPLE_HTML = """
<html><body>
<nav>
  <a href="/">Home</a>
  <a href="/shop">Shop</a>
  <a href="/contact/">Contact</a>
  <a href="https://example.com/external">External</a>
  <a href="mailto:x@y.z">Mail</a>
  <a href="#">Hash</a>
  <a href="/styles.css">CSS</a>
  <a href="javascript:void(0)">JS</a>
</nav>
<a href="/shop?ref=1#top">Shop query</a>
</body></html>
"""

SAMPLE_SITEMAP = """<?xml version="1.0"?>
<urlset>
  <url><loc>http://127.0.0.1:5173/</loc></url>
  <url><loc>http://127.0.0.1:5173/about</loc></url>
  <url><loc>https://other.example/x</loc></url>
</urlset>
"""


class TestDiscoverRoutes(unittest.TestCase):
    def test_extract_links_same_origin(self):
        links = dr.extract_links(SAMPLE_HTML, "http://127.0.0.1:5173/")
        self.assertEqual(links, ["/", "/shop", "/contact"])

    def test_filters_static_and_junk(self):
        links = dr.filter_same_origin(
            ["/app.js", "/x.png", "#", "mailto:a@b.c", "/ok"], "http://127.0.0.1:5173"
        )
        self.assertEqual(links, ["/ok"])

    def test_parse_sitemap(self):
        routes = dr.parse_sitemap(SAMPLE_SITEMAP, "http://127.0.0.1:5173")
        self.assertEqual(routes, ["/", "/about"])

    def test_parse_package_routes(self):
        routes = dr.parse_package_routes(json.dumps({"routes": ["/", "/shop", "/shop"]}))
        self.assertEqual(routes, ["/", "/shop"])
        self.assertEqual(dr.parse_package_routes("not-json"), [])

    def test_rank_routes_priority_and_cap(self):
        ranked = dr.rank_routes(
            [
                {"route": "/late", "source": "html-links", "priority": 3},
                {"route": "/seed", "source": "seed", "priority": 0},
                {"route": "/late", "source": "package.json", "priority": 1},
            ],
            max_routes=2,
        )
        self.assertEqual([r["route"] for r in ranked], ["/seed", "/late"])
        self.assertEqual(ranked[1]["source"], "package.json")

    def test_rank_routes_preserves_document_order(self):
        ranked = dr.rank_routes(
            [
                {"route": "/zeta", "source": "html-links", "priority": 3},
                {"route": "/alpha", "source": "html-links", "priority": 3},
                {"route": "/beta", "source": "html-links", "priority": 3},
            ],
            max_routes=12,
        )
        self.assertEqual([r["route"] for r in ranked], ["/zeta", "/alpha", "/beta"])

    def test_write_state_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bh = root / ".bug-hunter"
            bh.mkdir()
            (bh / "state.json").write_text(
                json.dumps({"surfaces": {"web": {"routes": ["/"], "base_url": "http://x"}}}),
                encoding="utf-8",
            )
            result = dr.discover(
                base_url="http://127.0.0.1:5173",
                seeds=["/"],
                html=SAMPLE_HTML,
            )
            write_result = dr.write_state_routes(root, result)
            self.assertIn("/shop", write_result["routes"])
            self.assertIn("/contact", write_result["routes"])
            state = json.loads((bh / "state.json").read_text(encoding="utf-8"))
            self.assertIn("/shop", state["surfaces"]["web"]["routes"])
            self.assertTrue(state["surfaces"]["web"]["route_discovery"]["enabled"])


class TestFpFeedback(unittest.TestCase):
    def _finding(self, **kwargs):
        base = {
            "modality": "web-visual",
            "category": "ui-layout",
            "rule_id": "touch-target",
            "location": {
                "route": "/",
                "viewport": "375x812",
                "selector": "[data-testid=btn-tiny]",
            },
            "core_assertion_digest": "touch-target|below-min",
            "title": "tiny",
        }
        base.update(kwargs)
        return base

    def test_pattern_match_modes(self):
        f = self._finding()
        exact = {
            "match": "exact",
            "rule_id": "touch-target",
            "modality": "web-visual",
            "category": "ui-layout",
            "route": "/",
            "viewport": "375x812",
            "selector_pattern": "[data-testid=btn-tiny]",
        }
        self.assertTrue(fpf.pattern_matches(exact, f))
        exact_bad_vp = dict(exact, viewport="1440x900")
        self.assertFalse(fpf.pattern_matches(exact_bad_vp, f))
        sel = {
            "match": "selector+rule+route",
            "rule_id": "touch-target",
            "route": "/",
            "selector_pattern": "[data-testid=btn-tiny]",
        }
        self.assertTrue(fpf.pattern_matches(sel, f))
        self.assertFalse(fpf.pattern_matches(dict(sel, route="/about"), f))
        digest = {"match": "digest", "core_assertion_digest": "touch-target|below-min"}
        self.assertTrue(fpf.pattern_matches(digest, f))
        rule_route = {
            "match": "rule+route",
            "rule_id": "touch-target",
            "route": "/",
        }
        self.assertTrue(fpf.pattern_matches(rule_route, f))
        self.assertFalse(fpf.pattern_matches(dict(rule_route, route="/about"), f))

    def test_absorb_and_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".bug-hunter").mkdir()
            bug_path = root / "bug.json"
            bug = self._finding(id="bug-1", status="rejected", reject_reason="design chip")
            bug_path.write_text(json.dumps(bug), encoding="utf-8")
            rc = fpf.main(
                [
                    "absorb",
                    "--root",
                    str(root),
                    "--bug",
                    str(bug_path),
                    "--match",
                    "selector+rule+route",
                ]
            )
            self.assertEqual(rc, 0)
            store = fpf.load_patterns(root / ".bug-hunter" / "fp_patterns.json")
            self.assertEqual(len(store["patterns"]), 1)
            marked, hits = fpf.apply_patterns([self._finding()], store)
            self.assertEqual(marked[0]["status"], "suppressed")
            self.assertEqual(hits[0]["pattern_id"], store["patterns"][0]["id"])

    def test_agents_snippet_generated_not_touch_agents_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".bug-hunter").mkdir()
            store = fpf.empty_store()
            fpf.add_pattern(
                store,
                {
                    "rule_id": "touch-target",
                    "route": "/",
                    "selector_pattern": "[data-testid=x]",
                    "match": "selector+rule+route",
                    "reason": "test",
                },
            )
            fpf.save_patterns(root / ".bug-hunter" / "fp_patterns.json", store)
            out = root / "AGENTS.bug-hunter.snippet.md"
            rc = fpf.main(["agents-snippet", "--root", str(root), "--out", str(out)])
            self.assertEqual(rc, 0)
            self.assertTrue(out.exists())
            self.assertFalse((root / "AGENTS.md").exists())


class TestExportReport(unittest.TestCase):
    def test_build_and_validate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bh = root / ".bug-hunter"
            (bh / "bugs" / "confirmed").mkdir(parents=True)
            (bh / "bugs" / "rejected").mkdir(parents=True)
            (bh / "runs" / "run-1").mkdir(parents=True)
            (bh / "state.json").write_text(
                json.dumps(
                    {
                        "phase": 3,
                        "mode": "hunt-only",
                        "modalities_enabled": ["code", "web-visual"],
                        "run_count": 1,
                        "quiet_streak": 0,
                        "convergence": {"quiet_streak": 0, "required_quiet_streak": 2, "converged": False},
                        "surfaces": {
                            "web": {
                                "base_url": "http://x",
                                "routes": ["/"],
                                "viewports": ["375x812"],
                                "degrade_level": "L2",
                            }
                        },
                        "stats": {"findings_total": 2},
                        "blind_spots": ["no-axe"],
                    }
                ),
                encoding="utf-8",
            )
            (bh / "bugs" / "confirmed" / "bug-1.json").write_text(
                json.dumps(
                    {
                        "id": "bug-1",
                        "status": "confirmed",
                        "modality": "web-visual",
                        "category": "ui-layout",
                        "rule_id": "overflow-x",
                        "title": "overflow",
                        "location": {"route": "/", "viewport": "375x812"},
                        "fix_route": "local",
                        "fix_reason_codes": ["oracle_ok"],
                        "fix_attempts": {"local": 1, "lite": 0, "diminishing": False},
                        "packet_path": ".bug-hunter/bugs/bug-1/packet.json",
                    }
                ),
                encoding="utf-8",
            )
            (bh / "runs" / "run-1" / "summary.json").write_text(
                json.dumps(
                    {
                        "run_id": "run-1",
                        "new_count": 1,
                        "known_count": 0,
                        "suppressed_count": 2,
                        "findings_total": 3,
                        "strategies": ["layout-geom"],
                        "degrade_level": "L2",
                    }
                ),
                encoding="utf-8",
            )
            (bh / "fingerprints.json").write_text(
                json.dumps({"entries": {"abc": {"status": "candidate"}}}),
                encoding="utf-8",
            )
            data = export_report.build_export(root)
            errors = export_report.validate_export(data)
            self.assertEqual(errors, [])
            self.assertEqual(data["counts"]["confirmed"], 1)
            self.assertEqual(data["counts"]["suppressed"], 2)
            self.assertEqual(data["convergence"]["required_quiet_streak"], 2)
            self.assertIn("fix_router", data)
            self.assertIn("budget", data)
            bug = data["bugs"][0]
            self.assertEqual(bug["fix_route"], "local")
            self.assertEqual(bug["fix_reason_codes"], ["oracle_ok"])
            self.assertFalse(bug["fix_attempts"]["diminishing"])
            self.assertEqual(bug["packet_path"], ".bug-hunter/bugs/bug-1/packet.json")

    def test_validate_rejects_missing(self):
        errors = export_report.validate_export({"schema_version": 1})
        self.assertTrue(any(e.startswith("missing:") for e in errors))
        self.assertTrue(export_report.validate_export({"schema_version": 99}))


class TestBaselineLock(unittest.TestCase):
    def test_snapshot_verify_drift_and_approvals(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "baselines"
            base.mkdir()
            png = base / "home__375x812.png"
            png.write_bytes(b"PNGDATA1")
            lock = Path(tmp) / "lock.json"
            baseline_lock.snapshot(base, lock)
            result = baseline_lock.verify(base, lock)
            self.assertTrue(result["ok"])

            png.write_bytes(b"PNGDATA2")
            result = baseline_lock.verify(base, lock)
            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "drift")

            # route×viewport approval WITHOUT matching sha256 must NOT unlock
            stale = Path(tmp) / "stale-approvals.jsonl"
            stale.write_text(
                json.dumps({"route": "/", "viewport": "375x812", "sha256": "deadbeef"}) + "\n",
                encoding="utf-8",
            )
            result = baseline_lock.verify(base, lock, approvals_path=stale)
            self.assertFalse(result["ok"], "stale sha256 approval must not allow drift")

            path_only = Path(tmp) / "path-approvals.jsonl"
            path_only.write_text(
                json.dumps({"file": "home__375x812.png"}) + "\n",
                encoding="utf-8",
            )
            result = baseline_lock.verify(base, lock, approvals_path=path_only)
            self.assertFalse(result["ok"], "path-only approval without sha256 must not allow drift")

            approvals = Path(tmp) / "approvals.jsonl"
            current = baseline_lock.sha256_file(png)
            approvals.write_text(
                json.dumps({"route": "/", "viewport": "375x812", "sha256": current}) + "\n",
                encoding="utf-8",
            )
            result = baseline_lock.verify(base, lock, approvals_path=approvals)
            self.assertTrue(result["ok"])

    def test_strict_unlocked_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "baselines"
            base.mkdir()
            locked = base / "home__375x812.png"
            locked.write_bytes(b"A")
            lock = Path(tmp) / "lock.json"
            baseline_lock.snapshot(base, lock)
            extra = base / "extra.png"
            extra.write_bytes(b"B")
            result = baseline_lock.verify(base, lock, strict=True)
            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "unlocked-strict")
            self.assertIn("extra.png", result["unlocked_files"])

    def test_no_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "b"
            base.mkdir()
            result = baseline_lock.verify(base, Path(tmp) / "lock.json")
            self.assertEqual(result["status"], "no-lock")


class TestAxeGate(unittest.TestCase):
    def test_unavailable_detector_not_pass_violations(self):
        def detector():
            return {"backend": "unavailable", "command": None}

        with tempfile.TemporaryDirectory() as tmp:
            report = axe_gate.run_gate(url="http://127.0.0.1:1/", out_dir=Path(tmp), detector=detector)
            self.assertEqual(report["status"], "unavailable")
            self.assertEqual(report["violations"], [])
            self.assertTrue((Path(tmp) / "axe-report.json").exists())

    def test_fail_on_violations_logic_in_main_path(self):
        def detector():
            return {"backend": "npx-axe", "command": ["false"]}

        report = axe_gate.run_gate(
            url="http://127.0.0.1:1",
            routes=["/"],
            detector=detector,
        )
        # command fails → not silently ok-with-violations
        self.assertIn(report["status"], {"unavailable", "ok"})


class TestCiGateImport(unittest.TestCase):
    def test_ci_gate_module_loads(self):
        import ci_gate

        self.assertTrue(hasattr(ci_gate, "run_ci"))


class TestLayoutProbeFpPatterns(unittest.TestCase):
    def test_cli_fp_patterns_suppresses(self):
        import layout_probe

        with tempfile.TemporaryDirectory() as tmp:
            patterns = Path(tmp) / "fp.json"
            patterns.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "patterns": [
                            {
                                "id": "fp-0001",
                                "match": "selector+rule+route",
                                "rule_id": "touch-target",
                                "route": "/",
                                "selector_pattern": "[data-testid=btn-tiny]",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            payload = {
                "route": "/",
                "viewport": "375x812",
                "elements": [
                    {
                        "selector": "[data-testid=btn-tiny]",
                        "interactive": True,
                        "bbox": {"x": 0, "y": 0, "w": 20, "h": 20},
                        "text": "x",
                    }
                ],
            }
            import contextlib
            import io

            buf = io.StringIO()
            old_stdin = sys.stdin
            try:
                sys.stdin = io.StringIO(json.dumps(payload))
                with contextlib.redirect_stdout(buf):
                    rc = layout_probe.main(
                        [
                            "--viewport-width",
                            "375",
                            "--fp-patterns",
                            str(patterns),
                        ]
                    )
            finally:
                sys.stdin = old_stdin
            self.assertEqual(rc, 0)
            data = json.loads(buf.getvalue())
            self.assertGreaterEqual(data.get("suppressed_count", 0), 1)
            statuses = {f.get("status") for f in data.get("findings") or [] if f.get("rule_id") == "touch-target"}
            self.assertIn("suppressed", statuses)


class TestHuntRoundFpSuppress(unittest.TestCase):
    def test_suppressed_not_counted_as_new(self):
        import hunt_round

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bh = root / ".bug-hunter"
            caps = bh / "runs" / "run-1" / "captures"
            caps.mkdir(parents=True)
            elements = [
                {
                    "selector": "[data-testid=btn-tiny]",
                    "tag": "button",
                    "interactive": True,
                    "bbox": {"x": 0, "y": 0, "w": 20, "h": 20},
                    "text": "x",
                    "inViewport": True,
                }
            ]
            (caps / "home__375x812__elements.json").write_text(
                json.dumps({"route": "/", "viewport": "375x812", "elements": elements}),
                encoding="utf-8",
            )
            (caps / "MANIFEST.json").write_text(
                json.dumps(
                    {
                        "backend": "fixture",
                        "items": [
                            {
                                "route": "/",
                                "viewport": "375x812",
                                "status": "ok",
                                "elements_json": "home__375x812__elements.json",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (bh / "state.json").write_text(
                json.dumps(
                    {
                        "phase": 3,
                        "modalities_enabled": ["web-visual"],
                        "surfaces": {
                            "web": {
                                "base_url": "http://x",
                                "routes": ["/"],
                                "viewports": ["375x812"],
                                "degrade_level": "L2",
                            }
                        },
                        "visual_oracle": {"touch_target_px": 44},
                        "convergence": {"quiet_streak": 0, "required_quiet_streak": 2},
                    }
                ),
                encoding="utf-8",
            )
            patterns = {
                "version": 1,
                "patterns": [
                    {
                        "id": "fp-0001",
                        "match": "selector+rule+route",
                        "rule_id": "touch-target",
                        "route": "/",
                        "selector_pattern": "[data-testid=btn-tiny]",
                        "reason": "chip",
                    }
                ],
            }
            fp_path = bh / "fp_patterns.json"
            fp_path.write_text(json.dumps(patterns), encoding="utf-8")

            summary = hunt_round.run_hunt_round(
                root=root,
                run_id="run-1",
                skip_capture=True,
                captures=caps,
            )
            self.assertGreaterEqual(summary.get("suppressed_count", 0), 1)
            self.assertEqual(summary.get("new_count", 0), 0)
            by_rule = summary.get("by_rule") or {}
            # suppressed findings still counted in by_rule for audit
            self.assertIn("touch-target", by_rule)


if __name__ == "__main__":
    unittest.main()
