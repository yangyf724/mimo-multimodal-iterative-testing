#!/usr/bin/env python3
"""contrast-type probe: WCAG contrast, font size, line-height (Phase 1)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

RGB_RE = re.compile(
    r"rgba?\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*(?:,\s*([0-9.]+)\s*)?\)",
    re.I,
)

ROOT_SELECTORS = {"html", "body", "document", ":root"}


def parse_css_color(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    text = value.strip().lower()
    if text in ("transparent", "inherit", "initial", "unset", "currentcolor"):
        return None
    m = RGB_RE.match(text)
    if not m:
        return None
    r, g, b = float(m.group(1)), float(m.group(2)), float(m.group(3))
    a = float(m.group(4)) if m.group(4) is not None else 1.0
    return (r, g, b, a)


def _srgb_to_linear(c: float) -> float:
    cs = c / 255.0
    if cs <= 0.04045:
        return cs / 12.92
    return ((cs + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: tuple[float, float, float]) -> float:
    r, g, b = rgb
    return (
        0.2126 * _srgb_to_linear(r)
        + 0.7152 * _srgb_to_linear(g)
        + 0.0722 * _srgb_to_linear(b)
    )


def contrast_ratio(fg: tuple[float, float, float], bg: tuple[float, float, float]) -> float:
    l1 = relative_luminance(fg)
    l2 = relative_luminance(bg)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def parse_px(value: str | float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower()
    m = re.match(r"^(-?[0-9.]+)px$", text)
    if m:
        return float(m.group(1))
    try:
        return float(text)
    except ValueError:
        return None


def _is_root(el: dict[str, Any]) -> bool:
    return el.get("selector") in ROOT_SELECTORS or el.get("tag") in ("html", "body")


def _finding(
    *,
    rule_id: str,
    title: str,
    statement: str,
    el: dict[str, Any],
    metrics: dict[str, Any],
    severity: str,
    digest: str,
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "modality": "web-visual",
        "category": "ui-visual",
        "severity": severity,
        "title": title,
        "statement": statement,
        "location": {
            "surface": "web",
            "route": el.get("route"),
            "viewport": el.get("viewport"),
            "selector": el.get("selector") or "unknown",
            "bbox": el.get("bbox"),
        },
        "metrics": metrics,
        "evidence_level_target": "L3",
        "detected_by": "contrast-type",
        "core_assertion_digest": digest,
    }


def resolve_background(
    el: dict[str, Any],
    elements_by_depth: list[dict[str, Any]],
) -> tuple[tuple[float, float, float], bool]:
    """Return (rgb, assumed). Walk nearest ancestors first (higher depth = closer)."""
    computed = el.get("computed") or {}
    bg = parse_css_color(computed.get("backgroundColor"))
    if bg and bg[3] > 0.95:
        return (bg[0], bg[1], bg[2]), False

    depth = int(el.get("depth") or 0)
    # Nearest ancestor first: candidates with lower depth, sorted descending
    # so the parent (depth-1) is preferred over html (depth 0).
    candidates = [
        e
        for e in elements_by_depth
        if e is not el and int(e.get("depth") or 0) < depth
    ]
    candidates.sort(key=lambda e: int(e.get("depth") or 0), reverse=True)
    for other in candidates:
        obg = parse_css_color((other.get("computed") or {}).get("backgroundColor"))
        if obg and obg[3] > 0.95:
            return (obg[0], obg[1], obg[2]), False

    # Fallback: any opaque bg in list (often body/html).
    for other in elements_by_depth:
        if other is el:
            continue
        obg = parse_css_color((other.get("computed") or {}).get("backgroundColor"))
        if obg and obg[3] > 0.95:
            return (obg[0], obg[1], obg[2]), False

    return (255.0, 255.0, 255.0), True


def is_large_text(font_size_px: float, font_weight: str | int | None) -> bool:
    try:
        weight = int(float(font_weight))
    except (TypeError, ValueError):
        weight = 400
    if font_size_px >= 24:
        return True
    if font_size_px >= 18.66 and weight >= 700:
        return True
    return False


def check_contrast_text(
    elements: list[dict[str, Any]],
    *,
    min_contrast: float = 4.5,
    large_text_min_contrast: float = 3.0,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    ordered = list(elements)
    for el in elements:
        if _is_root(el):
            continue
        text = (el.get("text") or "").strip()
        if not text:
            continue
        computed = el.get("computed") or {}
        fg = parse_css_color(computed.get("color"))
        if not fg or fg[3] < 0.05:
            continue
        bg, assumed = resolve_background(el, ordered)
        ratio = contrast_ratio((fg[0], fg[1], fg[2]), bg)
        font_size = parse_px(computed.get("fontSize")) or 16.0
        large = is_large_text(font_size, computed.get("fontWeight"))
        threshold = large_text_min_contrast if large else min_contrast
        if ratio >= threshold:
            continue
        selector = el.get("selector") or "unknown"
        findings.append(
            _finding(
                rule_id="contrast-text",
                title=f"Insufficient text contrast: {selector}",
                statement=(
                    f"期望对比度 ≥ {threshold:.1f}:1；实际 {ratio:.2f}:1"
                    + ("（背景按白色假定）" if assumed else "")
                ),
                el=el,
                metrics={
                    "contrast_ratio": round(ratio, 2),
                    "threshold": threshold,
                    "large_text": large,
                    "font_size_px": font_size,
                    "background_assumed": assumed,
                },
                severity="high" if ratio < 3.0 else "medium",
                digest="contrast-text|below-min",
            )
        )
    return findings


def check_font_too_small(
    elements: list[dict[str, Any]],
    *,
    font_too_small_px: float = 12.0,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for el in elements:
        if _is_root(el):
            continue
        text = (el.get("text") or "").strip()
        if not text:
            continue
        bbox = el.get("bbox") or {}
        if float(bbox.get("w") or 0) < 1 or float(bbox.get("h") or 0) < 1:
            continue  # zero-size owns degenerate boxes
        computed = el.get("computed") or {}
        font_size = parse_px(computed.get("fontSize"))
        if font_size is None or font_size <= 0:
            continue
        if font_size >= font_too_small_px:
            continue
        selector = el.get("selector") or "unknown"
        findings.append(
            _finding(
                rule_id="font-too-small",
                title=f"Font size too small: {selector}",
                statement=(
                    f"期望字号 ≥ {font_too_small_px:.0f}px；实际 {font_size:.1f}px"
                ),
                el=el,
                metrics={
                    "font_size_px": font_size,
                    "threshold": font_too_small_px,
                },
                severity="low",
                digest="font-too-small|below-min",
            )
        )
    return findings


def check_line_height_tight(
    elements: list[dict[str, Any]],
    *,
    min_ratio: float = 1.2,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for el in elements:
        if _is_root(el):
            continue
        text = (el.get("text") or "").strip()
        if not text:
            continue
        if "\n" not in text and len(text) < 40:
            continue
        computed = el.get("computed") or {}
        font_size = parse_px(computed.get("fontSize"))
        line_height = parse_px(computed.get("lineHeight"))
        if not font_size or font_size <= 0:
            continue
        if line_height is None or line_height <= 0:
            continue
        ratio = line_height / font_size
        if ratio >= min_ratio:
            continue
        selector = el.get("selector") or "unknown"
        findings.append(
            _finding(
                rule_id="line-height-tight",
                title=f"Line height too tight: {selector}",
                statement=(
                    f"期望 line-height/fontSize ≥ {min_ratio:.2f}；实际 {ratio:.2f}"
                ),
                el=el,
                metrics={
                    "line_height_px": line_height,
                    "font_size_px": font_size,
                    "ratio": round(ratio, 3),
                    "threshold": min_ratio,
                },
                severity="low",
                digest="line-height-tight|below-min",
            )
        )
    return findings


def run_contrast_rules(
    elements: list[dict[str, Any]],
    *,
    min_contrast: float = 4.5,
    large_text_min_contrast: float = 3.0,
    font_too_small_px: float = 12.0,
    line_height_min_ratio: float = 1.2,
    rules: list[str] | None = None,
) -> list[dict[str, Any]]:
    selected = set(rules) if rules else {"contrast-text", "font-too-small", "line-height-tight"}
    findings: list[dict[str, Any]] = []
    if "contrast-text" in selected:
        findings.extend(
            check_contrast_text(
                elements,
                min_contrast=min_contrast,
                large_text_min_contrast=large_text_min_contrast,
            )
        )
    if "font-too-small" in selected:
        findings.extend(check_font_too_small(elements, font_too_small_px=font_too_small_px))
    if "line-height-tight" in selected:
        findings.extend(check_line_height_tight(elements, min_ratio=line_height_min_ratio))
    return findings


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Contrast / type probe (Phase 1)")
    p.add_argument("--min-contrast", type=float, default=4.5)
    p.add_argument("--large-text-min-contrast", type=float, default=3.0)
    p.add_argument("--font-too-small-px", type=float, default=12.0)
    p.add_argument("--line-height-min-ratio", type=float, default=1.2)
    p.add_argument("--route", default=None)
    p.add_argument("--viewport", default=None)
    p.add_argument("--rules", default=None, help="comma-separated rule ids")
    p.add_argument(
        "--fp-patterns",
        dest="fp_patterns",
        default=None,
        help="optional FP whitelist JSON; matching findings get status=suppressed",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps({"ok": False, "error": f"invalid JSON: {e}"}), file=sys.stderr)
        return 2

    if isinstance(payload, dict):
        elements = payload.get("elements") or []
        min_contrast = float(payload.get("min_contrast") or args.min_contrast)
        large_min = float(payload.get("large_text_min_contrast") or args.large_text_min_contrast)
        font_min = float(payload.get("font_too_small_px") or args.font_too_small_px)
        lh_min = float(payload.get("line_height_min_ratio") or args.line_height_min_ratio)
        route = payload.get("route") or args.route
        viewport = payload.get("viewport") or args.viewport
        rules = payload.get("rules") or (
            [r.strip() for r in args.rules.split(",") if r.strip()] if args.rules else None
        )
    else:
        elements = payload
        min_contrast = args.min_contrast
        large_min = args.large_text_min_contrast
        font_min = args.font_too_small_px
        lh_min = args.line_height_min_ratio
        route = args.route
        viewport = args.viewport
        rules = [r.strip() for r in args.rules.split(",") if r.strip()] if args.rules else None

    for el in elements:
        if route and "route" not in el:
            el["route"] = route
        if viewport and "viewport" not in el:
            el["viewport"] = viewport

    findings = run_contrast_rules(
        elements,
        min_contrast=min_contrast,
        large_text_min_contrast=large_min,
        font_too_small_px=font_min,
        line_height_min_ratio=lh_min,
        rules=rules,
    )
    suppressed_count = 0
    if args.fp_patterns:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import fp_feedback as fpf  # noqa: PLC0415

        findings, hits = fpf.apply_patterns_path(findings, Path(args.fp_patterns))
        suppressed_count = len(hits)
    print(
        json.dumps(
            {"findings": findings, "count": len(findings), "suppressed_count": suppressed_count},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
