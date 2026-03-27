import pytest

from oracle.oci_iot_mcp_server.domain_context import derive_domain_context


def test_derive_domain_context_parses_short_ids_and_region():
    payload = derive_domain_context(
        iot_domain={
            "id": "domain-ocid",
            "name": "factory",
            "device_host": "abc123.device.iot.us-phoenix-1.oci.oraclecloud.com",
        },
        iot_domain_group={
            "id": "group-ocid",
            "name": "factory-group",
            "data_host": "xyz987.data.iot.us-phoenix-1.oci.oraclecloud.com",
            "db_token_scope": "dbscope",
        },
    )

    assert payload.domain_short_id == "abc123"
    assert payload.domain_group_short_id == "xyz987"
    assert payload.region == "us-phoenix-1"


def test_derive_domain_context_rejects_mismatched_regions():
    with pytest.raises(ValueError, match="share the same OCI region"):
        derive_domain_context(
            iot_domain={
                "id": "domain-ocid",
                "name": "factory",
                "device_host": "abc123.device.iot.us-phoenix-1.oci.oraclecloud.com",
            },
            iot_domain_group={
                "id": "group-ocid",
                "name": "factory-group",
                "data_host": "xyz987.data.iot.us-ashburn-1.oci.oraclecloud.com",
            },
        )
