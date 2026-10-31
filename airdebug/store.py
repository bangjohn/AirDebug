"""Remember phones that were paired, so AirDebug can reconnect them later."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import paths

log = logging.getLogger(__name__)


@dataclass
class KnownDevice:
    guid: str  # mDNS instance name of the phone, e.g. "adb-R58M123ABC-AbCdEf"
    name: str = ""  # friendly name (phone model) shown in the UI
    host: str = ""  # last known IP address
    port: int = 0  # last known connect port
    auto_reconnect: bool = True
    last_connected: float = 0.0

    @property
    def label(self) -> str:
        return self.name or self.guid


@dataclass
class Settings:
    auto_reconnect: bool = True
    start_minimized: bool = False
    check_interval: int = 5  # seconds between reconnect checks
    notifications: bool = True
    language: str = "auto"  # "auto", "en" or "id"


@dataclass
class _State:
    settings: Settings = field(default_factory=Settings)
    devices: dict[str, KnownDevice] = field(default_factory=dict)


class Store:
    def __init__(self, file: Path | None = None):
        self.file = file or (paths.data_dir() / "airdebug.json")
        self._lock = threading.RLock()
        self._state = self._load()

    # -- persistence ------------------------------------------------------ #

    def _load(self) -> _State:
        try:
            raw = json.loads(self.file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return _State()
        except (OSError, ValueError) as e:
            log.warning("Could not read %s (%s); starting fresh", self.file, e)
            return _State()
        settings_raw = raw.get("settings", {})
        settings = Settings(**{k: v for k, v in settings_raw.items() if k in Settings.__dataclass_fields__})
        devices = {}
        for guid, d in raw.get("devices", {}).items():
            d = {k: v for k, v in d.items() if k in KnownDevice.__dataclass_fields__}
            d["guid"] = guid
            devices[guid] = KnownDevice(**d)
        return _State(settings=settings, devices=devices)

    def save(self) -> None:
        with self._lock:
            data = {
                "settings": asdict(self._state.settings),
                "devices": {g: asdict(d) for g, d in self._state.devices.items()},
            }
        self.file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.file)

    # -- settings --------------------------------------------------------- #

    @property
    def settings(self) -> Settings:
        return self._state.settings

    def update_settings(self, **changes) -> None:
        with self._lock:
            for k, v in changes.items():
                if hasattr(self._state.settings, k):
                    setattr(self._state.settings, k, v)
        self.save()

    # -- devices ---------------------------------------------------------- #

    def devices(self) -> list[KnownDevice]:
        with self._lock:
            return sorted(self._state.devices.values(), key=lambda d: d.label.lower())

    def get(self, guid: str) -> KnownDevice | None:
        with self._lock:
            return self._state.devices.get(guid)

    def remember(self, guid: str, *, host: str = "", port: int = 0, name: str = "") -> KnownDevice:
        with self._lock:
            dev = self._state.devices.get(guid) or KnownDevice(guid=guid)
            if host:
                dev.host = host
            if port:
                dev.port = port
            if name:
                dev.name = name
            dev.last_connected = time.time()
            self._state.devices[guid] = dev
        self.save()
        return dev

    def set_auto_reconnect(self, guid: str, enabled: bool) -> None:
        with self._lock:
            dev = self._state.devices.get(guid)
            if dev:
                dev.auto_reconnect = enabled
        self.save()

    def forget(self, guid: str) -> None:
        with self._lock:
            self._state.devices.pop(guid, None)
        self.save()
