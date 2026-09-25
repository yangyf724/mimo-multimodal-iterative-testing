# Test Matrix (m2)

- frozen: True
- created: 2026-09-25T03:01:45Z
- counts: {"required": 5, "optional": 0, "n/a": 8}

| modality | mark | evidence floor | status |
|----------|------|----------------|--------|
| code | required | 测试退出码、lint/audit 报告 | pending |
| api | n/a | contract diff、authz 矩阵、黄金响应 | excluded |
| web | required | route×viewport、axe/contrast、visual diff | pending |
| mobile | n/a | 冷启动日志、权限流、设备矩阵 | excluded |
| desktop | n/a | installer verify、update path、签名状态 | excluded |
| cli | n/a | golden exit/stdout/stderr、flag 矩阵 | excluded |
| db | n/a | migrate dry-run、restore smoke | excluded |
| infra | n/a | image scan、readiness、secret hygiene | excluded |
| av | required | 元数据探针、可播冒烟、导出参数 | pending |
| canvas | required | scene 与导出交叉验证 | pending |
| 3d | required | 加载日志、预算计数 | pending |
| xr | n/a | session 日志、帧率采样、sim/real 标注 | excluded |
| plugin | n/a | host-API pin、install/upgrade 流 | excluded |
