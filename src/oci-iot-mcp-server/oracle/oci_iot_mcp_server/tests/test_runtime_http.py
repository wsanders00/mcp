"""Offline tests for authenticated fixture Streamable HTTP lifecycle."""

# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v1.0 as shown at
# https://oss.oracle.com/licenses/upl.

import asyncio
import asyncio
import json

import pytest
from starlette.testclient import TestClient

from oracle.oci_iot_mcp_server.runtime_http import build_fixture_app, fixture_targets


HOST = {"host": "127.0.0.1:8765"}
TOKEN_A = "a" * 40
TOKEN_B = "b" * 40


def initialize(client, token=TOKEN_A):
    response = client.post("/mcp", headers=HOST | {
        "authorization": f"Bearer {token}", "content-type": "application/json",
        "accept": "application/json, text/event-stream",
    }, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": "offline-test", "version": "1"},
    }})
    assert response.status_code == 200, response.text
    return response.headers["mcp-session-id"]


def rpc(client, token, session, request_id, method, params):
    headers = HOST | {
        "authorization": f"Bearer {token}", "content-type": "application/json",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": "2025-03-26", "mcp-session-id": session,
    }
    response = client.post("/mcp", headers=headers, json={
        "jsonrpc": "2.0", "id": request_id, "method": method, "params": params,
    })
    assert response.status_code == 200, response.text
    payload = next(json.loads(line[6:]) for line in response.text.splitlines()
                   if line.startswith("data: "))
    return payload


def call_tool(client, token, session, request_id, name, arguments):
    return rpc(client, token, session, request_id, "tools/call", {
        "name": name, "arguments": arguments,
    })


def tool_value(result):
    return result["result"]["structuredContent"]


def test_fixture_targets_are_explicit_synthetic_and_boat_pair_shares_context():
    ssv, sandbox, normal = fixture_targets()
    assert ssv.auth is sandbox.auth
    assert ssv.auth.context_id != normal.auth.context_id
    assert all("fixture" in value for target in (ssv, sandbox, normal)
               for value in (target.name, target.domain_id, target.group_id,
                             target.compartment_id, target.resource_tenancy))


def test_app_registers_only_fixture_tools_on_streamable_http():
    app = build_fixture_app(caller_tokens={TOKEN_A: "user-a"})
    assert "/mcp" in [route.path for route in app.app.routes]
    assert app.mcp.name == "OCI IoT Offline Fixture"
    tools = {tool.name for tool in __import__("asyncio").run(app.mcp.list_tools())}
    assert tools == {"select_target", "inspect_target", "renew_fixture_credentials",
                     "read_fixture_metadata", "close_target"}


def test_real_protocol_session_tools_and_same_caller_cross_session_isolation():
    app = build_fixture_app(caller_tokens={TOKEN_A: "user-a"})
    with TestClient(app) as client:
        session_one = initialize(client)
        # Ordinary initialization and tool listing do not renew fake credentials.
        listing = rpc(client, TOKEN_A, session_one, 2, "tools/list", {})
        assert {tool["name"] for tool in listing["result"]["tools"]} == {
            "select_target", "inspect_target", "renew_fixture_credentials",
            "read_fixture_metadata", "close_target",
        }
        selected = tool_value(call_tool(client, TOKEN_A, session_one, 4,
                                        "select_target", {"domain_id": "fixture-domain-ssv"}))
        handle = selected["handle"]
        before_renewal = call_tool(client, TOKEN_A, session_one, 3,
                                   "read_fixture_metadata", {"handle": handle})
        assert before_renewal["result"]["isError"] is True
        inspected = tool_value(call_tool(client, TOKEN_A, session_one, 5,
                                         "inspect_target", {"handle": handle}))
        assert inspected == {"fixture": "FIXTURE_ONLY_NOT_REAL",
                             "domain": "fixture-domain-ssv",
                             "group": "fixture-group-ssv", "sample_count": 2}
        assert call_tool(client, TOKEN_A, session_one, 6, "read_fixture_metadata",
                         {"handle": handle})["result"]["isError"] is True
        renewal = tool_value(call_tool(client, TOKEN_A, session_one, 7,
                                       "renew_fixture_credentials", {"handle": handle}))
        assert renewal["generation"] == 1
        metadata = tool_value(call_tool(client, TOKEN_A, session_one, 8,
                                       "read_fixture_metadata", {"handle": handle}))
        assert metadata["sample_count"] == 2

        session_two = initialize(client)
        cross_session = call_tool(client, TOKEN_A, session_two, 9, "inspect_target",
                                  {"handle": handle})
        assert cross_session["result"]["isError"] is True


def test_authentication_host_origin_and_duplicate_header_guards():
    app = build_fixture_app(caller_tokens={TOKEN_A: "user-a"})
    with TestClient(app) as client:
        assert client.get("/mcp", headers=HOST).status_code == 401
        assert client.get("/mcp", headers={"host": "attacker.invalid",
                                          "authorization": f"Bearer {TOKEN_A}"}).status_code == 400
        for origin in ("http://attacker.invalid", "http://localhost:8765/?x=1",
                       "http://user@localhost:8765", "http://localhost:8765/#fragment"):
            result = client.get("/mcp", headers=HOST | {
                "authorization": f"Bearer {TOKEN_A}", "origin": origin,
            })
            assert result.status_code == 403

        duplicated = client.get("/mcp", headers=[("host", "127.0.0.1:8765"),
            ("host", "127.0.0.1:8765"), ("authorization", f"Bearer {TOKEN_A}")])
        assert duplicated.status_code == 400
        non_ascii = client.get("/mcp", headers=[
            ("host", "127.0.0.1:8765"),
            ("authorization", b"Bearer " + ("é" * 40).encode("utf-8")),
        ])
        assert non_ascii.status_code == 401


def test_session_owner_delete_and_lifetime_capacity_bound():
    app = build_fixture_app(caller_tokens={TOKEN_A: "user-a", TOKEN_B: "user-b"}, max_sessions=1)
    with TestClient(app) as client:
        session = initialize(client)
        cross_caller = client.get("/mcp", headers=HOST | {
            "authorization": f"Bearer {TOKEN_B}", "mcp-session-id": session,
        })
        assert cross_caller.status_code == 404

        deleted = client.delete("/mcp", headers=HOST | {
            "authorization": f"Bearer {TOKEN_A}", "mcp-session-id": session,
            "mcp-protocol-version": "2025-03-26",
        })
        assert deleted.status_code == 200
        # FastMCP 3.4.5 has no supported session-manager deletion API. Keep a
        # lifetime initialization cap so expired/deleted sessions cannot grow its store.
        assert client.post("/mcp", headers=HOST | {
            "authorization": f"Bearer {TOKEN_A}", "content-type": "application/json",
            "accept": "application/json, text/event-stream",
        }, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "offline-test", "version": "1"},
        }}).status_code == 503


def test_session_is_owned_before_init_header_is_delivered_and_body_completes():
    async def exercise():
        app = build_fixture_app(caller_tokens={TOKEN_A: "user-a"}, max_sessions=1)
        session_id = "issued-during-init"
        header_delivered = asyncio.Event()
        release_init_body = asyncio.Event()

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def inner(scope, receive_inner, send_inner):
            if scope["method"] == "POST":
                await send_inner({"type": "http.response.start", "status": 200,
                                  "headers": [(b"mcp-session-id", session_id.encode())]})
                await release_init_body.wait()
                await send_inner({"type": "http.response.body", "body": b"init complete"})
                return
            await send_inner({"type": "http.response.start", "status": 200, "headers": []})
            await send_inner({"type": "http.response.body", "body": b"next request accepted"})

        app.app = inner

        def scope(method, session=None):
            headers = [(b"host", b"127.0.0.1:8765"),
                       (b"authorization", f"Bearer {TOKEN_A}".encode())]
            if session:
                headers.append((b"mcp-session-id", session.encode()))
            return {"type": "http", "http_version": "1.1", "method": method,
                    "scheme": "http", "path": "/mcp", "raw_path": b"/mcp",
                    "query_string": b"", "headers": headers,
                    "server": ("127.0.0.1", 8765), "client": ("127.0.0.1", 12345)}

        async def init_send(message):
            if message["type"] == "http.response.start":
                header_delivered.set()
                await release_init_body.wait()

        init_task = asyncio.create_task(app(scope("POST"), receive, init_send))
        await asyncio.wait_for(header_delivered.wait(), timeout=1)
        assert app.initialized == 1
        assert app.reserved == 0

        following_response = []
        async def following_send(message):
            following_response.append(message)

        await app(scope("GET", session_id), receive, following_send)
        assert following_response[0]["status"] == 200

        release_init_body.set()
        await asyncio.wait_for(init_task, timeout=1)
        assert app.initialized == 1
        assert app.reserved == 0

    asyncio.run(exercise())


def test_session_is_owned_before_init_header_is_delivered_and_body_completes():
    async def exercise():
        app = build_fixture_app(caller_tokens={TOKEN_A: "user-a"}, max_sessions=1)
        session_id = "issued-during-init"
        header_delivered = asyncio.Event()
        release_init_body = asyncio.Event()

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def inner(scope, receive_inner, send_inner):
            if scope["method"] == "POST":
                await send_inner({"type": "http.response.start", "status": 200,
                                  "headers": [(b"mcp-session-id", session_id.encode())]})
                await release_init_body.wait()
                await send_inner({"type": "http.response.body", "body": b"init complete"})
                return
            await send_inner({"type": "http.response.start", "status": 200, "headers": []})
            await send_inner({"type": "http.response.body", "body": b"next request accepted"})

        app.app = inner

        def scope(method, session=None):
            headers = [(b"host", b"127.0.0.1:8765"),
                       (b"authorization", f"Bearer {TOKEN_A}".encode())]
            if session:
                headers.append((b"mcp-session-id", session.encode()))
            return {"type": "http", "http_version": "1.1", "method": method,
                    "scheme": "http", "path": "/mcp", "raw_path": b"/mcp",
                    "query_string": b"", "headers": headers,
                    "server": ("127.0.0.1", 8765), "client": ("127.0.0.1", 12345)}

        async def init_send(message):
            if message["type"] == "http.response.start":
                header_delivered.set()
                await release_init_body.wait()

        init_task = asyncio.create_task(app(scope("POST"), receive, init_send))
        await asyncio.wait_for(header_delivered.wait(), timeout=1)
        assert app.initialized == 1
        assert app.reserved == 0

        following_response = []
        async def following_send(message):
            following_response.append(message)

        await app(scope("GET", session_id), receive, following_send)
        assert following_response[0]["status"] == 200

        release_init_body.set()
        await asyncio.wait_for(init_task, timeout=1)
        assert app.initialized == 1
        assert app.reserved == 0

    asyncio.run(exercise())


@pytest.mark.parametrize("kwargs", [
    {"caller_tokens": {"short": "user"}},
    {"caller_tokens": {"é" * 40: "user"}},
    {"caller_tokens": {TOKEN_A: "user", TOKEN_B: "other"}, "max_callers": 1},
    {"caller_tokens": {TOKEN_A: "user"}, "session_ttl_seconds": float("inf")},
    {"caller_tokens": {TOKEN_A: "user"}, "host": "0.0.0.0"},
])
def test_invalid_security_configuration_is_rejected(kwargs):
    with pytest.raises(ValueError):
        build_fixture_app(**kwargs)
