# Getting the local key with a one-time cloud lookup — phone only

For when you cannot run an emulator or borrow an Android phone. Everything here is done from
your phone plus one script on any machine that can reach the internet. It touches Tuya's cloud
**once, read-only**; the integration itself stays fully local afterwards and you can block the
station from the internet at the router.

## If you paired the station "without an account"

The Olight app lets you add the station without signing up. Under the hood the Tuya SDK still
creates an account — an **anonymous** one, bound to that one installation of the app on your phone.
Nobody can sign into it from anywhere else, which rules out the emulator route entirely. It also
means there is nothing to preserve: you lose nothing by re-pairing the station to a different app.

So the reliable path is to pair it with **Smart Life** (Tuya's own app, iOS and Android), for which
linking to the Tuya developer platform is the documented, supported procedure. Vendor apps like
Olight's *sometimes* link too, so try that first — it costs nothing.

## 1. Create a Tuya developer project (5 minutes, free)

1. Go to <https://iot.tuya.com> and sign up (email + verification code). Choose the data centre
   nearest you — for Italy and most of Europe, **Central Europe**.
2. **Cloud → Development → Create Cloud Project.** Any name; industry *Smart Home*; development
   method *Smart Home*; data centre as above. On the next screen keep the default API products.
3. Open the project. **Overview** shows the **Access ID/Client ID** and **Access Secret/Client
   Secret** — you will need both later.

## 2. Link the app that holds the station

In the project: **Devices → Link App Account → Add App Account**. A QR code appears.

- **Try the Olight app first**: *Me → scan icon* (top right). Scan the QR. Back on the website,
  if the station appears under *Devices*, skip to step 4.
- **Otherwise, re-pair with Smart Life**:
  1. Install **Smart Life** and create an account. Put the phone on the **2.4 GHz** Wi-Fi the
     station will use (it will not join 5 GHz).
  2. On the station: tap the screen → **Settings → Connection**. This puts it in pairing mode.
  3. In Smart Life: **+ → Add Device**. Keep Bluetooth on — the station is discovered over
     Bluetooth and then handed your Wi-Fi. Follow the prompts until it shows in the app.
  4. Back on iot.tuya.com: **Link App Account → Add App Account**, and scan the QR from Smart
     Life (*Me → scan icon*). The station now appears under *Devices*.

Re-pairing issues a **new** local key. Whatever key the Olight app held is now dead; the one you
read next is the current one.

## 3. Read the key

From the repository, on any machine with Python and internet:

```bash
pip install tinytuya
python3 tools/get_local_key.py --id <Access ID> --secret <Access Secret> --region eu
```

It prints every device on the project with its id, local key and (if known) IP. `--json` dumps
the raw list.

## 4. Prove it on the LAN

```bash
python3 tools/probe.py --host <station IP> --id <device id> --key <local key>
```

That is the integration's own decoder talking to the station directly. If it prints the four
bays, add the station in Home Assistant with the same three values.

## Notes

- The project's trial subscription expires after a while; it only matters for the lookup, never
  for the integration, and can be renewed for free.
- Once you have the key you can delete the project, remove Smart Life, and block the station at
  the router. The key stays valid until the station is paired again.
