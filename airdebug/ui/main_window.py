"""Main window and system tray icon."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCloseEvent, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, autostart, paths
from ..core import ConnectResult, Controller, guid_from_serial
from ..discovery import CONNECT
from ..i18n import current_language, t
from .dialogs import CodePairDialog, ConnectDialog, QrPairDialog
from .workers import run_async

log = logging.getLogger(__name__)

STYLE = """
QMainWindow { background: #f6f8fa; }
QPushButton#primary {
    background: #1b873f; color: white; border: none; border-radius: 6px;
    padding: 8px 14px; font-weight: 600;
}
QPushButton#primary:hover { background: #17733a; }
QPushButton { padding: 7px 12px; border-radius: 6px; }
QTreeWidget { background: white; border: 1px solid #d0d7de; border-radius: 6px; }
QLabel#title { font-size: 18px; font-weight: 700; }
QLabel#muted { color: #57606a; }
"""


@dataclass
class Row:
    name: str
    address: str
    status: str
    guid: str = ""  # remembered device id (for auto-reconnect / forget)
    serial: str = ""  # current adb serial (for disconnect)
    auto: bool | None = None


class _Bridge(QObject):
    """Moves zeroconf-thread callbacks onto the UI thread."""

    discovery_changed = Signal()


class MainWindow(QMainWindow):
    def __init__(self, ctl: Controller, start_hidden: bool = False):
        super().__init__()
        self.ctl = ctl
        self.bridge = _Bridge()
        self._busy = False
        self._online_before: dict[str, str] = {}
        self._tray_hint_shown = False
        self._quitting = False

        self.icon_on = QIcon(str(paths.resource("icon.png")))
        self.icon_off = QIcon(str(paths.resource("icon_off.png")))
        self.setWindowIcon(self.icon_on)
        self.setWindowTitle(f"AirDebug {__version__}")
        self.resize(760, 480)
        self.setStyleSheet(STYLE)

        self._build_ui()
        self._build_tray()

        self.bridge.discovery_changed.connect(self._on_discovery_changed)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(max(2, self.ctl.store.settings.check_interval) * 1000)
        QTimer.singleShot(200, self.tick)

        if not start_hidden:
            self.show()

    # ------------------------------------------------------------------ UI --

    def _build_ui(self) -> None:
        root = QWidget()
        lay = QVBoxLayout(root)
        lay.setContentsMargins(16, 14, 16, 12)

        head = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("AirDebug")
        title.setObjectName("title")
        sub = QLabel(t("app_tagline"))
        sub.setObjectName("muted")
        title_box.addWidget(title)
        title_box.addWidget(sub)
        head.addLayout(title_box)
        head.addStretch(1)
        lay.addLayout(head)

        actions = QHBoxLayout()
        b_qr = QPushButton("▣  " + t("pair_qr"))
        b_qr.setObjectName("primary")
        b_qr.clicked.connect(self.pair_qr)
        b_code = QPushButton("🔢  " + t("pair_code"))
        b_code.clicked.connect(self.pair_code)
        b_ip = QPushButton(t("connect_ip"))
        b_ip.clicked.connect(self.connect_ip)
        b_usb = QPushButton(t("usb_to_wifi"))
        b_usb.clicked.connect(self.usb_to_wifi)
        b_refresh = QPushButton("⟳")
        b_refresh.setToolTip(t("refresh"))
        b_refresh.clicked.connect(self.tick)
        for b in (b_qr, b_code, b_ip, b_usb):
            actions.addWidget(b)
        actions.addStretch(1)
        actions.addWidget(b_refresh)
        lay.addLayout(actions)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels([t("col_device"), t("col_address"), t("col_status"), t("col_auto")])
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.itemChanged.connect(self._item_changed)
        hdr = self.tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        lay.addWidget(self.tree, 1)

        self.empty = QLabel(t("empty_hint"))
        self.empty.setObjectName("muted")
        self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.empty)

        s = self.ctl.store.settings
        opts = QHBoxLayout()
        self.cb_auto = QCheckBox(t("opt_auto"))
        self.cb_auto.setChecked(s.auto_reconnect)
        self.cb_auto.toggled.connect(self._set_auto)
        opts.addWidget(self.cb_auto)
        self.cb_start = QCheckBox(t("opt_startup"))
        self.cb_start.setEnabled(autostart.supported())
        self.cb_start.setChecked(autostart.is_enabled())
        self.cb_start.toggled.connect(self._set_startup)
        opts.addWidget(self.cb_start)
        self.cb_min = QCheckBox(t("opt_minimized"))
        self.cb_min.setChecked(s.start_minimized)
        self.cb_min.toggled.connect(lambda v: self.ctl.store.update_settings(start_minimized=v))
        opts.addWidget(self.cb_min)
        self.cb_notify = QCheckBox(t("opt_notify"))
        self.cb_notify.setChecked(s.notifications)
        self.cb_notify.toggled.connect(lambda v: self.ctl.store.update_settings(notifications=v))
        opts.addWidget(self.cb_notify)
        opts.addStretch(1)
        opts.addWidget(QLabel(t("opt_language")))
        self.lang = QComboBox()
        self.lang.addItem("Auto", "auto")
        self.lang.addItem("English", "en")
        self.lang.addItem("Bahasa Indonesia", "id")
        self.lang.setCurrentIndex(max(0, self.lang.findData(s.language)))
        self.lang.currentIndexChanged.connect(self._set_language)
        opts.addWidget(self.lang)
        lay.addLayout(opts)

        self.setCentralWidget(root)
        try:
            ver = self.ctl.adb.version()
        except Exception:
            ver = "?"
        self.statusBar().showMessage(t("adb_version", ver=ver) + f"  ·  {self.ctl.adb.binary}")

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.icon_off, self)
        self.tray.setToolTip("AirDebug")
        menu = QMenu()
        menu.addAction(t("show"), self.show_window)
        menu.addSeparator()
        menu.addAction(t("pair_qr"), self.pair_qr)
        menu.addAction(t("pair_code"), self.pair_code)
        menu.addSeparator()
        self.tray_auto = QAction(t("opt_auto"), menu, checkable=True)
        self.tray_auto.setChecked(self.ctl.store.settings.auto_reconnect)
        self.tray_auto.toggled.connect(self.cb_auto.setChecked)
        menu.addAction(self.tray_auto)
        self.tray_devices = menu.addMenu(t("col_device"))
        menu.addSeparator()
        menu.addAction(t("quit"), self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    # ----------------------------------------------------------- actions --

    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _open(self, dlg) -> None:
        dlg.connected.connect(self._on_connected)
        self.show_window()
        dlg.exec()
        self.tick()

    def pair_qr(self) -> None:
        self._open(QrPairDialog(self.ctl, self))

    def pair_code(self) -> None:
        self._open(CodePairDialog(self.ctl, self))

    def connect_ip(self) -> None:
        self._open(ConnectDialog(self.ctl, self))

    def usb_to_wifi(self) -> None:
        usb = [d for d in self.ctl.devices() if d.is_online and not d.is_wireless]
        if not usb:
            QMessageBox.information(self, t("usb_to_wifi"), t("usb_none"))
            return
        labels = [f"{d.display_name}  ({d.serial})" for d in usb]
        choice, ok = QInputDialog.getItem(self, t("usb_to_wifi"), t("usb_pick"), labels, 0, False)
        if not ok:
            return
        dev = usb[labels.index(choice)]
        self.statusBar().showMessage(t("connecting"))
        run_async(lambda: self.ctl.usb_to_wifi(dev.serial), self._usb_done, self._error)

    def _usb_done(self, res: ConnectResult) -> None:
        if res.ok:
            self._on_connected(res)
        else:
            QMessageBox.warning(self, t("usb_to_wifi"), res.message)
        self.tick()

    def _error(self, msg: str) -> None:
        self.statusBar().showMessage(msg, 8000)

    def _on_connected(self, res: ConnectResult) -> None:
        self.statusBar().showMessage(res.message, 6000)
        self._notify(res.message)

    def quit(self) -> None:
        self._quitting = True
        self.tray.hide()
        from PySide6.QtWidgets import QApplication

        QApplication.quit()

    # ------------------------------------------------------- monitoring --

    def _on_discovery_changed(self) -> None:
        # A phone appeared / changed port: reconnect quickly instead of waiting.
        QTimer.singleShot(300, self.tick)

    def tick(self) -> None:
        if self._busy:
            return
        self._busy = True

        def work():
            reconnected = self.ctl.reconnect_pass()
            return reconnected, self.ctl.devices()

        def done(result):
            self._busy = False
            reconnected, devices = result
            for r in reconnected:
                self._notify(r.message)
            self._render(devices)

        def fail(err):
            self._busy = False
            self._error(err)

        run_async(work, done, fail)

    def _rows(self, devices) -> list[Row]:
        known = {k.guid: k for k in self.ctl.store.devices()}
        by_host = {k.host: k for k in known.values() if k.host}
        on_network = {s.instance for s in self.ctl.discovery.services(CONNECT)}
        rows: list[Row] = []
        seen: set[str] = set()

        for d in devices:
            guid = guid_from_serial(d.serial) or ""
            if not guid and ":" in d.serial:
                host = d.serial.rsplit(":", 1)[0]
                k = by_host.get(host)
                guid = k.guid if k else ""
            k = known.get(guid)
            if d.state == "device":
                status = t("st_connected") if d.is_wireless else t("st_usb")
            elif d.state == "unauthorized":
                status = t("st_unauthorized")
            else:
                status = t("st_offline")
            name = d.display_name if d.model else (k.label if k else d.serial)
            rows.append(Row(name, d.serial, status, guid if k else "", d.serial, k.auto_reconnect if k else None))
            if k:
                seen.add(k.guid)

        for k in known.values():
            if k.guid in seen:
                continue
            status = t("st_seen") if k.guid in on_network else t("st_offline")
            addr = f"{k.host}:{k.port}" if k.host and k.port else k.host
            rows.append(Row(k.label, addr, status, k.guid, "", k.auto_reconnect))
        return rows

    def _render(self, devices) -> None:
        rows = self._rows(devices)
        self.tree.blockSignals(True)
        selected = self.tree.currentItem().data(0, Qt.UserRole) if self.tree.currentItem() else None
        self.tree.clear()
        for r in rows:
            item = QTreeWidgetItem([r.name, r.address, r.status, ""])
            item.setData(0, Qt.UserRole, r)
            if r.auto is not None:
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(3, Qt.Checked if r.auto else Qt.Unchecked)
            self.tree.addTopLevelItem(item)
            if selected and (selected.guid, selected.serial) == (r.guid, r.serial):
                self.tree.setCurrentItem(item)
        self.tree.blockSignals(False)
        self.empty.setVisible(not rows)

        online = {d.serial: d.display_name for d in devices if d.is_online}
        for serial, name in self._online_before.items():
            wireless = ":" in serial or "._adb-tls" in serial
            if wireless and serial not in online:
                self._notify(t("disconnected", name=name))
        self._online_before = online

        n = len(online)
        self.tray.setIcon(self.icon_on if n else self.icon_off)
        self.tray.setToolTip("AirDebug · " + t("devices_online", n=n))
        self.tray_devices.clear()
        for r in rows:
            self.tray_devices.addAction(f"{r.name}  —  {r.status}").setEnabled(False)
        self.tray_devices.setEnabled(bool(rows))

    def _notify(self, msg: str) -> None:
        if self.ctl.store.settings.notifications and self.tray.isVisible():
            self.tray.showMessage("AirDebug", msg, self.icon_on, 3000)

    # ----------------------------------------------------- table events --

    def _item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        r: Row = item.data(0, Qt.UserRole)
        if column == 3 and r and r.guid:
            self.ctl.store.set_auto_reconnect(r.guid, item.checkState(3) == Qt.Checked)

    def _context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if not item:
            return
        r: Row = item.data(0, Qt.UserRole)
        menu = QMenu(self)
        if r.serial:
            menu.addAction(t("disconnect"), lambda: self._disconnect(r))
            menu.addAction(t("copy_serial"), lambda: QGuiApplication.clipboard().setText(r.serial))
        if r.guid:
            menu.addAction(t("reconnect_now"), self.tick)
            menu.addSeparator()
            menu.addAction(t("forget"), lambda: self._forget(r))
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _disconnect(self, r: Row) -> None:
        if r.guid:
            # Otherwise auto-reconnect would bring it straight back.
            self.ctl.store.set_auto_reconnect(r.guid, False)
        run_async(lambda: self.ctl.disconnect(r.serial), lambda _: self.tick(), self._error)

    def _forget(self, r: Row) -> None:
        if QMessageBox.question(self, "AirDebug", t("forget_confirm", name=r.name)) != QMessageBox.Yes:
            return
        self.ctl.store.forget(r.guid)
        if r.serial:
            run_async(lambda: self.ctl.disconnect(r.serial), lambda _: self.tick(), self._error)
        else:
            self.tick()

    # ---------------------------------------------------------- settings --

    def _set_auto(self, enabled: bool) -> None:
        self.ctl.store.update_settings(auto_reconnect=enabled)
        if self.tray_auto.isChecked() != enabled:
            self.tray_auto.setChecked(enabled)
        if enabled:
            self.tick()

    def _set_startup(self, enabled: bool) -> None:
        try:
            autostart.set_enabled(enabled)
        except OSError as e:
            self._error(str(e))

    def _set_language(self) -> None:
        lang = self.lang.currentData()
        self.ctl.store.update_settings(language=lang)
        if lang != "auto" and lang != current_language():
            QMessageBox.information(self, "AirDebug", t("lang_restart"))

    # ------------------------------------------------------------ window --

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.isVisible() and not self.isMinimized():
                self.hide()
            else:
                self.show_window()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._quitting or not QSystemTrayIcon.isSystemTrayAvailable():
            event.accept()
            return
        event.ignore()
        self.hide()
        if not self._tray_hint_shown:
            self._tray_hint_shown = True
            self._notify(t("tray_running"))
