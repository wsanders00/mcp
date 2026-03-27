from datetime import UTC, datetime

from oracle.oci_iot_mcp_server import server
from oracle.oci_iot_mcp_server.tool_models import DataApiTokenModel


def test_get_digital_twin_adapter_full_wraps_full_adapter_record(monkeypatch):
    monkeypatch.setattr(
        server,
        "get_digital_twin_adapter_record",
        lambda digital_twin_adapter_id: {
            "id": digital_twin_adapter_id,
            "digital_twin_model_id": "ocid1.digitaltwinmodel.oc1..aaaa",
            "digital_twin_model_spec_uri": "https://example.com/spec.json",
            "inbound_routes": [{"messageType": "telemetry"}],
        },
    )

    result = server.get_digital_twin_adapter_full("ocid1.digitaltwinadapter.oc1..aaaa")

    assert result["ok"] is True
    assert result["data"]["digital_twin_model_id"] == "ocid1.digitaltwinmodel.oc1..aaaa"


def test_derive_domain_context_returns_success_envelope(monkeypatch):
    monkeypatch.setattr(
        server,
        "resolve_domain_context_for_tool",
        lambda **_: {
            "iot_domain_id": "domain-ocid",
            "domain_short_id": "abc123",
            "region": "us-phoenix-1",
        },
    )

    result = server.derive_domain_context(iot_domain_id="domain-ocid")

    assert result == {
        "ok": True,
        "data": {
            "iot_domain_id": "domain-ocid",
            "domain_short_id": "abc123",
            "region": "us-phoenix-1",
        },
    }


def test_get_data_api_token_passes_through_structured_configuration_error(monkeypatch):
    monkeypatch.setattr(
        server,
        "get_data_api_token_impl",
        lambda **_: {
            "ok": False,
            "error": {
                "code": "missing_token_credentials",
                "message": "Missing one or more OCI IoT ORDS credential environment variables.",
            },
        },
    )

    result = server.get_data_api_token(iot_domain_id="domain-ocid")

    assert result["ok"] is False
    assert result["error"]["code"] == "missing_token_credentials"


def test_get_data_api_token_wraps_success_payload(monkeypatch):
    monkeypatch.setattr(
        server,
        "get_data_api_token_impl",
        lambda **_: {
            "access_token": "token-123",
            "token_type": "Bearer",
            "expires_at": "2026-03-26T13:00:00Z",
            "expires_in": 3600,
            "iot_domain_id": "domain-ocid",
        },
    )

    result = server.get_data_api_token(iot_domain_id="domain-ocid")

    assert result["ok"] is True
    assert result["data"]["access_token"] == "token-123"
    assert result["data"]["expires_at"] == "2026-03-26T13:00:00Z"


def test_get_data_api_token_serializes_nested_pydantic_payload(monkeypatch):
    monkeypatch.setattr(
        server,
        "get_data_api_token_impl",
        lambda **_: {
            "token": DataApiTokenModel(
                access_token="token-123",
                token_type="Bearer",
                expires_in=3600,
                expires_at=datetime(2026, 3, 26, 13, 0, 0, tzinfo=UTC),
            ),
            "iot_domain_id": "domain-ocid",
        },
    )

    result = server.get_data_api_token(iot_domain_id="domain-ocid")

    assert result["ok"] is True
    assert result["data"]["token"]["expires_at"] == "2026-03-26T13:00:00Z"


def test_get_raw_command_by_request_id_wraps_detail_record(monkeypatch):
    monkeypatch.setattr(
        server,
        "get_raw_command_by_request_id_impl",
        lambda **_: {
            "id": "rc-1",
            "digital_twin_instance_id": "ocid1.digitaltwininstance.oc1..aaaa",
            "delivery_status": "COMPLETED",
        },
    )

    result = server.get_raw_command_by_request_id(
        request_id="rc-1",
        digital_twin_instance_id="ocid1.digitaltwininstance.oc1..aaaa",
    )

    assert result["ok"] is True
    assert result["data"]["id"] == "rc-1"


def test_list_recent_raw_commands_for_twin_sorts_by_time_created_desc(monkeypatch):
    monkeypatch.setattr(
        server,
        "list_recent_raw_commands_for_twin_impl",
        lambda **_: [
            {"id": "rc-older", "time_created": "2026-03-26T11:59:59Z"},
            {"id": "rc-newer", "time_created": "2026-03-26T12:00:01Z"},
        ],
    )

    result = server.list_recent_raw_commands_for_twin(
        digital_twin_instance_id="ocid1.digitaltwininstance.oc1..aaaa",
        limit=20,
    )

    assert result["ok"] is True
    assert result["data"][0]["id"] == "rc-newer"


def test_list_recent_raw_commands_for_twin_rejects_limit_above_100():
    result = server.list_recent_raw_commands_for_twin(
        digital_twin_instance_id="ocid1.digitaltwininstance.oc1..aaaa",
        limit=101,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_input"


def test_invoke_raw_command_and_wait_wraps_terminal_record(monkeypatch):
    monkeypatch.setattr(
        server,
        "invoke_raw_command_and_wait_impl",
        lambda **_: {
            "request_id": "rc-1",
            "timed_out": False,
            "raw_command": {"id": "rc-1", "delivery_status": "COMPLETED"},
        },
    )

    result = server.invoke_raw_command_and_wait(
        digital_twin_instance_id="ocid1.digitaltwininstance.oc1..aaaa",
        request_endpoint="/v1/cmd",
        request_data_format="TEXT",
        request_data="PING",
        timeout=30,
    )

    assert result["ok"] is True
    assert result["data"]["request_id"] == "rc-1"
    assert result["data"]["raw_command"]["delivery_status"] == "COMPLETED"


def test_invoke_raw_command_and_wait_passes_through_recoverable_error(monkeypatch):
    monkeypatch.setattr(
        server,
        "invoke_raw_command_and_wait_impl",
        lambda **_: {
            "ok": False,
            "error": {
                "code": "ambiguous_identifier",
                "message": "Multiple raw command records matched the invoke request.",
            },
        },
    )

    result = server.invoke_raw_command_and_wait(
        digital_twin_instance_id="ocid1.digitaltwininstance.oc1..aaaa",
        request_endpoint="/v1/cmd",
        request_data_format="TEXT",
        request_data="PING",
        timeout=30,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "ambiguous_identifier"
