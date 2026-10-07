# Update checks, signatures, and the updater's install/rollback, in a fake app folder.
import base64, hashlib, io, json, tarfile
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import settings, updater, updates


def test_versions():
    assert updates.parse_version("v0.6.0") == (0, 6, 0) and updates.parse_version("0.10.2") == (0, 10, 2)
    assert updates.parse_version("latest") is None
    assert updates.newer("0.10.0", "0.9.9") and not updates.newer("0.5.0", "0.5.0") and not updates.newer("0.4.9", "0.5.0")


def test_signatures():
    key = Ed25519PrivateKey.generate()
    pub = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    data = b"package bytes"
    assert updates.verify(data, key.sign(data), pub)
    assert not updates.verify(data + b"!", key.sign(data), pub)
    # The real release key rejects a package signed by anyone else
    assert not updates.verify(data, key.sign(data))


def test_parse_release():
    rel = {"tag_name": "v0.6.0", "body": "Notes", "published_at": "2026-10-04T00:00:00Z", "html_url": "https://x",
           "assets": [{"name": "manifest.json", "browser_download_url": "https://x/manifest.json"}]}
    r = updates.parse_release(rel)
    assert r["version"] == "0.6.0" and r["notes"] == "Notes" and "manifest.json" in r["assets"]


def test_status_and_install_rules(client, monkeypatch):
    monkeypatch.setitem(updates.state, "latest", {"version": "99.0.0", "notes": "", "assets": {}, "manifest": {"sha256": "x"}})
    s = client.get("/api/updates").json()
    assert s["available"] and not s["can_install"] and "board" in s["reason"]   # not running as the board's service
    assert client.post("/api/updates/install").status_code == 409
    monkeypatch.setattr(settings, "as_service", lambda: True)
    monkeypatch.setitem(updates.state, "latest", {"version": "99.0.0", "notes": "", "assets": {}, "manifest": {"sha256": "x", "requires_setup": True}})
    s = client.get("/api/updates").json()
    assert not s["can_install"] and "setup" in s["reason"]
    monkeypatch.setitem(updates.state, "latest", None)
    assert client.post("/api/updates/install").status_code == 409


def make_package(path, files, version="9.9.9", extra=None):
    with tarfile.open(path, "w:gz") as t:
        for name, text in {**files, "VERSION": version}.items():
            data = text.encode(); info = tarfile.TarInfo(f"layerhound/{name}"); info.size = len(data)
            t.addfile(info, io.BytesIO(data))
        if extra:
            info = tarfile.TarInfo(extra); info.size = 1; t.addfile(info, io.BytesIO(b"x"))


@pytest.fixture
def app(tmp_path, monkeypatch):
    # A fake installed LayerHound: code, a database, its data folder and Python environment
    appdir = tmp_path / "layerhound"; backend = appdir / "backend"
    for p, text in {"backend/main.py": "old", "backend/old_only.py": "gone after update", "backend/requirements.txt": "a==1",
                    "dist/index.html": "old ui", "deploy/setup.sh": "old", "backend/.venv/marker": "venv",
                    "backend/data/secret.key": "key"}.items():
        (appdir / p).parent.mkdir(parents=True, exist_ok=True); (appdir / p).write_text(text)
    db = backend / "layerhound.db"
    import sqlite3
    c = sqlite3.connect(db); c.execute("CREATE TABLE t(v)"); c.execute("INSERT INTO t VALUES('before')"); c.commit(); c.close()
    for k, v in {"BACKEND": backend, "APP_DIR": appdir, "DB_PATH": db, "DATA": backend / "data", "UPDATES": backend / "data/updates",
                 "BACKUPS": backend / "data/backups", "ROLLBACK": tmp_path / "layerhound-rollback"}.items():
        monkeypatch.setattr(updater, k, v)
    (backend / "data/updates").mkdir(parents=True)
    calls = []
    monkeypatch.setattr(updater, "restart", lambda: calls.append("restart"))
    monkeypatch.setattr(updater, "pip_install", lambda: calls.append("pip"))
    return appdir, db, calls


def job(app_dir, package):
    return {"version": "9.9.9", "from_version": "0.5.0", "started": 0, "package": str(package)}


def test_update_installs_and_keeps_data(app, monkeypatch, tmp_path):
    appdir, db, calls = app
    pkg = tmp_path / "p.tar.gz"
    make_package(pkg, {"backend/main.py": "new", "backend/requirements.txt": "a==2", "dist/index.html": "new ui", "deploy/setup.sh": "new"})
    monkeypatch.setattr(updater, "wait_for", lambda v, timeout=0: v == "9.9.9")
    updater.run(job(appdir, pkg))
    state = json.loads((appdir / "backend/data/updates/state.json").read_text())
    assert state["phase"] == "done"
    assert (appdir / "backend/main.py").read_text() == "new" and (appdir / "dist/index.html").read_text() == "new ui"
    assert not (appdir / "backend/old_only.py").exists()
    # Kept: database, data folder, Python environment
    assert db.exists() and (appdir / "backend/data/secret.key").read_text() == "key" and (appdir / "backend/.venv/marker").exists()
    assert calls == ["pip", "restart"] and list((appdir / "backend/data/backups").glob("*.db"))


def test_failed_update_rolls_back(app, monkeypatch, tmp_path):
    appdir, db, calls = app
    pkg = tmp_path / "p.tar.gz"
    make_package(pkg, {"backend/main.py": "broken", "backend/requirements.txt": "a==1", "dist/index.html": "new ui"})
    # The new version never answers; the old one does after the rollback
    monkeypatch.setattr(updater, "wait_for", lambda v, timeout=0: v == "0.5.0")
    def restart():
        calls.append("restart")
        if calls.count("restart") == 1:   # the new version changes the database, then fails
            import sqlite3
            c = sqlite3.connect(db); c.execute("UPDATE t SET v='after'"); c.commit(); c.close()
    monkeypatch.setattr(updater, "restart", restart)
    updater.run(job(appdir, pkg))
    state = json.loads((appdir / "backend/data/updates/state.json").read_text())
    assert state["phase"] == "failed" and state["rolled_back"] is True and "did not start" in state["error"]
    assert (appdir / "backend/main.py").read_text() == "old" and (appdir / "backend/old_only.py").exists()
    assert (appdir / "dist/index.html").read_text() == "old ui"
    import sqlite3
    c = sqlite3.connect(db); v = c.execute("SELECT v FROM t").fetchone()[0]; c.close()
    assert v == "before"  # database restored from the backup taken before the update
    assert calls == ["restart", "restart"]


def test_unsafe_package_is_refused(app, tmp_path):
    appdir, _, _ = app
    pkg = tmp_path / "evil.tar.gz"
    make_package(pkg, {"backend/main.py": "x"}, extra="layerhound/../../escape.txt")
    with pytest.raises(ValueError):
        updater.safe_extract(pkg, tmp_path / "stage")
    assert not (tmp_path / "escape.txt").exists()


def test_kept_paths():
    assert updater.kept("backend/.venv/bin/python") and updater.kept("backend/layerhound.db") and updater.kept("backend/data/x")
    assert not updater.kept("backend/main.py") and not updater.kept("dist/index.html")


def test_docker_mode(client, monkeypatch):
    # In the Docker image: restart works (Docker restarts the container), shut down doesn't,
    # and updates are installed by pulling the new image
    monkeypatch.setenv("LAYERHOUND_DOCKER", "1")
    about = client.get("/api/settings/about").json()
    assert about["runtime"] == "docker" and about["can_restart"] is True and about["can_shutdown"] is False
    monkeypatch.setitem(updates.state, "latest", {"version": "99.0.0", "notes": "", "assets": {}, "manifest": {"sha256": "x"}})
    s = client.get("/api/updates").json()
    assert s["available"] and not s["can_install"] and "docker compose pull" in s["reason"]
    assert client.post("/api/settings/shutdown").status_code == 409


def test_automatic_updates(client, monkeypatch, tmp_path):
    from datetime import datetime
    monkeypatch.setattr(updates, "DIR", tmp_path)
    monkeypatch.setattr(settings, "as_service", lambda: True)
    at3 = datetime(2026, 10, 8, 3, 15); at4 = datetime(2026, 10, 8, 4, 15)
    # Off by default
    assert client.get("/api/settings").json()["auto_update"] is False and not updates.auto_due(at3)
    assert client.put("/api/settings", json={"auto_update": True, "auto_update_hour": 3, "time_zone": "America/Chicago"}).status_code == 200
    assert client.put("/api/settings", json={"time_zone": "Not/AZone"}).status_code == 400
    assert updates.auto_due(at3) and not updates.auto_due(at4)
    s = client.get("/api/updates").json()
    assert s["auto_update"] and s["auto_update_hour"] == 3 and s["can_auto"]

    latest = {"version": "99.0.0", "notes": "", "assets": {}, "manifest": {"sha256": "x"}}
    monkeypatch.setattr(updates, "check", lambda: (updates.state.update(latest=latest), updates.status())[1])
    installed = []
    monkeypatch.setattr(updates, "_install", lambda rel, auto=False: installed.append((rel["version"], auto)))
    assert updates.auto_update(at3) == "99.0.0" and installed == [("99.0.0", True)]
    # Only once a day, even after the restart that follows an update
    assert not updates.auto_due(at3) and updates.auto_due(datetime(2026, 10, 9, 3, 5))
    # A version that failed and rolled back isn't retried automatically
    updates.write_job(version="99.0.0", from_version="1.1.0", started=0, phase="failed", error="x", auto=True)
    assert updates.auto_update(datetime(2026, 10, 9, 3, 5)) is None and len(installed) == 1
    # Never in Docker (updates there come from pulling the image)
    monkeypatch.setenv("LAYERHOUND_DOCKER", "1")
    assert not updates.auto_due(datetime(2026, 10, 10, 3, 5)) and not client.get("/api/updates").json()["can_auto"]
    client.put("/api/settings", json={"auto_update": False, "time_zone": ""})   # the test client is shared


def test_owner_time_zone(monkeypatch):
    monkeypatch.setattr(settings, "get", lambda k: {"time_zone": "Asia/Tokyo"}.get(k))
    assert updates.local_now().utcoffset().total_seconds() == 9 * 3600
    monkeypatch.setattr(settings, "get", lambda k: {"time_zone": ""}.get(k))
    assert updates.local_now().tzinfo is not None


def test_updater_keeps_the_automatic_flag(app, monkeypatch, tmp_path):
    appdir, _, _ = app
    pkg = tmp_path / "p.tar.gz"
    make_package(pkg, {"backend/main.py": "new", "backend/requirements.txt": "a==2"})
    monkeypatch.setattr(updater, "wait_for", lambda v, timeout=0: True)
    updater.run({**job(appdir, pkg), "auto": True})
    state = json.loads((appdir / "backend/data/updates/state.json").read_text())
    assert state["phase"] == "done" and state["auto"] is True
