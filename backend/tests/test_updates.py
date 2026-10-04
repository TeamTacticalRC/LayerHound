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
