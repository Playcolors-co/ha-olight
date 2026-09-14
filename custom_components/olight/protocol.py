"""Pure decoding of the Ostation's Tuya datapoints — no I/O, so it can be tested without hardware.

The interesting one is DP110: a raw blob carrying the live state of all four charging bays at once.
Everything else is a plain boolean/integer DP.
"""

from __future__ import annotations

import base64
import binascii
import logging
from dataclasses import dataclass, field

_LOGGER = logging.getLogger(__name__)

# One telemetry record per bay. Confirmed against a real DP110 dump: a Ni-MH cell at 100% read
# 0x0578 mV (1400 mV) at offset 8-9 and 0x19 (25 °C) at offset 12, both physically sensible.
RECORD_LEN = 17

# Field offsets inside a record.
_OFF_SLOT, _OFF_CHEM, _OFF_SOC, _OFF_HOURS, _OFF_MINS = 0, 1, 2, 3, 4
_OFF_VOLTAGE = slice(8, 10)   # big-endian uint16, millivolts
_OFF_CURRENT = slice(10, 12)  # big-endian uint16, tens of milliamps
_OFF_TEMP = 12                # degrees Celsius

CHEMISTRY = {0x00: "detecting", 0x01: "nimh", 0x02: "liion"}

# Sanity ceilings. A misaligned record decodes into physically impossible numbers (a corrupted dump
# yielded 30.7 V on a AA bay); publishing those as sensor values poisons long-term statistics and
# any automation reading them, so a record that breaks physics is dropped instead.
MAX_VOLTAGE_MV = 6000   # comfortably above Li-ion AA charging voltage
MAX_CURRENT_MA = 5000
MAX_TEMP_C = 100

# The station reports bays by its own internal id; these are the labels printed on the unit.
# Keying off the embedded id (rather than the record's position) survives reordering.
SLOT_LABELS = {1: "AAA1", 2: "AAA2", 3: "AA1", 4: "AA2"}
SLOT_SIZE = {1: "AAA", 2: "AAA", 3: "AA", 4: "AA"}
SLOT_ORDER = (3, 4, 1, 2)


@dataclass(slots=True)
class SlotState:
    """Live state of one charging bay."""

    slot: int
    chemistry: str
    soc: int | None            # state of charge, %
    minutes: int               # elapsed charge time
    voltage: int | None        # mV
    current: int               # mA
    temperature: int | None    # °C
    raw: str = field(repr=False, default="")

    @property
    def label(self) -> str:
        return SLOT_LABELS.get(self.slot, f"Slot {self.slot}")

    @property
    def size(self) -> str | None:
        return SLOT_SIZE.get(self.slot)

    @property
    def occupied(self) -> bool:
        """A bay with no cell reads 0 mV.

        The station keeps reporting a 'ghost' voltage for a short while after a cell is pulled, so
        voltage dropping to exactly zero is the only reliable empty signal — not the SoC, which
        stays at its last value.
        """
        return bool(self.voltage)

    @property
    def charging(self) -> bool:
        return self.current > 0


def _as_bytes(value) -> bytes:
    """DP110 arrives as hex from some firmware/library combinations and base64 from others."""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if not isinstance(value, str) or not value:
        return b""
    text = value.strip()
    try:
        return bytes.fromhex(text)
    except (ValueError, binascii.Error):
        pass
    try:
        return base64.b64decode(text, validate=True)
    except (ValueError, binascii.Error):
        _LOGGER.warning("DP110 is neither hex nor base64: %r", text[:80])
        return b""


def _plausible_record(buf: bytes, i: int) -> bool:
    """Does a record start at this offset? Used only to resync a malformed payload."""
    if i + RECORD_LEN > len(buf):
        return False
    return buf[i] in SLOT_LABELS and buf[i + 1] in CHEMISTRY and buf[i + 2] <= 100


def _split(buf: bytes) -> list[bytes]:
    """Slice the blob into per-bay records.

    Normally a clean multiple of RECORD_LEN. If it isn't, we resync on record headers rather than
    returning nothing: a firmware revision that adds a trailing byte would otherwise take every
    sensor offline, and a partial read is still worth showing.
    """
    if buf and len(buf) % RECORD_LEN == 0:
        return [buf[i:i + RECORD_LEN] for i in range(0, len(buf), RECORD_LEN)]
    if buf:
        _LOGGER.debug("DP110 length %d is not a multiple of %d — resyncing on headers",
                      len(buf), RECORD_LEN)
    out, i = [], 0
    while i < len(buf):
        if _plausible_record(buf, i):
            out.append(buf[i:i + RECORD_LEN])
            i += RECORD_LEN
        else:
            i += 1
    return out


def _u16(chunk: bytes) -> int:
    return int.from_bytes(chunk, "big")


def _sane(voltage: int, current: int, temp: int) -> bool:
    return voltage <= MAX_VOLTAGE_MV and current <= MAX_CURRENT_MA and temp <= MAX_TEMP_C


def decode_slots(value) -> dict[int, SlotState]:
    """Decode DP110 into one SlotState per bay, keyed by the station's slot id."""
    slots: dict[int, SlotState] = {}
    for rec in _split(_as_bytes(value)):
        slot = rec[_OFF_SLOT]
        if slot not in SLOT_LABELS:
            continue
        voltage = _u16(rec[_OFF_VOLTAGE])
        current = _u16(rec[_OFF_CURRENT]) * 10
        soc = rec[_OFF_SOC]
        temp = rec[_OFF_TEMP]
        if not _sane(voltage, current, temp):
            _LOGGER.debug("dropping implausible DP110 record for slot %s: %s", slot, rec.hex())
            continue
        empty = voltage == 0
        slots[slot] = SlotState(
            slot=slot,
            chemistry=CHEMISTRY.get(rec[_OFF_CHEM], "unknown"),
            # Don't report 0% for an empty bay: that reads as a dead cell rather than no cell.
            soc=None if empty else soc,
            minutes=rec[_OFF_HOURS] * 60 + rec[_OFF_MINS],
            voltage=None if empty else voltage,
            current=current,
            temperature=None if empty or temp == 0 else temp,
            raw=rec.hex(),
        )
    return slots
