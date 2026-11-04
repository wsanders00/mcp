"""Synthetic key/token files exercise Common's actual signer without OCI traffic."""
import time
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from oracle.oci_iot_mcp_server import client


def test_real_common_security_token_constructs_one_actual_sdk_pair_without_network(tmp_path, monkeypatch):
    private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    key=tmp_path/'key.pem';key.write_bytes(private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    token=tmp_path/'token';token.write_text(jwt.encode({'exp':int(time.time())+3600},private,algorithm='RS256'))
    config=tmp_path/'config';config.write_text(f'[TEST]\ntenancy=ocid1.tenancy.oc1..synthetic\nuser=ocid1.user.oc1..synthetic\nfingerprint=00:00:00:00\nregion=us-phoenix-1\nkey_file={key}\nsecurity_token_file={token}\n')
    environment=tmp_path/'complete.toml';environment.write_text(f'[oci]\nconfig_file="{config}"\nresource_profile_name="TEST"\n')
    for p in [key,token,config,environment]:
        p.chmod(0o600)
    monkeypatch.setattr(client.oci.base_client.BaseClient,'call_api',lambda *a,**k: (_ for _ in ()).throw(AssertionError('network forbidden')))
    try:
        pair=client.initialize_shared_clients(environment)
        assert pair.iot.base_client.signer is pair.identity_client.base_client.signer is pair.signer
        assert pair.identity['principal']=='ocid1.user.oc1..synthetic'
        assert pair.config['additional_user_agent'].startswith('oci-iot-mcp/')
    finally:
        client.clear_shared_clients()
