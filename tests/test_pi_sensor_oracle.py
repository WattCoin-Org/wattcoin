from pathlib import Path

from pi.sensor_oracle.oracle import MockSensors, append_history, build_signature


def test_mock_sensors_support_two_sensor_types(tmp_path: Path):
    mock_file = tmp_path / "mock.json"
    mock_file.write_text('{"temperature_c": 21.0, "humidity_percent": 40.2, "motion": true}', encoding="utf-8")

    sensors = MockSensors(mock_file)
    dht = sensors.read_dht22()
    pir = sensors.read_pir()

    assert len(dht) == 2
    assert {s.sensor_type for s in dht} == {"temperature_c", "humidity_percent"}
    assert pir.sensor_type == "motion"
    assert pir.value is True


def test_signature_and_history_write(tmp_path: Path):
    payload = {"wallet": "w1", "timestamp": "2026-01-01T00:00:00Z", "readings": []}
    sig1 = build_signature(payload, "secret")
    sig2 = build_signature(payload, "secret")
    assert sig1 == sig2

    hist = tmp_path / "history.jsonl"
    append_history(hist, {"ok": True})
    line = hist.read_text(encoding="utf-8").strip()
    assert '"ok": true' in line
