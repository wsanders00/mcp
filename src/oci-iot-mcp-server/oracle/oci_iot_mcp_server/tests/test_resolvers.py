import socket
from types import SimpleNamespace

import pytest

import oracle.oci_iot_mcp_server.control_plane as control_plane
import oracle.oci_iot_mcp_server.resolvers as resolvers
from oracle.oci_iot_mcp_server.resolvers import (
    resolve_domain_selector,
    resolve_twin_for_tool,
    resolve_twin_selector,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("Unexpected network access in selector tests")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)


def test_resolve_domain_selector_returns_match_for_short_id(monkeypatch):
    monkeypatch.setattr(
        resolvers,
        "_iter_iot_domains_for_selector",
        lambda compartment_id: [
            {
                "id": "domain-ocid",
                "name": "factory-domain",
                "device_host": "abc123.device.iot.us-phoenix-1.oci.oraclecloud.com",
            }
        ],
    )

    result = resolve_domain_selector(
        domain_short_id="abc123",
        compartment_id="ocid1.compartment.oc1..aaaa",
    )

    assert result["ok"] is True
    assert result["data"]["id"] == "domain-ocid"


def test_resolve_twin_selector_by_ocid_derives_domain_context(monkeypatch):
    monkeypatch.setattr(
        resolvers,
        "get_digital_twin_instance_record",
        lambda digital_twin_instance_id: {
            "id": digital_twin_instance_id,
            "iot_domain_id": "ocid1.iotdomain.oc1..aaaa",
        },
    )

    result = resolve_twin_selector(
        digital_twin_instance_id="ocid1.digitaltwininstance.oc1..aaaa"
    )

    assert result == {
        "ok": True,
        "data": {
            "id": "ocid1.digitaltwininstance.oc1..aaaa",
            "iot_domain_id": "ocid1.iotdomain.oc1..aaaa",
        },
    }


def test_resolve_twin_selector_requires_domain_scope_for_display_name():
    result = resolve_twin_selector(digital_twin_instance_name="pump-01")

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_input"


def test_resolve_twin_selector_returns_ambiguity_error_with_candidates(monkeypatch):
    monkeypatch.setattr(
        resolvers,
        "_iter_twin_instances_for_selector",
        lambda iot_domain_id: [
            {"id": "twin-1", "name": "pump-01", "iot_domain_id": iot_domain_id},
            {"id": "twin-2", "name": "pump-01", "iot_domain_id": iot_domain_id},
        ],
    )

    result = resolve_twin_selector(
        digital_twin_instance_name="pump-01",
        iot_domain_id="ocid1.iotdomain.oc1..aaaa",
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "ambiguous_identifier"
    assert [candidate["id"] for candidate in result["error"]["details"]["candidates"]] == [
        "twin-1",
        "twin-2",
    ]


def test_resolve_domain_selector_requires_compartment_for_display_name():
    result = resolve_domain_selector(iot_domain_display_name="factory-domain")

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_input"


def test_first_label_returns_none_for_missing_host():
    assert resolvers._first_label(None) is None


def test_resolve_domain_selector_returns_supplied_ocid_without_lookup():
    assert resolve_domain_selector(iot_domain_id="domain-ocid") == {
        "ok": True,
        "data": {"id": "domain-ocid"},
    }


def test_resolve_domain_selector_returns_not_found_when_no_match(monkeypatch):
    monkeypatch.setattr(resolvers, "_iter_iot_domains_for_selector", lambda compartment_id: [])

    result = resolve_domain_selector(
        iot_domain_display_name="factory-domain",
        compartment_id="ocid1.compartment.oc1..aaaa",
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "resource_not_found"


def test_resolve_domain_selector_returns_ambiguity_error_for_multiple_matches(monkeypatch):
    monkeypatch.setattr(
        resolvers,
        "_iter_iot_domains_for_selector",
        lambda compartment_id: [
            {"id": "domain-1", "name": "factory-domain", "device_host": "abc.device.iot.us-phoenix-1.oci.oraclecloud.com"},
            {"id": "domain-2", "name": "factory-domain", "device_host": "xyz.device.iot.us-phoenix-1.oci.oraclecloud.com"},
        ],
    )

    result = resolve_domain_selector(
        iot_domain_display_name="factory-domain",
        compartment_id="ocid1.compartment.oc1..aaaa",
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "ambiguous_identifier"
    assert [candidate["id"] for candidate in result["error"]["details"]["candidates"]] == [
        "domain-1",
        "domain-2",
    ]


def test_resolve_domain_selector_deduplicates_same_row_matched_by_name_and_short_id(monkeypatch):
    monkeypatch.setattr(
        resolvers,
        "_iter_iot_domains_for_selector",
        lambda compartment_id: [
            {
                "id": "domain-ocid",
                "name": "factory-domain",
                "device_host": "abc123.device.iot.us-phoenix-1.oci.oraclecloud.com",
            }
        ],
    )

    result = resolve_domain_selector(
        iot_domain_display_name="factory-domain",
        domain_short_id="abc123",
        compartment_id="ocid1.compartment.oc1..aaaa",
    )

    assert result["ok"] is True
    assert result["data"]["id"] == "domain-ocid"


def test_resolve_twin_selector_returns_not_found_when_name_has_no_match(monkeypatch):
    monkeypatch.setattr(resolvers, "_iter_twin_instances_for_selector", lambda iot_domain_id: [])

    result = resolve_twin_selector(
        digital_twin_instance_name="pump-01",
        iot_domain_id="domain-ocid",
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "resource_not_found"


def test_resolve_twin_selector_returns_single_friendly_match(monkeypatch):
    monkeypatch.setattr(
        resolvers,
        "_iter_twin_instances_for_selector",
        lambda iot_domain_id: [{"id": "twin-1", "name": "pump-01", "iot_domain_id": iot_domain_id}],
    )

    result = resolve_twin_selector(
        digital_twin_instance_name="pump-01",
        iot_domain_id="domain-ocid",
    )

    assert result == {
        "ok": True,
        "data": {"id": "twin-1", "name": "pump-01", "iot_domain_id": "domain-ocid"},
    }


def test_resolve_twin_for_tool_returns_ocid_lookup_data(monkeypatch):
    monkeypatch.setattr(
        resolvers,
        "resolve_twin_selector",
        lambda **kwargs: {"ok": True, "data": {"id": kwargs["digital_twin_instance_id"], "iot_domain_id": "domain-ocid"}},
    )

    result = resolve_twin_for_tool(digital_twin_instance_id="twin-1")

    assert result == {"id": "twin-1", "iot_domain_id": "domain-ocid"}


def test_resolve_twin_for_tool_requires_selector():
    result = resolve_twin_for_tool()

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_input"


def test_resolve_twin_for_tool_passes_through_domain_resolution_error(monkeypatch):
    monkeypatch.setattr(
        resolvers,
        "resolve_domain_selector",
        lambda **kwargs: {"ok": False, "error": {"code": "ambiguous_identifier"}},
    )

    result = resolve_twin_for_tool(
        digital_twin_instance_name="pump-01",
        compartment_id="ocid1.compartment.oc1..aaaa",
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "ambiguous_identifier"


def test_resolve_twin_for_tool_returns_friendly_match(monkeypatch):
    monkeypatch.setattr(
        resolvers,
        "resolve_domain_selector",
        lambda **kwargs: {"ok": True, "data": {"id": "domain-ocid"}},
    )
    monkeypatch.setattr(
        resolvers,
        "resolve_twin_selector",
        lambda **kwargs: {"ok": True, "data": {"id": "twin-1", "iot_domain_id": kwargs["iot_domain_id"]}},
    )

    result = resolve_twin_for_tool(
        digital_twin_instance_name="pump-01",
        iot_domain_display_name="factory-domain",
        compartment_id="ocid1.compartment.oc1..aaaa",
    )

    assert result == {"id": "twin-1", "iot_domain_id": "domain-ocid"}


def test_resolve_twin_for_tool_passes_through_twin_selector_error(monkeypatch):
    monkeypatch.setattr(
        resolvers,
        "resolve_domain_selector",
        lambda **kwargs: {"ok": True, "data": {"id": "domain-ocid"}},
    )
    monkeypatch.setattr(
        resolvers,
        "resolve_twin_selector",
        lambda **kwargs: {"ok": False, "error": {"code": "resource_not_found"}},
    )

    result = resolve_twin_for_tool(
        digital_twin_instance_name="pump-01",
        iot_domain_id="domain-ocid",
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "resource_not_found"


@pytest.mark.parametrize("kind", ["domain", "twin"])
@pytest.mark.parametrize("first_match", [False, True])
def test_friendly_lookup_considers_later_pages(monkeypatch, kind, first_match):
    calls = []

    def listing(**kwargs):
        calls.append(kwargs)
        second = kwargs.get("page") == "next-synthetic"
        row = SimpleNamespace(id="second" if second else "first",
                              display_name="target" if second or first_match else "other")
        return SimpleNamespace(data=SimpleNamespace(items=[row]),
                               headers={} if second else {"opc-next-page": "next-synthetic"})

    client = SimpleNamespace(list_iot_domains=listing, list_digital_twin_instances=listing)
    monkeypatch.setattr(control_plane, "get_iot_client", lambda: client)
    if kind == "domain":
        result = resolve_domain_selector(iot_domain_display_name="target", compartment_id="scope")
    else:
        result = resolve_twin_selector(digital_twin_instance_name="target", iot_domain_id="scope")
    if first_match:
        assert result["error"]["code"] == "ambiguous_identifier"
    else:
        assert result["ok"] is True
        assert result["data"]["id"] == "second"
    assert [c.get("page") for c in calls] == [None, "next-synthetic"]
    assert all(c["limit"] == 100 and "display_name" not in c for c in calls)


def _install_pages(monkeypatch, pages):
    calls = []
    def listing(**kwargs):
        calls.append(kwargs)
        payload = pages[len(calls) - 1]
        if isinstance(payload, Exception):
            raise payload
        rows, token = payload
        return SimpleNamespace(data=SimpleNamespace(items=rows),
                               headers={"OPC-NEXT-PAGE": token} if token else {})
    monkeypatch.setattr(control_plane, "get_iot_client", lambda: SimpleNamespace(
        list_iot_domains=listing, list_digital_twin_instances=listing))
    return calls


def _row(id="same", name="target", short="short"):
    return SimpleNamespace(id=id, display_name=name, device_host=f"{short}.device.example")


def _lookup(kind, **kwargs):
    if kind == "domain":
        return resolve_domain_selector(compartment_id="scope", iot_domain_display_name="target", **kwargs)
    return resolve_twin_selector(iot_domain_id="scope", digital_twin_instance_name="target", **kwargs)


@pytest.mark.parametrize("kind", ["domain", "twin"])
def test_duplicate_ids_keep_first_seen_and_empty_pages_continue(monkeypatch, kind):
    calls = _install_pages(monkeypatch, [([_row()], "a"), ([], "b"),
                                        ([_row(short="changed")], None)])
    result = _lookup(kind)
    assert result["ok"] is True
    if kind == "domain":
        assert result["data"]["device_host"] == "short.device.example"
    assert len(calls) == 3


@pytest.mark.parametrize("selectors,expected", [
    ({"domain_short_id": "short"}, "same"),
    ({"iot_domain_display_name": "target", "domain_short_id": "missing"}, "same"),
    ({"iot_domain_display_name": "missing", "domain_short_id": "short"}, "same"),
])
def test_domain_short_id_and_both_selector_or_on_later_page(monkeypatch, selectors, expected):
    calls = _install_pages(monkeypatch, [([], "a"), ([_row()], None)])
    result = resolve_domain_selector(compartment_id="scope", **selectors)
    assert result["data"]["id"] == expected
    assert all("display_name" not in call for call in calls)


@pytest.mark.parametrize("kind", ["domain", "twin"])
@pytest.mark.parametrize("tokens", [["a", "a"], ["a", "b", "a"]])
def test_repeated_tokens_stop_without_another_request(monkeypatch, kind, tokens):
    calls = _install_pages(monkeypatch, [([_row()], token) for token in tokens])
    result = _lookup(kind)
    assert result["error"]["code"] == "incomplete_lookup"
    assert result["error"]["details"] == {"pages_fetched": len(tokens),
        "rows_fetched": len(tokens), "reason": "repeated_token"}
    assert len(calls) == len(tokens)
    assert "OCID" in result["error"]["retry_hint"]
    assert "opc_next_page" not in str(result)


@pytest.mark.parametrize("kind", ["domain", "twin"])
@pytest.mark.parametrize("match", [False, True])
@pytest.mark.parametrize("has_more", [False, True])
@pytest.mark.parametrize("rows_per_page", [0, 100])
def test_exact_limits_only_complete_on_exhaustion(monkeypatch, kind, match, has_more, rows_per_page):
    row = _row(name="target" if match else "other")
    pages = [([row] * rows_per_page, f"synthetic-{n}") for n in range(100)]
    if not has_more:
        pages[-1] = (pages[-1][0], None)
    calls = _install_pages(monkeypatch, pages)
    result = _lookup(kind)
    if has_more:
        assert result["error"]["code"] == "incomplete_lookup"
        assert result["error"]["details"] == {"pages_fetched": 100,
            "rows_fetched": rows_per_page * 100,
            "reason": "resource_limit" if rows_per_page else "page_limit"}
    elif rows_per_page and match:
        assert result["ok"] is True
    else:
        assert result["error"]["code"] == "resource_not_found"
    assert len(calls) == 100


@pytest.mark.parametrize("kind", ["domain", "twin"])
@pytest.mark.parametrize("sizes", [[10001], [9999, 2]])
def test_oversized_response_cannot_establish_unique_or_absent(monkeypatch, kind, sizes):
    calls = _install_pages(monkeypatch, [([_row()] * n, "next" if i == 0 and len(sizes)>1 else None)
                                       for i, n in enumerate(sizes)])
    result = _lookup(kind)
    assert result["error"]["code"] == "incomplete_lookup"
    assert result["error"]["details"] == {"pages_fetched": len(sizes),
        "rows_fetched": sum(sizes), "reason": "resource_limit"}
    assert len(calls) == len(sizes)


@pytest.mark.parametrize("kind", ["domain", "twin"])
def test_two_distinct_matches_return_first_two_without_exhausting(monkeypatch, kind):
    calls = _install_pages(monkeypatch, [([_row("first"), _row("first"), _row("second"), _row("third")], "next")])
    result = _lookup(kind)
    assert result["error"]["code"] == "ambiguous_identifier"
    assert [c["id"] for c in result["error"]["details"]["candidates"]] == ["first", "second"]
    assert len(calls) == 1


@pytest.mark.parametrize("kind", ["domain", "twin"])
def test_sdk_failure_after_partial_match_is_not_missing_or_unique(monkeypatch, kind):
    _install_pages(monkeypatch, [([_row()], "next"), RuntimeError("synthetic SDK failure")])
    with pytest.raises(RuntimeError, match="synthetic SDK failure"):
        _lookup(kind)


def test_direct_twin_ocid_preserves_sdk_error(monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("synthetic get failure")
    monkeypatch.setattr(resolvers, "get_digital_twin_instance_record", fail)
    with pytest.raises(RuntimeError, match="synthetic get failure"):
        resolve_twin_for_tool(digital_twin_instance_id="twin")


def test_missing_domain_selector_with_scope_stays_not_found(monkeypatch):
    _install_pages(monkeypatch, [([_row()], None)])
    assert resolve_domain_selector(compartment_id="scope")["error"]["code"] == "resource_not_found"


@pytest.mark.parametrize("kind", ["domain", "twin"])
@pytest.mark.parametrize("token", [None, "synthetic-next"])
def test_exact_row_budget_before_page_cap(monkeypatch, kind, token):
    calls = _install_pages(monkeypatch, [([_row()] * 10_000, token)])
    result = _lookup(kind)
    if token:
        assert result["error"]["code"] == "incomplete_lookup"
        assert result["error"]["details"] == {"reason": "resource_limit",
            "pages_fetched": 1, "rows_fetched": 10_000}
    else:
        assert result["data"]["id"] == "same"
    assert len(calls) == 1


@pytest.mark.parametrize("kind", ["domain", "twin"])
def test_mapping_failure_is_not_converted_to_incomplete(monkeypatch, kind):
    _install_pages(monkeypatch, [([SimpleNamespace(id={"invalid": "id"})], None)])
    with pytest.raises(ValueError):
        _lookup(kind)


def test_domain_incomplete_propagates_through_twin_tool_caller(monkeypatch):
    calls = _install_pages(monkeypatch, [([], "synthetic-next"), ([], "synthetic-next")])
    result = resolve_twin_for_tool(digital_twin_instance_name="target",
                                  iot_domain_display_name="target", compartment_id="scope")
    assert result["error"]["code"] == "incomplete_lookup"
    assert result["error"]["resource_type"] == "iot_domain"
    assert len(calls) == 2


def test_twin_incomplete_propagates_through_tool_caller(monkeypatch):
    _install_pages(monkeypatch, [([], "synthetic-next"), ([], "synthetic-next")])
    result = resolve_twin_for_tool(digital_twin_instance_name="target", iot_domain_id="domain")
    assert result["error"]["code"] == "incomplete_lookup"
    assert result["error"]["resource_type"] == "digital_twin_instance"


@pytest.mark.parametrize("selectors", [{}, {"iot_domain_display_name": "", "domain_short_id": ""}])
def test_missing_domain_selector_does_not_scan_continuation_pages(monkeypatch, selectors):
    calls = _install_pages(monkeypatch, [([], "synthetic-next"), ([], "synthetic-next")])
    result = resolve_domain_selector(compartment_id="scope", **selectors)
    assert result == {"ok": False, "error": {
        "code": "resource_not_found", "message": "No IoT domain matched the provided selector.",
        "resource_type": "iot_domain", "details": {"input": {
            "iot_domain_display_name": selectors.get("iot_domain_display_name"),
            "domain_short_id": selectors.get("domain_short_id"), "compartment_id": "scope"}}}}
    assert calls == []


@pytest.mark.parametrize("name", [None, ""])
@pytest.mark.parametrize("count", [0, 1, 2])
def test_direct_twin_missing_name_retains_single_page_matching(monkeypatch, name, count):
    calls = _install_pages(monkeypatch, [([_row(name=name)] * count, "synthetic-next"),
                                        ([], "synthetic-next")])
    result = resolve_twin_selector(digital_twin_instance_name=name, iot_domain_id="scope")
    if count == 1:
        assert result["data"]["id"] == "same"
    else:
        assert result["error"]["code"] == ("ambiguous_identifier" if count else "resource_not_found")
        if count:
            assert result["error"]["details"]["candidates"] == [
                {"id": "same", "display_name": name}, {"id": "same", "display_name": name}]
    assert len(calls) == 1
    assert calls[0] == {"iot_domain_id": "scope", "limit": 1000}
