#!/usr/bin/env python3
"""Validate REPORT.md contains required Phase 0 sections."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REQUIRED_PATTERNS = [
    (r"(?i)^#{1,3}\s*.*范围|Scope", "范围/Scope"),
    (r"(?i)^#{1,3}\s*.*执行摘要|Summary|摘要", "执行摘要"),
    (r"(?i)^#{1,3}\s*.*确认|Confirmed", "确认清单"),
    (r"(?i)^#{1,3}\s*.*盲区|Blind\s*Spots", "Blind Spots"),
    (r"(?i)modality", "modality 摘要"),
    (r"rule_id|rule-id|规则", "rule_id"),
]


def validate_report(text: str) -> list[str]:
    missing = []
    for pattern, label in REQUIRED_PATTERNS:
        if not re.search(pattern, text, flags=re.MULTILINE):
            missing.append(label)
    return missing


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Validate REPORT.md sections")
    p.add_argument("report", help="path to REPORT.md")
    args = p.parse_args(argv)
    path = Path(args.report)
    if not path.exists():
        print(f"MISSING_FILE {path}")
        return 1
    text = path.read_text(encoding="utf-8")
    missing = validate_report(text)
    if missing:
        print("MISSING: " + ", ".join(missing))
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
