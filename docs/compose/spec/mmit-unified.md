---
feature: mmit-unified
status: delivered
updated: 2026-09-25
branch: dev
commits: 59649ce..WORKTREE  # base..head (uncommitted at finalize; fill when committing)
---

# 统一 MMIT Skill（mmit 流水线）

## Report

**What was built** — 单一 skill 包 `mmit/`：统一流水线（depth=`hunt`|`release`），状态 `.mmit/`（hunts/tests/deliverables），出口一律 Allow/Deny/Escalate。34 脚本去重迁入（共享探针一份、`fix_gate` 双 CLI 超集、`init_state` 扁平并集 + 原 API、`migrate_state` 双源合并），39 篇 references，SKILL.md 单行 description 覆盖原 hunter/test 触发词。旧包 `mmit-hunter/`、`mmit-test/` 已删除。

**State schema 修订** — 初稿要求 `hunt.*`/`release.*` 分段；实现采用**扁平并集**（hunt 探针均读顶层字段）。已在 S2 记录为交付契约，语义分组不变。

**Verification** —
- `$MIMO_PYTHON -m unittest discover -s tests` → **PASS**（131 tests OK，含 dual-source migrate）
- `tests/phase1_fixture_e2e.py` → **PASS**
- `tests/phase2_fixture_e2e.py` → **PASS**
- release smoke：init → profile_scan → matrix_build --freeze → assemble_report → **PASS**
- 评审 critical 修复后复测全绿

**Journey log** —
1. 8 个探针字节级相同却被双包各存一份；合并必须先做路径/状态契约再删旧包。
2. hunt 探针强依赖扁平 `state` 字段；分段 schema 会迫使改十余个脚本，改为扁平并集并在 spec 记录偏差更稳。
3. 多源 migrate 不能 `save` 覆盖：须按源真实出现的字段合并，否则默认值会冲掉对端 release 字段。
4. `fix_gate` 双 CLI（四条件 / 探针实门）可共存，但文档必须写清「无回归绿不得 fixed」只对 `--defect-id` 路径绝对成立。

## [S1] Problem

仓库现有两个并列 skill：`mmit-hunter/`（抓 BUG 至 quiet 收敛）与 `mmit-test/`（发布就绪 RC Loop）。二者本意是边界互补，但落地后造成：

1. **脚本重复**：8 个探针/工具字节级相同各存一份（axe_gate、contrast_probe、fingerprint、fp_feedback、layout_probe、ux_flow、visual_diff、vlm_audit），另有 canvas_probe 分叉、fix_gate/init_state 各写各的。
2. **状态分裂**：目标项目同时可能出现 `.bug-hunter/` 与 `.mit/`，锁、指纹、缺陷、RC 语义不互通；`migrate_state.py` 只做了单向 `.bug-hunter→.mit`。
3. **入口分裂**：触发词互相指来指去（抓 BUG→hunter，发版→test）；「先抓干净再看能不能发」要用户自己串两个 skill。
4. **维护成本**：同一视觉规则阈值、Fix Gate 原则、Blind Spots 诚实性要求写在两套 references/tests 里，改一处易漏另一处。

目标：合成**一个** skill `mmit/`，以**统一质量门流水线**承载两条深度（轻量抓 BUG / 发布就绪），共享探针与状态，删除旧包。

## [S2] Design

### 命名与包

| 项 | 值 |
|----|-----|
| skill ID / 目录 | `mmit/`（仓库根） |
| 中文显示名 | MMIT 全模态质量门 |
| 状态目录 | 目标项目 `.mmit/` |
| Frontmatter | 单行 `description`（禁止多行续行） |

旧目录 `mmit-hunter/`、`mmit-test/` **删除**；README/测试/文档指向新路径。全局安装替换不在本 feature 自动执行（见 S3）。

### 流水线深度（depth）

统一主循环，用 `depth` 门控阶段；**出口一律三态 Allow / Deny / Escalate**。

| depth | 触发例 | 跑哪些阶段 | 三态含义 |
|-------|--------|------------|----------|
| `hunt` | 抓 BUG、design QA、修到没有、视觉/布局问题 | Bootstrap → Scope → Discover/Probe → Capture → Hunt → Confirm →（可选）Fix+Regression → Converge | Allow=约定范围内 quiet 收敛；Deny=仍有 Confirmed 缺陷；Escalate=盲区/预算尽/硬阻塞 |
| `release` | 发布就绪、go/no-go、RC 验收、能不能发版 | 上表全部 **+** Profile→Matrix 冻结 → Env+脱敏 → Build RC → 全量矩阵 → Triage → Fix → Rebuild → Assemble → Prod Test → Adjudicate | 发布裁决语义（artifact_ready × exposure_ready；缺 PRD 不得无条件 Allow） |

- Scope 问答推断 depth；冲突或不明时问用户。
- `hunt` **不**强制 matrix 冻结、脱敏、建 RC、生产测。
- `release` 内 Hunt/Confirm/Fix 是缺陷发现与修复子阶段，不得跳过 Confirm 门槛。

### 状态树（`.mmit/`）

```text
.mmit/
  .lock
  state.json          # 见下
  fingerprints.json
  fp_patterns.json
  bugs/               # confirmed|rejected|deferred
  flows/              # ux-flow 符号化
  hunts/              # hunt 轮次 runs/captures/findings
  tests/              # release：profile.json matrix.json rc/ runs/
  deliverables/       # release：TEST_REPORT evidence signals RELEASE_DECISION
  escalation/
```

`state.json` 采用 **扁平并集**（version=2，skill=mmit）。实现时 hunt 探针（hunt_round/converge/export/capture）均读取扁平字段，故未再嵌套 `hunt.*`/`release.*` 段；语义分组如下（与初稿分段契约等价，只是不建中间 key）：

- 核心：`version, skill, depth, mode, created_at, updated_at, decision, blinds[], blind_spots[], quiet_streak, run_count, round`
- **hunt 面**（顶层）：`modalities_enabled, surfaces, visual_oracle, ci, export, fp, fix_router, last_strategy_set, last_round, converged, stats`
- **release 面**（顶层）：`rc_n, rc_sha, matrix_rev, open_defects, signals, prod_access, prod_test_state`
- `budget.*`：合并护栏（max_runs, required_quiet_streak, max_rc_rounds, max_wall_clock_hours, fix 护栏）

单写者 main agent；写 `state.json` 前 `O_EXCL` 持 `.mmit/.lock`；禁双会话同项目。

### 包布局

```text
mmit/
  SKILL.md
  locales/{zh-CN.json,en-US.json}
  references/*.md
  scripts/*.py          # 扁平、共享脚本仅一份
  scripts/mmit_lib.py   # 锁/路径/读写/常量（吸收 mit_lib.py + hunter 内联锁）
```

脚本归并规则：

1. **8 个同名相同文件** → 保留一份，改依赖 `mmit_lib` 与 `.mmit/` 路径。
2. **init_state.py** → 合并 DEFAULT_STATE（hunt+release 分段）；`--depth hunt|release` 写对应段；resume 摘要保留。
3. **fix_gate.py** → **超集**：保留 hunter 探针实门（layout/contrast/visual_diff 可跑则跑）与 test 四条件 CLI（`--target-cleared --zero-new-high --non-target-stable --regression-green`）；四条件为必评，探针为增强证据；无回归不得 `fixed`。
4. **canvas_probe.py** → 以更完整实现为基，保留双方特有检查项（去重后合并）。
5. **release 专用**（profile_scan, matrix_build/run, env_up, data_mask, build_rc, defect_register, assemble_*, prod_probe, escalate, device_probe, api_contract_check）→ 迁入并改状态根 `.mmit/tests` 与 `mit_lib`→`mmit_lib`。
6. **hunt 专用**（capture_web, hunt_round, discover_routes, converge_check, export_report, validate_report, baseline_lock, ci_gate）→ 迁入并改 `.mmit/`。
7. **migrate_state.py** → 支持 `.bug-hunter/state.json` 与 `.mit/state.json` → `.mmit/state.json`（字段映射到分段结构）；旧目录只读不删。

### SKILL.md（单文件）

- frontmatter：`name: mmit` + **单行** description，覆盖抓 BUG + 发布就绪触发词与负例（一次性 lint、纯功能开发、无运行应用的纯静态 review）。
- 正文保留：Important / 触发与 depth / Scope 表 / 主循环（阶段标注 `H`/`R`）/ 三态出口 / Confirm 与 Fix Gate 指针 / 交付物 / 状态与并发 / 禁止 / Examples。
- 规则阈值、脚本参数、模态目录一律在 `references/`，禁止塞进 SKILL.md。

Scope 默认表（合并）：

| 项 | 默认 |
|----|------|
| depth | 由触发词推断，否则问 |
| mode | `hunt-and-fix` / `test-and-fix`（或 only） |
| modalities | hunt：code+web-visual（+canvas）；release：profile 推导 |
| routes / viewports | `/` `/about`；`375x812` `1440x900` |
| base_url / target | 用户 dev server / 当前工作区 |
| rc_ref | HEAD（release） |
| prod_access | `none` |
| K / max_runs | 2 / 20 |
| max_rc_rounds / wall_clock | 5 / 4h（release） |

### references 归并

- **共享**：confirm-protocol, fix-gate, fix-regression, visual-rules, strategies, fp-feedback, capture-protocol, canvas-protocol, ux-flow, vlm-audit。
- **H**：route-discovery, report-template, export-schema, ci-gate, compose-escalate, subagent-capture。
- **R**：profile-schema, matrix-rules, test-layers, modality-*.md, env-layers, data-masking, defect-severity, deliverables, adjudication, prod-test, escalate。

同主题文档去重；冲突时以「证据优先 / 无假 PASS / 无回归不得 fixed / 纯主观→Deferred」为上位规则。

### 测试契约

- `tests/` 全部改为 `mmit/scripts` 与 `.mmit/` 路径。
- 单副本脚本后，取消 `test_mit_core` 的 importlib 跨包隔离（除非仍有同名残留）。
- 验收：`$MIMO_PYTHON -m unittest discover -s tests` 全绿；phase1/2 fixture e2e 通过；fix_gate 超集行为有单测（四条件 + 可选探针拒绝假 PASS）。

### 文档

- `README.md`：单 skill 定位、快速开始、安装路径 `~/.config/mimocode/skills/mmit/`。
- `DESIGN.md`：增补「统一流水线」章节（depth 门控、`.mmit/`、三态出口）；不重写全文文献。
- `CHANGELOG.md`：记录 breaking（删双包、状态目录合并）。
- 既有 `docs/skill-refactor-mmit-test.md` / `docs/compose/spec/mmit-test.md` 保留为历史，文首注明 superseded-by。

## [S3] Out of Scope

- 自动卸载/替换本机 `~/.config/mimocode/skills/` 下已安装的 `mmit-hunter`、`mmit-test`（Finish 时询问；全局删除需用户确认）。
- 重写 DESIGN.md 研究综述、新增 M1–M13 以外模态、接云真机/商店流水线。
- 未授权生产写路径、渗透、法务签字。
- 兼容保留旧 skill ID 触发（旧包删除后由 `mmit` 单入口承接；description 覆盖原触发词）。
- 改变 Allow/Deny/Escalate 三态语义或引入第四出口。

## Tasks

- [x] T1: `mmit/` 骨架 + SKILL.md（单行 description、depth 主循环、Scope/禁止/Examples）+ locales — acceptance: `mmit/` 可被 skill 扫描；frontmatter 合法；display 名正确 (covers: S2)
- [x] T2: `mmit_lib.py` + 合并 `init_state.py`（扁平并集 state、`.mmit/` 树、锁）— acceptance: `--depth hunt|release` 均可初始化；写 state 前持锁；树含 bugs/hunts 与 tests/deliverables (covers: S2; depends: T1)
- [x] T3: 共享探针去重迁入（8 同名 + canvas_probe 合并）— acceptance: 每文件仅一份；`python -c "import"` 可加载；阈值与 Visual Oracle 一致 (covers: S2; depends: T2)
- [x] T4: `fix_gate.py` 超集 — acceptance: 四条件 CLI 与探针增强共存；无 `--regression-green` 不得 passed；失败原因可读 (covers: S2; depends: T3)
- [x] T5: hunt 脚本迁入（capture/hunt_round/discover/converge/export/ci 等）— acceptance: 对 fixture 项目可完成一轮 hunt 并写 `.mmit/hunts` (covers: S2; depends: T3)
- [x] T6: release 脚本迁入（profile/matrix/env/mask/build_rc/assemble/prod/escalate）— acceptance: 对 demo 可 profile→matrix freeze→RC→matrix_run 且状态在 `.mmit/tests` (covers: S2; depends: T2)
- [x] T7: `migrate_state.py` 双向源 — acceptance: `.bug-hunter/state.json` 与 `.mit/state.json` 均可迁入 `.mmit/state.json` 且关键字段不丢 (covers: S2; depends: T2)
- [x] T8: references 归并去重 — acceptance: 上表三类文件齐；无相互矛盾的确认/假通过规则 (covers: S2)
- [x] T9: tests 全面 retarget + 补 fix_gate/migrate 用例 — acceptance: `unittest discover -s tests` 全绿；phase1/2 e2e OK (covers: S2; depends: T2–T7)
- [x] T10: 删除 `mmit-hunter/` `mmit-test/`，改 README/DESIGN/CHANGELOG — acceptance: 仓库仅 `mmit/` skill 包；文档无死链指向旧目录 (covers: S1; depends: T9)
- [x] T11: 端到端冒烟（hunt 深度三态 + release 深度 demo 裁决）— acceptance: 两条深度各至少一次完整出口可复现 (covers: S2; depends: T5, T6, T9)
