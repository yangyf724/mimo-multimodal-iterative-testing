# 缺陷分级 P0–P3

发布风险分级。产物：`.mit/defects/*.json`（Triage 步骤 B5）。与来源状态（Confirmed/Deferred）叠加使用，不替代确认门。

## 分级表

| 级 | 定义 | 处理 | 对裁决 |
|----|------|------|--------|
| **P0** | 崩溃、数据丢失、安全漏洞、鉴权绕过、无法安装启动、核心路径不可用 | 立即修 + 强制回归 | 默认 Deny |
| **P1** | 主路径错误、严重性能回退、错误数据、关键 a11y 阻断、制品损坏 | 本轮必修或用户书面接受 | 默认 Deny |
| **P2** | 次要路径、明显视觉回归、部分设备问题、体验差但可恢复 | known-issues 后可条件放行 | 条件 Allow 需用户点头 |
| **P3** | 文案、边缘审美、文档问题、非阻断 polish | backlog | 默认不阻塞 |

## 主观结论规则

**纯审美、无规则可述的 VLM 主观结论 → P3 或 Deferred，不得单独支撑 Deny/Allow 主路径。**

- 可述规则（对比度阈值、尺寸断言、帧率下限）→ 按规则定级。
- 不可述的审美判断 → 最高 P3，或 Deferred。
- 主观 oracle 质量指标（`oracle_quality`：k、agreement_rate、fp_rate_estimate）写入裁决信号；一致率不足 → 保守降级。

## 定级原则

1. **取更保守**：介于两级之间就高不就低（例如疑似数据丢失按 P0 评估直至排除）。
2. **按用户可感知伤害**定级，不按修复难度。
3. **跨模态放大**：同一根因影响多 surface，按最高影响面定级，并合并指纹（去重）。
4. **证据缺陷**：融合层不一致（报告≠证据）≥P1，须先修复再裁决（见 `test-layers.md`）。
5. **只修 Confirmed**：Deferred/P3 可进 backlog，不阻塞（P2 需用户接受记录）。

## 与处理状态的关系

| 状态 | 含义 |
|------|------|
| Confirmed | 已复现/确认，进入修复 |
| Deferred | 暂不处理（主观、非阻塞、或策略性推迟） |
| fixed | 已修复 **且** 回归绿（无回归不得标记） |
| open | 仍开放（计数进裁决信号 `open_p0` 等） |

- `open_p0` / `open_p1` > 0 → 默认 Deny。
- `open_p2_accepted` → 条件 Allow 需用户点头。
- P3 默认不阻塞。

## 记录字段建议

```json
{
  "id": "D-12",
  "modality": "api",
  "layer": "ML",
  "severity": "P1",
  "status": "confirmed",
  "rc_sha": "…",
  "matrix_rev": "m2",
  "evidence_ids": ["E-34"],
  "fingerprint": "…",
  "user_accepted": false
}
```

## 检查清单

- [ ] 每个缺陷有 P0–P3 与 modality/layer
- [ ] 主观项已降为 P3/Deferred
- [ ] 融合层不一致 ≥P1 且阻塞裁决
- [ ] P2 用户接受有书面记录
- [ ] 开放 P0/P1 计数与裁决信号一致
