#!/usr/bin/env python3
"""Shared helpers for unified MMIT skill (mmit)."""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SKILL_ID = "mmit"
STATE_DIRNAME = ".mmit"
LOCK_RETRY = 3
LOCK_SLEEP_S = 0.05

MODALITIES = [
    "code",
    "api",
    "web",
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
]

MARKS = ("required", "optional", "n/a")
DEFECT_LEVELS = ("P0", "P1", "P2", "P3")
DECISIONS = ("in_progress", "allow", "deny", "escalate", "allow_release", "deny_release", "escalated")
PROD_ACCESS = ("none", "readonly", "shadow", "canary")
DEPTHS = ("hunt", "release")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def mit_dir(root: Path) -> Path:
    return root / STATE_DIRNAME


def ensure_mit(root: Path) -> Path:
    d = mit_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    return d


# Alias used by release scripts after migration
def ensure_mmit(root: Path) -> Path:
    return ensure_mit(root)


def ensure_tests(root: Path) -> Path:
    d = ensure_mit(root) / "tests"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_hunts(root: Path) -> Path:
    d = ensure_mit(root) / "hunts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_deliverables(root: Path) -> Path:
    d = ensure_mit(root) / "deliverables"
    d.mkdir(parents=True, exist_ok=True)
    return d


def acquire_lock(lock_path: Path) -> int:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    last_err: Exception | None = None
    for attempt in range(LOCK_RETRY):
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            stamp = utc_now()
            os.write(fd, f"{os.getpid()}\n{stamp}\n".encode("utf-8"))
            return fd
        except FileExistsError as e:
            last_err = e
            if attempt < LOCK_RETRY - 1:
                time.sleep(LOCK_SLEEP_S * (attempt + 1))
                continue
            raise RuntimeError(
                f"lock exists: {lock_path}. Another session may be writing."
            ) from e
    raise RuntimeError(f"lock acquire failed: {last_err}")


def release_lock(fd: int, lock_path: Path) -> None:
    try:
        os.close(fd)
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def load_state(root: Path) -> dict[str, Any]:
    p = mit_dir(root) / "state.json"
    data = read_json(p)
    if not isinstance(data, dict):
        raise FileNotFoundError(f"state.json missing or invalid: {p}")
    return data


def save_state(root: Path, state: dict[str, Any]) -> None:
    p = mit_dir(root) / "state.json"
    fd = acquire_lock(mit_dir(root) / ".lock")
    try:
        state["updated_at"] = utc_now()
        write_json(p, state)
    finally:
        release_lock(fd, mit_dir(root) / ".lock")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def blind_spot(state: dict, key: str, reason: str) -> None:
    blinds = state.setdefault("blinds", [])
    state.setdefault("blind_spots", blinds)
    entry = {"key": key, "reason": reason, "at": utc_now()}
    for b in blinds:
        if b.get("key") == key and b.get("reason") == reason:
            return
    blinds.append(entry)
