# M3 `web` — Web 模态

矩阵编号 **M3**。典型分级 **P0–P1**。层级以 **ML** 为主；跨图文/数字不一致记 **FL**。

## 覆盖范围

- 布局（重叠、溢出、错位）
- 对比度
- 响应式（viewport）
- 无障碍 a11y
- 关键路径 UX
- 视觉基线（visual regression）

复用 MMIT（mmit）Web 视觉/无障碍/布局探针实现。

## Evidence Floor（最低证据）

| 证据 | 说明 |
|------|------|
| route×viewport | 关键路由在目标 viewport 的执行记录 |
| axe/contrast | axe 或等价 a11y 扫描 + 对比度检查报告 |
| visual diff | 视觉基线对比图与差异指标 |

## 典型分级

| 现象 | 分级 |
|------|------|
| 核心路径不可用、关键 a11y 阻断（无法操作） | P0–P1 |
| 主路径错误、明显视觉回归 | P1–P2 |
| 次要视觉瑕疵、边缘 viewport 问题 | P2 |
| 纯审美、无规则可述的主观结论 | P3 / Deferred |

## 探针提示

- 路由清单来自项目真实关键旅程，不只首页。
- viewport 矩阵至少覆盖移动/桌面代表档；缺档记盲区。
- a11y：axe 类规则结果机读留存；对比度单独采样关键文本/按钮。
- 视觉基线与当前 `rc_sha` 绑定；基线漂移须人工确认，不得自动「修基线」消差。
- 主观 VLM 结论须 k 次一致率门槛（见 `adjudication.md` oracle_quality），禁止单独支撑 Allow/Deny 主路径。

## 回归固化

来源缺陷面 `web` → **route×viewport probe、视觉基线**。

## 禁止

- 无 visual diff / axe 报告的 PASS
- 用单一截图覆盖多 viewport
- 主观审美当 P0/P1
