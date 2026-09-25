# ux-flow（Phase 2）

modality: `web-visual`。脚本：`scripts/ux_flow.py`。

## 静态规则

| rule_id | 判定 | 备注 |
|---------|------|------|
| `dead-link` | `a[href]` ∈ {``, `#`, `javascript:void(0)`} | 需 capture 写入 `href` |
| `missing-feedback` | 存在显式 submit（`type=submit` / testid 含 submit），同路由无 alert/error/toast 反馈节点 | `inferred_oracle: true` |
| `missing-empty-state` | 容器 `data-list-empty=expected` 且无 `data-empty-state` 占位 | 启发式 |

## 符号化 flow（WebTestPilot 风格）

Flow 文件（运行时默认 `.bug-hunter/flows/*.json`；验收 demo 固定在 `examples/acceptance-demo/flows/`，避免被 `.bug-hunter/` ignore 掉）：

```json
{
  "id": "home-submit-empty",
  "route": "/",
  "viewport": "375x812",
  "symbols": {"formValid": false},
  "steps": [{
    "action": "click",
    "target": "[data-testid=flow-submit]",
    "pre": {"formValid": false, "[data-testid=flow-submit].visible": true},
    "post": {"[data-testid=flow-error].visible": true}
  }],
  "inferred_oracle": true
}
```

- `pre`/`post` 条件：`symbol` 布尔、`selector.visible`、`selector.exists`、`text_contains(sel, "…")`。
- 条件无法判定 → step `unavailable`，**不得**计 quiet 成功。
- 失败 step → finding `ux-flow-step` / `ui-ux-flow` / L3 + `inferred_oracle`。

## CLI

```powershell
# 静态 + flows，基于 MANIFEST
ux_flow.py --manifest runs/run-N/captures/MANIFEST.json --flows .bug-hunter/flows --out findings.json

# 单 elements + 单 flow
ux_flow.py --elements cell__elements.json --flow empty-submit.json
```

`hunt_round.py` 在 MANIFEST 可用时自动跑静态规则；`--flows DIR` 启用符号化。
