#!/usr/bin/env python3
"""Assemble TEST_REPORT.md (10 sections) for MMIT-Test."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mit_lib import ensure_mit, load_state, read_json, utc_now  # noqa: E402


def _load(root: Path, name: str) -> Any:
    p = ensure_mit(root) / name
    if p.exists():
        return read_json(p)
    return {}


def build_report(root: Path) -> str:
    state = _load(root, "state.json") or load_state(root)
    profile = _load(root, "profile.json")
    matrix = _load(root, "matrix.json")
    env = _load(root, "env_manifest.json")
    mask = _load(root, "data_mask_report.json")
    devices = _load(root, "device_probe.json")
    prod = _load(root, "prod_test_results.json")
    rc_id = f"RC-{state.get('rc_n', 0)}"
    results_path = ensure_mit(root) / "runs" / rc_id / "findings" / "matrix_results.json"
    results = read_json(results_path) if results_path.exists() else {"results": []}

    counts = matrix.get("counts", {})
    items = matrix.get("items", [])
    lines: list[str] = []
    lines += [
        "# 测试报告 TEST_REPORT",
        "",
        "## 1. 执行摘要",
        "",
        f"- 项目: `{profile.get('root', root)}`",
        f"- RC: `{rc_id}`  rc_sha: `{state.get('rc_sha')}`",
        f"- 轮次: {state.get('round')}  matrix_rev: `{state.get('matrix_rev')}`",
        f"- 生成时间: {utc_now()}",
        f"- 结论草稿: `{state.get('decision', 'in_progress')}`",
        "",
        "## 2. 项目画像与矩阵覆盖",
        "",
        f"- app_types: {profile.get('app_types')}",
        f"- runtime: {profile.get('runtime')}",
        f"- topology: {profile.get('topology')}",
        f"- counts: required={counts.get('required')} optional={counts.get('optional')} n/a={counts.get('n/a')}",
        "",
        "## 3. 环境与设备",
        "",
        f"- E0: {json.dumps(env.get('layers', {}).get('E0', {}), ensure_ascii=False)}",
        f"- E1: {json.dumps(env.get('layers', {}).get('E1', {}), ensure_ascii=False)}",
        f"- E2: {json.dumps(env.get('layers', {}).get('E2', {}), ensure_ascii=False)}",
        f"- E3: {json.dumps(env.get('layers', {}).get('E3', {}), ensure_ascii=False)}",
        f"- device coverage: {devices.get('coverage')} (all_sim={devices.get('all_sim')})",
        f"- 脱敏: clean={mask.get('clean')} count={mask.get('count')}",
        "",
        "## 4. 分模态测试结果",
        "",
        "| modality | mark | status | notes |",
        "|----------|------|--------|-------|",
    ]
    by_mod = {r["modality"]: r for r in results.get("results", [])}
    for item in items:
        r = by_mod.get(item["modality"], {})
        lines.append(
            f"| {item['modality']} | {item['mark']} | {r.get('status', item.get('status', 'pending'))} | {r.get('notes', '')} |"
        )
    lines += [
        "",
        "## 5. 缺陷清单与修复/回归",
        "",
        f"- open_defects: {json.dumps(state.get('open_defects', {}), ensure_ascii=False)}",
        "- 详见 `.mit/defects/`；无回归不得标记 fixed。",
        "",
        "## 6. 真实生产环境测试结果",
        "",
    ]
    if prod.get("available"):
        lines += [f"- mode: {prod.get('mode')}", f"- critical_path_pass: {prod.get('critical_path_pass')}", ""]
    else:
        md = prod.get("missing_declaration", {})
        lines += [
            "**缺失**",
            "",
            f"- reason: {md.get('reason', 'prod results unavailable')}",
            f"- impact: {md.get('impact', 'PRD missing; unconditional Allow forbidden')}",
            f"- recommended: {md.get('recommended', 'conditional Allow or Deny/Escalate')}",
            "",
        ]
    blinds = state.get("blinds", [])
    lines += ["## 7. 盲区与降级（Blind Spots）", ""]
    if blinds:
        for b in blinds:
            lines.append(f"- `{b.get('id')}`: {b.get('reason')}")
    else:
        lines.append("- （无）")
    lines += [
        "",
        "## 8. Known Issues",
        "",
        "- 见 defects 中 P2/P3 及用户接受记录（若有）。",
        "",
        "## 9. 裁决信号摘要",
        "",
        f"- quiet_streak: {state.get('quiet_streak')}",
        f"- signals: `{json.dumps(state.get('signals', {}), ensure_ascii=False)}`",
        "",
        "## 10. 证据包索引",
        "",
        "- 见 `.mit/deliverables/EVIDENCE_INDEX.md` 与 `.mit/deliverables/evidence/`。",
        "",
    ]
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Assemble TEST_REPORT.md")
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--out", type=Path, default=None)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    text = build_report(root)
    out = args.out or (ensure_mit(root) / "deliverables" / "TEST_REPORT.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    # minimal evidence index
    evidence_dir = ensure_mit(root) / "deliverables" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    state = _load(root, "state.json")
    index = evidence_dir.parent / "EVIDENCE_INDEX.md"
    index.write_text(
        "# EVIDENCE_INDEX\n\n"
        f"- generated: {utc_now()}\n"
        f"- rc_id: RC-{state.get('rc_n', 0)}\n"
        f"- rc_sha: `{state.get('rc_sha')}`\n"
        f"- matrix_rev: `{state.get('matrix_rev')}`\n"
        "- 证据目录: `evidence/`\n"
        "- 矩阵执行: `runs/RC-*/findings/matrix_results.json`\n"
        "- 脱敏: `data_mask_report.json`（命中已脱敏）\n"
        "- 生产: `prod_test_results.json` 或 `PROD_RESULTS_MISSING.md`\n",
        encoding="utf-8",
    )
    print(f"TEST_REPORT written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
