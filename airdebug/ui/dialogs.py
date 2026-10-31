"""Pairing dialogs: QR code, pairing code and manual IP:port."""

from __future__ import annotations

import io
import threading

import qrcode
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from ..core import Cancelled, ConnectResult, Controller, QrSession, parse_host_port
from ..discovery import PAIRING
from ..i18n import t
from .workers import run_async


def qr_pixmap(text: str, size: int = 280) -> QPixmap:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    pm = QPixmap()
    pm.loadFromData(buf.getvalue(), "PNG")
    return pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def _status_label() -> QLabel:
    lbl = QLabel()
    lbl.setWordWrap(True)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setMinimumHeight(48)
    return lbl


class _BaseDialog(QDialog):
    """Common bits: a result signal and a cancel flag for worker threads."""

    connected = Signal(object)  # ConnectResult

    def __init__(self, ctl: Controller, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        self._cancel = threading.Event()
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

    def done(self, r: int) -> None:  # called by accept()/reject()/close
        self._cancel.set()
        super().done(r)

    def _alive(self) -> bool:
        return not self._cancel.is_set()

    def _finish(self, res: ConnectResult, status: QLabel) -> None:
        if not self._alive():
            return
        if res.ok:
            self.connected.emit(res)
            status.setStyleSheet("color:#1b873f; font-weight:600")
            status.setText("✓ " + res.message)
            QTimer.singleShot(1200, self.accept)
        else:
            status.setStyleSheet("color:#c62828")
            status.setText(res.message)


# --------------------------------------------------------------------------- #
# QR code
# --------------------------------------------------------------------------- #


class QrPairDialog(_BaseDialog):
    def __init__(self, ctl: Controller, parent=None):
        super().__init__(ctl, parent)
        self.setWindowTitle(t("qr_title"))
        lay = QVBoxLayout(self)

        steps = QLabel(t("qr_steps"))
        steps.setWordWrap(True)
        lay.addWidget(steps)

        self.qr = QLabel()
        self.qr.setAlignment(Qt.AlignCenter)
        self.qr.setMinimumSize(300, 300)
        lay.addWidget(self.qr)

        self.status = _status_label()
        lay.addWidget(self.status)

        row = QHBoxLayout()
        self.btn_new = QPushButton(t("qr_new"))
        self.btn_new.clicked.connect(self.start)
        close = QPushButton(t("close"))
        close.clicked.connect(self.reject)
        row.addWidget(self.btn_new)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)

        self._generation = 0
        self.start()

    def start(self) -> None:
        self._generation += 1
        gen = self._generation
        session = QrSession.new()
        self.qr.setPixmap(qr_pixmap(session.payload))
        self.status.setStyleSheet("")
        self.status.setText(t("qr_waiting"))
        self.btn_new.setEnabled(False)

        def stale() -> bool:
            return self._cancel.is_set() or gen != self._generation

        def work():
            svc = self.ctl.wait_for_qr_scan(session, timeout=120, cancelled=stale)
            return svc

        def found(svc):
            if stale():
                return
            self.status.setText(t("qr_found", addr=svc.address))
            run_async(
                lambda: self.ctl.pair_and_connect(svc.host, svc.port, session.password, cancelled=stale),
                lambda res: (not stale()) and self._done(res),
                lambda err: (not stale()) and self._error(err),
            )

        run_async(work, found, lambda err: (not stale()) and self._error(err))

    def _done(self, res: ConnectResult) -> None:
        self.btn_new.setEnabled(True)
        self._finish(res, self.status)

    def _error(self, err: str) -> None:
        if err == Cancelled.__name__:
            return
        self.btn_new.setEnabled(True)
        self.status.setStyleSheet("color:#c62828")
        self.status.setText(t("qr_timeout") if "QR" in err or "time" in err.lower() else err)


# --------------------------------------------------------------------------- #
# Pairing code
# --------------------------------------------------------------------------- #


class CodePairDialog(_BaseDialog):
    def __init__(self, ctl: Controller, parent=None):
        super().__init__(ctl, parent)
        self.setWindowTitle(t("code_title"))
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)

        steps = QLabel(t("code_steps"))
        steps.setWordWrap(True)
        lay.addWidget(steps)

        lay.addWidget(QLabel(t("code_found")))
        self.list = QListWidget()
        self.list.setMaximumHeight(110)
        self.list.currentItemChanged.connect(self._picked)
        lay.addWidget(self.list)

        form = QFormLayout()
        self.addr = QLineEdit()
        self.addr.setPlaceholderText("192.168.1.5:37099")
        self.code = QLineEdit()
        self.code.setPlaceholderText("123456")
        self.code.setMaxLength(6)
        mono = QFont("Consolas")
        mono.setPointSize(14)
        self.code.setFont(mono)
        form.addRow(t("code_addr").replace("&", "&&"), self.addr)
        form.addRow(t("code_code"), self.code)
        lay.addLayout(form)

        self.status = _status_label()
        lay.addWidget(self.status)

        buttons = QDialogButtonBox()
        self.btn_pair = buttons.addButton(t("code_pair"), QDialogButtonBox.AcceptRole)
        buttons.addButton(t("cancel"), QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self._pair)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        self._timer = QTimer(self, interval=1000, timeout=self._refresh)
        self._timer.start()
        self._refresh()
        self.code.setFocus()

    def _refresh(self) -> None:
        current = {self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())}
        services = {s.address: s for s in self.ctl.discovery.services(PAIRING)}
        if set(services) == current - {None}:
            return
        self.list.clear()
        if not services:
            item = QListWidgetItem(t("code_none"))
            item.setFlags(Qt.NoItemFlags)
            self.list.addItem(item)
            return
        for addr, svc in services.items():
            item = QListWidgetItem(f"📱 {addr}   ({svc.instance})")
            item.setData(Qt.UserRole, addr)
            self.list.addItem(item)
        if len(services) == 1 and not self.addr.text():
            self.list.setCurrentRow(0)

    def _picked(self, item) -> None:
        if item and item.data(Qt.UserRole):
            self.addr.setText(item.data(Qt.UserRole))
            self.code.setFocus()

    def _pair(self) -> None:
        try:
            host, port = parse_host_port(self.addr.text())
        except ValueError as e:
            self._fail(str(e))
            return
        code = self.code.text().strip()
        if not (len(code) == 6 and code.isdigit()):
            self._fail(t("code_bad"))
            return
        self.btn_pair.setEnabled(False)
        self.status.setStyleSheet("")
        self.status.setText(t("pairing"))
        run_async(
            lambda: self.ctl.pair_and_connect(host, port, code, cancelled=lambda: not self._alive()),
            self._done,
            self._fail,
        )

    def _done(self, res: ConnectResult) -> None:
        if not self._alive():
            return
        self.btn_pair.setEnabled(True)
        self._finish(res, self.status)

    def _fail(self, msg: str) -> None:
        if not self._alive():
            return
        self.btn_pair.setEnabled(True)
        self.status.setStyleSheet("color:#c62828")
        self.status.setText(msg)


# --------------------------------------------------------------------------- #
# Manual IP:port (already paired phone)
# --------------------------------------------------------------------------- #


class ConnectDialog(_BaseDialog):
    def __init__(self, ctl: Controller, parent=None):
        super().__init__(ctl, parent)
        self.setWindowTitle(t("connect_title"))
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lbl = QLabel(t("connect_prompt"))
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        self.addr = QLineEdit()
        self.addr.setPlaceholderText("192.168.1.5:41235")
        lay.addWidget(self.addr)
        self.status = _status_label()
        lay.addWidget(self.status)
        buttons = QDialogButtonBox()
        self.btn = buttons.addButton(t("connect_ip"), QDialogButtonBox.AcceptRole)
        buttons.addButton(t("cancel"), QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self._go)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _go(self) -> None:
        try:
            host, port = parse_host_port(self.addr.text())
        except ValueError as e:
            self.status.setStyleSheet("color:#c62828")
            self.status.setText(str(e))
            return
        self.btn.setEnabled(False)
        self.status.setStyleSheet("")
        self.status.setText(t("connecting"))

        def done(res):
            if self._alive():
                self.btn.setEnabled(True)
                self._finish(res, self.status)

        def fail(err):
            if self._alive():
                self.btn.setEnabled(True)
                self._finish(ConnectResult(False, err), self.status)

        run_async(lambda: self.ctl.connect_manual(host, port), done, fail)
