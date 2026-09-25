# 测试矩阵规则 Matrix Rules

矩阵 = 「模态 × 检查项 × 证据要求」冻结表。产物：`.mmit/matrix.json` + `.mmit/matrix.md`。由 `scripts/matrix_build.py --freeze` 生成。

## 矩阵公式

```text
Matrix = (Profile 命中模态 ∩ 发布必测底线) ∪ 用户点名模态
```

- **Profile 命中**：画像线索映射到的 modality。
- **发布必测底线**：安全/发布相关必测项；与命中求交，避免全开。
- **用户点名**：强制加入，即使 profile 未命中。
- 设计原则：**不全开不漏列**——命中即列；未命中也要以 `n/a` 显式记录。

## 生成步骤 S1–S3

| 步骤 | 名称 | 输入 | 输出 | 规则 |
|------|------|------|------|------|
| S1 | Profile Scan | 仓库、清单、CI、README、媒体目录 | `profile.json` | 静默完成；缺字段用 `unknown`，不得臆造 |
| S2 | Surface Map | profile | 模态命中表 | 线索 → surface → modality 映射 |
| S3 | Matrix Freeze | 模态命中 + 用户点名 | `matrix.json` / `matrix.md` | 写入 `matrix_rev`；**未冻结不得开跑** |

### 矩阵变更

- 任何变更必须 **bump `matrix_rev`** 并记录原因。
- 变更后应对**当前 RC** 重跑受影响的 `required` 项。
- 范围蠕变靠冻结约束；新增模态走变更流程，不得静默扩表。

## 标注：required / optional / n-a

| 标注 | 含义 | 执行要求 | 裁决影响 |
|------|------|----------|----------|
| `required` | 安全底线或用户点名 | 必须执行并留证 | 缺失或失败强烈倾向 Deny |
| `optional` | 可降级/替代证据 | 执行或降级 | 降级必须记 Blind Spot |
| `n/a` | 画像未命中 | 保留排除记录 | 证明「考虑过」 |

- `required` 无证据 = 覆盖缺失，禁止假 PASS。
- `optional` 降级（如仅仿真、仅静态）→ 必须写入 Blind Spots。
- `n/a` 仅当画像线索**证明未命中**；`unknown` 线索不得标 `n/a`。

## 全模态目录（13 类 Surface）

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

各模态细规格见 `modality-*.md`。Evidence Floor 是**最低**证据，不足则不得判 PASS。

## 矩阵行建议字段

```json
{
  "modality": "api",
  "check_id": "M2-authz",
  "label": "鉴权矩阵",
  "mark": "required",
  "evidence_floor": ["authz_matrix"],
  "layer": "ML",
  "notes": ""
}
```

- `check_id` 稳定，供证据索引与回归对齐。
- `layer` 取 DL/ML/FL/AL（见 `test-layers.md`），与模态正交。
- 用户点名项 `mark` 至少为 `required`。

## 执行与证据绑定

1. 执行范围：全部 `required` + 已启用 `optional`。
2. 结果绑定当前 `rc_sha` 与 `matrix_rev`；禁止跨 RC 复用 PASS。
3. 探针失败 → Blind Spot，禁止静默跳过或假 PASS。
4. 每个 PASS 须有满足 Evidence Floor 的机读/多媒体证据。

## 冻结检查清单

- [ ] `matrix_rev` 已写入并冻结
- [ ] 命中模态全覆盖；未命中均有 `n/a` 记录
- [ ] 用户点名项已强制纳入
- [ ] 每行有 Evidence Floor 与标注
- [ ] `unknown` 画像字段未误标为 `n/a`
