---
feature: workspace-cleanup
status: delivered
updated: 2026-09-18
branch: workspace-cleanup
commits: 4f1b5b7..1db98ce37468995c4b26f69466cb1e1ff262ec52
---

# Workspace Cleanup

## Report

**What was built** �?深度清理 MMIT 源码仓工作区：删除运行时垃圾（`.playwright-mcp/`、`.mimocode/node_modules/`、`.mimocode/skills/` 重复副本、examples �?`.bug-hunter` 运行数据）；删除已交付历�?compose specs（phase0�?、real-acceptance-install、skill-config-opt、hunt-fix-router）与 `docs/blueprint/*` 正文；新�?`docs/BLUEPRINTS.md` 压缩研究索引；更�?`compose-escalate.md` 引用、`README.md` 仓库定位、`CHANGELOG.md` Unreleased、`.gitignore`（`.mimocode/`）；纳入 `SKILL.md` frontmatter 单行 description + 正文「运行环境」。交付后 docs 树仅保留：`ACCEPTANCE.md`、`METRICS.md`、`BLUEPRINTS.md`、`compose/spec/workspace-cleanup.md`�?
工作区选择覆盖：引擎拦�?linked `git worktree add`，经用户同意后在 `.worktrees/workspace-cleanup` 使用**独立本地 clone**（分�?`workspace-cleanup`，基�?`4f1b5b7`）。主仓磁盘垃圾已同步清理�?*�?*自动 merge �?main�?
**Verification** �?工作�?clone 内：
- `python -m unittest discover -s tests` �?**PASS**�?09 tests OK�?- `tests/phase2_fixture_e2e.py` �?**PASS**（PHASE2 E2E OK�?- `tests/phase1_fixture_e2e.py` �?**PASS**（PHASE1_FIXTURE_E2E_OK�?- `mmit-hunter/**` 对已�?docs 路径扫描 �?**PASS**�? 命中�?- 独立 review（general-1）→ **PASS**：Spec compliance �?AC met；Correctness �?critical；Consistency 对齐

**Journey log**
1. 引擎硬拦 `git worktree add`（共�?git 注册表保护）�?改用 `--no-hardlinks` 独立 clone；BaiduSyncdisk �?hardlink clone 失败属预期�?2. 运行时路由行为真源在 `references/compose-escalate.md`，blueprint/spec 删除前先�?skill 树路�?grep，确认无 live 依赖�?3. CHANGELOG 历史条目仍点名已删路径是**有意归档**，不是死链失败；AC9 只约�?skill 运行时引用�?4. `docs/BLUEPRINTS.md` 是源码仓研究索引�?*不是** skill 安装相对路径；安装后应以 compose-escalate 正文为准�?5. 深度 docs 清理（−2137 行）不碰 DESIGN/examples/tests/scripts，回归套件一次全绿即可关验证门�?
## [S1] Problem

源码仓工作区被运行时垃圾、技能重复副本与大量已交付历史文档淹没：

- 未跟踪运行时：`.playwright-mcp/`、`.mimocode/node_modules/`、examples �?`.bug-hunter/` 运行数据
- 项目�?skill 副本 `.mimocode/skills/mmit-hunter/`�?7 文件）与源码 `mmit-hunter/` 完全重复
- `docs/compose/spec/` �?Phase0�? / real-acceptance / skill-config-opt / hunt-fix-router 等已交付历史 feature 文档
- `docs/blueprint/` 两份大体量研究蓝图（v1/v2）仍�?`references/compose-escalate.md` 硬引�?- `README.md`「仓库定位」仍把上述历�?docs 写成一等公�?- `mmit-hunter/SKILL.md` frontmatter 有一处未提交的合规整理（description 单行 + compatibility 挪正文）

目标：工作区干净、文档职责清晰、源码与引用不断链�?
## [S2] Design

### 目标结构（交付后�?
```
.
├── DESIGN.md                 # 设计真源（保留）
├── README.md                 # 仓库定位与快速开始（更新�?├── CHANGELOG.md              # 发布记录（更新）
├── LICENSE
├── .gitignore                # 补齐 .mimocode/ �?├── mmit-hunter/     # skill 源码（唯一真源；SKILL.md 纳入 frontmatter 整理�?├── examples/                 # 验收 demo（保留；清掉本地 .bug-hunter 运行数据�?├── tests/                    # 单元测试（保留）
└── docs/
    ├── ACCEPTANCE.md         # DoD（保留）
    ├── METRICS.md            # 度量（保留）
    ├── BLUEPRINTS.md         # 研究蓝图压缩索引（新建，替代 docs/blueprint/*�?    └── compose/spec/
        └── workspace-cleanup.md  # 仅保留本�?feature 文档
```

### 删除 / 替换契约

| 路径 | 动作 | 理由 |
|------|------|------|
| `.playwright-mcp/` | 删除（磁盘，本就 gitignore�?| 采集运行时产�?|
| `.mimocode/node_modules/` | 删除 | 本地依赖，非源码 |
| `.mimocode/skills/mmit-hunter/` | 删除 | 与源码重复；安装路径写在 README 即可 |
| `examples/**/.bug-hunter/` | 删除运行数据 | gitignore �?hunt 状态，不进�?|
| `docs/compose/spec/phase0-*.md` �?`phase3-*.md` | 删除 | 已交付历史；结论已由 CHANGELOG + ACCEPTANCE + SKILL/references 承载 |
| `docs/compose/spec/real-acceptance-install.md` | 删除 | 真机验收结论已在 CHANGELOG 0.4.1 �?METRICS |
| `docs/compose/spec/skill-config-opt.md` | 删除 | frontmatter 修复结论并入本次 SKILL.md 变更�?CHANGELOG |
| `docs/compose/spec/hunt-fix-router.md` | 删除 | 路由行为真源�?`references/compose-escalate.md` + SKILL.md |
| `docs/blueprint/hunt-escalate-compose.md` | 删除，内容压�?`docs/BLUEPRINTS.md` | 研究增量，不作为运行时依�?|
| `docs/blueprint/hunt-escalate-compose-v2.md` | 删除，内容压�?`docs/BLUEPRINTS.md` | 同上 |
| `mmit-hunter/SKILL.md` | 保留未提�?frontmatter 整理 | 用户确认纳入 |

### 引用更新契约

1. `mmit-hunter/references/compose-escalate.md`  
   - 原：硬链 `docs/blueprint/hunt-escalate-compose-v2.md` �?`docs/compose/spec/hunt-fix-router.md`  
   - 改：准据链指�?`docs/BLUEPRINTS.md`（研究结论索引）与行为规范自身；不再依赖已删 spec/blueprint 正文�?
2. `README.md` 仓库定位  
   - 保留：DESIGN / skill 源码 / examples / tests / ACCEPTANCE / METRICS / BLUEPRINTS / �?feature spec  
   - 移除：对已删 phase specs �?blueprint 正文文件的列表项�?
3. `CHANGELOG.md`  
   - Unreleased 增加 Changed：工作区深度清理、docs 收敛、SKILL frontmatter、compose-escalate 引用更新�?
4. `.gitignore`  
   - 增加 `.mimocode/`（本�?MiMoCode 安装/依赖，不进源码仓）�?
### BLUEPRINTS.md 内容边界

- 每份蓝图保留：结论摘要、准据优先级、与 skill 的关系、主参考文献指针�? 
- 不保留：未实施的长流程草稿、决策日志全文、与 DESIGN/fix-gate 重复的算法细节�? 
- 明确标注：blueprint �?compose Spec；已删除�?spec �?CHANGELOG/代码为准�?
### 不改�?
- `DESIGN.md` 设计真源算法�?taxonomy  
- `examples/` 业务 demo 源码�?`flows/`/`canvas/` fixtures  
- `tests/` �?skill `scripts/`/`references/`（除 compose-escalate 引用）行�? 
- `docs/ACCEPTANCE.md` / `docs/METRICS.md` 已有勾选与观测记录

### 工作区选择（覆盖说明）

引擎拦截 `git worktree add`（共�?git 注册表保护）。经用户同意隔离后，采用 **独立本地 clone** �?`.worktrees/workspace-cleanup`，分�?`workspace-cleanup`，基�?`4f1b5b7`。非 linked worktree，合并回 main 需由用�?编排方执行�?
## [S3] Out of Scope

- 不重�?skill 算法、探针或 Fix Router 行为  
- 不改 DESIGN.md  
- 不把 blueprint 内容重新实现为新 feature  
- 不自�?merge/push �?main  
- 不删�?CHANGELOG 历史条目（只追加 Unreleased�? 
- 不修改全局 `~/.config/mimocode/skills` 安装副本

## Tasks

- [x] T1: 建立隔离工作区并复制未提�?SKILL.md �?acceptance: clone 分支 workspace-cleanup 可检出，SKILL.md �?frontmatter 整理 (covers: S2)
- [x] T2: 写入�?feature 文档 �?acceptance: docs/compose/spec/workspace-cleanup.md 存在�?status=designed (covers: S2)
- [x] T3: 深度删除运行时垃圾与 skill 重复副本 �?acceptance: 主仓磁盘�?.playwright-mcp、无 .mimocode/skills/mmit-hunter、examples �?.bug-hunter 运行数据�?gitignore �?.mimocode/ (covers: S2)
- [x] T4: 删除历史 compose specs �?blueprint 正文，新�?docs/BLUEPRINTS.md �?acceptance: docs 下仅 ACCEPTANCE/METRICS/BLUEPRINTS + compose/spec/workspace-cleanup.md；BLUEPRINTS 覆盖 v1/v2 关键结论 (covers: S2)
- [x] T5: 更新 compose-escalate.md、README.md、CHANGELOG.md 引用 �?acceptance: 无死链指向已�?docs；README 定位列表与树一�?(covers: S2)
- [x] T6: 跑单元测试与引用扫描 �?acceptance: `python -m unittest discover -s tests` 全绿；仓库内无对已删路径的硬引用 (covers: S2; depends: T3–T5)
- [x] T7: 独立 review �?finalize 文档 �?acceptance: review �?critical；spec status=delivered (covers: S2; depends: T6)
