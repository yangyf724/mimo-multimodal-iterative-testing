#!/usr/bin/env python3
"""layout-geom probe (Phase 0 overflow-x + Phase 1 full rule set)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT_SELECTORS = {"html", "body", "document", ":root"}
NON_RENDERED_TAGS = {"script", "style", "noscript", "template", "link", "meta", "head", "title"}

ALL_RULES = (
    "overflow-x",
    "text-clip",
    "overlap-interactive",
    "zero-size",
    "off-canvas",
    "touch-target",
)


def _bbox(el: dict[str, Any]) -> dict[str, float]:
    b = el.get("bbox") or {}
    return {
        "x": float(b.get("x") or 0),
        "y": float(b.get("y") or 0),
        "w": float(b.get("w") or 0),
        "h": float(b.get("h") or 0),
    }


def _is_root(el: dict[str, Any]) -> bool:
    return el.get("selector") in ROOT_SELECTORS or el.get("tag") in ("html", "body")


def _is_non_rendered(el: dict[str, Any]) -> bool:
    tag = str(el.get("tag") or "").lower()
    if tag in NON_RENDERED_TAGS:
        return True
    attrs = el.get("attrs") or {}
    if attrs.get("hidden") is True or attrs.get("hidden") == "":
        return True
    if str(el.get("selector") or "").startswith("script"):
        return True
    return False


def _finding(
    *,
    rule_id: str,
    title: str,
    statement: str,
    el: dict[str, Any] | None,
    route: str | None,
    viewport: str | None,
    selector: str,
    bbox: dict[str, float] | None,
    metrics: dict[str, Any],
    severity: str,
    digest: str,
    category: str = "ui-layout",
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "modality": "web-visual",
        "category": category,
        "severity": severity,
        "title": title,
        "statement": statement,
        "location": {
            "surface": "web",
            "route": route or (el or {}).get("route"),
            "viewport": viewport or (el or {}).get("viewport"),
            "selector": selector,
            "bbox": bbox,
        },
        "metrics": metrics,
        "evidence_level_target": "L3",
        "detected_by": "layout-geom",
        "core_assertion_digest": digest,
    }


def check_overflow_x(
    elements: list[dict[str, Any]],
    *,
    viewport_width: float,
    epsilon_px: float = 2.0,
) -> list[dict[str, Any]]:
    """Detect horizontal overflow from element/viewport metrics."""
    findings: list[dict[str, Any]] = []

    root = next((e for e in elements if e.get("selector") in ("html", "body", "document", ":root")), None)
    if root:
        sw = float(root.get("scrollWidth") or 0)
        cw = float(root.get("clientWidth") or viewport_width)
        if sw > cw + epsilon_px:
            findings.append(
                _finding(
                    rule_id="overflow-x",
                    title="Horizontal page overflow",
                    statement=(
                        f"期望 document.scrollWidth <= viewport width {cw:.0f}px；"
                        f"实际 scrollWidth={sw:.0f}px，溢出 {sw - cw:.0f}px"
                    ),
                    el=root,
                    route=root.get("route"),
                    viewport=root.get("viewport"),
                    selector="html",
                    bbox=root.get("bbox"),
                    metrics={
                        "scrollWidth": sw,
                        "clientWidth": cw,
                        "overflow_px": round(sw - cw, 2),
                        "epsilon_px": epsilon_px,
                    },
                    severity="high",
                    digest="overflow-x|horizontal-overflow",
                )
            )

    for el in elements:
        # Root nodes only participate in page-level overflow-x above.
        if root is not None and el is root:
            continue
        if _is_root(el):
            continue
        bbox = el.get("bbox") or {}
        if not bbox:
            continue
        right = float(bbox.get("x", 0)) + float(bbox.get("w", 0))
        if right > viewport_width + epsilon_px:
            selector = el.get("selector") or el.get("id") or "unknown"
            overflow = right - viewport_width
            findings.append(
                _finding(
                    rule_id="overflow-x",
                    title=f"Element overflows viewport horizontally: {selector}",
                    statement=(
                        f"期望元素右缘 ≤ viewport {viewport_width:.0f}px；"
                        f"实际 right={right:.0f}px，超出 {overflow:.0f}px"
                    ),
                    el=el,
                    route=el.get("route"),
                    viewport=el.get("viewport"),
                    selector=selector,
                    bbox=bbox,
                    metrics={
                        "right": round(right, 2),
                        "viewport_width": viewport_width,
                        "overflow_px": round(overflow, 2),
                        "epsilon_px": epsilon_px,
                    },
                    severity="high" if el.get("interactive") or "button" in str(selector).lower() else "medium",
                    digest="overflow-x|horizontal-overflow",
                )
            )

    for el in elements:
        if el is root:
            continue
        if _is_root(el):
            continue
        sw = el.get("scrollWidth")
        cw = el.get("clientWidth")
        if sw is None or cw is None:
            continue
        swf, cwf = float(sw), float(cw)
        if swf > cwf + epsilon_px and el.get("text_overflow") not in ("ellipsis", "clip-intentional"):
            selector = el.get("selector") or "unknown"
            findings.append(
                _finding(
                    rule_id="overflow-x",
                    title=f"Element content clipped horizontally: {selector}",
                    statement=(
                        f"期望 scrollWidth ≤ clientWidth {cwf:.0f}px；"
                        f"实际 scrollWidth={swf:.0f}px，超出 {swf - cwf:.0f}px"
                    ),
                    el=el,
                    route=el.get("route"),
                    viewport=el.get("viewport"),
                    selector=selector,
                    bbox=el.get("bbox"),
                    metrics={
                        "scrollWidth": swf,
                        "clientWidth": cwf,
                        "overflow_px": round(swf - cwf, 2),
                        "epsilon_px": epsilon_px,
                    },
                    severity="medium",
                    digest="overflow-x|horizontal-overflow",
                )
            )

    return findings


def check_text_clip(
    elements: list[dict[str, Any]],
    *,
    epsilon_px: float = 2.0,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for el in elements:
        if _is_root(el):
            continue
        text = (el.get("text") or "").strip()
        if not text:
            continue
        sw = el.get("scrollWidth")
        cw = el.get("clientWidth")
        if sw is None or cw is None:
            continue
        swf, cwf = float(sw), float(cw)
        if swf <= cwf + epsilon_px:
            continue
        if el.get("text_overflow") in ("ellipsis", "clip-intentional"):
            continue
        selector = el.get("selector") or "unknown"
        findings.append(
            _finding(
                rule_id="text-clip",
                title=f"Text content clipped: {selector}",
                statement=(
                    f"期望文本 scrollWidth ≤ clientWidth {cwf:.0f}px；"
                    f"实际 scrollWidth={swf:.0f}px，裁切 {swf - cwf:.0f}px"
                ),
                el=el,
                route=el.get("route"),
                viewport=el.get("viewport"),
                selector=selector,
                bbox=el.get("bbox"),
                metrics={
                    "scrollWidth": swf,
                    "clientWidth": cwf,
                    "clip_px": round(swf - cwf, 2),
                    "epsilon_px": epsilon_px,
                },
                severity="medium",
                digest="text-clip|content-clipped",
            )
        )
    return findings


def _intersect_area(a: dict[str, float], b: dict[str, float]) -> float:
    x1 = max(a["x"], b["x"])
    y1 = max(a["y"], b["y"])
    x2 = min(a["x"] + a["w"], b["x"] + b["w"])
    y2 = min(a["y"] + a["h"], b["y"] + b["h"])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    return (x2 - x1) * (y2 - y1)


def check_overlap_interactive(
    elements: list[dict[str, Any]],
    *,
    overlap_ratio: float = 0.2,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    interactives = []
    for el in elements:
        if _is_root(el) or not el.get("interactive"):
            continue
        bbox = _bbox(el)
        if bbox["w"] <= 0 or bbox["h"] <= 0:
            continue
        interactives.append((el, bbox))

    for i in range(len(interactives)):
        for j in range(i + 1, len(interactives)):
            a_el, a_box = interactives[i]
            b_el, b_box = interactives[j]
            area = _intersect_area(a_box, b_box)
            if area <= 0:
                continue
            min_area = min(a_box["w"] * a_box["h"], b_box["w"] * b_box["h"])
            if min_area <= 0:
                continue
            ratio = area / min_area
            if ratio <= overlap_ratio:
                continue
            sel_a = a_el.get("selector") or f"el-{i}"
            sel_b = b_el.get("selector") or f"el-{j}"
            pair = sorted([sel_a, sel_b])
            findings.append(
                _finding(
                    rule_id="overlap-interactive",
                    title=f"Interactive elements overlap: {pair[0]} / {pair[1]}",
                    statement=(
                        f"期望可点击元素不互相遮挡；实际 bbox 相交占较小元素 {ratio * 100:.0f}%"
                    ),
                    el=a_el,
                    route=a_el.get("route"),
                    viewport=a_el.get("viewport"),
                    selector=f"{pair[0]}~{pair[1]}",
                    bbox=a_box,
                    metrics={
                        "overlap_ratio": round(ratio, 3),
                        "overlap_area": round(area, 2),
                        "threshold": overlap_ratio,
                        "selectors": pair,
                    },
                    severity="high",
                    digest="overlap-interactive|bbox-intersect",
                )
            )
    return findings


def check_zero_size(elements: list[dict[str, Any]], *, min_size: float = 1.0) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for el in elements:
        if _is_root(el) or _is_non_rendered(el):
            continue
        has_content = bool((el.get("text") or "").strip()) or bool(el.get("interactive"))
        if not has_content:
            continue
        # Hidden sinks / deferred UI are not layout defects until revealed.
        if not el.get("interactive") and not el.get("inViewport", True):
            continue
        bbox = _bbox(el)
        if bbox["w"] < min_size or bbox["h"] < min_size:
            selector = el.get("selector") or "unknown"
            findings.append(
                _finding(
                    rule_id="zero-size",
                    title=f"Degenerate box for interactive/content node: {selector}",
                    statement=(
                        f"期望有内容节点 w/h ≥ {min_size}px；"
                        f"实际 w={bbox['w']:.2f}, h={bbox['h']:.2f}"
                    ),
                    el=el,
                    route=el.get("route"),
                    viewport=el.get("viewport"),
                    selector=selector,
                    bbox=bbox,
                    metrics={
                        "w": bbox["w"],
                        "h": bbox["h"],
                        "min_size": min_size,
                        "interactive": bool(el.get("interactive")),
                    },
                    severity="medium",
                    digest="zero-size|degenerate-box",
                )
            )
    return findings


def check_off_canvas(
    elements: list[dict[str, Any]],
    *,
    viewport_width: float,
    viewport_height: float,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for el in elements:
        if _is_root(el) or not el.get("interactive"):
            continue
        bbox = _bbox(el)
        if bbox["w"] <= 0 and bbox["h"] <= 0:
            continue
        outside = (
            bbox["x"] + bbox["w"] < 0
            or bbox["x"] > viewport_width
            or bbox["y"] + bbox["h"] < 0
            or bbox["y"] > viewport_height
        )
        if not outside:
            continue
        selector = el.get("selector") or "unknown"
        findings.append(
            _finding(
                rule_id="off-canvas",
                title=f"Interactive element fully off-canvas: {selector}",
                statement=(
                    f"期望可点击元素至少部分落在 viewport {viewport_width:.0f}x{viewport_height:.0f} 内；"
                    f"实际 bbox 完全在外"
                ),
                el=el,
                route=el.get("route"),
                viewport=el.get("viewport"),
                selector=selector,
                bbox=bbox,
                metrics={
                    "viewport_width": viewport_width,
                    "viewport_height": viewport_height,
                    "bbox": bbox,
                },
                severity="medium",
                digest="off-canvas|outside-viewport",
            )
        )
    return findings


def check_touch_target(
    elements: list[dict[str, Any]],
    *,
    touch_target_px: float = 44.0,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for el in elements:
        if _is_root(el) or _is_non_rendered(el) or not el.get("interactive"):
            continue
        bbox = _bbox(el)
        if bbox["w"] <= 0 or bbox["h"] <= 0:
            continue
        # Skip degenerate boxes — zero-size owns those.
        if bbox["w"] < 1 or bbox["h"] < 1:
            continue
        min_side = min(bbox["w"], bbox["h"])
        if min_side >= touch_target_px:
            continue
        selector = el.get("selector") or "unknown"
        findings.append(
            _finding(
                rule_id="touch-target",
                title=f"Touch target too small: {selector}",
                statement=(
                    f"期望可点击区域 min(w,h) ≥ {touch_target_px:.0f}px；"
                    f"实际 min={min_side:.1f}px"
                ),
                el=el,
                route=el.get("route"),
                viewport=el.get("viewport"),
                selector=selector,
                bbox=bbox,
                metrics={
                    "w": bbox["w"],
                    "h": bbox["h"],
                    "min_side": round(min_side, 2),
                    "touch_target_px": touch_target_px,
                },
                severity="high",
                digest="touch-target|below-min",
            )
        )
    return findings


def parse_viewport_size(label: str | None, width: float, height: float | None) -> tuple[float, float]:
    if label:
        text = str(label).strip().lower().replace(" ", "")
        if "x" in text:
            left, _, right = text.partition("x")
            try:
                return float(left), float(right)
            except ValueError:
                pass
    return width, float(height or 0)


def run_layout_rules(
    elements: list[dict[str, Any]],
    *,
    viewport_width: float,
    viewport_height: float | None = None,
    epsilon_px: float = 2.0,
    touch_target_px: float = 44.0,
    overlap_ratio: float = 0.2,
    rules: list[str] | None = None,
) -> list[dict[str, Any]]:
    selected = set(rules) if rules else set(ALL_RULES)
    findings: list[dict[str, Any]] = []
    if "overflow-x" in selected:
        findings.extend(check_overflow_x(elements, viewport_width=viewport_width, epsilon_px=epsilon_px))
    if "text-clip" in selected:
        findings.extend(check_text_clip(elements, epsilon_px=epsilon_px))
    if "overlap-interactive" in selected:
        findings.extend(check_overlap_interactive(elements, overlap_ratio=overlap_ratio))
    if "zero-size" in selected:
        findings.extend(check_zero_size(elements))
    if "off-canvas" in selected and viewport_height:
        findings.extend(
            check_off_canvas(elements, viewport_width=viewport_width, viewport_height=float(viewport_height))
        )
    if "touch-target" in selected:
        findings.extend(check_touch_target(elements, touch_target_px=touch_target_px))
    return findings


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Layout geom probe (Phase 1 full rules)")
    p.add_argument("--viewport-width", type=float, required=True, help="viewport width in px")
    p.add_argument("--viewport-height", type=float, default=None, help="viewport height in px")
    p.add_argument("--epsilon", type=float, default=2.0, help="overflow epsilon px")
    p.add_argument("--touch-target-px", type=float, default=44.0)
    p.add_argument("--overlap-ratio", type=float, default=0.2)
    p.add_argument("--route", default=None)
    p.add_argument("--viewport", default=None)
    p.add_argument(
        "--rules",
        default=None,
        help="comma-separated rule ids; default all",
    )
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
        viewport_width = float(payload.get("viewport_width") or args.viewport_width)
        viewport_height = payload.get("viewport_height") or args.viewport_height
        epsilon = float(payload.get("epsilon_px") or args.epsilon)
        touch = float(payload.get("touch_target_px") or args.touch_target_px)
        overlap = float(payload.get("overlap_ratio") or args.overlap_ratio)
        route = payload.get("route") or args.route
        viewport = payload.get("viewport") or args.viewport
        rules = payload.get("rules") or (
            [r.strip() for r in args.rules.split(",") if r.strip()] if args.rules else None
        )
    else:
        elements = payload
        viewport_width = args.viewport_width
        viewport_height = args.viewport_height
        epsilon = args.epsilon
        touch = args.touch_target_px
        overlap = args.overlap_ratio
        route = args.route
        viewport = args.viewport
        rules = [r.strip() for r in args.rules.split(",") if r.strip()] if args.rules else None

    vw, vh = parse_viewport_size(viewport, viewport_width, viewport_height)

    for el in elements:
        if route and "route" not in el:
            el["route"] = route
        if viewport and "viewport" not in el:
            el["viewport"] = viewport

    findings = run_layout_rules(
        elements,
        viewport_width=vw,
        viewport_height=vh,
        epsilon_px=epsilon,
        touch_target_px=touch,
        overlap_ratio=overlap,
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
