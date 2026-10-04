# Case fan speed control, against a fake /sys/class/hwmon folder.
import pytest
import fan, settings


def make_hwmon(root, name, **files):
    d = root / f"hwmon{len(list(root.glob('hwmon*')))}"
    d.mkdir()
    (d / "name").write_text(name + "\n")
    for k, v in files.items():
        (d / k).write_text(str(v))
    return d


@pytest.fixture
def board(tmp_path, monkeypatch):
    make_hwmon(tmp_path, "soc_thermal", temp1_input=44000)
    big = make_hwmon(tmp_path, "bigcore_thermal", temp1_input=46000)
    pwm = make_hwmon(tmp_path, "pwmfan", pwm1=255, pwm1_enable=1)
    monkeypatch.setattr(fan, "HWMON", tmp_path)
    fan.state.update(percent=None, target=None, temp_c=None, error=None)
    yield tmp_path, big, pwm
    fan.state.update(percent=None, target=None, temp_c=None, error=None)


def test_curve():
    assert fan.curve(30, 45, 65, 30) == 30
    assert fan.curve(45, 45, 65, 30) == 30
    assert fan.curve(55, 45, 65, 30) == 65
    assert fan.curve(65, 45, 65, 30) == 100
    assert fan.curve(90, 45, 65, 30) == 100
    assert fan.curve(None, 45, 65, 30) == 100  # no temperature: full speed


def test_speeds_up_at_once_and_slows_down_gently():
    assert fan.next_percent(30, 80) == 80
    assert fan.next_percent(80, 30) == 80 - fan.STEP_DOWN
    assert fan.next_percent(32, 30) == 30


def test_uses_hottest_sensor(board):
    root, _, _ = board
    assert fan.chip_temp(root) == 46.0


def test_tick_sets_speed_from_temperature(board):
    root, big, pwm = board
    d = fan.device(root)
    # Starts at full speed (as the board boots) and steps down toward the quiet minimum
    fan.tick(d, root)
    assert fan.state["target"] == fan.curve(46.0, 45, 65, 30)
    assert fan.state["percent"] == 100 - fan.STEP_DOWN
    for _ in range(30):
        fan.tick(d, root)
    assert fan.state["percent"] == fan.state["target"]
    assert int((pwm / "pwm1").read_text()) == round(255 * fan.state["percent"] / 100)
    # Hot: straight to full speed
    (big / "temp1_input").write_text("70000")
    fan.tick(d, root)
    assert fan.state["percent"] == 100 and (pwm / "pwm1").read_text() == "255"


def test_full_mode(board, monkeypatch):
    root, _, pwm = board
    real_get = settings.get
    monkeypatch.setattr(settings, "get", lambda k: "full" if k == "fan_mode" else real_get(k))
    fan.state["percent"] = 40
    fan.tick(fan.device(root), root)
    assert fan.state["percent"] == 100


def test_missing_temperature_means_full_speed(board):
    root, _, _ = board
    for d in root.glob("hwmon*"):
        t = d / "temp1_input"
        if t.exists():
            t.unlink()
    fan.state["percent"] = 30
    fan.tick(fan.device(root), root)
    assert fan.state["percent"] == 100 and fan.state["error"]


def test_no_fan_here(tmp_path, monkeypatch):
    monkeypatch.setattr(fan, "HWMON", tmp_path)
    assert fan.status() == {"available": False}


def test_settings_validation(client):
    r = client.put("/api/settings", json={"fan_quiet_temp": 70, "fan_full_temp": 60})
    assert r.status_code == 400
    r = client.put("/api/settings", json={"fan_mode": "turbo"})
    assert r.status_code == 400
    r = client.put("/api/settings", json={"fan_mode": "full"})
    assert r.status_code == 200 and r.json()["fan_mode"] == "full"
    client.put("/api/settings", json={"fan_mode": "auto"})
    assert "fan" in client.get("/api/server").json()
