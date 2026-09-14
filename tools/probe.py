#!/usr/bin/env python3
"""Talk to an Ostation directly, with no Home Assistant in the loop.

Use it the moment you have the local key: it proves the key and host are right, shows every raw
datapoint, and decodes the per-bay telemetry with the same code the integration uses. The raw DP110
/ DP112 / DP113 values it prints are exactly what is needed to confirm the payload layout on real
hardware, so keep a copy of the output when reporting an issue.

  python3 tools/probe.py --host 192.168.1.50 --id <22-char device id> --key <16-char local key>
  python3 tools/probe.py ... --watch     # keep polling and print only when something changes
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "olight"))

from protocol import SLOT_ORDER, decode_slots  # noqa: E402
from tuya_client import OstationClient, OstationError  # noqa: E402

TELEMETRY_DP = "110"


def render(dps: dict) -> str:
    lines = [json.dumps(dps, sort_keys=True)]
    slots = decode_slots(dps.get(TELEMETRY_DP))
    for slot in SLOT_ORDER:
        s = slots.get(slot)
        if s is None:
            lines.append(f"  {slot} ?      no record decoded")
            continue
        if not s.occupied:
            lines.append(f"  {s.label:5s} empty")
            continue
        lines.append(
            f"  {s.label:5s} {s.chemistry:9s} {s.soc:3d}%  {s.voltage} mV  {s.current} mA  "
            f"b12={s.byte12 if s.byte12 is not None else '?'}  {s.minutes} min  "
            f"{'charging' if s.charging else 'idle'}   raw={s.raw}"
        )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", required=True)
    ap.add_argument("--id", required=True, help="22-character Tuya device id")
    ap.add_argument("--key", required=True, help="16-character local key")
    ap.add_argument("--watch", action="store_true", help="poll until interrupted")
    ap.add_argument("--interval", type=float, default=5.0, help="seconds between polls")
    args = ap.parse_args()

    if len(args.id) != 22 or len(args.key) != 16:
        print("device id must be 22 characters and the local key 16", file=sys.stderr)
        return 2

    client = OstationClient(args.id, args.host, args.key)
    last = None
    try:
        while True:
            try:
                dps = client.status()
            except OstationError as err:
                print(f"error: {err}", file=sys.stderr)
                if not args.watch:
                    print("Check the host, that the key is current, and that the Olight app is "
                          "closed — the station accepts one local connection at a time.",
                          file=sys.stderr)
                    return 1
                time.sleep(args.interval)
                continue
            if dps != last:
                print(time.strftime("%H:%M:%S"), render(dps), sep="\n")
                last = dps
            if not args.watch:
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
