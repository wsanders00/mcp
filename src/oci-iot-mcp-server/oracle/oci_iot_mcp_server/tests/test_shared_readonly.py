"""Offline tests for policy-bound shared read-only mode."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import mcp.types as mt
from starlette.testclient import TestClient
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import MiddlewareContext

from oracle.oci_iot_mcp_server import server
from oracle.oci_iot_mcp_server.shared_http import build_shared_readonly_http_app
from oracle.oci_iot_mcp_server.shared_readonly import (
    ENABLED_TOOLS,
    ReadPolicy,
    RestrictedIoTReader,
    SharedReadOnlyMiddleware,
    derived_user_agent,
    _CALLER,
    load_read_policy,
)

TOKEN = "t" * 48
TOKEN_TWO = "u" * 48
POLICY = ReadPolicy(
    region="us-test-1", profile="test-profile", config_file=None,
    auth_tenancy_id="tenancy-id", credential_generation="generation-1",
    iot_domain_id="domain-id", iot_domain_group_id="group-id",
    compartment_id="compartment-id", model_ids=frozenset({"model-id"}),
    allowed_callers=frozenset({"allowed-caller", "second-caller"}),
)
HEADERS = {
    "host": "127.0.0.1:8765", "authorization": f"Bearer {TOKEN}",
    "content-type": "application/json", "accept": "application/json, text/event-stream",
}


def rpc(client, request_id, method, params):
    return client.post("/mcp", headers=HEADERS, json={
        "jsonrpc": "2.0", "id": request_id, "method": method, "params": params,
    })


def payload(response):
    if response.headers.get("content-type", "").startswith("application/json"):
        return response.json()
    return next(json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: "))


def make_app(callers=("allowed-caller", "second-caller")):
    original = list(server.mcp.middleware)
    app = build_shared_readonly_http_app(
        server.mcp, caller_tokens={TOKEN: callers[0], TOKEN_TWO: callers[1]}, policy=POLICY,
    )
    middleware = next(item for item in server.mcp.middleware if isinstance(item, SharedReadOnlyMiddleware))
    return app, middleware, original


def initialize(client):
    response = rpc(client, 1, "initialize", {
        "protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": "readonly-test", "version": "1"},
    })
    assert response.status_code == 200, response.text


def test_health_lists_only_two_enabled_calls_and_nonallowed_calls_are_denied(monkeypatch):
    app, middleware, original = make_app()
    called = []
    monkeypatch.setattr(middleware.reader, "get_domain", lambda value: called.append(value) or {"id": value})
    monkeypatch.setattr(middleware.reader, "get_model", lambda value: called.append(value) or {"id": value})
    try:
        with TestClient(app) as client:
            assert client.get("/healthz", headers=HEADERS).json() == {
                "cloud_access": "read_only", "tool_count": 72, "enabled_tools": ENABLED_TOOLS,
            }
            initialize(client)
            names = ["get_iot_domain", "get_digital_twin_model", "delete_iot_domain", "unknown"]
            listed = payload(rpc(client, 2, "tools/list", {}))["result"]["tools"]
            assert len(listed) == 72
            for index, name in enumerate(names, 3):
                args = ({"iot_domain_id": "domain-id"} if name == "get_iot_domain"
                        else {"digital_twin_model_id": "model-id"} if name == "get_digital_twin_model" else {})
                result = payload(rpc(client, index, "tools/call", {"name": name, "arguments": args}))
                if name in ENABLED_TOOLS:
                    assert result["result"]["structuredContent"]["id"] == args.get("iot_domain_id", args.get("digital_twin_model_id"))
                else:
                    assert result["result"]["isError"] is True
            bad = payload(rpc(client, 8, "tools/call", {
                "name": "get_iot_domain", "arguments": {"iot_domain_id": "other", "extra": True},
            }))
            assert bad["result"]["isError"] is True
            assert called == ["domain-id", "model-id"]
    finally:
        server.mcp.middleware[:] = original


def test_caller_allowlist_and_bearer_auth_precede_tool_dispatch(monkeypatch):
    app, middleware, original = make_app()
    monkeypatch.setattr(middleware.reader, "get_domain", lambda value: {"id": value})
    try:
        with TestClient(app) as client:
            assert client.get("/healthz").status_code == 400
            assert client.get("/healthz", headers={
                "host": HEADERS["host"], "authorization": "Bearer " + "x" * 48,
            }).status_code == 401
            assert client.get("/healthz", headers=HEADERS).status_code == 200
            initialize(client)
            result = payload(rpc(client, 2, "tools/call", {
                "name": "get_iot_domain", "arguments": {"iot_domain_id": "domain-id"},
            }))
            assert result["result"]["structuredContent"]["id"] == "domain-id"
    finally:
        server.mcp.middleware[:] = original


def test_unlisted_context_caller_is_denied_before_reader_dispatch(monkeypatch):
    app, middleware, original = make_app()
    monkeypatch.setattr(middleware.reader, "get_domain", lambda value: pytest.fail("unexpected dispatch"))

    async def invoke():
        marker = _CALLER.set("third-caller")
        try:
            message = mt.CallToolRequestParams(name="get_iot_domain", arguments={"iot_domain_id": "domain-id"})
            await middleware.on_call_tool(MiddlewareContext(message=message), lambda _: None)
        finally:
            _CALLER.reset(marker)

    try:
        with pytest.raises(ToolError, match="Caller is not authorized"):
            asyncio.run(invoke())
    finally:
        server.mcp.middleware[:] = original


def test_policy_loader_requires_private_policy_config_and_credentials(tmp_path):
    config = tmp_path / "oci-config"
    token = tmp_path / "token"
    key = tmp_path / "key"
    config.write_text(f"[test-profile]\nsecurity_token_file={token}\nkey_file={key}\n")
    config.chmod(0o600)
    token.write_text("synthetic-token")
    token.chmod(0o600)
    key.write_text("synthetic-key")
    key.chmod(0o600)
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({
        "version": 1, "region": "us-test-1", "profile": "test-profile",
        "config_file": str(config), "auth_tenancy_id": "tenancy-id",
        "credential_generation": "test-generation", "iot_domain_id": "domain-id",
        "iot_domain_group_id": "group-id", "compartment_id": "compartment-id",
        "model_ids": ["model-id"], "allowed_callers": ["allowed-caller", "second-caller"],
    }))
    policy.chmod(0o600)
    loaded = load_read_policy(policy)
    assert loaded.model_ids == frozenset({"model-id"})
    policy.chmod(0o644)
    with pytest.raises(RuntimeError, match="^shared_readonly_configuration_invalid$"):
        load_read_policy(policy)

    policy.chmod(0o600)
    values = json.loads(policy.read_text())
    values["model_ids"].append("extra-model")
    policy.write_text(json.dumps(values))
    policy.chmod(0o600)
    with pytest.raises(RuntimeError, match="^shared_readonly_configuration_invalid$"):
        load_read_policy(policy)

    values["model_ids"] = ["model-id"]
    values["allowed_callers"].append("third-caller")
    policy.write_text(json.dumps(values))
    policy.chmod(0o600)
    with pytest.raises(RuntimeError, match="^shared_readonly_configuration_invalid$"):
        load_read_policy(policy)



def test_policy_loader_rejects_relative_and_tilde_paths(tmp_path, monkeypatch):
    config_dir = tmp_path / "config-dir"
    config_dir.mkdir()
    token = config_dir / "relative-token"
    token.write_text("synthetic-token")
    token.chmod(0o600)
    key = config_dir / "relative-key"
    key.write_text("synthetic-key")
    key.chmod(0o600)
    config = config_dir / "oci-config"
    config.write_text("[test-profile]\nsecurity_token_file=relative-token\nkey_file=relative-key\n")
    config.chmod(0o600)
    policy_path = tmp_path / "policy.json"
    values = {
        "version": 1, "region": "us-test-1", "profile": "test-profile",
        "config_file": str(config), "auth_tenancy_id": "tenancy-id",
        "credential_generation": "generation", "iot_domain_id": "domain-id",
        "iot_domain_group_id": "group-id", "compartment_id": "compartment-id",
        "model_ids": ["model-id"], "allowed_callers": ["allowed-caller", "second-caller"],
    }
    policy_path.write_text(json.dumps(values))
    policy_path.chmod(0o600)
    working_dir = tmp_path / "working-directory"
    working_dir.mkdir()
    (working_dir / "relative-token").write_text("cwd-canary-token")
    (working_dir / "relative-token").chmod(0o600)
    (working_dir / "relative-key").write_text("cwd-canary-key")
    (working_dir / "relative-key").chmod(0o600)
    config.write_text(f"[test-profile]\nsecurity_token_file={token}\nkey_file={key}\n")
    config.chmod(0o600)
    monkeypatch.chdir(working_dir)

    for field, relative in (
        ("config_file", "../config-dir/oci-config"),
        ("config_file", "~/oci-config"),
        ("token_file", "relative-token"),
        ("key_file", "relative-key"),
    ):
        candidate = dict(values)
        if field == "config_file":
            candidate["config_file"] = relative
            if relative.startswith("~"):
                tilde_file = working_dir / relative
                tilde_file.parent.mkdir(parents=True, exist_ok=True)
                tilde_file.write_text(f"[test-profile]\nsecurity_token_file={token}\nkey_file={key}\n")
                tilde_file.chmod(0o600)
        else:
            config.write_text(
                "[test-profile]\n"
                + (f"security_token_file={relative}\n" if field == "token_file" else f"security_token_file={token}\n")
                + (f"key_file={relative}\n" if field == "key_file" else f"key_file={key}\n")
            )
            config.chmod(0o600)
        policy_path.write_text(json.dumps(candidate))
        policy_path.chmod(0o600)
        with pytest.raises(RuntimeError, match="^shared_readonly_configuration_invalid$"):
            load_read_policy(policy_path)

    config.write_text(f"[test-profile]\nsecurity_token_file={token}\nkey_file={key}\n")
    config.chmod(0o600)
    values["config_file"] = str(config)
    policy_path.write_text(json.dumps(values))
    policy_path.chmod(0o600)
    assert load_read_policy(policy_path).config_file == config


def test_policy_loader_preserves_private_config_and_credential_file_guards(tmp_path, monkeypatch):
    import os

    token = tmp_path / "token"
    token.write_text("synthetic-token")
    token.chmod(0o600)
    key = tmp_path / "key"
    key.write_text("synthetic-key")
    key.chmod(0o600)
    config = tmp_path / "oci-config"
    policy_path = tmp_path / "policy.json"
    values = {
        "version": 1, "region": "us-test-1", "profile": "test-profile",
        "config_file": str(config), "auth_tenancy_id": "tenancy-id",
        "credential_generation": "generation", "iot_domain_id": "domain-id",
        "iot_domain_group_id": "group-id", "compartment_id": "compartment-id",
        "model_ids": ["model-id"], "allowed_callers": ["allowed-caller", "second-caller"],
    }

    def write_config(token_path=token, key_path=key):
        config.write_text(
            f"[test-profile]\nsecurity_token_file={token_path}\nkey_file={key_path}\n"
        )
        config.chmod(0o600)
        policy_path.write_text(json.dumps(values))
        policy_path.chmod(0o600)

    def assert_rejected():
        with pytest.raises(RuntimeError, match="^shared_readonly_configuration_invalid$"):
            load_read_policy(policy_path)

    write_config()
    assert load_read_policy(policy_path).profile == "test-profile"
    for path in (config, token, key):
        original_mode = path.stat().st_mode & 0o777
        path.chmod(0o644)
        assert_rejected()
        path.chmod(original_mode)

    for name, target, config_path, token_path, key_path in (
        ("config-link", config, None, token, key),
        ("token-link", token, config, None, key),
        ("key-link", key, config, token, None),
    ):
        alias = tmp_path / name
        alias.symlink_to(target)
        if config_path is None:
            values["config_file"] = str(alias)
            write_config()
        elif token_path is None:
            write_config(token_path=alias)
        else:
            write_config(key_path=alias)
        assert_rejected()
        alias.unlink()
        values["config_file"] = str(config)

    write_config()
    real_uid = os.getuid()
    with monkeypatch.context() as context:
        context.setattr(os, "getuid", lambda: real_uid + 1)
        assert_rejected()

def test_startup_requires_exact_two_caller_mapping_and_rejects_extra_caller():
    original = list(server.mcp.middleware)
    with pytest.raises(ValueError, match="^shared_readonly_configuration_invalid$"):
        build_shared_readonly_http_app(
            server.mcp,
            caller_tokens={TOKEN: "allowed-caller", TOKEN_TWO: "second-caller", "v" * 48: "third-caller"},
            policy=POLICY,
        )
    with pytest.raises(ValueError, match="^shared_readonly_configuration_invalid$"):
        build_shared_readonly_http_app(
            server.mcp,
            caller_tokens={TOKEN: "allowed-caller", TOKEN_TWO: "not-the-policy-caller"},
            policy=POLICY,
        )
    assert server.mcp.middleware == original


def test_client_uses_exact_auth_user_agent_and_guarded_get(monkeypatch):
    signer = SimpleNamespace(api_key="ST$synthetic")
    auth = SimpleNamespace(tenancy_id="tenancy-id", region="us-test-1", signer=signer, config={})

    class Session:
        trust_env = True
        verify = False

        def request(self, method, url, **kwargs):
            self.last = (method, url, kwargs)
            return "ok"

    class Client:
        def __init__(self, config, **kwargs):
            self.config = config
            self.kwargs = kwargs
            self.base_client = SimpleNamespace(session=Session())

        def get_iot_domain(self, domain_id, **kwargs):
            self.base_client.session.request(
                "GET", f"https://iot.us-test-1.oci.oraclecloud.com/20250531/iotDomains/{domain_id}",
            )
            return SimpleNamespace(data=SimpleNamespace(
                id=domain_id, iot_domain_group_id="group-id", compartment_id="compartment-id",
            ))

    monkeypatch.setattr("oracle.oci_iot_mcp_server.shared_readonly.build_auth_context", lambda options: auth)
    monkeypatch.setattr("oracle.oci_iot_mcp_server.shared_readonly.oci.iot.IotClient", Client)
    monkeypatch.setattr("oracle.oci_iot_mcp_server.shared_readonly.jwt.decode", lambda *a, **k: {"exp": (datetime.now(UTC) + timedelta(hours=1)).timestamp()})
    reader = RestrictedIoTReader(POLICY)
    result = reader.get_domain("domain-id")
    assert result.id == "domain-id"
    assert reader._client.config["additional_user_agent"] == derived_user_agent()
    assert reader._client.base_client.session.trust_env is False
    assert reader._client.base_client.session.verify is True
    with pytest.raises(RuntimeError, match="readonly_request_rejected"):
        reader._client.base_client.session.request("POST", "https://iot.us-test-1.oci.oraclecloud.com/20250531/iotDomains/domain-id")
    with pytest.raises(RuntimeError, match="readonly_request_rejected"):
        reader._client.base_client.session.request("GET", "https://attacker.invalid/20250531/iotDomains/domain-id")


def test_expired_token_and_mismatched_response_are_blocked(monkeypatch):
    signer = SimpleNamespace(api_key="ST$synthetic")
    auth = SimpleNamespace(tenancy_id="tenancy-id", region="us-test-1", signer=signer, config={})

    class Session:
        def request(self, *args, **kwargs):
            return None

    class Client:
        def __init__(self, *args, **kwargs):
            self.base_client = SimpleNamespace(session=Session())

        def get_iot_domain(self, *args, **kwargs):
            return SimpleNamespace(data=SimpleNamespace(
                id="wrong", iot_domain_group_id="group-id", compartment_id="compartment-id",
            ))

    monkeypatch.setattr("oracle.oci_iot_mcp_server.shared_readonly.build_auth_context", lambda options: auth)
    monkeypatch.setattr("oracle.oci_iot_mcp_server.shared_readonly.oci.iot.IotClient", Client)
    monkeypatch.setattr("oracle.oci_iot_mcp_server.shared_readonly.jwt.decode", lambda *a, **k: {"exp": (datetime.now(UTC) + timedelta(hours=1)).timestamp()})
    with pytest.raises(Exception, match="response did not match"):
        RestrictedIoTReader(POLICY).get_domain("domain-id")

    reader = RestrictedIoTReader(POLICY)
    reader._client = object()
    reader._token_expiry = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(Exception, match="credential has expired"):
        reader._ensure_client()


def test_provider_exception_is_redacted(monkeypatch):
    signer = SimpleNamespace(api_key="ST$synthetic")
    auth = SimpleNamespace(tenancy_id="tenancy-id", region="us-test-1", signer=signer, config={})

    class Session:
        def request(self, *args, **kwargs):
            return None

    class Client:
        def __init__(self, *args, **kwargs):
            self.base_client = SimpleNamespace(session=Session())

        def get_iot_domain(self, *args, **kwargs):
            raise RuntimeError("credential-secret-and-provider-response")

    monkeypatch.setattr("oracle.oci_iot_mcp_server.shared_readonly.build_auth_context", lambda options: auth)
    monkeypatch.setattr("oracle.oci_iot_mcp_server.shared_readonly.oci.iot.IotClient", Client)
    monkeypatch.setattr("oracle.oci_iot_mcp_server.shared_readonly.jwt.decode", lambda *a, **k: {"exp": (datetime.now(UTC) + timedelta(hours=1)).timestamp()})
    with pytest.raises(Exception) as error:
        RestrictedIoTReader(POLICY).get_domain("domain-id")
    assert "credential-secret" not in str(error.value)


def test_caller_context_is_isolated_between_concurrent_tasks():
    async def read_value(value):
        marker = _CALLER.set(value)
        try:
            await asyncio.sleep(0)
            return _CALLER.get()
        finally:
            _CALLER.reset(marker)

    async def run():
        return await asyncio.gather(read_value("one"), read_value("two"))

    assert asyncio.run(run()) == ["one", "two"]



def test_real_common_sdk_and_asgi_path_uses_signed_intercepted_gets(tmp_path, monkeypatch):
    """Exercise real credential parsing, SDK signing, middleware, and ASGI locally."""
    import socket
    from datetime import timedelta
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from jwt import encode
    from oci.base_client import OCIHTTPAdapter
    from oci._vendor import requests

    private_key_path = tmp_path / "private-key.pem"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key_path.write_bytes(private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    private_key_path.chmod(0o600)
    security_token_path = tmp_path / "security-token.jwt"
    token_value = encode(
        {"exp": (datetime.now(UTC) + timedelta(hours=1)).timestamp(), "sub": "synthetic"},
        "local-test-secret-that-is-at-least-32-bytes", algorithm="HS256",
    )
    security_token_path.write_text(token_value)
    security_token_path.chmod(0o600)

    config_dir = tmp_path / "config-dir"
    config_dir.mkdir()
    config_path = config_dir / "oci-config"
    config_path.write_text(
        "[test-profile]\n"
        "tenancy=tenancy-id\n"
        "user=user-id\n"
        "fingerprint=00:11:22\n"
        f"key_file={private_key_path}\n"
        f"security_token_file={security_token_path}\n"
        "region=us-test-1\n"
    )
    config_path.chmod(0o600)
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps({
        "version": 1, "region": "us-test-1", "profile": "test-profile",
        "config_file": str(config_path), "auth_tenancy_id": "tenancy-id",
        "credential_generation": "local-generation", "iot_domain_id": "domain-id",
        "iot_domain_group_id": "group-id", "compartment_id": "compartment-id",
        "model_ids": ["model-id"],
        "allowed_callers": ["allowed-caller", "second-caller"],
    }))
    policy_path.chmod(0o600)
    working_dir = tmp_path / "working-directory"
    working_dir.mkdir()
    (working_dir / "security-token.jwt").write_text("cwd-canary-token")
    (working_dir / "security-token.jwt").chmod(0o600)
    (working_dir / "private-key.pem").write_text("cwd-canary-key")
    (working_dir / "private-key.pem").chmod(0o600)
    monkeypatch.chdir(working_dir)
    policy = load_read_policy(policy_path)
    original = list(server.mcp.middleware)
    try:
        app = build_shared_readonly_http_app(
            server.mcp,
            caller_tokens={TOKEN: "allowed-caller", TOKEN_TWO: "second-caller"},
            policy=policy,
        )
        auth_probe = RestrictedIoTReader(policy)
        auth_probe._ensure_client()
    except BaseException:
        server.mcp.middleware[:] = original
        raise
    sent = []
    mismatch_binding = None

    def reject_network(*args, **kwargs):
        raise AssertionError("unexpected network attempt")

    def intercept_send(adapter, request, **kwargs):
        authorization = request.headers.get("authorization", "")
        from oracle.oci_iot_mcp_server.shared_readonly import _CALLER

        sent.append((request.method, request.url, _CALLER.get(),
                     authorization.startswith("Signature "),
                     "cwd-canary-token" in authorization, token_value in authorization))
        if request.url.endswith("/iotDomains/domain-id"):
            data = {
                "id": "wrong-domain" if mismatch_binding == "domain-id" else "domain-id",
                "iotDomainGroupId": "wrong-group" if mismatch_binding == "group" else "group-id",
                "compartmentId": "wrong-compartment" if mismatch_binding == "compartment" else "compartment-id",
            }
        elif request.url.endswith("/digitalTwinModels/model-id"):
            data = {
                "id": "wrong-model" if mismatch_binding == "model-id" else "model-id",
                "iotDomainId": "wrong-domain" if mismatch_binding == "model-parent" else "domain-id",
            }
        else:
            data = {"id": "unexpected", "iotDomainId": "domain-id"}
        response = requests.Response()
        response.status_code = 200
        response.headers["content-type"] = "application/json"
        response.url = request.url
        response.request = request
        response._content = json.dumps(data).encode()
        return response

    monkeypatch.setattr(OCIHTTPAdapter, "send", intercept_send)
    monkeypatch.setattr(socket, "create_connection", reject_network)
    monkeypatch.setattr(socket, "getaddrinfo", reject_network)
    try:
        with TestClient(app) as client:
            initialize(client)
            unauthorized = client.post("/mcp", headers=HEADERS | {
                "authorization": "Bearer " + "x" * 48,
            }, json={
                "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": "get_iot_domain", "arguments": {"iot_domain_id": "domain-id"}},
            })
            assert unauthorized.status_code == 401
            assert sent == []
            for caller in (TOKEN, TOKEN_TWO):
                for name, args in (
                    ("get_iot_domain", {"iot_domain_id": "other-domain"}),
                    ("get_iot_domain", {"iot_domain_id": "domain-id", "extra": True}),
                    ("delete_iot_domain", {}),
                ):
                    denied = client.post("/mcp", headers=HEADERS | {
                        "authorization": f"Bearer {caller}",
                    }, json={
                        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
                        "params": {"name": name, "arguments": args},
                    })
                    assert payload(denied)["result"]["isError"] is True
                    assert sent == []

            from concurrent.futures import ThreadPoolExecutor

            def post_for_caller(request_id, token, name, args):
                return client.post("/mcp", headers=HEADERS | {
                    "authorization": f"Bearer {token}",
                }, json={
                    "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                    "params": {"name": name, "arguments": args},
                })

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(post_for_caller, 10, TOKEN,
                                    "get_iot_domain", {"iot_domain_id": "domain-id"}),
                    executor.submit(post_for_caller, 11, TOKEN_TWO,
                                    "get_digital_twin_model", {"digital_twin_model_id": "model-id"}),
                ]
                concurrent_responses = [future.result() for future in futures]
            assert all(response.status_code == 200 for response in concurrent_responses)
            assert [payload(response)["result"]["structuredContent"]["id"]
                    for response in concurrent_responses] == ["domain-id", "model-id"]
            assert len(sent) == 2
            assert {(item[1], item[2]) for item in sent} == {
                ("https://iot.us-test-1.oci.oraclecloud.com/20250531/iotDomains/domain-id", "allowed-caller"),
                ("https://iot.us-test-1.oci.oraclecloud.com/20250531/digitalTwinModels/model-id", "second-caller"),
            }
            assert all(item[3] and not item[4] and item[5] for item in sent)
            concurrent_sent = list(sent)
            sent.clear()
            request_id = 20
            for caller in (TOKEN, TOKEN_TWO):
                for name, args, expected_id in (
                    ("get_iot_domain", {"iot_domain_id": "domain-id"}, "domain-id"),
                    ("get_digital_twin_model", {"digital_twin_model_id": "model-id"}, "model-id"),
                ):
                    response = client.post("/mcp", headers=HEADERS | {
                        "authorization": f"Bearer {caller}",
                    }, json={
                        "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                        "params": {"name": name, "arguments": args},
                    })
                    result = payload(response)["result"]
                    assert result["structuredContent"]["id"] == expected_id
                    request_id += 1
            assert len(sent) == 4
            mismatch_cases = (
                ("domain-id", "get_iot_domain", {"iot_domain_id": "domain-id"}),
                ("group", "get_iot_domain", {"iot_domain_id": "domain-id"}),
                ("compartment", "get_iot_domain", {"iot_domain_id": "domain-id"}),
                ("model-id", "get_digital_twin_model", {"digital_twin_model_id": "model-id"}),
                ("model-parent", "get_digital_twin_model", {"digital_twin_model_id": "model-id"}),
            )
            for mismatch_binding, name, args in mismatch_cases:
                response = client.post("/mcp", headers=HEADERS, json={
                    "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                    "params": {"name": name, "arguments": args},
                })
                result = payload(response)["result"]
                assert result["isError"] is True
                assert "structuredContent" not in result
                assert result["content"][0]["text"] == "OCI response did not match the read-only policy."
                assert token_value not in json.dumps(result)
                request_id += 1
            mismatch_binding = None
            assert len(sent) == 9
            expired_token = encode(
                {"exp": (datetime.now(UTC) - timedelta(hours=1)).timestamp(), "sub": "synthetic"},
                "local-test-secret-that-is-at-least-32-bytes", algorithm="HS256",
            )
            security_token_path.write_text(expired_token)
            security_token_path.chmod(0o600)
            middleware = next(
                item for item in server.mcp.middleware
                if isinstance(item, SharedReadOnlyMiddleware)
            )
            middleware.reader = RestrictedIoTReader(policy)
            expired = client.post("/mcp", headers=HEADERS, json={
                "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                "params": {"name": "get_iot_domain", "arguments": {"iot_domain_id": "domain-id"}},
            })
            expired_result = payload(expired)["result"]
            assert expired_result["isError"] is True
            assert "credential has expired" in expired_result["content"][0]["text"]
            assert token_value not in json.dumps(expired_result)
            assert expired_token not in json.dumps(expired_result)
            assert len(sent) == 9
        assert all(item[0] == "GET" and item[3] and not item[4] and item[5] for item in sent)
        assert len(concurrent_sent) == 2
        assert [item[1] for item in sent[:4]] == [
            "https://iot.us-test-1.oci.oraclecloud.com/20250531/iotDomains/domain-id",
            "https://iot.us-test-1.oci.oraclecloud.com/20250531/digitalTwinModels/model-id",
            "https://iot.us-test-1.oci.oraclecloud.com/20250531/iotDomains/domain-id",
            "https://iot.us-test-1.oci.oraclecloud.com/20250531/digitalTwinModels/model-id",
        ]
        assert [item[2] for item in sent[:4]] == [
            "allowed-caller", "allowed-caller", "second-caller", "second-caller",
        ]
        assert [item[1] for item in sent[4:]] == [
            "https://iot.us-test-1.oci.oraclecloud.com/20250531/iotDomains/domain-id",
            "https://iot.us-test-1.oci.oraclecloud.com/20250531/iotDomains/domain-id",
            "https://iot.us-test-1.oci.oraclecloud.com/20250531/iotDomains/domain-id",
            "https://iot.us-test-1.oci.oraclecloud.com/20250531/digitalTwinModels/model-id",
            "https://iot.us-test-1.oci.oraclecloud.com/20250531/digitalTwinModels/model-id",
        ]
        assert all(item[2] == "allowed-caller" for item in sent[4:])
    finally:
        server.mcp.middleware[:] = original
