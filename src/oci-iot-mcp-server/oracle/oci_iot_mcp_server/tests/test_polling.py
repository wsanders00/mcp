from oracle.oci_iot_mcp_server.polling import (
    wait_for_raw_command_terminal_state,
    wait_for_snapshot_update,
)


def test_wait_for_raw_command_terminal_state_returns_latest_record_on_timeout():
    observed = [
        {
            "id": "rc-1",
            "delivery_status": "PENDING",
            "time_updated": "2026-03-26T12:00:01Z",
        }
    ]
    ticks = iter([0.0, 1.1, 1.1])

    result = wait_for_raw_command_terminal_state(
        fetch_detail=lambda _: observed[-1],
        record_id="rc-1",
        timeout_seconds=1,
        sleep=lambda _: None,
        monotonic=lambda: next(ticks),
    )

    assert result["timed_out"] is True
    assert result["raw_command"]["id"] == "rc-1"


def test_wait_for_snapshot_update_returns_first_record_after_since():
    rows = iter(
        [
            [
                {
                    "digital_twin_instance_id": "ocid1.digitaltwininstance.oc1..aaaa",
                    "content_path": "temperature",
                    "value": 71,
                    "time_observed": "2026-03-26T11:59:59Z",
                }
            ],
            [
                {
                    "digital_twin_instance_id": "ocid1.digitaltwininstance.oc1..aaaa",
                    "content_path": "temperature",
                    "value": 72,
                    "time_observed": "2026-03-26T12:00:05Z",
                }
            ],
        ]
    )
    ticks = iter([0.0, 0.2, 0.4, 2.1])

    result = wait_for_snapshot_update(
        fetch_rows=lambda: next(rows),
        since="2026-03-26T12:00:00Z",
        timeout_seconds=2,
        sleep=lambda _: None,
        monotonic=lambda: next(ticks),
    )

    assert result["content_path"] == "temperature"
    assert result["value"] == 72
