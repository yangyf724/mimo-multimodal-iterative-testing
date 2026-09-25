---
feature: mmit-test
status: delivered
updated: 2026-09-25
branch: dev
commits: 209a75c..  # reviewed worktree base; final commit pending user finish action
---

# 全模态迭代测试 Skill 重构（MMIT-Test）

## Report

**What was built** — 新 skill 包 `mmit-test/`（MMIT-Test）：SKILL.md + locales + 24 篇 references + 25 个脚本（画像/矩阵/状态/RC/矩阵执行/缺陷/修复门/脱敏/环境/设备/生产/交付装配/升级/迁移，及 MMIT 探针迁入副本）。核心契约落地为：Profile→Matrix 冻结（`matrix_rev`）、`.mit/` 状态机与 RC 原子性、P0–P3 + Fix Gate 四条件（无回归不得 fixed）、脱敏硬门（matrix_run 拒跑脏报告）、E0–E3 / PRD 缺失声明、TEST_REPORT 十节 + 证据包 + 裁决信号 + Allow/Deny/Escalate。SIG 不再假绿：`regression_green` 由缺陷/门推导，`artifact_ready` 要求 required 覆盖完整；探针禁止 `--help`/空跑假 PASS。

双 demo：`examples/mit-demo-webapi/`（Deny 路径）与 `examples/mit-demo-media/`（Escalate + 升级包）。DoD §17.1–6 演示通过；§17.7 经评审修复后关闭（canvas 真实检查、无空跑 PASS）。旧 MMIT 保留，description 负例指向 MMIT-Test。

**Verification** — 工作区命令与结果：
- `$MIMO_PYTHON -m unittest discover -s tests` → **PASS**（129 tests OK）
- `tests/phase1_fixture_e2e.py` → **PASS**（PHASE1_FIXTURE_E2E_OK）
- `tests/phase2_fixture_e2e.py` → **PASS**（PHASE2 E2E OK）
- `mmit-hunter/scripts/ci_gate.py --root .` → **PASS**（ok:true EXIT=0；PRE-EXISTING Windows GBK 读线程噪音）
- 双 demo 全流水线（profile→matrix freeze→mask→env→RC→matrix_run→prod→report/signals）→ **PASS**
- Fix-cycle：`fix_gate` 无回归 FAIL → 有回归 PASS → 重建 RC `rc_sha` 变化 → **PASS**
- 独立评审 general-2（初轮）→ 3 CRITICAL + 12 MAJOR；修复后 general-3 复审残留 canvas 假 PASS；修复后 general-4 聚焦复审 → **PASS**（3/3 目标测试 OK，canvas `checked_items:1` 合法 PASS）

**Journey log**
1. MIT/MMIT 脚本同名（`init_state`/`fix_gate`）在 `unittest discover` 共享 `sys.modules` 会串包 → 测试侧 `importlib` 以 `mit_*` 唯一名加载。
2. 「禁止假通过」不能只靠退出码：`--help` 探针、空检查恒绿、`layers` 未映射都会假 PASS；须探针自身诚实退出 + harness 拒 help/空跑。
3. 脱敏扫描报告不得回写命中实值（`snippet`）——否则证据包自己泄密。
4. `matrix --bump` 必须从画像重推 marks，否则旧误检（`quest`⊂`request`）会固化进矩阵。
5. Windows 子进程读 UTF-8 须 `encoding="utf-8", errors="replace"`，否则 GBK 解码炸线程（MMIT `ci_gate` 仍有 PRE-EXISTING 噪音）。

## [S1] Problem

`mmit-hunter`（MMIT）只覆盖 code / web-visual / canvas 三通道并以 quiet 收敛为出口，无法回答「这个候选版本能不能正常发布使用」。差距见设计真源 `docs/skill-refactor-mmit-test.md` §1.2（G1–G7）：模态漏测、本地环境不等价、无 RC 语义、缺陷无发布分级、交付物缺测试报告/证据包/裁决信号、无生产侧协议、裁决不可综合。

本 feature 将 MMIT 重构为 **全模态迭代测试** skill（`mmit-test` / MMIT-Test），按项目画像生成全模态测试矩阵，在生产等价环境与脱敏数据下迭代执行发布就绪测试，分级修复并强制回归，每轮重建 RC 全量复测，最终由 agent 综合四项依据裁决 Allow / Deny / Escalate。

## [S2] Design

设计真源：`docs/skill-refactor-mmit-test.md`（MIT-DESIGN-001 v1.0）。本节只记录落地契约；与真源冲突时以真源的目标、裁决原则与禁止项为准。

### 命名与包布局

| 项 | 值 |
|----|-----|
| 英文 ID / 目录 | `mmit-test/`（仓库根，与 `mmit-hunter/` 并列） |
| 中文显示名 | 全模态迭代测试 |
| 状态目录 | 目标项目 `.mit/` |
| Frontmatter | 单行 `description`，格式见真源 §4.2 |

```text
mmit-test/
  SKILL.md
  locales/{zh-CN.json,en-US.json}
  references/*.md          # 24 篇
  scripts/*.py             # 见任务表；含自 MMIT 迁入的探针副本
```

旧包 `mmit-hunter/` 保留为视觉/布局抓 BUG 入口；`SKILL.md` description 增补负例指向 MMIT-Test。提供 `scripts/migrate_state.py` 将 `.bug-hunter/state.json` 迁到 `.mit/state.json`。

### 核心契约（摘要）

1. **矩阵**：`Matrix = (Profile 命中模态 ∩ 发布必测底线) ∪ 用户点名模态`；标注 `required|optional|n/a`；冻结 `matrix_rev` 后才可开跑。
2. **RC 原子性**：B4–B8 绑定同一 `rc_sha`；禁止热修后复用旧 PASS。
3. **缺陷**：P0–P3；无回归不得 `fixed`（需 fix_gate.passed 或审计 `--force-fixed`）；Fix Gate 四条件。
4. **环境**：E0–E3；脱敏硬门失败拒绝开跑/立即升级；matrix_run 拒跑脏 mask。
5. **交付物**：`TEST_REPORT.md`（十节）+ `evidence/`+`EVIDENCE_INDEX.md` + `adjudication_signals.json` + `RELEASE_DECISION.md`。
6. **裁决**：SIG+RPT+EVD+PRD 四项互证；冲突取保守；缺 PRD 不得无条件 Allow；出口仅 Allow/Deny/Escalate。
7. **证据诚实**：探针 `--help`/空跑/无对象检查不得记 PASS；`regression_green`/`artifact_ready` 由数据推导。

### 测试与验收

- 单元测试：`tests/test_mit_core.py`（importlib 隔离），`python -m unittest discover -s tests` 全绿。
- 双 demo：`examples/mit-demo-webapi/`（Deny）、`examples/mit-demo-media/`（Escalate）；真源 §17 DoD 勾选见证据。

## [S3] Out of Scope

- 无障碍合规认证、渗透测试报告、法务/产品签字（真源 §2.2）。
- 通用云真机农场 / 完整 CI/CD 产品 / 应用商店流水线对接。
- 未授权生产写路径压测或破坏性数据操作。
- 本 feature 不删除 `mmit-hunter` 包，不迁移已安装到 `~/.config/mimocode/skills/` 的运行时副本（安装留给后续发布流程）。
- P5 验收演示使用本地 demo 项目，不连接真实生产、不真机部署。
- DoD §17.5 的 **Allow** 与 **canary 失败** 分支未做完整现场演示（规则已在 `adjudication.md` / signals 中编码；演示覆盖 Deny 与 Escalate）。

## Tasks

- [x] T1: SKILL 包骨架 — acceptance: `mmit-test/` 含 SKILL.md（单行 frontmatter）+ locales 显示名正确 + 空 references/scripts 目录约定成立 (covers: S2)
- [x] T2: profile_scan.py + references/profile-schema.md — acceptance: 对 demo 仓库产出合法 `profile.json`，缺字段为 `unknown` 不臆造 (covers: S2)
- [x] T3: matrix_build.py + references/matrix-rules.md + test-layers.md — acceptance: 由 profile 生成含 required/optional/n/a 的 `matrix.json`，写入 `matrix_rev`，可 `--freeze` (covers: S2)
- [x] T4: 状态机 init/state — acceptance: `init_state.py` 创建 `.mit/state.json` 字段齐全；锁协议可读；迁移 `migrate_state.py` 从 `.bug-hunter/state.json` 映射 (covers: S2; depends: T1)
- [x] T5: 模态参考 13 篇 + env/data/defect/fix 等 references — acceptance: 每个 M1–M13 有 modality-*.md 且含 Evidence Floor；env-layers/data-masking/defect-severity/fix-regression 可指导脚本实现 (covers: S2)
- [x] T6: build_rc.py + matrix_run.py — acceptance: 能构建 RC 元数据（rc_n/rc_sha）并对冻结矩阵执行 required 项，输出 runs/RC-n/**；探针失败记 Blind Spot 不假 PASS (covers: S2; depends: T3,T4)
- [x] T7: 缺陷分级与 Fix Gate — acceptance: defect 记录含 P0–P3；fix_gate 四条件可机判；无回归不得 fixed (covers: S2; depends: T6)
- [x] T8: env_up.py + data_mask.py + device_probe.py + prod_probe.py + 对应 references — acceptance: 产出 env_manifest.json；脱敏扫描失败拒绝开跑；prod_access=none 时写显式缺失声明 (covers: S2)
- [x] T9: 交付物装配 assemble_report/assemble_signals/escalate + deliverables/adjudication/escalate references — acceptance: TEST_REPORT 十节、adjudication_signals schema 合法、escalation/ 包完整 (covers: S2; depends: T6,T7)
- [x] T10: 自 MMIT 迁入探针副本并接线 — acceptance: layout/contrast/ux/canvas/vlm/visual_diff 等可在 matrix_run 下被调用；指纹/FP 白名单可用；canvas 支持 `.mit`+layers (covers: S2; depends: T6)
- [x] T11: 单元测试套件 tests/test_mit_*.py — acceptance: 覆盖 profile/matrix/state/RC/fix_gate/mask/signals/escalate 关键路径，discover 全绿 (covers: S2)
- [x] T12: demo-webapi + demo-media 与 DoD 验收记录 — acceptance: 两 demo 产出矩阵/报告/信号/裁决；真源 §17 条目 1–7 可勾选（5 的 Allow/canary 分支见 S3）；演示 Deny 与 Escalate 完整路径 (covers: S2; depends: T1–T11)
- [x] T13: 旧 skill 负例与 CHANGELOG/README 对齐 — acceptance: MMIT description 负例指向 MMIT-Test；README/CHANGELOG 描述新包；旧测试仍绿 (covers: S2; depends: T1)
