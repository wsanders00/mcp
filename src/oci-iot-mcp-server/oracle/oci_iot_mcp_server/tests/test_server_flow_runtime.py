"""
Copyright (c) 2026, Oracle and/or its affiliates.
Licensed under the Universal Permissive License v1.0 as shown at
https://oss.oracle.com/licenses/upl.
"""

import asyncio

from fastmcp import Client
import pytest

from oracle.oci_iot_mcp_server import server

def test_list_flow_runtimes_page_forwards_all_inputs_and_result(monkeypatch):
    expected = {"ok": True, "data": {"items": [], "opc_next_page": "next", "has_more": True}}
    calls = []

    def helper(**kwargs):
        calls.append(kwargs)
        return expected

    monkeypatch.setattr(server, "list_iot_flow_runtimes_page_record", helper)
    result = server.list_iot_flow_runtimes_page(
        compartment_id="ocid1.compartment.synthetic",
        iot_domain_id="domain-synthetic",
        id="runtime-synthetic",
        display_name="synthetic runtime",
        lifecycle_state="ACTIVE",
        page="token-synthetic",
        limit=25,
        sort_order="ASC",
        sort_by="displayName",
        opc_request_id="request-synthetic",
    )

    assert result is expected
    assert calls == [
        {
            "compartment_id": "ocid1.compartment.synthetic",
            "iot_domain_id": "domain-synthetic",
            "id": "runtime-synthetic",
            "display_name": "synthetic runtime",
            "lifecycle_state": "ACTIVE",
            "page": "token-synthetic",
            "limit": 25,
            "sort_order": "ASC",
            "sort_by": "displayName",
            "opc_request_id": "request-synthetic",
        }
    ]


def test_list_flow_runtimes_page_defaults_limit_and_preserves_helper_error(monkeypatch):
    expected = {"ok": False, "error": {"code": "request_failed"}}
    calls = []
    monkeypatch.setattr(
        server,
        "list_iot_flow_runtimes_page_record",
        lambda **kwargs: calls.append(kwargs) or expected,
    )

    result = server.list_iot_flow_runtimes_page(compartment_id="compartment-synthetic")

    assert result is expected
    assert calls[0]["limit"] == 100
    assert calls[0]["page"] is None


def test_get_flow_runtime_tools_forward_arguments_and_preserve_results(monkeypatch):
    runtime_result = {"ok": True, "data": {"runtime": {"id": "runtime-synthetic"}, "etag": '"runtime"'}}
    flows_result = {"ok": False, "error": {"code": "oci_service_error"}}
    runtime_calls = []
    flows_calls = []
    monkeypatch.setattr(
        server,
        "get_iot_flow_runtime_record",
        lambda **kwargs: runtime_calls.append(kwargs) or runtime_result,
    )
    monkeypatch.setattr(
        server,
        "get_iot_flow_runtime_flows_record",
        lambda **kwargs: flows_calls.append(kwargs) or flows_result,
    )

    assert server.get_iot_flow_runtime(
        iot_flow_runtime_id="runtime-synthetic", opc_request_id="request-synthetic"
    ) is runtime_result
    assert server.get_iot_flow_runtime_flows(
        iot_flow_runtime_id="runtime-synthetic", opc_request_id="request-synthetic"
    ) is flows_result
    assert runtime_calls == [
        {"iot_flow_runtime_id": "runtime-synthetic", "opc_request_id": "request-synthetic"}
    ]
    assert flows_calls == runtime_calls


def test_flow_runtime_tools_are_registered_with_bounded_list_schema():
    tools = {
        name: asyncio.run(server.mcp.get_tool(name))
        for name in (
            "list_iot_flow_runtimes_page",
            "get_iot_flow_runtime",
            "get_iot_flow_runtime_flows",
        )
    }

    list_schema = tools["list_iot_flow_runtimes_page"].parameters
    assert list_schema["properties"]["limit"]["default"] == 100
    assert list_schema["properties"]["limit"]["minimum"] == 1
    assert list_schema["properties"]["limit"]["maximum"] == 100
    assert "compartment_id" in list_schema["required"]
    assert "iot_flow_runtime_id" in tools["get_iot_flow_runtime"].parameters["required"]
    assert "iot_flow_runtime_id" in tools["get_iot_flow_runtime_flows"].parameters["required"]
    for registered in tools.values():
        assert registered.output_schema == {"additionalProperties": True, "type": "object"}


@pytest.mark.asyncio
async def test_fastmcp_calls_return_structured_envelopes_and_preserve_flows(monkeypatch):
    success = {"ok": True, "data": {"items": [], "opc_next_page": "next"}}
    failure = {"ok": False, "error": {"code": "oci_service_error", "message": "safe failure"}}
    flow_document = {
        "flows": [
            {"type": "tab", "id": "tab-a"},
            {"type": "tab", "id": "tab-b"},
            {"type": "config", "id": "config-a", "secret": "synthetic-secret"},
        ],
        "future_field": {"nested": [1, {"opaque": True}]},
        "embedded": '{"keep":"as a string"}',
    }
    monkeypatch.setattr(server, "list_iot_flow_runtimes_page_record", lambda **_: success)
    monkeypatch.setattr(server, "get_iot_flow_runtime_record", lambda **_: failure)
    monkeypatch.setattr(
        server,
        "get_iot_flow_runtime_flows_record",
        lambda **_: {"ok": True, "data": {"flows": flow_document, "etag": '"flows"'}},
    )

    async with Client(server.mcp) as client:
        list_result = await client.call_tool(
            "list_iot_flow_runtimes_page", {"compartment_id": "compartment-synthetic"}
        )
        error_result = await client.call_tool(
            "get_iot_flow_runtime", {"iot_flow_runtime_id": "runtime-synthetic"}
        )
        flows_result = await client.call_tool(
            "get_iot_flow_runtime_flows", {"iot_flow_runtime_id": "runtime-synthetic"}
        )

    assert list_result.structured_content == success
    assert error_result.structured_content == failure
    assert flows_result.structured_content["data"]["flows"] == flow_document


@pytest.mark.asyncio
async def test_fastmcp_rejects_flow_runtime_list_limit_before_helper(monkeypatch):
    calls = []
    monkeypatch.setattr(
        server,
        "list_iot_flow_runtimes_page_record",
        lambda **kwargs: calls.append(kwargs) or {"ok": True, "data": {}},
    )

    async with Client(server.mcp) as client:
        with pytest.raises(Exception, match="less than or equal to 100"):
            await client.call_tool(
                "list_iot_flow_runtimes_page",
                {"compartment_id": "compartment-synthetic", "limit": 101},
            )

    assert calls == []
