# Setup hotspot: when it turns on and off, the captive-portal redirect, and who may change Wi-Fi.
# NetworkManager is faked, so these tests never touch the real network.
import pytest
import hotspot, wifi
from conftest import new_client

ETH_DOWN = {"device": "end0", "type": "ethernet", "state": "unavailable", "connection": ""}
ETH_UP = {"device": "end0", "type": "ethernet", "state": "connected", "connection": "Wired"}


@pytest.fixture
def fake_nm(monkeypatch):
    calls = []
    net = {"devices": [ETH_DOWN, {"device": "wlan0", "type": "wifi", "state": "disconnected", "connection": ""}], "saved": {"Home"}, "clients": 0}
    monkeypatch.setattr(wifi, "nmcli", lambda *a, **k: (calls.append(a), (0, "", ""))[1])
    monkeypatch.setattr(wifi, "devices", lambda: net["devices"])
    monkeypatch.setattr(wifi, "wifi_device", lambda: "wlan0")
    monkeypatch.setattr(wifi, "saved_wifi", lambda: set(net["saved"]))
    monkeypatch.setattr(wifi, "scan", lambda rescan=False: [{"ssid": "Home", "signal": 80, "saved": True}])
    monkeypatch.setattr(hotspot, "clients", lambda: net["clients"])
    monkeypatch.setattr(hotspot, "REQUEST_FILE", hotspot.Path(__file__).with_name("no-such-request-file"))
    hotspot.state.update(active=False, reason=None, since=None, joining=None, last_error=None)
    yield calls, net
    hotspot.state.update(active=False, reason=None, since=None, joining=None, last_error=None)


def test_starts_after_being_offline(fake_nm):
    calls, net = fake_nm
    t = 1000.0
    since = hotspot.tick(t, None)
    assert since == t and not hotspot.state["active"]
    assert hotspot.tick(t + hotspot.OFFLINE_WAIT - 1, since) == since
    hotspot.tick(t + hotspot.OFFLINE_WAIT, since)
    assert hotspot.state["active"] and hotspot.state["reason"] == "offline"
    added = next(c for c in calls if c[:2] == ("connection", "add"))
    assert "ap" in added and "shared" in added and "LayerHound-Setup" in added
    # Open network: no Wi-Fi password settings
    assert not any("wifi-sec" in str(x) for x in added)


def test_stays_off_while_online(fake_nm):
    _, net = fake_nm
    net["devices"] = [ETH_UP]
    assert hotspot.tick(1000, None) is None and not hotspot.state["active"]


def test_stops_when_cable_plugged_in(fake_nm):
    _, net = fake_nm
    hotspot.state.update(active=True, reason="offline", since=1000)
    net["devices"] = [ETH_UP]
    hotspot.tick(1010, None)
    assert not hotspot.state["active"]


def test_retries_saved_wifi_only_when_no_phone_is_connected(fake_nm):
    _, net = fake_nm
    hotspot.state.update(active=True, reason="offline", since=1000)
    net["clients"] = 1
    hotspot.tick(1000 + hotspot.RETRY_EVERY + 1, None)
    assert hotspot.state["active"]
    net["clients"] = 0
    hotspot.tick(1000 + hotspot.RETRY_EVERY + 1, None)
    assert not hotspot.state["active"]


def test_manual_hotspot_turns_off_after_time_limit(fake_nm):
    hotspot.state.update(active=True, reason="manual", since=1000)
    hotspot.tick(1000 + hotspot.MANUAL_LIMIT - 1, None)
    assert hotspot.state["active"]
    hotspot.tick(1000 + hotspot.MANUAL_LIMIT + 1, None)
    assert not hotspot.state["active"]


def test_captive_portal_redirect(client, fake_nm, monkeypatch):
    hotspot.state.update(active=True, reason="manual", since=1000)
    c = new_client()
    # Someone on the home network (not the hotspot) isn't redirected
    r = c.get("/api/health", headers={"Host": "192.168.1.7"}, follow_redirects=False)
    assert r.status_code == 200
    monkeypatch.setattr(hotspot, "on_hotspot", lambda host: True)
    r = c.get("/hotspot-detect.html", headers={"Host": "captive.apple.com"}, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "http://10.42.0.1/"
    r = c.get("/api/health", headers={"Host": "10.42.0.1"}, follow_redirects=False)
    assert r.status_code == 200
    hotspot.state["active"] = False
    r = c.get("/api/health", headers={"Host": "captive.apple.com"}, follow_redirects=False)
    assert r.status_code == 200


def test_connect_needs_admin_once_accounts_exist(client, fake_nm, monkeypatch):
    monkeypatch.setattr(hotspot, "join", lambda ssid, pw: None)
    assert client.post("/api/hotspot/connect", json={"ssid": "Home"}).status_code == 409  # hotspot off
    hotspot.state.update(active=True, reason="manual", since=1000)
    assert new_client().post("/api/hotspot/connect", json={"ssid": "Home"}).status_code == 403
    r = client.post("/api/hotspot/connect", json={"ssid": "Home", "password": "home wifi pass"})
    assert r.status_code == 200 and r.json()["status"] == "joining"


def test_details_only_for_phones_on_the_hotspot(client):
    r = new_client().get("/api/hotspot").json()
    assert r["on_hotspot"] is False and "networks" not in r
    assert hotspot.on_hotspot("10.42.0.23") and not hotspot.on_hotspot("192.168.1.5")


def test_failed_join_brings_hotspot_back(fake_nm, monkeypatch):
    calls, _ = fake_nm
    monkeypatch.setattr(hotspot, "JOIN_DELAY", 0)
    monkeypatch.setattr(wifi, "nmcli", lambda *a, **k: (calls.append(a), (1, "", "Secrets were required, but not provided") if "connect" in a else (0, "", ""))[1])
    hotspot.state.update(active=True, reason="offline", since=1000, joining="Neighbor")
    hotspot.join("Neighbor", "wrong")
    assert hotspot.state["joining"] is None and "password was rejected" in hotspot.state["last_error"]
    assert calls[-1][-2:] == ("id", "LayerHound-Setup") and "up" in calls[-1]


def test_never_starts_when_network_status_is_unknown(fake_nm):
    _, net = fake_nm
    net["devices"] = []
    assert hotspot.tick(1000, 1000 - hotspot.OFFLINE_WAIT - 1) is None and not hotspot.state["active"]
