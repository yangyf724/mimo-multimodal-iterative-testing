#!/usr/bin/env python3
"""Acceptance hunt runner for examples/second-project (fixture path)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"D:\BaiduSyncdisk\project\MiMo Multimodal Iterative Testing\examples\second-project")
SCRIPTS = Path(r"D:\BaiduSyncdisk\project\MiMo Multimodal Iterative Testing\mmit-hunter\scripts")


def w(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    caps = ROOT / ".bug-hunter" / "runs" / "run-1" / "captures"
    caps.mkdir(parents=True, exist_ok=True)

    w(
        caps / "home__375x812__elements.json",
        {
            "route": "/",
            "viewport": "375x812",
            "elements": [
                {
                    "selector": "html",
                    "tag": "html",
                    "scrollWidth": 375,
                    "clientWidth": 375,
                    "bbox": {"x": 0, "y": 0, "w": 375, "h": 812},
                    "text": "",
                    "depth": 0,
                },
                {
                    "selector": ".helper-note",
                    "tag": "p",
                    "interactive": False,
                    "bbox": {"x": 16, "y": 200, "w": 300, "h": 20},
                    "text": "会员日全场 9 折，详情见条款细则补充说明。",
                    "computed": {
                        "color": "rgb(176, 183, 191)",
                        "backgroundColor": "rgb(255, 255, 255)",
                        "fontSize": "13px",
                        "lineHeight": "18px",
                    },
                    "depth": 2,
                    "inViewport": True,
                },
            ],
        },
    )
    w(
        caps / "shop__375x812__elements.json",
        {
            "route": "/shop",
            "viewport": "375x812",
            "elements": [
                {
                    "selector": "html",
                    "tag": "html",
                    "scrollWidth": 932,
                    "clientWidth": 375,
                    "bbox": {"x": 0, "y": 0, "w": 375, "h": 812},
                    "text": "",
                    "depth": 0,
                },
                {
                    "selector": ".product-grid",
                    "tag": "div",
                    "interactive": False,
                    "scrollWidth": 932,
                    "clientWidth": 375,
                    "bbox": {"x": 16, "y": 80, "w": 900, "h": 200},
                    "text": "",
                    "computed": {"overflowX": "visible"},
                    "depth": 2,
                    "inViewport": False,
                },
                {
                    "selector": 'a[href="#"]',
                    "tag": "a",
                    "interactive": True,
                    "href": "#",
                    "bbox": {"x": 20, "y": 240, "w": 80, "h": 20},
                    "text": "加入心愿单",
                    "depth": 3,
                    "inViewport": True,
                },
            ],
        },
    )
    w(
        caps / "contact__375x812__elements.json",
        {
            "route": "/contact",
            "viewport": "375x812",
            "elements": [
                {
                    "selector": "html",
                    "tag": "html",
                    "scrollWidth": 375,
                    "clientWidth": 375,
                    "bbox": {"x": 0, "y": 0, "w": 375, "h": 812},
                    "text": "",
                    "depth": 0,
                },
                {
                    "selector": "button[type=submit]",
                    "tag": "button",
                    "interactive": True,
                    "type": "submit",
                    "attrs": {"data-testid": "contact-submit"},
                    "bbox": {"x": 16, "y": 300, "w": 64, "h": 36},
                    "text": "提交",
                    "depth": 3,
                    "inViewport": True,
                },
                {
                    "selector": "[data-testid=contact-submit]",
                    "tag": "button",
                    "interactive": True,
                    "type": "submit",
                    "attrs": {"data-testid": "contact-submit"},
                    "bbox": {"x": 16, "y": 300, "w": 64, "h": 36},
                    "text": "提交",
                    "depth": 3,
                    "inViewport": True,
                },
                {
                    "selector": ".icon-tiny",
                    "tag": "button",
                    "interactive": True,
                    "attrs": {"aria-label": "折叠"},
                    "bbox": {"x": 16, "y": 350, "w": 20, "h": 20},
                    "text": "▾",
                    "depth": 3,
                    "inViewport": True,
                },
                {
                    "selector": "[data-empty-state-note]",
                    "tag": "p",
                    "interactive": False,
                    "attrs": {"data-empty-state-note": "1"},
                    "bbox": {"x": 16, "y": 400, "w": 300, "h": 20},
                    "text": "我们会在 1 个工作日内回复。",
                    "depth": 2,
                    "inViewport": True,
                },
            ],
        },
    )
    w(
        caps / "MANIFEST.json",
        {
            "base_url": "http://127.0.0.1:5174",
            "routes": ["/", "/shop", "/contact"],
            "viewports": ["375x812", "1440x900"],
            "backend": "fixture-from-html-css",
            "captured_at": "2026-09-18T02:37:00Z",
            "note": "Playwright unavailable; elements reconstructed from real second-project markup/styles",
            "items": [
                {
                    "route": "/",
                    "viewport": "375x812",
                    "stem": "home__375x812",
                    "status": "ok",
                    "elements_json": "home__375x812__elements.json",
                },
                {
                    "route": "/shop",
                    "viewport": "375x812",
                    "stem": "shop__375x812",
                    "status": "ok",
                    "elements_json": "shop__375x812__elements.json",
                },
                {
                    "route": "/contact",
                    "viewport": "375x812",
                    "stem": "contact__375x812",
                    "status": "ok",
                    "elements_json": "contact__375x812__elements.json",
                },
            ],
        },
    )

    sp = ROOT / ".bug-hunter" / "state.json"
    state = json.loads(sp.read_text(encoding="utf-8-sig"))
    state.setdefault("surfaces", {}).setdefault("web", {})["degrade_level"] = "L3"
    sp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    cmd = [
        sys.executable,
        str(SCRIPTS / "hunt_round.py"),
        "--root",
        str(ROOT),
        "--run-id",
        "run-1",
        "--skip-capture",
        "--captures",
        str(caps),
        "--dynamic-cmd",
        r"C:\Program Files\nodejs\node.exe --test test/checkout.test.js",
        "--flows",
        str(ROOT / "flows"),
        "--canvas-items",
        str(ROOT / "canvas" / "promo.scene.json"),
        "--write-candidates",
    ]
    out = subprocess.check_output(cmd, cwd=str(ROOT), text=True, stderr=subprocess.STDOUT)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
