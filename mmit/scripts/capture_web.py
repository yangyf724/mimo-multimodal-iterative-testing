#!/usr/bin/env python3
"""Multi-viewport web capture for mmit (Phase 1).

Browser backends (in order):
1. Python playwright package
2. Node + playwright module via a temp runner
3. Unavailable -> exit 3 with MANIFEST backend=unavailable

Pure helpers (matrix, slug, manifest, normalize) are unit-testable without a browser.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_CAPTURE_FAIL = 1
EXIT_USAGE = 2
EXIT_NO_BROWSER = 3

INTERACTIVE_SELECTORS = (
    "a[href]",
    "button",
    "input:not([type=hidden])",
    "select",
    "textarea",
    "[role=button]",
    "[role=link]",
    "[onclick]",
    # Note: [data-testid] is NOT interactive — it is often a container marker.
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def route_slug(route: str) -> str:
    text = (route or "root").strip() or "root"
    text = text.strip("/")
    if not text:
        return "home"
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "home"


def parse_viewport(label: str) -> tuple[int, int]:
    text = (label or "").strip().lower().replace(" ", "").replace("*", "x").replace("×", "x")
    m = re.match(r"^(\d+)x(\d+)$", text)
    if not m:
        raise ValueError(f"invalid viewport {label!r}, expected WIDTHxHEIGHT")
    return int(m.group(1)), int(m.group(2))


def expand_matrix(routes: list[str], viewports: list[str]) -> list[dict[str, str]]:
    cells: list[dict[str, str]] = []
    for route in routes:
        for vp in viewports:
            w, h = parse_viewport(vp)
            slug = route_slug(route)
            cells.append(
                {
                    "route": route if route.startswith("/") else f"/{route}",
                    "viewport": f"{w}x{h}",
                    "slug": slug,
                    "stem": f"{slug}__{w}x{h}",
                }
            )
    return cells


def normalize_element(raw: dict[str, Any], *, route: str, viewport: str) -> dict[str, Any]:
    bbox = raw.get("bbox") or {}
    computed = raw.get("computed") or {}
    return {
        "selector": raw.get("selector") or raw.get("tag") or "unknown",
        "tag": raw.get("tag") or "",
        "route": route,
        "viewport": viewport,
        "interactive": bool(raw.get("interactive")),
        "bbox": {
            "x": float(bbox.get("x") or 0),
            "y": float(bbox.get("y") or 0),
            "w": float(bbox.get("w") or 0),
            "h": float(bbox.get("h") or 0),
        },
        "scrollWidth": raw.get("scrollWidth"),
        "clientWidth": raw.get("clientWidth"),
        "text_overflow": raw.get("text_overflow") or "visible",
        "computed": computed,
        "text": raw.get("text") or "",
        "depth": int(raw.get("depth") or 0),
        "inViewport": bool(raw.get("inViewport", True)),
        "href": raw.get("href"),
        "role": raw.get("role"),
        "type": raw.get("type"),
        "attrs": raw.get("attrs") or {},
    }


def default_manifest(
    *,
    base_url: str,
    routes: list[str],
    viewports: list[str],
    backend: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "version": 1,
        "base_url": base_url,
        "routes": routes,
        "viewports": viewports,
        "backend": backend,
        "items": items,
        "captured_at": utc_now(),
    }


def parse_shard(spec: str | None) -> tuple[int, int] | None:
    """Parse 'i/n' shard spec. Returns (index, total) 0-based or None."""
    if not spec:
        return None
    text = str(spec).strip()
    if "/" not in text:
        raise ValueError(f"invalid shard {spec!r}, expected INDEX/TOTAL e.g. 0/2")
    left, _, right = text.partition("/")
    try:
        index = int(left)
        total = int(right)
    except ValueError as e:
        raise ValueError(f"invalid shard {spec!r}, expected INDEX/TOTAL e.g. 0/2") from e
    if total <= 0 or index < 0 or index >= total:
        raise ValueError(f"shard index out of range: {spec!r}")
    return index, total


def assign_shard_cells(
    cells: list[dict[str, str]],
    index: int,
    total: int,
) -> list[dict[str, str]]:
    """Deterministic round-robin assignment of matrix cells to a shard."""
    if total <= 1:
        return list(cells)
    return [cell for i, cell in enumerate(cells) if i % total == index]


def shard_dir_name(index: int) -> str:
    return f"shard-{index}"


def merge_shard_manifests(
    captures_dir: Path,
    *,
    out_name: str = "MANIFEST.json",
) -> dict[str, Any]:
    """Merge MANIFEST.shard-*.json under captures_dir into a root MANIFEST.json.

    Copies referenced artifact files from shard-* subdirs into captures_dir.
    Prefers status=ok; on conflict keeps the item whose elements file mtime is newer.
    Does not touch state.json / fingerprints.json.
    """
    shard_paths = sorted(captures_dir.glob("MANIFEST.shard-*.json"))
    if not shard_paths:
        # also accept shard-*/MANIFEST.shard-*.json layout
        shard_paths = sorted(captures_dir.glob("shard-*/MANIFEST.shard-*.json"))
    if not shard_paths:
        manifest = default_manifest(
            base_url="",
            routes=[],
            viewports=[],
            backend="unavailable",
            items=[],
        )
        manifest["error"] = "no shard manifests found"
        write_manifest(captures_dir / out_name, manifest)
        return {"ok": False, "manifest": manifest, "merged_from": []}

    merged_from: list[str] = []
    by_cell: dict[tuple[str, str], dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []
    base_url = ""
    routes: list[str] = []
    viewports: list[str] = []
    backends: list[str] = []

    def artifact_mtime(shard_root: Path, item: dict[str, Any]) -> float:
        rel = item.get("elements_json")
        if not rel:
            return 0.0
        path = shard_root / str(rel)
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    for sp in shard_paths:
        try:
            with sp.open("r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except Exception:
            continue
        try:
            rel_name = str(sp.relative_to(captures_dir))
        except ValueError:
            rel_name = sp.name
        merged_from.append(rel_name)
        base_url = base_url or data.get("base_url") or ""
        for r in data.get("routes") or []:
            if r not in routes:
                routes.append(r)
        for v in data.get("viewports") or []:
            if v not in viewports:
                viewports.append(v)
        if data.get("backend"):
            backends.append(str(data.get("backend")))
        shard_root = sp.parent
        # If manifest lives at shard-X/MANIFEST.shard-Y.json, artifacts are in that dir
        for item in data.get("items") or []:
            key = (str(item.get("route")), str(item.get("viewport")))
            existing = by_cell.get(key)
            new_item = dict(item)
            new_item["shard"] = shard_root.name if shard_root.name.startswith("shard-") else sp.stem
            # Rewrite artifact paths to shard-relative for copy step
            new_item["_shard_root"] = str(shard_root)
            new_item["_mtime"] = artifact_mtime(shard_root, item)
            if existing is None:
                by_cell[key] = new_item
                continue
            # Prefer ok over non-ok; then newer mtime
            existing_ok = existing.get("status") == "ok"
            new_ok = new_item.get("status") == "ok"
            prefer_new = False
            if new_ok and not existing_ok:
                prefer_new = True
            elif new_ok == existing_ok and new_item.get("_mtime", 0) > existing.get("_mtime", 0):
                prefer_new = True
            if prefer_new:
                conflicts.append(
                    {
                        "route": key[0],
                        "viewport": key[1],
                        "kept": new_item.get("shard"),
                        "dropped": existing.get("shard"),
                    }
                )
                by_cell[key] = new_item
            else:
                conflicts.append(
                    {
                        "route": key[0],
                        "viewport": key[1],
                        "kept": existing.get("shard"),
                        "dropped": new_item.get("shard"),
                    }
                )

    items: list[dict[str, Any]] = []
    for key in sorted(by_cell.keys(), key=lambda k: (k[0] or "", k[1] or "")):
        item = by_cell[key]
        shard_root = Path(item.pop("_shard_root", str(captures_dir)))
        item.pop("_mtime", None)
        # Copy artifacts into captures root (Windows-friendly; no symlink requirement)
        for field in ("viewport_png", "full_png", "elements_json", "console_json", "ax_json"):
            rel = item.get(field)
            if not rel:
                continue
            src = shard_root / str(rel)
            if not src.exists():
                item[field] = None
                continue
            dest = captures_dir / str(rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if src.resolve() != dest.resolve():
                import shutil

                shutil.copy2(src, dest)
        items.append(item)

    backend = "unavailable"
    for b in backends:
        if b and b != "unavailable":
            backend = b
            break
    if backends and all(b == "unavailable" for b in backends):
        backend = "unavailable"

    manifest = default_manifest(
        base_url=base_url,
        routes=routes,
        viewports=viewports,
        backend=backend,
        items=items,
    )
    manifest["merged_from"] = merged_from
    if conflicts:
        manifest["conflicts"] = conflicts
    write_manifest(captures_dir / out_name, manifest)
    return {
        "ok": backend != "unavailable" and any(i.get("status") == "ok" for i in items),
        "backend": backend,
        "items": items,
        "merged_from": merged_from,
        "conflicts": conflicts,
        "manifest": manifest,
    }


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def detect_backend() -> str:
    try:
        import playwright.sync_api  # noqa: F401

        return "python-playwright"
    except Exception:
        pass
    node = shutil.which("node")
    if not node:
        return "unavailable"
    try:
        probe = subprocess.run(
            [node, "-e", "require('playwright'); console.log('ok')"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if probe.returncode == 0 and "ok" in (probe.stdout or ""):
            return "node-playwright"
    except Exception:
        return "unavailable"
    return "unavailable"


NODE_RUNNER = r"""
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

async function main() {
  const cfg = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    reducedMotion: 'reduce',
    viewport: { width: cfg.width, height: cfg.height },
  });
  const page = await context.newPage();
  const consoleMsgs = [];
  page.on('console', (msg) => {
    const type = msg.type();
    if (type === 'error' || type === 'warning') {
      consoleMsgs.push({ type, text: msg.text() });
    }
  });
  await page.goto(cfg.url, { waitUntil: 'networkidle', timeout: cfg.timeout_ms });
  const data = await page.evaluate((selectors) => {
    const isInteractive = (el) => {
      if (!el || el.nodeType !== 1) return false;
      const tag = el.tagName.toLowerCase();
      if (tag === 'a') return !!el.getAttribute('href');
      if (['button', 'select', 'textarea'].includes(tag)) return true;
      if (tag === 'input' && el.type !== 'hidden') return true;
      if (el.getAttribute('role') === 'button' || el.getAttribute('role') === 'link') return true;
      if (el.hasAttribute('onclick')) return true;
      return false;
    };
    const cssColor = (value) => value;
    const depthOf = (el) => {
      let d = 0;
      let n = el;
      while (n && n.parentElement) { d += 1; n = n.parentElement; }
      return d;
    };
    const all = Array.from(document.querySelectorAll('body, body *')).slice(0, 800);
    const elements = [];
    // document root
    const de = document.documentElement;
    elements.push({
      selector: 'html',
      tag: 'html',
      interactive: false,
      bbox: { x: 0, y: 0, w: de.clientWidth, h: de.clientHeight },
      scrollWidth: de.scrollWidth,
      clientWidth: de.clientWidth,
      text_overflow: 'visible',
      computed: {},
      text: '',
      depth: 0,
      inViewport: true,
    });
    for (const el of all) {
      const rect = el.getBoundingClientRect();
      const cs = window.getComputedStyle(el);
      const selector = el.id
        ? `#${el.id}`
        : (el.getAttribute('data-testid')
            ? `[data-testid=${el.getAttribute('data-testid')}]`
            : el.tagName.toLowerCase() + (el.className && typeof el.className === 'string'
                ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.')
                : ''));
      elements.push({
        selector,
        tag: el.tagName.toLowerCase(),
        interactive: isInteractive(el),
        bbox: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
        scrollWidth: el.scrollWidth,
        clientWidth: el.clientWidth,
        text_overflow: cs.textOverflow,
        computed: {
          color: cssColor(cs.color),
          backgroundColor: cssColor(cs.backgroundColor),
          fontSize: cs.fontSize,
          lineHeight: cs.lineHeight,
          fontWeight: cs.fontWeight,
          overflowX: cs.overflowX,
          textOverflow: cs.textOverflow,
          cursor: cs.cursor,
        },
        text: (el.innerText || el.textContent || '').trim().slice(0, 200),
        depth: depthOf(el),
        inViewport: rect.bottom > 0 && rect.top < window.innerHeight && rect.right > 0 && rect.left < window.innerWidth,
        href: el.getAttribute('href'),
        role: el.getAttribute('role'),
        type: el.getAttribute('type'),
        attrs: {
          'data-testid': el.getAttribute('data-testid'),
          'data-list-empty': el.getAttribute('data-list-empty'),
          'data-empty-state': el.getAttribute('data-empty-state'),
          'data-feedback': el.getAttribute('data-feedback'),
        },
      });
    }
    let ax = null;
    try {
      // Playwright AX is not available from page.evaluate; leave placeholder.
      ax = null;
    } catch (e) {}
    return { elements, title: document.title, url: location.href };
  }, cfg.selectors);
  await page.screenshot({ path: cfg.viewport_png, fullPage: false });
  try {
    await page.screenshot({ path: cfg.full_png, fullPage: true });
  } catch (e) {}
  fs.writeFileSync(cfg.elements_path, JSON.stringify({
    route: cfg.route,
    viewport: cfg.viewport,
    width: cfg.width,
    height: cfg.height,
    url: data.url,
    title: data.title,
    elements: data.elements,
  }, null, 2));
  fs.writeFileSync(cfg.console_path, JSON.stringify({ messages: consoleMsgs }, null, 2));
  await context.close();
  await browser.close();
}

main().catch((err) => {
  console.error(String(err && err.stack || err));
  process.exit(1);
});
"""


def capture_with_python_playwright(
    *,
    base_url: str,
    cells: list[dict[str, str]],
    out_dir: Path,
    timeout_ms: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from playwright.sync_api import sync_playwright

    items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for cell in cells:
                w, h = parse_viewport(cell["viewport"])
                context = browser.new_context(
                    reduced_motion="reduce",
                    viewport={"width": w, "height": h},
                )
                page = context.new_page()
                console_msgs: list[dict[str, str]] = []
                page.on(
                    "console",
                    lambda msg: console_msgs.append({"type": msg.type, "text": msg.text})
                    if msg.type in ("error", "warning")
                    else None,
                )
                url = base_url.rstrip("/") + cell["route"]
                stem = cell["stem"]
                viewport_png = out_dir / f"{stem}__viewport.png"
                full_png = out_dir / f"{stem}__full.png"
                elements_path = out_dir / f"{stem}__elements.json"
                console_path = out_dir / f"{stem}__console.json"
                ax_path = out_dir / f"{stem}__ax.json"
                status = "ok"
                error = None
                try:
                    page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                    raw_elements = page.evaluate(
                        """(selectors) => {
                          const isInteractive = (el) => {
                            if (!el || el.nodeType !== 1) return false;
                            const tag = el.tagName.toLowerCase();
                            if (['a', 'button', 'select', 'textarea'].includes(tag)) {
                              if (tag === 'a' && !el.getAttribute('href')) return false;
                              return true;
                            }
                            if (tag === 'input' && el.type !== 'hidden') return true;
                            const role = el.getAttribute('role');
                            if (role === 'button' || role === 'link') return true;
                            if (el.hasAttribute('onclick')) return true;
                            return false;
                          };
                          const depthOf = (el) => {
                            let d = 0;
                            let n = el;
                            while (n && n.parentElement) { d += 1; n = n.parentElement; }
                            return d;
                          };
                          const all = Array.from(document.querySelectorAll('body, body *')).slice(0, 800);
                          const elements = [];
                          const de = document.documentElement;
                          elements.push({
                            selector: 'html', tag: 'html', interactive: false,
                            bbox: { x: 0, y: 0, w: de.clientWidth, h: de.clientHeight },
                            scrollWidth: de.scrollWidth, clientWidth: de.clientWidth,
                            text_overflow: 'visible', computed: {}, text: '', depth: 0, inViewport: true,
                          });
                          for (const el of all) {
                            const rect = el.getBoundingClientRect();
                            const cs = window.getComputedStyle(el);
                            const tid = el.getAttribute('data-testid');
                            const cls = (typeof el.className === 'string' && el.className.trim())
                              ? '.' + el.className.trim().split(/\\s+/).slice(0, 2).join('.') : '';
                            const selector = el.id ? ('#' + el.id) : (tid ? `[data-testid=${tid}]` : (el.tagName.toLowerCase() + cls));
                            elements.push({
                              selector, tag: el.tagName.toLowerCase(), interactive: isInteractive(el),
                              bbox: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
                              scrollWidth: el.scrollWidth, clientWidth: el.clientWidth,
                              text_overflow: cs.textOverflow,
                              computed: {
                                color: cs.color, backgroundColor: cs.backgroundColor,
                                fontSize: cs.fontSize, lineHeight: cs.lineHeight, fontWeight: cs.fontWeight,
                                overflowX: cs.overflowX, textOverflow: cs.textOverflow, cursor: cs.cursor,
                              },
                              text: (el.innerText || el.textContent || '').trim().slice(0, 200),
                              depth: depthOf(el),
                              inViewport: rect.bottom > 0 && rect.top < window.innerHeight
                                && rect.right > 0 && rect.left < window.innerWidth,
                            });
                          }
                          return elements;
                        }""",
                        list(INTERACTIVE_SELECTORS),
                    )
                    elements = [
                        normalize_element(e, route=cell["route"], viewport=cell["viewport"])
                        for e in raw_elements
                    ]
                    page.screenshot(path=str(viewport_png), full_page=False)
                    try:
                        page.screenshot(path=str(full_png), full_page=True)
                    except Exception:
                        pass
                    payload = {
                        "route": cell["route"],
                        "viewport": cell["viewport"],
                        "width": w,
                        "height": h,
                        "url": url,
                        "title": page.title(),
                        "elements": elements,
                    }
                    elements_path.write_text(
                        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    console_path.write_text(
                        json.dumps({"messages": console_msgs}, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    try:
                        ax = page.accessibility.snapshot()
                        ax_path.write_text(
                            json.dumps(ax, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8",
                        )
                    except Exception:
                        pass
                except Exception as e:  # noqa: BLE001
                    status = "error"
                    error = str(e)
                    errors.append({"route": cell["route"], "viewport": cell["viewport"], "error": error})
                items.append(
                    {
                        "route": cell["route"],
                        "viewport": cell["viewport"],
                        "stem": stem,
                        "status": status,
                        "error": error,
                        "viewport_png": f"{stem}__viewport.png" if viewport_png.exists() else None,
                        "full_png": f"{stem}__full.png" if full_png.exists() else None,
                        "elements_json": f"{stem}__elements.json" if elements_path.exists() else None,
                        "console_json": f"{stem}__console.json" if console_path.exists() else None,
                        "ax_json": f"{stem}__ax.json" if ax_path.exists() else None,
                    }
                )
                context.close()
        finally:
            browser.close()
    return items, errors


def capture_with_node_playwright(
    *,
    base_url: str,
    cells: list[dict[str, str]],
    out_dir: Path,
    timeout_ms: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("node not found")
    items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="ibh-capture-") as td:
        td_path = Path(td)
        runner = td_path / "runner.js"
        runner.write_text(NODE_RUNNER, encoding="utf-8")
        for cell in cells:
            w, h = parse_viewport(cell["viewport"])
            stem = cell["stem"]
            viewport_png = out_dir / f"{stem}__viewport.png"
            full_png = out_dir / f"{stem}__full.png"
            elements_path = out_dir / f"{stem}__elements.json"
            console_path = out_dir / f"{stem}__console.json"
            url = base_url.rstrip("/") + cell["route"]
            cfg = {
                "url": url,
                "route": cell["route"],
                "viewport": cell["viewport"],
                "width": w,
                "height": h,
                "timeout_ms": timeout_ms,
                "viewport_png": str(viewport_png),
                "full_png": str(full_png),
                "elements_path": str(elements_path),
                "console_path": str(console_path),
                "selectors": list(INTERACTIVE_SELECTORS),
            }
            cfg_path = td_path / f"{stem}.json"
            cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
            status = "ok"
            error = None
            try:
                proc = subprocess.run(
                    [node, str(runner), str(cfg_path)],
                    capture_output=True,
                    text=True,
                    timeout=max(20, timeout_ms // 1000 + 15),
                )
                if proc.returncode != 0:
                    status = "error"
                    error = (proc.stderr or proc.stdout or "node runner failed").strip()
                    errors.append({"route": cell["route"], "viewport": cell["viewport"], "error": error})
                elif elements_path.exists():
                    data = json.loads(elements_path.read_text(encoding="utf-8-sig"))
                    data["elements"] = [
                        normalize_element(e, route=cell["route"], viewport=cell["viewport"])
                        for e in data.get("elements") or []
                    ]
                    elements_path.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
            except Exception as e:  # noqa: BLE001
                status = "error"
                error = str(e)
                errors.append({"route": cell["route"], "viewport": cell["viewport"], "error": error})
            items.append(
                {
                    "route": cell["route"],
                    "viewport": cell["viewport"],
                    "stem": stem,
                    "status": status,
                    "error": error,
                    "viewport_png": f"{stem}__viewport.png" if viewport_png.exists() else None,
                    "full_png": f"{stem}__full.png" if full_png.exists() else None,
                    "elements_json": f"{stem}__elements.json" if elements_path.exists() else None,
                    "console_json": f"{stem}__console.json" if console_path.exists() else None,
                    "ax_json": None,
                }
            )
    return items, errors


def load_state_routes(root: Path) -> dict[str, Any]:
    state_path = root / ".mmit" / "state.json"
    if not state_path.exists():
        return {}
    with state_path.open("r", encoding="utf-8-sig") as f:
        state = json.load(f)
    web = (state.get("surfaces") or {}).get("web") or {}
    return {
        "base_url": web.get("base_url"),
        "routes": web.get("routes") or ["/"],
        "viewports": web.get("viewports") or ["375x812", "1440x900"],
    }


def run_capture(
    *,
    root: Path,
    base_url: str | None,
    routes: list[str] | None,
    viewports: list[str] | None,
    out: Path | None,
    run_id: str,
    timeout_ms: int,
    backend_force: str | None = None,
    shard: str | None = None,
) -> dict[str, Any]:
    from_state = load_state_routes(root)
    base = base_url or from_state.get("base_url") or "http://127.0.0.1:5173"
    route_list = routes or from_state.get("routes") or ["/"]
    vp_list = viewports or from_state.get("viewports") or ["375x812", "1440x900"]
    out_dir = out or (root / ".mmit" / "hunts" / "runs" / run_id / "captures")
    out_dir.mkdir(parents=True, exist_ok=True)
    cells = expand_matrix(route_list, vp_list)
    shard_spec = parse_shard(shard) if shard else None
    if shard_spec:
        s_index, s_total = shard_spec
        cells = assign_shard_cells(cells, s_index, s_total)
        out_dir = out_dir / shard_dir_name(s_index)
        out_dir.mkdir(parents=True, exist_ok=True)
    backend = backend_force or detect_backend()
    manifest_name = f"MANIFEST.shard-{shard_spec[0]}.json" if shard_spec else "MANIFEST.json"

    if backend == "unavailable":
        manifest = default_manifest(
            base_url=base,
            routes=route_list,
            viewports=vp_list,
            backend="unavailable",
            items=[],
        )
        manifest["error"] = (
            "No Playwright backend. Use playwright-mcp per capture-protocol.md, "
            "then run layout_probe/contrast_probe on collected elements.json."
        )
        if shard_spec:
            manifest["shard"] = {"index": shard_spec[0], "total": shard_spec[1], "cells": len(cells)}
        write_manifest(out_dir / manifest_name, manifest)
        return {"ok": False, "exit": EXIT_NO_BROWSER, "backend": "unavailable", "manifest": manifest}

    if backend == "python-playwright":
        items, errors = capture_with_python_playwright(
            base_url=base, cells=cells, out_dir=out_dir, timeout_ms=timeout_ms
        )
    elif backend == "node-playwright":
        items, errors = capture_with_node_playwright(
            base_url=base, cells=cells, out_dir=out_dir, timeout_ms=timeout_ms
        )
    else:
        write_manifest(
            out_dir / manifest_name,
            default_manifest(
                base_url=base,
                routes=route_list,
                viewports=vp_list,
                backend=backend,
                items=[],
            ),
        )
        return {"ok": False, "exit": EXIT_USAGE, "backend": backend, "error": f"unknown backend {backend}"}

    ok = all(i.get("status") == "ok" for i in items) and bool(items)
    manifest = default_manifest(
        base_url=base,
        routes=route_list,
        viewports=vp_list,
        backend=backend,
        items=items,
    )
    if errors:
        manifest["errors"] = errors
    if shard_spec:
        manifest["shard"] = {"index": shard_spec[0], "total": shard_spec[1], "cells": len(cells)}
    write_manifest(out_dir / manifest_name, manifest)
    return {
        "ok": ok,
        "exit": EXIT_OK if ok else EXIT_CAPTURE_FAIL,
        "backend": backend,
        "out": str(out_dir),
        "items": items,
        "errors": errors,
        "shard": manifest.get("shard"),
        "manifest": manifest,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Capture multi-viewport screenshots and elements.json")
    p.add_argument("--root", default=".", help="project root containing .mmit/")
    p.add_argument("--base-url", dest="base_url")
    p.add_argument("--routes", nargs="*")
    p.add_argument("--viewports", nargs="*")
    p.add_argument("--out", help="captures output dir")
    p.add_argument("--run-id", default="run-1")
    p.add_argument("--timeout-ms", type=int, default=20000)
    p.add_argument("--backend", choices=["python-playwright", "node-playwright", "unavailable"])
    p.add_argument(
        "--shard",
        help="optional INDEX/TOTAL (e.g. 0/2) — capture only this matrix shard into shard-I/",
    )
    p.add_argument(
        "command",
        nargs="?",
        default="capture",
        choices=["capture", "merge"],
        help="capture (default) or merge shard manifests",
    )
    p.add_argument("--captures", help="captures dir for merge (default runs/run-id/captures)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()
    if args.command == "merge":
        captures = Path(args.captures).resolve() if args.captures else (
            root / ".mmit" / "hunts" / "runs" / args.run_id / "captures"
        )
        result = merge_shard_manifests(captures)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return EXIT_OK if result.get("ok") else EXIT_CAPTURE_FAIL
    out = Path(args.out).resolve() if args.out else None
    result = run_capture(
        root=root,
        base_url=args.base_url,
        routes=args.routes,
        viewports=args.viewports,
        out=out,
        run_id=args.run_id,
        timeout_ms=args.timeout_ms,
        backend_force=args.backend,
        shard=args.shard,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result.get("exit", EXIT_CAPTURE_FAIL))


if __name__ == "__main__":
    raise SystemExit(main())
