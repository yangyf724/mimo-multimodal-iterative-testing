#!/usr/bin/env python3
"""Discover same-origin routes for mmit (Phase 3)."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

LOCK_RETRY = 3
LOCK_SLEEP_S = 0.05

STATIC_EXT = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico",
    ".css", ".js", ".mjs", ".map", ".woff", ".woff2", ".ttf", ".eot",
    ".mp4", ".webm", ".mp3", ".wav", ".pdf", ".zip",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def acquire_lock(lock_path: Path) -> int:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    last_err: Exception | None = None
    for attempt in range(LOCK_RETRY):
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            stamp = utc_now()
            os.write(fd, f"{os.getpid()}\n{stamp}\n".encode("utf-8"))
            return fd
        except FileExistsError as e:
            last_err = e
            if attempt < LOCK_RETRY - 1:
                time.sleep(LOCK_SLEEP_S * (attempt + 1))
                continue
            raise RuntimeError(f"lock exists: {lock_path}") from e
    raise RuntimeError(f"lock acquire failed: {last_err}")


def release_lock(fd: int, lock_path: Path) -> None:
    try:
        os.close(fd)
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value:
                self.hrefs.append(value)
                return


def _base_parts(base_url: str) -> tuple[str, str, int | None]:
    parsed = urlparse(base_url or "")
    host = (parsed.hostname or "").lower()
    port = parsed.port
    return parsed.scheme or "http", host, port


def is_same_origin(url: str, base_url: str) -> bool:
    if not url or url.startswith("#"):
        return False
    lowered = url.strip().lower()
    if lowered.startswith(("mailto:", "tel:", "javascript:", "data:", "about:")):
        return False
    if "#" in url and url.split("#", 1)[0] == "":
        return False
    abs_url = urljoin(base_url or "http://127.0.0.1/", url)
    parsed = urlparse(abs_url)
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        return False
    _, base_host, base_port = _base_parts(base_url or "http://127.0.0.1/")
    host = (parsed.hostname or "").lower()
    port = parsed.port
    if not base_host:
        # file-style base: accept relative only
        return not parsed.netloc
    if host and host != base_host:
        return False
    if port is not None and base_port is not None and port != base_port:
        return False
    return True


def is_static_resource(path: str) -> bool:
    path_only = path.split("?", 1)[0].split("#", 1)[0].lower()
    return any(path_only.endswith(ext) for ext in STATIC_EXT)


def path_from_url(url: str, base_url: str) -> str | None:
    abs_url = urljoin(base_url or "http://127.0.0.1/", url)
    parsed = urlparse(abs_url)
    path = parsed.path or "/"
    if not path.startswith("/"):
        path = "/" + path
    if is_static_resource(path):
        return None
    if len(path) > 1:
        path = path.rstrip("/") or "/"
    return path


def normalize_route(route: str) -> str:
    text = (route or "").strip()
    if not text:
        return "/"
    if not text.startswith("/") and not text.startswith("http"):
        text = "/" + text
    if text.startswith("http"):
        parsed = urlparse(text)
        text = parsed.path or "/"
    if len(text) > 1:
        text = text.rstrip("/") or "/"
    return text


def extract_links(html: str, base_url: str) -> list[str]:
    parser = _LinkParser()
    try:
        parser.feed(html or "")
    except Exception:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for href in parser.hrefs:
        if not is_same_origin(href, base_url):
            continue
        path = path_from_url(href, base_url)
        if path is None or path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


def parse_sitemap(xml: str, base_url: str) -> list[str]:
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml or "", flags=re.I)
    out: list[str] = []
    seen: set[str] = set()
    for loc in locs:
        loc = loc.strip()
        if not is_same_origin(loc, base_url):
            continue
        path = path_from_url(loc, base_url)
        if path is None or path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


def parse_package_routes(json_text: str) -> list[str]:
    try:
        data = json.loads(json_text or "{}")
    except json.JSONDecodeError:
        return []
    routes = data.get("routes")
    if not isinstance(routes, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in routes:
        if isinstance(item, str) and item.strip():
            route = normalize_route(item)
            if route not in seen:
                seen.add(route)
                out.append(route)
    return out


def filter_same_origin(urls: list[str], base_url: str) -> list[str]:
    out: list[str] = []
    for url in urls:
        if is_same_origin(url, base_url):
            path = path_from_url(url, base_url)
            if path is not None:
                out.append(path)
    return out


def rank_routes(
    entries: list[dict[str, Any]],
    max_routes: int = 12,
) -> list[dict[str, Any]]:
    """Dedupe by route keeping best (lowest) priority; preserve document order within a priority."""
    best: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    seq = 0
    for entry in entries:
        route = normalize_route(str(entry.get("route") or "/"))
        item = dict(entry)
        item["route"] = route
        item["priority"] = int(entry.get("priority", 99))
        item["_seq"] = seq
        seq += 1
        if route not in best:
            best[route] = item
            order.append(route)
            continue
        # Lower priority wins; tie keeps earlier document order (_seq).
        if item["priority"] < best[route]["priority"]:
            item["_seq"] = best[route]["_seq"]
            best[route] = item
    ordered = [best[r] for r in order]
    # Stable: priority first, then original document order — NOT alphabetical.
    ordered.sort(key=lambda x: (x["priority"], x["_seq"]))
    for item in ordered:
        item.pop("_seq", None)
    if max_routes and max_routes > 0:
        ordered = ordered[:max_routes]
    return ordered


def _fetch_text(url: str, timeout: float = 8.0) -> tuple[str | None, str | None]:
    """Return (text, error). Uses urllib only."""
    try:
        from urllib.request import Request, urlopen

        req = Request(url, headers={"User-Agent": "mmit/phase3"})
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - local/dev URLs
            raw = resp.read()
        return raw.decode("utf-8", errors="replace"), None
    except Exception as e:  # noqa: BLE001 - surface any fetch failure
        return None, str(e)


def discover(
    *,
    base_url: str = "",
    seeds: list[str] | None = None,
    package_path: Path | None = None,
    html: str | None = None,
    html_path: Path | None = None,
    from_url: str | None = None,
    sitemap: str | None = None,
    sitemap_path: Path | None = None,
    max_routes: int = 12,
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    sources: dict[str, Any] = {}

    for seed in seeds or []:
        entries.append({"route": normalize_route(seed), "source": "seed", "priority": 0})
    if seeds:
        sources["seed"] = {"ok": True, "count": len(seeds)}

    if package_path and package_path.exists():
        routes = parse_package_routes(package_path.read_text(encoding="utf-8-sig"))
        for r in routes:
            entries.append({"route": r, "source": "package.json", "priority": 1})
        sources["package.json"] = {"ok": True, "count": len(routes), "path": str(package_path)}
    elif package_path:
        sources["package.json"] = {"ok": False, "error": "missing", "path": str(package_path)}

    sitemap_text: str | None = None
    sitemap_src = sitemap
    if sitemap_path and sitemap_path.exists():
        sitemap_text = sitemap_path.read_text(encoding="utf-8-sig")
        sitemap_src = str(sitemap_path)
    elif sitemap:
        if sitemap.startswith("http"):
            sitemap_text, err = _fetch_text(sitemap)
            if err:
                sources["sitemap"] = {"ok": False, "error": err, "url": sitemap}
        else:
            p = Path(sitemap)
            if p.exists():
                sitemap_text = p.read_text(encoding="utf-8-sig")
                sitemap_src = str(p)
    elif base_url:
        candidate = base_url.rstrip("/") + "/sitemap.xml"
        fetched, err = _fetch_text(candidate)
        if fetched and "<loc" in fetched.lower():
            sitemap_text = fetched
            sitemap_src = candidate
        else:
            sources["sitemap"] = {"ok": False, "error": err or "no-locs", "url": candidate}

    if sitemap_text is not None:
        routes = parse_sitemap(sitemap_text, base_url or "http://127.0.0.1/")
        for r in routes:
            entries.append({"route": r, "source": "sitemap", "priority": 2})
        sources["sitemap"] = {"ok": True, "count": len(routes), "from": sitemap_src}

    html_text = html
    html_src = None
    if html_path and html_path.exists():
        html_text = html_path.read_text(encoding="utf-8-sig")
        html_src = str(html_path)
    elif from_url:
        fetched, err = _fetch_text(from_url)
        if err:
            sources["html-links"] = {"ok": False, "error": err, "url": from_url}
        else:
            html_text = fetched
            html_src = from_url

    if html_text is not None and "html-links" not in sources:
        base = base_url or (from_url or "http://127.0.0.1/")
        routes = extract_links(html_text, base)
        for r in routes:
            entries.append({"route": r, "source": "html-links", "priority": 3})
        sources["html-links"] = {"ok": True, "count": len(routes), "from": html_src}

    ranked = rank_routes(entries, max_routes=max_routes)
    return {
        "routes": ranked,
        "sources": sources,
        "max_routes": max_routes,
        "discovered_count": len(ranked),
        "discovered_at": utc_now(),
    }


def write_state_routes(root: Path, result: dict[str, Any]) -> dict[str, Any]:
    state_path = root / ".mmit" / "state.json"
    lock_path = root / ".mmit" / ".lock"
    if not state_path.exists():
        raise FileNotFoundError(f"state.json not found: {state_path}")
    fd = acquire_lock(lock_path)
    try:
        state = load_json(state_path)
        web = state.setdefault("surfaces", {}).setdefault("web", {})
        existing = [normalize_route(r) for r in (web.get("routes") or [])]
        discovered = [r["route"] for r in result.get("routes") or []]
        # preserve existing order, append new
        merged = list(existing)
        for r in discovered:
            if r not in merged:
                merged.append(r)
        max_r = int(
            ((web.get("route_discovery") or {}).get("max_routes"))
            or result.get("max_routes")
            or 12
        )
        if max_r > 0:
            merged = merged[:max_r]
        web["routes"] = merged
        rd = web.setdefault("route_discovery", {})
        rd["enabled"] = True
        rd["max_routes"] = max_r
        rd["last_run"] = {
            "at": result.get("discovered_at"),
            "sources": result.get("sources"),
            "discovered_count": result.get("discovered_count"),
        }
        state["updated_at"] = utc_now()
        save_json(state_path, state)
        return {"routes": merged, "written": True}
    finally:
        release_lock(fd, lock_path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Discover same-origin routes")
    p.add_argument("--root", default=".")
    p.add_argument("--base-url", default="http://127.0.0.1:5173")
    p.add_argument("--seed", nargs="*", default=None, help="seed routes")
    p.add_argument("--package", dest="package", default=None, help="package.json path")
    p.add_argument("--html", default=None, help="HTML file path")
    p.add_argument("--from-url", dest="from_url", default=None, help="fetch HTML from URL")
    p.add_argument("--sitemap", default=None, help="sitemap URL or path")
    p.add_argument("--max-routes", type=int, default=12)
    p.add_argument("--write", action="store_true", help="merge into state.json under lock")
    p.add_argument("--from-state", action="store_true", help="use existing state routes as seed")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()
    seeds = list(args.seed or [])
    package_path = Path(args.package) if args.package else None
    if args.package is None:
        guess = root / "package.json"
        if guess.exists():
            package_path = guess
    if args.from_state:
        state_path = root / ".mmit" / "state.json"
        if state_path.exists():
            state = load_json(state_path)
            web = (state.get("surfaces") or {}).get("web") or {}
            for r in web.get("routes") or []:
                if normalize_route(r) not in [normalize_route(s) for s in seeds]:
                    seeds.append(normalize_route(r))
            if web.get("base_url") and args.base_url == "http://127.0.0.1:5173":
                args.base_url = web["base_url"]

    result = discover(
        base_url=args.base_url,
        seeds=seeds,
        package_path=package_path,
        html_path=Path(args.html) if args.html else None,
        from_url=args.from_url,
        sitemap=args.sitemap,
        max_routes=args.max_routes,
    )
    payload: dict[str, Any] = dict(result)
    if args.write:
        try:
            write_result = write_state_routes(root, result)
            payload["state"] = write_result
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
            return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    sources = result.get("sources") or {}
    any_ok = any(v.get("ok") for v in sources.values() if isinstance(v, dict))
    if not result.get("routes") and not any_ok and not seeds:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
