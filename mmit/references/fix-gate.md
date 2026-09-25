# Fix Gate（可判定回归门）— Phase 1

> **双 CLI（统一 skill）**
>
> | 模式 | 何时用 | 退出条件 |
> |------|--------|----------|
> | 四条件 `--defect-id …` | release 缺陷 / 标记 `fixed` | 无 `--regression-green` **必失败**；四条件全绿 exit 0 |
> | 探针实门 `run_fix_gate --bug …` | hunt 修复后复验 | target_cleared / zero_new_layout / pixel_gate / unit_green |
>
> 四条件为**必评**；探针为**增强证据**。`--defect-id` 路径强制回归绿；`run_fix_gate` 在未给 `--test-cmd` 时 `unit_green` 可 skipped——**不得**据此单独标 `fixed`（见 [`fix-regression.md`](fix-regression.md)）。

1. 只修 **Confirmed**；Deferred 需用户点头。
2. 一次一修。
3. 回归门由 `scripts/fix_gate.py` 机器判定（禁止主观「看起来还行」）：

| 检查 | 通过条件 |
|------|----------|
| `target_cleared` | 同 `rule_id` 在同 route×viewport 不再命中（对修复后 captures 重跑 probe） |
| `zero_new_layout` | 回归矩阵重跑 layout+contrast，相对已有 fingerprints **零新增** |
| `pixel_gate` | 仅目标 route×viewport 允许 diff；其他已扫 cell 超阈 → fail，除非 intentional 审批 |

Phase 3：像素基线完整性可用 [`ci-gate.md`](ci-gate.md) 的 `baseline_lock.py verify`；有意变更仍走 `visual_diff.py approve`（approvals 必须带与当前文件一致的 `sha256`）。
| `unit_green` | 若提供 `--test-cmd` 则 exit 0 |

4. 失败 → agent 回滚（`git checkout` 等），记 `fix-failed`；更新 `fix_attempts`。分流见 [`compose-escalate.md`](compose-escalate.md)：未超 `max_local_attempts`/`lite_max_attempts` 时可换策略重试或转 `lite`（仍须过本门）；命中 oracle gap / 契约重定义 / `user_pr` 且 `escalations_used < max_compose_escalations` 时门控升 `compose`；否则同一 bug 失败 ≥ `max_fix_failures` → Deferred。**禁止同构重试**（失败 ≥2 次必须重定位/换策略/升档/Deferred）。

## 用法

```powershell
# 修复后重新采集
& $env:MIMO_PYTHON mmit/scripts/capture_web.py --root <project> --run-id run-fix --out <project>/.mmit/runs/run-fix/captures

# 跑门
& $env:MIMO_PYTHON mmit/scripts/fix_gate.py --root <project> `
  --bug bug-0001 `
  --captures <project>/.mmit/runs/run-fix/captures `
  --baseline-dir <project>/.mmit/baselines/web `
  --test-cmd "npm test" `
  --regression-mode matrix
```

退出码：`0` 门通过 · `1` 任一检查失败 · `2` bug 未找到。

结果写入 `runs/run-N/fix-verify.json`。

## intentional_visual_change

非目标路由像素 diff 默认 fail。放行方式：

1. `visual_diff.py approve --route … --viewport … --reason "..."`（写 `baselines/approvals.jsonl` 并更新基线）；或
2. 提供 `--fix-verify` JSON，含 `"intentional_visual_change": true` 与 `intentional_cells: ["/about@375x812"]`。

## 路由（Local / Lite / Compose）

本文件只定义 **Local/Lite 的机器门禁**。档位选择、bug packet、compose 升格与回 hunt 协议见 [`compose-escalate.md`](compose-escalate.md)。`fix_gate.py` 检查语义在所有档位**不降级**。

## 脚本不做的事

- 不修改源码；
- 不自动 `git` 回滚（回滚是 agent/SKILL 动作）；
- 不写 `bugs/**`（状态迁移由 main agent 持锁完成）。
