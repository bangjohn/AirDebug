from __future__ import annotations

import pytest

from airdebug import i18n
from airdebug.adb import Device, parse_connect_result, parse_devices, parse_pair_result
from airdebug.core import Controller, QrSession, guid_from_serial, parse_host_port
from airdebug.discovery import CONNECT, PAIRING, Service, instance_name
from airdebug.store import Store


@pytest.fixture(autouse=True)
def english():
    i18n.set_language("en")


# --------------------------------------------------------------------------- #
# Parsers
# --------------------------------------------------------------------------- #

DEVICES_OUT = """List of devices attached
192.168.1.20:41235     device product:panther model:Pixel_7 device:panther transport_id:3
adb-R58M123ABC-AbCdEf._adb-tls-connect._tcp device product:a52q model:SM_A525F device:a52q transport_id:4
R58M123ABC             unauthorized usb:1-1 transport_id:5
192.168.1.30:5555      offline transport_id:6

"""


def test_parse_devices():
    devs = parse_devices(DEVICES_OUT)
    assert [d.serial for d in devs] == [
        "192.168.1.20:41235",
        "adb-R58M123ABC-AbCdEf._adb-tls-connect._tcp",
        "R58M123ABC",
        "192.168.1.30:5555",
    ]
    assert devs[0].display_name == "Pixel 7" and devs[0].is_online and devs[0].is_wireless
    assert devs[1].is_wireless
    assert not devs[2].is_wireless and devs[2].state == "unauthorized"
    assert devs[3].state == "offline"


def test_parse_devices_ignores_daemon_noise():
    out = "* daemon not running; starting now at tcp:5037\n* daemon started successfully\nList of devices attached\n\n"
    assert parse_devices(out) == []


def test_parse_pair_result():
    ok, guid = parse_pair_result("Successfully paired to 192.168.1.20:37099 [guid=adb-R58M123ABC-AbCdEf]")
    assert ok and guid == "adb-R58M123ABC-AbCdEf"
    ok, msg = parse_pair_result("Failed: Wrong password or connection was dropped.")
    assert not ok and "Wrong password" in msg


def test_parse_connect_result():
    assert parse_connect_result("connected to 192.168.1.20:41235")
    assert parse_connect_result("already connected to 192.168.1.20:41235")
    assert not parse_connect_result("failed to connect to '192.168.1.20:41235': Connection refused")
    assert not parse_connect_result("cannot connect to 192.168.1.20:41235: No route to host (10065)")


def test_qr_payload_format():
    s = QrSession.new()
    assert s.name.startswith("airdebug-")
    assert s.payload == f"WIFI:T:ADB;S:{s.name};P:{s.password};;"
    assert ";" not in s.password and ":" not in s.password


def test_parse_host_port():
    assert parse_host_port(" 192.168.1.5:37099 ") == ("192.168.1.5", 37099)
    with pytest.raises(ValueError):
        parse_host_port("192.168.1.5")
    with pytest.raises(ValueError):
        parse_host_port("192.168.1.5:99999")


def test_guid_and_instance_helpers():
    assert guid_from_serial("adb-R58M-AbC._adb-tls-connect._tcp") == "adb-R58M-AbC"
    assert guid_from_serial("192.168.1.5:5555") is None
    assert instance_name("adb-R58M-AbC._adb-tls-connect._tcp.local.", CONNECT) == "adb-R58M-AbC"


# --------------------------------------------------------------------------- #
# Controller with fakes
# --------------------------------------------------------------------------- #


class FakeAdb:
    def __init__(self):
        self.online: dict[str, Device] = {}
        self.calls: list[tuple] = []
        self.pair_ok = True
        self.connect_ok = True

    def devices(self):
        return list(self.online.values())

    def pair(self, host, port, code):
        self.calls.append(("pair", host, port, code))
        if self.pair_ok:
            return True, "adb-SERIAL1-xyz"
        return False, "Failed: Wrong password or connection was dropped."

    def connect(self, host, port):
        self.calls.append(("connect", host, port))
        if self.connect_ok:
            s = f"{host}:{port}"
            self.online[s] = Device(s, "device", model="Pixel_7")
            return True, f"connected to {s}"
        return False, "failed to connect"

    def disconnect(self, serial):
        self.calls.append(("disconnect", serial))
        self.online.pop(serial, None)
        return "disconnected"

    def getprop(self, serial, prop):
        return "Pixel 7"


class FakeDiscovery:
    def __init__(self):
        self.items: dict[tuple[str, str], Service] = {}

    def add(self, kind, instance, host, port):
        self.items[(kind, instance)] = Service(instance, kind, host, port)

    def find(self, kind, instance):
        return self.items.get((kind, instance))

    def services(self, kind=None):
        return [s for s in self.items.values() if kind is None or s.kind == kind]


@pytest.fixture
def ctl(tmp_path):
    return Controller(FakeAdb(), FakeDiscovery(), Store(tmp_path / "s.json"))


def test_qr_flow_pairs_then_connects(ctl):
    session = QrSession.new()
    ctl.discovery.add(PAIRING, session.name, "192.168.1.20", 37099)
    svc = ctl.wait_for_qr_scan(session, timeout=1)
    assert svc.address == "192.168.1.20:37099"

    ctl.discovery.add(CONNECT, "adb-SERIAL1-xyz", "192.168.1.20", 41235)
    res = ctl.pair_and_connect(svc.host, svc.port, session.password)
    assert res.ok, res.message
    assert ("pair", "192.168.1.20", 37099, session.password) in ctl.adb.calls
    assert ("connect", "192.168.1.20", 41235) in ctl.adb.calls
    known = ctl.store.get("adb-SERIAL1-xyz")
    assert known and known.name == "Pixel 7" and known.port == 41235


def test_wrong_code_gives_friendly_message(ctl):
    ctl.adb.pair_ok = False
    res = ctl.pair_and_connect("192.168.1.20", 37099, "000000")
    assert not res.ok and "Wrong pairing code" in res.message


def test_reconnect_uses_new_port_from_mdns(ctl):
    ctl.store.remember("adb-SERIAL1-xyz", host="192.168.1.20", port=41235, name="Pixel 7")
    # Phone toggled Wireless debugging: new port, new IP via DHCP.
    ctl.discovery.add(CONNECT, "adb-SERIAL1-xyz", "192.168.1.21", 40001)
    results = ctl.reconnect_pass()
    assert [r.serial for r in results] == ["192.168.1.21:40001"]
    assert ctl.store.get("adb-SERIAL1-xyz").port == 40001
    # Second pass: already online, nothing to do.
    ctl.adb.calls.clear()
    assert ctl.reconnect_pass() == []
    assert not any(c[0] == "connect" for c in ctl.adb.calls)


def test_reconnect_skips_disabled_and_cleans_offline(ctl):
    ctl.store.remember("adb-SERIAL1-xyz", host="192.168.1.20", port=41235)
    ctl.store.set_auto_reconnect("adb-SERIAL1-xyz", False)
    ctl.adb.online["192.168.1.30:5555"] = Device("192.168.1.30:5555", "offline")
    assert ctl.reconnect_pass() == []
    assert ("disconnect", "192.168.1.30:5555") in ctl.adb.calls
    assert not any(c[0] == "connect" for c in ctl.adb.calls)


def test_reconnect_respects_global_switch(ctl):
    ctl.store.remember("adb-SERIAL1-xyz", host="192.168.1.20", port=41235)
    ctl.store.update_settings(auto_reconnect=False)
    assert ctl.reconnect_pass() == []


def test_store_roundtrip(tmp_path):
    f = tmp_path / "s.json"
    s = Store(f)
    s.remember("adb-A-1", host="10.0.0.2", port=1234, name="Phone A")
    s.update_settings(language="id", check_interval=9)
    s2 = Store(f)
    assert s2.get("adb-A-1").name == "Phone A"
    assert s2.settings.language == "id" and s2.settings.check_interval == 9


def test_translations_have_both_languages():
    for key, entry in i18n.keys().items():
        assert "en" in entry and "id" in entry, key


def test_blind_reconnect_is_rate_limited(ctl):
    # Phone not visible via mDNS (e.g. multicast blocked): try last address, but not every tick.
    ctl.store.remember("adb-SERIAL1-xyz", host="192.168.1.20", port=41235)
    ctl.adb.connect_ok = False
    ctl.reconnect_pass()
    ctl.reconnect_pass()
    attempts = [c for c in ctl.adb.calls if c[0] == "connect"]
    assert attempts == [("connect", "192.168.1.20", 41235)]


def test_connect_after_pair_accepts_already_connected_host(ctl):
    ctl.adb.online["192.168.1.20:41235"] = Device("192.168.1.20:41235", "device", model="Pixel_7")
    res = ctl.pair_and_connect("192.168.1.20", 37099, "123456")
    assert res.ok and res.serial == "192.168.1.20:41235"
