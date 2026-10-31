"""Find phones on the local network that have Wireless Debugging turned on.

Android 11+ advertises two mDNS (Bonjour) services while Wireless debugging is
enabled in Developer options:

* ``_adb-tls-pairing._tcp`` – only while a pairing screen (QR or code) is open
* ``_adb-tls-connect._tcp`` – whenever Wireless debugging is on; this is the
  port that ``adb connect`` needs. The port changes every time the toggle is
  switched, which is why plain ``adb connect`` with a remembered port breaks.

We browse for them with python-zeroconf, which is far more reliable on Windows
than adb's built-in mDNS backend.
"""

from __future__ import annotations

import logging
import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass

from zeroconf import IPVersion, ServiceBrowser, ServiceStateChange, Zeroconf

log = logging.getLogger(__name__)

PAIRING = "_adb-tls-pairing._tcp.local."
CONNECT = "_adb-tls-connect._tcp.local."
SERVICE_TYPES = (PAIRING, CONNECT)


@dataclass(frozen=True)
class Service:
    instance: str  # e.g. "adb-R58M123ABC-AbCdEf" or "airdebug-1a2b3c4d"
    kind: str  # PAIRING or CONNECT
    host: str  # IPv4 address
    port: int

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"


def instance_name(full_name: str, service_type: str) -> str:
    """'adb-XYZ-abc._adb-tls-connect._tcp.local.' -> 'adb-XYZ-abc'"""
    suffix = "." + service_type
    return full_name[: -len(suffix)] if full_name.endswith(suffix) else full_name.split("._", 1)[0]


class Discovery:
    """Background mDNS browser. Thread-safe snapshot via :meth:`services`."""

    def __init__(self, on_change: Callable[[], None] | None = None):
        self._on_change = on_change
        self._lock = threading.Lock()
        self._services: dict[tuple[str, str], Service] = {}
        self._zc: Zeroconf | None = None
        self._browsers: list[ServiceBrowser] = []

    # -- lifecycle -------------------------------------------------------- #

    def start(self) -> None:
        if self._zc:
            return
        self._zc = Zeroconf(ip_version=IPVersion.V4Only)
        self._browsers = [
            ServiceBrowser(self._zc, t, handlers=[self._handle]) for t in SERVICE_TYPES
        ]
        log.info("mDNS discovery started")

    def stop(self) -> None:
        for b in self._browsers:
            b.cancel()
        self._browsers = []
        if self._zc:
            self._zc.close()
            self._zc = None

    # -- queries ---------------------------------------------------------- #

    def services(self, kind: str | None = None) -> list[Service]:
        with self._lock:
            items = list(self._services.values())
        return [s for s in items if kind is None or s.kind == kind]

    def find(self, kind: str, instance: str) -> Service | None:
        with self._lock:
            return self._services.get((kind, instance))

    # -- zeroconf callback ------------------------------------------------ #

    def _handle(self, zeroconf: Zeroconf, service_type: str, name: str, state_change):
        key = (service_type, instance_name(name, service_type))
        if state_change is ServiceStateChange.Removed:
            with self._lock:
                removed = self._services.pop(key, None)
            if removed:
                log.info("mDNS lost %s", removed)
                self._notify()
            return

        info = zeroconf.get_service_info(service_type, name, timeout=3000)
        if not info or not info.port:
            return
        addrs = [socket.inet_ntoa(a) for a in info.addresses if len(a) == 4]
        if not addrs:
            return
        svc = Service(instance=key[1], kind=service_type, host=addrs[0], port=info.port)
        with self._lock:
            changed = self._services.get(key) != svc
            self._services[key] = svc
        if changed:
            log.info("mDNS found %s", svc)
            self._notify()

    def _notify(self) -> None:
        if self._on_change:
            try:
                self._on_change()
            except Exception:  # never let UI errors kill the zeroconf thread
                log.exception("discovery callback failed")
