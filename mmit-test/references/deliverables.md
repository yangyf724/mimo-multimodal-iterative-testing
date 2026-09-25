# 交付物规范

路径根：目标项目 `.mit/deliverables/`。缺件不得进入 Allow。

## 交付物清单

| 交付物 | 路径 | 必要性 |
|--------|------|--------|
| **测试报告** | `.mit/deliverables/TEST_REPORT.md` | 必须 |
| **证据包** | `.mit/deliverables/evidence/` + `EVIDENCE_INDEX.md` | 必须 |
| **裁决信号** | `.mit/deliverables/adjudication_signals.json` | 必须 |
| **发布裁决** | `.mit/deliverables/RELEASE_DECISION.md` | 必须 |
| 机读导出 | `.mit/deliverables/export.json` | 建议 |
| 升级包 | `.mit/escalation/` | 触发升级时必须 |

## TEST_REPORT.md 十节（顺序固定）

1. 执行摘要（项目、RC 哈希、轮次、总体结论草稿）
2. 项目画像与矩阵覆盖（required/optional/n-a 统计）
3. 环境与设备（E0–E3、偏差、sim/real）
4. 分模态测试结果
5. 缺陷清单（P0–P3）与修复/回归
6. **真实生产环境测试结果**（或「缺失」及原因、影响）
7. 盲区与降级（Blind Spots）
8. Known Issues（含用户接受记录）
9. 裁决信号摘要
10. 证据包索引

**质量要求**：每个结论句可追溯到证据 ID；无「大概/应该」式无证据断言。

### 分节要点

- 节 2：给出 `matrix_rev` 与 required/optional/n-a 计数；required 缺失必须显式。
- 节 3：`topology_delta` / `network_delta` / 仿真标注；缺可观测记盲区。
- 节 6：`prod_access=none` 时写「生产结果缺失」+ 原因 + 对裁决影响。
- 节 8：P2 用户接受须有记录；Known Issues 与开放缺陷计数一致。
- 节 10：指向 `EVIDENCE_INDEX.md`，可点开复核。

## 证据包规范

- 与 `rc_sha`、`matrix_rev` **绑定**。
- 含：
  - 矩阵执行记录
  - 关键缺陷复现
  - 修复后回归
  - 生产测试结果**或缺失声明**
  - 环境清单（`env_manifest.json`）
- 路径真实可打开；**禁止未脱敏敏感数据**。
- 证据伪造或不可追溯 → 直接 **Deny 或 Escalate**。

### EVIDENCE_INDEX.md

- 每条证据：证据 ID、类型、关联 check_id/缺陷 ID、文件路径、哈希（建议）。
- 支撑 TEST_REPORT 结论句的证据 ID 引用。

## 裁决信号与发布裁决

- `adjudication_signals.json`：结构化质量信号（模式见 `adjudication.md`）。
- `RELEASE_DECISION.md`：结论、四项依据摘要、冲突点、附带条件、RC 哈希、agent 置信说明（高/中/低及原因）。
- 二者由 Assemble（B7）生成；生产结果（B8）可在裁决前补入。

## 检查清单

- [ ] TEST_REPORT 十节顺序完整
- [ ] 结论句均有证据 ID
- [ ] 证据包与 rc_sha / matrix_rev 绑定且可打开
- [ ] 无未脱敏数据
- [ ] 裁决信号与报告指标一致
- [ ] 生产结果已写入或显式声明缺失
