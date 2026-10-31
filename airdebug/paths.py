"""Where AirDebug keeps its files."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "AirDebug"


def app_dir() -> Path:
    """Folder containing the running executable (or the source package)."""
    if getattr(sys, "frozen", False):  # PyInstaller
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource(name: str) -> Path:
    """Path to a bundled resource file (works from source and from the .exe)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "airdebug" / "resources" / name


def data_dir() -> Path:
    """Per-user writable folder: %APPDATA%\\AirDebug on Windows."""
    override = os.environ.get("AIRDEBUG_HOME")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / APP_NAME
