# PyInstaller spec for AirDebug: builds a single windowed AirDebug.exe
# Usage:  pyinstaller --clean --noconfirm airdebug.spec
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ["airdebug/__main__.py"],
    pathex=["."],
    datas=[("airdebug/resources", "airdebug/resources")],
    hiddenimports=collect_submodules("zeroconf"),
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.Qt3DCore", "PySide6.QtQml", "PySide6.QtQuick"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AirDebug",
    icon="airdebug/resources/icon.ico",
    console=False,
    upx=False,
    version="scripts/version_info.txt",
)
