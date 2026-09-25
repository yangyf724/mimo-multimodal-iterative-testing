---
name: mmit-hunter
description: 全模态迭代抓 BUG 直到收敛：代码 + 视觉布局/无障碍/响应式 + 画布通道，指纹去重、跨模态确认、可选修复+回归门。Use when the user says 抓BUG, 找bug, 修到没有, bug hunt, hunt until clean, 网页视觉问题, 布局炸了, 无障碍, 画布设计检查, UI不对, 对比度, 响应式问题, design QA, or visual bug. Do NOT use for one-shot lint 汇总, pure feature dev, or when no runnable app/assets and user only wants static code review. 发布就绪 / go-no-go / RC 验收 / 能不能发版 → mmit-test。
---

# MMIT Hunter

对当前项目持续抓 BUG，直到「在约定范围内无新增确认 BUG」。代码 + 视觉（Web）+ 画布通道；Phase 2 含 ux-flow 符号化、canvas-safe/asset、vlm-audit；Phase 3 含路由发现、FP 白名单、machine-readable 导出、baseline/axe CI 门禁。

运行环境：Python 3.10+（脚本）；Web 采集需 Playwright 或 playwright-mcp；axe-core 可选（L3）；画布 scene JSON 可选（L4）。

## Important

- 只在目标项目 cwd 的 `.bug-hunter/` 读写；**单写者** main agent；写 `state.json` 前必须持锁（见「状态与并发」）。
- 探测失败 / axe unavailable **不得**静默跳过或假装通过；必须记 Blind Spots。
- 纯审美 / 无规则 VLM 主观 → **Deferred**，不得 Confirmed（见「Confirm 门槛」）。
- 禁止自动改写用户项目 `AGENTS.md`（只生成 snippet）；完整禁止项见文末「禁止」。

## 触发

用户明确要求：抓 BUG / 找 bug / hunt until clean / 视觉问题 / design QA / 修到没有，且目标是当前项目或指定本地 Web 应用。

**不要**在仅需一次 lint 汇总、纯写功能、或用户只想要静态 code review 且无任何可运行应用时启用本 skill。

## Scope（开始前必须确认）

用 `question` 工具或直接从仓库/用户已给信息收集；缺省值写入 `state.json`：

| 项 | 默认 | 说明 |
|----|------|------|
| mode | `hunt-and-fix` | 或 `hunt-only` |
| modalities | `code, web-visual` | 有画布资产再加 `canvas` |
| routes | `/`, `/about` 或探测 | 以 `state.surfaces.web.routes` 为准 |
| viewports | `375x812`, `1440x900` | 指纹区分 viewport |
| base_url | 用户 dev server | 无则先尝试探测，失败进 L1 |
| canvas items | 可选 | `state.surfaces.canvas` 或 `--canvas-items` |
| flows | 可选 | `.bug-hunter/flows/*.json` 符号化，见 [`references/ux-flow.md`](references/ux-flow.md) |
| route discovery | 开 | `scripts/discover_routes.py`，见 [`references/route-discovery.md`](references/route-discovery.md) |
| fp patterns | 可选 | `.bug-hunter/fp_patterns.json`，见 [`references/fp-feedback.md`](references/fp-feedback.md) |
| K | 2 | `required_quiet_streak` |
| max_runs | 20 | 预算护栏 |

## 降级阶梯（摘要）

| 级别 | 条件 | 允许 |
|------|------|------|
| L0 | 无法识别项目/无工具 | 立即停止并报告 |
| L1 | 有源码，无浏览器/dev server | 仅 code 通道 |
| L2 | 可开页，暂无 axe | L1 + capture / layout-geom / contrast-type / responsive-matrix |
| L3 | L2 + axe-core | 默认 Web 全开 |
| L4 | L3 + 画布场景/导出 + 规范 | 全模态 |

细节与完整策略表：[`references/strategies.md`](references/strategies.md)。探测失败必须记入 Blind Spots，禁止静默跳过。

## 主循环

1. **Bootstrap** — `scripts/init_state.py`（已有 `state.json` 则 resume：`--resume-summary`）。
2. **Discover（可选）** — `scripts/discover_routes.py` 合并 seed/package/sitemap/HTML 链接。
3. **Probe** — 探测 dev server / 路由可达性，写 `degrade_level`；有 canvas items 且 web≥L3 可到 L4。
4. **Plan** — 选策略集；禁止连续两轮完全相同；quiet_streak≥1 时加压。
5. **Capture** — L≥2 时 `scripts/capture_web.py`（可 `--shard i/n` + `merge`，见 [`references/subagent-capture.md`](references/subagent-capture.md)；或 playwright-mcp 按 [`references/capture-protocol.md`](references/capture-protocol.md)）。
6. **Hunt** — `scripts/hunt_round.py`：probe 矩阵 → layout+contrast+ux → 可选 canvas/flows → FP 白名单 suppress → 指纹注册 → summary。UX flows 见 [`references/ux-flow.md`](references/ux-flow.md)；画布探针见 [`references/canvas-protocol.md`](references/canvas-protocol.md)。或逐步手动跑 `layout_probe.py` / `contrast_probe.py` / `ux_flow.py` / `canvas_probe.py`。
7. **VLM（可选）** — 双视角审图后 `vlm_audit.py merge`，仅 Candidate；见 [`references/vlm-audit.md`](references/vlm-audit.md)。
8. **Confirm** — 按 [`references/confirm-protocol.md`](references/confirm-protocol.md)，L3/L4 才 Confirmed；rejected 可 `fp_feedback.py absorb` 沉淀。
9. **Fix（可选）** — 仅 Confirmed；先按 [`references/compose-escalate.md`](references/compose-escalate.md) 做**三档路由**（`local` / `lite` / `compose`），再以 [`references/fix-gate.md`](references/fix-gate.md) 的 `scripts/fix_gate.py` 判门。默认 Local；Lite 重定位仍走 fix_gate；仅 oracle gap / 契约重定义 / 用户明确要 PR·Spec 时门控升 compose-next（slim），结束后必须回 hunt Converge。预算：`budget.max_local_attempts` / `lite_max_attempts` / `max_compose_escalations`；禁止同构重试。
10. **Converge** — `scripts/converge_check.py` 实现 quiet 四条件。
11. **Report** — 按 [`references/report-template.md`](references/report-template.md) 写 `.bug-hunter/REPORT.md`；机器视图 `scripts/export_report.py`，字段见 [`references/export-schema.md`](references/export-schema.md)。
12. **CI（可选）** — `scripts/ci_gate.py` / baseline lock / axe gate，见 [`references/ci-gate.md`](references/ci-gate.md)。

### quiet 四条件（K 默认 2）

本轮 quiet 当且仅当：

1. 执行了 ≥1 条「当前 degrade 允许」的策略；
2. 策略集覆盖 `modalities_enabled` 中每个**仍可用**的 modality；
3. 新 Confirmed == 0；
4. 无新回归（功能失败 / 视觉 diff 超阈或 intentional 已批 / 新 axe 违规）。

违反任一条则 `quiet_streak` 清零。`quiet_streak ≥ K` 且预算未耗尽 → 收敛。

## Confirm 门槛

- **L3**：截图或元素几何 + 可定位 selector/bbox + 复现（route×viewport）+ 机器规则命中（axe id / 溢出像素 / 对比度数值）→ 可 Confirmed。
- **L4**：L3 + 用户规范条文 → 优先 Confirmed。
- 纯审美 / 无规则 VLM 主观 → **Deferred**（`allow_subjective=false` 时不得 Confirmed）。

分类枚举与指纹字段：见 DESIGN.md §1.4 / §3.2；规则阈值：[`references/visual-rules.md`](references/visual-rules.md)。

## Examples

**应触发（正例）**

1. User: 「帮我抓一下这个前端项目的 BUG，布局好像有点炸」  
   → 确认 Scope（mode/modalities/routes/viewports）→ Bootstrap → Probe → 若可达则 Capture + Hunt → Confirm → 可选 Fix → 至 quiet 收敛 → REPORT 写明已扫面与 Blind Spots。
2. User: 「hunt until clean，看看无障碍和对比度」  
   → modalities 含 web-visual → 优先 axe/contrast 策略 → L3 证据门槛 → 连续 K 轮 quiet 后停。
3. User: 「design QA，海报导出尺寸好像不对，还有些按钮被裁切」  
   → 有 canvas items / 页面 UI → L2–L4 → canvas + layout 交叉确认 → 机器数值为准。
4. User: 「修到没有，复杂的 UI 问题该开 compose 吗？」  
   → Confirm 后按 [`compose-escalate.md`](references/compose-escalate.md) 三档路由：默认 local；lite 重定位；仅 oracle gap / 契约 / user_pr 门控升 compose，结束后回 hunt Converge。

**不应触发（负例）**

- User: 「帮我看下这段 Python 有没有语法错误」（一次静态检查，无迭代 hunt 需求）→ 不启用本 skill；直接做 code review / lint。
- User: 「给这个 API 加一个新接口」（纯功能开发）→ 不启用。

## 状态与并发（必须遵守）

- 只在目标项目 cwd 的 `.bug-hunter/` 读写。
- **单写者**：只有 main agent 写 `state.json` / `fingerprints.json` / `bugs/**`。
- 写 `state.json` 前必须持有 `.bug-hunter/.lock`（`O_EXCL`）；失败重试 3 次后中止本轮。
- **subagent 白名单**：仅 `runs/*/captures/shard-*` 与 `runs/*/findings/raw`；汇总用 `capture_web.py merge`。
- 禁止双会话对同一项目同时跑本 skill。

## 用户合同

> 我会用代码分析 + 浏览器截图/DOM/无障碍树（以及画布场景）反复扫你的项目：能机器判定的用规则和数字说话，拿不准的先当候选；能修的修完会做功能与视觉回归；连续两轮（在当前能力级别下）扫不出新的确认问题我就停，并明确告诉你扫过哪些页面和分辨率、降到了哪一档能力、还有哪些盲区。

## 停止条件

- `converged == true`（quiet 四条件连续 K 轮）；
- 或达到 `max_runs` / 墙钟 / 连续 fix 失败护栏；
- 或 degrade=L0。

停止时 REPORT 必须写清：已扫 route×viewport、degrade 级别、Blind Spots、确认/拒绝/暂缓计数。

## Troubleshooting

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| Probe 失败 / 无 base_url | 未起 dev server 或端口不对 | 先启动应用再 Probe；仍失败则 degrade=L1 并记 Blind Spots |
| Capture 无 Playwright | 本机未安装或不可用 | 用 playwright-mcp 按 [`references/capture-protocol.md`](references/capture-protocol.md)；或 fixture 降级并在 MANIFEST 标明 backend |
| axe 结果 `unavailable` | axe-core 未接入 | 保持 L2 策略；**禁止**把 unavailable 当通过；REPORT 记 Blind Spots |
| 写 state 抢锁失败 | 另一会话/进程持锁 | 重试 ≤3 次后中止本轮；禁止双会话同时 hunt 同一项目 |
| quiet 已 ≥K 但仍感觉有问题 | 策略未覆盖某 modality / 只扫了单 route | 检查 quiet 四条件是否真满足；补 route×viewport 或 modalities 后再跑 |
| 修复后再现同一 BUG | Fix 未过门或回归失败 | 仅修 Confirmed；`fix_gate.py` 拒绝则不写代码；失败计入护栏；按 [`compose-escalate.md`](references/compose-escalate.md) 换策略/转 lite/升 compose 或 Deferred，禁止同构重试 |
| 不知道该小修还是开 compose | 缺三档判据 | 读 [`compose-escalate.md`](references/compose-escalate.md)：oracle 可判定且编辑点小 → local；需重定位 → lite；oracle gap / 契约重定义 / user_pr → 门控 compose |

## 禁止

- 把 DESIGN.md 整篇塞进本文件；
- 无锁覆盖 `state.json`；
- 未授权页面截图当作 bug；
- 纯主观审美直接 Confirmed；
- 静默降级不记 Blind Spots；
- 把 axe `unavailable` 当成通过；
- 自动改写用户项目 `AGENTS.md`（只生成 snippet）。
