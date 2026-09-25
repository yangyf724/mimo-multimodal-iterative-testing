#!/usr/bin/env python3
"""canvas-safe / canvas-asset probe (Phase 2). stdlib-only."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ALL_RULES = (
    "safe-area-violation",
    "export-mismatch",
    "z-order-occlusion",
    "low-res-asset",
    "aspect-distort",
    "hierarchy-flat",
)


def parse_size(value: str | None) -> tuple[float, float] | None:
    if not value:
        return None
    text = str(value).strip().lower().replace(" ", "").replace("*", "x").replace("×", "x")
    m = re.match(r"^(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)$", text)
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


def _finding(
    *,
    rule_id: str,
    title: str,
    statement: str,
    canvas_id: str,
    object_id: str | None,
    metrics: dict[str, Any],
    severity: str,
    digest: str,
    category: str = "canvas-design",
    evidence_level: str = "L3",
    status: str = "candidate",
    export_size: str | None = None,
    bbox: dict[str, float] | None = None,
) -> dict[str, Any]:
    location: dict[str, Any] = {
        "surface": "canvas",
        "canvas_id": canvas_id,
        "viewport": export_size or "n/a",
    }
    if object_id:
        location["canvas_object_id"] = object_id
        location["selector"] = f"canvas#{canvas_id}#{object_id}"
    else:
        location["selector"] = f"canvas#{canvas_id}"
    if bbox is not None:
        location["bbox"] = bbox
    finding: dict[str, Any] = {
        "rule_id": rule_id,
        "modality": "canvas",
        "category": category,
        "severity": severity,
        "title": title,
        "statement": statement,
        "location": location,
        "metrics": metrics,
        "evidence_level_target": evidence_level,
        "detected_by": "canvas-safe" if category == "canvas-design" else "canvas-asset",
        "core_assertion_digest": digest,
    }
    if status:
        finding["status"] = status
    return finding


def normalize_item(raw: dict[str, Any], *, default_id: str | None = None) -> dict[str, Any]:
    item_id = raw.get("id") or default_id or "canvas-item"
    export_size = raw.get("export_size") or raw.get("export_target") or None
    spec = raw.get("spec") or {}
    objects = list(raw.get("objects") or [])
    assets = list(raw.get("assets") or [])
    return {
        "id": str(item_id),
        "kind": raw.get("kind") or "scene-json",
        "export_size": export_size,
        "export_target": spec.get("export_target") or raw.get("export_target"),
        "source": raw.get("source"),
        "render_png": raw.get("render_png"),
        "safe_inset_pct": float(spec.get("safe_inset_pct", raw.get("safe_inset_pct", 5.0))),
        "objects": objects,
        "assets": assets,
    }


def load_items_from_path(path: Path) -> list[dict[str, Any]]:
    """Load canvas items from a JSON file or directory of *.scene.json / canvas-*.json."""
    items: list[dict[str, Any]] = []
    if path.is_dir():
        candidates = list(path.glob("*.scene.json")) + list(path.glob("canvas-*.json"))
        for child in sorted(set(candidates)):
            with child.open("r", encoding="utf-8-sig") as f:
                data = json.load(f)
            if isinstance(data, list):
                for i, raw in enumerate(data):
                    if isinstance(raw, dict):
                        items.append(normalize_item(raw, default_id=child.stem))
            elif isinstance(data, dict):
                if "items" in data and isinstance(data.get("items"), list):
                    for raw in data["items"]:
                        if isinstance(raw, dict):
                            items.append(normalize_item(raw))
                else:
                    items.append(normalize_item(data, default_id=child.stem.replace(".scene", "")))
        return items
    with path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if isinstance(data, list):
        for raw in data:
            if isinstance(raw, dict):
                items.append(normalize_item(raw))
    elif isinstance(data, dict):
        if "items" in data and isinstance(data.get("items"), list):
            for raw in data["items"]:
                if isinstance(raw, dict):
                    items.append(normalize_item(raw))
        else:
            items.append(normalize_item(data))
    return items


def _object_bbox(obj: dict[str, Any]) -> dict[str, float]:
    return {
        "x": float(obj.get("x") or 0),
        "y": float(obj.get("y") or 0),
        "w": float(obj.get("w") or obj.get("width") or 0),
        "h": float(obj.get("h") or obj.get("height") or 0),
    }


def _rect_union_area(rects: list[dict[str, float]]) -> float:
    """Exact area of union of axis-aligned rects via coordinate compression."""
    if not rects:
        return 0.0
    xs = sorted({r["x1"] for r in rects} | {r["x2"] for r in rects})
    ys = sorted({r["y1"] for r in rects} | {r["y2"] for r in rects})
    total = 0.0
    for i in range(len(xs) - 1):
        x1, x2 = xs[i], xs[i + 1]
        if x2 <= x1:
            continue
        # y-intervals covered in this vertical strip
        intervals: list[tuple[float, float]] = []
        for r in rects:
            if r["x1"] <= x1 and r["x2"] >= x2:
                intervals.append((r["y1"], r["y2"]))
        if not intervals:
            continue
        intervals.sort()
        merged_y = 0.0
        cur_a, cur_b = intervals[0]
        for a, b in intervals[1:]:
            if a <= cur_b:
                cur_b = max(cur_b, b)
            else:
                merged_y += cur_b - cur_a
                cur_a, cur_b = a, b
        merged_y += cur_b - cur_a
        total += (x2 - x1) * merged_y
    return total


def check_safe_area(
    item: dict[str, Any],
    *,
    inset_pct: float | None = None,
) -> list[dict[str, Any]]:
    size = parse_size(item.get("export_size"))
    if not size or not item.get("objects"):
        return []
    export_w, export_h = size
    pct = float(inset_pct if inset_pct is not None else item.get("safe_inset_pct", 5.0))
    inset_x = export_w * pct / 100.0
    inset_y = export_h * pct / 100.0
    findings: list[dict[str, Any]] = []
    for obj in item["objects"]:
        bbox = _object_bbox(obj)
        if bbox["w"] <= 0 and bbox["h"] <= 0:
            continue
        # Full-bleed backgrounds intentionally cover the export box; not a safe-area bug.
        if (
            abs(bbox["w"] - export_w) <= 1.0
            and abs(bbox["h"] - export_h) <= 1.0
            and abs(bbox["x"]) <= 1.0
            and abs(bbox["y"]) <= 1.0
        ):
            continue
        left, top = bbox["x"], bbox["y"]
        right = bbox["x"] + bbox["w"]
        bottom = bbox["y"] + bbox["h"]
        violations = []
        if left < inset_x - 0.5:
            violations.append(f"left={left:.1f} < inset {inset_x:.1f}")
        if top < inset_y - 0.5:
            violations.append(f"top={top:.1f} < inset {inset_y:.1f}")
        if right > export_w - inset_x + 0.5:
            violations.append(f"right={right:.1f} > {export_w - inset_x:.1f}")
        if bottom > export_h - inset_y + 0.5:
            violations.append(f"bottom={bottom:.1f} > {export_h - inset_y:.1f}")
        if not violations:
            continue
        oid = str(obj.get("id") or "object")
        findings.append(
            _finding(
                rule_id="safe-area-violation",
                title=f"Canvas object outside safe area: {oid}",
                statement=(
                    f"期望对象 {oid} 完全位于安全区 inset {pct}%（{inset_x:.1f}×{inset_y:.1f}px）内；"
                    f"实际：{'; '.join(violations)}"
                ),
                canvas_id=item["id"],
                object_id=oid,
                export_size=item.get("export_size"),
                bbox=bbox,
                metrics={
                    "safe_inset_pct": pct,
                    "inset_x": inset_x,
                    "inset_y": inset_y,
                    "export_w": export_w,
                    "export_h": export_h,
                    "violations": violations,
                },
                severity="high",
                digest="safe-area-violation|outside-inset",
            )
        )
    return findings


def check_export_mismatch(
    item: dict[str, Any],
    *,
    export_target: str | None = None,
) -> list[dict[str, Any]]:
    target = export_target or item.get("export_target")
    actual = item.get("export_size")
    if not target or not actual:
        return []
    t = parse_size(target)
    a = parse_size(actual)
    if not t or not a:
        return []
    if abs(t[0] - a[0]) < 0.5 and abs(t[1] - a[1]) < 0.5:
        return []
    return [
        _finding(
            rule_id="export-mismatch",
            title=f"Canvas export size mismatch: {item['id']}",
            statement=f"期望导出尺寸 {target}；实际 export_size={actual}",
            canvas_id=item["id"],
            object_id=None,
            export_size=actual,
            metrics={"export_target": target, "export_size": actual, "delta_w": a[0] - t[0], "delta_h": a[1] - t[1]},
            severity="high",
            digest="export-mismatch|size-delta",
        )
    ]


def check_z_order_occlusion(
    item: dict[str, Any],
    *,
    min_coverage: float = 0.98,
) -> list[dict[str, Any]]:
    objects = item.get("objects") or []
    if len(objects) < 2:
        return []
    size = parse_size(item.get("export_size"))
    findings: list[dict[str, Any]] = []
    normalized = []
    for obj in objects:
        bbox = _object_bbox(obj)
        if bbox["w"] <= 0 or bbox["h"] <= 0:
            continue
        otype = str(obj.get("type") or "shape").lower()
        opacity = float(obj.get("opacity", 1.0))
        if opacity < 0.95:
            continue
        if size:
            # Skip objects fully outside export box
            if bbox["x"] + bbox["w"] < 0 or bbox["y"] + bbox["h"] < 0:
                continue
            if bbox["x"] > size[0] or bbox["y"] > size[1]:
                continue
        normalized.append((obj, bbox, float(obj.get("zIndex", obj.get("z_index", 0))), otype))

    for i, (obj, bbox, z, otype) in enumerate(normalized):
        if otype not in ("text", "cta", "button", "label"):
            continue
        area = bbox["w"] * bbox["h"]
        if area <= 0:
            continue
        # Union of occluder∩target regions (do not sum pairwise overlaps).
        # Grid-based union on the target bbox for exact-enough coverage.
        occluders: list[dict[str, float]] = []
        for j, (_other, ob, oz, _otype) in enumerate(normalized):
            if i == j or oz <= z:
                continue
            ox1 = max(bbox["x"], ob["x"])
            oy1 = max(bbox["y"], ob["y"])
            ox2 = min(bbox["x"] + bbox["w"], ob["x"] + ob["w"])
            oy2 = min(bbox["y"] + bbox["h"], ob["y"] + ob["h"])
            if ox2 > ox1 and oy2 > oy1:
                occluders.append({"x1": ox1, "y1": oy1, "x2": ox2, "y2": oy2})
        covered = _rect_union_area(occluders)
        ratio = min(1.0, covered / area)
        if ratio < min_coverage:
            continue
        oid = str(obj.get("id") or "object")
        findings.append(
            _finding(
                rule_id="z-order-occlusion",
                title=f"Canvas text/CTA fully occluded: {oid}",
                statement=(
                    f"期望可见主体 {oid} 不被更高 zIndex 完全遮挡；"
                    f"实际覆盖率 {ratio:.2%} ≥ {min_coverage:.0%}"
                ),
                canvas_id=item["id"],
                object_id=oid,
                export_size=item.get("export_size"),
                bbox=bbox,
                metrics={"coverage_ratio": round(ratio, 4), "min_coverage": min_coverage, "zIndex": z},
                severity="high",
                digest="z-order-occlusion|fully-covered",
            )
        )
    return findings


def check_low_res_assets(item: dict[str, Any], *, max_ratio: float = 2.0) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for asset in item.get("assets") or []:
        try:
            display_w = float(asset.get("display_w") or asset.get("display_width") or 0)
            display_h = float(asset.get("display_h") or asset.get("display_height") or 0)
            pixel_w = float(asset.get("pixel_w") or asset.get("pixel_width") or 0)
            pixel_h = float(asset.get("pixel_h") or asset.get("pixel_height") or 0)
        except (TypeError, ValueError):
            continue
        if min(display_w, display_h, pixel_w, pixel_h) <= 0:
            continue
        ratio = max(display_w / pixel_w, display_h / pixel_h)
        if ratio <= max_ratio + 1e-9:
            continue
        aid = str(asset.get("id") or asset.get("path") or "asset")
        findings.append(
            _finding(
                rule_id="low-res-asset",
                title=f"Low-resolution asset: {aid}",
                statement=(
                    f"期望显示尺寸/像素分辨率 ≤ {max_ratio:.1f}×；"
                    f"实际 ratio={ratio:.2f}（display {display_w:.0f}×{display_h:.0f} / pixel {pixel_w:.0f}×{pixel_h:.0f}）"
                ),
                canvas_id=item["id"],
                object_id=aid,
                export_size=item.get("export_size"),
                metrics={
                    "ratio": round(ratio, 3),
                    "max_ratio": max_ratio,
                    "display_w": display_w,
                    "display_h": display_h,
                    "pixel_w": pixel_w,
                    "pixel_h": pixel_h,
                    "path": asset.get("path"),
                },
                severity="medium",
                category="canvas-asset",
                digest="low-res-asset|upscale-ratio",
            )
        )
    return findings


def check_aspect_distort(item: dict[str, Any], *, tol: float = 0.02) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for asset in item.get("assets") or []:
        try:
            display_w = float(asset.get("display_w") or asset.get("display_width") or 0)
            display_h = float(asset.get("display_h") or asset.get("display_height") or 0)
            pixel_w = float(asset.get("pixel_w") or asset.get("pixel_width") or 0)
            pixel_h = float(asset.get("pixel_h") or asset.get("pixel_height") or 0)
        except (TypeError, ValueError):
            continue
        if min(display_w, display_h, pixel_w, pixel_h) <= 0:
            continue
        display_ratio = display_w / display_h
        pixel_ratio = pixel_w / pixel_h
        delta = abs(display_ratio - pixel_ratio) / pixel_ratio
        if delta <= tol:
            continue
        aid = str(asset.get("id") or asset.get("path") or "asset")
        findings.append(
            _finding(
                rule_id="aspect-distort",
                title=f"Asset aspect ratio distorted: {aid}",
                statement=(
                    f"期望显示宽高比与像素宽高比偏差 ≤ {tol:.0%}；"
                    f"实际偏差 {delta:.1%}（display {display_ratio:.3f} vs pixel {pixel_ratio:.3f}）"
                ),
                canvas_id=item["id"],
                object_id=aid,
                export_size=item.get("export_size"),
                metrics={
                    "delta_ratio": round(delta, 4),
                    "tol": tol,
                    "display_ratio": round(display_ratio, 4),
                    "pixel_ratio": round(pixel_ratio, 4),
                },
                severity="medium",
                category="canvas-asset",
                digest="aspect-distort|ratio-delta",
            )
        )
    return findings


def check_hierarchy_flat(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Heuristic: primary CTA smaller than a secondary element → deferred candidate."""
    objects = item.get("objects") or []
    primary = None
    secondary = []
    for obj in objects:
        otype = str(obj.get("type") or "").lower()
        if obj.get("primary") is True or otype == "cta":
            primary = obj
        elif otype in ("text", "shape", "button", "label"):
            secondary.append(obj)
    if primary is None or not secondary:
        return []
    pb = _object_bbox(primary)
    p_area = pb["w"] * pb["h"]
    if p_area <= 0:
        return []
    larger = []
    for obj in secondary:
        sb = _object_bbox(obj)
        area = sb["w"] * sb["h"]
        if area > p_area * 1.5:
            larger.append({"id": obj.get("id"), "area": area})
    if not larger:
        return []
    return [
        _finding(
            rule_id="hierarchy-flat",
            title=f"Canvas hierarchy may be flat: primary CTA {primary.get('id')}",
            statement=(
                f"主 CTA 面积 {p_area:.0f} 明显小于次级元素（{larger[0]['id']} 面积 {larger[0]['area']:.0f}），"
                "可能层级不清（启发式，需设计规范确认）"
            ),
            canvas_id=item["id"],
            object_id=str(primary.get("id") or "cta"),
            export_size=item.get("export_size"),
            bbox=pb,
            metrics={"primary_area": p_area, "larger": larger},
            severity="low",
            evidence_level="L2",
            status="deferred",
            digest="hierarchy-flat|cta-smaller",
        )
    ]


def run_canvas_rules(
    item: dict[str, Any],
    *,
    export_target: str | None = None,
    safe_inset_pct: float | None = None,
    min_coverage: float = 0.98,
    low_res_max_ratio: float = 2.0,
    aspect_tol: float = 0.02,
    rules: list[str] | None = None,
) -> list[dict[str, Any]]:
    selected = set(rules) if rules else set(ALL_RULES)
    findings: list[dict[str, Any]] = []
    if not item.get("objects") and not item.get("assets"):
        return []
    if "safe-area-violation" in selected:
        findings.extend(check_safe_area(item, inset_pct=safe_inset_pct))
    if "export-mismatch" in selected:
        findings.extend(check_export_mismatch(item, export_target=export_target))
    if "z-order-occlusion" in selected and item.get("objects"):
        findings.extend(check_z_order_occlusion(item, min_coverage=min_coverage))
    if "low-res-asset" in selected:
        findings.extend(check_low_res_assets(item, max_ratio=low_res_max_ratio))
    if "aspect-distort" in selected:
        findings.extend(check_aspect_distort(item, tol=aspect_tol))
    if "hierarchy-flat" in selected:
        findings.extend(check_hierarchy_flat(item))
    return findings


def run_canvas_items(
    items: list[dict[str, Any]],
    *,
    export_target: str | None = None,
    oracle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    oracle = oracle or {}
    all_findings: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    per_item: dict[str, int] = {}
    for raw in items:
        item = raw if "objects" in raw or "assets" in raw else normalize_item(raw)
        if not item.get("objects") and not item.get("assets"):
            unavailable.append(
                {
                    "canvas_id": item.get("id"),
                    "reason": "no-objects-or-assets",
                }
            )
            continue
        item_findings = run_canvas_rules(
            item,
            export_target=export_target or item.get("export_target"),
            safe_inset_pct=float(oracle.get("safe_inset_pct", item.get("safe_inset_pct", 5.0))),
            min_coverage=float(oracle.get("z_order_min_coverage", 0.98)),
            low_res_max_ratio=float(oracle.get("low_res_max_ratio", 2.0)),
            aspect_tol=float(oracle.get("aspect_distort_tol", 0.02)),
        )
        per_item[str(item.get("id"))] = len(item_findings)
        all_findings.extend(item_findings)
    return {
        "findings": all_findings,
        "unavailable": unavailable,
        "by_canvas": per_item,
        "items_scanned": len(items),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="canvas-safe / canvas-asset probe")
    p.add_argument("--items", help="path to items JSON file or directory")
    p.add_argument("--root", help="project root; reads state.surfaces.canvas.items")
    p.add_argument("--export-target", dest="export_target", help="target export size WxH")
    p.add_argument("--safe-inset-pct", type=float, default=None)
    p.add_argument("--rules", help="comma-separated rule ids")
    p.add_argument("--out", help="write findings JSON to this path")
    p.add_argument(
        "--fp-patterns",
        dest="fp_patterns",
        default=None,
        help="optional FP whitelist JSON; matching findings get status=suppressed",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    items: list[dict[str, Any]] = []
    oracle: dict[str, Any] = {}
    if args.items:
        items = load_items_from_path(Path(args.items).resolve())
    elif args.root:
        root = Path(args.root).resolve()
        state_path = root / ".bug-hunter" / "state.json"
        if not state_path.exists():
            print(json.dumps({"ok": False, "error": "state.json missing"}, ensure_ascii=False), file=sys.stderr)
            return 1
        with state_path.open("r", encoding="utf-8-sig") as f:
            state = json.load(f)
        canvas = (state.get("surfaces") or {}).get("canvas") or {}
        raw_items = canvas.get("items") or []
        items = [normalize_item(i) for i in raw_items if isinstance(i, dict)]
        oracle = state.get("visual_oracle") or {}
        if not args.export_target:
            args.export_target = canvas.get("export_target")
        # Resolve relative sources against root when source is a scene file
        for item in items:
            src = item.get("source")
            if src and not Path(src).is_absolute():
                src_path = root / src
                if src_path.exists():
                    loaded = load_items_from_path(src_path)
                    if loaded:
                        merged = loaded[0]
                        merged["id"] = item.get("id") or merged.get("id")
                        item.update({k: v for k, v in merged.items() if v is not None})
    else:
        print(json.dumps({"ok": False, "error": "--items or --root required"}, ensure_ascii=False), file=sys.stderr)
        return 2

    rules = [r.strip() for r in args.rules.split(",")] if args.rules else None
    if rules:
        selected_items = items
        findings: list[dict[str, Any]] = []
        unavailable: list[dict[str, Any]] = []
        for item in selected_items:
            findings.extend(
                run_canvas_rules(
                    item,
                    export_target=args.export_target or item.get("export_target"),
                    safe_inset_pct=args.safe_inset_pct,
                    rules=rules,
                )
            )
        result = {"ok": True, "findings": findings, "unavailable": unavailable}
    else:
        result = run_canvas_items(items, export_target=args.export_target, oracle=oracle)
        result["ok"] = True

    if args.fp_patterns:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import fp_feedback as fpf  # noqa: PLC0415

        findings, hits = fpf.apply_patterns_path(result.get("findings") or [], Path(args.fp_patterns))
        result["findings"] = findings
        result["suppressed_count"] = len(hits)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
