# Getting the local key — fully local, no cloud

The station is a Tuya device and its LAN sessions are encrypted with a 16-character key that is
unique to your unit. You need that key (and the 22-character device id) once; after that Home
Assistant talks to the station entirely over your LAN and you can block it from the internet.

This is the **fully local** route: an Android emulator on your own machine, no phone, no Tuya cloud
account. If you would rather use a one-time cloud lookup instead, see
[`tools/get_local_key.py`](../tools/get_local_key.py) — but everything below stays off the cloud.

## Why an emulator

The key is cached, encrypted, inside the Olight app and is only decrypted at runtime. The Tuya SDK
conveniently writes both the device id and the local key to Android's log as it syncs, so running
the app once and reading the log is enough. See [REVERSE-ENGINEERING.md](REVERSE-ENGINEERING.md)
for why there is no purely-static shortcut.

## You need

- A machine with hardware virtualisation (any Mac, or a PC/Linux box with VT-x/AMD-V). On Apple
  Silicon the emulator image must be **arm64**; on Intel/AMD, **x86_64**.
- **Android Studio** (bundles the SDK, the emulator and `adb`), or just the command-line tools.
- The **Olight** app APK — install it from the Play Store inside the emulator, or side-load
  `com.olight.omall`.

## Steps

1. **Create an emulator with Google APIs** (not "Google Play" — a plain Google APIs image is
   easier to work with over adb). Pixel-class device, recent API level.

   ```bash
   # command-line only, adjust the image to your architecture:
   sdkmanager "system-images;android-34;google_apis;arm64-v8a"   # or x86_64
   avdmanager create avd -n olight -k "system-images;android-34;google_apis;arm64-v8a"
   emulator -avd olight
   ```

2. **Install and sign in.** Install the Olight app in the emulator, create/sign into your Olight
   account — the same one your station is registered to. Wait until the station appears in the app.

   > The emulator has no Bluetooth/Wi-Fi radio of its own, so you cannot *pair* a new station from
   > it. This works because the station is **already paired** to your account; the app just syncs
   > it down from the cloud, and with it the local key. If your station is not yet set up, pair it
   > from a real phone first, then sign into that account here.

3. **Read the key from the log.** With the emulator running:

   ```bash
   adb logcat -v raw -s Thing-Network:D -e 'localkey:|deviceId:'
   ```

   Force-stop and reopen the Olight app so it re-syncs. The 22-character device id and the
   16-character local key appear in the log.

   If that tag is quiet on your app build, widen it:

   ```bash
   adb logcat | grep -iE 'localkey|local_key|devId|deviceId'
   ```

4. **Find the station's IP** on your LAN (your router's client list, or `nmap -p 6668 <subnet>` —
   Tuya devices listen on TCP 6668). A DHCP reservation for it is worth setting now.

5. **Add it to Home Assistant.** Settings → Devices & Services → Add Integration → Olight, and enter
   the IP, device id and local key.

## If the key ever stops working

Re-pairing the station, or a factory reset, makes the Tuya cloud issue a **new** local key. If Home
Assistant suddenly cannot connect after you have touched the station's setup, repeat the steps above
and update the key in the integration's options.
