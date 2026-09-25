# Fix Router — 三档修复路由（compose-escalate v2）

> 准据：根 `DESIGN.md`（Confirm / quiet 不变量）> [`fix-gate.md`](fix-gate.md)（Local 门禁）> 本文（路由）> compose-next 默认契约。  
> 研究索引：`docs/BLUEPRINTS.md`（原 blueprint v1/v2 已压缩；路由行为以本文为准）。

修复只针对 **Confirmed** 且 `mode=hunt-and-fix`。Candidate / Deferred **永不**自动进入任何修复档或 compose-next。

## 三档一览

| 档 | `fix_route` | 何时用 | 结束方式 |
|----|-------------|--------|----------|
| **Local Pipeline** | `local` | oracle 可判定 + 编辑点小 + 沿既有契约 | `fix_gate.py` 通过 → 回 hunt |
| **Escalate-Lite** | `lite` | oracle 在但需重定位/二次结构化，尚不需产品 Spec | 再定位后仍过 `fix_gate.py`；不 load compose-next |
| **Compose-Next** | `compose` | oracle gap / 契约重定义 / 用户要 PR·Spec | 门控后 slim compose → **强制回 hunt Converge** |

默认：**能 local 不 lite，能 lite 不 compose**。

## 判定顺序（每条 Confirmed）

1. **前置**：Confirmed？`mode=hunt-and-fix`？预算与锁可用？否则不修或仅报告。  
2. **能否写出机器 oracle？**（`oracle.pass_condition`：如「同 `rule_id` 在同 route×viewport 不再命中」+ 回归矩阵零新增）  
   - **否** → 倾向 `compose`（`oracle_gap`）或用户确认后 Deferred；**禁止**「看起来修好了」。  
3. **期望行为是否本身有歧义 / 需产品决策？**  
   - **是** → `compose`（`contract_change`）。  
4. **用户是否明确要求 PR / Spec / 工程交付？**  
   - **是** → `compose`（`user_pr`），仍需 Confirmed + packet。  
5. **编辑广度**：预计编辑点 ≤ `budget.max_local_edit_sites`（默认 3）且同一契约内 → 优先 `local`（`oracle_ok`）。  
6. **介于中间**：Local 未过且预算未尽，或编辑点 4–`max_lite_edit_sites`（默认 6）/ 跨包仍沿既有契约，或需要重定位假设 → `lite`（`needs_relocalize` 或 `edit_breadth`）。  
7. **单点可机器验收**（overflow / contrast / touch-target / aria 等）→ **不得**仅因「在 UI 上」升 `compose`。

判定结果写入 bug JSON：`fix_route`、`fix_reason_codes`；并更新 `state.fix_router.by_route`。

## 预算与递减

| 参数 | 默认位置 | 默认值 |
|------|----------|--------|
| `max_local_attempts` | `state.budget` | 3 |
| `lite_max_attempts` | `state.budget` | 2 |
| `max_compose_escalations` | `state.budget` / `state.fix_router` | 2 |
| `max_fix_failures` | `state.budget` | 5（既有，保留） |
| `max_local_edit_sites` | `state.budget` | 3 |
| `max_lite_edit_sites` | `state.budget` | 6 |

- **禁止同构重试**：同一 diff 策略失败两次后，必须重定位、换 oracle/策略、升档或 Deferred。  
- 同 bug 连续修复失败 ≥2 → `fix_attempts.diminishing = true`，REPORT 必须可见。  
- `escalations_used` ≥ `max_compose_escalations` → 本 session 不再自动升 compose，改 Deferred/报告；用户仍可显式要求。

## Local Pipeline

1. 结构化定位（文件/选择器/规则命中处），禁止只凭截图盲改。  
2. 可选：对同一 Confirmed 生成 ≤3 候选补丁，用**复现 probe + 回归**选优，禁止「感觉更好」。  
3. 修复后采集 → [`fix-gate.md`](fix-gate.md) `fix_gate.py`。  
4. 门通过：状态 → Fixed；更新 `fix_attempts`；继续 hunt/Converge。  
5. 门失败：回滚（agent 动作）；`fix_attempts.local += 1`；未超 `max_local_attempts` 且可换策略 → 重试或转 `lite`；超预算且无 compose 条件 → Deferred + 报告。

## Escalate-Lite

**不做**：load `compose-next`；开 worktree 仅因「升 lite」；跳过 `fix_gate`。

1. 写入/更新 **bug packet**（见下节）。  
2. 重定位：结合代码结构、测试/失败输出、route 序列，更新编辑点假设。  
3. 修复尝试 ≤ `lite_max_attempts`，每次仍跑 `fix_gate.py`。  
4. 成败处理同 Local；失败且命中 compose 条件且 `escalations_used < max` → 门控升 compose；否则 Deferred。

## Compose-Next 升格

**门控**：scope 预授权，或升格前 `question`（单点修 / 升 compose / 只出报告）。不得静默 load compose-next。

1. 确认 packet 完整（尤其 `oracle`、`serving_tree`、`base_url`、attempts）。  
2. load **compose-next**；**slim**：无设计面可跳 Grill/Spec（compose 自带捷径）；有契约重定义才写 feature 文档。  
3. compose 的 implement/verify/review 遵守 compose-next；**禁止** review/implement subagent 写 `.bug-hunter/state.json`（单写者）。  
4. Finalize 后 **必须回 hunt**：`base_url`/`serving_tree` 指向修复树 → 复测相关 route×viewport → Converge → REPORT。  
5. compose Review PASS **≠** quiet；无浏览器时写 Blind Spots，不得假装收敛。  
6. 合并/PR/删 worktree **不自动做**；报告 branch/base/head/workspace/packet 路径。

## Bug Packet SOP

路径建议：`.bug-hunter/bugs/<bug-id>/packet.json`（main agent 持锁写 `bugs/**`）。

最小字段：

```json
{
  "bug_id": "bug-0001",
  "fingerprint": "…",
  "status_at_handoff": "confirmed",
  "fix_route": "lite",
  "reason_codes": ["needs_relocalize"],
  "modality": "web-visual",
  "category": "ui-layout",
  "location": {
    "surface": "web",
    "routes": ["/login"],
    "viewports": ["375x812"],
    "selectors": ["[data-testid=submit]"],
    "bbox": {"x": 340, "y": 620, "w": 120, "h": 48}
  },
  "repro": {
    "steps": ["打开 /login", "viewport 375x812", "观察主按钮右缘"],
    "sequence_routes": ["/", "/login"]
  },
  "oracle": {
    "type": "rule+geometry",
    "rule_id": "overflow-x",
    "pass_condition": "同 rule_id 在同 route×viewport 不再命中",
    "regression_matrix": "all_scanned_cells_zero_new"
  },
  "attempts": {"local": 1, "lite": 0, "diminishing": false},
  "last_fix_gate": {"result": "fail", "file": "runs/run-N/fix-verify.json"},
  "serving_tree": ".",
  "base_url": "http://127.0.0.1:5173",
  "budget": {"max_local_attempts": 3, "lite_max_attempts": 2, "max_compose_escalations": 2},
  "deferred_notes": null
}
```

compose / lite **只消费 packet 与仓库证据**，不接受无 fingerprint 的口头「有个 UI 问题」。

## Worked examples（正例）

**例 A — 应 `local`**  
Confirmed：`overflow-x` @ `/` × `375x812`，selector 已知，改一处 `max-width`/布局即可。  
`reason_codes: ["oracle_ok"]` → 定位 → 修复 → `fix_gate.py` `target_cleared` + 回归矩阵零新增 → Fixed → Converge。

**例 B — 应 `lite`**  
Confirmed：`contrast-text`，oracle 清楚，但牵涉主题 token 与两处组件，首次 Local 改色后非目标 route 像素门失败。  
`reason_codes: ["needs_relocalize"]` → packet → 重定位设计 token → 第二次修复过 `fix_gate` → Fixed。

## Worked examples（负例）

**例 C — 不应升 `compose`**  
单点 `touch-target` 命中，selector 与 44px 规则明确。  
升 compose = 流程税 + 复杂度偏见。应走 `local`。

**例 D — 不应「假修」**  
「登录流程整体体验不对」，无 rule_id、无 pass_condition、无复现矩阵。  
→ 不得 Confirmed 后盲修；应 Deferred 或在用户参与下定义契约再考虑 `compose`（`oracle_gap`/`contract_change`）。禁止无 oracle 改代码后声称 Fixed。

**例 E — 不应并行互嵌**  
在 compose Implement 中途再开第二会话对同一项目 full hunt，或让 Reviewer 写 `state.json`。  
→ 禁止。状态单写；Verify/Review 与 hunt 串行；证据分层。

## 与 export / REPORT

- `export_report`：bug 上的 `fix_route` / `fix_reason_codes` / `fix_attempts` / `diminishing` / `packet_path` 有则写入；顶层 `fix_router`、`budget` 来自 state。  
- REPORT 必须能回答：走了哪一档、为何、试了几次、是否 diminishing、compose 是否已回 hunt 复测、Blind Spots。

## 禁止

- Confirmed 全部升 compose  
- 无 oracle / 无 packet 的 compose 交接  
- 同构无限重试  
- 把 compose Verify/Review PASS 当作 hunt quiet  
- compose-next 内部再嵌套自动 hunt（内置 skill 明文 no internal hand-offs；反向仅允许本门控升格）  
- subagent 写 `.bug-hunter` state / fingerprints / bugs  
- 静默降级、axe unavailable 当通过  
- 自动改写用户项目 `AGENTS.md`
