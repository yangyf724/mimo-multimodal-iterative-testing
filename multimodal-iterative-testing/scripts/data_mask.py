#!/usr/bin/env python3
"""Data masking hard gate for MIT-Test. Refuses to run when secrets/PII leak into fixtures."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mit_lib import ensure_mit, utc_now, write_json  # noqa: E402

# Patterns are intentionally conservative (shape-preserving detection, not full DLP).
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("generic_api_key", re.compile(r"(?i)(api[_-]?key|secret|token|passwd|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}['\"]?")),
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
    ("chinese_id", re.compile(r"\b[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b")),
    ("cn_mobile", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("email_literal", re.compile(r"\b[A-Za-z0-9._%+-]+@(?!example\.(?:com|org|net)|test\.(?:com|org)|localhost)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("card_like", re.compile(r"(?<!\d)(?:4\d{3}|5[1-5]\d{2}|3[47]\d{2})[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)")),
]

SCAN_SUFFIXES = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".md", ".yml", ".yaml",
    ".env", ".txt", ".sql", ".csv", ".html", ".css", ".toml", ".ini",
}


def scan_file(path: Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    findings: list[dict[str, Any]] = []
    for name, pattern in SECRET_PATTERNS:
        for m in pattern.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            findings.append(
                {
                    "rule": name,
                    "file": str(path),
                    "line": line,
                    # never store matched secret material — only rule + location
                    "match_length": min(len(m.group(0)), 40),
                    "redacted": True,
                }
            )
    return findings


def scan_tree(root: Path) -> list[dict[str, Any]]:
    exclude = {".git", ".mit", "node_modules", "__pycache__", ".venv", ".playwright-mcp"}
    findings: list[dict[str, Any]] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in exclude for part in rel.parts):
            continue
        if p.suffix.lower() not in SCAN_SUFFIXES and p.name not in {".env", ".env.local"}:
            continue
        findings.extend(scan_file(p))
    return findings


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Masking/secret scan hard gate (fail = refuse to start)")
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--out", type=Path, default=None)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    findings = scan_tree(root)
    report = {
        "scanned_at": utc_now(),
        "root": str(root),
        "clean": len(findings) == 0,
        "count": len(findings),
        "findings": findings,
    }
    out = args.out or (ensure_mit(root) / "data_mask_report.json")
    write_json(out, report)
    if findings:
        print(f"MASK FAIL: {len(findings)} finding(s) -> {out}")
        for f in findings[:10]:
            print(f"  - {f['rule']}: {f['file']}:{f['line']} (redacted)")
        return 1
    print(f"MASK CLEAN -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
