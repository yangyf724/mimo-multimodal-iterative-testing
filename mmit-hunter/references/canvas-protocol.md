# 画布协议（Phase 2）

modality: `canvas`。脚本：`scripts/canvas_probe.py`。

## 统一 item

`state.surfaces.canvas.items[]` 或 CLI `--items`：

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 画布标识 |
| `export_size` | 是 | `WxH` |
| `source` | 建议 | scene JSON 路径 |
| `objects[]` | 规则需要 | `id,type,x,y,w,h,zIndex,opacity,primary?` |
| `assets[]` | 资产规则需要 | `id,display_w/h,pixel_w/h,path?` |
| `spec.safe_inset_pct` | 否 | 默认 5 |
| `spec.export_target` | 否 | 目标导出尺寸 |

三种来源映射到同一结构：`scene-json` 直接读；`html-canvas-app` 由调试接口 dump；`figma-export` 仅接受用户导出。

## 规则

| rule_id | 判定 | 默认 |
|---------|------|------|
| `safe-area-violation` | object bbox 超出 inset 安全区；**全幅背景跳过** | inset 5% |
| `export-mismatch` | `export_size` ≠ target | — |
| `z-order-occlusion` | text/cta 被更高 z 不透明 bbox 覆盖 | coverage ≥ 0.98 |
| `low-res-asset` | max(display/pixel) > 阈值 | 2.0 |
| `aspect-distort` | 显示/像素宽高比偏差 | 2% |
| `hierarchy-flat` | 主 CTA 面积远小于次级 | 仅 Deferred / L2 |

Finding：`modality=canvas`，`location.canvas_id` / `canvas_object_id`。

## CLI

```powershell
canvas_probe.py --items examples/acceptance-demo/canvas --export-target 1080x1920
canvas_probe.py --root <project>   # 读 state.surfaces.canvas
```

无 objects/assets 的 item 记入 `unavailable`，不假装通过。
