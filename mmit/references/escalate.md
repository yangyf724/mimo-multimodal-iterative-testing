# 预算、护栏与人工升级

预算耗尽或硬阻塞时升级人工。产物：`.mmit/escalation/`（由 `scripts/escalate.py` 生成）。原则：**不擅自放行**。

## 默认预算与护栏

| 护栏 | 默认 | 触发动作 |
|------|------|----------|
| `max_rc_rounds` | 5 | 停止重建，Escalate |
| `max_wall_clock` | 4h | 保存现场，Escalate |
| `max_fix_failures_per_defect` | 2 | 换策略/升档/Deferred |
| `max_p0_fix_rounds` | 3 | Escalate |
| `max_compose_escalations` | 1 | 不再自动升 compose |
| `max_vlm_calls`（可选） | 按项目 | 超限降级主观通道并披露 |

- Scope 开跑确认表可覆盖默认值（用户确认后生效）。
- 触发护栏后：**停止同类自动重试**，保存现场，进入升级或 Deferred 路径。
- `max_fix_failures_per_defect` 达到 2：禁止同构重试，必须换策略/升档或 Deferred。

## 必须升级人工

1. 脱敏失败、密钥泄露、越权访问生产数据。
2. 需产品/法务/合规签字的决策。
3. 环境/设备/生产权限缺失且无法本地消除。
4. 需求或契约歧义导致 oracle 不可判定。
5. 预算耗尽仍有开放 P0/P1。
6. 四项依据严重冲突且无法保守收敛。
7. 用户中止或改道。

## 升级包布局

```text
.mmit/escalation/
  REASON.md
  TEST_REPORT.md
  adjudication_signals.json
  evidence/
  prod_test_results.json    # 或 PROD_RESULTS_MISSING.md
  defects_open.json
  env_manifest.json
  next_actions.md           # 建议人工动作 1–5 条
```

### 各文件要求

| 文件 | 要求 |
|------|------|
| `REASON.md` | 卡点、已覆盖范围、盲区、触发的护栏/必须升级条目 |
| `TEST_REPORT.md` | 当前完整测试报告（十节，见 `deliverables.md`） |
| `adjudication_signals.json` | 最新裁决信号 |
| `evidence/` | 证据包（可复核，已脱敏） |
| `prod_test_results.json` | E2 结果；无则 `PROD_RESULTS_MISSING.md` 显式缺失 |
| `defects_open.json` | 开放缺陷（P0–P3） |
| `env_manifest.json` | 环境清单与偏差 |
| `next_actions.md` | 建议人工动作 **1–5 条** |

## Escalate 对外表述

> 无法自动完成发布裁决，已升级人工。
> 卡点：…　已覆盖：…　盲区：…　升级包：`.mmit/escalation/`

- 与 Allow/Deny 话术模板一致（见设计附录 B）。
- Escalate 为三出口之一；不是失败，是保守收敛。

## 状态机

```text
in_progress → escalated   （终态，除非用户显式开启新一轮）
```

## 检查清单

- [ ] 预算/护栏触发点已记录
- [ ] 必须升级条目命中原因已写入 `REASON.md`
- [ ] 升级包八件齐全（或明确标注不可得原因）
- [ ] 未脱敏数据未入包
- [ ] `next_actions.md` 1–5 条可执行
