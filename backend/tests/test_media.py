# Thumbnails, layers and cameras.
import media

UNREACHABLE = "http://127.0.0.1:9"


def test_layers_from_klipper_print_stats():
    assert media.moonraker_layers(None, {"current_layer": 174, "total_layer": 913}, {}, 27.7, True) == (174, 913)


def test_layers_from_creality_counter():
    assert media.moonraker_layers(None, {"current_layer": None, "total_layer": None}, {"layer": 1336, "layer_count": 1742}, 266.8, True) == (1336, 1742)


def test_layers_worked_out_from_nozzle_height():
    # Elegoo Neptune 4: no layer info, so use slicer metadata and the nozzle's height
    meta = {"layer_count": 1900, "layer_height": 0.2, "first_layer_height": 0.2}
    assert media.moonraker_layers(meta, None, {}, 24.2, True) == (121, 1900)


def test_no_layers_when_not_printing():
    assert media.moonraker_layers({"layer_count": 10}, {"current_layer": 3, "total_layer": 10}, {}, 1.0, False) == (None, None)


def test_camera_url_validation_and_clearing(client):
    bad = client.post("/api/printers", json={"name": "Cam", "printer_type": "moonraker", "base_url": UNREACHABLE, "camera_url": "ftp://cam/x"})
    assert bad.status_code == 400
    p = client.post("/api/printers", json={"name": "Cam", "printer_type": "moonraker", "base_url": UNREACHABLE,
                                           "camera_url": "http://127.0.0.1:9/webcam/?action=snapshot"}).json()
    try:
        assert p["camera_url"].startswith("http://") and p["has_camera"] is True
        # The camera can't be reached, so the endpoint reports that instead of hanging or crashing
        assert client.get(f"/api/printers/{p['id']}/camera").status_code == 502
        cleared = client.put(f"/api/printers/{p['id']}", json={"camera_url": ""}).json()
        assert cleared["camera_url"] is None and cleared["has_camera"] is False
        assert client.get(f"/api/printers/{p['id']}/camera").status_code == 404
    finally:
        client.delete(f"/api/printers/{p['id']}")


def test_no_thumbnail_without_a_job(client):
    p = client.post("/api/printers", json={"name": "Idle", "printer_type": "moonraker", "base_url": UNREACHABLE}).json()
    try:
        assert client.get(f"/api/printers/{p['id']}/thumbnail").status_code == 404
        assert client.get("/api/printers/99999/camera").status_code == 404
    finally:
        client.delete(f"/api/printers/{p['id']}")
