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

