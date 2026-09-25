# 设计文档：全模态迭代测试 Skill 重构

| 字段 | 内容 |
|------|------|
| 文档编号 | MIT-DESIGN-001 |
| 版本 | v1.0 |
| 状态 | 设计定稿（待实现） |
| 源 Skill | `iterative-bug-hunter`（迭代式抓 BUG / MIBG） |
| 目标 Skill | **全模态迭代测试**（`multimodal-iterative-testing`，简称 **MIT-Test**） |
| 文档性质 | Skill 重构设计说明书（纯 Markdown） |
| 实现约束 | 落地时拆分为 `SKILL.md` + `references/` + `scripts/`；本文为设计真源 |

---

## 1. 背景与问题定义

### 1.1 背景

`iterative-bug-hunter` 面向「抓 BUG 直到收敛」：以代码、Web 视觉、画布三通道为主，输出缺陷报告。该模型适合设计 QA 与缺陷狩猎，但**不能直接回答发布问题**：

- 「这个候选版本能不能正常发布使用？」
- 「测过哪些模态？生产侧有没有验证？」
- 「结论依据是什么，能否复核？」

本重构将其升级为 **全模态迭代测试** skill：以指定项目为对象，按项目画像生成全模态测试矩阵，在生产等价环境与真实/仿真设备、脱敏数据下迭代执行发布就绪测试；按缺陷分级修复并补充回归测试；每轮重建候选版本并全量复测；最终由 agent 综合裁决是否允许发布，或在预算/阻塞时升级人工。

### 1.2 现状差距

| 编号 | 差距 | 风险 |
|------|------|------|
| G1 | 模态仅 code / web-visual / canvas | API、CLI、移动端、桌面、DB、基础设施、音视频、3D/XR、插件等漏测 |
| G2 | 默认本地开发环境 | 与生产拓扑/配置/数据形状不等价 |
| G3 | 无候选版本（RC）语义 | 修复后不重建、不全量复测，回归不可见 |
| G4 | 缺陷仅 Confirmed/Deferred | 无法按发布风险（P0–P3）裁决 |
| G5 | 交付物以 REPORT 为主 | 缺结构化测试报告、证据包、裁决信号 |
| G6 | 收敛即停或布尔门禁 | 缺 agent 综合判断与可解释发布结论 |
| G7 | 无生产侧测试协议 | 「本地绿、生产红」无法在裁决中体现 |

### 1.3 设计原则

1. **画像驱动，不全开不漏列**：矩阵来自项目画像；`n/a` 也要显式记录。
2. **证据优先，禁止假通过**：无机读证据不得判 PASS；`unavailable` ≠ 通过。
3. **RC 原子性**：每轮测试针对完整候选制品；禁止热修后跳过全量复测。
4. **修复必回归**：无回归测试不得标记 fixed。
5. **裁决综合化**：是否允许发布由 agent 综合四项依据，而非单一门禁颜色。
6. **保守收敛**：依据冲突、生产结果缺失、oracle 不可信时，取更保守结论或升级人工。
7. **可审计可恢复**：状态、矩阵、证据、结论全程落盘，可 resume。

---

## 2. 目标与非目标

### 2.1 目标

| 编号 | 目标 | 验收要点 |
|------|------|----------|
| O1 | 生成项目相关的**全模态测试矩阵** | 覆盖画像命中的全部模态，含 required/optional/n/a |
| O2 | 在**生产等价环境**、真实/仿真设备、**脱敏数据**下执行 | 环境偏差可声明；脱敏硬门通过 |
| O3 | **迭代**发布就绪测试并**分级修复** + 回归 | P0–P3；每项 fixed 有回归绿 |
| O4 | 每轮**重建 RC** 并**全量复测** | `rc_sha` 变化；矩阵 required 重跑 |
| O5 | 产出**测试报告**与**证据包** | 报告可独立阅读；证据可点开复核 |
| O6 | 由 **agent 综合裁决**是否允许发布 | 裁决信号 + 测试报告 + 证据包 + 真实生产环境测试结果 |
| O7 | 预算尽或阻塞时**升级人工** | 升级包完整；不擅自放行 |

### 2.2 非目标

- 不替代无障碍合规认证、渗透测试报告或法务/产品签字。
- 不承诺零缺陷；「允许发布」仅表示在**本矩阵、本预算、已披露盲区**内达到发布标准。
- 不建设通用云真机农场或完整 CI/CD 产品。
- 不做未授权生产破坏性操作；生产测试仅限授权的只读/影子/金丝雀/合成探测等范围。
- 不替代应用商店或云厂商发布流水线；交付物可供其消费。

---

## 3. 术语与缩写

| 术语 | 定义 |
|------|------|
| **全模态** | 项目实际涉及的测试表面集合：代码、API、Web、移动端、桌面端、CLI、数据库、基础设施、音视频、Canvas、3D/建模、XR、插件等 |
| **项目画像 Profile** | 从仓库/清单/运行时探测得到的项目特征（形态、拓扑、设备、数据等级、制品类型等） |
| **测试矩阵 Matrix** | 由 Profile 映射的「模态 × 检查项 × 证据要求」冻结表 |
| **RC** | Release Candidate，候选版本制品（带 `rc_n` 与内容哈希 `rc_sha`） |
| **RC Loop** | 构建 → 环境就绪 → 全量矩阵测 → 缺陷分级 → 修复回归 → 重建 RC 的循环 |
| **测试报告** | 人类可读、可复核的结构化测试结论文档 |
| **证据包** | 与 RC 绑定的机读/多媒体证据集合及索引 |
| **裁决信号** | 供 agent 综合判断的结构化质量信号 JSON |
| **真实生产环境测试结果** | 在授权范围内对生产环境（或与生产等价的准生产流量面）取得的测试/探测结果 |
| **Blind Spot** | 因工具/设备/权限/数据等原因未能覆盖或降级的范围，必须披露 |
| **P0–P3** | 缺陷发布分级（见 §8） |
| **Allow / Deny / Escalate** | 发布裁决三出口：允许发布 / 拒绝发布 / 升级人工 |
| **E0–E3** | 测试环境层级：本地沙箱 / 生产等价 / 真实生产 / 设备面（见 §7） |

---

## 4. Skill 身份与边界

### 4.1 命名

| 项 | 值 |
|----|-----|
| 中文显示名 | **全模态迭代测试** |
| 英文 ID | `multimodal-iterative-testing` |
| 对话简称 | MIT-Test（避免与许可证 MIT 混淆时写全名） |
| 状态目录 | `.mit/` |

### 4.2 Frontmatter（实现用）

```yaml
---
name: multimodal-iterative-testing
description: 全模态迭代测试：按项目画像生成覆盖代码/API/Web/移动端/桌面端/CLI/数据库/基础设施/音视频/Canvas/3D/XR/插件等实际模态的测试矩阵，在生产等价环境与真实/仿真设备、脱敏数据下迭代执行发布就绪测试，按缺陷分级修复并补充回归测试，每轮重建候选版本并全量复测；交付测试报告与证据包，是否允许发布由 agent 综合裁决信号、测试报告、证据包与真实生产环境测试结果判断，否则在轮次/时间预算或阻塞时升级人工。Use when 用户要 全模态迭代测试 / 发布就绪 / go-no-go / 发布裁决 / RC 验收 / 能不能发版。Do NOT use for 一次性 lint、纯功能开发、或仅需视觉抓 bug（→ iterative-bug-hunter）。
---
```

### 4.3 触发条件

满足任一即触发：

1. 用户点名：全模态迭代测试、发布就绪、发布裁决、go/no-go、RC 验收、「能不能正常发布使用」。
2. 用户给出候选版本（tag、构建产物、制品哈希）并要求发布级测试结论。
3. 用户要求以 skill 形式对指定项目做发布级、多表面迭代测试。

### 4.4 不触发

1. 一次性 lint / 静态检查 / 单点 code review。
2. 纯功能开发或新接口实现。
3. 仅视觉/布局抓 BUG（继续使用 `iterative-bug-hunter`）。
4. 无可构建、可运行目标，且用户拒绝提供制品与环境信息。

### 4.5 用户合同（对外口径）

> 我会先根据项目生成全模态测试矩阵，在尽量等价于生产的环境中，用脱敏数据和真实/仿真设备反复测这个候选版本，并在授权范围内补充真实生产环境测试结果。问题按严重级别修复并补上回归测试，每轮重新构建候选版本并全量复测。结束后交付**测试报告**和**证据包**；是否允许发布，由我综合**裁决信号、测试报告、证据包、真实生产环境测试结果**判断并写明理由，而不是只报一个门禁颜色。预算用尽或卡住时升级人工，并说明卡点、已覆盖范围与盲区。

---

## 5. 总体架构

### 5.1 逻辑视图

```text
┌─────────────────────────────────────────────────────────────────┐
│                        全模态迭代测试 MIT-Test                     │
├──────────────┬──────────────────┬───────────────────────────────┤
│  规划层       │  执行层           │  裁决与交付层                  │
│  Profile     │  Env (E0–E3)     │  测试报告                      │
│  Matrix      │  RC Build        │  证据包                        │
│  Scope       │  Matrix Full Test│  裁决信号                      │
│              │  Triage/Fix/Reg  │  Agent 综合裁决                │
│              │  RC Rebuild      │  Allow / Deny / Escalate       │
└──────────────┴──────────────────┴───────────────────────────────┘
```

### 5.2 数据流

```text
仓库/清单/运行时
    → profile.json
    → matrix.json（冻结 matrix_rev）
    → env_manifest.json + 脱敏数据
    → artifacts/RC-n.meta.json
    → runs/RC-n/**（采集与探针）
    → defects/*.json
    → deliverables/{TEST_REPORT.md, evidence/, adjudication_signals.json}
    →（授权时）prod_test_results.json
    → RELEASE_DECISION.md | escalation/
```

### 5.3 与源 Skill 的关系

| 能力 | 处理 |
|------|------|
| Web 视觉/无障碍/布局探针、canvas 探针 | **复用** MIBG 实现 |
| 指纹去重、跨模态确认、Fix Gate、状态锁 | **复用并加强** |
| quiet 收敛 | **降级为过程信号**，不再作为发布出口 |
| 主循环、模态目录、环境/数据、交付物、裁决 | **重写**为本设计 |

---

## 6. 项目画像与全模态测试矩阵

### 6.1 矩阵生成公式

```text
Matrix = (Profile 命中模态 ∩ 发布必测底线) ∪ 用户点名模态
```

### 6.2 生成步骤

| 步骤 | 名称 | 输入 | 输出 | 规则 |
|------|------|------|------|------|
| S1 | Profile Scan | 仓库、清单、CI、README、媒体目录 | `profile.json` | 静默完成；缺字段用 `unknown`，不得臆造 |
| S2 | Surface Map | profile | 模态命中表 | 线索→surface→modality 映射 |
| S3 | Matrix Freeze | 模态命中 + 用户点名 | `matrix.json` / `matrix.md` | 写入 `matrix_rev`；**未冻结不得开跑** |

矩阵变更必须 bump `matrix_rev` 并记录原因；变更后应对当前 RC 重跑受影响的 required 项。

### 6.3 Profile 字段

| 字段 | 类型 | 示例 | 说明 |
|------|------|------|------|
| `app_types` | string[] | `web,api,cli,mobile,desktop,xr,plugin` | 主交付形态 |
| `runtime` | string | `node@20` | 构建/运行时 |
| `topology` | string | `api+worker+postgres+redis` | 依赖形状 |
| `devices` | string[] | `ios-sim,android-emu,quest3` | 设备面 |
| `data_classes` | string[] | `pii,payment,media` | 数据等级 |
| `plugins` | string[] | `vscode-ext` | 插件宿主 |
| `release_artifact` | string | `oci-image,dmg,msix,npm,apk` | RC 形态 |
| `contract_apis` | string[] | `openapi.yaml,proto/` | 对外契约源 |
| `prod_access` | enum | `none,readonly,shadow,canary` | 生产测试授权 |

### 6.4 矩阵标注

| 标注 | 含义 | 执行要求 | 裁决影响 |
|------|------|----------|----------|
| `required` | 安全底线或用户点名 | 必须执行并留证 | 缺失或失败强烈倾向 Deny |
| `optional` | 可降级/替代证据 | 执行或降级 | 降级必须记 Blind Spot |
| `n/a` | 画像未命中 | 保留排除记录 | 证明「考虑过」 |

### 6.5 全模态目录（13 类 Surface）

| 编号 | modality | 覆盖内容 | 最低证据（Evidence Floor） | 典型分级 |
|------|----------|----------|----------------------------|----------|
| M1 | `code` | 单测/集成、类型/lint、依赖漏洞、资源与并发 | 测试退出码、lint/audit 报告 | P0–P1 |
| M2 | `api` | 契约、鉴权、错误模型、幂等、超时限流、版本兼容 | contract diff、authz 矩阵、黄金响应 | P0–P1 |
| M3 | `web` | 布局、对比度、响应式、a11y、关键路径 UX、视觉基线 | route×viewport、axe/contrast、visual diff | P0–P1 |
| M4 | `mobile` | 安装启动、权限、深链、恢复、推送、安全区 | 冷启动日志、权限流、设备矩阵 | P0–P1 |
| M5 | `desktop` | 安装包、签名公证、更新、托盘/快捷键、DPI、崩溃转储 | installer verify、update path、签名状态 | P0–P1 |
| M6 | `cli` | help/退出码、管道重定向、配置发现、非交互 CI | golden exit/stdout/stderr、flag 矩阵 | P1 |
| M7 | `db` | 迁移、约束、查询、备份恢复、锁与慢查询 | migrate dry-run、restore smoke | P0–P1 |
| M8 | `infra` | 镜像、健康检查、配置/密钥、TLS、限额、滚动就绪 | image scan、readiness、secret hygiene | P0–P1 |
| M9 | `av` | 可解码可播、时长对齐、响度、字幕音轨、导出参数 | 元数据探针、可播冒烟、导出参数 | P1–P2 |
| M10 | `canvas` | 安全区、层级、导出尺寸、资产分辨率 | scene 与导出交叉验证 | P1–P2 |
| M11 | `3d` | 加载、法线/UV/材质、面数预算、动画、导出格式 | 加载日志、预算计数 | P1 |
| M12 | `xr` | 会话生命周期、追踪丢失、交互、帧率、舒适度 | session 日志、帧率采样、sim/real 标注 | P0–P1 |
| M13 | `plugin` | 宿主 API、安装/升级/卸载、权限、冲突、沙箱 | host-API pin、install/upgrade 流 | P0–P1 |

### 6.6 测试层级（正交维度）

矩阵除「模态」外，增加四层检查维度（与模态正交，取自业界多模态测试实践的 Data→Modality→Fusion→Decision）：

| 层 | 代号 | 检查内容 |
|----|------|----------|
| 数据层 | DL | 输入/夹具/种子质量、扰动鲁棒性、脱敏完整性 |
| 单模态层 | ML | 各 surface 自身功能与非功能 |
| 融合层 | FL | 跨模态一致：图文表数字、版本、流程状态一致 |
| 决策层 | AL | 裁决信号完整、报告-证据一致、发布结论可追溯 |

融合层不一致（例如报告数字 ≠ 证据数字）视为**证据缺陷（≥P1）**，须先修复再裁决。

### 6.7 跨模态一致门

- 同一事实跨图/表/文/制品一致。
- 版本号、人名、日期、URL 跨源一致；不一致必须披露。
- 禁止在不一致状态下宣称完成。

---

## 7. 环境、设备与数据

### 7.1 环境层级

| 层级 | 名称 | 用途 | 裁决权重 |
|------|------|------|----------|
| E0 | 本地/CI 隔离沙箱 | 单测、静态、快速反馈 | 辅助 |
| E1 | 生产等价环境 | 主执行面（拓扑/配置/数据形状对齐） | 主证据 |
| E2 | 真实生产环境（授权内） | 只读/影子/金丝雀/合成探测 | **强裁决输入** |
| E3 | 真实或仿真设备 | 移动、桌面、XR 等设备面 | 设备相关模态强依据 |

### 7.2 生产等价（E1）要求

| 维度 | 要求 | 允许偏差 |
|------|------|----------|
| 拓扑 | 依赖形状与生产一致 | 须记录 `topology_delta` |
| 配置 | 同一配置模式 | 禁止 dev-only 旁路 |
| 网络 | 出口、TLS、超时重试对齐 | 离线须声明 `network_delta` |
| 版本 | 运行时与制品锁定 | 禁止 `latest` |
| 可观测 | 日志/指标/追踪可导出 | 无则 Blind Spot |

### 7.3 真实生产环境测试（E2）

**授权级别**（`prod_access`）：

| 级别 | 允许动作 |
|------|----------|
| `none` | 不测生产；报告必须声明「生产结果缺失」 |
| `readonly` | 只读健康检查、合成探测、脱敏日志/指标抽样 |
| `shadow` | 影子流量对比（若具备） |
| `canary` | 小流量金丝雀（须用户明确批准） |

**推荐协议（Canary vs Control）**：

1. 选择少量用户可感知 SLI（错误率、延迟分位、关键旅程成功率），避免嘈杂资源指标。
2. 金丝雀与对照**同期对比**，禁止仅 before/after 自比。
3. 一次只观察一个变更；保证指标可归因。
4. 观察窗覆盖有代表性的流量；聚合窗口 ≤ 观察窗。
5. 偏离阈值 → 暂停/回滚并记缺陷；健康 → 按策略放量。
6. 记录 error budget 消耗；烧穿阈值直接保守裁决。

**Synthetic Monitoring（推荐作为 E2 主探针）**：对生产（或准生产）持续注入合成用户旅程，覆盖可用性、关键事务、性能、第三方依赖；探针自身健康也须监控。

**禁止**：未授权写路径压测、破坏性数据操作、对真实用户切换未批准版本、将未脱敏生产数据写入证据包。

### 7.4 设备（E3）

- 真机：记录型号、OS、DPI、区域。
- 仿真：必须标注 `sim`，覆盖率单独统计。
- 缺设备：optional + Blind Spot；若阻塞 P0 路径 → Escalate。

### 7.5 脱敏数据契约（硬门）

1. 识别 `data_classes`。
2. 合成/脱敏种子：保留**形状**，替换敏感值。
3. 开跑前扫描密钥、证件号、手机号、卡号、邮箱实值等；失败拒绝开跑。
4. 生产抽样导出同样脱敏；违规 → 立即 Escalate 并隔离产物。

---

## 8. 缺陷分级、修复与回归

### 8.1 分级

| 级 | 定义 | 处理 | 对裁决 |
|----|------|------|--------|
| **P0** | 崩溃、数据丢失、安全漏洞、鉴权绕过、无法安装启动、核心路径不可用 | 立即修 + 强制回归 | 默认 Deny |
| **P1** | 主路径错误、严重性能回退、错误数据、关键 a11y 阻断、制品损坏 | 本轮必修或用户书面接受 | 默认 Deny |
| **P2** | 次要路径、明显视觉回归、部分设备问题、体验差但可恢复 | known-issues 后可条件放行 | 条件 Allow 需用户点头 |
| **P3** | 文案、边缘审美、文档问题、非阻断 polish | backlog | 默认不阻塞 |

纯审美、无规则可述的 VLM 主观结论 → P3 或 Deferred，不得单独支撑 Deny/Allow 主路径。

### 8.2 修复纪律

1. 只修 **Confirmed** 缺陷；一次一修。
2. **无回归测试不得标记 fixed。**
3. Fix Gate（机器判定）：
   - `target_cleared`：同缺陷同路径不再命中；
   - `zero_new_high`：无新增 P0/P1；
   - `non_target_stable`：非目标面无意外回归；
   - `regression_green`：新增/加强回归测试退出码 0。
4. 失败回滚或换策略（local / lite / compose 门控）；**禁止同构重试**（≥2 次失败必须重定位或升级）。

### 8.3 回归测试固化

| 来源缺陷面 | 回归形态 |
|------------|----------|
| API | contract / CDC、黄金响应 |
| Web | route×viewport probe、视觉基线 |
| CLI | golden exit/stdout/stderr |
| DB | migrate + query/constraint fixture |
| Mobile/Desktop | 安装启动冒烟、关键流 |
| Infra | readiness、secret scan |
| AV / Canvas / 3D / XR | 可播/加载/尺寸/预算断言 |
| Plugin | host-API pin、install/upgrade |
| Code | 最小复现单测/集成测 |
| Prod | 合成旅程 / canary SLI 断言 |

---

## 9. 迭代测试主循环（RC Loop）

### 9.1 循环图

```text
Bootstrap → Environment Up → Build RCn → Matrix Full Test
    ↑                                       ↓
    │                                 Triage P0–P3
    │                                       ↓
    │                                 Fix + Regression
    │                                       ↓
    └────────── Rebuild RCn+1 ←── 仍有阻塞且预算内
                                        ↓
                              Assemble Deliverables
                              （测试报告 / 证据包 / 裁决信号）
                                        ↓
                              Prod Test（授权范围内 E2）
                                        ↓
                              Agent 综合裁决
                     ┌──────────────┼──────────────┐
                     ↓              ↓              ↓
               Allow Release  Deny Release  Escalate Human
```

### 9.2 步骤规格

| 步 | 名称 | 动作 | 产物 | 失败处理 |
|----|------|------|------|----------|
| B1 | Bootstrap | 初始化/恢复 `.mit/`；加载 profile/matrix | `state.json` | 无法识别项目 → Escalate |
| B2 | Environment Up | 拉起 E1（+授权 E2/E3）；脱敏扫描 | `env_manifest.json` | 脱敏失败 → Escalate |
| B3 | Build RC | 干净基线构建 RC，锁哈希 | `artifacts/RC-n.meta.json` | 构建失败 → P0 级阻塞 |
| B4 | Matrix Full Test | 执行 required + 已启用 optional | `runs/RC-n/**` | 探针失败记 Blind Spot，禁止假 PASS |
| B5 | Triage | 去重、确认、分级 | `defects/*.json` | 主观项 Deferred |
| B6 | Fix + Regression | 仅 Confirmed；过 Fix Gate | 修复提交 + 回归结果 | 超失败护栏 → Escalate/Deferred |
| B7 | Assemble | 生成交付物 | 测试报告、证据包、裁决信号 | 缺件不得进入 Allow |
| B8 | Prod Test | E2 协议（§7.3） | `prod_test_results.json` 或缺失声明 | 无授权则显式缺失 |
| B9 | Adjudicate | Agent 综合四项依据 | `RELEASE_DECISION.md` | 见 §11 |
| B10 | Loop | Deny 且预算内 | RCn+1 | 见 §12 护栏 |

**RC 原子性**：B4–B8 必须针对同一 `rc_sha`。任何源码修改后不得直接复用旧结果宣告 Allow。

### 9.3 与 quiet 信号的关系

quiet（连续 N 轮无新增确认缺陷）可作为**过程健康信号**写入裁决信号，**不是**发布出口。发布出口只有：Allow / Deny / Escalate。

---

## 10. 交付物

### 10.1 交付物清单

| 交付物 | 路径 | 必要性 |
|--------|------|--------|
| **测试报告** | `.mit/deliverables/TEST_REPORT.md` | 必须 |
| **证据包** | `.mit/deliverables/evidence/` + `EVIDENCE_INDEX.md` | 必须 |
| **裁决信号** | `.mit/deliverables/adjudication_signals.json` | 必须 |
| **发布裁决** | `.mit/deliverables/RELEASE_DECISION.md` | 必须 |
| 机读导出 | `.mit/deliverables/export.json` | 建议 |
| 升级包 | `.mit/escalation/` | 触发升级时必须 |

### 10.2 测试报告规范（TEST_REPORT.md）

必须包含且顺序固定：

1. 执行摘要（项目、RC 哈希、轮次、总体结论草稿）
2. 项目画像与矩阵覆盖（required/optional/n/a 统计）
3. 环境与设备（E0–E3、偏差、sim/real）
4. 分模态测试结果
5. 缺陷清单（P0–P3）与修复/回归
6. **真实生产环境测试结果**（或「缺失」及原因、影响）
7. 盲区与降级（Blind Spots）
8. Known Issues（含用户接受记录）
9. 裁决信号摘要
10. 证据包索引

**质量要求**：每个结论句可追溯到证据 ID；无「大概/应该」式无证据断言。

### 10.3 证据包规范

- 与 `rc_sha`、`matrix_rev` 绑定。
- 含：矩阵执行记录、关键缺陷复现、修复后回归、生产测试或缺失声明、环境清单。
- 路径真实可打开；禁止未脱敏敏感数据。
- 证据伪造或不可追溯 → 直接 Deny 或 Escalate。

---

## 11. Agent 综合裁决模型

### 11.1 裁决原则

**是否允许发布的依据，必须由 agent 综合以下四项判断**，禁止只看自动门禁颜色或只读报告标题：

| 依据 | 代号 | 内容 |
|------|------|------|
| 裁决信号 | SIG | `adjudication_signals.json` 结构化质量信号 |
| 测试报告 | RPT | `TEST_REPORT.md` 完整叙述与指标 |
| 证据包 | EVD | 可复核的机读/多媒体证据 |
| 真实生产环境测试结果 | PRD | E2 结果或显式缺失说明 |

规则：

1. 四项**互证**：报告结论须能落到证据；信号须与报告一致。
2. **冲突取保守**：不一致时取更严格一侧，并在 `RELEASE_DECISION.md` 写明冲突。
3. **缺项不得无条件 Allow**：尤其 PRD 缺失时，只能条件 Allow（如仅灰度）或 Deny/Escalate。
4. **硬失败直决**：脱敏失败、生产关键路径失败、证据不可信 → Deny/Escalate，不得被其他「好看」信号抵消。

### 11.2 裁决信号模式（摘要）

```json
{
  "rc_id": "RC-3",
  "rc_sha": "…",
  "matrix_rev": "m2",
  "signals": {
    "build_ok": true,
    "matrix_required_coverage": 1.0,
    "optional_degraded": ["xr-sim-only"],
    "open_p0": 0,
    "open_p1": 0,
    "open_p2_accepted": 1,
    "regression_green": true,
    "device_coverage": 0.8,
    "data_mask_clean": true,
    "release_layers": {
      "artifact_ready": true,
      "exposure_ready": false,
      "exposure_constraint": "canary_5pct_only"
    },
    "prod_test": {
      "available": true,
      "mode": "canary_vs_control",
      "slis": ["http_5xx_rate", "p95_latency", "journey_success"],
      "critical_path_pass": true,
      "control_delta_error_rate": 0.001,
      "error_budget_burn": 0.12,
      "rollback_ready": true
    },
    "oracle_quality": {
      "k": 3,
      "agreement_rate": 0.86,
      "fp_rate_estimate": 0.08
    },
    "contract_breaking_unreviewed": false,
    "blind_spots": ["xr-no-hmd"],
    "quiet_streak": 2
  }
}
```

### 11.3 分层发布语义

| 字段 | 含义 |
|------|------|
| `artifact_ready` | RC 制品在测试意义上可交付 |
| `exposure_ready` | 可对用户/流量放量 |
| `exposure_constraint` | 放量约束（暗启动、金丝雀比例、白名单等） |

- `artifact_ready=true` 且 `exposure_ready=true` → 可无条件 Allow。
- `artifact_ready=true` 且 `exposure_ready=false` → **仅条件 Allow**（按 `exposure_constraint`）或 Deny 全量。
- 将「测通过」与「放量」分离，对齐 Progressive Delivery 的 Deploy≠Release。

### 11.4 裁决输出

| 结论 | 条件 | 对外表述 |
|------|------|----------|
| **Allow Release** | 四项齐备且综合支持；残余风险可接受 | **该版本可正常发布使用**（附条件则一并说明） |
| **Deny Release** | 开放 P0/P1、生产失败、证据冲突/不可信、覆盖不足等 | **不可发布**；列出阻塞项与修复顺序 |
| **Escalate Human** | 预算尽、硬阻塞、需签字、oracle 不可判定、无生产且不愿在缺失下裁决 | **请人工裁决**；附升级包 |

`RELEASE_DECISION.md` 必须包含：结论、四项依据摘要、冲突点、附带条件、RC 哈希、agent 置信说明（高/中/低及原因）。

### 11.5 进入裁决前检查清单

- [ ] profile / matrix 已冻结
- [ ] RC 哈希与构建记录齐备
- [ ] 环境与偏差已声明（含 E2/E3）
- [ ] 脱敏扫描通过
- [ ] required 矩阵已执行
- [ ] 修复均带回归且绿
- [ ] 测试报告完整
- [ ] 证据包索引可复核
- [ ] 裁决信号已生成
- [ ] 生产结果已写入或显式声明缺失
- [ ] Blind Spots 已披露

**清单未完成 → 只能 Escalate 或继续补测，不得 Allow。**

---

## 12. 预算、护栏与人工升级

### 12.1 默认预算

| 护栏 | 默认 | 触发动作 |
|------|------|----------|
| `max_rc_rounds` | 5 | 停止重建，Escalate |
| `max_wall_clock` | 4h | 保存现场，Escalate |
| `max_fix_failures_per_defect` | 2 | 换策略/升档/Deferred |
| `max_p0_fix_rounds` | 3 | Escalate |
| `max_compose_escalations` | 1 | 不再自动升 compose |
| `max_vlm_calls`（可选） | 按项目 | 超限降级主观通道并披露 |

### 12.2 必须升级人工

1. 脱敏失败、密钥泄露、越权访问生产数据。
2. 需产品/法务/合规签字的决策。
3. 环境/设备/生产权限缺失且无法本地消除。
4. 需求或契约歧义导致 oracle 不可判定。
5. 预算耗尽仍有开放 P0/P1。
6. 四项依据严重冲突且无法保守收敛。
7. 用户中止或改道。

### 12.3 升级包

```text
.mit/escalation/
  REASON.md
  TEST_REPORT.md
  adjudication_signals.json
  evidence/
  prod_test_results.json    # 或 PROD_RESULTS_MISSING.md
  defects_open.json
  env_manifest.json
  next_actions.md           # 建议人工动作 1–5 条
```

---

## 13. 状态机与目录布局

### 13.1 并发与写入

- 仅在目标项目 `.mit/` 读写；**单写者**为 main agent。
- 写 `state.json` 前持 `.mit/.lock`；失败重试 ≤3 次后中止本轮。
- subagent 白名单：`runs/*/captures`、`runs/*/findings/raw`。
- 禁止双会话同时跑同一项目。

### 13.2 目录

```text
.mit/
  profile.json
  matrix.json
  matrix.md
  state.json
  fingerprints.json
  defects/
  artifacts/
    RC-*.meta.json
  runs/
    RC-n/
      captures/ findings/ probes/ logs/
  baselines/
  deliverables/
    TEST_REPORT.md
    RELEASE_DECISION.md
    adjudication_signals.json
    evidence/
    EVIDENCE_INDEX.md
    export.json
  escalation/          # 如触发
  .lock
```

### 13.3 状态字段

| 字段 | 说明 |
|------|------|
| `rc_n`, `rc_sha` | 候选序号与制品哈希 |
| `matrix_rev` | 矩阵版本 |
| `round`, `quiet_streak` | 轮次与过程信号 |
| `open_defects` | P0–P3 聚合 |
| `signals` | 最新裁决信号镜像 |
| `prod_access`, `prod_test_state` | 生产权限与结果状态 |
| `decision` | `in_progress \| allow_release \| deny_release \| escalated` |
| `blinds` | 盲区列表 |

### 13.4 状态迁移

```text
in_progress → allow_release | deny_release | escalated
deny_release → in_progress   （预算内重建 RC 后）
allow_release / escalated    （终态，除非用户显式开启新一轮）
```

---

## 14. 重构映射（MIBG → MIT-Test）

| 源（iterative-bug-hunter） | 目标（multimodal-iterative-testing） | 策略 |
|----------------------------|--------------------------------------|------|
| 名称「迭代抓 BUG」 | 「全模态迭代测试」 | 更名 |
| 三模态 taxonomy | 13 类 surface + 四层（DL/ML/FL/AL） | 扩展 |
| hunt_round 主循环 | RC Loop | 替换 |
| quiet 收敛出口 | Agent 综合裁决三出口 | 替换 |
| Confirmed/Deferred | + P0–P3 | 叠加 |
| fix_gate | Fix Gate + 强制回归 | 加强 |
| web/canvas/axe/layout 探针 | 原样复用 | 复用 |
| ci_gate / baseline_lock | 并入信号源 | 合并 |
| `.bug-hunter/` | `.mit/` | 迁移 |
| REPORT.md | 测试报告 + 证据包 + 裁决信号 + RELEASE_DECISION | 交付物扩展 |
| 无环境/生产协议 | E0–E3 + 脱敏硬门 + E2 协议 | 新增 |
| 布尔门禁放行 | 四项依据综合裁决 + 分层 exposure | 替换 |

兼容：可提供 `migrate_state` 将 `.bug-hunter/state.json` 迁到 `.mit/state.json`；旧 skill 描述指向本 skill。

---

## 15. 目标 Skill 目录结构

```text
multimodal-iterative-testing/
  SKILL.md
  locales/
    zh-CN.json          # displayName: 全模态迭代测试
    en-US.json
  references/
    profile-schema.md
    matrix-rules.md
    modality-code.md
    modality-api.md
    modality-web.md
    modality-mobile.md
    modality-desktop.md
    modality-cli.md
    modality-db.md
    modality-infra.md
    modality-av.md
    modality-canvas.md
    modality-3d.md
    modality-xr.md
    modality-plugin.md
    test-layers.md
    env-layers.md
    prod-test.md
    data-masking.md
    defect-severity.md
    fix-regression.md
    deliverables.md
    adjudication.md
    escalate.md
  scripts/
    profile_scan.py
    matrix_build.py
    env_up.py
    data_mask.py
    device_probe.py
    prod_probe.py
    build_rc.py
    matrix_run.py
    assemble_report.py
    assemble_signals.py
    escalate.py
    migrate_state.py
    # 及自 MIBG 迁入探针
```

**SKILL.md 边界**：只含触发、Scope、主循环步骤、交付物指针、裁决原则、停止/升级条件。阈值与脚本参数进 `references/` 与 `scripts/`。

---

## 16. 实施路线

| 阶段 | 内容 | 退出标准 |
|------|------|----------|
| **P1 骨架** | SKILL 更名、profile/matrix 冻结、`.mit/` 状态 | 矩阵可生成可冻结 |
| **P2 执行** | RC 构建、矩阵执行器、P0–P3、Fix Gate、回归 | 跑通 RC Loop 单轮 |
| **P3 环境** | E1 生产等价、脱敏硬门、E3 设备、E2 只读/合成 | 环境清单与生产缺失声明可用 |
| **P4 交付与裁决** | 测试报告、证据包、裁决信号、综合裁决、升级包 | 三出口演示通过 |
| **P5 验收** | 双 demo（web+api；含设备或媒体/3D） | 第 17 章验收全过 |

---

## 17. 验收标准（DoD）

1. **矩阵**：给定 demo 项目，能生成含 required/optional/n/a 的冻结矩阵，覆盖画像命中模态。
2. **环境**：产出 `env_manifest.json` 与脱敏报告；非法夹具拒绝开跑。
3. **迭代**：人为植入 P0/P1，能分级、修复、补回归，重建 RC 并全量复测。
4. **交付物**：测试报告十节完整；证据包可点开；裁决信号 schema 合法。
5. **裁决**：
   - 无生产结果时不会无条件 Allow；
   - canary 失败时 Deny 或 Escalate；
   - 四项一致且无 P0/P1 时 Allow 并写明理由。
6. **升级**：预算耗尽或脱敏失败路径能生成升级包。
7. **禁止项**：抽查无假 PASS、无热修补测、无未脱敏入包。

---

## 18. 风险与对策

| 风险 | 对策 |
|------|------|
| 模态过多导致预算爆炸 | 影响面必测 + optional 抽样；矩阵冻结避免范围蠕变 |
| 生产环境不可用 | 显式缺失入裁决；条件 Allow（灰度）或 Escalate |
| VLM/主观 oracle 不稳定 | k 次一致率门槛；禁止单独支撑 Allow |
| 证据膨胀/含敏感数据 | 索引化 + 脱敏扫描硬门 + 哈希摘要 |
| RC 轮次互相污染 | `rc_sha` 绑定结果；禁止跨 RC 复用 PASS |
| 与 MIBG 边界模糊 | 触发条件负例写清；视觉-only 场景继续走 MIBG |

---

## 19. 参考与设计依据（摘要）

| 类型 | 来源 | 吸收点 |
|------|------|--------|
| 论文 | arXiv:2501.00217 LLM 测试代理（生成-执行-报告） | 报告与覆盖率指标 |
| 论文 | arXiv:2601.05542 / ACM Test Oracle Automation | 意图 oracle、oracle 质量 |
| 论文 | arXiv:2507.14705 Neo 多智能体测试 | 生成/评估分离 |
| 论文 | IEEE Test-Agent（多模态 App 测试） | 移动多模态代理 |
| 工程 | Google SRE Workbook / Progressive Delivery | Deploy≠Release、canary vs control、error budget |
| 工程 | Microsoft Synthetic Monitoring Playbook | 生产侧合成探测 |
| 工程 | Pact CDC | 契约发布门 |
| 开源 | visual-test-oracle 等 | k 投票、FP/一致性、自愈定位器度量 |
| 实践 | 多模态 D-M-F-D 等 | 数据-模态-融合-决策层级 |
| 内部 | MIBG DESIGN/fix-gate/confirm 协议 | 指纹、确认门、回归门 |

---

## 附录 A. Scope 开跑确认表

| 项 | 默认 | 确认 |
|----|------|------|
| target 项目路径 | 当前工作区 | |
| rc_ref | 用户指定或 HEAD | |
| mode | `test-and-fix` / `test-only` | |
| modalities | profile 推导；用户点名强制 | |
| prod_access | 用户确认 | |
| devices | profile.devices | |
| data 种子 | 脱敏种子 | |
| max_rc_rounds | 5 | |
| max_wall_clock | 4h | |

## 附录 B. 三出口话术模板

**Allow**

> 综合裁决信号、测试报告、证据包与真实生产环境测试结果，RC `<sha>` **可正常发布使用**。  
> 依据摘要：…　附带条件：…　盲区：…

**Deny**

> 综合判断 RC `<sha>` **不可发布**。  
> 阻塞项：…（P0/P1/生产/证据）　建议修复顺序：…

**Escalate**

> 无法自动完成发布裁决，已升级人工。  
> 卡点：…　已覆盖：…　盲区：…　升级包：`.mit/escalation/`

---

**文档结束。** 本文为全模态迭代测试 skill 重构的设计真源；实现按 §15–16 落地，未尽细节以实现期 `references/` 为准，且不得与本文目标、裁决原则与禁止项冲突。
