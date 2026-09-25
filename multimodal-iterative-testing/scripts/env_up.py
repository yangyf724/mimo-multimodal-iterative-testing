#!/usr/bin/env python3
"""Environment manifest for MIT-Test (E0–E3)."""
from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mit_lib import ensure_mit, read_json, utc_now, write_json  # noqa: E402


def build_env_manifest(root: Path, prod_access: str = "none") -> dict[str, Any]:
    profile_path = ensure_mit(root) / "profile.json"
    profile = read_json(profile_path) if profile_path.exists() else {}
    runtime = profile.get("runtime", "unknown")
    return {
        "version": 1,
        "created_at": utc_now(),
        "root": str(root.resolve()),
        "host": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "layers": {
            "E0": {"name": "local-sandbox", "available": True, "notes": "default execution"},
            "E1": {
                "name": "prod-equivalent",
                "available": False,
                "topology": profile.get("topology", "unknown"),
                "topology_delta": "unverified",
                "network_delta": "unverified",
                "notes": "E1 equivalence not verified in this workspace; do not treat as production-equivalent without §7.2 checks",
            },
            "E2": {
                "name": "real-production",
                "available": prod_access != "none",
                "prod_access": prod_access,
                "notes": "prod test authorized" if prod_access != "none" else "no prod access — results must be declared missing",
            },
            "E3": {
                "name": "devices",
                "available": bool(profile.get("devices") and profile.get("devices") != ["unknown"]),
                "devices": profile.get("devices", ["unknown"]),
                "notes": "sim must be labeled; missing device => blind spot",
            },
        },
        "runtime_locked": runtime,
        "dev_only_bypass": False,
        "observability_exportable": False,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Write env_manifest.json for MIT-Test")
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--prod-access", default=None)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    prod_access = args.prod_access
    if prod_access is None:
        state_path = ensure_mit(root) / "state.json"
        prod_access = "none"
        if state_path.exists():
            prod_access = read_json(state_path).get("prod_access", "none")
    manifest = build_env_manifest(root, prod_access=prod_access)
    out = ensure_mit(root) / "env_manifest.json"
    write_json(out, manifest)
    print(f"env_manifest written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
