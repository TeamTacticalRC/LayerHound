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
    monkeypatch.setattr(main, "CONFIRM_WAITS", {})
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


# ---- Phase 2: printer files, sending a file and starting it --------------------------------
@pytest.fixture
def starting(client, farm, monkeypatch):
    ids, states, sent = farm
    client.put("/api/settings", json={"printer_start": True})
    for pid in ids.values():
        if isinstance(pid, int): states[pid] = "idle"
    monkeypatch.setattr(main, "START_WAIT", 0); monkeypatch.setattr(main, "START_POLL", 0)
    uploads = []
    def send_file(url, fields, name, path, headers=None):
        uploads.append((url, fields, name, path.read_bytes(), headers))
        if fields.get("print") == "true":   # the printer starts it
            states[ids["moonraker" if "/server/files" in url else "octoprint"]] = "printing"
        return 201
    monkeypatch.setattr(main, "send_file", send_file)
    yield ids, states, sent, uploads
    client.put("/api/settings", json={"printer_start": False})


def upload(c, pid, data=b"G28\nG1 X10\n", name="cube.gcode", **q):
    qs = "&".join(f"{k}={str(v).lower()}" for k, v in q.items())
    return c.put(f"/api/printers/{pid}/print?name={name}&{qs}", content=data)


def test_multipart_body(tmp_path):
    from email.parser import BytesParser
    from email.policy import default
    f = tmp_path / "x.gcode"; f.write_bytes(b"G28\n" * 1000)
    chunks, ctype, size = main.multipart({"root": "gcodes", "print": "true"}, "x.gcode", f)
    body = b"".join(chunks)
    assert len(body) == size
    msg = BytesParser(policy=default).parsebytes(b"Content-Type: " + ctype.encode() + b"\r\n\r\n" + body)
    parts = {p.get_param("name", header="content-disposition"): p for p in msg.iter_parts()}
    assert parts["root"].get_content().strip() == "gcodes" and parts["print"].get_content().strip() == "true"
    assert parts["file"].get_filename() == "x.gcode" and parts["file"].get_payload(decode=True) == b"G28\n" * 1000


def test_send_needs_its_own_switch(client, farm):
    ids, states, sent = farm
    states[ids["moonraker"]] = "idle"
    assert upload(client, ids["moonraker"], start=True, bed_clear=True).status_code == 403   # printer_start is off
    assert client.get(f"/api/printers/{ids['moonraker']}/files").status_code == 403


def test_upload_and_start_klipper(client, starting):
    ids, states, sent, uploads = starting
    r = upload(client, ids["moonraker"], start=True, bed_clear=True).json()
    assert r["status"] == "done"
    url, fields, name, data, _ = uploads[-1]
    assert url == "http://127.0.0.1:9/server/files/upload" and fields == {"root": "gcodes", "print": "true"} and name == "cube.gcode" and data == b"G28\nG1 X10\n"
    # Upload only
    states[ids["moonraker"]] = "idle"
    assert upload(client, ids["moonraker"]).json()["status"] == "uploaded" and uploads[-1][1]["print"] == "false"


def test_upload_and_start_octoprint(client, starting):
    ids, states, sent, uploads = starting
    assert upload(client, ids["octoprint"], start=True, bed_clear=True).json()["status"] == "done"
    url, fields, _, _, headers = uploads[-1]
    assert url.endswith("/api/files/local") and fields == {"select": "true", "print": "true"} and headers == {"X-Api-Key": "OCTOKEY"}


def test_start_safety_checks(client, starting):
    ids, states, sent, uploads = starting
    assert upload(client, ids["moonraker"], start=True).status_code == 400                        # bed not confirmed clear
    assert upload(client, ids["moonraker"], name="evil.sh", start=True, bed_clear=True).status_code == 400
    assert upload(client, ids["moonraker"], data=b"", start=True, bed_clear=True).status_code == 400
    states[ids["moonraker"]] = "printing"
    r = upload(client, ids["moonraker"], start=True, bed_clear=True)
    assert r.status_code == 409 and "printing" in r.json()["detail"]                                # never on top of a print
    assert upload(client, ids["bambu"], start=True, bed_clear=True).status_code == 409                # Bambu: not yet
    assert uploads == []
    # A name with folders or odd characters becomes a plain file name
    states[ids["moonraker"]] = "idle"
    upload(client, ids["moonraker"], name="..%2F..%2Fetc%2Fcube%3B.gcode")
    assert uploads[-1][2] == "cube_.gcode"


def test_start_not_confirmed(client, starting, monkeypatch):
    ids, states, sent, uploads = starting
    monkeypatch.setattr(main, "send_file", lambda *a, **k: 201)   # took the file, but doesn't start
    r = upload(client, ids["moonraker"], start=True, bed_clear=True).json()
    assert r["status"] == "unconfirmed" and "still says it's idle" in r["message"]


def test_printer_files_and_start_one(client, starting, monkeypatch):
    ids, states, sent, uploads = starting
    def get_json(u, headers=None, timeout=None):
        if "/server/files/list" in u:
            return {"result": [{"path": "old.gcode", "modified": 100, "size": 5}, {"path": "shelf/new.gcode", "modified": 200, "size": 9},
                               {"path": "notes.txt", "modified": 300, "size": 1}]}
        return {"files": [{"type": "folder", "children": [{"type": "machinecode", "name": "a.gcode", "path": "parts/a.gcode", "date": 5, "size": 1}]},
                          {"type": "model", "name": "b.stl", "path": "b.stl", "date": 9}]}
    monkeypatch.setattr(main, "get_json", get_json)
    files = client.get(f"/api/printers/{ids['moonraker']}/files").json()["files"]
    assert [f["path"] for f in files] == ["shelf/new.gcode", "old.gcode"] and files[0]["name"] == "new.gcode"   # newest first, G-code only
    assert [f["path"] for f in client.get(f"/api/printers/{ids['octoprint']}/files").json()["files"]] == ["parts/a.gcode"]
    # Start one: Klipper by file name; OctoPrint select-and-print
    sent.clear()
    import main as m
    def post(u, body=None, headers=None):
        sent.append((u, body, headers)); states[ids["moonraker" if "/printer/print/start" in u else "octoprint"]] = "printing"; return 204
    monkeypatch.setattr(m, "post_json", post)
    assert client.post(f"/api/printers/{ids['moonraker']}/print", json={"path": "shelf/new.gcode"}).status_code == 400   # bed not confirmed
    r = client.post(f"/api/printers/{ids['moonraker']}/print", json={"path": "shelf/new.gcode", "bed_clear": True}).json()
    assert r["status"] == "done" and sent[-1][0] == "http://127.0.0.1:9/printer/print/start?filename=shelf/new.gcode"
    client.post(f"/api/printers/{ids['octoprint']}/print", json={"path": "parts/a.gcode", "bed_clear": True})
    assert sent[-1][0].endswith("/api/files/local/parts/a.gcode") and sent[-1][1] == {"command": "select", "print": True}
    assert client.post(f"/api/printers/{ids['moonraker']}/print", json={"path": "../secret.gcode", "bed_clear": True}).status_code in (400, 409)


def test_viewers_cannot_send_or_list(client, starting):
    ids, states, sent, uploads = starting
    client.post("/api/auth/users", json={"username": "sendviewer", "password": "send viewer 12", "role": "viewer"})
    v = new_client(); v.post("/api/auth/login", json={"username": "sendviewer", "password": "send viewer 12"})
    assert upload(v, ids["moonraker"], start=True, bed_clear=True).status_code == 403
    assert v.get(f"/api/printers/{ids['moonraker']}/files").status_code == 403
    assert uploads == []


def test_slow_printer_still_confirms(client, starting, monkeypatch):
    # What the Elegoo did: it started, but its first readings timed out. The check must keep asking
    # (not fall back to the remembered "idle") and report it once the printer answers.
    ids, states, sent, uploads = starting
    pid = ids["moonraker"]
    monkeypatch.setattr(main, "START_WAIT", 5)
    answers = iter([{"state": "idle"}, {"state": "offline", "connected": False}, {"state": "offline", "connected": False}])
    def snapshot(r, grace=True):
        if r["id"] != pid: return {"id": r["id"], "name": r["name"], "state": states[r["id"]]}
        if grace: return {"id": pid, "name": r["name"], "state": "idle"}           # the remembered reading
        return {"id": pid, "name": r["name"], **next(answers, {"state": states[pid]})}
    monkeypatch.setattr(main, "snapshot", snapshot)
    r = upload(client, pid, start=True, bed_clear=True).json()
    assert r["status"] == "done" and r["printer"]["state"] == "printing"


def test_timeouts_are_not_a_cancel(client, farm, monkeypatch):
    ids, states, sent = farm
    pid = ids["moonraker"]
    ids["_obey"]["on"] = False
    first = {"done": False}
    def snapshot(r, grace=True):
        if not first["done"]: first["done"] = True; return {"id": pid, "name": r["name"], "state": "printing"}
        return {"id": pid, "name": r["name"], "state": "offline", "connected": False}   # every later reading times out
    monkeypatch.setattr(main, "snapshot", snapshot)
    r = act(client, pid, "cancel").json()
    assert r["status"] == "unconfirmed" and "didn't answer in time" in r["message"]


def test_slow_reply_is_not_a_failure(client, starting, monkeypatch):
    # What the Elegoo did on the second test: it started (and later cancelled) the print, but only
    # answered after LayerHound stopped waiting. A slow answer means "check the printer", not "failed".
    import urllib.error
    ids, states, sent, uploads = starting
    pid = ids["moonraker"]
    def slow(u, body=None, headers=None):
        states[pid] = "printing" if "/print/start" in u else "idle"
        raise TimeoutError("timed out")
    monkeypatch.setattr(main, "post_json", slow)
    r = client.post(f"/api/printers/{pid}/print", json={"path": "shelf/new.gcode", "bed_clear": True}).json()
    assert r["status"] == "done"
    assert act(client, pid, "cancel").json()["status"] == "done"
    # Not reaching the printer at all is still an error
    def unreachable(u, body=None, headers=None): raise urllib.error.URLError(TimeoutError("timed out"))
    monkeypatch.setattr(main, "post_json", unreachable)
    states[pid] = "printing"
    assert act(client, pid, "pause").status_code == 502


def test_printer_complains_but_does_it(client, farm, monkeypatch):
    # The Elegoo cancelled while still heating: it answered "400 Bad Request" (its cancel routine
    # tried to move before homing) but the print was cancelled. Check the state, pass on its words.
    import io, urllib.error
    ids, states, sent = farm
    pid = ids["moonraker"]
    def complain(u, body=None, headers=None, does_it=True):
        if does_it: states[pid] = "idle"
        raise urllib.error.HTTPError(u, 400, "Bad Request", {}, io.BytesIO(b'{"error": {"code": 400, "message": "Must home axis first: 0.000 0.000 10.000 [0.000]"}}'))
    monkeypatch.setattr(main, "post_json", complain)
    r = act(client, pid, "cancel").json()
    assert r["status"] == "done" and r["note"].startswith("Must home axis first")
    # Didn't do it: the printer's own words, not "Bad Request"
    states[pid] = "printing"
    monkeypatch.setattr(main, "post_json", lambda u, body=None, headers=None: complain(u, does_it=False))
    r = act(client, pid, "cancel")
    assert r.status_code == 502 and "Must home axis first" in r.json()["detail"]


def test_file_list_gets_more_time(client, starting, monkeypatch):
    # Listing the Elegoo's files hit the usual 4 s limit while it was slow; listing gets 20 s
    ids, states, sent, uploads = starting
    seen = []
    monkeypatch.setattr(main, "get_json", lambda u, headers=None, timeout=main.TIMEOUT: seen.append(timeout) or {"result": []})
    assert client.get(f"/api/printers/{ids['moonraker']}/files").status_code == 200
    assert seen == [main.FILES_TIMEOUT] and main.FILES_TIMEOUT >= 15
