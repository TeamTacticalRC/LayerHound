# Pause / resume / cancel from the dashboard, with stand-ins for the printers (nothing real is contacted).
import json
import pytest
import main, settings, vault
from conftest import new_client

UNREACHABLE = "http://127.0.0.1:9"


@pytest.fixture
def farm(client, monkeypatch):
    """Three printers, one of each type; their state is whatever the test sets."""
    c = main.db(); ids = {}
    for name, t, url, key, serial in (("Klipper", "moonraker", UNREACHABLE, None, None),
                                      ("Octo", "octoprint", UNREACHABLE, "OCTOKEY", None),
                                      ("P1S", "bambu", "mqtts://127.0.0.1:8883", "12345678", "01P00A000000001")):
        ids[t] = c.execute("INSERT INTO printers(name,printer_type,base_url,api_key,serial,enabled,created_at,updated_at,sort_order) VALUES(?,?,?,?,?,1,?,?,99)",
                           (name, t, url, vault.encrypt(key) if key else None, serial, main.now(), main.now())).lastrowid
    c.commit(); c.close()
    states = {pid: "printing" for pid in ids.values()}
    monkeypatch.setattr(main, "snapshot", lambda r, grace=True: {"id": r["id"], "name": r["name"], "state": states[r["id"]]})
    monkeypatch.setattr(main, "check", lambda r: {"id": r["id"], "state": states[r["id"]]})
    monkeypatch.setattr(main.time, "sleep", lambda s: None)
    sent = []
    # A printer that does what it's told: its state changes (tests can turn this off)
    obey = {"on": True}
    NEW = {"pause": "paused", "resume": "printing", "cancel": "idle"}
    def post(u, body=None, headers=None):
        sent.append((u, body, headers))
        action = u.rsplit("/", 1)[1] if "/printer/print/" in u else ("cancel" if body["command"] == "cancel" else body["action"])
        pid = next(i for t, i in ids.items() if t == ("moonraker" if "/printer/print/" in u else "octoprint"))
        if obey["on"]: states[pid] = NEW[action]
        return 204
    monkeypatch.setattr(main, "post_json", post)
    monkeypatch.setattr(main, "CONFIRM_WAIT", 0)
    ids["_obey"] = obey
    client.put("/api/settings", json={"printer_controls": True})
    yield ids, states, sent
    client.put("/api/settings", json={"printer_controls": False})   # shared test client
    c = main.db(); c.executemany("DELETE FROM printers WHERE id=?", [(i,) for k, i in ids.items() if k != "_obey"]); c.commit(); c.close()


def act(c, pid, action):
    return c.post(f"/api/printers/{pid}/control", json={"action": action})


def test_off_by_default(client):
    assert settings.SCHEMA["printer_controls"][0] is False
    assert act(client, 1, "pause").status_code == 403


def test_klipper(client, farm):
    ids, states, sent = farm
    r = act(client, ids["moonraker"], "pause").json()
    assert r["status"] == "done" and r["printer"]["state"] == "paused"
    assert sent[-1][0] == UNREACHABLE + "/printer/print/pause"
    act(client, ids["moonraker"], "resume"); act(client, ids["moonraker"], "cancel")
    assert [u.rsplit("/", 1)[1] for u, _, _ in sent] == ["pause", "resume", "cancel"]


def test_not_confirmed_is_never_reported_as_done(client, farm):
    # The printer took the command but is still printing: say so, don't claim "Paused."
    ids, states, sent = farm
    ids["_obey"]["on"] = False
    r = act(client, ids["moonraker"], "pause").json()
    assert r["status"] == "unconfirmed" and "still says it's printing" in r["message"]


def test_octoprint(client, farm):
    ids, states, sent = farm
    act(client, ids["octoprint"], "pause")
    assert sent[-1] == (UNREACHABLE + "/api/job", {"command": "pause", "action": "pause"}, {"X-Api-Key": "OCTOKEY"})
    states[ids["octoprint"]] = "printing"
    act(client, ids["octoprint"], "cancel")
    assert sent[-1][1] == {"command": "cancel"}


def test_wrong_state_and_unknown_action(client, farm):
    ids, states, sent = farm
    states[ids["moonraker"]] = "idle"
    r = act(client, ids["moonraker"], "pause")
    assert r.status_code == 409 and "idle" in r.json()["detail"]
    states[ids["moonraker"]] = "printing"
    assert act(client, ids["moonraker"], "resume").status_code == 409     # only a paused print resumes
    assert act(client, ids["moonraker"], "explode").status_code == 400
    assert act(client, 99999, "pause").status_code == 404
    assert sent == []


class FakeBambu:
    def __init__(self, answer, on_send=None):
        self.answers, self.serial, self.answer, self.published, self.replies = {}, "01P00A000000001", answer, [], []
        outer = self
        class Client:
            def is_connected(self): return True
            def publish(self, topic, payload):
                outer.published.append((topic, json.loads(payload)))
                cmd = json.loads(payload)["print"]["command"]
                if outer.answer: outer.answers[cmd] = (outer.answer, "auth denied" if outer.answer == "fail" else "", main.time.time() + 1)
                if on_send: on_send(cmd)
        self.client = Client()


def test_bambu(client, farm, monkeypatch):
    ids, states, sent = farm
    pid = ids["bambu"]
    ok = FakeBambu("success", on_send=lambda cmd: states.__setitem__(pid, "idle"))
    monkeypatch.setitem(main.bambu_watchers, pid, ok)
    assert act(client, pid, "cancel").json()["status"] == "done"
    topic, msg = ok.published[-1]
    assert topic == "device/01P00A000000001/request" and msg["print"]["command"] == "stop"
    # Newer firmware refuses controls outside LAN Only / Developer mode: say so plainly
    refused = FakeBambu("fail"); monkeypatch.setitem(main.bambu_watchers, pid, refused)
    states[pid] = "printing"
    r = act(client, pid, "pause")
    assert r.status_code == 502 and "LAN Only" in r.json()["detail"]
    # Says nothing and keeps printing (what a P1S on firmware 01.10 did): explain, never "Paused."
    silent = FakeBambu(None); monkeypatch.setitem(main.bambu_watchers, pid, silent)
    monkeypatch.setattr(main, "BAMBU_WAIT", 0)
    r = act(client, pid, "pause").json()
    assert r["status"] == "unconfirmed" and "Developer Mode" in r["message"] and "still printing" in r["message"]


def test_only_admins(client, farm):
    ids, states, sent = farm
    client.post("/api/auth/users", json={"username": "ctlviewer", "password": "ctl viewer 12", "role": "viewer"})
    v = new_client(); v.post("/api/auth/login", json={"username": "ctlviewer", "password": "ctl viewer 12"})
    assert act(v, ids["moonraker"], "pause").status_code == 403
    key = client.post("/api/auth/keys", json={"name": "wall screen"}).json()["key"]
    k = new_client(); k.headers["Authorization"] = f"Bearer {key}"
    assert act(k, ids["moonraker"], "pause").status_code == 403
    assert sent == []
