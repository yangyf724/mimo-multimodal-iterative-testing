# Route Discovery

`scripts/discover_routes.py` fills `state.surfaces.web.routes` from multiple sources.

## Sources (priority)

| Source | Priority | Notes |
|--------|----------|-------|
| seed (`--seed` / existing state) | 0 | always kept |
| package.json `routes` | 1 | convention field |
| sitemap.xml `<loc>` | 2 | same-origin only |
| HTML `<a href>` | 3 | document order |

Static assets, `mailto:`, `javascript:`, hash-only, and cross-origin links are ignored.

## CLI

```bash
python scripts/discover_routes.py --root . --base-url http://127.0.0.1:5174 \
  --seed / --from-url http://127.0.0.1:5174/ --max-routes 12 --write
```

- Without `--write`: stdout JSON only (dry-run / tests).
- With `--write`: merge under `.mmit/.lock` into `state.surfaces.web.routes`.
- Exit `2` only when every source failed and there is no seed.

## State

```json
"route_discovery": {
  "enabled": true,
  "max_routes": 12,
  "sources": ["seed", "package.json", "sitemap", "html-links"],
  "last_run": {"at": "...", "sources": {}, "discovered_count": 0}
}
```
