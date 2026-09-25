# Agent 综合裁决

是否允许发布的依据，必须由 agent **综合** SIG / RPT / EVD / PRD 四项判断，**禁止**只看自动门禁颜色或只读报告标题。产物：`.mit/deliverables/RELEASE_DECISION.md`。

## 四项依据

| 依据 | 代号 | 内容 |
|------|------|------|
| 裁决信号 | SIG | `adjudication_signals.json` 结构化质量信号 |
| 测试报告 | RPT | `TEST_REPORT.md` 完整叙述与指标 |
| 证据包 | EVD | 可复核的机读/多媒体证据 |
| 真实生产环境测试结果 | PRD | E2 结果或显式缺失说明 |

### 规则

1. **四项互证**：报告结论须能落到证据；信号须与报告一致。
2. **冲突取保守**：不一致时取更严格一侧，并在 `RELEASE_DECISION.md` 写明冲突。
3. **缺项不得无条件 Allow**：尤其 PRD 缺失时，只能条件 Allow（如仅灰度）或 Deny/Escalate。
4. **硬失败直决**：脱敏失败、生产关键路径失败、证据不可信 → Deny/Escalate，不得被其他「好看」信号抵消。

## 裁决信号模式（摘要）

```json
{
  "rc_id": "RC-3",
  "rc_sha": "…",
  "matrix_rev": "m2",
  "signals": {
    "build_ok": true,
    "matrix_required_coverage": 1.0,
    "optional_degraded": ["xr-sim-only"],
    "open_p0": 0,
    "open_p1": 0,
    "open_p2_accepted": 1,
    "regression_green": true,
    "device_coverage": 0.8,
    "data_mask_clean": true,
    "release_layers": {
      "artifact_ready": true,
      "exposure_ready": false,
      "exposure_constraint": "canary_5pct_only"
    },
    "prod_test": {
      "available": true,
      "mode": "canary_vs_control",
      "slis": ["http_5xx_rate", "p95_latency", "journey_success"],
      "critical_path_pass": true,
      "control_delta_error_rate": 0.001,
      "error_budget_burn": 0.12,
      "rollback_ready": true
    },
    "oracle_quality": {"k": 3, "agreement_rate": 0.86, "fp_rate_estimate": 0.08},
    "contract_breaking_unreviewed": false,
    "blind_spots": ["xr-no-hmd"],
    "quiet_streak": 2
  }
}
```

- `quiet_streak` 仅为**过程健康信号**，不是发布出口。
- 发布出口只有：**Allow / Deny / Escalate**。

## 分层发布语义

| 字段 | 含义 |
|------|------|
| `artifact_ready` | RC 制品在测试意义上可交付 |
| `exposure_ready` | 可对用户/流量放量 |
| `exposure_constraint` | 放量约束（暗启动、金丝雀比例、白名单等） |

| artifact_ready | exposure_ready | 裁决 |
|----------------|----------------|------|
| true | true | 可无条件 Allow |
| true | false | **仅条件 Allow**（按 `exposure_constraint`）或 Deny 全量 |

- 将「测通过」与「放量」分离，对齐 Progressive Delivery 的 Deploy≠Release。

## 裁决输出

| 结论 | 条件 | 对外表述 |
|------|------|----------|
| **Allow Release** | 四项齐备且综合支持；残余风险可接受 | **该版本可正常发布使用**（附条件则一并说明） |
| **Deny Release** | 开放 P0/P1、生产失败、证据冲突/不可信、覆盖不足等 | **不可发布**；列出阻塞项与修复顺序 |
| **Escalate Human** | 预算尽、硬阻塞、需签字、oracle 不可判定、无生产且不愿在缺失下裁决 | **请人工裁决**；附升级包 |

`RELEASE_DECISION.md` 必须包含：结论、四项依据摘要、冲突点、附带条件、RC 哈希、agent 置信说明（高/中/低及原因）。

## 进入裁决前检查清单

- [ ] profile / matrix 已冻结
- [ ] RC 哈希与构建记录齐备
- [ ] 环境与偏差已声明（含 E2/E3）
- [ ] 脱敏扫描通过
- [ ] required 矩阵已执行
- [ ] 修复均带回归且绿
- [ ] 测试报告完整
- [ ] 证据包索引可复核
- [ ] 裁决信号已生成
- [ ] 生产结果已写入或显式声明缺失
- [ ] Blind Spots 已披露

**清单未完成 → 只能 Escalate 或继续补测，不得 Allow。**
