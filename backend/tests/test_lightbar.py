# The LED status light endpoint: a ring (arc per printer) or a bar (LED per printer), in display
# order, read with an access key.
import lightbar
from conftest import new_client

FARM = [{"name": "P1S", "state": "printing", "connected": True, "progress": 42.4},
        {"name": "U1", "state": "paused", "connected": True, "progress": 80},
        {"name": "K1", "state": "error", "connected": True},
        {"name": "Neptune", "state": "offline", "connected": False},
        {"name": "Voron", "state": "complete", "connected": True},
        {"name": "Ender", "state": "idle", "connected": True},
        {"name": "Mystery", "state": "warming up", "connected": True}]
GREEN = lightbar.LOOK["printing"][0]


def farm(monkeypatch, printers):
    monkeypatch.setattr(lightbar, "_printers", lambda: {"printers": printers})


def test_bar_one_led_per_printer_in_order(client, monkeypatch):
    farm(monkeypatch, FARM)
    r = client.get("/api/lightbar?layout=bar").json()
    assert r["v"] == 1 and r["layout"] == "bar" and r["printers"] == 7 and len(r["leds"]) == 8 and 5 <= r["brightness"] <= 100
    assert [l["state"] for l in r["leds"]] == ["printing", "paused", "error", "offline", "complete", "idle", "idle", "none"]
    first = r["leds"][0]
    assert first["name"] == "P1S" and first["printer"] == 0 and first["effect"] == "solid" and first["progress"] == 42 and first["rgb"] == list(GREEN)
    assert r["leds"][1]["effect"] == "pulse" and r["leds"][2]["effect"] == "blink"
    assert r["leds"][7] == lightbar.OFF


def test_ring_is_the_default_with_an_arc_per_printer(client, monkeypatch):
    farm(monkeypatch, [{"name": "A", "state": "error", "connected": True}, {"name": "B", "state": "idle", "connected": True},
                       {"name": "C", "state": "complete", "connected": True}, {"name": "D", "state": "offline", "connected": False}])
    r = client.get("/api/lightbar").json()
    assert r["layout"] == "ring" and len(r["leds"]) == 12 and r["names"] == ["A", "B", "C", "D"]
    # 4 printers on 12 LEDs: 2 lit + 1 dark gap each
    assert [l["printer"] for l in r["leds"]] == [0, 0, None, 1, 1, None, 2, 2, None, 3, 3, None]
    assert [l["effect"] for l in r["leds"][:3]] == ["blink", "blink", "off"]


def test_ring_fills_with_print_progress(client, monkeypatch):
    farm(monkeypatch, [{"name": "P1S", "state": "printing", "connected": True, "progress": 50}])
    leds = client.get("/api/lightbar?layout=ring").json()["leds"]
    # One printer gets the whole ring less one gap: 11 LEDs, half of them bright
    assert sum(1 for l in leds if l["printer"] == 0) == 11
    bright = [l for l in leds if l["rgb"] == list(GREEN)]
    dim = [l for l in leds if l["printer"] == 0 and l["rgb"] != list(GREEN)]
    assert len(bright) == 6 and len(dim) == 5 and all(max(l["rgb"]) < 60 for l in dim)
    # Just started: still one bright LED, so the arc is never blank
    farm(monkeypatch, [{"name": "P1S", "state": "printing", "connected": True, "progress": 0}])
    assert sum(1 for l in client.get("/api/lightbar").json()["leds"] if l["rgb"] == list(GREEN)) == 1


def test_ring_with_many_printers_and_none(client, monkeypatch):
    farm(monkeypatch, [{"name": f"P{i}", "state": "idle", "connected": True} for i in range(5)])
    leds = client.get("/api/lightbar").json()["leds"]
    assert [l["printer"] for l in leds] == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, None, None]   # 2 each, no room for gaps
    farm(monkeypatch, [{"name": f"P{i}", "state": "idle", "connected": True} for i in range(15)])
    assert [l["printer"] for l in client.get("/api/lightbar").json()["leds"]] == list(range(12))
    farm(monkeypatch, [])
    assert all(l == lightbar.OFF for l in client.get("/api/lightbar").json()["leds"])


def test_led_count_and_reversed(client, monkeypatch):
    many = [{"name": f"P{i}", "state": "idle", "connected": True} for i in range(10)]
    farm(monkeypatch, many)
    assert len(client.get("/api/lightbar?layout=ring&leds=16").json()["leds"]) == 16
    assert client.get("/api/lightbar?leds=0").status_code == 400 and client.get("/api/lightbar?layout=star").status_code == 400
    assert client.put("/api/settings", json={"lightbar_reverse": True, "lightbar_brightness": 70}).status_code == 200
    r = client.get("/api/lightbar?layout=bar").json()
    assert [l["name"] for l in r["leds"]] == [f"P{i}" for i in range(7, -1, -1)] and r["brightness"] == 70
    assert client.put("/api/settings", json={"lightbar_brightness": 2}).status_code == 400
    assert client.put("/api/settings", json={"lightbar_layout": "bar"}).json()["lightbar_layout"] == "bar"
    assert client.get("/api/lightbar").json()["layout"] == "bar"
    client.put("/api/settings", json={"lightbar_reverse": False, "lightbar_brightness": 40, "lightbar_layout": "ring"})   # shared test client


def test_light_reads_with_an_access_key(client, monkeypatch):
    farm(monkeypatch, FARM)
    key = client.post("/api/auth/keys", json={"name": "LED ring"}).json()["key"]
    light = new_client()
    assert light.get("/api/lightbar").status_code == 401
    assert light.get("/api/lightbar", headers={"Authorization": "Bearer lhk_wrong"}).status_code == 401
    assert light.get("/api/lightbar", headers={"Authorization": f"Bearer {key}"}).status_code == 200
    # The key can only look
    assert light.put("/api/settings", json={"lightbar_brightness": 90}, headers={"Authorization": f"Bearer {key}"}).status_code == 403
