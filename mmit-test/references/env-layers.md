# 环境层级 E0–E3

测试环境分层与生产等价要求。环境清单产物：`.mit/env_manifest.json`（由 `scripts/env_up.py` 生成）。所有偏差必须显式声明，禁止静默降级。

## 环境层级总表

| 层级 | 名称 | 用途 | 裁决权重 |
|------|------|------|----------|
| E0 | 本地/CI 隔离沙箱 | 单测、静态、快速反馈 | 辅助 |
| E1 | 生产等价环境 | 主执行面（拓扑/配置/数据形状对齐） | 主证据 |
| E2 | 真实生产环境（授权内） | 只读/影子/金丝雀/合成探测 | **强裁决输入** |
| E3 | 真实或仿真设备 | 移动、桌面、XR 等设备面 | 设备相关模态强依据 |

- E0 结果不得单独支撑 Allow。
- E1 是矩阵执行主面；required 项原则上在 E1（或 E3，设备模态）完成。
- E2 仅在 `prod_access` 授权内进行，见 `prod-test.md`。
- E3 仿真必须标注 `sim`，覆盖率单独统计。

## E1 生产等价要求

| 维度 | 要求 | 允许偏差 |
|------|------|----------|
| 拓扑 | 依赖形状与生产一致 | 须记录 `topology_delta` |
| 配置 | 同一配置模式 | 禁止 dev-only 旁路 |
| 网络 | 出口、TLS、超时重试对齐 | 离线须声明 `network_delta` |
| 版本 | 运行时与制品锁定 | 禁止 `latest` |
| 可观测 | 日志/指标/追踪可导出 | 无则 Blind Spot |

### topology_delta

- 记录 E1 与生产拓扑的**每一处**形状差异（缺失组件、替代组件、单机 vs 集群、托管 vs 自建等）。
- 写入 `env_manifest.json`；并在测试报告「环境与设备」节披露。
- 差异影响关键路径时，相关结论降置信或标盲区；不得假装等价。

### network_delta

- 记录网络面差异：离线、代理、TLS 终结点不同、DNS/出口 IP 不同、超时/重试策略未对齐等。
- 离线或强隔离环境必须声明。
- 与生产探测相关的行为（外呼第三方、CDN）在有 `network_delta` 时结论保守处理。

### 版本锁定

- `runtime` 与制品版本/哈希锁定；镜像用 digest，不用 `latest`。
- 与 `profile.runtime` 一致；漂移记入 `topology_delta` 或单独版本偏差说明。

## E3 设备

- **真机**：记录型号、OS、DPI、区域。
- **仿真**：必须标注 `sim`，覆盖率单独统计。
- **缺设备**：optional + Blind Spot；若阻塞 P0 路径 → Escalate。

## env_manifest.json 建议字段

```json
{
  "e1": {
    "topology": "api+worker+postgres+redis",
    "topology_delta": ["worker=1(prod=3)"],
    "network_delta": ["offline-third-party-mocked"],
    "versions": {"runtime": "node@20.11.0", "image_digest": "sha256:…"},
    "observability": "exportable"
  },
  "e3": [
    {"device": "ios-sim", "os": "17.2", "sim": true},
    {"device": "quest3", "os": "v62", "sim": false}
  ],
  "e2_ref": "prod_access=readonly"
}
```

## 检查清单

- [ ] E1 拓扑/配置/网络/版本/可观测均已核对
- [ ] `topology_delta` / `network_delta` 已记录（无则显式空）
- [ ] 无 `latest` 标签
- [ ] E3 真机/仿真已标注并分开统计
- [ ] 偏差已写入测试报告
