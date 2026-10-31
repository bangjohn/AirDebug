# Contributing to AirDebug

Thanks for helping! Bug reports, translations and pull requests are all welcome.

## Reporting a bug

Please include:

- Windows version and AirDebug version (`AirDebug.exe --version`)
- Phone model and Android version
- What you did, what you expected, what happened
- The log file: run `AirDebug.exe --verbose`, reproduce, then attach `%APPDATA%\AirDebug\airdebug.log`

## Development setup

```powershell
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m airdebug --verbose
```

Before opening a pull request:

```powershell
ruff check airdebug tests
pytest
```

The pairing and reconnect logic lives in `airdebug/core.py` and has no Qt dependency; please add a test in `tests/test_core.py` (it uses a fake adb and a fake mDNS browser) for any behaviour change.

## Adding a language

All UI text is in `airdebug/i18n.py`. Add your language code to every entry and to `detect_language()` / the language combo box in `ui/main_window.py`. A test checks that no string is missing.
