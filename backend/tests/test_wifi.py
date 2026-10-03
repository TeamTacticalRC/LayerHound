# Wi-Fi settings: parsing nmcli output, and behavior where Wi-Fi isn't managed (e.g. a Mac).
import wifi

SCAN = r"""*:HomeNetwork_5:100:5660 MHz:WPA1 WPA2
 :HomeNetwork_2.4:78:2462 MHz:WPA1 WPA2
 :HomeNetwork_2.4:55:2412 MHz:WPA1 WPA2
 ::40:2437 MHz:WPA2
 :Cafe\:Guest:30:2412 MHz:
 :Office:61:5180 MHz:WPA2 802.1X
"""


def test_parse_scan():
    nets = wifi.parse_scan(SCAN, saved={"HomeNetwork_5"})
    names = [n["ssid"] for n in nets]
    assert names[0] == "HomeNetwork_5"                      # the connected network comes first
    assert names.count("HomeNetwork_2.4") == 1              # duplicates collapse to the strongest
    assert "" not in names                                  # hidden networks are skipped
    first = nets[0]
    assert first["in_use"] and first["saved"] and first["band"] == "5 GHz" and first["secure"]
    two = next(n for n in nets if n["ssid"] == "HomeNetwork_2.4")
    assert two["signal"] == 78 and two["band"] == "2.4 GHz"
    cafe = next(n for n in nets if n["ssid"] == "Cafe:Guest")  # escaped ":" in the name
    assert cafe["secure"] is False
    assert next(n for n in nets if n["ssid"] == "Office")["enterprise"] is True


def test_friendly_errors():
    assert wifi.friendly("Error: Connection activation failed: Secrets were required, but not provided.") == "The password was rejected"
    assert wifi.friendly("Error: No network with SSID 'Nope' found.") == "That network isn't in range"


def test_unavailable_where_wifi_isnt_managed(client, monkeypatch):
    monkeypatch.setattr(wifi, "available", lambda: False)
    s = client.get("/api/network/wifi").json()
    assert s["available"] is False and "board" in s["reason"]
    assert client.post("/api/network/wifi/connect", json={"ssid": "x", "password": "y"}).status_code == 404
    assert client.post("/api/network/wifi/forget", json={"ssid": "x"}).status_code == 404
