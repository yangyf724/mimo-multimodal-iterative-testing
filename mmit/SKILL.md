---
name: mmit
description: 全模态质量门流水线：抓 BUG 至 quiet 收敛，并在发布深度执行 Profile→Matrix→RC 全量测试，出口统一为 Allow/Deny/Escalate。覆盖代码+Web 视觉/无障碍/响应式+画布；指纹去重、跨模态 Confirm、Fix Gate（无回归不得 fixed）。Use when the user says 抓BUG, 找bug, 修到没有, bug hunt, hunt until clean, design QA, 视觉问题, 布局炸了, 无障碍, 对比度, 发布就绪, go/no-go, RC 验收, 能不能发版, 全模态迭代测试. Do NOT use for one-shot lint, pure feature dev, or static-only review with no runnable app.
---

# MMIT 全模态质量门

对目标项目跑**统一流水线**：深度 `hunt` 抓缺陷直到约定范围内 quiet 收敛；深度 `release` 在 hunt 之上执行画像→冻结矩阵→RC 原子构建→全量复测→证据装配→发布裁决。**出口一律三态：Allow / Deny / Escalate。**

运行环境：Python 3.10+；Web 采集需 Playwright 或 playwright-mcp；axe-core 可选；画布 scene JSON 可选。状态目录：目标项目 `.mmit/`。

## Important

- 只在目标项目 `.mmit/` 读写；**单写者** main agent；写 `state.json` 前必须 `O_EXCL` 持 `.mmit/.lock`。
- **证据优先，禁止假通过**：无机读证据不得 PASS；`unavailable` ≠ 通过；axe unavailable 必须记 Blind Spots。
- **无回归测试不得标记 `fixed`**（四条件 CLI `scripts/fix_gate.py --defect-id …` 无 `--regression-green` 必失败）。
- 纯审美 / 无规则 VLM 主观 → **Deferred**，不得 Confirmed。
- **RC 原子性**（release）：矩阵执行、缺陷、生产结果绑定同一 `rc_sha`；禁止热修后复用旧 PASS。
- 禁止自动改写用户项目 `AGENTS.md`（只生成 snippet）。
- 与旧 skill 关系：`mmit-hunter` / `mmit-test` 已合并为本 skill；legacy `.bug-hunter/`、`.mit/` 可用 `scripts/migrate_state.py` 迁入。

## 触发与深度

| depth | 触发例 | 跑什么 | 三态含义 |
|-------|--------|--------|----------|
| `hunt`（默认轻量） | 抓 BUG、design QA、修到没有、布局/无障碍/对比度/画布问题 | Bootstrap → Discover/Probe → Capture → Hunt → Confirm →（可选）Fix → Converge | Allow=范围内 quiet；Deny=仍有 Confirmed；Escalate=盲区/预算尽 |
| `release` | 发布就绪、go/no-go、RC 验收、能不能发版、给候选版本要发布结论 | hunt 全流程 **+** Profile→Matrix 冻结 → Env+脱敏 → Build RC → 全量矩阵 → Triage → Fix → Rebuild → Assemble → Prod Test → Adjudicate | 发布裁决（缺 PRD 不得无条件 Allow；`artifact_ready`×`exposure_ready`） |

**不要**在一次性 lint、纯写功能、或无任何可运行应用的纯静态 code review 时启用本 skill。

## Scope（开跑前确认）

| 项 | 默认 | 说明 |
|----|------|------|
| depth | 触发词推断，否则问 | `hunt` \| `release` |
| mode | `hunt-and-fix` / `test-and-fix` | 或 `*-only` |
| modalities | hunt：`code,web-visual`（+canvas）；release：profile 推导 | 用户点名强制 |
| routes / viewports | `/` `/about`；`375x812` `1440x900` | 指纹区分 viewport |
| base_url / target | dev server / 当前工作区 | 失败则降级并记盲区 |
| rc_ref | HEAD（release） | 候选基线 |
| prod_access | `none` | `none\|readonly\|shadow\|canary` |
| K / max_runs | 2 / 20 | quiet 护栏 |
| max_rc_rounds / wall_clock | 5 / 4h | release 预算 |

## 主循环（U）

阶段标注 **H**=hunt 深度也要跑，**R**=仅 release。

1. **Bootstrap (H)** — `scripts/init_state.py --depth hunt|release`；已有 `state.json` 则 `--resume`。
2. **Profile → Matrix (R)** — `scripts/profile_scan.py` → `scripts/matrix_build.py --freeze`。未冻结不得开跑矩阵。
3. **Environment Up (R)** — `scripts/env_up.py` + `scripts/data_mask.py`；脱敏失败 → Escalate。
4. **Build RC (R)** — `scripts/build_rc.py` 锁 `rc_n`/`rc_sha`。
5. **Discover (H)** — `scripts/discover_routes.py`（可选）。
6. **Capture (H)** — L≥2：`scripts/capture_web.py`（或 playwright-mcp 按 capture-protocol）。
7. **Hunt (H)** — `scripts/hunt_round.py`：probe 矩阵 → layout/contrast/ux → canvas → FP 白名单 → 指纹 → summary。或逐步 `layout_probe.py` / `contrast_probe.py` / `ux_flow.py` / `canvas_probe.py`。
8. **Confirm (H)** — L3 证据门槛（截图/几何 + selector + 复现 + 机器规则）才 Confirmed；主观 → Deferred。见 [`references/confirm-protocol.md`](references/confirm-protocol.md)。
9. **Fix + Regression (H)** — 仅 Confirmed；`scripts/fix_gate.py` 四条件 CLI（`--defect-id`）无 `--regression-green` 必失败；探针实门 `run_fix_gate` 为增强证据。见 [`references/fix-gate.md`](references/fix-gate.md) 与 [`references/fix-regression.md`](references/fix-regression.md)。路由三档见 [`references/compose-escalate.md`](references/compose-escalate.md)。
10. **Converge (H)** — `scripts/converge_check.py` quiet 四条件（策略覆盖、无新 Confirmed、无回归、预算内）。`quiet_streak ≥ K` 收敛。
11. **Matrix Full Test (R)** — `scripts/matrix_run.py` required+optional；探针失败记 Blind Spot。缺陷 `scripts/defect_register.py` P0–P3。
12. **Rebuild (R)** — 仍有阻塞且预算内 → 重建 RCn+1，全量复测。
13. **Assemble (R)** — `scripts/assemble_report.py` / `assemble_signals.py`。
14. **Prod Test (R)** — 授权内 `scripts/prod_probe.py`；无授权显式缺失声明。
15. **Adjudicate (R)** — agent 综合 SIG+RPT+EVD+PRD → `RELEASE_DECISION.md`。
16. **Escalate (H/R)** — 预算尽/硬阻塞 → `scripts/escalate.py`。

### quiet 四条件（K 默认 2）

1. 执行了 ≥2 条当前 degrade 允许的策略；  
2. 策略集覆盖 `modalities_enabled` 中每个仍可用的 modality；  
3. 新 Confirmed == 0；  
4. 无新回归（功能失败 / 视觉 diff 超阈 / 新 axe 违规）。

## 三态出口

- **Allow** — hunt：`converged`；release：四项互证且分层条件满足（可条件 Allow）。
- **Deny** — hunt：仍有 Confirmed 未修；release：阻塞性缺陷/证据不支持发布。
- **Escalate** — 盲区过大、oracle 不可判定、脱敏/权限失败、预算尽、四项严重冲突、用户中止。

分层发布（release）：`artifact_ready` 与 `exposure_ready` 分离；`exposure_ready=false` 时只能条件 Allow 或 Deny 全量。

## 交付物

| 深度 | 路径 |
|------|------|
| hunt | `.mmit/hunts/<run>/` + 可选 `.mmit/bugs/`；导出 `scripts/export_report.py` |
| release | `.mmit/deliverables/TEST_REPORT.md`、`evidence/`+`EVIDENCE_INDEX.md`、`adjudication_signals.json`、`RELEASE_DECISION.md`；升级 `.mmit/escalation/` |

机器可读：`scripts/export_report.py`（字段见 [`references/export-schema.md`](references/export-schema.md)）。

## 状态与并发

```text
.mmit/
  .lock  state.json  fingerprints.json  fp_patterns.json
  bugs/  flows/  baselines/
  hunts/          # hunt 轮次 runs/captures/findings
  tests/          # profile.json matrix.json runs/ defects/
  deliverables/  escalation/
```

禁双会话对同一项目同时跑本 skill。legacy 迁移：`scripts/migrate_state.py`（`.bug-hunter/` 与 `.mit/` → `.mmit/`）。

## Examples

**应触发**

1. 「帮我抓一下这个前端项目的 BUG，布局好像有点炸」→ depth=hunt → Capture+Hunt+Confirm → 可选 Fix → quiet → 三态。
2. 「hunt until clean，看看无障碍和对比度」→ modalities 含 web-visual → 优先 axe/contrast → L3 证据 → 连续 K 轮 quiet 停。
3. 「这版能不能发？」→ depth=release → 冻结矩阵 → RC 全量 → 脱敏硬门 → 四项裁决 → Allow/Deny/Escalate。
4. 「design QA 海报导出尺寸不对，有按钮被裁切」→ canvas+layout 交叉确认 → 机器数值为准。

**不应触发**

- 「帮我看下这段 Python 有没有语法错误」→ 一次性静态检查 → 不启用。
- 「给这个 API 加一个新接口」→ 纯功能开发 → 不启用。

## 禁止

- 把 DESIGN.md 整篇塞进本文件；
- 无锁覆盖 `state.json`；
- 未授权页面截图当 bug；
- 纯主观审美直接 Confirmed；
- 静默降级不记 Blind Spots；
- 把 axe `unavailable` 当成通过；
- 无证据假 PASS / 无回归标 `fixed`；
- 热修后不重建 RC 即宣告 Allow；
- 未脱敏生产数据入包；
- 将 quiet 或单一门禁颜色当作发布出口；
- 自动改写用户项目 `AGENTS.md`（只生成 snippet）。

## Troubleshooting

| 现象 | 处理 |
|------|------|
| Probe 失败 / 无 base_url | 先起应用；仍失败则降级并记 Blind Spots |
| 无 Playwright | 用 playwright-mcp 按 capture-protocol；或 `--skip-capture` 降级 |
| axe unavailable | 保持 L2；**禁止**当通过；记 Blind Spots |
| 写 state 抢锁失败 | 重试 ≤3 后中止；禁双会话 |
| quiet≥K 但仍觉有问题 | 查 quiet 四条件是否真满足；补 route×viewport 后再跑 |
| 修后复现同一 BUG | `fix_gate.py` 拒绝则不写码；换策略/Deferred；禁同栈重试 |
| 旧目录 `.bug-hunter`/`.mit` | `scripts/migrate_state.py` 迁入 `.mmit/` |
