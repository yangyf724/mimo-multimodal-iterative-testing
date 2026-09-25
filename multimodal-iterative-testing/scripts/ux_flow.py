#!/usr/bin/env python3
"""ux-flow probe: static UX rules + WebTestPilot-style symbolic steps (Phase 2)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

DEAD_HREFS = {"", "#", "javascript:void(0)", "javascript:void(0);", "javascript:;"}

FEEDBACK_SELECTORS_HINTS = (
    "[role=alert]",
    "[data-testid*=error]",
    "[data-testid*=toast]",
    "[data-feedback]",
    "[data-empty-state]",
    ".error",
    ".toast",
    ".alert",
)

SUBMIT_HINTS = re.compile(r"submit|提交", re.I)


def _finding(
    *,
    rule_id: str,
    title: str,
    statement: str,
    route: str | None,
    viewport: str | None,
    selector: str,
    bbox: dict[str, float] | None,
    metrics: dict[str, Any],
    severity: str,
    digest: str,
    detected_by: str = "ux-flow",
    evidence_level: str = "L3",
    inferred_oracle: bool = False,
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "modality": "web-visual",
        "category": "ui-ux-flow",
        "severity": severity,
        "title": title,
        "statement": statement,
        "location": {
            "surface": "web",
            "route": route,
            "viewport": viewport,
            "selector": selector,
            "bbox": bbox,
        },
        "metrics": metrics,
        "evidence_level_target": evidence_level,
        "detected_by": detected_by,
        "core_assertion_digest": digest,
        "inferred_oracle": inferred_oracle,
    }


def _el_route(el: dict[str, Any], route: str | None) -> str | None:
    return route or el.get("route")


def _el_viewport(el: dict[str, Any], viewport: str | None) -> str | None:
    return viewport or el.get("viewport")


def check_dead_link(
    elements: list[dict[str, Any]],
    *,
    route: str | None = None,
    viewport: str | None = None,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for el in elements:
        selector = str(el.get("selector") or "")
        tag = str(el.get("tag") or "").lower()
        href = el.get("href")
        if href is None and "href" in (el.get("attrs") or {}):
            href = (el.get("attrs") or {}).get("href")
        # elements.json may carry href only via selector text or dedicated field
        if href is None and tag == "a":
            href = el.get("href")
        if href is None:
            # Infer from raw selector patterns like a[href="#"]
            m = re.search(r'href=["\']([^"\']*)["\']', selector)
            if m:
                href = m.group(1)
            elif el.get("attrs") and isinstance(el["attrs"], dict):
                href = el["attrs"].get("href")
        if href is None:
            # Dedicated data field used by fixtures / extended capture
            href = el.get("link_href")
        if href is None:
            continue
        href_norm = str(href).strip().lower()
        if href_norm not in DEAD_HREFS:
            continue
        findings.append(
            _finding(
                rule_id="dead-link",
                title=f"Dead link: {selector or tag}",
                statement=f"期望导航链接有有效目标；实际 href={href!r}（占位/空）",
                route=_el_route(el, route),
                viewport=_el_viewport(el, viewport),
                selector=selector or "a[href]",
                bbox=el.get("bbox"),
                metrics={"href": href},
                severity="medium",
                digest="dead-link|href-stub",
            )
        )
    return findings


def _is_feedback_sink(el: dict[str, Any]) -> bool:
    sel = str(el.get("selector") or "").lower()
    attrs = el.get("attrs") or {}
    role = (el.get("role") or attrs.get("role") or "").lower()
    testid = str(attrs.get("data-testid") or "")
    return (
        "[role=alert]" in sel
        or "data-testid=contact-error" in sel
        or "data-testid*=error" in sel
        or role == "alert"
        or "error" in testid.lower()
        or "toast" in testid.lower()
        or "error" in sel
        or "toast" in sel
        or el.get("is_feedback") is True
    )


def _is_visible(el: dict[str, Any]) -> bool:
    bbox = el.get("bbox") or {}
    w = float(bbox.get("w") or 0)
    h = float(bbox.get("h") or 0)
    if w < 1 or h < 1:
        # Static captures often freeze sinks before interaction; existence of a
        # dedicated feedback node is enough for post-condition `.visible` when
        # the element is a known alert/error sink.
        return _is_feedback_sink(el) and bool((el.get("text") or "").strip())
    return bool(el.get("inViewport", True))


def _selector_matches(el_selector: str, pattern: str) -> bool:
    if not el_selector or not pattern:
        return False
    if el_selector == pattern:
        return True
    # pattern may be a loose contains match for fixture tags
    if pattern in el_selector:
        return True
    return False


def check_missing_feedback(
    elements: list[dict[str, Any]],
    *,
    route: str | None = None,
    viewport: str | None = None,
) -> list[dict[str, Any]]:
    has_submit = False
    submit_el: dict[str, Any] | None = None
    has_feedback = False
    for el in elements:
        selector = str(el.get("selector") or "")
        tag = str(el.get("tag") or "").lower()
        el_type = str(el.get("type") or (el.get("attrs") or {}).get("type") or "").lower()
        if not has_submit:
            is_submit = (
                (tag == "button" and el_type == "submit")
                or (tag == "input" and el_type == "submit")
                or bool(SUBMIT_HINTS.search(selector))
                or bool(SUBMIT_HINTS.search(str(el.get("text") or "")))
            )
            # Avoid false positive on every primary button without submit marker:
            # require explicit type=submit or data-testid containing submit / role=button with form context.
            explicit = (
                el_type == "submit"
                or "submit" in selector.lower()
                or "[data-testid=flow-submit]" in selector
                or el.get("is_submit") is True
            )
            if is_submit and explicit:
                has_submit = True
                submit_el = el
        sel_l = selector.lower()
        text_l = str(el.get("text") or "").lower()
        if (
            "[role=alert]" in sel_l
            or "[data-testid*=error]" in sel_l
            or "data-testid=flow-error" in sel_l
            or "data-testid=flow-toast" in sel_l
            or "[data-feedback]" in sel_l
            or el.get("role") == "alert"
            or el.get("is_feedback") is True
            or "error" in sel_l
            or "toast" in sel_l
        ):
            has_feedback = True
    if not has_submit or has_feedback:
        return []
    el = submit_el or {}
    return [
        _finding(
            rule_id="missing-feedback",
            title="Submit control without visible feedback sink",
            statement=(
                "期望提交控件同路由存在 error/toast/alert 反馈节点；"
                "实际未检测到 [role=alert]/[data-testid*=error|toast]/[data-feedback]"
            ),
            route=_el_route(el, route),
            viewport=_el_viewport(el, viewport),
            selector=str(el.get("selector") or "button[type=submit]"),
            bbox=el.get("bbox"),
            metrics={"feedback_selector_hints": list(FEEDBACK_SELECTORS_HINTS)},
            severity="medium",
            digest="missing-feedback|no-error-sink",
            inferred_oracle=True,
        )
    ]


def check_missing_empty_state(
    elements: list[dict[str, Any]],
    *,
    route: str | None = None,
    viewport: str | None = None,
    empty_state_attr: str = "data-empty-state",
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    # Containers explicitly marked as expecting an empty state when empty
    expected_containers = []
    for el in elements:
        selector = str(el.get("selector") or "")
        attrs = el.get("attrs") or {}
        flag = attrs.get("data-list-empty") or el.get("data-list-empty") or el.get("list_empty_expected")
        if flag in ("expected", True, "true"):
            expected_containers.append(el)
        elif "data-list-empty" in selector:
            expected_containers.append(el)
    if not expected_containers:
        return []
    has_placeholder = any(
        empty_state_attr in str(el.get("selector") or "")
        or (el.get("attrs") or {}).get(empty_state_attr) is not None
        or el.get("is_empty_state") is True
        for el in elements
    )
    for el in expected_containers:
        # If container has visible child items beyond itself, skip
        child_count = el.get("visible_child_count")
        if child_count is None:
            child_count = el.get("item_count")
        if child_count is not None and int(child_count) > 0:
            continue
        if has_placeholder:
            continue
        findings.append(
            _finding(
                rule_id="missing-empty-state",
                title=f"List missing empty state: {el.get('selector')}",
                statement=(
                    f"期望空列表容器展示 {empty_state_attr} 占位；实际未找到占位节点"
                ),
                route=_el_route(el, route),
                viewport=_el_viewport(el, viewport),
                selector=str(el.get("selector") or "list"),
                bbox=el.get("bbox"),
                metrics={"empty_state_attr": empty_state_attr, "child_count": child_count},
                severity="medium",
                digest="missing-empty-state|no-placeholder",
                inferred_oracle=True,
            )
        )
    return findings


def run_static_ux_rules(
    elements: list[dict[str, Any]],
    *,
    route: str | None = None,
    viewport: str | None = None,
    empty_state_attr: str = "data-empty-state",
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    out.extend(check_dead_link(elements, route=route, viewport=viewport))
    out.extend(check_missing_feedback(elements, route=route, viewport=viewport))
    out.extend(check_missing_empty_state(
        elements, route=route, viewport=viewport, empty_state_attr=empty_state_attr
    ))
    return out


def find_element(
    elements: list[dict[str, Any]],
    selector: str,
) -> dict[str, Any] | None:
    for el in elements:
        if _selector_matches(str(el.get("selector") or ""), selector):
            return el
    # Also match data-testid exact from selector field
    bare = selector.strip("[]")
    if bare.startswith("data-testid="):
        tid = bare.split("=", 1)[1].strip("\"'")
        for el in elements:
            if el.get("testid") == tid or f"[data-testid={tid}]" == el.get("selector"):
                return el
    return None


def evaluate_condition(
    condition: str,
    *,
    elements: list[dict[str, Any]],
    symbols: dict[str, Any],
    state_data: dict[str, Any] | None,
) -> tuple[bool | None, dict[str, Any]]:
    """Return (observed_bool_or_None_if_unavailable, metrics)."""
    cond = condition.strip()
    # symbol boolean: formValid
    if "." not in cond:
        if cond in symbols:
            val = symbols[cond]
            if isinstance(val, bool):
                return val, {"symbol": cond, "value": val}
        if state_data and cond in state_data:
            val = state_data[cond]
            if isinstance(val, bool):
                return val, {"state": cond, "value": val}
        return None, {"unavailable": cond}

    # selector.visible / selector.exists / text_contains
    if cond.endswith(".visible") or cond.endswith(".exists"):
        sel = cond.rsplit(".", 1)[0]
        # Resolve symbol aliases: symbols.submitBtn -> selector string
        if sel in symbols and isinstance(symbols[sel], str):
            sel = symbols[sel]
        el = find_element(elements, sel)
        if el is None:
            if cond.endswith(".exists"):
                return False, {"selector": sel, "exists": False}
            return False, {"selector": sel, "visible": False, "missing": True}
        if cond.endswith(".exists"):
            return True, {"selector": sel, "exists": True}
        vis = _is_visible(el)
        return vis, {"selector": sel, "visible": vis, "bbox": el.get("bbox")}

    m = re.match(r"text_contains\(([^,]+),\s*(.+)\)$", cond)
    if m:
        sel = m.group(1).strip().strip("\"'")
        if sel in symbols and isinstance(symbols[sel], str):
            sel = symbols[sel]
        needle = m.group(2).strip().strip("\"'")
        el = find_element(elements, sel)
        if el is None:
            return False, {"selector": sel, "missing": True}
        text = str(el.get("text") or "")
        ok = needle in text
        return ok, {"selector": sel, "needle": needle, "text": text[:80]}

    # Unknown form
    return None, {"unavailable": cond}


def load_flow(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"flow must be object: {path}")
    data.setdefault("id", path.stem)
    data.setdefault("inferred_oracle", True)
    data.setdefault("steps", [])
    data.setdefault("symbols", {})
    return data


def evaluate_flow(
    flow: dict[str, Any],
    elements: list[dict[str, Any]],
    *,
    state_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    symbols = dict(flow.get("symbols") or {})
    route = flow.get("route") or (elements[0].get("route") if elements else None)
    viewport = flow.get("viewport") or (elements[0].get("viewport") if elements else None)
    findings: list[dict[str, Any]] = []
    step_results: list[dict[str, Any]] = []
    unavailable = False

    for idx, step in enumerate(flow.get("steps") or []):
        step_id = step.get("id") or f"step-{idx + 1}"
        pre = step.get("pre") or {}
        post = step.get("post") or {}
        pre_metrics: dict[str, Any] = {}
        post_metrics: dict[str, Any] = {}
        pre_ok = True
        post_ok = True
        step_unavailable = False

        for cond, expected in pre.items():
            observed, metrics = evaluate_condition(
                cond, elements=elements, symbols=symbols, state_data=state_data
            )
            pre_metrics[cond] = {"expected": expected, "observed": observed, **metrics}
            if observed is None:
                step_unavailable = True
            elif bool(observed) != bool(expected):
                pre_ok = False

        for cond, expected in post.items():
            observed, metrics = evaluate_condition(
                cond, elements=elements, symbols=symbols, state_data=state_data
            )
            post_metrics[cond] = {"expected": expected, "observed": observed, **metrics}
            if observed is None:
                step_unavailable = True
            elif bool(observed) != bool(expected):
                post_ok = False

        status = "pass"
        if step_unavailable:
            status = "unavailable"
            unavailable = True
        elif not pre_ok:
            status = "pre-failed"
        elif not post_ok:
            status = "fail"

        step_results.append(
            {
                "id": step_id,
                "action": step.get("action"),
                "target": step.get("target"),
                "status": status,
                "pre": pre_metrics,
                "post": post_metrics,
            }
        )

        if status == "fail":
            failed_posts = {
                k: v for k, v in post_metrics.items() if v.get("observed") != v.get("expected")
            }
            findings.append(
                _finding(
                    rule_id="ux-flow-step",
                    title=f"UX flow step failed: {flow.get('id')} / {step_id}",
                    statement=(
                        f"期望 {step.get('action')}({step.get('target')}) 后 post 条件满足 "
                        f"{list(post.keys())}；实际失败条件 {list(failed_posts.keys())}"
                    ),
                    route=route,
                    viewport=viewport,
                    selector=str(step.get("target") or step.get("action") or "flow"),
                    bbox=None,
                    metrics={
                        "flow_id": flow.get("id"),
                        "step_id": step_id,
                        "action": step.get("action"),
                        "target": step.get("target"),
                        "pre": pre_metrics,
                        "post": post_metrics,
                        "failed_posts": failed_posts,
                    },
                    severity="high",
                    digest="ux-flow-step|post-condition",
                    inferred_oracle=bool(flow.get("inferred_oracle", True)),
                )
            )

    return {
        "flow_id": flow.get("id"),
        "route": route,
        "viewport": viewport,
        "status": "unavailable" if unavailable and not findings else ("fail" if findings else "pass"),
        "steps": step_results,
        "findings": findings,
        "unavailable": unavailable,
        "inferred_oracle": bool(flow.get("inferred_oracle", True)),
    }


def load_elements(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return list(data.get("elements") or [])
    return []


def run_ux_on_manifest(
    *,
    manifest_path: Path,
    flows_dir: Path | None = None,
    oracle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    oracle = oracle or {}
    empty_attr = str(oracle.get("ux_empty_state_attr", "data-empty-state"))
    with manifest_path.open("r", encoding="utf-8-sig") as f:
        manifest = json.load(f)
    captures_dir = manifest_path.parent
    findings: list[dict[str, Any]] = []
    flow_results: list[dict[str, Any]] = []
    cells = 0

    # Index cells for flow matching
    cell_elements: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in manifest.get("items") or []:
        if item.get("status") != "ok" or not item.get("elements_json"):
            continue
        elements_path = captures_dir / str(item["elements_json"])
        if not elements_path.exists():
            continue
        elements = load_elements(elements_path)
        route = item.get("route")
        viewport = item.get("viewport")
        cell_elements[(str(route), str(viewport))] = elements
        cells += 1
        findings.extend(
            run_static_ux_rules(
                elements, route=route, viewport=viewport, empty_state_attr=empty_attr
            )
        )

    if flows_dir and flows_dir.exists():
        for flow_path in sorted(flows_dir.glob("*.json")):
            flow = load_flow(flow_path)
            key = (str(flow.get("route")), str(flow.get("viewport")))
            elements = cell_elements.get(key)
            if elements is None:
                # try any cell with same route
                for (r, v), els in cell_elements.items():
                    if r == str(flow.get("route")):
                        elements = els
                        break
            if elements is None:
                flow_results.append(
                    {
                        "flow_id": flow.get("id"),
                        "status": "unavailable",
                        "reason": "no-matching-capture-cell",
                        "findings": [],
                    }
                )
                continue
            result = evaluate_flow(flow, elements)
            flow_results.append(result)
            findings.extend(result["findings"])

    return {
        "findings": findings,
        "flows": flow_results,
        "cells_scanned": cells,
        "flows_dir": str(flows_dir) if flows_dir else None,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ux-flow static rules + symbolic steps")
    p.add_argument("--elements", help="elements.json path")
    p.add_argument("--flow", help="single flow JSON path")
    p.add_argument("--state-json", dest="state_json", help="optional page state JSON")
    p.add_argument("--manifest", help="MANIFEST.json path for multi-cell static rules")
    p.add_argument("--flows", help="flows directory")
    p.add_argument("--out", help="write findings JSON")
    p.add_argument("--out-dir", dest="out_dir", help="write per-strategy files")
    p.add_argument(
        "--fp-patterns",
        dest="fp_patterns",
        default=None,
        help="optional FP whitelist JSON; matching findings get status=suppressed",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.manifest:
        result = run_ux_on_manifest(
            manifest_path=Path(args.manifest).resolve(),
            flows_dir=Path(args.flows).resolve() if args.flows else None,
        )
    elif args.elements:
        elements = load_elements(Path(args.elements).resolve())
        findings = run_static_ux_rules(elements)
        flow_results = []
        if args.flow:
            flow = load_flow(Path(args.flow).resolve())
            state_data = None
            if args.state_json:
                with Path(args.state_json).open("r", encoding="utf-8-sig") as f:
                    state_data = json.load(f)
            fr = evaluate_flow(flow, elements, state_data=state_data)
            flow_results.append(fr)
            findings.extend(fr["findings"])
        result = {"findings": findings, "flows": flow_results}
    else:
        print(
            json.dumps({"ok": False, "error": "--manifest or --elements required"}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2

    result["ok"] = True
    if args.fp_patterns:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import fp_feedback as fpf  # noqa: PLC0415

        findings, hits = fpf.apply_patterns_path(result.get("findings") or [], Path(args.fp_patterns))
        result["findings"] = findings
        result["suppressed_count"] = len(hits)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write("\n")
    if args.out_dir:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        with (out_dir / "ux-flow__findings.json").open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
