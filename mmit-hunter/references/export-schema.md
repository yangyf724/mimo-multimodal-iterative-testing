# Export Schema (v1)

`scripts/export_report.py` writes a machine-readable snapshot for CI and downstream tools.

Default path: `.bug-hunter/export/report.json`

## Top-level fields

| Field | Type | Required |
|-------|------|----------|
| `schema_version` | `1` | yes |
| `exported_at` | ISO UTC | yes |
| `skill` | string | yes |
| `phase` | int | no |
| `scope` | object | yes |
| `convergence` | object | yes |
| `counts` | object | yes |
| `bugs` | array | yes |
| `fingerprints` | object (`total`, `by_status`) | yes |
| `blind_spots` | array | yes |
| `runs` | array | yes |
| `fp_patterns` | `{count, ids}` | no |
| `report_md_path` | string | no |
| `budget` | object（来自 `state.budget`，含 fix 路由预算字段） | no |
| `fix_router` | `{enabled, escalations_used, max_compose_escalations, by_route}` | no |

`scope` requires `modalities_enabled`, `routes`, `viewports`.
`counts` requires `confirmed`, `rejected`, `fixed`, `deferred`, `findings_total`.
`convergence` requires `run_count`, `quiet_streak`, `required_quiet_streak`, `converged`.

### Bug 对象可选字段（fix router）

| Field | Type | When |
|-------|------|------|
| `fix_route` | `local` \| `lite` \| `compose` | 已做修复路由判定 |
| `fix_reason_codes` | string[] | 与 route 一并记录 |
| `fix_attempts` | `{local, lite, diminishing}` | 有修复尝试时 |
| `packet_path` | string | 已写 bug packet |

## CLI

```bash
python scripts/export_report.py --root .
python scripts/export_report.py --validate .bug-hunter/export/report.json
```

Validate exit `0` when schema checks pass; unknown `schema_version` → exit `3`; other validation errors → exit `1`.

REPORT.md remains the human document; export is a parallel machine view derived from the same `.bug-hunter` state.
