"""Application entry point."""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import sys

from . import __version__, paths
from .i18n import set_language, t

SINGLETON_KEY = "AirDebug-single-instance-v1"


def _setup_logging(verbose: bool) -> None:
    log_dir = paths.data_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(
            log_dir / "airdebug.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8"
        )
    ]
    if sys.stderr and sys.stderr.name != os.devnull:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=handlers,
    )


def _ensure_adb(parent=None):
    """Return an Adb instance, offering to download Platform-Tools if missing."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

    from .adb import Adb, AdbError, download_platform_tools, find_adb

    if find_adb():
        return Adb()

    ans = QMessageBox.question(
        parent,
        t("adb_missing_title"),
        t("adb_missing", path=paths.data_dir() / "platform-tools"),
    )
    if ans != QMessageBox.Yes:
        return None

    dlg = QProgressDialog(t("adb_downloading"), None, 0, 100, parent)
    dlg.setWindowModality(Qt.ApplicationModal)
    dlg.setMinimumDuration(0)
    dlg.show()

    def progress(done: int, total: int) -> None:
        if total:
            dlg.setValue(int(done * 100 / total))
        QApplication.processEvents()

    try:
        binary = download_platform_tools(progress)
    except (OSError, AdbError) as e:
        dlg.close()
        QMessageBox.critical(parent, t("adb_missing_title"), t("adb_failed", err=e))
        return None
    dlg.close()
    return Adb(binary)


def main(argv: list[str] | None = None) -> int:
    # A windowed (no console) exe has no stdout/stderr; give argparse somewhere to write.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")  # noqa: SIM115
    parser = argparse.ArgumentParser(prog="airdebug", description="Wireless ADB connector")
    parser.add_argument("--minimized", action="store_true", help="start hidden in the system tray")
    parser.add_argument("--verbose", action="store_true", help="debug logging")
    parser.add_argument("--version", action="version", version=f"AirDebug {__version__}")
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)
    log = logging.getLogger("airdebug")
    log.info("AirDebug %s starting", __version__)

    from PySide6.QtGui import QIcon
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtWidgets import QApplication, QMessageBox

    from .core import Controller
    from .discovery import Discovery
    from .store import Store
    from .ui.main_window import MainWindow

    app = QApplication(sys.argv[:1])
    app.setApplicationName("AirDebug")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(str(paths.resource("icon.png"))))
    app.setQuitOnLastWindowClosed(False)  # keep running in the tray

    # --- single instance: a second launch just shows the running window ---
    sock = QLocalSocket()
    sock.connectToServer(SINGLETON_KEY)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.waitForBytesWritten(300)
        log.info("Already running; asked the other instance to show itself")
        return 0
    QLocalServer.removeServer(SINGLETON_KEY)
    server = QLocalServer()
    server.listen(SINGLETON_KEY)

    store = Store()
    set_language(store.settings.language)

    adb = _ensure_adb()
    if adb is None:
        return 1
    try:
        adb.start_server()
    except Exception as e:  # noqa: BLE001 - show any startup failure to the user
        QMessageBox.critical(None, "AirDebug", str(e))
        return 1

    discovery = Discovery()
    ctl = Controller(adb, discovery, store)
    window = MainWindow(ctl, start_hidden=args.minimized or store.settings.start_minimized)
    discovery._on_change = window.bridge.discovery_changed.emit
    discovery.start()

    def on_new_connection():
        conn = server.nextPendingConnection()
        if conn:
            conn.readyRead.connect(lambda: (conn.readAll(), window.show_window()))

    server.newConnection.connect(on_new_connection)

    try:
        return app.exec()
    finally:
        discovery.stop()
        log.info("AirDebug stopped")


if __name__ == "__main__":
    sys.exit(main())
