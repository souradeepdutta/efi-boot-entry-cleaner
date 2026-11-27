"""Path helpers that work both from source and inside a PyInstaller bundle."""

from __future__ import annotations

import sys
from pathlib import Path


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative


def app_icon_path() -> Path:
    return resource_path("assets/app.ico")
