#!/usr/bin/env python3
"""Optional axe-core gate (Phase 3). Never silent-pass when unavailable."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def detect_backend() -> dict[str, Any]:
    """Return {backend, command_prefix} or backend=unavailable."""
    npx = shutil.which("npx")
    node = shutil.which("node")
    local_axe = Path("node_modules") / ".bin" / ("axe.cmd" if os.name == "nt" else "axe")
    if local_axe.exists():
        return {"backend": "local-axe", "command": [str(local_axe)]}
    if npx:
        return {"backend": "npx-axe", "command": [npx, "--yes", "@axe-core/cli"]}
    if node and Path("node_modules", "axe-core").exists():
        return {"backend": "node-axe-core", "command": [node]}
    if node:
        return {"backend": "node-no-axe", "command": None}
    return {"backend": "unavailable", "command": None}


def run_cli_axe(command: list[str], url: str, timeout: int = 60) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            [*command, url, "--stdout"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "violations": []}
    text = (proc.stdout or "").strip()
    # axe CLI may print non-JSON warnings; try to parse last JSON object
    data: dict[str, Any] | None = None
    if text:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # try last {...} block
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    data = json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    data = None
    violations: list[dict[str, Any]] = []
    if isinstance(data, dict):
        raw = data.get("violations") or data.get("issues") or []
        if isinstance(raw, list):
            for v in raw:
                if not isinstance(v, dict):
                    continue
                violations.append(
                    {
                        "id": v.get("id"),
                        "impact": v.get("impact"),
                        "help": v.get("help") or v.get("description"),
                        "nodes": len(v.get("nodes") or []) if isinstance(v.get("nodes"), list) else 0,
                    }
                )
    return {
        "ok": proc.returncode == 0 or bool(data),
        "returncode": proc.returncode,
        "violations": violations,
        "raw_truncated": text[:500] if not data else None,
    }


def run_axe_file_html(node: str, html_path: Path) -> dict[str, Any]:
    """Best-effort offline path: only works if axe-core + jsdom exist locally."""
    script = r"""
const fs = require('fs');
let axe, JSDOM;
try {
  axe = require('axe-core');
  JSDOM = require('jsdom').JSDOM;
} catch (e) {
  console.log(JSON.stringify({status: 'unavailable', error: String(e)}));
  process.exit(0);
}
const html = fs.readFileSync(process.argv[2], 'utf8');
const dom = new JSDOM(html, {url: 'http://127.0.0.1/'});
axe.run(dom.window.document).then((results) => {
  const violations = (results.violations || []).map(v => ({
    id: v.id, impact: v.impact, help: v.help, nodes: (v.nodes||[]).length
  }));
  console.log(JSON.stringify({status: 'ok', violations}));
}).catch((e) => {
  console.log(JSON.stringify({status: 'unavailable', error: String(e)}));
});
"""
    try:
        proc = subprocess.run(
            [node, "-e", script, str(html_path)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        out = (proc.stdout or "").strip()
        data = json.loads(out) if out else {}
        return {
            "backend": "node-jsdom-axe",
            "status": data.get("status", "unavailable"),
            "violations": data.get("violations") or [],
            "error": data.get("error"),
        }
    except Exception as e:  # noqa: BLE001
        return {"backend": "node-jsdom-axe", "status": "unavailable", "violations": [], "error": str(e)}


def run_gate(
    *,
    url: str | None = None,
    routes: list[str] | None = None,
    html_file: Path | None = None,
    out_dir: Path | None = None,
    fail_on_violations: bool = False,
    detector=None,
) -> dict[str, Any]:
    detect = detector or detect_backend
    backend_info = detect()
    backend = backend_info.get("backend")
    base_url = (url or "").rstrip("/")

    report: dict[str, Any] = {
        "backend": backend,
        "status": "unavailable",
        "violations": [],
        "routes": [],
        "checked_at": utc_now(),
        "notes": [],
    }

    if backend in ("unavailable", "node-no-axe") and html_file is None:
        report["notes"].append("axe-core not available; gate cannot run (not a pass)")
        if out_dir:
            save_json(out_dir / "axe-report.json", report)
        return report

    if html_file is not None and backend_info.get("command"):
        node = shutil.which("node")
        if node:
            file_result = run_axe_file_html(node, html_file)
            report.update(
                {
                    "backend": file_result.get("backend") or backend,
                    "status": file_result.get("status"),
                    "violations": file_result.get("violations") or [],
                    "error": file_result.get("error"),
                }
            )
            if out_dir:
                save_json(out_dir / "axe-report.json", report)
            return report

    if not backend_info.get("command") or not base_url:
        report["notes"].append("missing axe CLI or base URL")
        if out_dir:
            save_json(out_dir / "axe-report.json", report)
        return report

    command = list(backend_info["command"])
    all_violations: list[dict[str, Any]] = []
    checked: list[str] = []
    any_ok = False
    for route in routes or ["/"]:
        route = route if route.startswith("/") else "/" + route
        target = base_url + (route if route != "/" else "/")
        result = run_cli_axe(command, target)
        checked.append(route)
        if result.get("ok"):
            any_ok = True
        for v in result.get("violations") or []:
            item = dict(v)
            item["route"] = route
            all_violations.append(item)
        if result.get("error"):
            report["notes"].append(f"{route}: {result['error']}")

    report["routes"] = checked
    report["violations"] = all_violations
    report["status"] = "ok" if any_ok else "unavailable"
    if out_dir:
        save_json(out_dir / "axe-report.json", report)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Optional axe-core gate")
    p.add_argument("--url", default=None)
    p.add_argument("--routes", nargs="*", default=None)
    p.add_argument("--html-file", dest="html_file", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--fail-on", dest="fail_on", default=None, choices=["violations"])
    p.add_argument("--root", default=".")
    p.add_argument("--run-id", default="run-axe")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_dir = Path(args.out) if args.out else (
        Path(args.root).resolve() / ".bug-hunter" / "runs" / args.run_id / "axe"
    )
    report = run_gate(
        url=args.url,
        routes=args.routes,
        html_file=Path(args.html_file) if args.html_file else None,
        out_dir=out_dir,
        fail_on_violations=args.fail_on == "violations",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report.get("status") == "ok" and report.get("violations") and args.fail_on == "violations":
        return 1
    # unavailable is exit 0 so local/CI can continue; report is explicit
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
