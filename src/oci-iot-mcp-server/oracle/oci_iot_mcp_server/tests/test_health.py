import oracle.oci_iot_mcp_server.health as health


def test_health_check_uses_imported_version_constant(monkeypatch):
    monkeypatch.setattr(health, "__version__", "9.9.9", raising=False)
    assert health.health_check()["version"] == "9.9.9"
