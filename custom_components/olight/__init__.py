"""Olight for Home Assistant (unofficial) — the Ostation 2 Pro over the local network.

One config entry is one station. No cloud, no vendor app running in the background: the station is
a Tuya protocol 3.5 device and everything happens on the LAN.
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .const import CONF_DEVICE_ID, CONF_LOCAL_KEY, DOMAIN
from .coordinator import OstationCoordinator
from .tuya_client import HEARTBEAT_INTERVAL, OstationClient

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.TIME,
]

type OlightConfigEntry = ConfigEntry[OstationCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: OlightConfigEntry) -> bool:
    """Set up one station."""
    client = OstationClient(
        entry.data[CONF_DEVICE_ID], entry.data[CONF_HOST], entry.data[CONF_LOCAL_KEY]
    )
    coordinator = OstationCoordinator(hass, client, entry.title)
    # Fail setup loudly if the station never answers: unlike a cloud outage this is almost always a
    # wrong local key or a changed IP, and the user needs to be told rather than left with a
    # silently empty device.
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    # The station drops a quiet socket well inside the poll interval; a keep-alive on HA's own
    # timer stops with the entry, unlike a thread.
    entry.async_on_unload(async_track_time_interval(
        hass, coordinator.async_heartbeat, timedelta(seconds=HEARTBEAT_INTERVAL)))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OlightConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
        if coordinator is not None:
            await coordinator.async_shutdown()
    return ok
