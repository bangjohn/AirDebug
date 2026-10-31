# How AirDebug works

AirDebug does not implement the ADB protocol. It drives Google's official `adb` binary, the same way Android Studio's *Pair devices using Wi-Fi* dialog does, and adds network discovery and a reconnect loop around it.

## The two mDNS services

When **Wireless debugging** is on (Android 11+), the phone advertises itself on the local network with multicast DNS (Bonjour):

| Service type | When it is advertised | Used for |
|---|---|---|
| `_adb-tls-pairing._tcp` | Only while a pairing screen (QR or code) is open | `adb pair <ip>:<port> <code>` |
| `_adb-tls-connect._tcp` | Whenever Wireless debugging is on | `adb connect <ip>:<port>` |

The connect service's instance name looks like `adb-<serial>-<random>` and stays the same for a given phone, while its **port changes** every time Wireless debugging is toggled. That is why a remembered `ip:port` stops working, and why AirDebug keys remembered phones by the instance name (the *guid* that `adb pair` prints) instead of by address.

AirDebug browses for both services with [python-zeroconf](https://github.com/python-zeroconf/python-zeroconf), which is more reliable on Windows than adb's built-in mDNS backend.

## QR pairing

1. AirDebug creates a random service name `airdebug-XXXXXXXX` and a random 12-character password.
2. It shows them as a QR code using the Wi-Fi-style format Android's scanner expects:

   ```text
   WIFI:T:ADB;S:airdebug-XXXXXXXX;P:<password>;;
   ```

3. The phone scans it and starts advertising `_adb-tls-pairing._tcp` **with that exact instance name**, so AirDebug knows which phone answered.
4. AirDebug runs `adb pair <ip>:<port> <password>`. adb replies `Successfully paired to … [guid=adb-<serial>-<random>]`.
5. AirDebug waits for `_adb-tls-connect._tcp` with that guid, runs `adb connect`, reads `ro.product.model` for a friendly name, and remembers the phone.

## Pairing-code flow

Identical from step 4, except the user types the 6-digit code shown on the phone, and the IP:port comes from the discovered `_adb-tls-pairing._tcp` service (or is typed by hand).

## Reconnect loop

Every `check_interval` seconds (default 5), and right after any mDNS change:

1. `adb devices -l` gives the current state.
2. Wireless entries in the `offline` state are `adb disconnect`ed, since they block a fresh connection.
3. For each remembered phone with auto-reconnect enabled that isn't online:
   - if its connect service is visible via mDNS, `adb connect` to the advertised address and port;
   - otherwise try the last known address, at most once every 30 seconds (some networks block multicast).
4. Successful reconnects raise a tray notification.

All adb calls are serialised behind a lock and run on worker threads, so the UI never freezes.

## Files

| Path | Content |
|---|---|
| `%APPDATA%\AirDebug\airdebug.json` | Settings and remembered phones |
| `%APPDATA%\AirDebug\airdebug.log` | Rotating log (use `--verbose` for adb command traces) |
| `%APPDATA%\AirDebug\platform-tools\` | adb downloaded by AirDebug, if none was found |

## adb lookup order

1. `AIRDEBUG_ADB` environment variable
2. `platform-tools\` next to `AirDebug.exe` (portable setups)
3. `%APPDATA%\AirDebug\platform-tools\`
4. `%ANDROID_HOME%` / `%ANDROID_SDK_ROOT%` / `%LOCALAPPDATA%\Android\Sdk` (Android Studio's default)
5. `adb` on `PATH`
