#!/usr/bin/env python3
"""vlm-audit dual-perspective candidate merger (Phase 2).

Does not call a VLM. Merges two independently authored view JSON files into
consensus candidates, then cross-checks against machine findings so the same
issue is not double-counted.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# Machine finding families that can corroborate VLM candidates
RULE_FAMILY = {
    "overflow-x": "layout",
    "text-clip": "layout",
    "overlap-interactive": "layout",
    "zero-size": "layout",
    "off-canvas": "layout",
    "touch-target": "layout",
    "contrast-text": "visual",
    "font-too-small": "visual",
    "line-height-tight": "visual",
    "dead-link": "ux",
    "missing-feedback": "ux",
    "missing-empty-state": "ux",
    "ux-flow-step": "ux",
    "safe-area-violation": "canvas",
    "export-mismatch": "canvas",
    "z-order-occlusion": "canvas",
    "low-res-asset": "canvas",
    "aspect-distort": "canvas",
    "visual-diff": "visual",
}


def _norm_text(value: str) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-z0-9一-鿿/:._\- ]+", "", text)
    return text.strip()


def _title_distance(a: str, b: str) -> float:
    """Normalized Levenshtein-ish ratio in [0,1]; 0 = identical."""
    ta, tb = _norm_text(a), _norm_text(b)
    if not ta and not tb:
        return 0.0
    if not ta or not tb:
        return 1.0
    # cheap similarity: 1 - jaccard on char trigrams + length ratio
    def trigrams(s: str) -> set[str]:
        if len(s) < 3:
            return {s}
        return {s[i : i + 3] for i in range(len(s) - 2)}

    sa, sb = trigrams(ta), trigrams(tb)
    inter = len(sa & sb)
    union = len(sa | sb) or 1
    jaccard = inter / union
    return 1.0 - jaccard


def bbox_iou(a: dict[str, Any] | None, b: dict[str, Any] | None) -> float:
    if not a or not b:
        return 0.0
    try:
        ax1 = float(a.get("x") or 0)
        ay1 = float(a.get("y") or 0)
        ax2 = ax1 + float(a.get("w") or 0)
        ay2 = ay1 + float(a.get("h") or 0)
        bx1 = float(b.get("x") or 0)
        by1 = float(b.get("y") or 0)
        bx2 = bx1 + float(b.get("w") or 0)
        by2 = by1 + float(b.get("h") or 0)
    except (TypeError, ValueError):
        return 0.0
    ix = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = ix * iy
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return inter / union


def normalize_candidate(raw: dict[str, Any], *, view: str) -> dict[str, Any]:
    loc = raw.get("location") or {}
    bbox = loc.get("bbox") or raw.get("bbox")
    return {
        "view": view,
        "title": raw.get("title") or raw.get("problem") or raw.get("description") or "",
        "problem": raw.get("problem") or raw.get("description") or raw.get("title") or "",
        "confidence": float(raw.get("confidence") or 0.5),
        "location": {
            "route": loc.get("route") or raw.get("route"),
            "viewport": loc.get("viewport") or raw.get("viewport"),
            "selector": loc.get("selector") or raw.get("selector"),
            "bbox": bbox,
        },
        "category_hint": raw.get("category") or raw.get("category_hint"),
        "inferred_oracle": True,
    }


def load_view(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"view file must be object: {path}")
    data.setdefault("view", path.stem)
    data.setdefault("candidates", [])
    return data


def locations_match(a: dict[str, Any], b: dict[str, Any], *, iou_threshold: float = 0.3) -> bool:
    la = a.get("location") or {}
    lb = b.get("location") or {}
    if (la.get("route") or "") != (lb.get("route") or ""):
        return False
    if (la.get("viewport") or "") != (lb.get("viewport") or ""):
        # allow missing viewport on one side
        if la.get("viewport") and lb.get("viewport"):
            return False
    sa = la.get("selector")
    sb = lb.get("selector")
    if sa and sb and sa == sb:
        return True
    if sa and sb and (sa in sb or sb in sa):
        return True
    iou = bbox_iou(la.get("bbox"), lb.get("bbox"))
    if iou >= iou_threshold:
        return True
    # title proximity on same route
    if _title_distance(a.get("title") or "", b.get("title") or "") < 0.3:
        return True
    return False


def merge_views(
    view_a: dict[str, Any],
    view_b: dict[str, Any],
    *,
    min_agreement: int = 2,
) -> list[dict[str, Any]]:
    """Return consensus candidates (view A × view B)."""
    if min_agreement < 2:
        min_agreement = 2
    cands_a = [normalize_candidate(c, view=str(view_a.get("view") or "a")) for c in view_a.get("candidates") or []]
    cands_b = [normalize_candidate(c, view=str(view_b.get("view") or "b")) for c in view_b.get("candidates") or []]
    consensus: list[dict[str, Any]] = []
    used_b: set[int] = set()
    for ca in cands_a:
        match_idx = None
        for i, cb in enumerate(cands_b):
            if i in used_b:
                continue
            if locations_match(ca, cb):
                match_idx = i
                break
        if match_idx is None:
            continue
        cb = cands_b[match_idx]
        used_b.add(match_idx)
        # Prefer longer / more specific title
        title = ca["title"] if len(ca["title"]) >= len(cb["title"]) else cb["title"]
        confidence = max(ca.get("confidence") or 0, cb.get("confidence") or 0)
        consensus.append(
            {
                "rule_id": "vlm-consensus",
                "modality": "web-visual",
                "category": ca.get("category_hint") or cb.get("category_hint") or "ui-ux-flow",
                "severity": "medium",
                "title": title,
                "statement": (
                    f"双视角 VLM 一致：A[{ca['view']}] 与 B[{cb['view']}] 均指出 — "
                    f"{ca['problem']}"
                ),
                "location": {
                    "surface": "web",
                    "route": (ca["location"].get("route") or cb["location"].get("route")),
                    "viewport": (ca["location"].get("viewport") or cb["location"].get("viewport")),
                    "selector": (ca["location"].get("selector") or cb["location"].get("selector")),
                    "bbox": ca["location"].get("bbox") or cb["location"].get("bbox"),
                },
                "metrics": {
                    "confidence": confidence,
                    "views": [ca["view"], cb["view"]],
                    "problems": [ca["problem"], cb["problem"]],
                },
                "evidence_level_target": "L2",
                "detected_by": "vlm-audit",
                "core_assertion_digest": "vlm-consensus|dual-view",
                "inferred_oracle": True,
                "status": "candidate",
                "agreement": min_agreement,
            }
        )
    return consensus


def load_raw_findings(raw_dir: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not raw_dir.exists():
        return findings
    for path in sorted(raw_dir.rglob("*.json")):
        try:
            with path.open("r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except Exception:
            continue
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("rule_id"):
                    findings.append(item)
        elif isinstance(data, dict):
            if data.get("rule_id"):
                findings.append(data)
            for item in data.get("findings") or []:
                if isinstance(item, dict):
                    findings.append(item)
    return findings


def cross_check(
    consensus: list[dict[str, Any]],
    raw_findings: list[dict[str, Any]],
    *,
    iou_threshold: float = 0.3,
) -> dict[str, Any]:
    """Attach VLM corroboration to machine findings instead of double-counting."""
    standalone: list[dict[str, Any]] = []
    corroboration: list[dict[str, Any]] = []
    for cand in consensus:
        matched = None
        for raw in raw_findings:
            # same route/viewport + selector or bbox overlap
            cl = cand.get("location") or {}
            rl = raw.get("location") or {}
            if (cl.get("route") or "") and (rl.get("route") or "") and cl.get("route") != rl.get("route"):
                continue
            if (
                cl.get("viewport")
                and rl.get("viewport")
                and cl.get("viewport") != rl.get("viewport")
            ):
                continue
            sel_c = cl.get("selector") or ""
            sel_r = rl.get("selector") or ""
            sel_match = bool(sel_c and sel_r and (sel_c == sel_r or sel_c in sel_r or sel_r in sel_c))
            iou = bbox_iou(cl.get("bbox"), rl.get("bbox"))
            if sel_match or iou >= iou_threshold:
                matched = raw
                break
            # family keyword overlap in titles for layout overflow etc.
            if RULE_FAMILY.get(str(raw.get("rule_id"))) in ("layout",) and _title_distance(
                cand.get("title") or "", raw.get("title") or ""
            ) < 0.35:
                matched = raw
                break
        if matched is None:
            standalone.append(cand)
            continue
        metrics = dict(matched.get("metrics") or {})
        prev = metrics.get("vlm_corroboration") or []
        if not isinstance(prev, list):
            prev = [prev]
        prev.append(
            {
                "title": cand.get("title"),
                "views": (cand.get("metrics") or {}).get("views"),
                "confidence": (cand.get("metrics") or {}).get("confidence"),
            }
        )
        metrics["vlm_corroboration"] = prev
        matched["metrics"] = metrics
        corroboration.append(
            {
                "machine_rule_id": matched.get("rule_id"),
                "machine_title": matched.get("title"),
                "vlm_title": cand.get("title"),
            }
        )
    return {
        "standalone": standalone,
        "corroboration": corroboration,
        "merged_into_machine": len(corroboration),
    }


def scaffold_views(
    *,
    screenshot: str,
    route: str,
    viewport: str,
    perspective_a: str = "布局/信息层级/裁切/重叠",
    perspective_b: str = "空状态/错误反馈/可点性/死路",
) -> tuple[dict[str, Any], dict[str, Any]]:
    base = {
        "screenshot": screenshot,
        "route": route,
        "viewport": viewport,
        "candidates": [],
        "instructions": (
            "仅列出可定位的 UI 问题；每条含 title/problem/location.selector 或 bbox/confidence。"
            "不要输出纯审美偏好。"
        ),
    }
    view_a = dict(base)
    view_a["view"] = "A"
    view_a["perspective"] = perspective_a
    view_b = dict(base)
    view_b["view"] = "B"
    view_b["perspective"] = perspective_b
    return view_a, view_b


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="vlm-audit dual-view merge")
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("merge", help="merge two VLM views and cross-check raw findings")
    m.add_argument("--view-a", required=True)
    m.add_argument("--view-b", required=True)
    m.add_argument("--raw-dir", help="directory of machine findings")
    m.add_argument("--out", help="write consensus JSON")
    m.add_argument("--min-agreement", type=int, default=2)

    s = sub.add_parser("scaffold", help="write empty dual-view templates")
    s.add_argument("--screenshot", required=True)
    s.add_argument("--route", default="/")
    s.add_argument("--viewport", default="375x812")
    s.add_argument("--out-a", required=True)
    s.add_argument("--out-b", required=True)

    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.cmd == "scaffold":
        a, b = scaffold_views(
            screenshot=args.screenshot, route=args.route, viewport=args.viewport
        )
        for path, data in ((args.out_a, a), (args.out_b, b)):
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
        print(json.dumps({"ok": True, "out_a": args.out_a, "out_b": args.out_b}, ensure_ascii=False))
        return 0

    view_a = load_view(Path(args.view_a).resolve())
    view_b = load_view(Path(args.view_b).resolve())
    consensus = merge_views(view_a, view_b, min_agreement=args.min_agreement)
    raw = load_raw_findings(Path(args.raw_dir).resolve()) if args.raw_dir else []
    cross = cross_check(consensus, raw)
    result = {
        "ok": True,
        "consensus_count": len(cross["standalone"]) + len(cross["corroboration"]),
        "standalone": cross["standalone"],
        "corroboration": cross["corroboration"],
        "merged_into_machine": cross["merged_into_machine"],
        "inferred_oracle": True,
    }
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
