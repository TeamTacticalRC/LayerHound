# Sign-in, first-run setup, roles, access keys and guest viewing.
import auth
from conftest import ADMIN, HEADERS, new_client


def login(c, username, password, remember=False):
    return c.post("/api/auth/login", json={"username": username, "password": password, "remember": remember})


def test_setup_only_once(client):
    s = client.get("/api/auth/status").json()
    assert s["setup_required"] is False and s["user"]["role"] == "admin" and s["farm_name"]
    r = new_client().post("/api/auth/setup", json={"farm_name": "Hijack", "username": "x", "password": "password123"})
    assert r.status_code == 409


def test_signed_out_requests_are_refused(client):
    c = new_client()
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/auth/status").json()["user"] is None
    for path in ("/api/printers", "/api/settings", "/api/system", "/api/history"):
        assert c.get(path).status_code == 401, path


def test_changes_need_the_request_header(client):
    # A form on another website can't add this header, so it can't make changes with your login
    r = client.put("/api/settings", json={"temp_unit": "F"}, headers={"X-Requested-With": ""})
    assert r.status_code == 403


def test_login_logout_and_cookie(client):
    c = new_client()
    assert login(c, "owner", "wrong password").status_code == 401
    r = login(c, "OWNER", ADMIN["password"], remember=True)
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "max-age=2592000" in cookie
    assert c.get("/api/printers").status_code == 200
    c.post("/api/auth/logout")
    assert c.get("/api/printers").status_code == 401


def test_session_cookie_without_remember(client):
    r = login(new_client(), "owner", ADMIN["password"])
    assert "max-age" not in r.headers["set-cookie"].lower()


def test_lockout_after_five_wrong_passwords(client):
    c = new_client()
    for _ in range(5):
        assert login(c, "owner", "nope nope").status_code == 401
    r = login(c, "owner", ADMIN["password"])
    assert r.status_code == 429
    auth._fails.clear()
    assert login(c, "owner", ADMIN["password"]).status_code == 200


def test_viewer_is_read_only(client):
    r = client.post("/api/auth/users", json={"username": "shopfloor", "password": "viewer pass 1", "role": "viewer"})
    assert r.status_code == 200
    uid = r.json()["id"]
    v = new_client()
    assert login(v, "shopfloor", "viewer pass 1").status_code == 200
    assert v.get("/api/printers").status_code == 200
    assert v.put("/api/settings", json={"temp_unit": "F"}).status_code == 403
    assert v.get("/api/settings/backup").status_code == 403
    assert v.post("/api/settings/shutdown").status_code == 403
    assert v.get("/api/auth/users").status_code == 403
    # Viewers may still change their own password
    assert v.post("/api/auth/password", json={"current": "viewer pass 1", "new": "viewer pass 2"}).status_code == 200
    assert client.delete(f"/api/auth/users/{uid}").status_code == 200
    assert v.get("/api/printers").status_code == 401


def test_cannot_remove_last_admin(client):
    me = next(u for u in client.get("/api/auth/users").json()["users"] if u["username"] == "owner")
    assert client.delete(f"/api/auth/users/{me['id']}").status_code == 409
    assert client.put(f"/api/auth/users/{me['id']}", json={"role": "viewer"}).status_code == 409


def test_password_rules(client):
    r = client.post("/api/auth/users", json={"username": "short", "password": "1234567"})
    assert r.status_code == 400
    r = client.post("/api/auth/users", json={"username": "bad name!", "password": "long enough"})
    assert r.status_code == 400


def test_access_keys(client):
    r = client.post("/api/auth/keys", json={"name": "LED bar"})
    key = r.json()["key"]
    assert key.startswith("lhk_")
    listed = client.get("/api/auth/keys").json()["keys"]
    assert all("key" not in k and "key_hash" not in k for k in listed)
    d = new_client()
    assert d.get("/api/printers", headers={"Authorization": f"Bearer {key}"}).status_code == 200
    assert d.get(f"/api/printers?key={key}").status_code == 200
    assert d.put("/api/settings", json={"temp_unit": "F"}, headers={"Authorization": f"Bearer {key}"}).status_code == 403
    assert client.delete(f"/api/auth/keys/{r.json()['id']}").status_code == 200
    assert d.get("/api/printers", headers={"Authorization": f"Bearer {key}"}).status_code == 401


def test_guest_viewing(client):
    g = new_client()
    assert g.get("/api/printers").status_code == 401
    client.put("/api/settings", json={"guest_view": True})
    try:
        assert g.get("/api/printers").status_code == 200
        assert g.get("/api/auth/status").json()["user"]["kind"] == "guest"
        assert g.put("/api/settings", json={"temp_unit": "F"}).status_code == 403
    finally:
        client.put("/api/settings", json={"guest_view": False})


def test_only_local_addresses_count_as_local():
    from conftest import _is_local
    assert _is_local("192.168.1.20") and _is_local("10.0.0.5") and _is_local("127.0.0.1") and _is_local("fe80::1")
    assert not _is_local("8.8.8.8") and not _is_local("testclient")


def test_password_hashes_are_one_way():
    h = auth.hash_password("hunter2 hunter2")
    assert "hunter2" not in h and auth.check_password("hunter2 hunter2", h) and not auth.check_password("hunter3 hunter3", h)


def test_reset_password_on_the_board(client):
    auth.reset_password("owner", "a brand new pass")
    c = new_client()
    assert login(c, "owner", ADMIN["password"]).status_code == 401
    assert login(c, "owner", "a brand new pass").status_code == 200
    auth.reset_password("owner", ADMIN["password"])
    # The shared test client was signed out by the reset; sign it back in
    assert login(client, "owner", ADMIN["password"]).status_code == 200
