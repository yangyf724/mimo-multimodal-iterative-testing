# 测试报告 TEST_REPORT

## 1. 执行摘要

- 项目: `D:\mimo\worktrees\MiMo Multimodal Iterative Testing\examples\mit-demo-media`
- RC: `RC-1`  rc_sha: `871f2b7eda99f1da4e2d7decc80f1da5eefd3a88c445c4da4491d448c1c562e0`
- 轮次: 1  matrix_rev: `m2`
- 生成时间: 2026-09-25T03:00:13Z
- 结论草稿: `in_progress`

## 2. 项目画像与矩阵覆盖

- app_types: ['web', 'canvas', '3d']
- runtime: node@20
- topology: api
- counts: required=5 optional=0 n/a=8

## 3. 环境与设备

- E0: {"name": "local-sandbox", "available": true, "notes": "default execution"}
- E1: {"name": "prod-equivalent", "available": false, "topology": "api", "topology_delta": "unverified", "network_delta": "unverified", "notes": "E1 equivalence not verified in this workspace; do not treat as production-equivalent without §7.2 checks"}
- E2: {"name": "real-production", "available": false, "prod_access": "none", "notes": "no prod access — results must be declared missing"}
- E3: {"name": "devices", "available": false, "devices": ["unknown"], "notes": "sim must be labeled; missing device => blind spot"}
- device coverage: 0.0 (all_sim=True)
- 脱敏: clean=True count=0

## 4. 分模态测试结果

| modality | mark | status | notes |
|----------|------|--------|-------|
| code | required | pass |  |
| api | n/a | excluded |  |
| web | required | blind_spot | required modality has no real executable probe; recorded as blind spot (not PASS) |
| mobile | n/a | excluded |  |
| desktop | n/a | excluded |  |
| cli | n/a | excluded |  |
| db | n/a | excluded |  |
| infra | n/a | excluded |  |
| av | required | blind_spot | required modality has no real executable probe; recorded as blind spot (not PASS) |
| canvas | required | pass |  |
| 3d | required | blind_spot | required modality has no real executable probe; recorded as blind spot (not PASS) |
| xr | n/a | excluded |  |
| plugin | n/a | excluded |  |

## 5. 缺陷清单与修复/回归

- open_defects: {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
- 详见 `.mit/defects/`；无回归不得标记 fixed。

## 6. 真实生产环境测试结果

**缺失**

- reason: prod_access=none — no authorized production probe
- impact: PRD missing; unconditional Allow is forbidden
- recommended: conditional Allow (exposure constraint) or Deny/Escalate

## 7. 盲区与降级（Blind Spots）

- `RC-1:web`: required modality has no real executable probe; recorded as blind spot (not PASS)
- `RC-1:av`: required modality has no real executable probe; recorded as blind spot (not PASS)
- `RC-1:3d`: required modality has no real executable probe; recorded as blind spot (not PASS)

## 8. Known Issues

- 见 defects 中 P2/P3 及用户接受记录（若有）。

## 9. 裁决信号摘要

- quiet_streak: 0
- signals: `{"build_ok": true, "matrix_required_coverage": 0.2, "required_gaps": ["web:blind_spot", "av:blind_spot", "canvas:fail", "3d:blind_spot"], "optional_degraded": [], "open_p0": 0, "open_p1": 0, "open_p2": 0, "p2_user_accepted": false, "regression_green": true, "fixed_without_regression": [], "device_coverage": 0.0, "device_all_sim": true, "data_mask_clean": true, "release_layers": {"artifact_ready": false, "exposure_ready": false, "exposure_constraint": "no_prod_or_coverage_gap_conditional_only"}, "prod_test": {"available": false, "mode": "none", "slis": [], "critical_path_pass": null}, "oracle_quality": {"k": 0, "agreement_rate": null, "fp_rate_estimate": null}, "contract_breaking_unreviewed": false, "blind_spots": ["RC-1:web", "RC-1:av", "RC-1:3d"], "quiet_streak": 0}`

## 10. 证据包索引

- 见 `.mit/deliverables/EVIDENCE_INDEX.md` 与 `.mit/deliverables/evidence/`。
