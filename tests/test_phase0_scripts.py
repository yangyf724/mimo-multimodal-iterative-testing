import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mmit" / "scripts"))

import fingerprint as fp  # noqa: E402
import init_state as init_mod  # noqa: E402
import converge_check as cc  # noqa: E402
import layout_probe as lp  # noqa: E402
import validate_report as vr  # noqa: E402


class TestInitState(unittest.TestCase):
    def test_creates_tree_and_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = init_mod.init_state(root, routes=["/", "/about"], viewports=["375x812"])
            self.assertTrue((root / ".mmit" / "state.json").exists())
            self.assertTrue((root / ".mmit" / "fingerprints.json").exists())
            self.assertTrue((root / ".mmit" / "bugs" / "confirmed").is_dir())
            self.assertEqual(state["surfaces"]["web"]["routes"], ["/", "/about"])
            self.assertEqual(state["convergence"]["required_quiet_streak"], 2)
            budget = state["budget"]
            self.assertEqual(budget["max_local_attempts"], 3)
            self.assertEqual(budget["lite_max_attempts"], 2)
            self.assertEqual(budget["max_compose_escalations"], 2)
            self.assertEqual(budget["max_local_edit_sites"], 3)
            self.assertEqual(budget["max_lite_edit_sites"], 6)
            router = state["fix_router"]
            self.assertTrue(router["enabled"])
            self.assertEqual(router["escalations_used"], 0)
            self.assertEqual(router["max_compose_escalations"], 2)
            self.assertEqual(router["by_route"]["local"], 0)
            self.assertEqual(router["by_route"]["compose"], 0)

    def test_resume_summary_includes_fix_router_budget(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_mod.init_state(root)
            summary = init_mod.resume_summary(root)
            self.assertTrue(summary["ok"])
            self.assertIn("max_local_attempts", summary["budget"])
            self.assertEqual(summary["fix_router"]["enabled"], True)

    def test_refuses_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_mod.init_state(root)
            with self.assertRaises(FileExistsError):
                init_mod.init_state(root)

    def test_resume_summary(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_mod.init_state(root, quiet_streak=1)
            summary = init_mod.resume_summary(root)
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["quiet_streak"], 1)

    def test_resume_summary_bom(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_mod.init_state(root, quiet_streak=2)
            state_path = root / ".mmit" / "state.json"
            raw = state_path.read_bytes()
            state_path.write_bytes(b"\xef\xbb\xbf" + raw)
            summary = init_mod.resume_summary(root)
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["quiet_streak"], 2)


class TestFingerprint(unittest.TestCase):
    def test_stable(self):
        a = fp.compute_fingerprint(
            modality="web-visual",
            route_or_file="/login",
            viewport="375x812",
            category="ui-layout",
            element_ref="button[data-testid=submit]",
            assertion="overflow 18px",
        )
        b = fp.compute_fingerprint(
            modality="web-visual",
            route_or_file="/login/",
            viewport="375 x 812",
            category="ui-layout",
            element_ref=" button[data-testid=submit] ",
            assertion="overflow  18px",
        )
        self.assertEqual(a, b)
        self.assertEqual(len(a), 16)

    def test_viewport_changes_fingerprint(self):
        a = fp.compute_fingerprint(
            modality="web-visual",
            route_or_file="/",
            viewport="375x812",
            category="ui-layout",
            element_ref="button",
            assertion="overflow",
        )
        b = fp.compute_fingerprint(
            modality="web-visual",
            route_or_file="/",
            viewport="1440x900",
            category="ui-layout",
            element_ref="button",
            assertion="overflow",
        )
        self.assertNotEqual(a, b)

    def test_rejects_bad_modality(self):
        with self.assertRaises(ValueError):
            fp.compute_fingerprint(
                modality="a11y",
                route_or_file="/",
                viewport="1x1",
                category="ui-a11y",
                element_ref="x",
                assertion="y",
            )

    def test_register_dedupe(self):
        with tempfile.TemporaryDirectory() as td:
            fp_path = Path(td) / "fingerprints.json"
            finding = {
                "modality": "code",
                "category": "logic",
                "title": "add off-by-one",
                "location": {"file": "src/calc.js", "viewport": "n/a"},
                "statement": "expected 5 got 6",
            }
            r1 = fp.register_fingerprints([finding], fp_path=fp_path, run_id="run-1", now="t1")
            r2 = fp.register_fingerprints([finding], fp_path=fp_path, run_id="run-2", now="t2")
            self.assertEqual(r1["new_count"], 1)
            self.assertEqual(r2["known_count"], 1)
            self.assertEqual(r2["new_count"], 0)
            self.assertAlmostEqual(r2["duplicate_rate"], 1.0)


class TestConverge(unittest.TestCase):
    def _payload(self, **kw):
        base = {
            "strategies": ["static", "dynamic", "layout-geom", "a11y-axe"],
            "degrade_level": "L3",
            "modalities_enabled": ["code", "web-visual"],
            "new_confirmed": 0,
            "new_regressions": [],
            "previous_quiet_streak": 0,
            "required_quiet_streak": 2,
        }
        base.update(kw)
        return base

    def test_quiet_true(self):
        result = cc.evaluate_round(**self._payload())
        self.assertTrue(result["quiet"])
        self.assertEqual(result["quiet_streak"], 1)
        self.assertFalse(result["converged"])

    def test_missing_modality_not_quiet(self):
        result = cc.evaluate_round(**self._payload(strategies=["static", "dynamic"]))
        self.assertFalse(result["quiet"])
        self.assertEqual(result["quiet_streak"], 0)

    def test_new_confirmed_not_quiet(self):
        result = cc.evaluate_round(**self._payload(new_confirmed=1))
        self.assertFalse(result["quiet"])

    def test_regression_not_quiet(self):
        result = cc.evaluate_round(**self._payload(new_regressions=["axe: new violation"]))
        self.assertFalse(result["quiet"])

    def test_converge_after_k(self):
        result = cc.evaluate_round(**self._payload(previous_quiet_streak=1, required_quiet_streak=2))
        self.assertTrue(result["quiet"])
        self.assertTrue(result["converged"])

    def test_l1_code_only_is_quiet(self):
        result = cc.evaluate_round(
            strategies=["static", "dynamic"],
            degrade_level="L1",
            modalities_enabled=["code", "web-visual"],
            new_confirmed=0,
            new_regressions=[],
            previous_quiet_streak=0,
            required_quiet_streak=2,
        )
        self.assertTrue(result["quiet"])


class TestLayoutProbe(unittest.TestCase):
    def test_root_overflow(self):
        elements = [
            {
                "selector": "html",
                "route": "/",
                "viewport": "375x812",
                "scrollWidth": 420,
                "clientWidth": 375,
                "bbox": {"x": 0, "y": 0, "w": 375, "h": 812},
            }
        ]
        findings = lp.check_overflow_x(elements, viewport_width=375)
        self.assertTrue(any(f["rule_id"] == "overflow-x" for f in findings))
        self.assertEqual(findings[0]["metrics"]["overflow_px"], 45)

    def test_element_right_overflow(self):
        elements = [
            {
                "selector": "[data-testid=primary-cta]",
                "route": "/",
                "viewport": "375x812",
                "interactive": True,
                "bbox": {"x": 16, "y": 200, "w": 400, "h": 48},
            }
        ]
        findings = lp.check_overflow_x(elements, viewport_width=375)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["evidence_level_target"], "L3")
        self.assertGreater(findings[0]["metrics"]["overflow_px"], 0)

    def test_root_overflow_not_double_counted(self):
        elements = [
            {
                "selector": "html",
                "route": "/",
                "viewport": "375x812",
                "scrollWidth": 436,
                "clientWidth": 360,
                "bbox": {"x": 0, "y": 0, "w": 360, "h": 797},
            },
            {
                "selector": ".cta-row",
                "route": "/",
                "viewport": "375x812",
                "scrollWidth": 420,
                "clientWidth": 420,
                "bbox": {"x": 16, "y": 208, "w": 420, "h": 80},
            },
        ]
        findings = lp.check_overflow_x(elements, viewport_width=375)
        html_findings = [f for f in findings if f["location"]["selector"] == "html"]
        self.assertEqual(len(html_findings), 1)

    def test_fingerprint_stable_under_metric_noise(self):
        base = {
            "modality": "web-visual",
            "category": "ui-layout",
            "rule_id": "overflow-x",
            "core_assertion_digest": "overflow-x|horizontal-overflow",
            "location": {"route": "/", "viewport": "375x812", "selector": "html"},
            "statement": "overflow A",
            "metrics": {"overflow_px": 76.0},
        }
        noisy = dict(base)
        noisy["metrics"] = {"overflow_px": 75.0}
        noisy["statement"] = "overflow B"
        self.assertEqual(fp.fingerprint_from_finding(base), fp.fingerprint_from_finding(noisy))

    def test_no_overflow(self):
        elements = [
            {
                "selector": "html",
                "scrollWidth": 375,
                "clientWidth": 375,
                "bbox": {"x": 0, "y": 0, "w": 375, "h": 812},
            },
            {"selector": "p", "bbox": {"x": 16, "y": 10, "w": 300, "h": 20}},
        ]
        findings = lp.check_overflow_x(elements, viewport_width=375)
        self.assertEqual(findings, [])


class TestValidateReport(unittest.TestCase):
    def test_missing_sections(self):
        missing = vr.validate_report("# foo\nnothing")
        self.assertTrue(missing)
        self.assertTrue(any("盲区" in m or "Blind" in m for m in missing))

    def test_requires_rule_id(self):
        text = """# Report
## 范围
## 执行摘要
| modality |
## 确认清单
## 已知盲区 Blind Spots
"""
        missing = vr.validate_report(text)
        self.assertTrue(any("rule" in m.lower() or "规则" in m for m in missing))

    def test_ok(self):
        text = """# Report
## 范围
## 执行摘要
| modality |
## 确认清单
- bug — rule_id=overflow-x
## 已知盲区 Blind Spots
"""
        self.assertEqual(vr.validate_report(text), [])


class TestInitStateLock(unittest.TestCase):
    def test_lock_prevents_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            lock = root / ".mmit" / ".lock"
            lock.parent.mkdir(parents=True, exist_ok=True)
            lock.write_text("other\n", encoding="utf-8")
            with self.assertRaises(init_mod.LockError):
                init_mod.init_state(root)
            self.assertFalse((root / ".mmit" / "state.json").exists())


if __name__ == "__main__":
    unittest.main()
