# 真实生产环境测试（E2）

生产侧测试协议。产物：`.mit/deliverables/prod_test_results.json`，或 `PROD_RESULTS_MISSING.md` 显式缺失声明。执行入口：`scripts/prod_probe.py`。**仅在授权范围内操作。**

## prod_access 授权级别

| 级别 | 允许动作 |
|------|----------|
| `none` | 不测生产；报告必须声明「生产结果缺失」 |
| `readonly` | 只读健康检查、合成探测、脱敏日志/指标抽样 |
| `shadow` | 影子流量对比（若具备） |
| `canary` | 小流量金丝雀（须用户明确批准） |

- 级别来自 `profile.prod_access`，**须用户确认**（Scope 表）。
- 未授权不得自行升权；越权按硬失败 → Escalate。
- `none` 时 PRD 缺失：裁决侧不得无条件 Allow（见 `adjudication.md`）。

## 推荐协议：Canary vs Control

1. 选择少量**用户可感知 SLI**（错误率、延迟分位、关键旅程成功率），避免嘈杂资源指标。
2. 金丝雀与对照**同期对比**，禁止仅 before/after 自比。
3. 一次只观察一个变更；保证指标可归因。
4. 观察窗覆盖有代表性的流量；聚合窗口 ≤ 观察窗。
5. 偏离阈值 → 暂停/回滚并记缺陷；健康 → 按策略放量。
6. 记录 error budget 消耗；**烧穿阈值直接保守裁决**。

### SLI 示例（裁决信号 `prod_test.slis`）

- `http_5xx_rate`
- `p95_latency`
- `journey_success`

### 结果记录要点

- `mode`：如 `canary_vs_control`、`readonly_probe`、`shadow`、`synthetic_only`
- `critical_path_pass`：关键路径是否通过
- `control_delta_error_rate`：相对对照的错误率差
- `error_budget_burn`：error budget 消耗
- `rollback_ready`：是否具备回滚能力

## Synthetic Monitoring（推荐作为 E2 主探针）

对生产（或准生产）持续注入**合成用户旅程**，覆盖：

- 可用性
- 关键事务
- 性能
- 第三方依赖

探针自身健康也须监控；探针故障不得计为业务通过。

## 禁止（硬约束）

- 未授权写路径压测
- 破坏性数据操作
- 对真实用户切换未批准版本
- 将未脱敏生产数据写入证据包

## 与其他文档

- 授权与画像字段 → `profile-schema.md`
- 环境层级 → `env-layers.md`
- 脱敏 → `data-masking.md`
- 缺失/失败对裁决的影响 → `adjudication.md`
