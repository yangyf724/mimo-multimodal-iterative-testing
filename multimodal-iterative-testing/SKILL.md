---
name: multimodal-iterative-testing
description: 全模态迭代测试：按项目画像生成覆盖代码/API/Web/移动端/桌面端/CLI/数据库/基础设施/音视频/Canvas/3D/XR/插件等实际模态的测试矩阵，在生产等价环境与真实/仿真设备、脱敏数据下迭代执行发布就绪测试，按缺陷分级修复并补充回归测试，每轮重建候选版本并全量复测；交付测试报告与证据包，是否允许发布由 agent 综合裁决信号、测试报告、证据包与真实生产环境测试结果判断，否则在轮次/时间预算或阻塞时升级人工。Use when 用户要 全模态迭代测试 / 发布就绪 / go-no-go / 发布裁决 / RC 验收 / 能不能发版。Do NOT use for 一次性 lint、纯功能开发、或仅需视觉抓 bug（→ iterative-bug-hunter）。
---

# 全模态迭代测试（MIT-Test）

以指定项目为对象，按**项目画像**生成**全模态测试矩阵**，在**生产等价环境**与真实/仿真设备、**脱敏数据**下迭代执行发布就绪测试；按缺陷分级修复并补充回归测试；每轮重建候选版本并全量复测；最终由 agent 综合四项依据裁决是否允许发布，或在预算/阻塞时升级人工。

对话简称：MIT-Test。状态目录：目标项目 `.mit/`。

## Important

- 只在目标项目 `.mit/` 读写；**单写者**为 main agent。写 `state.json` 前持 `.mit/.lock`。
- **证据优先，禁止假通过**：无机读证据不得判 PASS；`unavailable` ≠ 通过。
- **RC 原子性**：矩阵执行、缺陷、生产结果必须绑定同一 `rc_sha`；禁止热修后复用旧 PASS。
- **无回归测试不得标记 fixed。**
- **脱敏硬门**：扫描失败拒绝开跑或立即 Escalate；禁止未脱敏数据入证据包。
- 发布出口只有 **Allow / Deny / Escalate**。quiet 只是过程信号，不是发布出口。
- 与 MIBG 边界：仅视觉/布局抓 BUG → `iterative-bug-hunter`；发布就绪 / go-no-go → 本 skill。

## 触发

用户点名：全模态迭代测试、发布就绪、发布裁决、go/no-go、RC 验收、「能不能正常发布使用」；或给出候选版本（tag、构建产物、制品哈希）并要求发布级测试结论。

**不要**在一次性 lint、纯功能开发、或仅视觉抓 bug 时启用本 skill。

## Scope（开跑前必须确认）

| 项 | 默认 | 说明 |
|----|------|------|
| target 项目路径 | 当前工作区 | 被测项目 |
| rc_ref | 用户指定或 HEAD | 候选基线 |
| mode | `test-and-fix` | 或 `test-only` |
| modalities | profile 推导 | 用户点名强制 |
| prod_access | 用户确认 | `none\|readonly\|shadow\|canary` |
| devices | profile.devices | 真机/仿真 |
| data 种子 | 脱敏种子 | 硬门 |
| max_rc_rounds | 5 | 预算护栏 |
| max_wall_clock | 4h | 预算护栏 |

## 主循环（RC Loop）

1. **Bootstrap** — `scripts/init_state.py` 初始化/恢复 `.mit/`；加载 profile/matrix。
2. **Profile → Matrix** — `scripts/profile_scan.py` → `scripts/matrix_build.py --freeze`。未冻结不得开跑。
3. **Environment Up** — `scripts/env_up.py` + `scripts/data_mask.py` 脱敏扫描；失败 Escalate。
4. **Build RC** — `scripts/build_rc.py` 干净构建，锁 `rc_n`/`rc_sha`。
5. **Matrix Full Test** — `scripts/matrix_run.py` 执行 required + 已启用 optional；探针失败记 Blind Spot。
6. **Triage** — 去重、确认、P0–P3 分级（[`references/defect-severity.md`](references/defect-severity.md)）。
7. **Fix + Regression** — 仅 Confirmed；`scripts/fix_gate.py` 四条件；无回归不得 fixed（[`references/fix-regression.md`](references/fix-regression.md)）。
8. **Rebuild** — 仍有阻塞且预算内 → 重建 RCn+1，全量复测。
9. **Assemble** — `scripts/assemble_report.py` / `scripts/assemble_signals.py` 生成测试报告、证据包、裁决信号。
10. **Prod Test** — 授权范围内 `scripts/prod_probe.py`（E2）；无授权则显式缺失声明。
11. **Adjudicate** — agent 综合 SIG+RPT+EVD+PRD → `RELEASE_DECISION.md`。
12. **Escalate** — 预算尽/硬阻塞 → `scripts/escalate.py` 升级包。

细规格见 [`references/`](references/)：矩阵规则、模态目录、环境层级、脱敏、缺陷、交付物、裁决、升级。

## 交付物

| 交付物 | 路径 |
|--------|------|
| 测试报告 | `.mit/deliverables/TEST_REPORT.md` |
| 证据包 | `.mit/deliverables/evidence/` + `EVIDENCE_INDEX.md` |
| 裁决信号 | `.mit/deliverables/adjudication_signals.json` |
| 发布裁决 | `.mit/deliverables/RELEASE_DECISION.md` |
| 升级包 | `.mit/escalation/`（触发时） |

## 裁决原则

是否允许发布的依据，必须由 agent **综合**以下四项判断，禁止只看自动门禁颜色：

1. **SIG** — `adjudication_signals.json` 结构化质量信号
2. **RPT** — `TEST_REPORT.md` 完整叙述与指标
3. **EVD** — 可复核的机读/多媒体证据
4. **PRD** — 真实生产环境测试结果（或显式缺失）

规则：四项互证；冲突取保守；缺项不得无条件 Allow（尤其 PRD）；硬失败（脱敏失败、生产关键路径失败、证据不可信）直决 Deny/Escalate。

分层发布：`artifact_ready` 与 `exposure_ready` 分离；`exposure_ready=false` 时只能条件 Allow（按 `exposure_constraint`）或 Deny 全量。

## 停止与升级

预算：`max_rc_rounds=5`、`max_wall_clock=4h`、`max_fix_failures_per_defect=2`、`max_p0_fix_rounds=3`、`max_compose_escalations=1`。

必须升级人工：脱敏失败/密钥泄露、需签字决策、环境/设备/生产权限缺失、oracle 不可判定、预算尽仍有开放 P0/P1、四项严重冲突、用户中止。

## 禁止

- 无证据假 PASS / 静默跳过探针
- 热修后不重建 RC 即宣告 Allow
- 无回归标记 fixed
- 未脱敏生产数据入包
- 未授权生产写路径压测或破坏性操作
- 将 quiet 或单一门禁颜色当作发布出口
