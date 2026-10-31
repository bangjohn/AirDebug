"""Thin, testable wrapper around the `adb` command-line tool.

AirDebug never talks the ADB wire protocol itself. Everything goes through the
official `adb` binary from Google's Android SDK Platform-Tools, exactly like
Android Studio does behind the scenes (`adb pair`, `adb connect`, ...).
"""

from __future__ import annotations

import io
import logging
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from . import paths

log = logging.getLogger(__name__)

PLATFORM_TOOLS_URLS = {
    "win32": "https://dl.google.com/android/repository/platform-tools-latest-windows.zip",
    "darwin": "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip",
    "linux": "https://dl.google.com/android/repository/platform-tools-latest-linux.zip",
}

ADB_EXE = "adb.exe" if sys.platform == "win32" else "adb"

# Hide the black console window that would otherwise flash on Windows
# every time we spawn adb.exe from a GUI app.
_CREATIONFLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class AdbError(RuntimeError):
    """Raised when adb is missing or a command fails."""


@dataclass(frozen=True)
class Device:
    serial: str  # e.g. "192.168.1.20:41235", "R58M123ABC" or "adb-R58M...-x._adb-tls-connect._tcp"
    state: str  # "device", "offline", "unauthorized", ...
    model: str = ""
    product: str = ""
    transport: str = ""

    @property
    def is_wireless(self) -> bool:
        return ":" in self.serial or "._adb-tls-connect." in self.serial

    @property
    def is_online(self) -> bool:
        return self.state == "device"

    @property
    def display_name(self) -> str:
        return self.model.replace("_", " ") if self.model else self.serial


# --------------------------------------------------------------------------- #
# Locating / installing adb
# --------------------------------------------------------------------------- #


def find_adb() -> Path | None:
    """Return the adb binary to use, or None if it is not available.

    Search order:
      1. ``AIRDEBUG_ADB`` environment variable (explicit override)
      2. ``platform-tools`` next to the AirDebug executable (portable installs)
      3. ``platform-tools`` that AirDebug downloaded into its data folder
      4. ``ANDROID_HOME`` / ``ANDROID_SDK_ROOT`` / default Android Studio SDK
      5. ``adb`` on PATH
    """
    override = os.environ.get("AIRDEBUG_ADB")
    if override and Path(override).is_file():
        return Path(override)

    candidates = [
        paths.app_dir() / "platform-tools" / ADB_EXE,
        paths.data_dir() / "platform-tools" / ADB_EXE,
    ]
    for var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = os.environ.get(var)
        if root:
            candidates.append(Path(root) / "platform-tools" / ADB_EXE)
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            candidates.append(Path(local) / "Android" / "Sdk" / "platform-tools" / ADB_EXE)

    for c in candidates:
        if c.is_file():
            return c

    on_path = shutil.which("adb")
    return Path(on_path) if on_path else None


def download_platform_tools(progress=None) -> Path:
    """Download Google's official Platform-Tools into the AirDebug data folder.

    ``progress`` is an optional callable ``(downloaded_bytes, total_bytes)``.
    Returns the path to the adb binary.
    """
    url = PLATFORM_TOOLS_URLS.get(sys.platform, PLATFORM_TOOLS_URLS["linux"])
    log.info("Downloading platform-tools from %s", url)
    with urllib.request.urlopen(url, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        buf = io.BytesIO()
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            buf.write(chunk)
            if progress:
                progress(buf.tell(), total)
    target = paths.data_dir()
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(buf) as zf:
        zf.extractall(target)
    adb = target / "platform-tools" / ADB_EXE
    if not adb.is_file():
        raise AdbError("Downloaded archive did not contain adb")
    if sys.platform != "win32":
        adb.chmod(0o755)
    return adb


# --------------------------------------------------------------------------- #
# Output parsers (pure functions, unit tested)
# --------------------------------------------------------------------------- #


def parse_devices(output: str) -> list[Device]:
    """Parse the output of ``adb devices -l``."""
    devices: list[Device] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state, extras = parts[0], parts[1], parts[2:]
        info = dict(p.split(":", 1) for p in extras if ":" in p)
        devices.append(
            Device(
                serial=serial,
                state=state,
                model=info.get("model", ""),
                product=info.get("product", ""),
                transport=info.get("transport_id", ""),
            )
        )
    return devices


_PAIR_OK = re.compile(r"Successfully paired to (\S+)(?: \[guid=(\S+)\])?", re.I)


def parse_pair_result(output: str) -> tuple[bool, str]:
    m = _PAIR_OK.search(output)
    if m:
        return True, m.group(2) or m.group(1)
    return False, output.strip() or "Pairing failed"


def parse_connect_result(output: str) -> bool:
    text = output.lower()
    return ("connected to" in text) and ("cannot" not in text) and ("failed" not in text)


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #


class Adb:
    def __init__(self, binary: Path | str | None = None):
        found = Path(binary) if binary else find_adb()
        if not found:
            raise AdbError("adb not found")
        self.binary = Path(found)

    def run(self, *args: str, timeout: float = 15.0) -> str:
        cmd = [str(self.binary), *args]
        log.debug("$ %s", " ".join(cmd))
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                creationflags=_CREATIONFLAGS,
            )
        except subprocess.TimeoutExpired as e:
            raise AdbError(f"adb {' '.join(args)} timed out") from e
        except OSError as e:
            raise AdbError(f"Cannot run adb: {e}") from e
        out = (proc.stdout or "") + (proc.stderr or "")
        log.debug("%s", out.strip())
        return out

    # -- high level helpers ------------------------------------------------ #

    def version(self) -> str:
        first = self.run("version").splitlines()
        return first[0] if first else "unknown"

    def start_server(self) -> None:
        self.run("start-server", timeout=30)

    def devices(self) -> list[Device]:
        return parse_devices(self.run("devices", "-l"))

    def pair(self, host: str, port: int, code: str) -> tuple[bool, str]:
        return parse_pair_result(self.run("pair", f"{host}:{port}", code, timeout=30))

    def connect(self, host: str, port: int) -> tuple[bool, str]:
        out = self.run("connect", f"{host}:{port}", timeout=20)
        return parse_connect_result(out), out.strip()

    def disconnect(self, serial: str) -> str:
        return self.run("disconnect", serial).strip()

    def getprop(self, serial: str, prop: str) -> str:
        return self.run("-s", serial, "shell", "getprop", prop, timeout=10).strip()

    def tcpip(self, serial: str, port: int = 5555) -> str:
        return self.run("-s", serial, "tcpip", str(port), timeout=15).strip()

    def wifi_ip(self, serial: str) -> str | None:
        """Best effort: read the Wi-Fi IPv4 address of a (USB) device."""
        out = self.run("-s", serial, "shell", "ip", "-f", "inet", "addr", "show", "wlan0", timeout=10)
        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", out)
        return m.group(1) if m else None
