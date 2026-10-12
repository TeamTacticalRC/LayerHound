# Recent problems: recording, repeats, saving, scrubbing for sharing, who can see it, crashes.
import json
from fastapi.testclient import TestClient
import main, problems
from conftest import ADMIN, HEADERS, new_client


def test_repeats_count_up_and_survive_a_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(problems, "_items", [])
    problems.configure(tmp_path)
    problems.record("printer", "P1S: The printer didn't answer in time.", "TimeoutError")
    problems.record("printer", "P1S: The printer didn't answer in time.", "TimeoutError")
    problems.record("update", "Updating to v9.9.9 failed: no space")
    assert [(p["message"], p["count"]) for p in problems._items] == [("P1S: The printer didn't answer in time.", 2), ("Updating to v9.9.9 failed: no space", 1)]
    problems._items.clear(); problems.configure(tmp_path)          # LayerHound restarts
    assert len(problems._items) == 2 and json.loads((tmp_path / "problems.json").read_text())[0]["count"] == 2
    for i in range(problems.MAX + 20): problems.record("system", f"problem {i}")
    assert len(problems._items) == problems.MAX                       # only the most recent are kept


def test_scrub_for_sharing(monkeypatch):
    monkeypatch.setattr(problems, "_names", lambda: [("U1 Left", "Klipper"), ("U1", "Klipper"), ("Kyle's P1S", "Bambu")])
    text = problems.scrub("U1 Left at http://192.168.1.55:7125 and Kyle's P1S (01P00A123456789) at 10.0.0.9, "
                          "owner kyle@example.com, layerhound.local, layerhound.taila76720.ts.net, key lhk_abcDEF123, mac aa:bb:cc:dd:ee:ff, fe80::1274:c5ff:febf:9373")
    for secret in ("U1 Left", "192.168.1.55", "Kyle", "01P00A123456789", "10.0.0.9", "kyle@example.com", "layerhound.local", "taila76720", "lhk_abc", "aa:bb", "fe80::"):
        assert secret not in text, secret
    assert "Klipper printer 1" in text and "Bambu printer" in text and "<ip>" in text and "<serial>" in text


def test_who_can_see_and_report(client):
    client.delete("/api/problems")
    client.post("/api/auth/users", json={"username": "probviewer", "password": "prob viewer 12", "role": "viewer"})
    v = new_client(); v.post("/api/auth/login", json={"username": "probviewer", "password": "prob viewer 12"})
    # Anyone signed in can report a crash in their page; only admins can read or clear the list
    assert v.post("/api/problems/report", json={"message": "TypeError: x is undefined", "detail": "at Card (main.jsx:10)", "page": "Print Farm"}).json()["status"] == "recorded"
    assert v.get("/api/problems").status_code == 403 and v.delete("/api/problems").status_code == 403
    assert new_client().post("/api/problems/report", json={"message": "x"}).status_code == 401     # signed out
    r = client.get("/api/problems?shareable_text=true").json()
    assert r["problems"][0]["source_label"] == "Dashboard page" and "Print Farm" in r["problems"][0]["message"]
    assert "TypeError" in r["shareable"]
    for _ in range(15): v.post("/api/problems/report", json={"message": f"flood"})
    assert sum(p["count"] for p in client.get("/api/problems").json()["problems"] if "flood" in p["message"]) <= 10   # a few a minute at most
    assert client.delete("/api/problems").status_code == 200 and client.get("/api/problems").json()["problems"] == []


def test_crashes_are_caught_and_listed(client):
    def boom(): raise RuntimeError("kaboom")
    main.app.add_api_route("/api/test-crash", boom)
    main.app.router.routes.insert(0, main.app.router.routes.pop())   # ahead of the dashboard's catch-all
    c = TestClient(main.app, headers=HEADERS, raise_server_exceptions=False)
    c.post("/api/auth/login", json=ADMIN)
    r = c.get("/api/test-crash")
    assert r.status_code == 500 and "Recent problems" in r.json()["detail"]
    p = client.get("/api/problems").json()["problems"][0]
    assert p["source"] == "crash" and "GET /api/test-crash" in p["message"] and "kaboom" in p["detail"]


def test_an_offline_printer_is_listed(client):
    client.delete("/api/problems")
    row = {"id": 777001, "name": "Bench Klipper", "printer_type": "moonraker", "base_url": "http://127.0.0.1:9", "serial": None,
           "api_key": None, "enabled": 1, "camera_url": None}
    main.snapshot(row, grace=False)
    msgs = [p["message"] for p in client.get("/api/problems").json()["problems"]]
    assert any(m.startswith("Bench Klipper: ") for m in msgs)
