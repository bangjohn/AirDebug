"""Light and dark themes that follow the Windows app mode.

Every colour used by AirDebug's widgets comes from here, so text can never end
up white-on-white (or black-on-black) when Windows switches between light and
dark mode.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Theme:
    dark: bool
    window: str
    base: str  # list / input background
    alt_base: str
    text: str
    muted: str
    border: str
    button: str
    button_hover: str
    header: str
    accent: str
    accent_hover: str
    accent_text: str
    highlight: str
    ok: str
    error: str
    disabled: str


LIGHT = Theme(
    dark=False,
    window="#f6f8fa",
    base="#ffffff",
    alt_base="#f6f8fa",
    text="#1f2328",
    muted="#57606a",
    border="#d0d7de",
    button="#ffffff",
    button_hover="#eef1f4",
    header="#eaeef2",
    accent="#1b873f",
    accent_hover="#17733a",
    accent_text="#ffffff",
    highlight="#cfe6ff",
    ok="#1b873f",
    error="#c62828",
    disabled="#8c959f",
)

DARK = Theme(
    dark=True,
    window="#1e1f22",
    base="#26282c",
    alt_base="#2b2d31",
    text="#e6e6e6",
    muted="#a0a6ad",
    border="#3c3f45",
    button="#2f3136",
    button_hover="#3a3d43",
    header="#2b2d31",
    accent="#2ea043",
    accent_hover="#3fb950",
    accent_text="#ffffff",
    highlight="#1f4a7a",
    ok="#3fb950",
    error="#ff7b72",
    disabled="#6e7681",
)

_current: Theme = LIGHT


def current() -> Theme:
    return _current


def system_is_dark() -> bool:
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:  # Qt < 6.5
        return False


def _palette(t: Theme) -> QPalette:
    p = QPalette()
    c = QColor
    roles = {
        QPalette.Window: t.window,
        QPalette.WindowText: t.text,
        QPalette.Base: t.base,
        QPalette.AlternateBase: t.alt_base,
        QPalette.Text: t.text,
        QPalette.Button: t.button,
        QPalette.ButtonText: t.text,
        QPalette.ToolTipBase: t.base,
        QPalette.ToolTipText: t.text,
        QPalette.PlaceholderText: t.muted,
        QPalette.Highlight: t.highlight,
        QPalette.HighlightedText: t.text,
        QPalette.Link: t.accent,
        QPalette.BrightText: t.error,
    }
    for role, color in roles.items():
        p.setColor(QPalette.All, role, c(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, c(t.disabled))
    return p


def _check_path() -> str:
    from .. import paths

    return paths.resource("check.svg").as_posix()


def stylesheet(t: Theme) -> str:
    return f"""
QWidget {{ color: {t.text}; }}
QMainWindow, QDialog {{ background: {t.window}; }}
QLabel#title {{ font-size: 18px; font-weight: 700; color: {t.text}; }}
QLabel#muted {{ color: {t.muted}; }}
QPushButton {{
    background: {t.button}; color: {t.text};
    border: 1px solid {t.border}; border-radius: 6px; padding: 7px 12px;
}}
QPushButton:hover {{ background: {t.button_hover}; }}
QPushButton:disabled {{ color: {t.disabled}; }}
QPushButton#primary {{
    background: {t.accent}; color: {t.accent_text}; border: none; font-weight: 600; padding: 8px 14px;
}}
QPushButton#primary:hover {{ background: {t.accent_hover}; }}
QTreeWidget, QListWidget, QLineEdit, QComboBox {{
    background: {t.base}; color: {t.text};
    border: 1px solid {t.border}; border-radius: 6px;
}}
QLineEdit, QComboBox {{ padding: 4px 6px; }}
QTreeWidget::item, QListWidget::item {{ padding: 3px 2px; }}
QTreeWidget::item:selected, QListWidget::item:selected {{ background: {t.highlight}; color: {t.text}; }}
QHeaderView::section {{
    background: {t.header}; color: {t.text};
    border: none; border-bottom: 1px solid {t.border}; padding: 5px 6px; font-weight: 600;
}}
QCheckBox {{ color: {t.text}; spacing: 6px; }}
QCheckBox:disabled {{ color: {t.disabled}; }}
QCheckBox::indicator, QTreeWidget::indicator {{
    width: 14px; height: 14px; border-radius: 3px;
    border: 1px solid {t.muted}; background: {t.base};
}}
QCheckBox::indicator:checked, QTreeWidget::indicator:checked {{
    border: 1px solid {t.accent}; background: {t.accent}; image: url({_check_path()});
}}
QCheckBox::indicator:disabled {{ border-color: {t.border}; background: {t.alt_base}; }}
QMenu {{ background: {t.base}; color: {t.text}; border: 1px solid {t.border}; }}
QMenu::item:selected {{ background: {t.highlight}; }}
QMenu::item:disabled {{ color: {t.muted}; }}
QStatusBar {{ color: {t.muted}; }}
QToolTip {{ background: {t.base}; color: {t.text}; border: 1px solid {t.border}; }}
"""


def apply(app: QApplication | None = None, dark: bool | None = None) -> Theme:
    """Apply the light or dark theme to the whole application."""
    global _current
    app = app or QApplication.instance()
    if dark is None:
        dark = system_is_dark()
    _current = DARK if dark else LIGHT
    # Fusion renders the palette faithfully on every Windows version,
    # unlike the native "windowsvista"/"windows11" styles.
    app.setStyle("Fusion")
    app.setPalette(_palette(_current))
    app.setStyleSheet(stylesheet(_current))
    return _current


def follow_system(app: QApplication, on_change=None) -> None:
    """Re-apply the theme when Windows switches between light and dark mode."""
    try:
        hints = QGuiApplication.styleHints()

        def changed(*_):
            apply(app)
            if on_change:
                on_change()

        hints.colorSchemeChanged.connect(changed)
    except AttributeError:
        pass


def ok_style() -> str:
    return f"color:{_current.ok}; font-weight:600"


def error_style() -> str:
    return f"color:{_current.error}"
