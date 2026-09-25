# 研究蓝图索引（Blueprints）

> 状态：**索引**。原 `docs/blueprint/hunt-escalate-compose.md`（v1）与 `hunt-escalate-compose-v2.md`（v2）正文已删除。  
> **blueprint ≠ compose Spec**；运行时行为真源：根 `DESIGN.md` > `mmit-hunter/references/fix-gate.md` > `mmit-hunter/references/compose-escalate.md`。  
> 历史 compose feature 文档结论见 `CHANGELOG.md` 与 `docs/ACCEPTANCE.md` / `docs/METRICS.md`。

## 适用范围

本索引只覆盖 **Hunt → Fix 升格路径** 的研究结论（曾用于 Fix Router）。不重写 hunt 算法、quiet 四条件、指纹或探针。

## 结论摘要

### v1（升格桥）

- compose-next **不可**内嵌 hunt；hunt **可**在 Fix 门控后升格 compose-next。
- 缺口不是「要不要修」，而是「大修没有 Spec / Worktree / Review」。
- 默认路径仍是本地 `fix_gate.py`；compose 仅作**窄口**工程升格。
- 非协商项不放宽：Candidate/Deferred 不自动进 compose；单写者；探测失败记 Blind Spots。

### v2（三档路由 · 现行为依据）

- v1 的「本地 fix_gate vs compose-next」二分方向正确但**过粗**。
- 文献支持：**三档路由 + 预算递减 + 结构化交接包 + 可机器判定的升格门**。
- 默认路径应比 v1 **更偏简单流水线**（Agentless 气质）；compose-next 仅留给 oracle / 设计契约缺口。

| 档 | 名称 | 何时用 |
|----|------|--------|
| L | Local Pipeline | oracle 可判定 + 编辑点小 + 沿既有契约 |
| Lite | Escalate-Lite | oracle 在但需重定位/二次结构化，尚不需产品 Spec |
| C | Compose-Next | oracle gap / 契约重定义 / 用户明确要 PR·Spec |

- 默认：**能 local 不 lite，能 lite 不 compose**。
- 升 C 主门：`oracle_gap` / `contract_change` / `user_pr`；单点 overflow/contrast/touch-target/aria **不得**仅因「在 UI 上」升 C。
- 硬预算默认：`max_local_attempts=3`、`lite_max_attempts=2`、`max_compose_escalations=2`；**禁止同构重试**；连续失败 ≥2 记 `diminishing`。
- 升档交接唯一工件：**bug packet**（含 `oracle.pass_condition`、`serving_tree`、attempts 等）；禁止口头「帮我修 UI」。
- Compose Finalize 后 **必须回 hunt Converge**；compose Review PASS ≠ quiet。

### 准据优先级（交付后仍有效）

1. 仓库根 `DESIGN.md`（quiet / 指纹 / Confirm）  
2. `references/fix-gate.md`（Local 门禁）  
3. `references/compose-escalate.md`（三档路由操作化）  
4. compose-next 默认契约  

用户指令可选流程，**不可**放宽 Confirm / 单写者 / 禁止静默降级。

## 主参考（蓝图时期）

arXiv: 2407.01489（Agentless）、2405.15793（SWE-agent）、2404.05427（AutoCodeRover）、2310.06770（SWE-bench）、2407.03037（Trident）、2504.20412（kAgent）、2505.02931（Art of Repair）、2308.00352（MetaGPT）、2309.10691（MINT）、2402.01680、2402.05120、2304.07575，以及仓内 `DESIGN.md` §2 调研表。

## 已删除历史 docs 对照

| 原路径 | 去向 |
|--------|------|
| `docs/blueprint/hunt-escalate-compose.md` | 本文件「v1」节 |
| `docs/blueprint/hunt-escalate-compose-v2.md` | 本文件「v2」节 + `compose-escalate.md` 运行时规范 |
| `docs/compose/spec/phase0`–`phase3-*.md` | `CHANGELOG.md` + `docs/ACCEPTANCE.md` |
| `docs/compose/spec/real-acceptance-install.md` | `CHANGELOG.md` 0.4.1 + `docs/METRICS.md` |
| `docs/compose/spec/skill-config-opt.md` | `CHANGELOG.md` 0.4.2 + 当前 `SKILL.md` frontmatter |
| `docs/compose/spec/hunt-fix-router.md` | `references/compose-escalate.md`（行为真源） |
