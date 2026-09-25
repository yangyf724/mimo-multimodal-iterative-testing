# M8 `infra` — 基础设施模态

矩阵编号 **M8**。典型分级 **P0–P1**。层级 **ML**。执行面以 **E1** 为主；只读探测可延伸至 **E2**（授权内）。

## 覆盖范围

- 镜像（构建产物镜像）
- 健康检查（liveness / readiness）
- 配置与密钥
- TLS
- 限额（资源/速率）
- 滚动就绪（rolling update readiness）

拓扑与运行时来自 `profile.topology` / `profile.runtime`。

## Evidence Floor（最低证据）

| 证据 | 说明 |
|------|------|
| image scan | 镜像扫描（漏洞/配置）报告 |
| readiness | 健康检查/就绪探针结果 |
| secret hygiene | 密钥卫生检查（硬编码、权限、轮换痕迹） |

## 典型分级

| 现象 | 分级 |
|------|------|
| 密钥泄露、TLS 失效导致不可用、镜像带高危漏洞可利用 | P0 |
| readiness 失败、配置错误导致主路径不可用、滚动更新中断 | P1 |
| 限额配置偏紧/偏松、非关键探针瑕疵 | P2 |
| 文档/注释问题 | P3 |

## 探针提示

- 镜像：记录 digest（禁止 `latest`）；扫描器与漏洞库版本入证。
- 健康检查：liveness 与 readiness 分开验证；滚动更新中观察就绪门。
- 配置/密钥：禁止 dev-only 旁路；密钥不进日志与证据包（见 `data-masking.md`）。
- TLS：证书链、过期、协议版本；离线环境记 `network_delta`。
- 限额：CPU/内存/速率限制行为可观察；超限表现记入结果。
- 可观测（日志/指标/追踪）不可导出 → Blind Spot。

## 回归固化

来源缺陷面 `infra` → **readiness、secret scan**。

## 禁止

- 未授权对生产做写/压测
- 把密钥或未脱敏配置写入证据
- 用 `latest` 标签掩盖版本漂移
