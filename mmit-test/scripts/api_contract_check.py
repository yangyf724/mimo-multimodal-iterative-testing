#!/usr/bin/env python3
"""API contract smoke probe for MMIT-Test (M2).

Reads openapi.yaml/openapi.json if present and checks structure;
optionally probes a running base URL for health. Never uses --help as evidence.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def check_contract(root: Path) -> dict[str, Any]:
    findings: list[str] = []
    files = []
    for name in ("openapi.yaml", "openapi.json", "swagger.yaml", "swagger.json"):
        p = root / name
        if p.exists():
            files.append(name)
    if not files and not (root / "proto").is_dir():
        return {
            "ok": False,
            "reason": "no contract source (openapi/proto) found",
            "findings": ["missing-contract"],
        }

    if "openapi.json" in files:
        try:
            data = json.loads((root / "openapi.json").read_text(encoding="utf-8"))
            if not data.get("paths"):
                findings.append("openapi.json has empty paths")
        except (json.JSONDecodeError, OSError) as e:
            findings.append(f"openapi.json unreadable: {e}")
    if "openapi.yaml" in files or "swagger.yaml" in files:
        text = (root / ("openapi.yaml" if "openapi.yaml" in files else "swagger.yaml")).read_text(
            encoding="utf-8", errors="replace"
        )
        if "paths:" not in text and "paths" not in text:
            findings.append("openapi.yaml missing paths")
        if "openapi:" not in text and "swagger:" not in text:
            findings.append("openapi.yaml missing version key")
    return {
        "ok": len(findings) == 0,
        "files": files,
        "findings": findings,
    }


def probe_health(base_url: str | None) -> dict[str, Any]:
    if not base_url:
        return {"skipped": True, "reason": "no --base-url"}
    url = base_url.rstrip("/") + "/api/health"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            body = resp.read(200).decode("utf-8", errors="replace")
            return {"ok": resp.status == 200, "status": resp.status, "body": body[:120]}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"ok": False, "error": str(e)}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="API contract/health probe")
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--base-url", default=None)
    p.add_argument("--json-out", type=Path, default=None)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    contract = check_contract(root)
    health = probe_health(args.base_url)
    report = {"contract": contract, "health": health}
    if args.json_out:
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ok = contract.get("ok", False) and (health.get("skipped") or health.get("ok"))
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
