# 采集协议（Capture Protocol）— Phase 2

1. **环境**：优先 `scripts/capture_web.py`（Playwright Python 或 Node）；不可用时用 playwright-mcp 按本协议手工采集，再跑 probes。
2. **路由集**：`state.surfaces.web.routes`；可用 [`route-discovery.md`](route-discovery.md) 的 `discover_routes.py` 从 package.json / sitemap / HTML 链接自动补全，设上限。
3. **Viewport 矩阵**：至少 `375x812`、`1440x900`。
4. **每页产物**（写入 `runs/run-N/captures/`）：

```
{route_slug}__{WxH}__viewport.png
{route_slug}__{WxH}__full.png          # 可选
{route_slug}__{WxH}__elements.json
{route_slug}__{WxH}__ax.json           # 可选
{route_slug}__{WxH}__console.json
MANIFEST.json
```

5. **稳定化**：network idle；`prefers-reduced-motion: reduce` 禁动画。
6. **认证**：storage_state；未授权页跳过并记 Blind Spots。
7. **MANIFEST**：`base_url`, `routes`, `viewports`, `backend`, `items[]`（route/viewport/stem/status/相对路径）, `captured_at`。
8. **Phase 2 扩展**：elements 含 `href` / `role` / `type` / `attrs`（供 ux-flow）；支持 `--shard i/n` 分片与 `merge` 汇总（见 [`subagent-capture.md`](subagent-capture.md)）。

## 脚本入口

```powershell
# 从 state.json 读 routes/viewports/base_url
& $env:MIMO_PYTHON mmit-hunter/scripts/capture_web.py --root <project> --run-id run-1

# 或显式指定
& $env:MIMO_PYTHON mmit-hunter/scripts/capture_web.py --root <project> `
  --base-url http://127.0.0.1:5173 --routes / /about --viewports 375x812 1440x900

# Phase 2：分片 + 汇总
& $env:MIMO_PYTHON mmit-hunter/scripts/capture_web.py --root <project> --run-id run-1 --shard 0/2
& $env:MIMO_PYTHON mmit-hunter/scripts/capture_web.py merge --root <project> --run-id run-1
```

退出码：`0` 全部成功 · `1` 部分失败 · `2` 参数错误 · `3` 无 Playwright backend（MANIFEST `backend=unavailable`）。

## elements.json schema（供 layout / contrast / responsive）

每项必填：

```json
{
  "selector": "[data-testid=primary-cta]",
  "tag": "button",
  "route": "/",
  "viewport": "375x812",
  "interactive": true,
  "bbox": {"x": 0, "y": 0, "w": 12, "h": 12},
  "scrollWidth": 0,
  "clientWidth": 0,
  "text_overflow": "visible",
  "computed": {
    "color": "rgb(15, 23, 42)",
    "backgroundColor": "rgb(255, 255, 255)",
    "fontSize": "16px",
    "lineHeight": "24px",
    "fontWeight": "400",
    "overflowX": "visible",
    "textOverflow": "clip",
    "cursor": "pointer"
  },
  "text": "…",
  "depth": 0,
  "inViewport": true
}
```

document 根：`selector: "html"`，带 `scrollWidth` / `clientWidth`。

## Playwright MCP 手工采集（backend 不可用时）

1. 打开 `base_url + route`，viewport 设为矩阵中一格；
2. 截 viewport 截图，路径按上表命名；
3. `page.evaluate` 抽取 elements（字段同 schema）；
4. 写 `elements.json` 与 `MANIFEST.json`（`backend: "manual-mcp"`）；
5. 再跑 `layout_probe.py` / `contrast_probe.py` 或 `hunt_round.py --skip-capture`。

## 画布（Phase 2 索引）

统一 item：`id`, `export_size`, `source`；可选 `render_png`, `spec.safe_inset_pct`。kind：`scene-json` | `html-canvas-app` | `figma-export`。
