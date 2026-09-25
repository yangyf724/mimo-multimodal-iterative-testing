# VLM 双视角审计（Phase 2）

脚本：`scripts/vlm_audit.py`。**不调用模型**——只规定协议、合并共识、与机器 finding 交叉。

## 协议

1. 对同一截图独立产出两份 JSON：
   - 视角 A：布局 / 层级 / 裁切 / 重叠
   - 视角 B：空状态 / 错误反馈 / 可点性 / 死路
2. 候选字段：`title`, `problem`, `location{route,viewport,selector|bbox}`, `confidence`。
3. **两视角都点名同一问题**（selector 相同或 bbox IoU>0.3 或标题近似 + 同 route）→ consensus。
4. 与 `findings/raw/**` 交叉：同 selector / bbox 重合 → 写入机器 finding 的 `metrics.vlm_corroboration`，**不重复计数**。
5. 纯审美、无机器支撑 → standalone candidate；`allow_subjective=false` 时不得 Confirmed。
6. 每条候选 `inferred_oracle: true`。

## CLI

```powershell
# 生成空模板供 agent 填写
vlm_audit.py scaffold --screenshot runs/run-N/captures/home__375x812__viewport.png `
  --route / --viewport 375x812 --out-a view-a.json --out-b view-b.json

# 合并
vlm_audit.py merge --view-a view-a.json --view-b view-b.json `
  --raw-dir runs/run-N/findings/raw --out runs/run-N/findings/vlm/consensus.json
```

## 确认门槛

- consensus 仅 Candidate（evidence L2）。
- 要 Confirmed 仍须 L3 机器证据或用户 L4 规范（见 confirm-protocol）。
- METRICS：VLM 候选→Confirmed 目标 10%–30%。
