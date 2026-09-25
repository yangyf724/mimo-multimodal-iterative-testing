# 修复纪律与回归固化

修复（B6）与回归规则。原则：**无回归测试不得标记 fixed。** Fix Gate 由 `scripts/fix_gate.py` 机器判定。

## 修复纪律

1. 只修 **Confirmed** 缺陷；**一次一修**。
2. **无回归测试不得标记 fixed。**
3. 修复必须过 Fix Gate 四条件（下表）。
4. 失败回滚或换策略（local / lite / compose 门控）；**禁止同构重试**（≥2 次失败必须重定位或升级）。
5. 修复后进入 Rebuild：重建 RCn+1，**全量复测**；禁止热修后复用旧 PASS 宣告 Allow。

## Fix Gate 四条件（机器判定）

| 条件 | 代号 | 含义 |
|------|------|------|
| 目标已清除 | `target_cleared` | 同缺陷同路径不再命中 |
| 无新增高危 | `zero_new_high` | 无新增 P0/P1 |
| 非目标稳定 | `non_target_stable` | 非目标面无意外回归 |
| 回归绿 | `regression_green` | 新增/加强回归测试退出码 0 |

- 四条全部满足才可标记 fixed。
- 任一条失败 → 不得 fixed；回滚或换策略，失败次数受 `max_fix_failures_per_defect` 护栏约束（见 `escalate.md`）。

## 回归测试固化（按来源缺陷面）

| 来源缺陷面 | 回归形态 |
|------------|----------|
| API | contract / CDC、黄金响应 |
| Web | route×viewport probe、视觉基线 |
| CLI | golden exit/stdout/stderr |
| DB | migrate + query/constraint fixture |
| Mobile/Desktop | 安装启动冒烟、关键流 |
| Infra | readiness、secret scan |
| AV / Canvas / 3D / XR | 可播/加载/尺寸/预算断言 |
| Plugin | host-API pin、install/upgrade |
| Code | 最小复现单测/集成测 |
| Prod | 合成旅程 / canary SLI 断言 |

## 回归要求

- 回归测试与缺陷 **1:1 或 1:N 绑定**（一个缺陷至少一条可重复断言）。
- 回归用例进入常规矩阵执行集（required 侧），后续 RC 全量复测时自动覆盖。
- 回归结果绑定修复后的 `rc_sha`；旧 RC 的绿不算新 RC 的绿。
- 探针失败记 Blind Spot，禁止把「跑不起来」当通过。

## 与 RC Loop 的关系

```text
Triage → Fix + Regression（Fix Gate）→ Rebuild RCn+1 → Matrix Full Test
```

- RC 原子性：B4–B8 必须针对同一 `rc_sha`；源码修改后不得直接复用旧结果宣告 Allow。
- 仍有阻塞且预算内 → 继续循环；超护栏 → Escalate/Deferred（`escalate.md`）。

## 检查清单

- [ ] 仅 Confirmed 进入修复，一次一修
- [ ] 每个 fixed 都有回归测试且退出码 0
- [ ] Fix Gate 四条件全过
- [ ] 无同构重试（≥2 次失败已重定位或升级）
- [ ] 修复后已重建 RC 并全量复测
