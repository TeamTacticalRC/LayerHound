# Optional anonymous usage stats: what's in them, and that nothing goes out without a yes.
import urllib.parse
import network, settings, stats

FORM = {"id": "FORMID", "fields": {k: f"entry.{i}" for i, k in enumerate(
    ["install_id", "version", "install_type", "board", "klipper", "bambu", "octoprint", "country"])}}


def test_preview_has_only_counts_and_basics(client, monkeypatch):
    r = client.post("/api/printers", json={"name": "Secret Shop Voron", "printer_type": "moonraker", "base_url": "http://127.0.0.1:9"})
    monkeypatch.setitem(network.state, "country", "US")
    p = client.get("/api/stats").json()["preview"]
    assert set(p) == {"install_id", "version", "install_type", "board", "klipper", "bambu", "octoprint", "country"}
    assert p["klipper"] >= 1 and p["country"] == "US" and len(p["install_id"]) == 16
    # Nothing identifying: no printer names, addresses or the farm name
    text = str(p)
    assert "Secret Shop" not in text and "127.0.0.1" not in text and settings.get("farm_name") not in text
    client.delete(f"/api/printers/{r.json()['id']}")


def test_install_id_is_stable_and_kept_outside_the_database(client):
    a = stats.install_id(); b = stats.install_id()
    assert a == b and stats._id_file.read_text().strip() == a and stats._id_file.parent.name == "data"


def test_sends_exactly_the_preview(monkeypatch, client):
    sent = []
    class R:
        def __enter__(self): return self
        def __exit__(self, *a): pass
    monkeypatch.setattr(stats, "FORM", FORM)
    monkeypatch.setattr(stats.urllib.request, "urlopen", lambda req, timeout=20: (sent.append(req), R())[1])
    assert stats.send()
    req = sent[0]
    assert req.full_url == "https://docs.google.com/forms/d/e/FORMID/formResponse"
    body = dict(urllib.parse.parse_qsl(req.data.decode(), keep_blank_values=True))
    assert body["entry.0"] == stats.install_id() and body["entry.1"] == settings.APP_VERSION and set(body) == set(FORM["fields"].values())


def test_nothing_is_sent_without_a_form_or_a_yes(monkeypatch, client):
    monkeypatch.setattr(stats, "FORM", None)
    assert stats.send() is False
    assert settings.get("usage_stats") in ("ask", "no", "yes")
    assert client.get("/api/stats").json()["choice"] == settings.get("usage_stats")


def test_choice_is_validated_and_saved(client):
    assert client.put("/api/settings", json={"usage_stats": "maybe"}).status_code == 400
    assert client.put("/api/settings", json={"usage_stats": "no"}).json()["usage_stats"] == "no"
    client.put("/api/settings", json={"usage_stats": "ask"})
