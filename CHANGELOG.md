# Changelog

All notable changes to this project are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/).
Versioning follows [SemVer](https://semver.org/).

## [Unreleased]

## [2.0.0] - 2026-09-25

### 摘要
Skill 重构：新增 **全模态迭代测试（MIT-Test）**，从「抓 BUG 收敛」升级为「发布就绪裁决」。含画像→矩阵冻结、RC Loop、P0–P3+Fix Gate、脱敏硬门、E0–E3/生产缺失声明、测试报告+证据包+SIG/RPT/EVD/PRD 综合裁决（Allow/Deny/Escalate）；双 demo 验收与防假 PASS 评审修复。

### Added
- `multimodal-iterative-testing/` — 新 skill **全模态迭代测试（MIT-Test）**：Profile→Matrix 冻结、`.mit/` 状态与 RC Loop、P0–P3 缺陷与 Fix Gate（含强制回归）、E0–E3 环境/脱敏硬门/设备与生产探测、TEST_REPORT + 证据包 + 裁决信号 + Allow/Deny/Escalate 升级包（设计真源 `docs/skill-refactor-multimodal-iterative-testing.md`）
- `multimodal-iterative-testing/references/` — 24 篇契约文档（profile/matrix/13 模态/四层/env/prod/data/defect/fix/deliverables/adjudication/escalate）
- `multimodal-iterative-testing/scripts/` — 画像/矩阵/状态/RC/矩阵执行/缺陷/修复门/脱敏/环境/设备/生产/交付装配/升级/迁移，及自 MIBG 迁入探针副本
- `examples/mit-demo-webapi/` / `examples/mit-demo-media/` — MIT-Test 双验收 demo 与 `.mit/` 交付物（含 Deny / Escalate 裁决演示）
- `tests/test_mit_core.py` — MIT 核心路径单元测试（与 MIBG 脚本同名模块隔离加载）

### Changed
- `iterative-bug-hunter/SKILL.md` — description 负例指向 MIT-Test（发布就绪/go-no-go/RC 验收）
- `README.md` — 双 skill 仓库定位与 MIT 快速开始

## [1.0.2] - 2026-09-18

### 摘要
深度 hunt-and-fix 验收 second-project：清掉 12 项已确认缺陷（代码/网页视觉/画布），并修复 skill 探针三类误报与编码问题；demo 与探针行为可在 quiet 收敛后稳定复测。

### Changed
- `examples/second-project/public/styles.css` — 响应式商品栅格、对比度、触控目标与表单布局修复 → 375px 不再横向溢出，交互区域达到 44px，文本对比度满足 WCAG
- `examples/second-project/public/contact.html` — 增加 error sink（`data-testid=contact-error`）与提交校验脚本 → 空表单提交有可见反馈，ux-flow post 条件可满足
- `examples/second-project/public/shop.html` — 心愿单死链改为 `/contact` → 避免 `href=#` 死端
- `examples/second-project/canvas/promo.scene.json` — 导出尺寸对齐 1080x1920，对象移入 5% 安全区，资源像素/宽高比与显示一致 → canvas-safe/asset 规则不再命中
- `examples/second-project/flows/contact-submit.json` — post 增加 `errorBanner.exists` → 静态采集与交互反馈均可判定

### Fixed
- `examples/second-project/src/checkout.js` — 优惠券改为 `amount * 0.9` → `npm test` 断言 100→90 通过
- `iterative-bug-hunter/scripts/layout_probe.py` — `zero-size`/`touch-target` 跳过 script/style/hidden sink → 隐藏 UI 与非渲染节点不再误报
- `iterative-bug-hunter/scripts/ux_flow.py` — feedback sink 的 `.visible` 在静态采集下按存在+文案判定 → 隐藏 error banner 不再误判 flow 失败
- `iterative-bug-hunter/scripts/hunt_round.py` — `run_dynamic` 使用 UTF-8 + `errors=replace` → 中文测试输出不再因 GBK 解码崩溃

## [1.0.1] - 2026-09-18

### 摘要
工作区深度清理与 docs 收敛：删除运行时垃圾与已交付历史文档，源码仓只保留设计真源、skill 源码、验收记录与蓝图索引；SKILL frontmatter 合规整理。

### Changed
- 工作区深度清理 — 删除运行时垃圾与 skill 重复副本、收敛历史 docs、`.gitignore` 增加 `.mimocode/` → 源码仓只保留真源与必要验收文档
- `docs/BLUEPRINTS.md` — 新增研究蓝图压缩索引，替代已删 `docs/blueprint/*` 正文 → Fix 路由结论可查且不双真源
- `iterative-bug-hunter/references/compose-escalate.md` — 硬链改为指向 `docs/BLUEPRINTS.md`；路由行为仍以本文为准
- `README.md` — 仓库定位列表与收敛后的 docs 树一致；增加项目简称 **MIBG**（Mimo Iterative Bug Hunter）→ 对话、文档与检索可用统一短名；仓库/skill 路径名不变
- `iterative-bug-hunter/SKILL.md` — frontmatter `description` 压为单行、`compatibility` 挪到正文「运行环境」→ 符合 skill-creator 校验习惯
- 删除 `docs/compose/spec/phase0`–`phase3`、`real-acceptance-install`、`skill-config-opt`、`hunt-fix-router` 与 `docs/blueprint/*` 正文 → 历史结论由 CHANGELOG / ACCEPTANCE / METRICS / BLUEPRINTS / skill references 承载

### Added
- `docs/compose/spec/workspace-cleanup.md` — 本次工作区清理 compose feature 文档 → 可追溯 AC、验证与 review 结论

## [1.0.0] - 2026-09-18

### 摘要
首个 1.x 稳定线：为 iterative-bug-hunter 落地 Fix 三档路由（local / lite / compose），并附 research blueprint 与 compose Spec；GitHub 仓库改为公开。

### Added
- `iterative-bug-hunter/references/compose-escalate.md` — 三档修复路由操作化（判据、预算、bug packet、正反例、禁止项）→ Confirm 后可陈述地选择小修 / 结构化重试 / 门控 compose-next
- `docs/compose/spec/hunt-fix-router.md` — compose-next feature 文档与验收记录 → 可追溯 AC、Verify 与独立 review 结论
- `docs/blueprint/hunt-escalate-compose.md` / `hunt-escalate-compose-v2.md` — 升格方案 v1 与文献研判 v2 → 记录 Agentless 式默认路径与 oracle 主门的依据

### Changed
- `iterative-bug-hunter/SKILL.md` — Fix 主循环改为三档路由并链 compose-escalate；Examples/Troubleshooting 补升格边界 → agent 不再只有「小修或 Deferred」
- `iterative-bug-hunter/references/fix-gate.md` — 失败后按 local/lite/compose 分流，禁止同构重试；`fix_gate.py` 判定语义不变
- `iterative-bug-hunter/scripts/init_state.py` — `state.budget` 增加 max_local_attempts / lite_max_attempts / max_compose_escalations 与编辑点上限；新增 `state.fix_router`
- `iterative-bug-hunter/scripts/export_report.py` — bug 可选透出 fix_route / fix_reason_codes / fix_attempts / packet_path；顶层 budget 与 fix_router；schema_version 仍为 1
- `iterative-bug-hunter/references/report-template.md` / `export-schema.md` — REPORT 增加 Fix Router 节；export 文档化可选路由字段

### Fixed
- `tests/test_phase0_scripts.py` / `test_phase3_scripts.py` — 覆盖 budget/fix_router 与 export 路由字段 → 回归门防止路由契约被静默改掉

## [0.4.2] - 2026-09-18

### 摘要
修复 iterative-bug-hunter 的 skill 配置合规问题：frontmatter 通过 skill-creator 校验，正文补全 Examples/Troubleshooting 与 orphan references 链接，并记录双路径安装验收。

### Added
- `docs/compose/spec/skill-config-opt.md` — skill 配置优化 feature 文档与验收记录 → 可追溯 frontmatter 修复、安装路径与 validator 结论

### Fixed
- `iterative-bug-hunter/SKILL.md` — 去掉 frontmatter 中会被校验器判为非法的 YAML 折叠符，补全 `compatibility`，增加 Important/Examples/Troubleshooting 并挂接 ux-flow/canvas/export 等 references → 技能可通过 skill-creator 规范门禁，agent 触发与排错说明更完整

## [0.4.1] - 2026-09-18

### 摘要
真机验收：skill 安装到本机 MiMoCode 路径；在 `examples/second-project` 上完成 hunt（fixture 降级路径），METRICS/ACCEPTANCE 补观测记录。

### Added
- `docs/compose/spec/real-acceptance-install.md` — 真机验收 feature 文档与结论 → 可追溯安装/hunt 过程
- `examples/second-project/run_acceptance_hunt.py` — 验收用 fixture 采集 + hunt_round 入口 → 无 Playwright 时可复现 second-project 扫描

### Changed
- `docs/ACCEPTANCE.md` — 增「真机验收」勾选表 → 安装与 hunt 命中可查
- `docs/METRICS.md` — second-project 观测行（13 类 rule，backend=fixture）→ 度量落点

## [0.4.0] - 2026-09-17

### 摘要
Phase 3 工程化：路由自动发现、误报白名单、machine-readable 导出、baseline/axe CI 门禁，以及第二验收 demo，证明 skill 不绑定单一项目路径。

### Added
- `iterative-bug-hunter/scripts/discover_routes.py` — seed/package.json/sitemap/HTML 同源路由发现与 state 合并 → 开箱可扫多页站
- `iterative-bug-hunter/scripts/fp_feedback.py` — rejected→FP 模式库、hunt/probe suppress、AGENTS snippet 生成（不改用户 AGENTS.md）
- `iterative-bug-hunter/scripts/export_report.py` — schema_version=1 machine-readable report.json → CI/下游可稳定消费
- `iterative-bug-hunter/scripts/baseline_lock.py` — 基线 sha256 锁；approvals 必须匹配当前 hash，避免历史批准永久解锁
- `iterative-bug-hunter/scripts/axe_gate.py` — 可选 axe-core 门禁；unavailable 不假装通过
- `iterative-bug-hunter/scripts/ci_gate.py` + `.github/workflows/ci.yml` — 本地/CI 同一编排入口
- `examples/second-project/` — 第二验收 demo（`/shop` `/contact` + 不同缺陷组合）→ 泛化 DoD
- `iterative-bug-hunter/references/route-discovery.md` `fp-feedback.md` `export-schema.md` `ci-gate.md`
- `tests/test_phase3_scripts.py` — Phase 3 单测（共 108 tests 全绿）

### Changed
- `hunt_round.py` / 四探针 — 支持 `--fp-patterns`；summary 增 `suppressed_count`，suppress 不计入 new
- `init_state.py` — phase=3、route_discovery/ci/export/fp 默认段
- `SKILL.md` / `docs/ACCEPTANCE.md` / README — Phase 3 指针与 DoD

### Fixed
- 独立审查 3 critical：baseline approvals 过宽、路由同优先级字母序、probe 缺 FP 集成 → 已在合并前修复并复审关闭

## [0.3.0] - 2026-09-17

### 摘要
Phase 2 深层与画布：ux-flow（死链/反馈缺失/符号化前后置条件）、canvas-safe/asset（安全区/导出/分辨率/层级）、vlm-audit 双视角候选合并、subagent 分片采集。审查 critical 已修复。

### Added
- `iterative-bug-hunter/scripts/ux_flow.py` — 静态 UX 规则 + WebTestPilot 符号化 pre/post → 死链、无反馈提交、空状态可机器判定；缺符号记 unavailable 不假 quiet
- `iterative-bug-hunter/scripts/canvas_probe.py` — safe-area / export-mismatch / z-order（矩形并集）/ low-res / aspect / hierarchy-flat → 画布 scene-json 可出 L3 数值证据
- `iterative-bug-hunter/scripts/vlm_audit.py` — 双视角 scaffold/merge + 与机器 finding 交叉 → VLM 只产候选，不与 layout 重复计数
- `iterative-bug-hunter/references/ux-flow.md` `canvas-protocol.md` `vlm-audit.md` `subagent-capture.md` — Phase 2 通道与并发协议 → agent 有可执行配方
- `examples/acceptance-demo/canvas/poster.scene.json` `flows/empty-submit.json` — 注入画布与 flow 缺陷（非 gitignore 路径）→ Phase 2 DoD 可复现
- `tests/test_phase2_scripts.py` `tests/phase2_fixture_e2e.py` — 27 unit + fixture E2E → 回归安全网（含 stub-canvas 不升 L4、z-order 并集）

### Changed
- `iterative-bug-hunter/scripts/capture_web.py` — 增加 `--shard i/n` 与 `merge`；elements 写入 href/role/type/attrs → 支持 subagent 并行采集与 ux-flow
- `iterative-bug-hunter/scripts/hunt_round.py` — 编排 ux/canvas；仅 objects/assets 真实可扫时才升 L4 → 避免 stub 配置假 quiet
- `iterative-bug-hunter/scripts/init_state.py` — phase=2、canvas/ux/vlm oracle 默认值、subagent 写路径白名单 → 新项目开箱即用 Phase 2
- `iterative-bug-hunter/SKILL.md` 与 references strategies/visual-rules/capture-protocol — 主循环指向 Phase 2 脚本 → 正文仍精简
- `docs/ACCEPTANCE.md` — Phase 2 DoD 8 项勾选 → 验收可查

### Fixed
- 独立审查：stub canvas 不再假升 L3→L4 或假 quiet canvas modality
- z-order 覆盖改矩形并集，两块各盖 60% 的同区面板不再加成 100%
- 验收 flow fixture 移出 `.bug-hunter/`（gitignore）到 `examples/acceptance-demo/flows/`

## [0.2.0] - 2026-09-17

### 摘要
Phase 1 全模态成型：多 viewport 采集、完整 layout-geom / contrast-type / responsive-matrix、像素 visual-diff 与可判定 Fix Gate、hunt_round 单轮编排。独立审查 5 个 critical 已修复。

### Added
- `iterative-bug-hunter/scripts/capture_web.py` — routes×viewports 采集，MANIFEST + elements schema；Playwright Python/Node 后端，不可用时 exit 3 → agent 不必手搓 elements.json
- `iterative-bug-hunter/scripts/layout_probe.py` 扩展 — `text-clip` / `overlap-interactive` / `zero-size` / `off-canvas` / `touch-target` → 窄屏触控与布局问题可机器判定
- `iterative-bug-hunter/scripts/contrast_probe.py` — WCAG `contrast-text` / `font-too-small` / `line-height-tight`，最近祖先背景回溯 → 低对比度可出 L3 数值证据
- `iterative-bug-hunter/scripts/visual_diff.py` — baseline snapshot / 像素 compare / intentional approve → 修完可判视觉回归与有意变更
- `iterative-bug-hunter/scripts/fix_gate.py` — target_cleared + zero_new_layout + pixel_gate + unit_green → Fix Gate 可机器放行
- `iterative-bug-hunter/scripts/hunt_round.py` — 单轮 capture→probe→register→summary→converge → 缩短 agent 手工编排
- `examples/acceptance-demo/` — 注入 touch-target / overlap-interactive / zero-size → Phase 1 DoD 可复现
- `tests/test_phase1_scripts.py` + `tests/phase1_fixture_e2e.py` — 61 unit + fixture E2E → 回归安全网

### Changed
- `iterative-bug-hunter/references/` capture-protocol / visual-rules / fix-gate / strategies — 更新为 Phase 1 契约，细节不塞 SKILL.md
- `iterative-bug-hunter/SKILL.md` — 主循环指向 capture_web / hunt_round / fix_gate
- `docs/ACCEPTANCE.md` — 增补 Phase 1 DoD 8 项
- `iterative-bug-hunter/scripts/init_state.py` — phase=1 与 overlap/line-height/visual_diff oracle 默认值

### Fixed
- 空/`unavailable` MANIFEST 不再记入 web 策略或抬升 degrade，避免假 quiet
- capture 计算真实 DOM depth（原写死 0），对比度祖先回溯可用
- `[data-testid]` 不再视为 interactive，容器不再误报 overlap
- 对比度背景取最近不透明祖先，而非最浅层
- html/body 只参与 page-level `overflow-x`，不再双计元素级 right 溢出

## [0.1.0] - 2026-09-16

### 摘要
Phase 0：可安装的 iterative-bug-hunter skill 骨架，能在本地 demo 上完成扫描 → L3 确认 → 指纹去重 → quiet 收敛 → 带盲区的 REPORT。

### Added
- `LICENSE` — MIT 许可证 → 仓库可被他人合法复用与分发
- `iterative-bug-hunter/SKILL.md` — 触发、Scope、主循环、quiet 四条件、Confirm 门槛与用户合同 → agent 可按协议迭代抓 bug 而非一次 lint 汇总
- `iterative-bug-hunter/scripts/init_state.py` — O_EXCL 单写锁 + state/fingerprints/目录树初始化与 resume → 多会话安全、可断点续跑
- `iterative-bug-hunter/scripts/fingerprint.py` — DESIGN §3.2 粗粒度指纹注册与去重 → 同 viewport 同问题跨轮不重复计数，1px 采集噪声不伪造新 bug
- `iterative-bug-hunter/scripts/converge_check.py` — §6.2 quiet 四条件判定 → 明确「何时停」并支持 K 轮收敛
- `iterative-bug-hunter/scripts/layout_probe.py` — Phase 0 overflow-x 几何规则 → 375px 下可产出 L3 视觉 Finding
- `iterative-bug-hunter/scripts/validate_report.py` — REPORT 必含节校验（含 rule_id）→ 报告结构可机器验收
- `iterative-bug-hunter/references/` — 策略库、采集/确认协议、视觉规则、Fix Gate、报告模板 → 细节不塞进 SKILL.md
- `examples/acceptance-demo/` — 零依赖双路由站 + 注入 overflow 与 add off-by-one → Phase 0 DoD 可复现
- `docs/ACCEPTANCE.md` / `docs/METRICS.md` — DoD 8 项勾选与指标观测表 → 验收与后续度量有落点
- `tests/test_phase0_scripts.py` — 23 个单元测试覆盖状态机/指纹/收敛/探针/锁 → 回归安全网
