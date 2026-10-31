"""Tiny translation table. English and Bahasa Indonesia.

Usage: ``t("pair_qr")`` or ``t("connected_to", name="Pixel 8")``.
"""

from __future__ import annotations

import locale
import os

_STRINGS: dict[str, dict[str, str]] = {
    # --- generic ---------------------------------------------------------
    "app_tagline": {
        "en": "Wireless ADB for Android, without Android Studio",
        "id": "ADB nirkabel untuk Android, tanpa Android Studio",
    },
    "ok": {"en": "OK", "id": "OK"},
    "cancel": {"en": "Cancel", "id": "Batal"},
    "close": {"en": "Close", "id": "Tutup"},
    "quit": {"en": "Quit AirDebug", "id": "Keluar dari AirDebug"},
    "show": {"en": "Open AirDebug", "id": "Buka AirDebug"},
    # --- actions ---------------------------------------------------------
    "pair_qr": {"en": "Pair with QR code", "id": "Pairing dengan QR code"},
    "pair_code": {"en": "Pair with pairing code", "id": "Pairing dengan kode"},
    "connect_ip": {"en": "Connect IP:port", "id": "Sambungkan IP:port"},
    "usb_to_wifi": {"en": "USB → Wi-Fi", "id": "USB → Wi-Fi"},
    "refresh": {"en": "Refresh", "id": "Muat ulang"},
    "disconnect": {"en": "Disconnect", "id": "Putuskan"},
    "forget": {"en": "Forget device", "id": "Lupakan perangkat"},
    "copy_serial": {"en": "Copy serial", "id": "Salin serial"},
    "reconnect_now": {"en": "Reconnect now", "id": "Sambungkan ulang sekarang"},
    # --- device table ----------------------------------------------------
    "col_device": {"en": "Device", "id": "Perangkat"},
    "col_address": {"en": "Address", "id": "Alamat"},
    "col_status": {"en": "Status", "id": "Status"},
    "col_auto": {"en": "Auto-reconnect", "id": "Sambung otomatis"},
    "st_connected": {"en": "● Connected", "id": "● Terhubung"},
    "st_offline": {"en": "○ Not connected", "id": "○ Tidak terhubung"},
    "st_seen": {"en": "◐ On network, connecting…", "id": "◐ Ada di jaringan, menyambung…"},
    "st_unauthorized": {"en": "⚠ Allow debugging on phone", "id": "⚠ Izinkan debugging di HP"},
    "st_usb": {"en": "● USB", "id": "● USB"},
    "empty_hint": {
        "en": "No devices yet. On your phone open Settings › Developer options › Wireless debugging, then click “Pair with QR code”.",
        "id": "Belum ada perangkat. Di HP buka Setelan › Opsi developer › Debugging nirkabel, lalu klik “Pairing dengan QR code”.",
    },
    # --- settings --------------------------------------------------------
    "opt_auto": {"en": "Auto-reconnect paired phones", "id": "Sambungkan ulang HP otomatis"},
    "opt_startup": {"en": "Start with Windows", "id": "Jalankan saat Windows mulai"},
    "opt_minimized": {"en": "Start minimized to tray", "id": "Mulai tersembunyi di tray"},
    "opt_notify": {"en": "Show notifications", "id": "Tampilkan notifikasi"},
    "opt_language": {"en": "Language", "id": "Bahasa"},
    "lang_restart": {
        "en": "Language will change after restarting AirDebug.",
        "id": "Bahasa akan berubah setelah AirDebug dibuka ulang.",
    },
    # --- QR dialog -------------------------------------------------------
    "qr_title": {"en": "Pair with QR code", "id": "Pairing dengan QR code"},
    "qr_steps": {
        "en": "1. Connect the phone to the same Wi-Fi as this PC.\n"
              "2. On the phone: Settings › Developer options › Wireless debugging.\n"
              "3. Tap “Pair device with QR code” and scan this code.",
        "id": "1. Sambungkan HP ke Wi-Fi yang sama dengan PC ini.\n"
              "2. Di HP: Setelan › Opsi developer › Debugging nirkabel.\n"
              "3. Ketuk “Sambungkan perangkat dengan kode QR”, lalu pindai kode ini.",
    },
    "qr_waiting": {"en": "Waiting for the phone to scan…", "id": "Menunggu HP memindai…"},
    "qr_found": {"en": "Phone found at {addr}, pairing…", "id": "HP ditemukan di {addr}, pairing…"},
    "qr_timeout": {
        "en": "Nobody scanned the code in time. Click “New code” to try again.",
        "id": "Kode tidak dipindai tepat waktu. Klik “Kode baru” untuk mencoba lagi.",
    },
    "qr_new": {"en": "New code", "id": "Kode baru"},
    # --- code dialog -----------------------------------------------------
    "code_title": {"en": "Pair with pairing code", "id": "Pairing dengan kode"},
    "code_steps": {
        "en": "On the phone tap “Pair device with pairing code”. It shows an IP address & port and a 6-digit code.",
        "id": "Di HP ketuk “Sambungkan perangkat dengan kode penyambungan”. HP akan menampilkan alamat IP & port serta kode 6 digit.",
    },
    "code_found": {"en": "Phones currently showing a pairing code:", "id": "HP yang sedang menampilkan kode pairing:"},
    "code_none": {"en": "(none detected yet, you can type the IP:port below)", "id": "(belum terdeteksi, ketik IP:port di bawah)"},
    "code_addr": {"en": "IP address & port", "id": "Alamat IP & port"},
    "code_code": {"en": "Wi-Fi pairing code", "id": "Kode penyambungan Wi-Fi"},
    "code_pair": {"en": "Pair", "id": "Pairing"},
    "code_bad": {"en": "The pairing code has 6 digits.", "id": "Kode pairing terdiri dari 6 digit."},
    # --- connect dialog --------------------------------------------------
    "connect_title": {"en": "Connect to IP:port", "id": "Sambungkan ke IP:port"},
    "connect_prompt": {
        "en": "Address shown under “IP address & port” on the Wireless debugging screen (phone must be paired already):",
        "id": "Alamat di bawah “Alamat IP & port” pada layar Debugging nirkabel (HP harus sudah dipairing):",
    },
    # --- USB -------------------------------------------------------------
    "usb_none": {
        "en": "No phone connected by USB. Plug it in and allow USB debugging first.",
        "id": "Tidak ada HP tersambung lewat USB. Colokkan dan izinkan debugging USB dulu.",
    },
    "usb_pick": {"en": "Choose the USB phone to switch to Wi-Fi:", "id": "Pilih HP USB yang akan dialihkan ke Wi-Fi:"},
    "usb_no_ip": {
        "en": "Could not read the phone's Wi-Fi IP. Is Wi-Fi turned on?",
        "id": "Tidak bisa membaca IP Wi-Fi HP. Apakah Wi-Fi menyala?",
    },
    # --- results / errors ------------------------------------------------
    "pairing": {"en": "Pairing…", "id": "Pairing…"},
    "connecting": {"en": "Connecting…", "id": "Menyambungkan…"},
    "connected_to": {"en": "Connected to {name}", "id": "Terhubung ke {name}"},
    "reconnected": {"en": "Reconnected {name}", "id": "Tersambung ulang: {name}"},
    "disconnected": {"en": "{name} disconnected", "id": "{name} terputus"},
    "paired_not_connected": {
        "en": "Paired successfully, but could not connect yet. AirDebug will keep trying automatically.",
        "id": "Pairing berhasil, tetapi belum bisa tersambung. AirDebug akan terus mencoba otomatis.",
    },
    "err_wrong_code": {
        "en": "Wrong pairing code, or the code expired. Open the pairing screen again and retry.",
        "id": "Kode pairing salah atau sudah kedaluwarsa. Buka lagi layar pairing di HP dan coba lagi.",
    },
    "err_unreachable": {
        "en": "Could not reach the phone. Make sure the PC and phone are on the same Wi-Fi and the pairing screen is still open.",
        "id": "HP tidak bisa dijangkau. Pastikan PC dan HP di Wi-Fi yang sama dan layar pairing masih terbuka.",
    },
    "err_no_connect_port": {
        "en": "The phone did not announce its connect port. Is Wireless debugging still on?",
        "id": "HP tidak mengumumkan port sambungannya. Apakah Debugging nirkabel masih menyala?",
    },
    "err_format": {
        "en": "Use the format IP:port, for example 192.168.1.5:37099",
        "id": "Gunakan format IP:port, contoh 192.168.1.5:37099",
    },
    # --- adb setup -------------------------------------------------------
    "adb_missing_title": {"en": "ADB not found", "id": "ADB tidak ditemukan"},
    "adb_missing": {
        "en": "AirDebug needs Google's Android Platform-Tools (adb). Download them now (about 7 MB)?\n\n"
              "They will be stored in {path}.",
        "id": "AirDebug membutuhkan Android Platform-Tools (adb) dari Google. Unduh sekarang (sekitar 7 MB)?\n\n"
              "File akan disimpan di {path}.",
    },
    "adb_downloading": {"en": "Downloading Platform-Tools…", "id": "Mengunduh Platform-Tools…"},
    "adb_failed": {
        "en": "Could not download Platform-Tools: {err}\n\nYou can install them manually and set the AIRDEBUG_ADB variable.",
        "id": "Gagal mengunduh Platform-Tools: {err}\n\nAnda bisa memasangnya manual lalu mengatur variabel AIRDEBUG_ADB.",
    },
    "adb_version": {"en": "adb: {ver}", "id": "adb: {ver}"},
    "tray_running": {
        "en": "AirDebug is still running in the tray and will keep your phones connected.",
        "id": "AirDebug tetap berjalan di tray dan menjaga HP tetap tersambung.",
    },
    "devices_online": {"en": "{n} device(s) connected", "id": "{n} perangkat terhubung"},
    "forget_confirm": {
        "en": "Forget {name}? AirDebug will stop reconnecting it.",
        "id": "Lupakan {name}? AirDebug tidak akan menyambungkannya lagi.",
    },
}

_lang = "en"


def detect_language() -> str:
    for var in ("AIRDEBUG_LANG", "LANG", "LC_ALL"):
        v = os.environ.get(var, "")
        if v:
            return "id" if v.lower().startswith(("id", "in")) else "en"
    try:
        code = locale.getlocale()[0] or ""
    except ValueError:
        code = ""
    if not code:
        try:
            import ctypes  # Windows UI language

            lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()  # type: ignore[attr-defined]
            return "id" if lcid & 0x3FF == 0x21 else "en"
        except Exception:
            return "en"
    return "id" if code.lower().startswith(("id", "in", "indonesian")) else "en"


def set_language(lang: str) -> None:
    global _lang
    _lang = detect_language() if lang in ("", "auto") else ("id" if lang == "id" else "en")


def current_language() -> str:
    return _lang


def t(key: str, **kw) -> str:
    entry = _STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(_lang) or entry["en"]
    return text.format(**kw) if kw else text


def keys() -> dict[str, dict[str, str]]:
    return _STRINGS
