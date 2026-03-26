# OCI IoT MCP Server Expansion Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the eight approved `oci-iot-mcp-server` enhancements, plus the supporting refactor needed for friendly selector resolution, ORDS data-plane access, stable tool result envelopes, and package-local test coverage.

**Architecture:** Split the current single-file server into focused modules for OCI client creation, control-plane wrappers, selector resolution, domain-context derivation, ORDS token/data access, and polling, while keeping `server.py` as thin FastMCP registration. Existing control-plane tools remain available, the new tools use a consistent `{ "ok": true|false, "data"| "error": ... }` contract, and the implementation is driven by mocked package-local tests before any end-to-end follow-up.

**Tech Stack:** Python 3.13, FastMCP, OCI Python SDK, Pydantic 2, httpx, pytest, pytest-asyncio, pytest-cov

---

**Spec:** `ai/features/oci-iot-mcp-server-expansion/2026-03-26-design.md`

**Execution Notes:**
- Follow `@superpowers:subagent-driven-development` when implementing this plan.
- Use `@superpowers:verification-before-completion` before claiming any task is done.
- Keep commits signed off with `git commit -s`.

## File Structure Lock-In

**Modify these existing files:**
- `src/oci-iot-mcp-server/pyproject.toml:12-39`
  Add runtime/test dependencies and package-local coverage config.
- `src/oci-iot-mcp-server/README.md:13-42`
  Document the new tools, selector rules, ORDS credentials, token behavior, and ambiguity/error semantics.
- `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/server.py:7-514`
  Reduce this file to FastMCP tool registration plus thin delegation into internal modules.
- `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/models.py:7-214`
  Keep this file focused on control-plane resource mapping, but broaden the mapped fields for domains, domain groups, twins, and adapters.
- `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/health.py:5-26`
  Remove the hardcoded version string and import `__version__`.

**Create these new runtime modules:**
- `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/client.py`
  Profile-aware OCI config loading, signer creation, and IoT client caching.
- `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/errors.py`
  Stable error-code helpers and builders for the `{ "ok": false, "error": ... }` contract.
- `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tool_models.py`
  Pydantic models for tool envelopes, domain context, token responses, raw command records, rejected data rows, and twin update results.
- `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/control_plane.py`
  Thin wrappers around `oci.iot.IotClient` get/list/invoke operations.
- `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/resolvers.py`
  `OCID + friendly` selector resolution with explicit scope requirements.
- `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/domain_context.py`
  Host parsing and normalized domain-context assembly.
- `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/data_plane.py`
  ORDS token minting, authenticated GET helpers, `q` filters, `limit`/`offset` pagination, and raw/snapshot/rejected reads.
- `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/polling.py`
  Shared polling loops and terminal-state handling for raw commands and twin updates.

**Create these package-local tests:**
- `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/conftest.py`
- `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_client.py`
- `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_errors.py`
- `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_control_plane.py`
- `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_resolvers.py`
- `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_domain_context.py`
- `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_data_plane.py`
- `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_polling.py`
- `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_server_phase1_tools.py`
- `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_server_phase2_tools.py`
- `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_health.py`

**Create this e2e follow-up artifact after unit coverage is in place:**
- `tests/e2e/features/oci-iot-mcp-server.feature`

## Chunk 1: Foundations And Existing Surface

### Task 1: Add Package Test Scaffolding And Profile-Aware Client Caching

**Files:**
- Modify: `src/oci-iot-mcp-server/pyproject.toml:12-39`
- Modify: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/server.py:7-88`
- Create: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/client.py`
- Create: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/conftest.py`
- Test: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_client.py`

- [ ] **Step 1: Write the failing test**

```python
from oracle.oci_iot_mcp_server import client


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

    monkeypatch.setattr(client.oci.config, "from_file", fake_from_file)
    monkeypatch.setattr(client.oci.signer, "load_private_key_from_file", lambda path: f"pk:{path}")
    monkeypatch.setattr(client.oci.auth.signers, "SecurityTokenSigner", lambda token, key: (token, key))
    monkeypatch.setattr(client.oci.iot, "IotClient", lambda config, signer=None: {"profile": config["profile_name"], "signer": signer})

    client.clear_iot_client_cache()

    default_client = client.get_iot_client("DEFAULT")
    alt_client = client.get_iot_client("ALT")

    assert default_client["profile"] == "DEFAULT"
    assert alt_client["profile"] == "ALT"
    assert default_client is not alt_client
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory src/oci-iot-mcp-server pytest oracle/oci_iot_mcp_server/tests/test_client.py::test_get_iot_client_caches_per_profile -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'oracle.oci_iot_mcp_server.client'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/oci-iot-mcp-server/pyproject.toml
[project]
dependencies = [
    "fastmcp==2.12.2",
    "oci>=2.165.1",
    "pydantic>=2.5.0",
    "httpx>=0.28.1",
]

[dependency-groups]
dev = [
    "pytest>=8.4.2",
    "pytest-asyncio>=1.2.0",
    "pytest-cov>=7.0.0",
]

[tool.coverage.run]
omit = ["**/__init__.py", "**/tests/*", "dist/*", ".venv/*"]

[tool.coverage.report]
precision = 2
fail_under = 90

# src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/conftest.py
import pytest

from oracle.oci_iot_mcp_server.client import clear_iot_client_cache


@pytest.fixture(autouse=True)
def reset_iot_client_cache():
    clear_iot_client_cache()
    yield
    clear_iot_client_cache()

# src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/client.py
import os
from functools import lru_cache

import oci


def _resolved_profile_name(profile_name: str | None) -> str:
    return profile_name or os.getenv("OCI_CONFIG_PROFILE", "DEFAULT")


@lru_cache(maxsize=None)
def _build_iot_client(profile_name: str):
    config = oci.config.from_file(profile_name=profile_name)
    private_key = oci.signer.load_private_key_from_file(config["key_file"])
    with open(config["security_token_file"], "r") as token_file:
        token = token_file.read()
    signer = oci.auth.signers.SecurityTokenSigner(token, private_key)
    return oci.iot.IotClient(config, signer=signer)


def get_iot_client(profile_name: str | None = None):
    return _build_iot_client(_resolved_profile_name(profile_name))


def clear_iot_client_cache():
    _build_iot_client.cache_clear()


# src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/server.py
from .client import get_iot_client

# Delete from server.py:
# - the `_iot_client = None` global
# - the inline `get_iot_client(...)` implementation
# Keep the existing tool call sites unchanged so every current tool now uses the imported
# profile-aware client helper.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --directory src/oci-iot-mcp-server pytest oracle/oci_iot_mcp_server/tests/test_client.py -v`
Expected: PASS with `1 passed`

- [ ] **Step 5: Commit**

```bash
git add src/oci-iot-mcp-server/pyproject.toml
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/server.py
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/client.py
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/conftest.py
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_client.py
git commit -s -m "refactor: make iot client cache profile aware"
```

### Task 2: Add Stable Tool Envelope And Error Builders

**Files:**
- Create: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/errors.py`
- Create: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tool_models.py`
- Test: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_errors.py`

- [ ] **Step 1: Write the failing test**

```python
from oracle.oci_iot_mcp_server.errors import ambiguity_error
from oracle.oci_iot_mcp_server.tool_models import success_result


def test_ambiguity_error_returns_stable_payload():
    payload = ambiguity_error(
        resource_type="digital_twin_instance",
        message="Multiple digital twin instances matched display name 'pump-01'.",
        input_payload={"digital_twin_instance_name": "pump-01", "iot_domain_id": "ocid1.iotdomain.oc1..aaaa"},
        candidates=[{"id": "ocid1.digitaltwininstance.oc1..aaaa", "display_name": "pump-01"}],
    )

    assert payload["ok"] is False
    assert payload["error"]["code"] == "ambiguous_identifier"
    assert payload["error"]["details"]["candidates"][0]["display_name"] == "pump-01"


def test_success_result_wraps_tool_data():
    assert success_result({"id": "abc"}) == {"ok": True, "data": {"id": "abc"}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory src/oci-iot-mcp-server pytest oracle/oci_iot_mcp_server/tests/test_errors.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'oracle.oci_iot_mcp_server.errors'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tool_models.py
from pydantic import BaseModel, Field


class ToolErrorPayload(BaseModel):
    code: str
    message: str
    resource_type: str | None = None
    retry_hint: str | None = None
    details: dict = Field(default_factory=dict)


def success_result(data: dict) -> dict:
    return {"ok": True, "data": data}


# src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/errors.py
from .tool_models import ToolErrorPayload


def ambiguity_error(*, resource_type: str, message: str, input_payload: dict, candidates: list[dict]) -> dict:
    return {
        "ok": False,
        "error": ToolErrorPayload(
            code="ambiguous_identifier",
            message=message,
            resource_type=resource_type,
            retry_hint="Retry with the OCID of the intended resource.",
            details={"input": input_payload, "candidates": candidates},
        ).model_dump(exclude_none=True),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --directory src/oci-iot-mcp-server pytest oracle/oci_iot_mcp_server/tests/test_errors.py -v`
Expected: PASS with `2 passed`

- [ ] **Step 5: Commit**

```bash
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/errors.py
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tool_models.py
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_errors.py
git commit -s -m "feat: add stable iot tool result envelopes"
```

### Task 3: Split Control-Plane Access And Broaden Existing Resource Models

**Files:**
- Create: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/control_plane.py`
- Modify: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/models.py:11-214`
- Modify: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/server.py:90-493`
- Test: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_control_plane.py`

- [ ] **Step 1: Write the failing test**

```python
from types import SimpleNamespace

from oracle.oci_iot_mcp_server import server
from oracle.oci_iot_mcp_server.control_plane import (
    map_digital_twin_adapter,
    map_digital_twin_instance,
    map_iot_domain,
    map_iot_domain_group,
)


def test_map_iot_domain_includes_device_host_and_identity_domain_host():
    model = SimpleNamespace(
        id="ocid1.iotdomain.oc1..aaaa",
        display_name="factory-domain",
        device_host="abc123.device.iot.us-phoenix-1.oci.oraclecloud.com",
        db_allowed_identity_domain_host="id.example.com",
    )

    result = map_iot_domain(model)

    assert result["device_host"] == "abc123.device.iot.us-phoenix-1.oci.oraclecloud.com"
    assert result["db_allowed_identity_domain_host"] == "id.example.com"


def test_map_iot_domain_group_includes_data_host_and_db_token_scope():
    model = SimpleNamespace(
        id="ocid1.iotdomaingroup.oc1..aaaa",
        display_name="factory-group",
        data_host="xyz987.data.iot.us-phoenix-1.oci.oraclecloud.com",
        db_token_scope="ignored-by-ords-but-exposed",
    )

    result = map_iot_domain_group(model)

    assert result["data_host"].startswith("xyz987.data.iot.")
    assert result["db_token_scope"] == "ignored-by-ords-but-exposed"


def test_map_digital_twin_instance_includes_iot_domain_and_adapter_ids():
    model = SimpleNamespace(
        id="ocid1.digitaltwininstance.oc1..aaaa",
        display_name="pump-01",
        iot_domain_id="ocid1.iotdomain.oc1..aaaa",
        digital_twin_adapter_id="ocid1.digitaltwinadapter.oc1..aaaa",
    )

    result = map_digital_twin_instance(model)

    assert result["iot_domain_id"] == "ocid1.iotdomain.oc1..aaaa"
    assert result["digital_twin_adapter_id"] == "ocid1.digitaltwinadapter.oc1..aaaa"


def test_map_digital_twin_adapter_includes_model_spec_and_routes():
    model = SimpleNamespace(
        id="ocid1.digitaltwinadapter.oc1..aaaa",
        display_name="pump-adapter",
        digital_twin_model_id="ocid1.digitaltwinmodel.oc1..aaaa",
        digital_twin_model_spec_uri="https://example.com/spec.json",
        inbound_envelope={"type": "JSON"},
        inbound_routes=[{"messageType": "telemetry"}],
    )

    result = map_digital_twin_adapter(model)

    assert result["digital_twin_model_id"] == "ocid1.digitaltwinmodel.oc1..aaaa"
    assert result["digital_twin_model_spec_uri"] == "https://example.com/spec.json"
    assert result["inbound_routes"] == [{"messageType": "telemetry"}]


def test_server_get_iot_domain_delegates_to_control_plane(monkeypatch):
    monkeypatch.setattr(
        server,
        "get_iot_domain_record",
        lambda iot_domain_id: {"id": iot_domain_id, "device_host": "abc123.device.iot.us-phoenix-1.oci.oraclecloud.com"},
    )

    result = server.get_iot_domain("ocid1.iotdomain.oc1..aaaa")

    assert result["id"] == "ocid1.iotdomain.oc1..aaaa"
    assert result["device_host"].startswith("abc123.device.iot.")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory src/oci-iot-mcp-server pytest oracle/oci_iot_mcp_server/tests/test_control_plane.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'oracle.oci_iot_mcp_server.control_plane'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/control_plane.py
from .client import get_iot_client
from .models import DigitalTwinAdapterModel, DigitalTwinInstanceModel, IoTDomainGroupModel, IoTDomainModel


def map_iot_domain(model):
    return IoTDomainModel.from_oci_model(model).model_dump()


def map_iot_domain_group(model):
    return IoTDomainGroupModel.from_oci_model(model).model_dump()


def map_digital_twin_adapter(model):
    return DigitalTwinAdapterModel.from_oci_model(model).model_dump()


def map_digital_twin_instance(model):
    return DigitalTwinInstanceModel.from_oci_model(model).model_dump()


def get_iot_domain_record(iot_domain_id: str):
    return map_iot_domain(get_iot_client().get_iot_domain(iot_domain_id=iot_domain_id).data)


def get_digital_twin_instance_record(digital_twin_instance_id: str):
    return map_digital_twin_instance(
        get_iot_client().get_digital_twin_instance(digital_twin_instance_id=digital_twin_instance_id).data
    )


def get_digital_twin_adapter_record(digital_twin_adapter_id: str):
    return map_digital_twin_adapter(
        get_iot_client().get_digital_twin_adapter(digital_twin_adapter_id=digital_twin_adapter_id).data
    )


# src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/server.py
from .control_plane import get_digital_twin_adapter_record, get_digital_twin_instance_record, get_iot_domain_record
```

Update `server.py` so these existing MCP tools delegate into `control_plane.py` instead of calling `oci.iot.IotClient` directly:

- `get_digital_twin_adapter`
- `get_digital_twin_instance`
- `get_digital_twin_model`
- `get_digital_twin_relationship`
- `get_iot_domain`
- `get_iot_domain_group`
- `get_work_request`
- `list_digital_twin_adapters`
- `list_digital_twin_models`
- `list_digital_twin_instances`
- `list_digital_twin_relationships`
- `list_iot_domain_groups`
- `list_iot_domains`
- `list_work_request_errors`
- `list_work_request_logs`
- `list_work_requests`

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --directory src/oci-iot-mcp-server pytest oracle/oci_iot_mcp_server/tests/test_control_plane.py -v`
Expected: PASS with `5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/control_plane.py
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/models.py
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/server.py
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_control_plane.py
git commit -s -m "refactor: split iot control plane helpers"
```

## Chunk 2: Resolution And Data-Plane Foundations

### Task 4: Implement Selector Resolution And Domain-Context Derivation

**Files:**
- Modify: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/control_plane.py:1-220`
- Create: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/resolvers.py`
- Create: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/domain_context.py`
- Modify: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tool_models.py:1-120`
- Test: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_resolvers.py`
- Test: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_domain_context.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest

import oracle.oci_iot_mcp_server.resolvers as resolvers
from oracle.oci_iot_mcp_server.domain_context import derive_domain_context
from oracle.oci_iot_mcp_server.resolvers import resolve_domain_selector, resolve_twin_selector


def test_derive_domain_context_parses_short_ids_and_region():
    payload = derive_domain_context(
        iot_domain={"id": "domain-ocid", "name": "factory", "device_host": "abc123.device.iot.us-phoenix-1.oci.oraclecloud.com"},
        iot_domain_group={"id": "group-ocid", "name": "factory-group", "data_host": "xyz987.data.iot.us-phoenix-1.oci.oraclecloud.com", "db_token_scope": "dbscope"},
    )

    assert payload.domain_short_id == "abc123"
    assert payload.domain_group_short_id == "xyz987"
    assert payload.region == "us-phoenix-1"


def test_derive_domain_context_rejects_mismatched_regions():
    with pytest.raises(ValueError, match="share the same OCI region"):
        derive_domain_context(
            iot_domain={"id": "domain-ocid", "name": "factory", "device_host": "abc123.device.iot.us-phoenix-1.oci.oraclecloud.com"},
            iot_domain_group={"id": "group-ocid", "name": "factory-group", "data_host": "xyz987.data.iot.us-ashburn-1.oci.oraclecloud.com"},
        )


def test_resolve_domain_selector_returns_match_for_short_id(monkeypatch):
    monkeypatch.setattr(
        resolvers,
        "list_iot_domains_records",
        lambda compartment_id: [
            {
                "id": "domain-ocid",
                "name": "factory-domain",
                "device_host": "abc123.device.iot.us-phoenix-1.oci.oraclecloud.com",
            }
        ],
    )

    result = resolve_domain_selector(domain_short_id="abc123", compartment_id="ocid1.compartment.oc1..aaaa")

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

    result = resolve_twin_selector(digital_twin_instance_id="ocid1.digitaltwininstance.oc1..aaaa")

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
        "list_digital_twin_instances_records",
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
    assert [candidate["id"] for candidate in result["error"]["details"]["candidates"]] == ["twin-1", "twin-2"]


def test_resolve_domain_selector_requires_compartment_for_display_name():
    result = resolve_domain_selector(iot_domain_display_name="factory-domain")
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_input"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory src/oci-iot-mcp-server pytest oracle/oci_iot_mcp_server/tests/test_resolvers.py oracle/oci_iot_mcp_server/tests/test_domain_context.py -v`
Expected: FAIL with `ModuleNotFoundError` for `resolvers` or `domain_context`

- [ ] **Step 3: Write minimal implementation**

```python
# src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tool_models.py
from pydantic import BaseModel


class DomainContextModel(BaseModel):
    iot_domain_id: str
    iot_domain_display_name: str | None = None
    iot_domain_group_id: str
    iot_domain_group_display_name: str | None = None
    device_host: str
    data_host: str
    domain_short_id: str
    domain_group_short_id: str
    region: str
    db_token_scope: str | None = None
    db_allowed_identity_domain_host: str | None = None


# src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/control_plane.py
# Add these functions to the module created in Task 3, below the existing
# `get_iot_client`, `map_iot_domain`, and `map_digital_twin_instance` helpers.
def list_iot_domains_records(*, compartment_id: str):
    response = get_iot_client().list_iot_domains(compartment_id=compartment_id)
    return [map_iot_domain(item) for item in response.data.items]


def list_digital_twin_instances_records(*, iot_domain_id: str):
    response = get_iot_client().list_digital_twin_instances(iot_domain_id=iot_domain_id)
    return [map_digital_twin_instance(item) for item in response.data.items]


# src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/resolvers.py
from .control_plane import (
    get_digital_twin_instance_record,
    list_digital_twin_instances_records,
    list_iot_domains_records,
)
from .tool_models import ToolErrorPayload, success_result


def _error(*, code: str, message: str, resource_type: str, input_payload: dict, candidates: list[dict] | None = None, retry_hint: str | None = None):
    details = {"input": input_payload}
    if candidates:
        details["candidates"] = candidates
    return {
        "ok": False,
        "error": ToolErrorPayload(
            code=code,
            message=message,
            resource_type=resource_type,
            retry_hint=retry_hint,
            details=details,
        ).model_dump(exclude_none=True),
    }


def _first_label(host: str | None) -> str | None:
    return host.split(".", 1)[0] if host else None


def resolve_domain_selector(*, iot_domain_id: str | None = None, iot_domain_display_name: str | None = None, domain_short_id: str | None = None, compartment_id: str | None = None):
    if iot_domain_id:
        return success_result({"id": iot_domain_id})
    if not compartment_id:
        return _error(
            code="invalid_input",
            message="Friendly IoT domain lookup requires compartment_id.",
            resource_type="iot_domain",
            input_payload={"iot_domain_display_name": iot_domain_display_name, "domain_short_id": domain_short_id},
            retry_hint="Retry with iot_domain_id or include compartment_id.",
        )

    matches = []
    for row in list_iot_domains_records(compartment_id=compartment_id):
        if iot_domain_display_name and row.get("name") == iot_domain_display_name:
            matches.append(row)
        if domain_short_id and _first_label(row.get("device_host")) == domain_short_id:
            matches.append(row)

    unique_matches = list({row["id"]: row for row in matches}.values())
    if not unique_matches:
        return _error(
            code="resource_not_found",
            message="No IoT domain matched the provided selector.",
            resource_type="iot_domain",
            input_payload={"iot_domain_display_name": iot_domain_display_name, "domain_short_id": domain_short_id, "compartment_id": compartment_id},
        )
    if len(unique_matches) > 1:
        return _error(
            code="ambiguous_identifier",
            message="Multiple IoT domains matched the provided selector.",
            resource_type="iot_domain",
            input_payload={"iot_domain_display_name": iot_domain_display_name, "domain_short_id": domain_short_id, "compartment_id": compartment_id},
            candidates=[{"id": row["id"], "display_name": row.get("name")} for row in unique_matches],
            retry_hint="Retry with the OCID of the intended resource.",
        )
    return success_result(unique_matches[0])


def resolve_twin_selector(*, digital_twin_instance_id: str | None = None, digital_twin_instance_name: str | None = None, iot_domain_id: str | None = None):
    if digital_twin_instance_id:
        return success_result(
            get_digital_twin_instance_record(digital_twin_instance_id=digital_twin_instance_id)
        )
    if not iot_domain_id:
        return _error(
            code="invalid_input",
            message="Friendly digital twin lookup requires an IoT domain selector.",
            resource_type="digital_twin_instance",
            input_payload={"digital_twin_instance_name": digital_twin_instance_name},
            retry_hint="Retry with digital_twin_instance_id or include iot_domain_id.",
        )

    matches = [
        row
        for row in list_digital_twin_instances_records(iot_domain_id=iot_domain_id)
        if row.get("name") == digital_twin_instance_name
    ]
    if not matches:
        return _error(
            code="resource_not_found",
            message="No digital twin instance matched the provided selector.",
            resource_type="digital_twin_instance",
            input_payload={"digital_twin_instance_name": digital_twin_instance_name, "iot_domain_id": iot_domain_id},
        )
    if len(matches) > 1:
        return _error(
            code="ambiguous_identifier",
            message=f"Multiple digital twin instances matched display name '{digital_twin_instance_name}'.",
            resource_type="digital_twin_instance",
            input_payload={"digital_twin_instance_name": digital_twin_instance_name, "iot_domain_id": iot_domain_id},
            candidates=[{"id": row["id"], "display_name": row.get("name")} for row in matches],
            retry_hint="Retry with the OCID of the intended resource.",
        )
    return success_result(matches[0])


# src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/domain_context.py
from .tool_models import DomainContextModel


def _first_label(host: str) -> str:
    return host.split(".", 1)[0]


def _parse_region(host: str) -> str:
    return host.split(".iot.", 1)[1].split(".oci.oraclecloud.com", 1)[0]


def derive_domain_context(*, iot_domain: dict, iot_domain_group: dict):
    device_region = _parse_region(iot_domain["device_host"])
    data_region = _parse_region(iot_domain_group["data_host"])
    if device_region != data_region:
        raise ValueError("device_host and data_host must share the same OCI region.")
    return DomainContextModel(
        iot_domain_id=iot_domain["id"],
        iot_domain_display_name=iot_domain.get("name"),
        iot_domain_group_id=iot_domain_group["id"],
        iot_domain_group_display_name=iot_domain_group.get("name"),
        device_host=iot_domain["device_host"],
        data_host=iot_domain_group["data_host"],
        domain_short_id=_first_label(iot_domain["device_host"]),
        domain_group_short_id=_first_label(iot_domain_group["data_host"]),
        region=device_region,
        db_token_scope=iot_domain_group.get("db_token_scope"),
        db_allowed_identity_domain_host=iot_domain.get("db_allowed_identity_domain_host"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --directory src/oci-iot-mcp-server pytest oracle/oci_iot_mcp_server/tests/test_resolvers.py oracle/oci_iot_mcp_server/tests/test_domain_context.py -v`
Expected: PASS with all tests green

- [ ] **Step 5: Commit**

```bash
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/resolvers.py
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/domain_context.py
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tool_models.py
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_resolvers.py
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_domain_context.py
git commit -s -m "feat: add iot selector resolution"
```

### Task 5: Implement ORDS Token Minting And Paginated Data-Plane Reads

**Files:**
- Create: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/data_plane.py`
- Modify: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tool_models.py:1-220`
- Test: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_data_plane.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import UTC, datetime

import oracle.oci_iot_mcp_server.data_plane as data_plane
from oracle.oci_iot_mcp_server.data_plane import (
    build_ords_base_url,
    build_twin_filter,
    encode_q,
    list_collection_records,
    mint_data_api_token,
    require_token_credentials,
)


def test_build_ords_base_url_uses_domain_group_host_and_domain_short_id():
    result = build_ords_base_url(
        {
            "data_host": "xyz987.data.iot.us-phoenix-1.oci.oraclecloud.com",
            "domain_short_id": "abc123",
        }
    )

    assert result == "https://xyz987.data.iot.us-phoenix-1.oci.oraclecloud.com/ords/abc123/20250531"


def test_mint_data_api_token_uses_password_grant_and_scope(monkeypatch):
    class FakeResponse:
        def json(self):
            return {"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600}

    monkeypatch.setattr(data_plane.httpx, "post", lambda *args, **kwargs: FakeResponse())

    context = {
        "domain_short_id": "abc123",
        "domain_group_short_id": "xyz987",
        "db_allowed_identity_domain_host": "id.example.com",
    }

    result = mint_data_api_token(
        domain_context=context,
        env={
            "OCI_IOT_ORDS_CLIENT_ID": "client-id",
            "OCI_IOT_ORDS_CLIENT_SECRET": "client-secret",
            "OCI_IOT_ORDS_USERNAME": "iot.user@example.com",
            "OCI_IOT_ORDS_PASSWORD": "secret-password",
        },
        now=lambda: datetime(2026, 3, 26, 12, 0, 0, tzinfo=UTC),
    )

    assert result.access_token == "token-123"
    assert result.expires_at.isoformat() == "2026-03-26T13:00:00+00:00"
    assert build_twin_filter("ocid1.digitaltwininstance.oc1..aaaa") == {"$and": [{"digital_twin_instance_id": "ocid1.digitaltwininstance.oc1..aaaa"}]}
    assert encode_q(build_twin_filter("ocid1.digitaltwininstance.oc1..aaaa")) == '{"$and":[{"digital_twin_instance_id":"ocid1.digitaltwininstance.oc1..aaaa"}]}'


def test_require_token_credentials_returns_structured_error_for_missing_env():
    result = require_token_credentials({"OCI_IOT_ORDS_CLIENT_ID": "client-id"})

    assert result["ok"] is False
    assert result["error"]["code"] == "missing_token_credentials"
    assert result["error"]["details"]["missing"] == [
        "OCI_IOT_ORDS_CLIENT_SECRET",
        "OCI_IOT_ORDS_USERNAME",
        "OCI_IOT_ORDS_PASSWORD",
    ]


def test_require_token_credentials_returns_sanitized_success_payload():
    result = require_token_credentials(
        {
            "OCI_IOT_ORDS_CLIENT_ID": "client-id",
            "OCI_IOT_ORDS_CLIENT_SECRET": "client-secret",
            "OCI_IOT_ORDS_USERNAME": "iot.user@example.com",
            "OCI_IOT_ORDS_PASSWORD": "secret-password",
        }
    )

    assert result == {
        "ok": True,
        "data": {
            "present": [
                "OCI_IOT_ORDS_CLIENT_ID",
                "OCI_IOT_ORDS_CLIENT_SECRET",
                "OCI_IOT_ORDS_USERNAME",
                "OCI_IOT_ORDS_PASSWORD",
            ],
            "missing": [],
        },
    }


def test_list_collection_records_uses_limit_offset_until_target_count(monkeypatch):
    observed_params = []
    pages = iter([
        {"items": [{"id": "1"}, {"id": "2"}]},
        {"items": [{"id": "3"}]},
    ])

    monkeypatch.setattr(
        data_plane,
        "_get_json",
        lambda **kwargs: observed_params.append(kwargs["params"]) or next(pages),
    )

    records = list_collection_records(
        base_url="https://xyz987.data.iot.us-phoenix-1.oci.oraclecloud.com/ords/abc123/20250531",
        path="/rawCommandData",
        token="token-123",
        params={"q": '{"$and":[{"digital_twin_instance_id":"ocid1.digitaltwininstance.oc1..aaaa"}]}'},
        target_count=3,
    )

    assert [record["id"] for record in records] == ["1", "2", "3"]
    assert observed_params == [
        {
            "q": '{"$and":[{"digital_twin_instance_id":"ocid1.digitaltwininstance.oc1..aaaa"}]}',
            "limit": 3,
            "offset": 0,
        },
        {
            "q": '{"$and":[{"digital_twin_instance_id":"ocid1.digitaltwininstance.oc1..aaaa"}]}',
            "limit": 3,
            "offset": 2,
        },
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory src/oci-iot-mcp-server pytest oracle/oci_iot_mcp_server/tests/test_data_plane.py::test_mint_data_api_token_uses_password_grant_and_scope -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'oracle.oci_iot_mcp_server.data_plane'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tool_models.py
from datetime import datetime

from pydantic import BaseModel


class DataApiTokenModel(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    expires_at: datetime


# src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/data_plane.py
import base64
from datetime import timedelta
import json

import httpx

from .tool_models import DataApiTokenModel, ToolErrorPayload, success_result

ORDS_API_DATE = "20250531"


def build_ords_base_url(domain_context: dict) -> str:
    return f"https://{domain_context['data_host']}/ords/{domain_context['domain_short_id']}/{ORDS_API_DATE}"


def build_twin_filter(digital_twin_instance_id: str) -> dict:
    return {"$and": [{"digital_twin_instance_id": digital_twin_instance_id}]}


def encode_q(filter_payload: dict) -> str:
    return json.dumps(filter_payload, separators=(",", ":"))


def require_token_credentials(env: dict):
    required = [
        "OCI_IOT_ORDS_CLIENT_ID",
        "OCI_IOT_ORDS_CLIENT_SECRET",
        "OCI_IOT_ORDS_USERNAME",
        "OCI_IOT_ORDS_PASSWORD",
    ]
    missing = [name for name in required if not env.get(name)]
    if missing:
        return {
            "ok": False,
            "error": ToolErrorPayload(
                code="missing_token_credentials",
                message="Missing one or more OCI IoT ORDS credential environment variables.",
                retry_hint="Set the missing OCI_IOT_ORDS_* environment variables and retry.",
                details={"missing": missing},
            ).model_dump(exclude_none=True),
        }
    return success_result({"present": required, "missing": []})


def mint_data_api_token(*, domain_context: dict, env: dict, now):
    scope = f"/{domain_context['domain_group_short_id']}/iot/{domain_context['domain_short_id']}"
    auth = base64.b64encode(f"{env['OCI_IOT_ORDS_CLIENT_ID']}:{env['OCI_IOT_ORDS_CLIENT_SECRET']}".encode()).decode()
    response = httpx.post(
        f"https://{domain_context['db_allowed_identity_domain_host']}/oauth2/v1/token",
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "password",
            "username": env["OCI_IOT_ORDS_USERNAME"],
            "password": env["OCI_IOT_ORDS_PASSWORD"],
            "scope": scope,
        },
        timeout=30.0,
    )
    payload = response.json()
    minted_at = now()
    return DataApiTokenModel(
        access_token=payload["access_token"],
        token_type=payload["token_type"],
        expires_in=payload["expires_in"],
        expires_at=minted_at + timedelta(seconds=payload["expires_in"]),
    )


def _get_json(*, url: str, token: str, params: dict):
    response = httpx.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def list_collection_records(*, base_url: str, path: str, token: str, params: dict, target_count: int):
    records = []
    offset = 0
    scanned = 0
    while len(records) < target_count and scanned < 500:
        page = _get_json(
            url=f"{base_url}{path}",
            token=token,
            params={**params, "limit": min(100, target_count), "offset": offset},
        )
        items = page.get("items", [])
        if not items:
            break
        records.extend(items)
        offset += len(items)
        scanned += len(items)
    return records[:target_count]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --directory src/oci-iot-mcp-server pytest oracle/oci_iot_mcp_server/tests/test_data_plane.py -v`
Expected: PASS with the token and pagination tests green

- [ ] **Step 5: Commit**

```bash
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/data_plane.py
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tool_models.py
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_data_plane.py
git commit -s -m "feat: add iot data plane client"
```

### Task 6: Add Shared Polling Helpers For Raw Commands And Snapshot Updates

**Files:**
- Create: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/polling.py`
- Test: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_polling.py`

- [ ] **Step 1: Write the failing test**

```python
from oracle.oci_iot_mcp_server.polling import wait_for_raw_command_terminal_state, wait_for_snapshot_update


def test_wait_for_raw_command_terminal_state_returns_latest_record_on_timeout():
    observed = [{"id": "rc-1", "delivery_status": "PENDING", "time_updated": "2026-03-26T12:00:01Z"}]
    ticks = iter([0.0, 1.1, 1.1])

    result = wait_for_raw_command_terminal_state(
        fetch_detail=lambda _: observed[-1],
        record_id="rc-1",
        timeout_seconds=1,
        sleep=lambda _: None,
        monotonic=lambda: next(ticks),
    )

    assert result["timed_out"] is True
    assert result["raw_command"]["id"] == "rc-1"


def test_wait_for_snapshot_update_returns_first_record_after_since():
    rows = iter([
        [{"digital_twin_instance_id": "ocid1.digitaltwininstance.oc1..aaaa", "content_path": "temperature", "value": 71, "time_observed": "2026-03-26T11:59:59Z"}],
        [{"digital_twin_instance_id": "ocid1.digitaltwininstance.oc1..aaaa", "content_path": "temperature", "value": 72, "time_observed": "2026-03-26T12:00:05Z"}],
    ])
    ticks = iter([0.0, 0.2, 0.4, 2.1])

    result = wait_for_snapshot_update(
        fetch_rows=lambda: next(rows),
        since="2026-03-26T12:00:00Z",
        timeout_seconds=2,
        sleep=lambda _: None,
        monotonic=lambda: next(ticks),
    )

    assert result["content_path"] == "temperature"
    assert result["value"] == 72
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory src/oci-iot-mcp-server pytest oracle/oci_iot_mcp_server/tests/test_polling.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'oracle.oci_iot_mcp_server.polling'`

- [ ] **Step 3: Write minimal implementation**

```python
from datetime import datetime

RAW_COMMAND_TERMINAL_SUCCESS = {"COMPLETED"}
RAW_COMMAND_TERMINAL_FAILURE = {"REFUSED", "EXPIRED", "NOT_RESPONDED", "REJECTED", "BAD_RESPONSE"}


def _parse_rfc3339(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def wait_for_raw_command_terminal_state(*, fetch_detail, record_id: str, timeout_seconds: int, sleep, monotonic):
    deadline = monotonic() + timeout_seconds
    latest = None
    while monotonic() < deadline:
        latest = fetch_detail(record_id)
        status = latest["delivery_status"]
        if status in RAW_COMMAND_TERMINAL_SUCCESS | RAW_COMMAND_TERMINAL_FAILURE:
            return {"timed_out": False, "raw_command": latest}
        sleep(2)
    return {"timed_out": True, "raw_command": latest}


def wait_for_snapshot_update(*, fetch_rows, since: str, timeout_seconds: int, sleep, monotonic):
    deadline = monotonic() + timeout_seconds
    observed_after = _parse_rfc3339(since)
    while monotonic() < deadline:
        rows = fetch_rows()
        for row in rows:
            if _parse_rfc3339(row["time_observed"]) > observed_after:
                return row
        sleep(2)
    return {"timed_out": True}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --directory src/oci-iot-mcp-server pytest oracle/oci_iot_mcp_server/tests/test_polling.py -v`
Expected: PASS with polling tests green

- [ ] **Step 5: Commit**

```bash
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/polling.py
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_polling.py
git commit -s -m "feat: add iot polling helpers"
```

## Chunk 3: New Tools, Docs, And Verification

### Task 7: Add `get_digital_twin_adapter_full`, `derive_domain_context`, And `get_data_api_token`

**Files:**
- Modify: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/server.py:90-514`
- Test: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_server_phase1_tools.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import UTC, datetime

from oracle.oci_iot_mcp_server import server
from oracle.oci_iot_mcp_server.tool_models import DataApiTokenModel


def test_get_digital_twin_adapter_full_wraps_full_adapter_record(monkeypatch):
    monkeypatch.setattr(
        server,
        "get_digital_twin_adapter_record",
        lambda digital_twin_adapter_id: {
            "id": digital_twin_adapter_id,
            "digital_twin_model_id": "ocid1.digitaltwinmodel.oc1..aaaa",
            "digital_twin_model_spec_uri": "https://example.com/spec.json",
            "inbound_routes": [{"messageType": "telemetry"}],
        },
    )

    result = server.get_digital_twin_adapter_full("ocid1.digitaltwinadapter.oc1..aaaa")

    assert result["ok"] is True
    assert result["data"]["digital_twin_model_id"] == "ocid1.digitaltwinmodel.oc1..aaaa"


def test_derive_domain_context_returns_success_envelope(monkeypatch):
    monkeypatch.setattr(
        server,
        "resolve_domain_context_for_tool",
        lambda **_: {"iot_domain_id": "domain-ocid", "domain_short_id": "abc123", "region": "us-phoenix-1"},
    )

    result = server.derive_domain_context(iot_domain_id="domain-ocid")

    assert result == {
        "ok": True,
        "data": {"iot_domain_id": "domain-ocid", "domain_short_id": "abc123", "region": "us-phoenix-1"},
    }


def test_get_data_api_token_passes_through_structured_configuration_error(monkeypatch):
    monkeypatch.setattr(
        server,
        "get_data_api_token_impl",
        lambda **_: {
            "ok": False,
            "error": {
                "code": "missing_token_credentials",
                "message": "Missing one or more OCI IoT ORDS credential environment variables.",
            },
        },
    )

    result = server.get_data_api_token(iot_domain_id="domain-ocid")

    assert result["ok"] is False
    assert result["error"]["code"] == "missing_token_credentials"


def test_get_data_api_token_wraps_success_payload(monkeypatch):
    monkeypatch.setattr(
        server,
        "get_data_api_token_impl",
        lambda **_: {
            "access_token": "token-123",
            "token_type": "Bearer",
            "expires_at": "2026-03-26T13:00:00Z",
            "expires_in": 3600,
            "iot_domain_id": "domain-ocid",
        },
    )

    result = server.get_data_api_token(iot_domain_id="domain-ocid")

    assert result["ok"] is True
    assert result["data"]["access_token"] == "token-123"
    assert result["data"]["expires_at"] == "2026-03-26T13:00:00Z"


def test_get_data_api_token_serializes_nested_pydantic_payload(monkeypatch):
    monkeypatch.setattr(
        server,
        "get_data_api_token_impl",
        lambda **_: {
            "token": DataApiTokenModel(
                access_token="token-123",
                token_type="Bearer",
                expires_in=3600,
                expires_at=datetime(2026, 3, 26, 13, 0, 0, tzinfo=UTC),
            ),
            "iot_domain_id": "domain-ocid",
        },
    )

    result = server.get_data_api_token(iot_domain_id="domain-ocid")

    assert result["ok"] is True
    assert result["data"]["token"]["expires_at"] == "2026-03-26T13:00:00Z"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory src/oci-iot-mcp-server pytest oracle/oci_iot_mcp_server/tests/test_server_phase1_tools.py -k 'adapter_full or derive_domain_context or data_api_token' -v`
Expected: FAIL with `AttributeError` for one or more of `get_digital_twin_adapter_full`, `derive_domain_context`, or `get_data_api_token`

- [ ] **Step 3: Write minimal implementation**

```python
# server.py imports used below:
# from .control_plane import get_digital_twin_adapter_record
# from typing import Any
# from pydantic import TypeAdapter
# from .tool_models import ToolErrorPayload, success_result

JSON_ADAPTER = TypeAdapter(Any)


def _as_tool_result(payload):
    if isinstance(payload, dict) and payload.get("ok") is False:
        return payload
    return success_result(JSON_ADAPTER.dump_python(payload, mode="json"))


@mcp.tool(description="Return the full mapped digital twin adapter payload for debugging and migration workflows.")
def get_digital_twin_adapter_full(
    digital_twin_adapter_id: Annotated[str, "The digital twin adapter OCID"],
):
    return _as_tool_result(get_digital_twin_adapter_record(digital_twin_adapter_id))


@mcp.tool(description="Derive normalized IoT domain context for ORDS and operator workflows.")
def derive_domain_context(
    iot_domain_id: Annotated[str | None, "The IoT domain OCID"] = None,
    iot_domain_display_name: Annotated[str | None, "The IoT domain display name"] = None,
    domain_short_id: Annotated[str | None, "The IoT domain short ID"] = None,
    compartment_id: Annotated[str | None, "Compartment OCID for friendly domain lookup"] = None,
):
    context = resolve_domain_context_for_tool(
        iot_domain_id=iot_domain_id,
        iot_domain_display_name=iot_domain_display_name,
        domain_short_id=domain_short_id,
        compartment_id=compartment_id,
    )
    return _as_tool_result(context)


@mcp.tool(description="Mint and return an IoT Data API bearer token plus the resolved domain context.")
def get_data_api_token(
    iot_domain_id: Annotated[str | None, "The IoT domain OCID"] = None,
    iot_domain_display_name: Annotated[str | None, "The IoT domain display name"] = None,
    domain_short_id: Annotated[str | None, "The IoT domain short ID"] = None,
    compartment_id: Annotated[str | None, "Compartment OCID for friendly domain lookup"] = None,
):
    token_payload = get_data_api_token_impl(
        iot_domain_id=iot_domain_id,
        iot_domain_display_name=iot_domain_display_name,
        domain_short_id=domain_short_id,
        compartment_id=compartment_id,
    )
    return _as_tool_result(token_payload)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --directory src/oci-iot-mcp-server pytest oracle/oci_iot_mcp_server/tests/test_server_phase1_tools.py -v`
Expected: PASS with the adapter-full, domain-context, and token-tool tests green

- [ ] **Step 5: Commit**

```bash
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/server.py
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_server_phase1_tools.py
git commit -s -m "feat: add iot domain context and token tools"
```

### Task 8: Add `get_raw_command_by_request_id` And `list_recent_raw_commands_for_twin`

**Files:**
- Modify: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/server.py:90-514`
- Test: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_server_phase1_tools.py`

- [ ] **Step 1: Write the failing test**

```python
from oracle.oci_iot_mcp_server import server


def test_get_raw_command_by_request_id_wraps_detail_record(monkeypatch):
    monkeypatch.setattr(
        server,
        "get_raw_command_by_request_id_impl",
        lambda **_: {
            "id": "rc-1",
            "digital_twin_instance_id": "ocid1.digitaltwininstance.oc1..aaaa",
            "delivery_status": "COMPLETED",
        },
    )

    result = server.get_raw_command_by_request_id(
        request_id="rc-1",
        digital_twin_instance_id="ocid1.digitaltwininstance.oc1..aaaa",
    )

    assert result["ok"] is True
    assert result["data"]["id"] == "rc-1"


def test_list_recent_raw_commands_for_twin_sorts_by_time_created_desc(monkeypatch):
    monkeypatch.setattr(
        server,
        "list_recent_raw_commands_for_twin_impl",
        lambda **_: [
            {"id": "rc-older", "time_created": "2026-03-26T11:59:59Z"},
            {"id": "rc-newer", "time_created": "2026-03-26T12:00:01Z"},
        ],
    )

    result = server.list_recent_raw_commands_for_twin(
        digital_twin_instance_id="ocid1.digitaltwininstance.oc1..aaaa",
        limit=20,
    )

    assert result["ok"] is True
    assert result["data"][0]["id"] == "rc-newer"


def test_list_recent_raw_commands_for_twin_rejects_limit_above_100():
    result = server.list_recent_raw_commands_for_twin(
        digital_twin_instance_id="ocid1.digitaltwininstance.oc1..aaaa",
        limit=101,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_input"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory src/oci-iot-mcp-server pytest oracle/oci_iot_mcp_server/tests/test_server_phase1_tools.py -k 'raw_command_by_request_id or recent_raw_commands' -v`
Expected: FAIL with `AttributeError` because one or both new raw-command lookup tools are not defined yet

- [ ] **Step 3: Write minimal implementation**

```python
def _limit_error(*, field_name: str, value: int):
    if 1 <= value <= 100:
        return None
    return {
        "ok": False,
        "error": ToolErrorPayload(
            code="invalid_input",
            message=f"{field_name} must be between 1 and 100.",
            retry_hint=f"Retry with {field_name} set between 1 and 100.",
            details={field_name: value},
        ).model_dump(exclude_none=True),
    }


@mcp.tool(description="Fetch the raw command detail record for an ORDS request ID.")
def get_raw_command_by_request_id(
    request_id: Annotated[str, "The IoT Data API raw command record ID"],
    iot_domain_id: Annotated[str | None, "The IoT domain OCID"] = None,
    iot_domain_display_name: Annotated[str | None, "The IoT domain display name"] = None,
    domain_short_id: Annotated[str | None, "The IoT domain short ID"] = None,
    compartment_id: Annotated[str | None, "Compartment OCID for friendly domain lookup"] = None,
    digital_twin_instance_id: Annotated[str | None, "Optional digital twin OCID for validation"] = None,
    digital_twin_instance_name: Annotated[str | None, "Optional digital twin display name for validation"] = None,
    since: Annotated[str | None, "Optional RFC 3339 lower bound for validation"] = None,
    until: Annotated[str | None, "Optional RFC 3339 upper bound for validation"] = None,
):
    return _as_tool_result(
        get_raw_command_by_request_id_impl(
            request_id=request_id,
            iot_domain_id=iot_domain_id,
            iot_domain_display_name=iot_domain_display_name,
            domain_short_id=domain_short_id,
            compartment_id=compartment_id,
            digital_twin_instance_id=digital_twin_instance_id,
            digital_twin_instance_name=digital_twin_instance_name,
            since=since,
            until=until,
        )
    )


@mcp.tool(description="List recent raw command records for a digital twin instance.")
def list_recent_raw_commands_for_twin(
    digital_twin_instance_id: Annotated[str | None, "The digital twin instance OCID"] = None,
    digital_twin_instance_name: Annotated[str | None, "The digital twin instance display name"] = None,
    iot_domain_id: Annotated[str | None, "Required when using a twin display name"] = None,
    limit: Annotated[int, "Maximum records to return"] = 20,
):
    limit_error = _limit_error(field_name="limit", value=limit)
    if limit_error:
        return limit_error
    rows = list_recent_raw_commands_for_twin_impl(
        digital_twin_instance_id=digital_twin_instance_id,
        digital_twin_instance_name=digital_twin_instance_name,
        iot_domain_id=iot_domain_id,
        limit=limit,
    )
    if isinstance(rows, dict) and rows.get("ok") is False:
        return rows
    ordered = sorted(rows, key=lambda row: row["time_created"], reverse=True)
    return success_result(ordered[:limit])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --directory src/oci-iot-mcp-server pytest oracle/oci_iot_mcp_server/tests/test_server_phase1_tools.py -v`
Expected: PASS with raw-command lookup tests green

- [ ] **Step 5: Commit**

```bash
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/server.py
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_server_phase1_tools.py
git commit -s -m "feat: add raw command lookup tools"
```

### Task 9: Add `invoke_raw_command_and_wait`

**Files:**
- Modify: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/server.py:90-514`
- Test: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_server_phase1_tools.py`

- [ ] **Step 1: Write the failing test**

```python
from oracle.oci_iot_mcp_server import server


def test_invoke_raw_command_and_wait_wraps_terminal_record(monkeypatch):
    monkeypatch.setattr(
        server,
        "invoke_raw_command_and_wait_impl",
        lambda **_: {
            "request_id": "rc-1",
            "timed_out": False,
            "raw_command": {"id": "rc-1", "delivery_status": "COMPLETED"},
        },
    )

    result = server.invoke_raw_command_and_wait(
        digital_twin_instance_id="ocid1.digitaltwininstance.oc1..aaaa",
        request_endpoint="/v1/cmd",
        request_data_format="TEXT",
        request_data="PING",
        timeout=30,
    )

    assert result["ok"] is True
    assert result["data"]["request_id"] == "rc-1"
    assert result["data"]["raw_command"]["delivery_status"] == "COMPLETED"


def test_invoke_raw_command_and_wait_passes_through_recoverable_error(monkeypatch):
    monkeypatch.setattr(
        server,
        "invoke_raw_command_and_wait_impl",
        lambda **_: {
            "ok": False,
            "error": {
                "code": "ambiguous_identifier",
                "message": "Multiple raw command records matched the invoke request.",
            },
        },
    )

    result = server.invoke_raw_command_and_wait(
        digital_twin_instance_id="ocid1.digitaltwininstance.oc1..aaaa",
        request_endpoint="/v1/cmd",
        request_data_format="TEXT",
        request_data="PING",
        timeout=30,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "ambiguous_identifier"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory src/oci-iot-mcp-server pytest oracle/oci_iot_mcp_server/tests/test_server_phase1_tools.py -k 'invoke_raw_command_and_wait' -v`
Expected: FAIL with `AttributeError` because the new tool is not defined yet

- [ ] **Step 3: Write minimal implementation**

```python
@mcp.tool(description="Invoke a raw command on a digital twin instance and wait for a terminal data-plane result.")
def invoke_raw_command_and_wait(
    digital_twin_instance_id: Annotated[str | None, "The digital twin instance OCID"] = None,
    digital_twin_instance_name: Annotated[str | None, "The digital twin instance display name"] = None,
    iot_domain_id: Annotated[str | None, "Required when using a twin display name"] = None,
    request_endpoint: Annotated[str, "Device endpoint for the outbound request"] = "",
    request_data_format: Annotated[str, "TEXT, JSON, or BINARY"] = "TEXT",
    request_data: Annotated[object, "Request payload"] = "",
    response_endpoint: Annotated[str | None, "Optional response endpoint"] = None,
    request_duration: Annotated[str | None, "Request duration string"] = None,
    response_duration: Annotated[str | None, "Response duration string"] = None,
    timeout: Annotated[int, "Maximum seconds to wait for a terminal result"] = 30,
):
    result = invoke_raw_command_and_wait_impl(
        digital_twin_instance_id=digital_twin_instance_id,
        digital_twin_instance_name=digital_twin_instance_name,
        iot_domain_id=iot_domain_id,
        request_endpoint=request_endpoint,
        request_data_format=request_data_format,
        request_data=request_data,
        response_endpoint=response_endpoint,
        request_duration=request_duration,
        response_duration=response_duration,
        timeout=timeout,
    )
    return _as_tool_result(result)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --directory src/oci-iot-mcp-server pytest oracle/oci_iot_mcp_server/tests/test_server_phase1_tools.py -v`
Expected: PASS with the invoke/wait tests green

- [ ] **Step 5: Commit**

```bash
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/server.py
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_server_phase1_tools.py
git commit -s -m "feat: add invoke raw command wait tool"
```

### Task 10: Add `wait_for_twin_update` And `list_recent_rejected_data_for_twin`

**Files:**
- Modify: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/server.py:90-514`
- Test: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_server_phase2_tools.py`

- [ ] **Step 1: Write the failing test**

```python
from oracle.oci_iot_mcp_server import server


def test_wait_for_twin_update_returns_first_matching_content_path(monkeypatch):
    monkeypatch.setattr(
        server,
        "wait_for_twin_update_impl",
        lambda **_: {"digital_twin_instance_id": "ocid1.digitaltwininstance.oc1..aaaa", "content_path": "temperature", "value": 72, "time_observed": "2026-03-26T12:00:05Z"},
    )

    result = server.wait_for_twin_update(
        digital_twin_instance_id="ocid1.digitaltwininstance.oc1..aaaa",
        content_path="temperature",
        since="2026-03-26T12:00:00Z",
        timeout=30,
    )

    assert result["ok"] is True
    assert result["data"]["content_path"] == "temperature"


def test_wait_for_twin_update_requires_since():
    result = server.wait_for_twin_update(
        digital_twin_instance_id="ocid1.digitaltwininstance.oc1..aaaa",
        since="",
        timeout=30,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_input"


def test_list_recent_rejected_data_for_twin_sorts_by_time_received_desc(monkeypatch):
    monkeypatch.setattr(
        server,
        "list_recent_rejected_data_for_twin_impl",
        lambda **_: [
            {"id": "r-older", "time_received": "2026-03-26T11:59:59Z"},
            {"id": "r-newer", "time_received": "2026-03-26T12:00:01Z"},
        ],
    )

    result = server.list_recent_rejected_data_for_twin(
        digital_twin_instance_id="ocid1.digitaltwininstance.oc1..aaaa",
        limit=20,
    )

    assert result["ok"] is True
    assert result["data"][0]["id"] == "r-newer"


def test_list_recent_rejected_data_for_twin_rejects_limit_above_100():
    result = server.list_recent_rejected_data_for_twin(
        digital_twin_instance_id="ocid1.digitaltwininstance.oc1..aaaa",
        limit=101,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_input"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory src/oci-iot-mcp-server pytest oracle/oci_iot_mcp_server/tests/test_server_phase2_tools.py -v`
Expected: FAIL with `AttributeError` because the new tools are not defined yet

- [ ] **Step 3: Write minimal implementation**

```python
@mcp.tool(description="Wait for a twin snapshot update after a given timestamp.")
def wait_for_twin_update(
    digital_twin_instance_id: Annotated[str | None, "The digital twin instance OCID"] = None,
    digital_twin_instance_name: Annotated[str | None, "The digital twin instance display name"] = None,
    iot_domain_id: Annotated[str | None, "Required when using a twin display name"] = None,
    content_path: Annotated[str | None, "Optional exact snapshot content path"] = None,
    since: Annotated[str, "RFC 3339 timestamp"] = "",
    timeout: Annotated[int, "Maximum seconds to wait"] = 30,
):
    if not since:
        return {
            "ok": False,
            "error": ToolErrorPayload(
                code="invalid_input",
                message="since is required and must be an RFC 3339 timestamp.",
                retry_hint="Retry with since set to an RFC 3339 timestamp.",
                details={"since": since},
            ).model_dump(exclude_none=True),
        }
    return _as_tool_result(
        wait_for_twin_update_impl(
            digital_twin_instance_id=digital_twin_instance_id,
            digital_twin_instance_name=digital_twin_instance_name,
            iot_domain_id=iot_domain_id,
            content_path=content_path,
            since=since,
            timeout=timeout,
        )
    )


@mcp.tool(description="List recent rejected ingest records for a digital twin instance.")
def list_recent_rejected_data_for_twin(
    digital_twin_instance_id: Annotated[str | None, "The digital twin instance OCID"] = None,
    digital_twin_instance_name: Annotated[str | None, "The digital twin instance display name"] = None,
    iot_domain_id: Annotated[str | None, "Required when using a twin display name"] = None,
    limit: Annotated[int, "Maximum records to return"] = 20,
    since: Annotated[str | None, "Optional RFC 3339 lower bound"] = None,
    until: Annotated[str | None, "Optional RFC 3339 upper bound"] = None,
):
    limit_error = _limit_error(field_name="limit", value=limit)
    if limit_error:
        return limit_error
    rows = list_recent_rejected_data_for_twin_impl(
        digital_twin_instance_id=digital_twin_instance_id,
        digital_twin_instance_name=digital_twin_instance_name,
        iot_domain_id=iot_domain_id,
        limit=limit,
        since=since,
        until=until,
    )
    if isinstance(rows, dict) and rows.get("ok") is False:
        return rows
    ordered = sorted(rows, key=lambda row: row["time_received"], reverse=True)
    return _as_tool_result(ordered[:limit])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --directory src/oci-iot-mcp-server pytest oracle/oci_iot_mcp_server/tests/test_server_phase2_tools.py -v`
Expected: PASS with the twin-update and rejected-data tests green

- [ ] **Step 5: Commit**

```bash
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/server.py
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_server_phase2_tools.py
git commit -s -m "feat: add twin update and rejected data tools"
```

### Task 11: Finish Documentation, Health Versioning, And Final Verification

**Files:**
- Modify: `src/oci-iot-mcp-server/README.md:13-42`
- Modify: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/health.py:5-26`
- Test: `src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_health.py`
- Create: `tests/e2e/features/oci-iot-mcp-server.feature`

- [ ] **Step 1: Write the failing test**

```python
import oracle.oci_iot_mcp_server.health as health


def test_health_check_uses_imported_version_constant(monkeypatch):
    monkeypatch.setattr(health, "__version__", "9.9.9", raising=False)
    assert health.health_check()["version"] == "9.9.9"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory src/oci-iot-mcp-server pytest oracle/oci_iot_mcp_server/tests/test_health.py -v`
Expected: FAIL because `health_check()` still returns the hardcoded `"1.0.0"` string

- [ ] **Step 3: Write minimal implementation**

```python
# src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/health.py
from . import __version__


def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "service": "oci-iot-mcp-server",
        "version": __version__,
    }
```

```markdown
<!-- src/oci-iot-mcp-server/README.md -->
## New Tools

- `get_digital_twin_adapter_full`
- `derive_domain_context`
- `get_data_api_token`
- `get_raw_command_by_request_id`
- `list_recent_raw_commands_for_twin`
- `invoke_raw_command_and_wait`
- `wait_for_twin_update`
- `list_recent_rejected_data_for_twin`

## Friendly Identifier Rules

- `digital_twin_instance_id` and `iot_domain_id` work directly.
- Twin display-name lookup requires an IoT domain selector.
- Domain display-name lookup and `domain_short_id` lookup require `compartment_id`.
- Ambiguous friendly matches fail with `ambiguous_identifier` and list candidate OCIDs and names.

## ORDS Credentials And Token Behavior

- Required environment variables:
  - `OCI_IOT_ORDS_CLIENT_ID`
  - `OCI_IOT_ORDS_CLIENT_SECRET`
  - `OCI_IOT_ORDS_USERNAME`
  - `OCI_IOT_ORDS_PASSWORD`
- `get_data_api_token` returns a live bearer token and expiry metadata to the MCP caller.
- Treat the returned bearer token as a secret and do not log, persist, or echo it beyond the intended caller.
- Tokens are minted in-memory per call, are not cached across tool invocations, and must never be logged.
```

```gherkin
# tests/e2e/features/oci-iot-mcp-server.feature
Feature: OCI IoT MCP server high-value flows

  Scenario: Invoke a raw command and wait for an observed outcome
    Given the OCI IoT MCP server package is installed
    And the OCI IoT e2e environment is configured
    When I invoke "invoke_raw_command_and_wait" for the configured digital twin
    Then the response should have "ok" equal to true
    And the response data should include "request_id"

  Scenario: List recent raw commands for a configured twin
    Given the OCI IoT MCP server package is installed
    And the OCI IoT e2e environment is configured
    When I invoke "list_recent_raw_commands_for_twin" for the configured digital twin
    Then the response should have "ok" equal to true
    And the response data should be a list
```

- [ ] **Step 4: Run final verification**

Run: `uv run --directory src/oci-iot-mcp-server pytest oracle/oci_iot_mcp_server/tests -v`
Expected: PASS with all package-local tests green

Run: `uv run --directory src/oci-iot-mcp-server pytest oracle/oci_iot_mcp_server/tests --cov=. --cov-branch --cov-report=term-missing -q`
Expected: PASS with coverage output shown and no import errors for `pytest-cov`

Run: `uv run behave tests/e2e/features/oci-iot-mcp-server.feature`
Expected: PASS if IoT e2e environment variables and target resources are configured; otherwise document this as a remaining validation gap before merge

- [ ] **Step 5: Commit**

```bash
git add src/oci-iot-mcp-server/README.md
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/health.py
git add src/oci-iot-mcp-server/oracle/oci_iot_mcp_server/tests/test_health.py
git add tests/e2e/features/oci-iot-mcp-server.feature
git commit -s -m "docs: finish iot expansion rollout"
```
