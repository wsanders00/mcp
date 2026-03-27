from datetime import UTC, datetime

import oracle.oci_iot_mcp_server.data_plane as data_plane
from oracle.oci_iot_mcp_server.data_plane import (
    build_ords_base_url,
    build_twin_filter,
    encode_q,
    list_collection_records,
    mint_data_api_token,
    require_token_credentials,
)


def test_build_ords_base_url_uses_domain_group_host_and_domain_short_id():
    result = build_ords_base_url(
        {
            "data_host": "xyz987.data.iot.us-phoenix-1.oci.oraclecloud.com",
            "domain_short_id": "abc123",
        }
    )

    assert result == "https://xyz987.data.iot.us-phoenix-1.oci.oraclecloud.com/ords/abc123/20250531"


def test_mint_data_api_token_uses_password_grant_and_scope(monkeypatch):
    class FakeResponse:
        def json(self):
            return {"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600}

    monkeypatch.setattr(data_plane.httpx, "post", lambda *args, **kwargs: FakeResponse())

    context = {
        "domain_short_id": "abc123",
        "domain_group_short_id": "xyz987",
        "db_allowed_identity_domain_host": "id.example.com",
    }

    result = mint_data_api_token(
        domain_context=context,
        env={
            "OCI_IOT_ORDS_CLIENT_ID": "client-id",
            "OCI_IOT_ORDS_CLIENT_SECRET": "client-secret",
            "OCI_IOT_ORDS_USERNAME": "iot.user@example.com",
            "OCI_IOT_ORDS_PASSWORD": "secret-password",
        },
        now=lambda: datetime(2026, 3, 26, 12, 0, 0, tzinfo=UTC),
    )

    assert result.access_token == "token-123"
    assert result.expires_at.isoformat() == "2026-03-26T13:00:00+00:00"
    assert build_twin_filter("ocid1.digitaltwininstance.oc1..aaaa") == {
        "$and": [{"digital_twin_instance_id": "ocid1.digitaltwininstance.oc1..aaaa"}]
    }
    assert encode_q(build_twin_filter("ocid1.digitaltwininstance.oc1..aaaa")) == (
        '{"$and":[{"digital_twin_instance_id":"ocid1.digitaltwininstance.oc1..aaaa"}]}'
    )


def test_require_token_credentials_returns_structured_error_for_missing_env():
    result = require_token_credentials({"OCI_IOT_ORDS_CLIENT_ID": "client-id"})

    assert result["ok"] is False
    assert result["error"]["code"] == "missing_token_credentials"
    assert result["error"]["details"]["missing"] == [
        "OCI_IOT_ORDS_CLIENT_SECRET",
        "OCI_IOT_ORDS_USERNAME",
        "OCI_IOT_ORDS_PASSWORD",
    ]


def test_require_token_credentials_returns_sanitized_success_payload():
    result = require_token_credentials(
        {
            "OCI_IOT_ORDS_CLIENT_ID": "client-id",
            "OCI_IOT_ORDS_CLIENT_SECRET": "client-secret",
            "OCI_IOT_ORDS_USERNAME": "iot.user@example.com",
            "OCI_IOT_ORDS_PASSWORD": "secret-password",
        }
    )

    assert result == {
        "ok": True,
        "data": {
            "present": [
                "OCI_IOT_ORDS_CLIENT_ID",
                "OCI_IOT_ORDS_CLIENT_SECRET",
                "OCI_IOT_ORDS_USERNAME",
                "OCI_IOT_ORDS_PASSWORD",
            ],
            "missing": [],
        },
    }


def test_list_collection_records_uses_limit_offset_until_target_count(monkeypatch):
    observed_params = []
    pages = iter(
        [
            {"items": [{"id": "1"}, {"id": "2"}]},
            {"items": [{"id": "3"}]},
        ]
    )

    monkeypatch.setattr(
        data_plane,
        "_get_json",
        lambda **kwargs: observed_params.append(kwargs["params"]) or next(pages),
    )

    records = list_collection_records(
        base_url="https://xyz987.data.iot.us-phoenix-1.oci.oraclecloud.com/ords/abc123/20250531",
        path="/rawCommandData",
        token="token-123",
        params={"q": '{"$and":[{"digital_twin_instance_id":"ocid1.digitaltwininstance.oc1..aaaa"}]}'},
        target_count=3,
    )

    assert [record["id"] for record in records] == ["1", "2", "3"]
    assert observed_params == [
        {
            "q": '{"$and":[{"digital_twin_instance_id":"ocid1.digitaltwininstance.oc1..aaaa"}]}',
            "limit": 3,
            "offset": 0,
        },
        {
            "q": '{"$and":[{"digital_twin_instance_id":"ocid1.digitaltwininstance.oc1..aaaa"}]}',
            "limit": 3,
            "offset": 2,
        },
    ]
