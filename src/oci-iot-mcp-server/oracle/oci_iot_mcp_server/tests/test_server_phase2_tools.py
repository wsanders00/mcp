from oracle.oci_iot_mcp_server import server


def test_wait_for_twin_update_returns_first_matching_content_path(monkeypatch):
    monkeypatch.setattr(
        server,
        "wait_for_twin_update_impl",
        lambda **_: {
            "digital_twin_instance_id": "ocid1.digitaltwininstance.oc1..aaaa",
            "content_path": "temperature",
            "value": 72,
            "time_observed": "2026-03-26T12:00:05Z",
        },
    )

    result = server.wait_for_twin_update(
        digital_twin_instance_id="ocid1.digitaltwininstance.oc1..aaaa",
        content_path="temperature",
        since="2026-03-26T12:00:00Z",
        timeout=30,
    )

    assert result["ok"] is True
    assert result["data"]["content_path"] == "temperature"


def test_wait_for_twin_update_requires_since():
    result = server.wait_for_twin_update(
        digital_twin_instance_id="ocid1.digitaltwininstance.oc1..aaaa",
        since="",
        timeout=30,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_input"


def test_list_recent_rejected_data_for_twin_sorts_by_time_received_desc(monkeypatch):
    monkeypatch.setattr(
        server,
        "list_recent_rejected_data_for_twin_impl",
        lambda **_: [
            {"id": "r-older", "time_received": "2026-03-26T11:59:59Z"},
            {"id": "r-newer", "time_received": "2026-03-26T12:00:01Z"},
        ],
    )

    result = server.list_recent_rejected_data_for_twin(
        digital_twin_instance_id="ocid1.digitaltwininstance.oc1..aaaa",
        limit=20,
    )

    assert result["ok"] is True
    assert result["data"][0]["id"] == "r-newer"


def test_list_recent_rejected_data_for_twin_rejects_limit_above_100():
    result = server.list_recent_rejected_data_for_twin(
        digital_twin_instance_id="ocid1.digitaltwininstance.oc1..aaaa",
        limit=101,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_input"
