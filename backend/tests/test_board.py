# The board's own login on a LayerHound card: set once from the setup page (board.py).
import sqlite3
import pytest
import auth, board
from conftest import ADMIN, new_client


@pytest.fixture
def card(tmp_path, monkeypatch):
    # A card that still has its maker's board password; records what LayerHound asks the helper to set
    mark = tmp_path / "board-password-needed"; mark.write_text("radxa\n")
    monkeypatch.setattr(board, "MARK", mark)
    calls = []
    def fake_set(pw):
        calls.append(pw)
        if fake_set.error: return fake_set.error
        mark.unlink(); return None
    fake_set.error = None
    monkeypatch.setattr(board, "set_password", fake_set)
    return calls, fake_set


@pytest.fixture
def new_farm(tmp_path, monkeypatch):
    # An empty database, so first-run setup can run again
    def fresh():
        c = sqlite3.connect(tmp_path / "farm.db"); c.row_factory = sqlite3.Row; return c
    monkeypatch.setattr(auth, "_db", auth._db)   # put back afterwards
    auth.configure(fresh)
    return new_client()


def setup(c, **extra):
    return c.post("/api/auth/setup", json={"farm_name": "Card Farm", "username": "admin", "password": "admin password 1", **extra})


def test_only_the_person_setting_up_or_an_admin_is_told(client, card):
    s = client.get("/api/auth/status").json()
    assert s["board_password_needed"] is True and s["board_user"] == "radxa"
    signed_out = new_client().get("/api/auth/status").json()
    assert signed_out["board_password_needed"] is False and "board_user" not in signed_out


def test_not_asked_on_other_boards(client):
    assert client.get("/api/auth/status").json()["board_password_needed"] is False


def test_setup_needs_a_board_password_on_a_card(new_farm, card):
    calls, _ = card
    assert new_farm.get("/api/auth/status").json()["board_password_needed"] is True
    assert setup(new_farm).status_code == 400
    assert setup(new_farm, board_password="short").status_code == 400
    assert calls == []
    r = setup(new_farm, board_password="board password 1")
    assert r.status_code == 200 and r.json()["board_password"] == {"set": True}
    assert calls == ["board password 1"]
    assert new_farm.get("/api/auth/status").json()["board_password_needed"] is False


def test_setup_finishes_even_if_the_board_password_fails(new_farm, card):
    calls, fake = card
    fake.error = "The board is still finishing its first start. Try again in a minute."
    r = setup(new_farm, board_password="board password 1")
    assert r.status_code == 200 and r.json()["recovery_key"]
    assert r.json()["board_password"] == {"set": False, "error": fake.error}
    # Then the dashboard asks again
    assert new_farm.get("/api/auth/status").json()["board_password_needed"] is True


def test_setup_elsewhere_ignores_the_board_password(new_farm):
    r = setup(new_farm, board_password="anything at all")
    assert r.status_code == 200 and "board_password" not in r.json()


def test_admin_sets_it_later_with_their_password(client, card):
    calls, _ = card
    assert client.post("/api/auth/board-password", json={"password": "wrong", "board_password": "board password 2"}).status_code == 400
    assert client.post("/api/auth/board-password", json={"password": ADMIN["password"], "board_password": "short"}).status_code == 400
    assert calls == []
    assert client.post("/api/auth/board-password", json={"password": ADMIN["password"], "board_password": "board password 2"}).status_code == 200
    assert calls == ["board password 2"]
    # Only once: after that it's changed on the board itself
    assert client.post("/api/auth/board-password", json={"password": ADMIN["password"], "board_password": "board password 3"}).status_code == 409


def test_viewers_cant_set_it(client, card):
    client.post("/api/auth/users", json={"username": "boardviewer", "password": "viewer pass 9", "role": "viewer"})
    v = new_client()
    assert v.post("/api/auth/login", json={"username": "boardviewer", "password": "viewer pass 9"}).status_code == 200
    assert v.get("/api/auth/status").json()["board_password_needed"] is False
    assert v.post("/api/auth/board-password", json={"password": "viewer pass 9", "board_password": "board password 4"}).status_code == 403
    assert card[0] == []


def test_helper_errors_are_passed_on(tmp_path, monkeypatch):
    mark = tmp_path / "mark"; mark.write_text("radxa")
    monkeypatch.setattr(board, "MARK", mark)
    monkeypatch.setattr(board, "HELPER", str(tmp_path / "missing"))
    assert "can't set its password" in board.set_password("board password 5")
    helper = tmp_path / "helper"; helper.write_text("#!/bin/sh\necho 'The board password is already set.' >&2\nexit 1\n"); helper.chmod(0o755)
    monkeypatch.setattr(board, "HELPER", str(helper))
    monkeypatch.setattr(board.os, "geteuid", lambda: 0)   # run it directly, without sudo
    assert board.set_password("board password 5") == "The board password is already set."
    mark.unlink()
    assert board.set_password("board password 5") is None   # nothing to do without the mark
