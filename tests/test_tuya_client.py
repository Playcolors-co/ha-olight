"""Client tests against a fake tinytuya device — no network, no station."""

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "olight"))


class FakeDevice:
    """Stands in for tinytuya.Device; scripted replies, records every call."""

    instances: list = []

    def __init__(self, dev_id, host, key):
        self.args = (dev_id, host, key)
        self.replies: list = []
        self.calls: list = []
        self.closed = False
        FakeDevice.instances.append(self)

    def set_version(self, v): self.calls.append(("version", v))
    def set_socketPersistent(self, v): self.calls.append(("persistent", v))
    def set_socketTimeout(self, v): self.calls.append(("timeout", v))
    def set_socketRetryLimit(self, v): self.calls.append(("retry", v))
    def close(self): self.closed = True
    def heartbeat(self, nowait=False): self.calls.append(("heartbeat",))

    def _next(self):
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def status(self):
        self.calls.append(("status",))
        return self._next()

    def set_value(self, dp, value, nowait=False):
        self.calls.append(("set", dp, value))
        return self._next()


@pytest.fixture
def client(monkeypatch):
    FakeDevice.instances.clear()
    monkeypatch.setitem(sys.modules, "tinytuya", types.SimpleNamespace(Device=FakeDevice))
    sys.modules.pop("tuya_client", None)
    import tuya_client
    return tuya_client


def script(*replies):
    """Queue replies for the next device the client creates."""
    FakeDevice.pending = list(replies)


def new_device_with(*replies):
    original_init = FakeDevice.__init__

    def init(self, *a, **k):
        original_init(self, *a, **k)
        self.replies = list(replies)
    return init


def test_connect_uses_protocol_35_and_a_persistent_socket(client, monkeypatch):
    monkeypatch.setattr(FakeDevice, "__init__", new_device_with({"dps": {"101": True}}))
    c = client.OstationClient("d" * 22, "10.0.0.2", "k" * 16)
    assert c.status() == {"101": True}
    dev = FakeDevice.instances[0]
    assert dev.args == ("d" * 22, "10.0.0.2", "k" * 16)
    assert ("version", 3.5) in dev.calls
    assert ("persistent", True) in dev.calls


def test_socket_is_reused_between_polls(client, monkeypatch):
    monkeypatch.setattr(FakeDevice, "__init__",
                        new_device_with({"dps": {"101": True}}, {"dps": {"101": False}}))
    c = client.OstationClient("d" * 22, "h", "k" * 16)
    c.status(); c.status()
    # One connection for two polls: reconnecting per poll would evict the app every 15 s.
    assert len(FakeDevice.instances) == 1


def test_error_payload_triggers_one_reconnect_then_succeeds(client, monkeypatch):
    replies = iter([
        [{"Error": "Network Error: Unable to Connect", "Err": "901"}],  # first device
        [{"dps": {"101": True}}],                                        # second device
    ])
    original_init = FakeDevice.__init__

    def init(self, *a, **k):
        original_init(self, *a, **k)
        self.replies = next(replies)
    monkeypatch.setattr(FakeDevice, "__init__", init)

    c = client.OstationClient("d" * 22, "h", "k" * 16)
    assert c.status() == {"101": True}
    assert len(FakeDevice.instances) == 2
    assert FakeDevice.instances[0].closed is True


def test_persistent_failure_raises_after_retry(client, monkeypatch):
    monkeypatch.setattr(FakeDevice, "__init__", new_device_with({"Error": "boom"}))
    c = client.OstationClient("d" * 22, "h", "k" * 16)
    with pytest.raises(client.OstationError):
        c.status()
    assert len(FakeDevice.instances) == 2  # exactly one retry, not an infinite loop


def test_reply_without_dps_is_an_error(client, monkeypatch):
    monkeypatch.setattr(FakeDevice, "__init__", new_device_with({"foo": 1}, {"foo": 1}))
    c = client.OstationClient("d" * 22, "h", "k" * 16)
    with pytest.raises(client.OstationError):
        c.status()


def test_set_dp_writes_and_returns_dps(client, monkeypatch):
    monkeypatch.setattr(FakeDevice, "__init__", new_device_with({"dps": {"101": False}}))
    c = client.OstationClient("d" * 22, "h", "k" * 16)
    assert c.set_dp(101, False) == {"101": False}
    assert ("set", 101, False) in FakeDevice.instances[0].calls


def test_set_dp_failure_resets_the_socket(client, monkeypatch):
    monkeypatch.setattr(FakeDevice, "__init__", new_device_with(OSError("reset by peer")))
    c = client.OstationClient("d" * 22, "h", "k" * 16)
    with pytest.raises(client.OstationError):
        c.set_dp(101, True)
    assert FakeDevice.instances[0].closed is True


def test_close_is_safe_when_never_connected(client):
    client.OstationClient("d" * 22, "h", "k" * 16).close()


def test_heartbeat_is_sent_only_when_connected(client, monkeypatch):
    monkeypatch.setattr(FakeDevice, "__init__", new_device_with({"dps": {"101": True}}))
    c = client.OstationClient("d" * 22, "h", "k" * 16)
    assert c.heartbeat() is False          # nothing to keep alive yet, and no socket opened for it
    assert FakeDevice.instances == []
    c.status()
    assert c.heartbeat() is True
    assert ("heartbeat",) in FakeDevice.instances[0].calls


def test_failed_heartbeat_drops_the_socket_so_the_next_poll_starts_clean(client, monkeypatch):
    monkeypatch.setattr(FakeDevice, "__init__",
                        new_device_with({"dps": {"101": True}}, {"dps": {"101": True}}))
    c = client.OstationClient("d" * 22, "h", "k" * 16)
    c.status()

    def boom(self, nowait=False): raise OSError("reset by peer")
    monkeypatch.setattr(FakeDevice, "heartbeat", boom)
    assert c.heartbeat() is False
    assert FakeDevice.instances[0].closed is True
    monkeypatch.setattr(FakeDevice, "heartbeat", lambda self, nowait=False: None)
    assert c.status() == {"101": True}     # reconnects without needing its retry
    assert len(FakeDevice.instances) == 2
