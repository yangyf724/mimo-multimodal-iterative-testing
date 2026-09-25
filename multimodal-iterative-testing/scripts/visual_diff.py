#!/usr/bin/env python3
"""Baseline snapshot / pixel diff / intentional approve (Phase 1)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_DIFF_FAIL = 1
EXIT_USAGE = 2
EXIT_SKIPPED = 0  # Pillow missing is a documented skip, not a hard fail


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _pillow():
    try:
        from PIL import Image  # type: ignore

        return Image
    except Exception:
        return None


def compare_images(
    baseline_path: Path,
    current_path: Path,
    *,
    threshold: float = 0.01,
) -> dict[str, Any]:
    Image = _pillow()
    if Image is None:
        return {
            "status": "skipped",
            "reason": "Pillow not available",
            "baseline": str(baseline_path),
            "current": str(current_path),
        }

    with Image.open(baseline_path) as base_im, Image.open(current_path) as cur_im:
        base = base_im.convert("RGB")
        cur = cur_im.convert("RGB")
        if base.size != cur.size:
            return {
                "status": "fail",
                "reason": "size-mismatch",
                "baseline_size": list(base.size),
                "current_size": list(cur.size),
                "diff_ratio": 1.0,
                "threshold": threshold,
            }
        b_px = base.load()
        c_px = cur.load()
        w, h = base.size
        differing = 0
        total = w * h
        # Sample every pixel; images in skill demos are small.
        for y in range(h):
            for x in range(w):
                if b_px[x, y] != c_px[x, y]:
                    differing += 1
        ratio = differing / total if total else 0.0
        status = "fail" if ratio > threshold else "ok"
        return {
            "status": status,
            "diff_ratio": round(ratio, 6),
            "differing_pixels": differing,
            "total_pixels": total,
            "threshold": threshold,
            "baseline": str(baseline_path),
            "current": str(current_path),
        }


def list_viewport_pngs(captures_dir: Path) -> list[Path]:
    if not captures_dir.exists():
        return []
    return sorted(captures_dir.glob("*__viewport.png"))


def stem_from_viewport_png(path: Path) -> str:
    name = path.name
    suffix = "__viewport.png"
    if name.endswith(suffix):
        return name[: -len(suffix)]
    return path.stem


def baseline_name_from_stem(stem: str) -> str:
    # home__375x812 -> home__375x812.png
    return f"{stem}.png"


def snapshot_baselines(
    captures_dir: Path,
    baseline_dir: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    baseline_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    skipped: list[str] = []
    for png in list_viewport_pngs(captures_dir):
        stem = stem_from_viewport_png(png)
        dest = baseline_dir / baseline_name_from_stem(stem)
        if dest.exists() and not force:
            skipped.append(dest.name)
            continue
        shutil.copy2(png, dest)
        created.append(dest.name)
    return {"ok": True, "created": created, "skipped": skipped, "baseline_dir": str(baseline_dir)}


def compare_captures(
    captures_dir: Path,
    baseline_dir: Path,
    *,
    threshold: float = 0.01,
) -> dict[str, Any]:
    Image = _pillow()
    if Image is None:
        return {
            "ok": True,
            "status": "skipped",
            "reason": "Pillow not available; pixel gate skipped — record Blind Spot",
            "findings": [],
        }

    findings: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    missing_baseline: list[str] = []
    for png in list_viewport_pngs(captures_dir):
        stem = stem_from_viewport_png(png)
        base_path = baseline_dir / baseline_name_from_stem(stem)
        if not base_path.exists():
            missing_baseline.append(stem)
            continue
        result = compare_images(base_path, png, threshold=threshold)
        result["stem"] = stem
        results.append(result)
        if result.get("status") == "fail":
            # stem: home__375x812
            parts = stem.split("__")
            route_slug = parts[0] if parts else stem
            viewport = parts[1] if len(parts) > 1 else "?"
            findings.append(
                {
                    "rule_id": "visual-diff",
                    "modality": "web-visual",
                    "category": "ui-visual",
                    "severity": "medium",
                    "title": f"Visual regression vs baseline: {stem}",
                    "statement": (
                        f"期望与基线像素差异 ≤ {threshold:.2%}；"
                        f"实际 diff_ratio={result.get('diff_ratio')}"
                    ),
                    "location": {
                        "surface": "web",
                        "route": f"/{route_slug}" if route_slug != "home" else "/",
                        "viewport": viewport,
                        "selector": "page",
                        "bbox": None,
                    },
                    "metrics": result,
                    "evidence_level_target": "L3",
                    "detected_by": "visual-diff",
                    "core_assertion_digest": "visual-diff|pixel-delta",
                }
            )

    return {
        "ok": len(findings) == 0,
        "status": "fail" if findings else ("ok" if results else "empty"),
        "findings": findings,
        "results": results,
        "missing_baseline": missing_baseline,
        "threshold": threshold,
    }


def approve_intentional(
    captures_dir: Path,
    baseline_dir: Path,
    root: Path,
    *,
    route: str | None = None,
    viewport: str | None = None,
    reason: str,
    stems: list[str] | None = None,
) -> dict[str, Any]:
    baseline_dir.mkdir(parents=True, exist_ok=True)
    approvals_path = root / ".bug-hunter" / "baselines" / "approvals.jsonl"
    approvals_path.parent.mkdir(parents=True, exist_ok=True)

    selected: list[Path] = []
    if stems:
        for stem in stems:
            png = captures_dir / f"{stem}__viewport.png"
            if png.exists():
                selected.append(png)
    else:
        for png in list_viewport_pngs(captures_dir):
            stem = stem_from_viewport_png(png)
            parts = stem.split("__")
            slug = parts[0] if parts else ""
            vp = parts[1] if len(parts) > 1 else ""
            if route:
                want = route.strip("/")
                if want and slug != want and not (want == "" and slug == "home"):
                    continue
            if viewport and vp and vp != viewport:
                continue
            selected.append(png)

    approved: list[dict[str, Any]] = []
    now = utc_now()
    with approvals_path.open("a", encoding="utf-8") as f:
        for png in selected:
            stem = stem_from_viewport_png(png)
            dest = baseline_dir / baseline_name_from_stem(stem)
            shutil.copy2(png, dest)
            digest = sha256_file(dest)
            record = {
                "stem": stem,
                "route": route,
                "viewport": viewport,
                "reason": reason,
                "sha256": digest,
                "at": now,
                "baseline": dest.name,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            approved.append(record)

    return {"ok": True, "approved": approved, "approvals_path": str(approvals_path)}


def load_approvals(root: Path) -> list[dict[str, Any]]:
    path = root / ".bug-hunter" / "baselines" / "approvals.jsonl"
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Visual baseline snapshot / diff / approve")
    sub = p.add_subparsers(dest="cmd", required=True)

    snap = sub.add_parser("snapshot", help="copy current viewport shots into baselines")
    snap.add_argument("--captures", required=True)
    snap.add_argument("--baseline-dir", required=True)
    snap.add_argument("--force", action="store_true")

    cmp = sub.add_parser("compare", help="compare captures against baselines")
    cmp.add_argument("--captures", required=True)
    cmp.add_argument("--baseline-dir", required=True)
    cmp.add_argument("--threshold", type=float, default=0.01)
    cmp.add_argument("--out", help="optional findings JSON output path")

    appr = sub.add_parser("approve", help="promote current shots as intentional baselines")
    appr.add_argument("--root", default=".")
    appr.add_argument("--captures", required=True)
    appr.add_argument("--baseline-dir", required=True)
    appr.add_argument("--route")
    appr.add_argument("--viewport")
    appr.add_argument("--reason", required=True)
    appr.add_argument("--stems", nargs="*")

    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.cmd == "snapshot":
        result = snapshot_baselines(
            Path(args.captures), Path(args.baseline_dir), force=args.force
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return EXIT_OK

    if args.cmd == "compare":
        result = compare_captures(
            Path(args.captures), Path(args.baseline_dir), threshold=args.threshold
        )
        if args.out:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("status") == "skipped":
            return EXIT_SKIPPED
        return EXIT_OK if result.get("ok") else EXIT_DIFF_FAIL

    if args.cmd == "approve":
        result = approve_intentional(
            Path(args.captures),
            Path(args.baseline_dir),
            Path(args.root).resolve(),
            route=args.route,
            viewport=args.viewport,
            reason=args.reason,
            stems=args.stems,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return EXIT_OK

    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
