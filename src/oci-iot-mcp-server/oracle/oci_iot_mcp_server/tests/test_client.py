from types import SimpleNamespace

import pytest

from oracle.oci_iot_mcp_server import client
from oracle.oci_iot_mcp_server import auth
from oracle.oci_iot_mcp_server import __project__, __version__


@pytest.fixture(autouse=True)
def isolated_oci_config(monkeypatch, tmp_path):
    config_file = tmp_path / "config"
    config_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("OCI_CONFIG_FILE", str(config_file))
    for name in (
        "OCI_MCP_AUTH_TYPE", "OCI_AUTH_TYPE", "ORACLE_MCP_AUTH_METHOD", "OCI_MCP_DELEGATION_TOKEN_FILE",
        "OCI_MCP_DELEGATION_TOKEN", "OCI_MCP_OKE_SERVICE_ACCOUNT_TOKEN_PATH", "OCI_MCP_OKE_SERVICE_ACCOUNT_TOKEN",
        "OCI_MCP_TENANCY_ID_OVERRIDE", "OCI_REGION", "OCI_IOT_DELEGATION_TOKEN",
        "OCI_IOT_OKE_SERVICE_ACCOUNT_TOKEN_PATH", "OCI_IOT_OKE_SERVICE_ACCOUNT_TOKEN",
        "OCI_IOT_AUTH_TYPE", "OCI_CONFIG_PROFILE", "ORACLE_MCP_AUTH_PROFILE", "TENANCY_ID_OVERRIDE",
    ):
        monkeypatch.delenv(name, raising=False)


def _expected_user_agent():
    return f"{__project__.split('oracle.', 1)[1].removesuffix('-server')}/{__version__}"


def _set_profile_token(tmp_path, monkeypatch, token_path, profiles=("DEFAULT",)):
    config_file = tmp_path / "config"
    config_file.write_text(
        "".join(f"[{profile}]\nsecurity_token_file = {token_path}\n" for profile in profiles),
        encoding="utf-8",
    )
    monkeypatch.setenv("OCI_CONFIG_FILE", str(config_file))


def test_get_iot_client_caches_per_profile(monkeypatch, tmp_path):
    key_file = tmp_path / "key.pem"
    token_file = tmp_path / "token.txt"
    key_file.write_text("private-key")
    token_file.write_text("security-token")
    _set_profile_token(tmp_path, monkeypatch, token_file, ("DEFAULT", "ALT"))

    def fake_from_file(*, profile_name, file_location=None):
        return {
            "profile_name": profile_name,
            "key_file": str(key_file),
            "security_token_file": str(token_file),
        }

    expected_user_agent = _expected_user_agent()

    monkeypatch.setattr(client.oci.config, "from_file", fake_from_file)
    monkeypatch.setattr(
        client.oci.signer,
        "load_private_key_from_file",
        lambda path, pass_phrase=None: f"pk:{path}",
    )
    monkeypatch.setattr(client.oci.auth.signers, "SecurityTokenSigner", lambda token, key: (token, key))
    monkeypatch.setattr(
        client.oci.iot,
        "IotClient",
        lambda config, signer=None: {
            "profile": config["profile_name"],
            "signer": signer,
            "user_agent": config.get("additional_user_agent"),
        },
    )

    client.clear_iot_client_cache()

    default_client = client.get_iot_client("DEFAULT")
    alt_client = client.get_iot_client("ALT")

    assert default_client["profile"] == "DEFAULT"
    assert alt_client["profile"] == "ALT"
    assert default_client["user_agent"] == expected_user_agent
    assert alt_client["user_agent"] == expected_user_agent
    assert default_client is not alt_client


def test_get_iot_client_auto_falls_back_to_api_key_when_no_security_token(monkeypatch):
    expected_user_agent = _expected_user_agent()

    monkeypatch.setenv("OCI_IOT_AUTH_TYPE", "auto")
    monkeypatch.setattr(
        client.oci.config,
        "from_file",
        lambda *, profile_name, file_location=None: {
            "profile_name": profile_name,
            "tenancy": "ocid1.tenancy.oc1..aaaa",
            "user": "ocid1.user.oc1..aaaa",
            "fingerprint": "aa:bb",
            "key_file": "/tmp/api-key.pem",
            "region": "us-ashburn-1",
        },
    )
    monkeypatch.setattr(
        client.oci.signer,
        "Signer",
        lambda **kwargs: {"kind": "api_key", "kwargs": kwargs},
    )
    monkeypatch.setattr(
        client.oci.iot,
        "IotClient",
        lambda config, signer=None: {"config": config, "signer": signer},
    )

    client.clear_iot_client_cache()

    built_client = client.get_iot_client("DEFAULT")

    assert built_client["signer"]["kind"] == "api_key"
    assert built_client["config"]["additional_user_agent"] == expected_user_agent


def test_get_iot_client_security_token_uses_private_key_pass_phrase(monkeypatch, tmp_path):
    observed = {}
    token_file = tmp_path / "token.txt"
    token_file.write_text("security-token")
    _set_profile_token(tmp_path, monkeypatch, token_file)

    monkeypatch.setenv("OCI_IOT_AUTH_TYPE", "security_token")
    monkeypatch.setattr(
        client.oci.config,
        "from_file",
        lambda *, profile_name, file_location=None: {
            "profile_name": profile_name,
            "key_file": "/tmp/encrypted-key.pem",
            "security_token_file": str(token_file),
            "pass_phrase": "top-secret",
        },
    )

    def fake_load_private_key(path, pass_phrase=None):
        observed["path"] = path
        observed["pass_phrase"] = pass_phrase
        return f"pk:{path}:{pass_phrase}"

    monkeypatch.setattr(client.oci.signer, "load_private_key_from_file", fake_load_private_key)
    monkeypatch.setattr(client.oci.auth.signers, "SecurityTokenSigner", lambda token, key: (token, key))
    monkeypatch.setattr(
        client.oci.iot,
        "IotClient",
        lambda config, signer=None: {"config": config, "signer": signer},
    )

    client.clear_iot_client_cache()

    built_client = client.get_iot_client("DEFAULT")

    assert observed == {"path": "/tmp/encrypted-key.pem", "pass_phrase": "top-secret"}
    assert built_client["signer"] == ("security-token", "pk:/tmp/encrypted-key.pem:top-secret")
    assert built_client["config"]["additional_user_agent"] == _expected_user_agent()


def test_get_iot_client_uses_instance_principal_when_configured(monkeypatch):
    signer = SimpleNamespace(
        kind="instance_principal",
        tenancy_id="ocid1.tenancy.oc1..aaaa",
        region="us-phoenix-1",
    )

    monkeypatch.setenv("OCI_IOT_AUTH_TYPE", "instance_principal")
    monkeypatch.setattr(
        client.oci.auth.signers,
        "InstancePrincipalsSecurityTokenSigner",
        lambda: signer,
    )
    monkeypatch.setattr(
        client.oci.iot,
        "IotClient",
        lambda config, signer=None: {"config": config, "signer": signer},
    )

    client.clear_iot_client_cache()

    built_client = client.get_iot_client()

    assert built_client["signer"] is signer
    assert built_client["config"]["region"] == "us-phoenix-1"
    assert built_client["config"]["additional_user_agent"] == _expected_user_agent()


def test_get_iot_client_uses_resource_principal_when_configured(monkeypatch):
    signer = SimpleNamespace(
        kind="resource_principal",
        tenancy_id="ocid1.tenancy.oc1..bbbb",
        region="us-chicago-1",
    )

    monkeypatch.setenv("OCI_IOT_AUTH_TYPE", "resource_principal")
    monkeypatch.setattr(
        client.oci.auth.signers,
        "get_resource_principals_signer",
        lambda: signer,
    )
    monkeypatch.setattr(
        client.oci.iot,
        "IotClient",
        lambda config, signer=None: {"config": config, "signer": signer},
    )

    client.clear_iot_client_cache()

    built_client = client.get_iot_client()

    assert built_client["signer"] is signer
    assert built_client["config"]["region"] == "us-chicago-1"
    assert built_client["config"]["additional_user_agent"] == _expected_user_agent()


def test_get_iot_client_uses_instance_principal_delegation_when_configured(monkeypatch):
    observed = {}
    signer = SimpleNamespace(
        kind="instance_principal_delegation",
        tenancy_id="ocid1.tenancy.oc1..delegation1",
        region="us-ashburn-1",
    )

    monkeypatch.setenv("OCI_IOT_AUTH_TYPE", "instance_principal_delegation")
    monkeypatch.setenv("OCI_IOT_DELEGATION_TOKEN", "delegation-token-123")

    def fake_instance_delegation_signer(**kwargs):
        observed.update(kwargs)
        return signer

    monkeypatch.setattr(
        client.oci.auth.signers,
        "InstancePrincipalsDelegationTokenSigner",
        fake_instance_delegation_signer,
    )
    monkeypatch.setattr(
        client.oci.iot,
        "IotClient",
        lambda config, signer=None: {"config": config, "signer": signer},
    )

    client.clear_iot_client_cache()

    built_client = client.get_iot_client()

    assert observed == {"delegation_token": "delegation-token-123"}
    assert built_client["signer"] is signer
    assert built_client["config"]["region"] == "us-ashburn-1"
    assert built_client["config"]["additional_user_agent"] == _expected_user_agent()


def test_get_iot_client_uses_resource_principal_delegation_when_configured(monkeypatch):
    observed = {}
    signer = SimpleNamespace(
        kind="resource_principal_delegation",
        tenancy_id="ocid1.tenancy.oc1..delegation2",
        region="us-sanjose-1",
    )

    monkeypatch.setenv("OCI_IOT_AUTH_TYPE", "resource_principal_delegation")
    monkeypatch.setenv("OCI_IOT_DELEGATION_TOKEN", "delegation-token-456")

    def fake_resource_delegation_signer(*, delegation_token, resource_principal_token_path_provider=None):
        observed["delegation_token"] = delegation_token
        observed["path_provider"] = resource_principal_token_path_provider
        return signer

    monkeypatch.setattr(
        client.oci.auth.signers,
        "get_resource_principal_delegation_token_signer",
        fake_resource_delegation_signer,
    )
    monkeypatch.setattr(
        client.oci.iot,
        "IotClient",
        lambda config, signer=None: {"config": config, "signer": signer},
    )

    client.clear_iot_client_cache()

    built_client = client.get_iot_client()

    assert observed == {"delegation_token": "delegation-token-456", "path_provider": None}
    assert built_client["signer"] is signer
    assert built_client["config"]["region"] == "us-sanjose-1"
    assert built_client["config"]["additional_user_agent"] == _expected_user_agent()


def test_get_iot_client_rejects_conflicting_oke_token_sources(monkeypatch):
    monkeypatch.setenv("OCI_IOT_AUTH_TYPE", "oke_workload_identity")
    monkeypatch.setenv("OCI_IOT_OKE_SERVICE_ACCOUNT_TOKEN_PATH", "/tmp/serviceaccount/token")
    monkeypatch.setenv("OCI_IOT_OKE_SERVICE_ACCOUNT_TOKEN", "inline-token")

    client.clear_iot_client_cache()

    with pytest.raises(ValueError, match="Set only OCI_MCP_OKE_SERVICE_ACCOUNT_TOKEN_PATH"):
        client.get_iot_client()


def test_get_iot_client_uses_oke_token_file_and_exact_user_agent(monkeypatch):
    observed = {}
    signer = SimpleNamespace(kind="oke_workload_identity", region="us-phoenix-1")
    monkeypatch.setenv("OCI_MCP_AUTH_TYPE", "oke_workload_identity")
    monkeypatch.setenv("OCI_MCP_OKE_SERVICE_ACCOUNT_TOKEN_PATH", "/tmp/serviceaccount/token")

    def fake_oke_signer(service_account_token_path=None, **kwargs):
        observed["path"] = service_account_token_path
        return signer

    monkeypatch.setattr(client.oci.auth.signers, "get_oke_workload_identity_resource_principal_signer", fake_oke_signer)
    monkeypatch.setattr(client.oci.iot, "IotClient", lambda config, signer=None: {"config": config, "signer": signer})

    built_client = client.get_iot_client()

    assert observed == {"path": "/tmp/serviceaccount/token"}
    assert built_client["config"]["additional_user_agent"] == _expected_user_agent()


def test_get_iot_client_cache_tracks_region_selector(monkeypatch):
    signer = SimpleNamespace(region="us-phoenix-1")
    monkeypatch.setenv("OCI_MCP_AUTH_TYPE", "instance_principal")
    monkeypatch.setenv("OCI_REGION", "us-ashburn-1")
    monkeypatch.setattr(client.oci.auth.signers, "InstancePrincipalsSecurityTokenSigner", lambda: signer)
    monkeypatch.setattr(client.oci.iot, "IotClient", lambda config, signer=None: {"config": config, "signer": signer})
    client.clear_iot_client_cache()

    first = client.get_iot_client()
    monkeypatch.setenv("OCI_REGION", "us-chicago-1")
    second = client.get_iot_client()

    assert first is not second
    assert first["config"]["region"] == "us-ashburn-1"
    assert second["config"]["region"] == "us-chicago-1"


@pytest.mark.parametrize(
    "auth_type",
    [
        "instance_principal_delegation",
        "resource_principal_delegation",
    ],
)
def test_get_iot_client_requires_delegation_token_for_delegation_modes(monkeypatch, auth_type):
    monkeypatch.setenv("OCI_IOT_AUTH_TYPE", auth_type)
    monkeypatch.delenv("OCI_IOT_DELEGATION_TOKEN", raising=False)
    client.clear_iot_client_cache()

    with pytest.raises(ValueError, match="OCI_MCP_DELEGATION_TOKEN_FILE"):
        client.get_iot_client()


def test_get_iot_client_rejects_unknown_auth_type(monkeypatch):
    monkeypatch.setenv("OCI_IOT_AUTH_TYPE", "not-a-real-auth-mode")
    client.clear_iot_client_cache()

    with pytest.raises(ValueError, match="Unsupported OCI authentication type"):
        client.get_iot_client("DEFAULT")


def test_auth_mode_precedence_and_iot_supported_boundary(monkeypatch):
    monkeypatch.setenv("OCI_MCP_AUTH_TYPE", "api_key")
    monkeypatch.setenv("OCI_IOT_AUTH_TYPE", "instance_principal")

    assert auth.resolved_auth_type() == "api_key"
    assert auth.resolved_auth_type("resource-principal") == "resource_principal"
    with pytest.raises(ValueError, match="Supported values:.*oke_workload_identity"):
        auth.resolved_auth_type("identity_domain_upst")


def test_security_token_requires_selected_profile_declaration(monkeypatch, tmp_path):
    token_file = tmp_path / "token.txt"
    token_file.write_text("token", encoding="utf-8")
    config_file = tmp_path / "config"
    config_file.write_text(
        f"[DEFAULT]\nsecurity_token_file = {token_file}\n[ALT]\nuser = ocid1.user.oc1..test\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OCI_CONFIG_FILE", str(config_file))
    monkeypatch.setenv("OCI_MCP_AUTH_TYPE", "security_token")
    monkeypatch.setattr(
        client.oci.config,
        "from_file",
        lambda *, file_location=None, profile_name=None: {
            "key_file": "/tmp/key.pem",
            "security_token_file": str(token_file),
        },
    )

    with pytest.raises(ValueError, match="declared directly in the selected OCI_CONFIG_PROFILE"):
        auth.build_auth_context(profile_name="ALT")


def test_iot_data_region_profile_lookup_does_not_construct_signer(monkeypatch):
    monkeypatch.setattr(
        auth.oci.config,
        "from_file",
        lambda *, file_location=None, profile_name=None: {"region": "us-ashburn-1"},
    )
    monkeypatch.setattr(client.oci.signer, "Signer", lambda **kwargs: pytest.fail("signer must not be built"))

    assert auth.get_default_region() == "us-ashburn-1"
