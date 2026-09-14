"""Blocking Tuya LAN client, kept off the event loop.

The Ostation speaks Tuya protocol 3.5 on the local network and **accepts a single local connection
at a time** — if Home Assistant reconnects on every poll, or the Olight app is open at the same
time, the station drops whoever connected first. So we hold one persistent socket per device and
serialise every call through it.

The station also **closes an idle socket**: owners who scripted it report that without regular
heartbeats "the Ostation will kill the socket connection". `heartbeat()` is the keep-alive; the
caller decides the cadence (the coordinator uses Home Assistant's own timer, so nothing lingers
when the entry unloads).

tinytuya is synchronous; the coordinator runs these methods in an executor thread.
"""

from __future__ import annotations

import logging
import threading

import tinytuya

_LOGGER = logging.getLogger(__name__)

PROTOCOL_VERSION = 3.5
_CONNECT_TIMEOUT = 5
# Below the ~10 s at which Tuya firmware tends to give up on a quiet socket.
HEARTBEAT_INTERVAL = 8.0


class OstationError(Exception):
    """Raised when the station can't be reached or refuses a command."""


class OstationClient:
    """One persistent, serialised LAN connection to a single station."""

    def __init__(self, device_id: str, host: str, local_key: str) -> None:
        self._device_id = device_id
        self._host = host
        self._local_key = local_key
        self._lock = threading.Lock()
        self._device: tinytuya.Device | None = None

    def _connect(self) -> tinytuya.Device:
        device = tinytuya.Device(self._device_id, self._host, self._local_key)
        device.set_version(PROTOCOL_VERSION)
        # Persistent socket + heartbeats: reconnecting per poll costs a full 3.5 handshake and
        # makes the station drop the app's connection every few seconds.
        device.set_socketPersistent(True)
        device.set_socketTimeout(_CONNECT_TIMEOUT)
        device.set_socketRetryLimit(1)
        return device

    def _reset(self) -> None:
        if self._device is not None:
            try:
                self._device.close()
            except Exception:  # noqa: BLE001 - closing a dead socket must never mask the real error
                pass
        self._device = None

    def _dps(self, result) -> dict:
        """tinytuya reports transport problems as a payload rather than an exception."""
        if not isinstance(result, dict):
            raise OstationError(f"unexpected reply: {result!r}")
        if "Error" in result:
            raise OstationError(str(result.get("Error")))
        dps = result.get("dps")
        if not isinstance(dps, dict):
            raise OstationError(f"reply carried no datapoints: {result!r}")
        return dps

    def status(self) -> dict:
        """Read every datapoint. Retries once on a stale socket."""
        with self._lock:
            for attempt in (1, 2):
                if self._device is None:
                    self._device = self._connect()
                try:
                    return self._dps(self._device.status())
                except OstationError:
                    self._reset()
                    if attempt == 2:
                        raise
                except Exception as err:  # noqa: BLE001
                    self._reset()
                    if attempt == 2:
                        raise OstationError(str(err)) from err
            raise OstationError("unreachable")  # pragma: no cover - loop always returns or raises

    def set_dp(self, dp: int, value) -> dict:
        """Write one datapoint and return the station's reply."""
        with self._lock:
            if self._device is None:
                self._device = self._connect()
            try:
                return self._dps(self._device.set_value(dp, value, nowait=False))
            except OstationError:
                self._reset()
                raise
            except Exception as err:  # noqa: BLE001
                self._reset()
                raise OstationError(str(err)) from err

    def heartbeat(self) -> bool:
        """Keep the persistent socket alive. Returns whether one was sent.

        Does nothing when not connected: the next real call opens the socket, and a heartbeat
        should never be the thing that establishes a connection. On failure the socket is dropped
        so the next poll starts clean instead of spending its single retry on a dead one.
        """
        with self._lock:
            if self._device is None:
                return False
            try:
                # Wait for the ack rather than fire-and-forget: an unread ack left in the socket
                # buffer would be the first thing the next status() call reads.
                self._device.heartbeat(nowait=False)
                return True
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("heartbeat failed, dropping the socket: %s", err)
                self._reset()
                return False

    def close(self) -> None:
        with self._lock:
            self._reset()
