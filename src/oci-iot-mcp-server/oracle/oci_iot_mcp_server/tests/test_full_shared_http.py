"""Synthetic full-dispatch HTTP/auth context tests: no real config or OCI calls."""
import json
import time
from types import SimpleNamespace
from unittest.mock import Mock

import jwt
import pytest
from starlette.testclient import TestClient

from oracle.oci_iot_mcp_server import auth, client as clients, server
from oracle.oci_iot_mcp_server.shared_http import build_full_shared_http_app
from oracle.oci_iot_mcp_server.tests.test_shared_http import HEADERS, TOKEN, payload, rpc


@pytest.fixture
def synthetic(tmp_path, monkeypatch):
    key = tmp_path / "key.pem"
    token = tmp_path / "token"
    key.write_text("synthetic-key")
    token.write_text("synthetic-token")
    config = tmp_path / "oci-config"
    config.write_text(f"[TEST]\ntenancy=tenant-a\nuser=principal-a\nregion=us-phoenix-1\nkey_file={key}\nsecurity_token_file={token}\n")
    environment = tmp_path / "environment.toml"
    environment.write_text(f'[oci]\nconfig_file="{config}"\nresource_profile_name="TEST"\n')
    for path in [key, token, config, environment]:
        path.chmod(0o600)
    signer = SimpleNamespace(api_key="ST$" + jwt.encode({"exp": int(time.time()) + 3600}, "synthetic-key-0123456789abcdef0123456789", algorithm="HS256"))
    context = SimpleNamespace(config={"tenancy": "tenant-a", "user": "principal-a", "region": "us-phoenix-1", "key_file": str(key)}, signer=signer, tenancy_id="tenant-a", region="us-phoenix-1")
    build = Mock(return_value=context)
    monkeypatch.setattr(auth, "_build_shared_auth_context", build)
    iot = Mock()
    identity = Mock()
    monkeypatch.setattr(clients.oci.iot, "IotClient", Mock(return_value=iot))
    monkeypatch.setattr(clients.oci.identity, "IdentityClient", Mock(return_value=identity))
    original = list(server.mcp.middleware)
    yield SimpleNamespace(environment=environment, config=config, token=token, key=key, iot=iot, identity=identity, build=build)
    server.mcp.middleware[:] = original
    clients.clear_shared_clients()


def test_full_registry_uses_normal_handlers_and_authenticated_binding(synthetic, monkeypatch):
    synthetic.iot.get_iot_domain.return_value = SimpleNamespace(data=SimpleNamespace(id="domain-synthetic"))
    # Existing mutating handler, mocked at its established service boundary.
    synthetic.iot.delete_iot_domain.return_value = SimpleNamespace(status=204, headers={}, data=None)
    app = build_full_shared_http_app(server.mcp, caller_tokens={TOKEN: "client"}, environment_config=synthetic.environment, service_identity="synthetic-source-v1")
    assert synthetic.build.call_count == 1
    assert clients.get_iot_client() is synthetic.iot
    assert server.get_identity_client() == (synthetic.identity, "tenant-a")
    with TestClient(app) as http:
        assert http.get("/binding", headers=HEADERS | {"authorization": "Bearer wrong"}).status_code == 401
        binding = http.get("/binding", headers=HEADERS)
        assert binding.status_code == 200
        assert binding.json()["service_identity"] == "synthetic-source-v1"
        assert binding.json()["auth_binding"]["tenancy"] == "tenant-a"
        rpc(http, 1, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "synthetic", "version": "1"}})
        listing = payload(rpc(http, 2, "tools/list", {}))["result"]["tools"]
        assert len(listing) == 72
        read = payload(rpc(http, 3, "tools/call", {"name": "get_iot_domain", "arguments": {"iot_domain_id": "domain-synthetic"}}))["result"]
        assert not read.get("isError", False), read
        write = payload(rpc(http, 4, "tools/call", {"name": "delete_iot_domain", "arguments": {"iot_domain_id": "domain-synthetic"}}))["result"]
        assert not write.get("isError", False), write
    synthetic.iot.get_iot_domain.assert_called_once()
    synthetic.iot.delete_iot_domain.assert_called_once()
    assert synthetic.build.call_count == 1


def test_token_metadata_change_refuses_calls_and_never_reconstructs(synthetic):
    app = build_full_shared_http_app(server.mcp, caller_tokens={TOKEN: "client"}, environment_config=synthetic.environment, service_identity="synthetic")
    synthetic.token.write_text("replacement-synthetic-token")
    with pytest.raises(Exception, match="changed"):
        clients.get_iot_client()
    assert synthetic.build.call_count == 1
    with TestClient(app) as http:
        assert http.get("/binding", headers=HEADERS).status_code == 409


@pytest.mark.parametrize('edit', ['tenancy', 'user', 'region', 'token_reference', 'key_reference', 'environment_selection'])
def test_same_path_identity_reference_edits_refuse_all_cached_clients(synthetic, edit):
    clients.initialize_shared_clients(synthetic.environment)
    before = auth.resolve_shared_binding(synthetic.environment)[0]
    if edit == 'environment_selection':
        synthetic.environment.write_text(synthetic.environment.read_text().replace('TEST', 'OTHER'))
    else:
        text = synthetic.config.read_text()
        if edit in ('tenancy', 'user', 'region'):
            text = text.replace({'tenancy': 'tenant-a', 'user': 'principal-a', 'region': 'us-phoenix-1'}[edit], 'changed-synthetic')
        else:
            replacement = synthetic.key.with_name('replacement')
            replacement.write_text('replacement'); replacement.chmod(0o600)
            text = text.replace(str(synthetic.token if edit == 'token_reference' else synthetic.key), str(replacement))
        synthetic.config.write_text(text)
    for acquire in [clients.get_iot_client, server.get_identity_client]:
        with pytest.raises(auth.SharedAuthError):
            acquire()
    assert synthetic.build.call_count == 1
    if edit != 'environment_selection':
        after = auth.resolve_shared_binding(synthetic.environment)[0]
        assert after != before


@pytest.mark.parametrize('factory', ['common', 'iot', 'identity'])
def test_changes_during_each_construction_phase_refuse_start(synthetic, monkeypatch, factory):
    if factory == 'common':
        original = synthetic.build.return_value
        def change(*args):
            synthetic.token.write_text('changed-during-common')
            return original
        synthetic.build.side_effect = change
    else:
        constructor = clients.oci.iot.IotClient if factory == 'iot' else clients.oci.identity.IdentityClient
        original = constructor.return_value
        def change(*args, **kwargs):
            synthetic.token.write_text('changed-during-' + factory)
            return original
        constructor.side_effect = change
    with pytest.raises(auth.SharedAuthError, match='changed'):
        clients.initialize_shared_clients(synthetic.environment)
    assert clients.get_shared_clients() is None


def test_identity_client_is_not_lazy_and_unknown_profile_cannot_rebuild(synthetic):
    clients.initialize_shared_clients(synthetic.environment)
    assert clients.oci.identity.IdentityClient.call_count == 1
    with pytest.raises(auth.SharedAuthError, match='switch'):
        server.get_identity_client('OTHER')
    synthetic.key.write_text('changed-key')
    with pytest.raises(auth.SharedAuthError, match='changed'):
        server.get_identity_client()
    assert synthetic.build.call_count == 1
    assert clients.oci.identity.IdentityClient.call_count == 1


def test_region_and_separate_data_api_bearer_and_token_return_remain_normal(synthetic, monkeypatch):
    response = Mock(headers={'Content-Type': 'application/json'})
    response.json.return_value = {'items': [{'id': 'synthetic-data'}]}
    request = Mock(return_value=response)
    monkeypatch.setattr(server.httpx, 'get', request)
    token_handler = Mock(return_value={'synthetic_access_token': 'FAKE-NOT-A-CREDENTIAL'})
    monkeypatch.setattr(server, 'get_data_api_token_impl', token_handler)
    app = build_full_shared_http_app(server.mcp, caller_tokens={TOKEN: 'caller'}, environment_config=synthetic.environment, service_identity='synthetic')
    with TestClient(app) as http:
        rpc(http, 1, 'initialize', {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'synthetic', 'version': '1'}})
        args = {'iot_domain_group_short_id': 'group', 'iot_domain_short_id': 'domain', 'region': 'us-ashburn-1', 'access_token': 'synthetic-data-bearer'}
        data = payload(rpc(http, 2, 'tools/call', {'name': 'list_raw_data', 'arguments': args}))['result']
        assert not data.get('isError', False), data
        assert 'us-ashburn-1' in request.call_args.args[0]
        assert request.call_args.kwargs['headers']['Authorization'] == 'Bearer synthetic-data-bearer'
        assert 'ST$' not in str(request.call_args)
        returned = payload(rpc(http, 3, 'tools/call', {'name': 'get_data_api_token', 'arguments': {'iot_domain_id': 'synthetic-domain'}}))['result']
        assert 'FAKE-NOT-A-CREDENTIAL' in json.dumps(returned)
        missing = payload(rpc(http, 4, 'tools/call', {'name': 'list_raw_data', 'arguments': {k:v for k,v in args.items() if k != 'access_token'}}))['result']
        assert 'missing_access_token' in json.dumps(missing)
    assert request.call_count == 1
    token_handler.assert_called_once()


def test_full_http_rejects_bearer_host_origin_before_any_dispatch(synthetic):
    app = build_full_shared_http_app(server.mcp, caller_tokens={TOKEN: 'caller'}, environment_config=synthetic.environment, service_identity='synthetic')
    with TestClient(app) as http:
        assert http.get('/binding', headers=HEADERS | {'authorization': 'Bearer wrong'}).status_code == 401
        assert http.get('/binding', headers=HEADERS | {'host': 'external.invalid'}).status_code == 400
        assert http.get('/binding', headers=HEADERS | {'origin': 'http://external.invalid'}).status_code == 403
    synthetic.iot.get_iot_domain.assert_not_called()


def test_full_http_catalog_schema_equals_ordinary_registry(synthetic):
    import asyncio
    ordinary = [tool.to_mcp_tool().model_dump(by_alias=True, exclude_none=True)
                for tool in asyncio.run(server.mcp.list_tools())]
    app = build_full_shared_http_app(server.mcp, caller_tokens={TOKEN: 'caller'}, environment_config=synthetic.environment, service_identity='synthetic')
    with TestClient(app) as http:
        rpc(http, 1, 'initialize', {'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'synthetic','version':'1'}})
        shared = payload(rpc(http, 2, 'tools/list', {}))['result']['tools']
    assert sorted(shared, key=lambda item:item['name']) == sorted(ordinary, key=lambda item:item['name'])


@pytest.mark.parametrize('failure', ['missing_token', 'expired_token', 'common_auth_error'])
def test_unavailable_expired_auth_has_bounded_owner_guidance(synthetic, failure):
    if failure == 'missing_token':
        synthetic.token.unlink()
    elif failure == 'expired_token':
        synthetic.build.return_value.signer.api_key = 'ST$' + jwt.encode({'exp':int(time.time())-5}, 'synthetic-key-0123456789abcdef0123456789', algorithm='HS256')
    else:
        synthetic.build.side_effect = ValueError('DO-NOT-EXPOSE-SYNTHETIC-SECRET')
    with pytest.raises(auth.SharedAuthError, match='token-mgr') as caught:
        clients.initialize_shared_clients(synthetic.environment)
    assert 'DO-NOT-EXPOSE' not in str(caught.value)
    assert synthetic.build.call_count <= 1
    assert clients.get_shared_clients() is None


def test_permission_denial_remains_normal_error_without_reauthentication(synthetic):
    import oci
    synthetic.iot.delete_iot_domain.side_effect = oci.exceptions.ServiceError(403, 'NotAuthorized', {}, 'synthetic-denial')
    app = build_full_shared_http_app(server.mcp, caller_tokens={TOKEN:'caller'}, environment_config=synthetic.environment, service_identity='synthetic')
    with TestClient(app) as http:
        rpc(http,1,'initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'synthetic','version':'1'}})
        result = payload(rpc(http,2,'tools/call',{'name':'delete_iot_domain','arguments':{'iot_domain_id':'synthetic-domain'}}))['result']
    assert result['isError'] is True
    assert 'token-mgr' not in json.dumps(result)
    assert synthetic.build.call_count == 1
    synthetic.iot.delete_iot_domain.assert_called_once()
