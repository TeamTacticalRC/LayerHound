# API tests. Printers point at 127.0.0.1:9 (nothing listens there), so no real printer is contacted.
import json
import os

UNREACHABLE = "http://127.0.0.1:9"


# ---- Basics -------------------------------------------------------------------------------
def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["service"] == "layerhound-api"
    # Open tabs compare this with their own build to offer a reload after an update
    assert {"version", "build"} <= r.json().keys()


def test_build_id(tmp_path, monkeypatch):
    import main
    monkeypatch.setattr(main, "DIST", tmp_path)
    monkeypatch.setattr(main, "_build", {"mtime": None, "id": None})
    assert main.build_id() is None
    (tmp_path / "index.html").write_text('<script type="module" crossorigin src="/assets/index-AbC_12-x.js"></script>')
    assert main.build_id() == "index-AbC_12-x.js"


def test_system_and_server(client):
    s = client.get("/api/system").json()
    assert {"cpu_percent", "memory_percent", "storage_percent", "network", "services"} <= s.keys()
    assert client.get("/api/server").status_code == 200


# ---- Printers -----------------------------------------------------------------------------
def test_printer_lifecycle(client):
    r = client.post("/api/printers", json={"name": "Test Klipper", "printer_type": "moonraker", "base_url": UNREACHABLE})
    assert r.status_code == 200
    p = r.json()
    assert p["state"] == "offline" and p["connected"] is False

    r = client.put(f"/api/printers/{p['id']}", json={"name": "Renamed"})
    assert r.json()["name"] == "Renamed"

    # Test connection reports the live result
    t = client.post(f"/api/printers/{p['id']}/test").json()
    assert t["ok"] is False

    assert client.delete(f"/api/printers/{p['id']}").status_code == 200
    assert client.get(f"/api/printers/{p['id']}").status_code == 404


def test_printer_validation(client):
    assert client.post("/api/printers", json={"name": "x", "printer_type": "nope", "base_url": UNREACHABLE}).status_code == 400
    # Bambu printers need a serial number and access code
    r = client.post("/api/printers", json={"name": "P1S", "printer_type": "bambu", "base_url": "mqtts://127.0.0.1:8883"})
    assert r.status_code == 400
    assert client.post("/api/printers", json={"name": "", "printer_type": "moonraker", "base_url": UNREACHABLE}).status_code == 422


def test_printer_secrets_never_returned(client):
    p = client.post("/api/printers", json={"name": "Octo", "printer_type": "octoprint", "base_url": UNREACHABLE, "api_key": "SECRET123"}).json()
    try:
        listing = client.get("/api/printers").text
        assert "SECRET123" not in listing and "api_key" not in listing
    finally:
        client.delete(f"/api/printers/{p['id']}")


def test_printer_reorder(client):
    a = client.post("/api/printers", json={"name": "A", "printer_type": "moonraker", "base_url": UNREACHABLE}).json()
    b = client.post("/api/printers", json={"name": "B", "printer_type": "moonraker", "base_url": UNREACHABLE}).json()
    try:
        client.put("/api/printers/order", json={"ids": [b["id"], a["id"]]})
        names = [p["name"] for p in client.get("/api/printers").json()["printers"]]
        assert names.index("B") < names.index("A")
    finally:
        client.delete(f"/api/printers/{a['id']}")
        client.delete(f"/api/printers/{b['id']}")


# ---- Shared files -------------------------------------------------------------------------
def test_files_round_trip(client):
    assert client.post("/api/files/folder", json={"path": "", "name": "Parts"}).status_code == 200
    r = client.put("/api/files/upload", params={"path": "Parts", "name": "bracket.gcode"}, content=b"G28\nG1 X10\n")
    assert r.status_code == 200
    # Same name again is kept, not overwritten
    r2 = client.put("/api/files/upload", params={"path": "Parts", "name": "bracket.gcode"}, content=b"G28\n")
    assert r2.json()["name"] == "bracket (2).gcode"

    assert client.get("/api/files/download", params={"path": "Parts/bracket.gcode"}).content == b"G28\nG1 X10\n"
    assert client.post("/api/files/rename", json={"path": "Parts/bracket (2).gcode", "name": "copy.gcode"}).status_code == 200
    # Renaming onto an existing name is refused
    assert client.post("/api/files/rename", json={"path": "Parts/copy.gcode", "name": "bracket.gcode"}).status_code == 409

    assert client.post("/api/files/delete", json={"path": "Parts"}).status_code == 200
    assert client.get("/api/storage").json()["files"]["trash_count"] >= 1
    assert client.post("/api/files/trash/empty").status_code == 200
    assert client.get("/api/storage").json()["files"]["trash_count"] == 0


def test_files_cannot_escape_folder(client, files_root):
    for path in ("..", "../..", ".trash", "a/../../etc"):
        assert client.get("/api/files", params={"path": path}).status_code == 400, path
    assert client.get("/api/files/download", params={"path": "../.ssh/id_rsa"}).status_code == 400
    for name in ("../evil.txt", ".hidden", "a/b"):
        r = client.put("/api/files/upload", params={"path": "", "name": name}, content=b"x")
        assert r.status_code == 400, name
    assert client.put("/api/files/upload", params={"path": "..", "name": "evil.txt"}, content=b"x").status_code == 400
    assert client.post("/api/files/rename", json={"path": "", "name": "x"}).status_code == 400
    assert client.post("/api/files/delete", json={"path": ""}).status_code == 400

    # A symlink pointing outside the folder can't be followed
    link = files_root / "sneaky"
    os.symlink("/etc", link)
    try:
        assert client.get("/api/files", params={"path": "sneaky"}).status_code == 400
        assert client.get("/api/files/download", params={"path": "sneaky/hosts"}).status_code == 400
    finally:
        link.unlink()


# ---- Settings, backups --------------------------------------------------------------------
def test_settings_validation(client):
    assert client.get("/api/settings").json()["farm_name"]
    r = client.put("/api/settings", json={"farm_name": "Test Farm", "temp_unit": "F"})
    assert r.status_code == 200 and r.json()["farm_name"] == "Test Farm"
    assert client.put("/api/settings", json={"farm_name": ""}).json()["detail"] == "Farm name is required"
    assert client.put("/api/settings", json={"accent": "red"}).status_code == 400
    assert client.put("/api/settings", json={"evil": 1}).status_code == 400
    # Thresholds must stay in order
    assert client.put("/api/settings", json={"temp_warn": 100, "temp_hot": 90}).status_code == 400
    client.put("/api/settings", json={"temp_unit": "C"})


def test_backup_and_restore(client):
    p = client.post("/api/printers", json={"name": "Backup Me", "printer_type": "octoprint", "base_url": UNREACHABLE, "api_key": "KEY1"}).json()
    try:
        full = json.loads(client.get("/api/settings/backup").text)
        assert full["app"] == "layerhound" and any(x["api_key"] == "KEY1" for x in full["printers"])
        bare = json.loads(client.get("/api/settings/backup", params={"secrets": "false"}).text)
        assert all(x["api_key"] is None for x in bare["printers"])

        assert client.post("/api/settings/restore", json={"hello": 1}).status_code == 400
        r = client.post("/api/settings/restore", json=full)
        assert r.status_code == 200 and r.json()["printers"] == len(full["printers"])
        assert any(x["name"] == "Backup Me" for x in client.get("/api/printers").json()["printers"])
    finally:
        client.delete(f"/api/printers/{p['id']}")


def test_old_backup_branding_is_migrated(client):
    old = {"app": "ttrc-dashboard", "printers": [], "net_devices": [], "services": [],
           "settings": {"brand_name": "Smith Print Shop", "brand_description": "Our farm"}}
    assert client.post("/api/settings/restore", json=old).status_code == 200
    s = client.get("/api/settings").json()
    assert s["farm_name"] == "Smith Print Shop" and "brand_name" not in s


def test_restart_only_as_service(client, monkeypatch):
    # Outside the LayerHound service the restart button must not kill the process,
    # even under systemd (e.g. on CI runners, which set INVOCATION_ID)
    monkeypatch.delenv("LAYERHOUND_SERVICE", raising=False)
    monkeypatch.setenv("INVOCATION_ID", "ci-runner")
    assert client.post("/api/settings/restart").status_code == 409
    assert client.get("/api/settings/about").json()["can_restart"] is False


# ---- Network & services -------------------------------------------------------------------
def test_network_device_validation(client):
    assert client.post("/api/network/devices", json={"name": "Bad", "host": "bad host!"}).status_code == 400
    assert client.post("/api/network/devices", json={"name": "Bad", "host": "1.2.3.4", "kind": "toaster"}).status_code == 400
    d = client.post("/api/network/devices", json={"name": "Lab switch", "host": "127.0.0.1", "kind": "other"}).json()
    assert client.delete(f"/api/network/devices/{d['id']}").status_code == 200


def test_service_validation_and_token_privacy(client):
    assert client.post("/api/services", json={"name": "x", "url": "javascript:alert(1)"}).status_code == 400
    assert client.post("/api/services", json={"name": "HA", "url": "http://127.0.0.1:9", "integration": "homeassistant"}).status_code == 400
    s = client.post("/api/services", json={"name": "HA", "url": "http://127.0.0.1:9", "integration": "homeassistant", "token": "TOKEN123"}).json()
    try:
        assert "token" not in s and s["has_token"] is True
        assert "TOKEN123" not in client.get("/api/services").text
    finally:
        client.delete(f"/api/services/{s['id']}")


def test_docker_restart_rejects_bad_ids(client):
    # "../" is collapsed before routing, so this never reaches the restart handler at all
    assert client.post("/api/services/docker/../../etc/restart").status_code >= 400
    assert client.post("/api/services/docker/not-hex/restart").status_code == 400
