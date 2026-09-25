#!/usr/bin/env python3
"""Build and freeze full-modality test matrix for MMIT-Test."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mit_lib import (  # noqa: E402
    MARKS,
    MODALITIES,
    ensure_mit,
    read_json,
    sha256_text,
    utc_now,
    write_json,
)

# 发布必测底线：命中画像的这些模态至少 optional，安全相关默认 required
BASELINE_REQUIRED = {"code", "api", "web"}
BASELINE_OPTIONAL = {
    "mobile",
    "desktop",
    "cli",
    "db",
    "infra",
    "av",
    "canvas",
    "3d",
    "xr",
    "plugin",
}

EVIDENCE_FLOOR = {
    "code": "测试退出码、lint/audit 报告",
    "api": "contract diff、authz 矩阵、黄金响应",
    "web": "route×viewport、axe/contrast、visual diff",
    "mobile": "冷启动日志、权限流、设备矩阵",
    "desktop": "installer verify、update path、签名状态",
    "cli": "golden exit/stdout/stderr、flag 矩阵",
    "db": "migrate dry-run、restore smoke",
    "infra": "image scan、readiness、secret hygiene",
    "av": "元数据探针、可播冒烟、导出参数",
    "canvas": "scene 与导出交叉验证",
    "3d": "加载日志、预算计数",
    "xr": "session 日志、帧率采样、sim/real 标注",
    "plugin": "host-API pin、install/upgrade 流",
}


def map_profile_to_modalities(profile: dict[str, Any]) -> dict[str, str]:
    """Return modality -> mark (required|optional|n/a) from profile hits."""
    hits: set[str] = set()
    for t in profile.get("app_types") or []:
        t = str(t).lower()
        if t in MODALITIES:
            hits.add(t)
        if t == "web":
            hits.update({"web", "code"})
        if t == "api":
            hits.update({"api", "code", "db"})
        if t == "cli":
            hits.update({"cli", "code"})
        if t == "mobile":
            hits.update({"mobile", "api"})
        if t == "desktop":
            hits.update({"desktop", "code"})
        if t == "infra":
            hits.add("infra")
        if t == "av":
            hits.add("av")
        if t == "canvas":
            hits.add("canvas")
        if t == "3d":
            hits.add("3d")
        if t == "xr":
            hits.add("xr")
        if t == "plugin":
            hits.add("plugin")
        if t == "db":
            hits.add("db")
    plugins = profile.get("plugins") or []
    if plugins:
        hits.add("plugin")
    devices = profile.get("devices") or []
    if any("ios" in str(d) or "android" in str(d) for d in devices):
        hits.add("mobile")
    if any("xr" in str(d) for d in devices):
        hits.add("xr")
    contracts = profile.get("contract_apis") or []
    if contracts and contracts != ["unknown"]:
        hits.add("api")
    if profile.get("topology") not in (None, "", "unknown") and "postgres" in str(profile.get("topology")):
        hits.add("db")

    marks: dict[str, str] = {}
    # If profile is fully unknown / no hits, do NOT blanket n/a — treat code as required floor.
    profile_unknown = (
        not hits
        or profile.get("app_types") in (None, [], ["unknown"])
        or (len(hits) == 1 and "unknown" in hits)
    )
    if profile_unknown:
        hits = {"code"}
    for mod in MODALITIES:
        if mod not in hits:
            marks[mod] = "n/a"
        elif mod in BASELINE_REQUIRED or mod == "code":
            marks[mod] = "required"
        else:
            marks[mod] = "optional"
    # code is required whenever anything is hit
    if hits and marks.get("code") != "required":
        marks["code"] = "required"
    return marks


def build_matrix(profile: dict[str, Any], user_modalities: list[str] | None = None) -> dict[str, Any]:
    marks = map_profile_to_modalities(profile)
    user_modalities = user_modalities or []
    for mod in user_modalities:
        if mod in marks:
            marks[mod] = "required"
    items = []
    for mod in MODALITIES:
        items.append(
            {
                "modality": mod,
                "mark": marks[mod],
                "evidence_floor": EVIDENCE_FLOOR[mod],
                "status": "pending" if marks[mod] != "n/a" else "excluded",
            }
        )
    payload = {
        "version": 1,
        "skill": "mmit-test",
        "matrix_rev": "m1",
        "frozen": False,
        "created_at": utc_now(),
        "profile_hash": sha256_text(json.dumps(profile, sort_keys=True, ensure_ascii=False)),
        "user_modalities": user_modalities,
        "counts": {
            "required": sum(1 for i in items if i["mark"] == "required"),
            "optional": sum(1 for i in items if i["mark"] == "optional"),
            "n/a": sum(1 for i in items if i["mark"] == "n/a"),
        },
        "items": items,
    }
    payload["matrix_hash"] = sha256_text(
        json.dumps({"items": items, "rev": payload["matrix_rev"]}, sort_keys=True, ensure_ascii=False)
    )
    return payload


def freeze_matrix(matrix: dict[str, Any], reason: str = "initial freeze") -> dict[str, Any]:
    matrix = dict(matrix)
    matrix["frozen"] = True
    matrix["frozen_at"] = utc_now()
    matrix["freeze_reason"] = reason
    history = matrix.setdefault("history", [])
    history.append({"matrix_rev": matrix["matrix_rev"], "reason": reason, "at": matrix["frozen_at"]})
    return matrix


def bump_matrix_rev(matrix: dict[str, Any], reason: str) -> dict[str, Any]:
    matrix = dict(matrix)
    old = matrix.get("matrix_rev", "m1")
    if old.startswith("m") and old[1:].isdigit():
        matrix["matrix_rev"] = f"m{int(old[1:]) + 1}"
    else:
        matrix["matrix_rev"] = "m2"
    matrix["frozen"] = False
    history = matrix.setdefault("history", [])
    history.append({"matrix_rev": matrix["matrix_rev"], "reason": reason, "at": utc_now()})
    return matrix


def render_matrix_md(matrix: dict[str, Any]) -> str:
    lines = [
        f"# Test Matrix ({matrix.get('matrix_rev')})",
        "",
        f"- frozen: {matrix.get('frozen')}",
        f"- created: {matrix.get('created_at')}",
        f"- counts: {json.dumps(matrix.get('counts', {}), ensure_ascii=False)}",
        "",
        "| modality | mark | evidence floor | status |",
        "|----------|------|----------------|--------|",
    ]
    for item in matrix.get("items", []):
        lines.append(
            f"| {item['modality']} | {item['mark']} | {item['evidence_floor']} | {item['status']} |"
        )
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build MMIT-Test matrix from profile")
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--profile", type=Path, default=None)
    p.add_argument("--matrix", type=Path, default=None)
    p.add_argument("--user-modality", action="append", default=[], dest="user_modalities")
    p.add_argument("--freeze", action="store_true")
    p.add_argument("--bump", action="store_true", help="bump matrix_rev and unfreeze")
    p.add_argument("--reason", default="")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    mit = ensure_mit(root)
    profile_path = args.profile or (mit / "profile.json")
    matrix_path = args.matrix or (mit / "matrix.json")
    if not profile_path.exists():
        print(f"error: profile not found: {profile_path}", file=sys.stderr)
        return 2
    profile = read_json(profile_path)

    if args.bump:
        if not matrix_path.exists():
            print(f"error: matrix not found for bump: {matrix_path}", file=sys.stderr)
            return 2
        old = read_json(matrix_path)
        # Re-derive marks from current profile, keep rev history bump
        fresh = build_matrix(profile, args.user_modalities or old.get("user_modalities") or [])
        matrix = bump_matrix_rev(fresh, args.reason or "bump")
    else:
        matrix = build_matrix(profile, args.user_modalities)

    if args.freeze:
        matrix = freeze_matrix(matrix, args.reason or "initial freeze")

    write_json(matrix_path, matrix)
    md_path = mit / "matrix.md"
    md_path.write_text(render_matrix_md(matrix), encoding="utf-8")
    print(f"matrix written: {matrix_path} rev={matrix['matrix_rev']} frozen={matrix['frozen']}")
    print(json.dumps(matrix["counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
