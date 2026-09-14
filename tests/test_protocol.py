"""Decoder tests. Pure functions, so they run without Home Assistant or a station."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "olight"))

import protocol  # noqa: E402
from protocol import RECORD_LEN, SLOT_ORDER, decode_slots  # noqa: E402


# The DP110 blob exactly as published in tuya-local issue #6069.
PUBLISHED_DUMP = (
    "03016400000000000578000019000000000401640000000005780000190000000001"
    "01640000000005780000190000000002016400000000057800001900000000"
)


def record(slot, chem=0x01, soc=100, hours=0, mins=0, mv=1400, ca=0, temp=25):
    """Build one 17-byte bay record."""
    return bytes([slot, chem, soc, hours, mins, 0, 0, 0]) \
        + mv.to_bytes(2, "big") + ca.to_bytes(2, "big") + bytes([temp, 0, 0, 0, 0])


def payload(*records):
    return b"".join(records).hex()


def test_record_length_matches_spec():
    assert len(record(3)) == RECORD_LEN


def test_decodes_a_full_four_bay_payload():
    raw = payload(*(record(s) for s in SLOT_ORDER))
    assert len(bytes.fromhex(raw)) == 68
    slots = decode_slots(raw)
    assert set(slots) == set(SLOT_ORDER)
    aa1 = slots[3]
    assert (aa1.label, aa1.size) == ("AA1", "AA")
    assert (aa1.chemistry, aa1.soc, aa1.voltage, aa1.temperature) == ("nimh", 100, 1400, 25)


def test_published_dump_degrades_to_the_trustworthy_bay():
    """The DP110 dump published in tuya-local issue #6069 is 65 bytes, not 68.

    Zero bytes were lost transcribing it, so only the first record survives intact. That record is
    what confirms the field layout (1400 mV / 25 C on a charged Ni-MH cell). The decoder must
    recover it and discard the three misaligned ones rather than publishing impossible readings.
    """
    slots = decode_slots(PUBLISHED_DUMP)
    assert len(bytes.fromhex(PUBLISHED_DUMP)) == 65
    assert set(slots) == {3}
    assert (slots[3].voltage, slots[3].temperature, slots[3].soc) == (1400, 25, 100)


def test_empty_bay_reports_none_not_zero():
    """0 mV means no cell. Reporting 0% would read as a dead battery instead of an empty bay."""
    slots = decode_slots(payload(record(3, chem=0, soc=0, mv=0, temp=0)))
    bay = slots[3]
    assert bay.occupied is False
    assert bay.soc is None and bay.voltage is None and bay.temperature is None


def test_charging_is_driven_by_current():
    charging = decode_slots(payload(record(3, soc=40, ca=50)))[3]
    assert charging.charging is True
    assert charging.current == 500  # the raw field is tens of milliamps
    assert decode_slots(payload(record(3, ca=0)))[3].charging is False


def test_elapsed_time_is_flattened_to_minutes():
    assert decode_slots(payload(record(3, hours=2, mins=30)))[3].minutes == 150


@pytest.mark.parametrize("code,name", [(0x00, "detecting"), (0x01, "nimh"), (0x02, "liion")])
def test_known_chemistries(code, name):
    assert decode_slots(payload(record(3, chem=code, mv=1400)))[3].chemistry == name


def test_implausible_records_are_dropped():
    """A misaligned record decodes to physics that cannot happen; it must not reach a sensor."""
    bogus = record(4, mv=30720)
    slots = decode_slots(payload(record(3), bogus))
    assert 3 in slots and 4 not in slots


def test_base64_payload_is_accepted():
    """Some firmware/library combinations hand the raw DP over as base64 rather than hex."""
    import base64
    raw = b"".join(record(s) for s in SLOT_ORDER)
    assert decode_slots(base64.b64encode(raw).decode())[3].voltage == 1400


@pytest.mark.parametrize("junk", ["", None, "zzzz", 0, [], "0x"])
def test_garbage_never_raises(junk):
    assert decode_slots(junk) == {}


def test_trailing_byte_still_decodes_every_bay():
    """A firmware revision appending a byte must not take all four bays offline."""
    raw = b"".join(record(s) for s in SLOT_ORDER) + b"\x00"
    slots = decode_slots(raw.hex())
    assert set(slots) == set(SLOT_ORDER)


def test_unknown_slot_ids_are_ignored():
    assert decode_slots(payload(record(9))) == {}


def test_labels_cover_every_slot():
    assert set(protocol.SLOT_LABELS) == set(SLOT_ORDER) == set(protocol.SLOT_SIZE)
