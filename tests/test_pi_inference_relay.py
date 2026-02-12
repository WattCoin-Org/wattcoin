from pi.inference_relay import InferenceRelay, RelayConfig


def test_run_once_contains_required_fields():
    relay = InferenceRelay(RelayConfig(relay_id="relay-test", relay_secret="secret"))
    result = relay.run_once({"job_id": "job-1", "prompt": "hello world"})

    assert result["job_id"] == "job-1"
    assert result["relay_id"] == "relay-test"
    assert result["status"] == "completed"
    assert "output" in result and "hello world" in result["output"]
    assert isinstance(result["latency_ms"], int)


def test_signature_stable_for_same_payload():
    relay = InferenceRelay(RelayConfig(relay_id="relay-test", relay_secret="secret"))
    payload = {"a": 1, "b": 2}

    sig1 = relay._signed_headers(payload)["X-Relay-Signature"]
    sig2 = relay._signed_headers(payload)["X-Relay-Signature"]

    assert sig1 == sig2
    assert len(sig1) == 64
