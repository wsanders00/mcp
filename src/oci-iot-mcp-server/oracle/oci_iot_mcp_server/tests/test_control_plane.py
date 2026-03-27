from types import SimpleNamespace

from oracle.oci_iot_mcp_server import server
from oracle.oci_iot_mcp_server.control_plane import (
    map_digital_twin_adapter,
    map_digital_twin_instance,
    map_iot_domain,
    map_iot_domain_group,
)


def test_map_iot_domain_includes_device_host_and_identity_domain_host():
    model = SimpleNamespace(
        id="ocid1.iotdomain.oc1..aaaa",
        display_name="factory-domain",
        device_host="abc123.device.iot.us-phoenix-1.oci.oraclecloud.com",
        db_allowed_identity_domain_host="id.example.com",
    )

    result = map_iot_domain(model)

    assert result["device_host"] == "abc123.device.iot.us-phoenix-1.oci.oraclecloud.com"
    assert result["db_allowed_identity_domain_host"] == "id.example.com"


def test_map_iot_domain_group_includes_data_host_and_db_token_scope():
    model = SimpleNamespace(
        id="ocid1.iotdomaingroup.oc1..aaaa",
        display_name="factory-group",
        data_host="xyz987.data.iot.us-phoenix-1.oci.oraclecloud.com",
        db_token_scope="ignored-by-ords-but-exposed",
    )

    result = map_iot_domain_group(model)

    assert result["data_host"].startswith("xyz987.data.iot.")
    assert result["db_token_scope"] == "ignored-by-ords-but-exposed"


def test_map_digital_twin_instance_includes_iot_domain_and_adapter_ids():
    model = SimpleNamespace(
        id="ocid1.digitaltwininstance.oc1..aaaa",
        display_name="pump-01",
        iot_domain_id="ocid1.iotdomain.oc1..aaaa",
        digital_twin_adapter_id="ocid1.digitaltwinadapter.oc1..aaaa",
    )

    result = map_digital_twin_instance(model)

    assert result["iot_domain_id"] == "ocid1.iotdomain.oc1..aaaa"
    assert result["digital_twin_adapter_id"] == "ocid1.digitaltwinadapter.oc1..aaaa"


def test_map_digital_twin_adapter_includes_model_spec_and_routes():
    model = SimpleNamespace(
        id="ocid1.digitaltwinadapter.oc1..aaaa",
        display_name="pump-adapter",
        digital_twin_model_id="ocid1.digitaltwinmodel.oc1..aaaa",
        digital_twin_model_spec_uri="https://example.com/spec.json",
        inbound_envelope={"type": "JSON"},
        inbound_routes=[{"messageType": "telemetry"}],
    )

    result = map_digital_twin_adapter(model)

    assert result["digital_twin_model_id"] == "ocid1.digitaltwinmodel.oc1..aaaa"
    assert result["digital_twin_model_spec_uri"] == "https://example.com/spec.json"
    assert result["inbound_routes"] == [{"messageType": "telemetry"}]


def test_server_get_iot_domain_delegates_to_control_plane(monkeypatch):
    monkeypatch.setattr(
        server,
        "get_iot_domain_record",
        lambda iot_domain_id: {
            "id": iot_domain_id,
            "device_host": "abc123.device.iot.us-phoenix-1.oci.oraclecloud.com",
        },
    )

    result = server.get_iot_domain("ocid1.iotdomain.oc1..aaaa")

    assert result["id"] == "ocid1.iotdomain.oc1..aaaa"
    assert result["device_host"].startswith("abc123.device.iot.")
