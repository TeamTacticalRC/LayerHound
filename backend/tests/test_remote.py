# Remote access with Tailscale, using a stand-in for the tailscale command.
import json, subprocess
import pytest
import remote, settings

RUNNING = {"BackendState": "Running", "AuthURL": "",
           "Self": {"DNSName": "layerhound.example-tail.ts.net.", "TailscaleIPs": ["100.101.102.103", "fd7a::1"], "UserID": 7,
                    "KeyExpiry": "2027-04-01T00:00:00Z"},
           "CurrentTailnet": {"Name": "owner@example.com", "MagicDNSEnabled": True},
           "User": {"7": {"LoginName": "owner@example.com"}}}


class FakeTailscale:
    """Answers "tailscale status --json" with whatever state the test sets, and records commands."""
    def __init__(self, state):
        self.state, self.calls = state, []

    def run(self, args, **kw):
        self.calls.append(args[1:])
        if args[1:3] == ["status", "--json"]:
            return subprocess.CompletedProcess(args, 0, json.dumps(self.state), "")
        if args[1] == "down": self.state = {**self.state, "BackendState": "Stopped"}
        if args[1] == "logout": self.state = {"BackendState": "NeedsLogin"}
        return subprocess.CompletedProcess(args, 0, "", "")


class FakeUp:
    def __init__(self, args, **kw): FakeUp.args = args
    def poll(self): return None
    def kill(self): pass


@pytest.fixture
def ts(monkeypatch):
    fake = FakeTailscale({"BackendState": "NeedsLogin"})
    monkeypatch.setattr(subprocess, "run", fake.run)
    monkeypatch.setattr(remote.subprocess, "Popen", FakeUp)
    monkeypatch.setattr(remote, "_up", None)
    monkeypatch.setattr(settings, "as_service", lambda: True)
    return fake


def test_only_on_the_board(client, monkeypatch):
    assert client.get("/api/remote").json() == {"available": False}   # not running as the board's service
    monkeypatch.setattr(settings, "as_service", lambda: True); monkeypatch.setenv("LAYERHOUND_DOCKER", "1")
    assert client.get("/api/remote").json() == {"available": False}
    assert client.post("/api/remote/connect").status_code == 409


def test_not_installed(client, monkeypatch):
    monkeypatch.setattr(settings, "as_service", lambda: True)
    def missing(*a, **k): raise FileNotFoundError("tailscale")
    monkeypatch.setattr(subprocess, "run", missing)
    r = client.get("/api/remote").json()
    assert r["available"] and not r["installed"]
    assert "install" in client.post("/api/remote/connect").json()["detail"]


def test_connect_shows_the_sign_in_link(client, ts, monkeypatch):
    assert client.get("/api/remote").json()["state"] == "needs_login"
    def start(*a, **k):
        FakeUp(*a, **k)
        ts.state = {"BackendState": "NeedsLogin", "AuthURL": "https://login.tailscale.com/a/abc123"}
    monkeypatch.setattr(remote.subprocess, "Popen", lambda *a, **k: (start(*a, **k), FakeUp(*a, **k))[1])
    r = client.post("/api/remote/connect").json()
    assert r["auth_url"] == "https://login.tailscale.com/a/abc123" and r["auth_qr"].startswith("<svg") and r["waiting_for_sign_in"]
    # Keeps LayerHound in control, keeps the board's own DNS, and uses the board's name
    args = FakeUp.args
    assert args[:3] == ["tailscale", "up", "--reset"] and "--accept-dns=false" in args
    assert any(a.startswith("--operator=") for a in args) and any(a.startswith("--hostname=") for a in args)


def test_connected(client, ts):
    ts.state = RUNNING
    r = client.get("/api/remote").json()
    assert r["state"] == "connected" and r["account"] == "owner@example.com" and r["ip"] == "100.101.102.103"
    assert r["url"] == "http://layerhound.example-tail.ts.net" and r["url_qr"].startswith("<svg")
    # Already connected: nothing to start
    client.post("/api/remote/connect")
    assert not any(c[:1] == ["up"] for c in ts.calls)


def test_address_uses_the_port_and_falls_back_to_the_ip(client, ts, monkeypatch):
    monkeypatch.setenv("LAYERHOUND_PORT", "8080")
    ts.state = {**RUNNING, "CurrentTailnet": {"Name": "x", "MagicDNSEnabled": False}}
    assert client.get("/api/remote").json()["url"] == "http://100.101.102.103:8080"


def test_turn_off_and_sign_out(client, ts):
    ts.state = RUNNING
    assert client.post("/api/remote/off").json()["state"] == "off"
    assert ["down"] in ts.calls
    assert client.post("/api/remote/sign-out").json()["state"] == "needs_login"
    assert ["logout"] in ts.calls


def test_viewers_cannot_see_or_change_it(client, ts):
    from conftest import new_client
    client.post("/api/auth/users", json={"username": "remoteviewer", "password": "remote view 1", "role": "viewer"})
    v = new_client()
    v.post("/api/auth/login", json={"username": "remoteviewer", "password": "remote view 1"})
    assert v.get("/api/remote").status_code == 403
    assert v.post("/api/remote/connect").status_code == 403
