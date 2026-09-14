#!/usr/bin/env python3
"""List the devices on a Tuya IoT project with their local keys — no phone needed past the QR scan.

Prerequisites (one-off, ~15 minutes, free):
  1. Sign up at https://iot.tuya.com and create a Cloud project (Smart Home, your data centre —
     for Italy that's "Central Europe").
  2. Project → Devices → Link App Account → Add App Account → scan the QR code with the app that
     holds the station (the Olight app: Me → scan icon; or Smart Life if you re-paired it there).
  3. Project → Overview: copy Access ID and Access Secret.

Then:
  python3 tools/get_local_key.py --id <ACCESS_ID> --secret <ACCESS_SECRET> --region eu
"""

import argparse
import json
import sys

import tinytuya

REGIONS = {"eu": "eu", "eu-w": "eu-w", "us": "us", "us-e": "us-e", "cn": "cn", "in": "in"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", required=True, help="Access ID from the Tuya IoT project overview")
    ap.add_argument("--secret", required=True, help="Access Secret from the same page")
    ap.add_argument("--region", default="eu", choices=REGIONS, help="Data centre of the project")
    ap.add_argument("--json", action="store_true", help="Print the raw device list as JSON")
    args = ap.parse_args()

    cloud = tinytuya.Cloud(apiRegion=args.region, apiKey=args.id, apiSecret=args.secret)
    devices = cloud.getdevices(verbose=False)
    if isinstance(devices, dict) and devices.get("Error"):
        print(f"Tuya cloud refused the request: {devices}", file=sys.stderr)
        print("Usual causes: wrong region, Access ID/Secret typo, project subscription expired, "
              "or the app account was never linked to the project.", file=sys.stderr)
        return 1
    if not devices:
        print("The project sees no devices. The app account is not linked, or the app's cloud "
              "partition is not visible to the IoT platform (a known limitation of some OEM apps).")
        return 2

    if args.json:
        print(json.dumps(devices, indent=2))
        return 0
    for d in devices:
        print(f"{d.get('name', '?'):28s} id={d.get('id')}  key={d.get('key')}  "
              f"product={d.get('product_id', '?')}  ip={d.get('ip', '?')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
