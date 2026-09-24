"""Помощник для чтения версии приложения."""

from __future__ import annotations

import sys
from pathlib import Path


def _read_file(path: Path) -> str | None:
    try:
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
    except Exception:
        return None
    return None


def _read_version() -> str:
    # В frozen-режиме сначала пробуем бандл, затем папку рядом с exe.
    if getattr(sys, "frozen", False):
        candidates: list[Path] = []
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "VERSION")
        candidates.append(Path(sys.executable).resolve().parent / "VERSION")

        for candidate in candidates:
            if value := _read_file(candidate):
                return value
        return "0.0.0"

    # В режиме разработки читаем VERSION из корня проекта.
    project_root = Path(__file__).resolve().parent.parent
    if value := _read_file(project_root / "VERSION"):
        return value
    return "0.0.0"


__version__ = _read_version()

