# CI Gate

Local and GitHub Actions share one entrypoint: `scripts/ci_gate.py`.

## Steps

1. `python -m unittest discover -s tests`
2. fixture E2E (`tests/phase1_fixture_e2e.py`, `tests/phase2_fixture_e2e.py`) unless `--skip-e2e`
3. `baseline_lock.py verify` when a lock exists under the demo project
4. `export_report.py` smoke when a target `.mmit/state.json` exists
5. optional `axe_gate.py` (`--with-axe`)

Stdout is a JSON report: `{ok, steps: [{name, status, detail}]}`.

```bash
python mmit/scripts/ci_gate.py --root .
python mmit/scripts/ci_gate.py --root . --with-axe
```

Axe is **disabled by default**; pass `--with-axe` to enable (and then use `--fail-on violations`).

## Baseline lock

```bash
python scripts/baseline_lock.py snapshot --root <project>
python scripts/baseline_lock.py verify --root <project>
```

- Lock file: `.mmit/baselines/lock.json` (sha256 per PNG).
- Drift fails verify unless `baselines/approvals.jsonl` contains a matching intentional approval (`visual_diff.py approve`).
- `--strict` also fails on unlocked extra PNGs.

## axe gate

```bash
python scripts/axe_gate.py --url http://127.0.0.1:5174/ --routes / /shop --fail-on violations
python scripts/axe_gate.py --html-file examples/second-project/public/index.html
```

Backend detection: local `node_modules/.bin/axe` → `npx @axe-core/cli` → unavailable.

**Unavailable is not a pass.** Report `status: unavailable` is written so Blind Spots / CI can see the gap. Do not treat axe absence as green a11y.

## GitHub Actions

See `.github/workflows/ci.yml`. Default job runs unittest + fixture E2E + `ci_gate` (axe off). Enable axe with `--with-axe` after provisioning `@axe-core/cli` and a reachable demo URL.
