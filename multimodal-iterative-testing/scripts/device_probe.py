#!/usr/bin/env python3
"""Device coverage probe for MIT-Test (E3)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mit_lib import ensure_mit, read_json, utc_now, write_json  # noqa: E402


def probe_devices(root: Path) -> dict[str, Any]:
    profile_path = ensure_mit(root) / "profile.json"
    profile = read_json(profile_path) if profile_path.exists() else {}
    wanted = profile.get("devices") or ["unknown"]
    entries = []
    covered = 0
    for d in wanted:
        # Local workspace cannot claim real hardware or even simulators — only "declared".
        available = False
        is_real = False
        if d != "unknown":
            covered += 0  # honest coverage: 0 until a real/sim probe is attached
        entries.append(
            {
                "device": d,
                "kind": "missing" if d == "unknown" else "declared",
                "real": is_real,
                "available": available,
                "notes": "no device probe attached; coverage counts only verified devices",
            }
        )
    total = max(len(wanted), 1)
    return {
        "scanned_at": utc_now(),
        "devices": entries,
        "coverage": round(covered / total, 3),
        "all_sim": True,
        "verified": False,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Device probe (E3) for MIT-Test")
    p.add_argument("--root", type=Path, default=Path.cwd())
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    report = probe_devices(root)
    out = ensure_mit(root) / "device_probe.json"
    write_json(out, report)
    print(f"device_probe written: {out} coverage={report['coverage']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
