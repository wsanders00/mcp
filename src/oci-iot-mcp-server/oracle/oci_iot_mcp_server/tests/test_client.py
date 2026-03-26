from oracle.oci_iot_mcp_server import client
from oracle.oci_iot_mcp_server import __project__, __version__


def test_get_iot_client_caches_per_profile(monkeypatch, tmp_path):
    key_file = tmp_path / "key.pem"
    token_file = tmp_path / "token.txt"
    key_file.write_text("private-key")
    token_file.write_text("security-token")

    def fake_from_file(*, profile_name):
        return {
            "profile_name": profile_name,
            "key_file": str(key_file),
            "security_token_file": str(token_file),
        }

    expected_user_agent = f"{__project__.split('oracle.', 1)[1].split('-server', 1)[0]}/{__version__}"

    monkeypatch.setattr(client.oci.config, "from_file", fake_from_file)
    monkeypatch.setattr(client.oci.signer, "load_private_key_from_file", lambda path: f"pk:{path}")
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
