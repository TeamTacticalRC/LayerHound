# Printer suggestions: what the scan and Bambu announcements find, and adding them.
import io, json, urllib.error
import pytest
import discovery, settings


@pytest.fixture(autouse=True)
def printers_offline(monkeypatch):
    # Stand in for real printers: every check answers "offline" at once, so adding stays quick
    import main
    def offline(*a, **k): raise ConnectionError("Printer is offline")
    for name in ("moonraker", "bambu", "octoprint"):
        monkeypatch.setattr(main, name, offline)
    monkeypatch.setattr(main.media, "moonraker_webcams", lambda base: [])   # no camera lookups either


def found(ip, kind="moonraker", port=7125, serial=None, hostname=None):
    return {"ip": ip, "hostname": hostname, "printer": {"type": kind, "host": ip, "port": port, "serial": serial}}


def keys(client):
    return {s["key"]: s for s in client.get("/api/discovery").json()["suggestions"]}


def test_scan_results_become_suggestions(client):
    discovery.record_scan([found("127.0.0.11", hostname="voron"), {"ip": "127.0.0.12", "printer": None}])
    s = keys(client)
    k = "moonraker:127.0.0.11:7125"
    assert k in s and s[k]["suggested_name"] == "voron" and s[k]["label"] == "Klipper"
    assert not any("127.0.0.12" in x for x in s)   # not a printer


def test_printers_already_on_the_dashboard_are_not_suggested(client):
    r = client.post("/api/printers", json={"name": "Existing", "printer_type": "moonraker", "base_url": "http://127.0.0.13:7125"})
    discovery.record_scan([found("127.0.0.13")])
    assert "moonraker:127.0.0.13:7125" not in keys(client)
    client.delete(f"/api/printers/{r.json()['id']}")


def test_add_a_klipper_printer_in_one_click(client):
    discovery.record_scan([found("127.0.0.14")])
    r = client.post("/api/discovery/moonraker:127.0.0.14:7125/add", json={"name": "Bench Voron"})
    assert r.status_code == 200
    p = r.json()["printer"]
    assert p["name"] == "Bench Voron" and p["base_url"] == "http://127.0.0.14:7125"
    assert "moonraker:127.0.0.14:7125" not in keys(client)
    client.delete(f"/api/printers/{p['id']}")


def test_dismissed_printers_stay_dismissed(client):
    discovery.record_scan([found("127.0.0.15")])
    assert client.post("/api/discovery/moonraker:127.0.0.15:7125/dismiss").status_code == 200
    discovery.record_scan([found("127.0.0.15")])   # seen again by a later scan
    assert "moonraker:127.0.0.15:7125" not in keys(client)


def test_bambu_needs_its_access_code(client):
    discovery.record_scan([found("127.0.0.16", "bambu", 8883, "01P00A123456789")])
    k = "bambu:01P00A123456789"
    assert k in keys(client)
    assert client.post(f"/api/discovery/{k}/add", json={}).status_code == 400
    assert client.post(f"/api/discovery/{k}/add", json={"access_code": "short"}).status_code == 400
    r = client.post(f"/api/discovery/{k}/add", json={"access_code": "12345678", "name": "P1S"})
    assert r.status_code == 200 and r.json()["printer"]["serial"] == "01P00A123456789"
    assert k not in keys(client)
    client.delete(f"/api/printers/{r.json()['printer']['id']}")


ANNOUNCE = (b"NOTIFY * HTTP/1.1\r\nHOST: 239.255.255.250:1990\r\nServer: UPnP/1.0\r\nLocation: 127.0.0.17\r\n"
            b"NT: urn:bambulab-com:device:3dprinter:1\r\nUSN: 01S00C987654321\r\nCache-Control: max-age=1800\r\n"
            b"DevModel.bambu.com: C12\r\nDevName.bambu.com: Garage P1S\r\nDevConnect.bambu.com: lan\r\n\r\n")


def test_bambu_announcements():
    a = discovery.parse_announcement(ANNOUNCE)
    assert a == {"host": "127.0.0.17", "serial": "01S00C987654321", "name": "Garage P1S", "model": "P1S"}
    assert discovery.parse_announcement(b"NOTIFY * HTTP/1.1\r\nNT: upnp:rootdevice\r\nLocation: 1.2.3.4\r\n") is None


def test_same_bambu_seen_by_scan_and_announcement_is_listed_once(client):
    discovery.record_scan([found("127.0.0.17", "bambu", 8883, None)])          # scan: no serial yet
    a = discovery.parse_announcement(ANNOUNCE)
    discovery.remember("bambu", a["host"], 8883, a["serial"], a["name"], a["model"])
    s = [x for x in keys(client).values() if x["host"] == "127.0.0.17"]
    assert len(s) == 1 and s[0]["suggested_name"] == "Garage P1S" and s[0]["model"] == "P1S"


def test_auto_add_klipper_setting(client, monkeypatch):
    real = settings.get
    monkeypatch.setattr(settings, "get", lambda k: True if k == "auto_add_klipper" else real(k))
    discovery.record_scan([found("127.0.0.18", hostname="auto-voron")])
    printers = client.get("/api/printers").json()
    printers = printers if isinstance(printers, list) else printers["printers"]
    added = [p for p in printers if "127.0.0.18" in p["base_url"]]
    assert len(added) == 1
    client.delete(f"/api/printers/{added[0]['id']}")


class FakeResponse(io.BytesIO):
    def __init__(self, status=200, body=b"", headers=None):
        super().__init__(body); self.status = status; self.headers = headers or {}
    def __enter__(self): return self
    def __exit__(self, *a): pass


def test_octoprint_allow_flow(client, monkeypatch):
    discovery.record_scan([found("127.0.0.19", "octoprint", 5000)])
    k = "octoprint:127.0.0.19:5000"
    replies = [FakeResponse(201, headers={"Location": "/plugin/appkeys/request/abc"}),   # request made
               FakeResponse(202),                                                     # waiting for Allow
               FakeResponse(200, json.dumps({"api_key": "octo-key-123"}).encode())]   # approved
    seen = []
    def fake_urlopen(req, timeout=10):
        seen.append(req.full_url if hasattr(req, "full_url") else req); return replies.pop(0)
    monkeypatch.setattr(discovery.urllib.request, "urlopen", fake_urlopen)
    assert client.post(f"/api/discovery/{k}/add", json={}).status_code == 400   # needs the Allow flow
    assert client.post(f"/api/discovery/{k}/octoprint", json={"name": "Ender"}).json()["status"] == "waiting"
    assert keys(client)[k]["awaiting_approval"] is True
    assert client.post(f"/api/discovery/{k}/octoprint/check").json()["status"] == "waiting"
    r = client.post(f"/api/discovery/{k}/octoprint/check").json()
    assert r["status"] == "added" and r["printer"]["name"] == "Ender"
    assert seen[0] == "http://127.0.0.19:5000/plugin/appkeys/request" and seen[1] == "http://127.0.0.19:5000/plugin/appkeys/request/abc"
    client.delete(f"/api/printers/{r['printer']['id']}")


def test_octoprint_denied(client, monkeypatch):
    discovery.record_scan([found("127.0.0.20", "octoprint", 80)])
    k = "octoprint:127.0.0.20:80"
    replies = [FakeResponse(201, headers={"Location": "http://127.0.0.20:80/plugin/appkeys/request/x"})]
    def fake_urlopen(req, timeout=10):
        if replies: return replies.pop(0)
        raise urllib.error.HTTPError("x", 404, "Not found", {}, None)
    monkeypatch.setattr(discovery.urllib.request, "urlopen", fake_urlopen)
    client.post(f"/api/discovery/{k}/octoprint", json={})
    assert client.post(f"/api/discovery/{k}/octoprint/check").json()["status"] == "denied"


def test_viewers_cannot_add_or_dismiss(client):
    from conftest import new_client
    client.post("/api/auth/users", json={"username": "lookonly", "password": "lookonly-pass", "role": "viewer"})
    v = new_client()
    v.post("/api/auth/login", json={"username": "lookonly", "password": "lookonly-pass"})
    assert v.get("/api/discovery").status_code == 200
    assert v.post("/api/discovery/scan").status_code == 403
    assert v.post("/api/discovery/moonraker:1.2.3.4:7125/add", json={}).status_code == 403
    assert v.post("/api/discovery/moonraker:1.2.3.4:7125/octoprint/check").status_code == 403
