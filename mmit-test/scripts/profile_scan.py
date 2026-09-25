#!/usr/bin/env python3
"""Project profile scan for mmit-test (MMIT-Test)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mit_lib import ensure_mit, read_json, utc_now, write_json  # noqa: E402

APP_TYPE_CLUES: list[tuple[str, list[str]]] = [
    ("web", ["package.json", "index.html", "vite.config", "next.config", "webpack.config"]),
    ("api", ["openapi.yaml", "openapi.json", "swagger.yaml", "proto/", "routes/", "controllers/"]),
    ("cli", ["setup.py", "pyproject.toml", "bin/", "cli.py", "cmd/"]),
    ("mobile", ["android/", "ios/", "pubspec.yaml", "app.json", "AndroidManifest.xml"]),
    ("desktop", ["electron", "tauri", "Cargo.toml", "wix", "msix", ".dmg", "desktop/"]),
    ("db", ["migrations/", "alembic/", "prisma/schema.prisma", "flyway", "schema.sql"]),
    ("infra", ["Dockerfile", "docker-compose", "k8s/", "kubernetes/", "helm/", "terraform/"]),
    ("av", ["audio/", "video/", "media/", ".mp4", ".mp3", ".wav", "ffmpeg"]),
    ("canvas", ["canvas/", ".scene.json", "figma", "poster"]),
    ("3d", ["models/", ".glb", ".gltf", ".fbx", "three", "blender"]),
    ("xr", ["xr/", "webxr", "quest", "unity/", "openxr"]),
    ("plugin", ["plugin/", "extension/", "vscode", "manifest.json"]),
]


def _has_clue(root: Path, clue: str) -> bool:
    if clue.endswith("/"):
        return (root / clue.rstrip("/")).is_dir()
    if clue.startswith("."):
        matches = list(root.rglob(f"*{clue}"))
        return any(m.is_file() for m in matches[:5])
    return (root / clue).exists() or any(root.rglob(clue))


def detect_app_types(root: Path) -> list[str]:
    found: list[str] = []
    for app_type, clues in APP_TYPE_CLUES:
        if any(_has_clue(root, c) for c in clues):
            found.append(app_type)
    return found or ["unknown"]


def detect_runtime(root: Path) -> str:
    pkg = root / "package.json"
    if pkg.exists():
        try:
            data = read_json(pkg)
            engines = data.get("engines") or {}
            node = engines.get("node")
            if node:
                return f"node@{node}"
            return "node"
        except (json.JSONDecodeError, OSError):
            return "node"
    for name in ("pyproject.toml", "requirements.txt", "setup.py", "Pipfile"):
        if (root / name).exists():
            return "python"
    if (root / "Cargo.toml").exists():
        return "rust"
    if (root / "go.mod").exists():
        return "go"
    return "unknown"


def detect_topology(root: Path) -> str:
    parts: list[str] = []
    text_blob = ""
    for name in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        p = root / name
        if p.exists():
            text_blob += p.read_text(encoding="utf-8", errors="ignore").lower()
    if re.search(r"postgres|postgre", text_blob):
        parts.append("postgres")
    if re.search(r"redis", text_blob):
        parts.append("redis")
    if re.search(r"mysql|mariadb", text_blob):
        parts.append("mysql")
    if re.search(r"mongo", text_blob):
        parts.append("mongo")
    if re.search(r"kafka|rabbit|nats", text_blob):
        parts.append("queue")
    apiish = (root / "package.json").exists() or (root / "server.js").exists() or _has_clue(root, "openapi.yaml")
    if apiish:
        parts.insert(0, "api")
    return "+".join(parts) if parts else "unknown"


def detect_devices(root: Path) -> list[str]:
    devices: list[str] = []
    blob = ""
    for pattern in ("*.md", "*.json", "*.yml", "*.yaml"):
        for p in root.rglob(pattern):
            if p.stat().st_size > 200_000:
                continue
            try:
                blob += p.read_text(encoding="utf-8", errors="ignore").lower()
            except OSError:
                continue
    if "ios" in blob or "iphone" in blob or "ipad" in blob:
        devices.append("ios")
    if "android" in blob:
        devices.append("android")
    if re.search(r"\bquest[0-9]?\b|webxr|openxr", blob):
        devices.append("xr")
    return devices or ["unknown"]


def detect_data_classes(root: Path) -> list[str]:
    blob = ""
    for p in root.rglob("*"):
        if not p.is_file() or p.stat().st_size > 200_000:
            continue
        if p.suffix.lower() not in {".py", ".js", ".ts", ".json", ".md", ".yml", ".yaml", ".env.example", ".sql"}:
            continue
        try:
            blob += p.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
    classes: list[str] = []
    if re.search(r"\bpii\b|email|phone|id_?card|passport|ssn", blob):
        classes.append("pii")
    if re.search(r"payment|card_?number|billing|stripe|cvv", blob):
        classes.append("payment")
    if re.search(r"\bmedia\b|audio|video|image_?asset|upload", blob):
        classes.append("media")
    return classes or ["unknown"]


def detect_plugins(root: Path) -> list[str]:
    plugins: list[str] = []
    if (root / "package.json").exists():
        try:
            data = read_json(root / "package.json")
            eng = data.get("engines") or {}
            if "vscode" in eng:
                plugins.append("vscode-ext")
            contributes = data.get("contributes")
            if contributes:
                plugins.append("editor-ext")
        except (json.JSONDecodeError, OSError):
            pass
    return plugins or []


def detect_release_artifact(root: Path) -> str:
    names = " ".join(p.name.lower() for p in root.rglob("*") if p.is_file() and p.stat().st_size < 50_000)
    if "dockerfile" in names:
        return "oci-image"
    if "electron" in names or "tauri" in names:
        return "desktop-installer"
    if "androidmanifest.xml" in names or "pubspec.yaml" in names:
        return "apk"
    if "msix" in names:
        return "msix"
    if (root / "package.json").exists():
        return "npm"
    if (root / "pyproject.toml").exists():
        return "pypi"
    return "unknown"


def detect_contract_apis(root: Path) -> list[str]:
    found: list[str] = []
    for name in ("openapi.yaml", "openapi.json", "swagger.yaml", "swagger.json"):
        if (root / name).exists():
            found.append(name)
    if (root / "proto").is_dir():
        found.append("proto/")
    return found or ["unknown"]


def detect_prod_access(root: Path) -> str:
    blob = ""
    for name in ("README.md", "docs/ACCEPTANCE.md", "AGENTS.md"):
        p = root / name
        if p.exists():
            try:
                blob += p.read_text(encoding="utf-8", errors="ignore").lower()
            except OSError:
                continue
    if "canary" in blob and "approved" in blob:
        return "canary"
    if "shadow" in blob:
        return "shadow"
    if "readonly" in blob or "read-only" in blob:
        return "readonly"
    return "none"


def scan_profile(root: Path) -> dict[str, Any]:
    return {
        "version": 1,
        "skill": "mmit-test",
        "scanned_at": utc_now(),
        "root": str(root.resolve()),
        "app_types": detect_app_types(root),
        "runtime": detect_runtime(root),
        "topology": detect_topology(root),
        "devices": detect_devices(root),
        "data_classes": detect_data_classes(root),
        "plugins": detect_plugins(root),
        "release_artifact": detect_release_artifact(root),
        "contract_apis": detect_contract_apis(root),
        "prod_access": detect_prod_access(root),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scan project profile for MMIT-Test")
    p.add_argument("--root", type=Path, default=Path.cwd(), help="target project root")
    p.add_argument("--out", type=Path, default=None, help="output path (default .mit/profile.json)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        print(f"error: root not a directory: {root}", file=sys.stderr)
        return 2
    profile = scan_profile(root)
    out = args.out or (ensure_mit(root) / "profile.json")
    write_json(out, profile)
    print(f"profile written: {out}")
    print(json.dumps({k: profile[k] for k in ("app_types", "runtime", "topology", "prod_access")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
