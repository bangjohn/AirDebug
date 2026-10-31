"""AirDebug's brain: pairing, connecting and auto-reconnecting.

This module has no Qt dependency so it can be unit tested and reused from the
command line. The GUI calls these (blocking) methods from worker threads.
"""

from __future__ import annotations

import logging
import re
import secrets
import string
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from .adb import Adb, AdbError, Device
from .discovery import CONNECT, PAIRING, Discovery, Service
from .i18n import t
from .store import Store

log = logging.getLogger(__name__)

_ALPHABET = string.ascii_letters + string.digits
_MDNS_SERIAL = re.compile(r"^(?P<guid>adb-[^.]+)\._adb-tls-connect\._tcp\.?$")


# --------------------------------------------------------------------------- #
# QR pairing payload
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class QrSession:
    """The data encoded in the pairing QR code.

    Android's "Pair device with QR code" scanner expects a Wi-Fi style string::

        WIFI:T:ADB;S:<service name>;P:<password>;;

    After scanning, the phone advertises ``_adb-tls-pairing._tcp`` using
    ``<service name>`` as instance name, and we run
    ``adb pair <ip>:<port> <password>`` against it.
    """

    name: str
    password: str

    @property
    def payload(self) -> str:
        return f"WIFI:T:ADB;S:{self.name};P:{self.password};;"

    @classmethod
    def new(cls) -> QrSession:
        name = "airdebug-" + "".join(secrets.choice(_ALPHABET) for _ in range(8))
        password = "".join(secrets.choice(_ALPHABET) for _ in range(12))
        return cls(name=name, password=password)


def parse_host_port(text: str) -> tuple[str, int]:
    """'192.168.1.5:37099' -> ('192.168.1.5', 37099). Raises ValueError."""
    text = text.strip()
    m = re.fullmatch(r"\[?([0-9A-Za-z.:\-]+?)\]?:(\d{1,5})", text)
    if not m:
        raise ValueError(t("err_format"))
    port = int(m.group(2))
    if not 0 < port < 65536:
        raise ValueError("Port must be between 1 and 65535")
    return m.group(1), port


def guid_from_serial(serial: str) -> str | None:
    m = _MDNS_SERIAL.match(serial)
    return m.group("guid") if m else None


class Cancelled(Exception):
    pass


# --------------------------------------------------------------------------- #
# Controller
# --------------------------------------------------------------------------- #


@dataclass
class ConnectResult:
    ok: bool
    message: str
    serial: str = ""
    guid: str = ""


class Controller:
    def __init__(self, adb: Adb, discovery: Discovery, store: Store):
        self.adb = adb
        self.discovery = discovery
        self.store = store
        self._adb_lock = threading.Lock()  # serialise adb calls from threads
        # When a phone is not visible via mDNS we still try its last known
        # address, but only every FALLBACK_RETRY seconds to avoid slow timeouts.
        self._next_blind_try: dict[str, float] = {}

    FALLBACK_RETRY = 30.0

    # -- adb (serialised) --------------------------------------------------- #

    def devices(self) -> list[Device]:
        with self._adb_lock:
            try:
                return self.adb.devices()
            except AdbError as e:
                log.warning("adb devices failed: %s", e)
                return []

    def _pair(self, host: str, port: int, code: str) -> tuple[bool, str]:
        with self._adb_lock:
            return self.adb.pair(host, port, code)

    def _connect(self, host: str, port: int) -> tuple[bool, str]:
        with self._adb_lock:
            return self.adb.connect(host, port)

    def disconnect(self, serial: str) -> str:
        with self._adb_lock:
            return self.adb.disconnect(serial)

    def _model(self, serial: str) -> str:
        with self._adb_lock:
            try:
                model = self.adb.getprop(serial, "ro.product.model")
            except AdbError:
                return ""
        return "" if "error" in model.lower() else model

    # -- pairing ------------------------------------------------------------ #

    def wait_for_qr_scan(
        self,
        session: QrSession,
        timeout: float = 120.0,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> Service:
        """Block until the phone that scanned ``session`` shows up via mDNS."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if cancelled():
                raise Cancelled()
            svc = self.discovery.find(PAIRING, session.name)
            if svc:
                return svc
            time.sleep(0.3)
        raise TimeoutError("No phone scanned the QR code in time")

    def pair_and_connect(
        self,
        host: str,
        port: int,
        code: str,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> ConnectResult:
        """Run ``adb pair`` then find the phone's connect port and connect."""
        ok, info = self._pair(host, port, code.strip())
        if not ok:
            return ConnectResult(False, _friendly_pair_error(info))
        guid = info if info.startswith("adb-") else ""
        log.info("Paired with %s (guid=%s)", host, guid or "?")
        result = self.connect_after_pair(host, guid, cancelled=cancelled)
        if not result.ok:
            result.message = t("paired_not_connected") + "\n\n" + result.message
            # Still remember it so the monitor can connect once it is reachable.
            self.store.remember(guid or host, host=host)
        return result

    def connect_after_pair(
        self,
        host: str,
        guid: str,
        timeout: float = 20.0,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> ConnectResult:
        deadline = time.monotonic() + timeout
        last = t("err_no_connect_port")
        while time.monotonic() < deadline:
            if cancelled():
                raise Cancelled()
            # adb's own mDNS may already have auto-connected it.
            for d in self.devices():
                if not d.is_online:
                    continue
                if guid and guid_from_serial(d.serial) == guid:
                    return self._remember_connected(d.serial, guid, host, 0)
                if ":" in d.serial and d.serial.rsplit(":", 1)[0] == host:
                    port = int(d.serial.rsplit(":", 1)[1])
                    return self._remember_connected(d.serial, guid or host, host, port)
            svc = self._connect_service_for(guid, host)
            if svc:
                ok, out = self._connect(svc.host, svc.port)
                if ok:
                    return self._remember_connected(svc.address, guid or svc.instance, svc.host, svc.port)
                last = out
            time.sleep(1.0)
        return ConnectResult(False, last)

    def connect_manual(self, host: str, port: int) -> ConnectResult:
        """Connect to an already paired phone using IP:port from its screen."""
        ok, out = self._connect(host, port)
        if not ok:
            return ConnectResult(False, out or t("err_no_connect_port"))
        svc = self._connect_service_for("", host)
        guid = svc.instance if svc else f"{host}"
        return self._remember_connected(f"{host}:{port}", guid, host, port)

    def _connect_service_for(self, guid: str, host: str) -> Service | None:
        if guid:
            svc = self.discovery.find(CONNECT, guid)
            if svc:
                return svc
        for svc in self.discovery.services(CONNECT):
            if svc.host == host:
                return svc
        return None

    def _remember_connected(self, serial: str, guid: str, host: str, port: int) -> ConnectResult:
        name = self._model(serial)
        self.store.remember(guid, host=host, port=port, name=name)
        label = name or serial
        return ConnectResult(True, t("connected_to", name=label), serial=serial, guid=guid)

    # -- USB -> Wi-Fi ------------------------------------------------------- #

    def usb_to_wifi(self, serial: str, port: int = 5555) -> ConnectResult:
        """Legacy mode: switch a USB-attached phone to `adb tcpip` and connect.

        Works on every Android version, but needs the cable once per reboot.
        """
        with self._adb_lock:
            ip = self.adb.wifi_ip(serial)
            if not ip:
                return ConnectResult(False, t("usb_no_ip"))
            self.adb.tcpip(serial, port)
        time.sleep(2.0)
        ok, out = self._connect(ip, port)
        if not ok:
            return ConnectResult(False, out)
        return self._remember_connected(f"{ip}:{port}", f"tcpip-{ip}", ip, port)

    # -- auto reconnect ----------------------------------------------------- #

    def reconnect_pass(self) -> list[ConnectResult]:
        """One round of: for every remembered phone that is offline, reconnect.

        Returns the successful reconnections (for notifications).
        """
        if not self.store.settings.auto_reconnect:
            return []
        current = self.devices()
        online = {d.serial for d in current if d.is_online}
        online_guids = {guid_from_serial(s) for s in online}
        online_hosts = {s.rsplit(":", 1)[0] for s in online if ":" in s}

        # Clean up stale "offline" entries that would block a fresh connect.
        for d in current:
            if d.is_wireless and d.state == "offline":
                log.info("Dropping stale offline entry %s", d.serial)
                try:
                    self.disconnect(d.serial)
                except AdbError:
                    pass

        results: list[ConnectResult] = []
        for known in self.store.devices():
            if not known.auto_reconnect:
                continue
            if known.guid in online_guids:
                continue
            svc = self._connect_service_for(
                known.guid if known.guid.startswith("adb-") else "", known.host
            )
            host, port = (svc.host, svc.port) if svc else (known.host, known.port)
            if not host or not port:
                continue
            if f"{host}:{port}" in online or (svc is None and host in online_hosts):
                continue
            if svc is None:
                if time.monotonic() < self._next_blind_try.get(known.guid, 0.0):
                    continue
                self._next_blind_try[known.guid] = time.monotonic() + self.FALLBACK_RETRY
            try:
                ok, out = self._connect(host, port)
            except AdbError as e:
                log.debug("reconnect %s failed: %s", known.label, e)
                continue
            if ok:
                log.info("Auto-reconnected %s at %s:%s", known.label, host, port)
                self.store.remember(known.guid, host=host, port=port)
                results.append(
                    ConnectResult(True, t("reconnected", name=known.label), f"{host}:{port}", known.guid)
                )
        return results


def _friendly_pair_error(raw: str) -> str:
    low = raw.lower()
    if "wrong password" in low or "protocol fault" in low:
        return t("err_wrong_code")
    if "unable to connect" in low or "connection refused" in low or "timed out" in low:
        return t("err_unreachable")
    return raw
