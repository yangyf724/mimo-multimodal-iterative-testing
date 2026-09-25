# 策略库（Phase 3）

modality 仅三值：`code` | `web-visual` | `canvas`。调度与统计用 modality；策略 ID 决定本轮 rule 集。

Phase 3 工程化入口（非 modality 策略，但属于主循环辅助）：`discover_routes.py`、`fp_feedback.py`、`export_report.py`、`baseline_lock.py`、`axe_gate.py`、`ci_gate.py`。

## Phase 2–3 策略集

| ID | modality | 动作 | Oracle | 成本 | 脚本 |
|----|----------|------|--------|------|------|
| `static` | code | typecheck / lint / 安全扫描 | 工具退出码 | 低 | agent |
| `dynamic` | code | 跑测试、复现失败栈 | 测试断言 | 中 | `hunt_round.py --dynamic-cmd` |
| `capture-baseline` | web-visual | 多 viewport 截图 + elements/AX；支持 `--shard i/n` | 采集成功 | 低 | `capture_web.py` |
| `layout-geom` | web-visual | overflow-x / text-clip / overlap / zero-size / off-canvas / touch-target | 几何规则 | 中 | `layout_probe.py` |
| `contrast-type` | web-visual | contrast-text / font-too-small / line-height-tight | WCAG 公式 | 低 | `contrast_probe.py` |
| `responsive-matrix` | web-visual | routes×viewports 重复 layout+contrast | 几何/对比度 | 中 | `hunt_round.py` |
| `visual-diff` | web-visual | 与 baseline 像素 diff | diff_ratio 阈值 | 中 | `visual_diff.py` |
| `a11y-axe` | web-visual | axe-core（若可安装/npx） | axe 违规 | 低 | `axe_gate.py` / agent |
| **`ux-flow`** | web-visual | dead-link / missing-feedback / empty-state + 符号化 pre/post | 静态规则 + flow | 中 | `ux_flow.py` |
| **`canvas-safe`** | canvas | safe-area / export-mismatch / z-order | 画布几何 | 中 | `canvas_probe.py` |
| **`canvas-asset`** | canvas | low-res / aspect-distort | 资源元数据 | 低 | `canvas_probe.py` |
| **`vlm-audit`** | web-visual | 双视角一致候选 + 与机器 finding 交叉 | ≥2 视角一致 | 高 | `vlm_audit.py`（agent 产出 views） |

## 单轮编排

```powershell
& $env:MIMO_PYTHON mmit/scripts/hunt_round.py --root <project> --run-id run-1 `
  [--skip-capture] [--captures DIR] [--dynamic-cmd "npm test"] [--write-candidates] `
  [--flows DIR] [--canvas-items PATH] [--fp-patterns PATH]
```

步骤：（可选 capture / shard merge）→ probe MANIFEST 全矩阵（layout+contrast+ux 静态）→ 可选 flows / canvas → **FP 白名单 suppress** → register 指纹 → `runs/run-N/summary.json` → converge 评估。**不**自动 Confirm/修代码。suppressed 不计入 `new_count`。

## 轮换规则

1. 首轮（degrade≥L2）：`static` + `dynamic` + `capture-baseline` + `layout-geom` + `contrast-type`（有 axe 再加 `a11y-axe`；有 flow 再加 `ux-flow`）。
2. 之后：cursor 轮换；优先上轮有新发现的 modality。
3. `quiet_streak ≥ 1`：加压 `visual-diff` / `responsive-matrix` / `ux-flow` / `canvas-*` / `vlm-audit`。
4. **禁止连续两轮完全相同策略集**。

## Degrade Ladder

| 级别 | 条件 | 允许策略 |
|------|------|----------|
| L0 | 无法开工 | （停止） |
| L1 | 有源码，无浏览器 | `static` `dynamic` `generate` `structural` `meta-test` |
| L2 | 可开页，无 axe | L1 + `capture-baseline` `layout-geom` `contrast-type` `responsive-matrix` `visual-diff`（静态 ux 规则可跑） |
| L3 | L2 + axe | L2 + `a11y-axe` |
| L4 | L3 + 画布 items | L3 + `canvas-safe` `canvas-asset` `vlm-audit` `ux-flow` |

只升不隐式降：中途失败可本轮降级，必须写入 summary 与 REPORT Blind Spots。有有效 canvas items 时 `hunt_round` 可从 L3 升 L4（`degrade_elevated_by: canvas-items`）。

**已有 captures 时**：`hunt_round.py --skip-capture` 或 MANIFEST 存在则直接 probe（视为 web-visual 已演练）。

**并行采集**：subagent 用 `--shard i/n`，main 用 `capture_web.py merge`；见 [`subagent-capture.md`](subagent-capture.md)。

## Phase 3+（未实现，仅索引）

`generate` `structural` `speculative` `meta-test` — 完整配方见 DESIGN.md §5.1。

## 策略输出约定

每条 raw finding 至少包含：

```json
{
  "title": "...",
  "modality": "code|web-visual|canvas",
  "category": "...",
  "severity": "high|medium|low",
  "statement": "期望 vs 实际",
  "location": {"surface":"web","route":"/","viewport":"375x812","selector":"..."},
  "metrics": {},
  "rule_id": "overflow-x",
  "core_assertion_digest": "overflow-x|horizontal-overflow",
  "evidence_level_target": "L3",
  "detected_by": "layout-geom|contrast-type|visual-diff|dynamic",
  "status": "candidate"
}
```
