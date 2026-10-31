# Build AirDebug.exe on Windows.
#   powershell -ExecutionPolicy Bypass -File scripts\build.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path .venv)) { py -3 -m venv .venv }
& .venv\Scripts\python.exe -m pip install --upgrade pip
& .venv\Scripts\python.exe -m pip install -r requirements-dev.txt
& .venv\Scripts\python.exe -m pytest -q
& .venv\Scripts\pyinstaller.exe --clean --noconfirm airdebug.spec

Write-Host ""
Write-Host "Done: dist\AirDebug.exe" -ForegroundColor Green
