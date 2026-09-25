import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIT_SCRIPTS = ROOT / "multimodal-iterative-testing" / "scripts"
sys.path.insert(0, str(MIT_SCRIPTS))

# Load MIT modules under unique names to avoid clashing with iterative-bug-hunter scripts
# (both packages ship init_state.py / fix_gate.py; unittest discover shares sys.modules).
def _load(mod_name: str):
    name = f"mit_{mod_name}"
    if name in sys.modules:
        return sys.modules[name]
    path = MIT_SCRIPTS / f"{mod_name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


asig = _load("assemble_signals")
brc = _load("build_rc")
dm = _load("data_mask")
dr = _load("defect_register")
eu = _load("env_up")
esc = _load("escalate")
fg = _load("fix_gate")
init_mod = _load("init_state")
mb = _load("matrix_build")
mr = _load("matrix_run")
ms = _load("migrate_state")
ps = _load("profile_scan")
pp = _load("prod_probe")
mit_lib = _load("mit_lib")
read_json = mit_lib.read_json
write_json = mit_lib.write_json


class MitTmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mit-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _demo_project(self) -> Path:
        root = self.tmp / "proj"
        (root / "tests").mkdir(parents=True)
        (root / "package.json").write_text(
            json.dumps({"name": "demo", "engines": {"node": "20"}, "scripts": {"test": "echo ok"}}),
            encoding="utf-8",
        )
        (root / "server.js").write_text("console.log('hi');\n", encoding="utf-8")
        (root / "openapi.yaml").write_text("openapi: 3.0.0\n", encoding="utf-8")
        (root / "public").mkdir()
        (root / "public" / "index.html").write_text("<html><body>hi</body></html>", encoding="utf-8")
        (root / "migrations").mkdir()
        return root


class TestProfileAndMatrix(MitTmp):
    def test_profile_scan_and_matrix_marks(self):
        root = self._demo_project()
        profile = ps.scan_profile(root)
        self.assertIn("web", profile["app_types"])
        self.assertEqual(profile["runtime"].startswith("node"), True)
        marks = mb.map_profile_to_modalities(profile)
        self.assertEqual(marks["code"], "required")
        self.assertEqual(marks["web"], "required")
        self.assertEqual(marks["api"], "required")
        self.assertEqual(marks["db"], "optional")
        self.assertEqual(marks["xr"], "n/a")
        matrix = mb.build_matrix(profile)
        self.assertEqual(matrix["matrix_rev"], "m1")
        self.assertFalse(matrix["frozen"])
        frozen = mb.freeze_matrix(matrix)
        self.assertTrue(frozen["frozen"])
        self.assertTrue(frozen["history"])

    def test_user_modality_forces_required(self):
        root = self._demo_project()
        profile = ps.scan_profile(root)
        matrix = mb.build_matrix(profile, user_modalities=["xr"])
        by = {i["modality"]: i["mark"] for i in matrix["items"]}
        self.assertEqual(by["xr"], "required")


class TestStateAndMigrate(MitTmp):
    def test_init_state_defaults(self):
        root = self._demo_project()
        rc = init_mod.main(["--root", str(root), "--prod-access", "readonly"])
        self.assertEqual(rc, 0)
        state = read_json(root / ".mit" / "state.json")
        self.assertEqual(state["skill"], "multimodal-iterative-testing")
        self.assertEqual(state["prod_access"], "readonly")
        self.assertEqual(state["decision"], "in_progress")
        self.assertEqual(state["budget"]["max_rc_rounds"], 5)

    def test_migrate_from_bug_hunter(self):
        root = self._demo_project()
        bh = root / ".bug-hunter"
        bh.mkdir()
        write_json(
            bh / "state.json",
            {
                "skill": "iterative-bug-hunter",
                "mode": "hunt-and-fix",
                "run_count": 7,
                "quiet_streak": 2,
                "modalities_enabled": ["code", "web-visual"],
                "created_at": "2026-01-01T00:00:00Z",
            },
        )
        rc = ms.main(["--root", str(root)])
        self.assertEqual(rc, 0)
        state = read_json(root / ".mit" / "state.json")
        self.assertEqual(state["mode"], "test-and-fix")
        self.assertEqual(state["round"], 7)
        self.assertEqual(state["quiet_streak"], 2)
        self.assertIn("migrated_from", state)


class TestMaskGate(MitTmp):
    def test_clean_tree_passes(self):
        root = self._demo_project()
        rc = dm.main(["--root", str(root)])
        self.assertEqual(rc, 0)
        report = read_json(root / ".mit" / "data_mask_report.json")
        self.assertTrue(report["clean"])

    def test_secret_fails_gate(self):
        root = self._demo_project()
        (root / "leak.env").write_text("API_KEY=FAKE_TEST_KEY_NOT_A_SECRET_0123456789\n", encoding="utf-8")
        rc = dm.main(["--root", str(root)])
        self.assertEqual(rc, 1)
        report = read_json(root / ".mit" / "data_mask_report.json")
        self.assertFalse(report["clean"])
        self.assertGreater(report["count"], 0)


class TestFixGate(MitTmp):
    def test_pass_and_fail(self):
        ok = fg.evaluate_fix_gate(True, True, True, True)
        self.assertTrue(ok["passed"])
        bad = fg.evaluate_fix_gate(True, True, True, False)
        self.assertFalse(bad["passed"])
        self.assertIn("regression_green", bad["failed_checks"])


class TestRCAndRun(MitTmp):
    def test_build_rc_and_matrix_run_dry(self):
        root = self._demo_project()
        ps.main(["--root", str(root)])
        mb.main(["--root", str(root), "--freeze"])
        init_mod.main(["--root", str(root)])
        dm.main(["--root", str(root)])
        self.assertEqual(brc.main(["--root", str(root)]), 0)
        state = read_json(root / ".mit" / "state.json")
        self.assertEqual(state["rc_n"], 1)
        self.assertTrue(state["rc_sha"])
        meta = read_json(root / ".mit" / "artifacts" / "RC-1.meta.json")
        self.assertEqual(meta["rc_sha"], state["rc_sha"])
        self.assertEqual(mr.main(["--root", str(root), "--dry-run"]), 0)
        results = read_json(root / ".mit" / "runs" / "RC-1" / "findings" / "matrix_results.json")
        self.assertIn("results", results)
        for r in results["results"]:
            if r["mark"] == "n/a":
                self.assertEqual(r["status"], "excluded")
            if r["status"] == "dry_run":
                self.assertNotEqual(r["status"], "pass")

    def test_matrix_run_requires_freeze(self):
        root = self._demo_project()
        ps.main(["--root", str(root)])
        mb.main(["--root", str(root)])
        init_mod.main(["--root", str(root)])
        dm.main(["--root", str(root)])
        rc = mr.main(["--root", str(root), "--dry-run"])
        self.assertEqual(rc, 2)


class TestEnvProdSignals(MitTmp):
    def test_env_prod_missing_and_signals(self):
        root = self._demo_project()
        ps.main(["--root", str(root)])
        mb.main(["--root", str(root), "--freeze"])
        init_mod.main(["--root", str(root), "--prod-access", "none"])
        eu.main(["--root", str(root)])
        env = read_json(root / ".mit" / "env_manifest.json")
        self.assertFalse(env["layers"]["E2"]["available"])
        pp.main(["--root", str(root)])
        prod = read_json(root / ".mit" / "prod_test_results.json")
        self.assertFalse(prod["available"])
        self.assertIn("missing_declaration", prod)
        self.assertTrue((root / ".mit" / "deliverables" / "PROD_RESULTS_MISSING.md").exists())
        asig.main(["--root", str(root)])
        signals = read_json(root / ".mit" / "deliverables" / "adjudication_signals.json")
        self.assertIn("signals", signals)
        self.assertFalse(signals["signals"]["prod_test"]["available"])
        self.assertFalse(signals["signals"]["release_layers"]["exposure_ready"])


class TestDefectRegister(MitTmp):
    def test_register_counts_open(self):
        root = self._demo_project()
        init_mod.main(["--root", str(root)])
        dr.main(["--root", str(root), "--id", "D1", "--level", "P0", "--status", "open", "--title", "crash"])
        state = read_json(root / ".mit" / "state.json")
        self.assertEqual(state["open_defects"]["P0"], 1)

    def test_fixed_requires_regression_and_gate(self):
        root = self._demo_project()
        init_mod.main(["--root", str(root)])
        dr.main(["--root", str(root), "--id", "D2", "--level", "P1", "--status", "confirmed"])
        # no regression → reject
        rc = dr.main(["--root", str(root), "--id", "D2", "--level", "P1", "--status", "fixed"])
        self.assertEqual(rc, 2)
        # regression but no gate → reject
        rc = dr.main(
            ["--root", str(root), "--id", "D2", "--level", "P1", "--status", "fixed", "--regression", "tests/t.py"]
        )
        self.assertEqual(rc, 2)
        # gate pass + regression → ok
        fg.main(
            [
                "--root",
                str(root),
                "--defect-id",
                "D2",
                "--target-cleared",
                "--zero-new-high",
                "--non-target-stable",
                "--regression-green",
            ]
        )
        rc = dr.main(
            ["--root", str(root), "--id", "D2", "--level", "P1", "--status", "fixed", "--regression", "tests/t.py"]
        )
        self.assertEqual(rc, 0)
        state = read_json(root / ".mit" / "state.json")
        self.assertEqual(state["open_defects"]["P1"], 0)

    def test_path_traversal_rejected(self):
        root = self._demo_project()
        init_mod.main(["--root", str(root)])
        rc = dr.main(["--root", str(root), "--id", "../../evil", "--level", "P1"])
        self.assertEqual(rc, 2)
        rc = fg.main(["--root", str(root), "--defect-id", "../../evil", "--target-cleared"])
        self.assertEqual(rc, 2)


class TestEscalateAndSignalsIntegrity(MitTmp):
    def test_escalate_package(self):
        root = self._demo_project()
        init_mod.main(["--root", str(root)])
        ps.main(["--root", str(root)])
        mb.main(["--root", str(root), "--freeze"])
        pp.main(["--root", str(root)])
        ar = _load("assemble_report")
        ar.main(["--root", str(root)])
        rc = esc.main(["--root", str(root), "--reason", "budget exhausted", "--next-action", "human review"])
        self.assertEqual(rc, 0)
        esc_dir = root / ".mit" / "escalation"
        self.assertTrue((esc_dir / "REASON.md").exists())
        self.assertTrue((esc_dir / "next_actions.md").exists())
        self.assertTrue((esc_dir / "TEST_REPORT.md").exists())
        state = read_json(root / ".mit" / "state.json")
        self.assertEqual(state["decision"], "escalated")

    def test_mask_dirty_blocks_matrix_run(self):
        root = self._demo_project()
        ps.main(["--root", str(root)])
        mb.main(["--root", str(root), "--freeze"])
        init_mod.main(["--root", str(root)])
        (root / "leak.env").write_text("API_KEY=FAKE_TEST_KEY_NOT_A_SECRET_0123456789\n", encoding="utf-8")
        self.assertEqual(dm.main(["--root", str(root)]), 1)
        rc = mr.main(["--root", str(root), "--dry-run"])
        self.assertEqual(rc, 3)
        # clean re-scan after removing leak
        (root / "leak.env").unlink()
        self.assertEqual(dm.main(["--root", str(root)]), 0)
        rc = mr.main(["--root", str(root), "--dry-run"])
        self.assertEqual(rc, 0)

    def test_signals_not_false_green(self):
        root = self._demo_project()
        ps.main(["--root", str(root)])
        mb.main(["--root", str(root), "--freeze"])
        init_mod.main(["--root", str(root)])
        dm.main(["--root", str(root)])
        brc.main(["--root", str(root)])
        # no probes wired for web/api → blind_spot, coverage must be < 1 and artifact_ready false
        mr.main(["--root", str(root)])
        asig.main(["--root", str(root)])
        signals = read_json(root / ".mit" / "deliverables" / "adjudication_signals.json")
        self.assertFalse(signals["signals"]["release_layers"]["artifact_ready"])
        self.assertLess(signals["signals"]["matrix_required_coverage"], 1.0)
        self.assertTrue(signals["signals"]["regression_green"])  # no open high, no fixed-without-reg
        # plant fixed-without-regression via force then rebuild signals
        dr.main(
            [
                "--root",
                str(root),
                "--id",
                "D9",
                "--level",
                "P1",
                "--status",
                "fixed",
                "--force-fixed",
                "--title",
                "bad fix",
            ]
        )
        asig.main(["--root", str(root)])
        signals = read_json(root / ".mit" / "deliverables" / "adjudication_signals.json")
        self.assertFalse(signals["signals"]["regression_green"])
        self.assertIn("D9", signals["signals"]["fixed_without_regression"])


class TestMaskGateNoSnippet(MitTmp):
    def test_report_has_no_secret_material(self):
        root = self._demo_project()
        (root / "leak.env").write_text("API_KEY=FAKE_TEST_KEY_NOT_A_SECRET_0123456789\n", encoding="utf-8")
        dm.main(["--root", str(root)])
        raw = (root / ".mit" / "data_mask_report.json").read_text(encoding="utf-8")
        self.assertNotIn("FAKE_TEST_KEY_NOT_A_SECRET_0123456789", raw)
        self.assertNotIn("snippet", raw)


class TestCanvasProbeNoFalsePass(MitTmp):
    def test_layers_schema_and_findings_exit(self):
        root = self._demo_project()
        canvas_dir = root / "canvas"
        canvas_dir.mkdir()
        scene = {
            "scene_id": "s1",
            "width": 100,
            "height": 100,
            "export_target": {"width": 100, "height": 100},
            "safe_area": {"top": 5, "bottom": 5, "left": 5, "right": 5},
            "layers": [
                {"id": "bad", "type": "rect", "z": 0, "x": 0, "y": 0, "w": 10, "h": 10},
            ],
        }
        (canvas_dir / "s1.scene.json").write_text(json.dumps(scene), encoding="utf-8")
        init_mod.main(["--root", str(root)])
        cp = _load("canvas_probe")
        out = root / "canvas_out.json"
        import io
        from contextlib import redirect_stderr, redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            rc = cp.main(["--root", str(root), "--out", str(out)])
        self.assertEqual(rc, 1, msg=buf.getvalue()[:500])
        payload = read_json(out)
        self.assertGreater(payload.get("checked_items", 0), 0)
        self.assertFalse(payload.get("ok"))

    def test_empty_checks_do_not_pass(self):
        root = self._demo_project()
        canvas_dir = root / "canvas"
        canvas_dir.mkdir()
        (canvas_dir / "empty.scene.json").write_text(json.dumps({"scene_id": "e", "layers": []}), encoding="utf-8")
        init_mod.main(["--root", str(root)])
        cp = _load("canvas_probe")
        out = root / "canvas_out.json"
        import io
        from contextlib import redirect_stderr, redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            rc = cp.main(["--root", str(root), "--out", str(out)])
        self.assertEqual(rc, 1)
        payload = read_json(out)
        self.assertFalse(payload.get("ok"))


class TestForceFixedNotGreen(MitTmp):
    def test_force_fixed_blocks_regression_green(self):
        root = self._demo_project()
        init_mod.main(["--root", str(root)])
        dm.main(["--root", str(root)])
        dr.main(
            [
                "--root",
                str(root),
                "--id",
                "DX",
                "--level",
                "P1",
                "--status",
                "fixed",
                "--regression",
                "tests/t.py",
                "--force-fixed",
            ]
        )
        asig.main(["--root", str(root)])
        signals = read_json(root / ".mit" / "deliverables" / "adjudication_signals.json")
        self.assertFalse(signals["signals"]["regression_green"])
        self.assertIn("DX", signals["signals"]["fixed_without_gate"])


if __name__ == "__main__":
    unittest.main()
