# Stored secrets are encrypted: in the database, through the API, and in backups.
import json
import os
import stat
import main
import vault
from cryptography.fernet import Fernet

UNREACHABLE = "http://127.0.0.1:9"
CODE = "12345678"


def stored(table, col, row_id):
    c = main.db()
    v = c.execute(f"SELECT {col} FROM {table} WHERE id=?", (row_id,)).fetchone()[0]
    c.close()
    return v


def test_round_trip():
    a, b = vault.encrypt("secret"), vault.encrypt("secret")
    assert a.startswith(vault.PREFIX) and "secret" not in a and a != b
    assert vault.decrypt(a) == "secret"
    assert vault.encrypt(a) == a  # already encrypted: left alone
    assert vault.encrypt(None) is None and vault.encrypt("") is None and vault.decrypt(None) is None
    assert vault.decrypt("old plain value") == "old plain value"


def test_key_file_is_private():
    mode = stat.S_IMODE(os.stat(main.KEY_PATH).st_mode)
    assert mode == 0o600
    assert str(main.KEY_PATH).endswith(os.path.join("data", "secret.key"))


def test_wrong_key_gives_nothing_instead_of_crashing():
    other = Fernet(Fernet.generate_key())
    foreign = vault.PREFIX + other.encrypt(b"from another board").decode()
    assert vault.decrypt(foreign) is None


def test_printer_access_code_is_encrypted(client):
    r = client.post("/api/printers", json={"name": "Vault P1S", "printer_type": "bambu", "base_url": "127.0.0.1", "serial": "01P00A000000001", "api_key": CODE})
    assert r.status_code == 200
    pid = r.json()["id"]
    assert "api_key" not in r.json()
    raw = stored("printers", "api_key", pid)
    assert raw.startswith(vault.PREFIX) and CODE not in raw
    # Editing without a new code keeps the saved one; a new code replaces it
    client.put(f"/api/printers/{pid}", json={"name": "Vault P1S renamed"})
    assert vault.decrypt(stored("printers", "api_key", pid)) == CODE
    client.put(f"/api/printers/{pid}", json={"api_key": "87654321"})
    assert vault.decrypt(stored("printers", "api_key", pid)) == "87654321"
    client.delete(f"/api/printers/{pid}")


def test_service_token_is_encrypted(client):
    r = client.post("/api/services", json={"name": "HA", "url": UNREACHABLE, "integration": "homeassistant", "token": "ha-long-lived-token"})
    sid = r.json()["id"]
    raw = stored("services", "token", sid)
    assert raw.startswith(vault.PREFIX) and "ha-long-lived-token" not in raw
    client.delete(f"/api/services/{sid}")


def test_backup_and_restore(client):
    pid = client.post("/api/printers", json={"name": "Backup Octo", "printer_type": "octoprint", "base_url": UNREACHABLE, "api_key": "octo-key"}).json()["id"]
    with_secrets = json.loads(client.get("/api/settings/backup?secrets=true").content)
    assert next(p for p in with_secrets["printers"] if p["id"] == pid)["api_key"] == "octo-key"
    without = json.loads(client.get("/api/settings/backup?secrets=false").content)
    assert next(p for p in without["printers"] if p["id"] == pid)["api_key"] is None
    assert client.post("/api/settings/restore", json=with_secrets).status_code == 200
    raw = stored("printers", "api_key", pid)
    assert raw.startswith(vault.PREFIX) and vault.decrypt(raw) == "octo-key"
    client.delete(f"/api/printers/{pid}")


def test_existing_plain_values_are_encrypted_at_startup():
    c = main.db()
    pid = c.execute("INSERT INTO printers(name,printer_type,base_url,api_key,enabled,created_at,updated_at) VALUES('Old','octoprint',?, 'plain-old-key',0,'x','x')", (UNREACHABLE,)).lastrowid
    c.commit(); c.close()
    vault.migrate(main.db)
    raw = stored("printers", "api_key", pid)
    assert raw.startswith(vault.PREFIX) and vault.decrypt(raw) == "plain-old-key"
    c = main.db(); c.execute("DELETE FROM printers WHERE id=?", (pid,)); c.commit(); c.close()
