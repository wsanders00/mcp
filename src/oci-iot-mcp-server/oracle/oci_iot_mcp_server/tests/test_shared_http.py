"""Offline tests for authenticated, cloud-disabled shared HTTP mode."""

# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v1.0 as shown at
# https://oss.oracle.com/licenses/upl.

import json
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from oracle.oci_iot_mcp_server import server
from oracle.oci_iot_mcp_server.shared_http import (
    SUPPORTED_TOOL_COUNT,
    build_shared_http_app,
    load_caller_tokens,
)


TOKEN = "t" * 48
HEADERS = {
    "host": "127.0.0.1:8765",
    "authorization": f"Bearer {TOKEN}",
    "content-type": "application/json",
    "accept": "application/json, text/event-stream",
}


def rpc(client, request_id, method, params):
    return client.post("/mcp", headers=HEADERS, json={
        "jsonrpc": "2.0", "id": request_id, "method": method, "params": params,
    })


def payload(response):
    if response.headers.get("content-type", "").startswith("application/json"):
        return response.json()
    return next(json.loads(line[6:]) for line in response.text.splitlines()
                if line.startswith("data: "))


def make_app():
    original_middleware = list(server.mcp.middleware)
    app = build_shared_http_app(server.mcp, caller_tokens={TOKEN: "local-caller"})
    return app, original_middleware


def test_shared_http_lists_actual_72_tool_catalog_and_health_is_authenticated():
    app, original = make_app()
    try:
        with TestClient(app) as client:
            health = client.get("/healthz", headers=HEADERS)
            assert health.status_code == 200
            assert health.json() == {"cloud_access": "disabled", "tool_count": 72}

            init = rpc(client, 1, "initialize", {
                "protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "offline-test", "version": "1"},
            })
            assert init.status_code == 200, init.text
            listing = rpc(client, 2, "tools/list", {})
            assert listing.status_code == 200, listing.text
            tools = payload(listing)["result"]["tools"]
            assert len(tools) == SUPPORTED_TOOL_COUNT == 72
            assert {tool["name"] for tool in tools} >= {
                "list_compartments", "get_data_api_token", "health_check",
            }
    finally:
        server.mcp.middleware[:] = original


def test_every_tool_call_is_rejected_before_provider_or_tool_code(monkeypatch):
    app, original = make_app()
    forbidden = AssertionError("cloud/provider code must not run")
    monkeypatch.setattr(server, "get_identity_client", lambda *a, **k: (_ for _ in ()).throw(forbidden))
    monkeypatch.setattr(server, "get_iot_client", lambda *a, **k: (_ for _ in ()).throw(forbidden))
    monkeypatch.setattr(server, "build_auth_context", lambda *a, **k: (_ for _ in ()).throw(forbidden))
    monkeypatch.setattr(server.oci.config, "from_file", lambda *a, **k: (_ for _ in ()).throw(forbidden))
    monkeypatch.setattr(server.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(forbidden))
    monkeypatch.setattr(server.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(forbidden))
    try:
        with TestClient(app) as client:
            init = rpc(client, 1, "initialize", {
                "protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "offline-test", "version": "1"},
            })
            assert init.status_code == 200, init.text
            tools = payload(rpc(client, 2, "tools/list", {}))["result"]["tools"]
            names = [tool["name"] for tool in tools] + ["unknown-tool"]
            for index, name in enumerate(names, 10):
                response = rpc(client, index, "tools/call", {"name": name, "arguments": {}})
                assert response.status_code == 200, response.text
                result = payload(response)["result"]
                assert result["isError"] is True
                assert "Cloud operations are disabled" in result["content"][0]["text"]
    finally:
        server.mcp.middleware[:] = original


def test_stateless_http_has_no_fixture_lifetime_session_cap():
    app, original = make_app()
    try:
        with TestClient(app) as client:
            for request_id in range(1, 40):
                response = rpc(client, request_id, "initialize", {
                    "protocolVersion": "2025-03-26", "capabilities": {},
                    "clientInfo": {"name": "offline-test", "version": "1"},
                })
                assert response.status_code == 200, response.text
                assert "mcp-session-id" not in response.headers
    finally:
        server.mcp.middleware[:] = original


def test_bearer_host_and_origin_are_checked_before_protocol():
    app, original = make_app()
    try:
        with TestClient(app) as client:
            assert client.get("/healthz").status_code == 400
            assert client.get("/healthz", headers={
                "host": "127.0.0.1:8765", "authorization": "Bearer " + "x" * 48,
            }).status_code == 401
            assert client.get("/healthz", headers=HEADERS | {
                "origin": "http://attacker.invalid",
            }).status_code == 403
            assert client.get("/healthz", headers=HEADERS | {
                "host": "attacker.invalid",
            }).status_code == 400
    finally:
        server.mcp.middleware[:] = original


def test_private_caller_config_is_loaded_without_echoing_payload(tmp_path):
    config = tmp_path / "callers.json"
    config.write_text(json.dumps({TOKEN: "local-caller"}))
    config.chmod(0o600)
    assert load_caller_tokens(config) == {TOKEN: "local-caller"}

    config.chmod(0o644)
    with pytest.raises(RuntimeError, match="^shared_http_configuration_invalid$"):
        load_caller_tokens(config)

    config.write_text(json.dumps({"a" * 31 + "\n": "local-caller"}))
    config.chmod(0o600)
    with pytest.raises(RuntimeError, match="^shared_http_configuration_invalid$"):
        load_caller_tokens(config)
    with pytest.raises(ValueError, match="^shared_http_configuration_invalid$"):
        build_shared_http_app(server.mcp, caller_tokens={"a" * 31 + "\n": "local-caller"})


def test_shared_http_entry_uses_requested_listener_without_stdio(tmp_path):
    config = tmp_path / "callers.json"
    config.write_text(json.dumps({TOKEN: "local-caller"}))
    config.chmod(0o600)
    args = ["server", "--shared-http-cloud-disabled", "--caller-config", str(config),
            "--listen-host", "0.0.0.0", "--listen-port", "8765"]
    original = list(server.mcp.middleware)
    try:
        with patch("sys.argv", args), patch("uvicorn.run") as run, \
                patch.object(server.mcp, "run") as stdio:
            server.main()
        run.assert_called_once()
        assert run.call_args.kwargs == {
            "host": "0.0.0.0", "port": 8765, "access_log": False, "log_level": "warning",
        }
        stdio.assert_not_called()

        run.reset_mock()
        stdio.reset_mock()
        default_args = ["server", "--shared-http-cloud-disabled", "--caller-config", str(config)]
        with patch("sys.argv", default_args), patch("uvicorn.run") as default_run:
            server.main()
        default_run.assert_called_once()
        assert default_run.call_args.kwargs == {
            "host": "127.0.0.1", "port": 8765,
            "access_log": False, "log_level": "warning",
        }
        stdio.assert_not_called()
    finally:
        server.mcp.middleware[:] = original
