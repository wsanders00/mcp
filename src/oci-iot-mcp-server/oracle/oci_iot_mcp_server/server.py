"""
Copyright (c) 2025, Oracle and/or its affiliates.
Licensed under the Universal Permissive License v1.0 as shown at
https://oss.oracle.com/licenses/upl.
"""

import logging
import os
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import TypeAdapter

from . import __project__, __version__
from .control_plane import (
    get_digital_twin_adapter_record,
    get_digital_twin_instance_content_record,
    get_digital_twin_instance_record,
    get_digital_twin_model_record,
    get_digital_twin_model_spec_record,
    get_digital_twin_relationship_record,
    get_iot_domain_group_record,
    get_iot_domain_record,
    get_work_request_record,
    invoke_raw_command,
    list_digital_twin_adapters_records,
    list_digital_twin_instances_records,
    list_digital_twin_models_records,
    list_digital_twin_relationships_records,
    list_iot_domain_groups_records,
    list_iot_domains_records,
    list_work_request_errors_records,
    list_work_request_logs_records,
    list_work_requests_records,
)
from .data_plane import (
    build_ords_base_url,
    get_raw_command_record,
    list_raw_command_records,
    list_rejected_data_records,
    list_snapshot_records,
    mint_data_api_token,
    require_token_credentials,
)
from .domain_context import resolve_domain_context_for_tool
from .errors import ambiguity_error, error_result, invalid_input_error, not_found_error
from .polling import wait_for_raw_command_terminal_state, wait_for_snapshot_update
from .resolvers import resolve_twin_for_tool
from .tool_models import success_result

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create FastMCP instance
mcp = FastMCP(name=__project__)
JSON_ADAPTER = TypeAdapter(Any)


def tool(*, description: str):
    def decorator(func):
        mcp.tool(description=description)(func)
        return func

    return decorator


def _delegate(message: str, func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception as e:
        logger.error(f"{message}: {e}")
        raise


def _is_error(payload) -> bool:
    return isinstance(payload, dict) and payload.get("ok") is False


def _as_tool_result(payload):
    if isinstance(payload, dict) and payload.get("ok") is False:
        return payload
    if isinstance(payload, dict) and payload.get("ok") is True and "data" in payload:
        return JSON_ADAPTER.dump_python(payload, mode="json")
    return success_result(JSON_ADAPTER.dump_python(payload, mode="json"))


def _limit_error(*, field_name: str, value: int):
    if 1 <= value <= 100:
        return None
    return error_result(
        code="invalid_input",
        message=f"{field_name} must be between 1 and 100.",
        retry_hint=f"Retry with {field_name} set between 1 and 100.",
        details={field_name: value},
    )


def _parse_rfc3339(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _in_time_window(value: str | None, since: str | None, until: str | None) -> bool:
    observed = _parse_rfc3339(value)
    if observed is None:
        return since is None and until is None
    if since and observed < _parse_rfc3339(since):
        return False
    if until and observed > _parse_rfc3339(until):
        return False
    return True


def _sort_desc(rows: list[dict], field_name: str) -> list[dict]:
    floor = datetime.min.replace(tzinfo=UTC)
    return sorted(
        rows,
        key=lambda row: _parse_rfc3339(row.get(field_name)) or floor,
        reverse=True,
    )


def _resolve_data_plane_access(**selectors):
    domain_context = resolve_domain_context_for_tool(**selectors)
    if _is_error(domain_context):
        return domain_context

    credentials = require_token_credentials(os.environ)
    if _is_error(credentials):
        return credentials

    try:
        token = mint_data_api_token(
            domain_context=domain_context,
            env=os.environ,
            now=lambda: datetime.now(UTC),
        )
    except Exception as exc:
        return error_result(
            code="data_plane_error",
            message="Failed to mint an IoT Data API bearer token.",
            retry_hint="Verify the ORDS credentials and domain access, then retry.",
            details={"reason": str(exc)},
        )

    return domain_context, token


def _resolve_twin_with_data_plane_access(
    *,
    digital_twin_instance_id: str | None = None,
    digital_twin_instance_name: str | None = None,
    iot_domain_id: str | None = None,
    iot_domain_display_name: str | None = None,
    domain_short_id: str | None = None,
    compartment_id: str | None = None,
):
    twin = resolve_twin_for_tool(
        digital_twin_instance_id=digital_twin_instance_id,
        digital_twin_instance_name=digital_twin_instance_name,
        iot_domain_id=iot_domain_id,
        iot_domain_display_name=iot_domain_display_name,
        domain_short_id=domain_short_id,
        compartment_id=compartment_id,
    )
    if _is_error(twin):
        return twin

    access = _resolve_data_plane_access(digital_twin_instance_id=twin["id"])
    if _is_error(access):
        return access

    domain_context, token = access
    return twin, domain_context, token


def get_data_api_token_impl(
    *,
    iot_domain_id: str | None = None,
    iot_domain_display_name: str | None = None,
    domain_short_id: str | None = None,
    compartment_id: str | None = None,
):
    access = _resolve_data_plane_access(
        iot_domain_id=iot_domain_id,
        iot_domain_display_name=iot_domain_display_name,
        domain_short_id=domain_short_id,
        compartment_id=compartment_id,
    )
    if _is_error(access):
        return access

    domain_context, token = access
    return {**domain_context, **token.model_dump()}


def get_raw_command_by_request_id_impl(
    *,
    request_id: str,
    iot_domain_id: str | None = None,
    iot_domain_display_name: str | None = None,
    domain_short_id: str | None = None,
    compartment_id: str | None = None,
    digital_twin_instance_id: str | None = None,
    digital_twin_instance_name: str | None = None,
    since: str | None = None,
    until: str | None = None,
):
    access = _resolve_data_plane_access(
        iot_domain_id=iot_domain_id,
        iot_domain_display_name=iot_domain_display_name,
        domain_short_id=domain_short_id,
        compartment_id=compartment_id,
        digital_twin_instance_id=digital_twin_instance_id,
        digital_twin_instance_name=digital_twin_instance_name,
    )
    if _is_error(access):
        return access

    domain_context, token = access
    try:
        record = get_raw_command_record(
            base_url=build_ords_base_url(domain_context),
            token=token.access_token,
            request_id=request_id,
        )
    except Exception as exc:
        return error_result(
            code="data_plane_error",
            message="Failed to fetch the raw command detail record.",
            retry_hint="Verify the request_id and domain selector, then retry.",
            details={"request_id": request_id, "reason": str(exc)},
        )

    if digital_twin_instance_id or digital_twin_instance_name:
        twin = resolve_twin_for_tool(
            digital_twin_instance_id=digital_twin_instance_id,
            digital_twin_instance_name=digital_twin_instance_name,
            iot_domain_id=iot_domain_id,
            iot_domain_display_name=iot_domain_display_name,
            domain_short_id=domain_short_id,
            compartment_id=compartment_id,
        )
        if _is_error(twin):
            return twin
        if record.get("digital_twin_instance_id") != twin["id"]:
            return not_found_error(
                resource_type="raw_command",
                message="The raw command record did not match the provided twin selector.",
                input_payload={
                    "request_id": request_id,
                    "digital_twin_instance_id": digital_twin_instance_id,
                    "digital_twin_instance_name": digital_twin_instance_name,
                },
            )

    try:
        if not _in_time_window(record.get("time_created"), since, until):
            return not_found_error(
                resource_type="raw_command",
                message="The raw command record did not match the provided time window.",
                input_payload={
                    "request_id": request_id,
                    "since": since,
                    "until": until,
                },
            )
    except ValueError:
        return invalid_input_error(
            resource_type="raw_command",
            message="since and until must be RFC 3339 timestamps when provided.",
            input_payload={"since": since, "until": until},
            retry_hint="Retry with RFC 3339 timestamps for since and until.",
        )

    return record


def list_recent_raw_commands_for_twin_impl(
    *,
    digital_twin_instance_id: str | None = None,
    digital_twin_instance_name: str | None = None,
    iot_domain_id: str | None = None,
    iot_domain_display_name: str | None = None,
    domain_short_id: str | None = None,
    compartment_id: str | None = None,
    limit: int = 20,
    since: str | None = None,
    until: str | None = None,
):
    resolved = _resolve_twin_with_data_plane_access(
        digital_twin_instance_id=digital_twin_instance_id,
        digital_twin_instance_name=digital_twin_instance_name,
        iot_domain_id=iot_domain_id,
        iot_domain_display_name=iot_domain_display_name,
        domain_short_id=domain_short_id,
        compartment_id=compartment_id,
    )
    if _is_error(resolved):
        return resolved

    twin, domain_context, token = resolved
    try:
        rows = list_raw_command_records(
            base_url=build_ords_base_url(domain_context),
            token=token.access_token,
            digital_twin_instance_id=twin["id"],
            target_count=500 if since or until else max(limit, 20),
        )
    except Exception as exc:
        return error_result(
            code="data_plane_error",
            message="Failed to list recent raw command records.",
            retry_hint="Verify the twin selector and domain access, then retry.",
            details={"reason": str(exc)},
        )

    try:
        return [
            row
            for row in rows
            if row.get("digital_twin_instance_id") == twin["id"]
            and _in_time_window(row.get("time_created"), since, until)
        ]
    except ValueError:
        return invalid_input_error(
            resource_type="raw_command",
            message="since and until must be RFC 3339 timestamps when provided.",
            input_payload={"since": since, "until": until},
            retry_hint="Retry with RFC 3339 timestamps for since and until.",
        )


def _candidate_matches_invoke(
    *,
    row: dict,
    twin_id: str,
    request_endpoint: str,
    request_data_format: str,
    response_endpoint: str | None,
    request_duration: str | None,
    response_duration: str | None,
    invoke_started_at: datetime,
) -> bool:
    if row.get("digital_twin_instance_id") != twin_id:
        return False
    if row.get("request_endpoint") != request_endpoint:
        return False
    if (row.get("request_data_format") or "").upper() != request_data_format.upper():
        return False
    if response_endpoint is not None and row.get("response_endpoint") != response_endpoint:
        return False
    if request_duration is not None and row.get("request_duration") != request_duration:
        return False
    if response_duration is not None and row.get("response_duration") != response_duration:
        return False
    created = _parse_rfc3339(row.get("time_created"))
    if created and created < invoke_started_at - timedelta(seconds=5):
        return False
    return True


def invoke_raw_command_and_wait_impl(
    *,
    digital_twin_instance_id: str | None = None,
    digital_twin_instance_name: str | None = None,
    iot_domain_id: str | None = None,
    iot_domain_display_name: str | None = None,
    domain_short_id: str | None = None,
    compartment_id: str | None = None,
    request_endpoint: str,
    request_data_format: str,
    request_data: object,
    response_endpoint: str | None = None,
    request_duration: str | None = None,
    response_duration: str | None = None,
    timeout: int = 30,
):
    resolved = _resolve_twin_with_data_plane_access(
        digital_twin_instance_id=digital_twin_instance_id,
        digital_twin_instance_name=digital_twin_instance_name,
        iot_domain_id=iot_domain_id,
        iot_domain_display_name=iot_domain_display_name,
        domain_short_id=domain_short_id,
        compartment_id=compartment_id,
    )
    if _is_error(resolved):
        return resolved

    twin, domain_context, token = resolved
    invoke_started_at = datetime.now(UTC)
    try:
        invoke_metadata = invoke_raw_command(
            digital_twin_instance_id=twin["id"],
            request_endpoint=request_endpoint,
            request_data_format=request_data_format,
            request_data=request_data,
            response_endpoint=response_endpoint,
            request_duration=request_duration,
            response_duration=response_duration,
        )
    except ValueError as exc:
        return invalid_input_error(
            resource_type="raw_command",
            message=str(exc),
            input_payload={
                "request_data_format": request_data_format,
                "request_endpoint": request_endpoint,
            },
            retry_hint="Retry with valid raw command inputs for the selected format.",
        )
    except Exception as exc:
        return error_result(
            code="control_plane_error",
            message="Failed to invoke the raw command on the digital twin instance.",
            retry_hint="Verify the twin selector and command payload, then retry.",
            details={"reason": str(exc)},
        )

    base_url = build_ords_base_url(domain_context)
    deadline = time.monotonic() + timeout
    last_candidates = []
    candidate = None
    while time.monotonic() < deadline:
        try:
            rows = list_raw_command_records(
                base_url=base_url,
                token=token.access_token,
                digital_twin_instance_id=twin["id"],
                target_count=100,
            )
        except Exception as exc:
            return error_result(
                code="data_plane_error",
                message="Failed while correlating the raw command against the data-plane feed.",
                retry_hint="Retry the command or inspect recent raw commands for the twin.",
                details={"reason": str(exc)},
            )

        candidates = [
            row
            for row in rows
            if _candidate_matches_invoke(
                row=row,
                twin_id=twin["id"],
                request_endpoint=request_endpoint,
                request_data_format=request_data_format,
                response_endpoint=response_endpoint,
                request_duration=request_duration,
                response_duration=response_duration,
                invoke_started_at=invoke_started_at,
            )
        ]
        last_candidates = candidates
        if len(candidates) == 1:
            candidate = candidates[0]
            break
        if len(candidates) > 1 and time.monotonic() + 2 >= deadline:
            return ambiguity_error(
                resource_type="raw_command",
                message="Multiple raw command records matched the invoke request.",
                input_payload={
                    "digital_twin_instance_id": twin["id"],
                    "request_endpoint": request_endpoint,
                    "request_data_format": request_data_format,
                    "response_endpoint": response_endpoint,
                },
                candidates=[
                    {
                        "id": row.get("id"),
                        "time_created": row.get("time_created"),
                        "request_endpoint": row.get("request_endpoint"),
                    }
                    for row in candidates
                ],
            )
        time.sleep(2)

    if candidate is None:
        if last_candidates:
            return ambiguity_error(
                resource_type="raw_command",
                message="Multiple raw command records matched the invoke request.",
                input_payload={
                    "digital_twin_instance_id": twin["id"],
                    "request_endpoint": request_endpoint,
                    "request_data_format": request_data_format,
                    "response_endpoint": response_endpoint,
                },
                candidates=[
                    {
                        "id": row.get("id"),
                        "time_created": row.get("time_created"),
                        "request_endpoint": row.get("request_endpoint"),
                    }
                    for row in last_candidates
                ],
            )
        return error_result(
            code="timeout",
            message="Timed out waiting for a correlated raw command record.",
            retry_hint="Retry with a larger timeout or inspect recent raw commands for the twin.",
            details={"digital_twin_instance_id": twin["id"]},
        )

    remaining = max(0, int(deadline - time.monotonic()))
    terminal = wait_for_raw_command_terminal_state(
        fetch_detail=lambda record_id: get_raw_command_record(
            base_url=base_url,
            token=token.access_token,
            request_id=record_id,
        ),
        record_id=candidate["id"],
        timeout_seconds=remaining,
        sleep=time.sleep,
        monotonic=time.monotonic,
    )
    return {
        **invoke_metadata,
        "request_id": candidate["id"],
        "timed_out": terminal["timed_out"],
        "raw_command": terminal["raw_command"],
    }


def wait_for_twin_update_impl(
    *,
    digital_twin_instance_id: str | None = None,
    digital_twin_instance_name: str | None = None,
    iot_domain_id: str | None = None,
    iot_domain_display_name: str | None = None,
    domain_short_id: str | None = None,
    compartment_id: str | None = None,
    content_path: str | None = None,
    since: str,
    timeout: int = 30,
):
    resolved = _resolve_twin_with_data_plane_access(
        digital_twin_instance_id=digital_twin_instance_id,
        digital_twin_instance_name=digital_twin_instance_name,
        iot_domain_id=iot_domain_id,
        iot_domain_display_name=iot_domain_display_name,
        domain_short_id=domain_short_id,
        compartment_id=compartment_id,
    )
    if _is_error(resolved):
        return resolved

    twin, domain_context, token = resolved
    base_url = build_ords_base_url(domain_context)

    def fetch_rows():
        rows = list_snapshot_records(
            base_url=base_url,
            token=token.access_token,
            digital_twin_instance_id=twin["id"],
            target_count=500,
        )
        if content_path:
            return [row for row in rows if row.get("content_path") == content_path]
        return rows

    try:
        return wait_for_snapshot_update(
            fetch_rows=fetch_rows,
            since=since,
            timeout_seconds=timeout,
            sleep=time.sleep,
            monotonic=time.monotonic,
        )
    except ValueError:
        return invalid_input_error(
            resource_type="snapshot_data",
            message="since must be an RFC 3339 timestamp.",
            input_payload={"since": since},
            retry_hint="Retry with since set to an RFC 3339 timestamp.",
        )
    except Exception as exc:
        return error_result(
            code="data_plane_error",
            message="Failed while waiting for a twin snapshot update.",
            retry_hint="Verify the twin selector and data-plane access, then retry.",
            details={"reason": str(exc)},
        )


def list_recent_rejected_data_for_twin_impl(
    *,
    digital_twin_instance_id: str | None = None,
    digital_twin_instance_name: str | None = None,
    iot_domain_id: str | None = None,
    iot_domain_display_name: str | None = None,
    domain_short_id: str | None = None,
    compartment_id: str | None = None,
    limit: int = 20,
    since: str | None = None,
    until: str | None = None,
):
    resolved = _resolve_twin_with_data_plane_access(
        digital_twin_instance_id=digital_twin_instance_id,
        digital_twin_instance_name=digital_twin_instance_name,
        iot_domain_id=iot_domain_id,
        iot_domain_display_name=iot_domain_display_name,
        domain_short_id=domain_short_id,
        compartment_id=compartment_id,
    )
    if _is_error(resolved):
        return resolved

    twin, domain_context, token = resolved
    try:
        rows = list_rejected_data_records(
            base_url=build_ords_base_url(domain_context),
            token=token.access_token,
            digital_twin_instance_id=twin["id"],
            target_count=500 if since or until else max(limit, 20),
        )
    except Exception as exc:
        return error_result(
            code="data_plane_error",
            message="Failed to list recent rejected ingest records.",
            retry_hint="Verify the twin selector and data-plane access, then retry.",
            details={"reason": str(exc)},
        )

    try:
        return [
            row
            for row in rows
            if row.get("digital_twin_instance_id") == twin["id"]
            and _in_time_window(row.get("time_received"), since, until)
        ]
    except ValueError:
        return invalid_input_error(
            resource_type="rejected_data",
            message="since and until must be RFC 3339 timestamps when provided.",
            input_payload={"since": since, "until": until},
            retry_hint="Retry with RFC 3339 timestamps for since and until.",
        )


@tool(
    description="Retrieves a specific digital twin adapter by its identifier."
)
def get_digital_twin_adapter(
    digital_twin_adapter_id: Annotated[str, "The digital twin adapter identifier"]
):
    return _delegate(
        f"Error getting digital twin adapter {digital_twin_adapter_id}",
        get_digital_twin_adapter_record,
        digital_twin_adapter_id,
    )

@tool(
    description="Retrieves a specific digital twin instance by its identifier."
)
def get_digital_twin_instance(
    digital_twin_instance_id: Annotated[str, "The digital twin instance identifier"]
):
    return _delegate(
        f"Error getting digital twin instance {digital_twin_instance_id}",
        get_digital_twin_instance_record,
        digital_twin_instance_id,
    )

@tool(
    description="Retrieves the content of a specific digital twin instance by its identifier."
)
def get_digital_twin_instance_content(
    digital_twin_instance_id: Annotated[str, "The digital twin instance identifier"]
):
    return _delegate(
        f"Error getting digital twin instance content {digital_twin_instance_id}",
        get_digital_twin_instance_content_record,
        digital_twin_instance_id,
    )

@tool(
    description="Retrieves a specific digital twin model by its identifier."
)
def get_digital_twin_model(
    digital_twin_model_id: Annotated[str, "The digital twin model identifier"]
):
    return _delegate(
        f"Error getting digital twin model {digital_twin_model_id}",
        get_digital_twin_model_record,
        digital_twin_model_id,
    )

@tool(
    description="Retrieves the specification of a specific digital twin model by its identifier."
)
def get_digital_twin_model_spec(
    digital_twin_model_id: Annotated[str, "The digital twin model identifier"]
):
    return _delegate(
        f"Error getting digital twin model spec {digital_twin_model_id}",
        get_digital_twin_model_spec_record,
        digital_twin_model_id,
    )

@tool(
    description="Retrieves a specific digital twin relationship by its identifier."
)
def get_digital_twin_relationship(
    digital_twin_relationship_id: Annotated[str, "The digital twin relationship identifier"]
):
    return _delegate(
        f"Error getting digital twin relationship {digital_twin_relationship_id}",
        get_digital_twin_relationship_record,
        digital_twin_relationship_id,
    )

@tool(
    description="Retrieves a specific IoT domain by its identifier."
)
def get_iot_domain(
    iot_domain_id: Annotated[str, "The IoT domain identifier"]
):
    return _delegate(f"Error getting IoT domain {iot_domain_id}", get_iot_domain_record, iot_domain_id)

@tool(
    description="Retrieves a specific IoT domain group by its identifier."
)
def get_iot_domain_group(
    iot_domain_group_id: Annotated[str, "The IoT domain group identifier"]
):
    return _delegate(
        f"Error getting IoT domain group {iot_domain_group_id}",
        get_iot_domain_group_record,
        iot_domain_group_id,
    )

@tool(
    description="Retrieves a specific work request by its identifier."
)
def get_work_request(
    work_request_id: Annotated[str, "The work request identifier"]
):
    return _delegate(
        f"Error getting work request {work_request_id}",
        get_work_request_record,
        work_request_id,
    )

@tool(
    description="Lists digital twin adapters in a specified IoT domain."
)
def list_digital_twin_adapters(
    iot_domain_id: Annotated[str, "The IoT domain identifier"]
):
    return _delegate(
        f"Error listing digital twin adapters for domain {iot_domain_id}",
        list_digital_twin_adapters_records,
        iot_domain_id=iot_domain_id,
    )

@tool(
    description="Lists digital twin models in a specified IoT domain."
)
def list_digital_twin_models(
    iot_domain_id: Annotated[str, "The IoT domain identifier"]
):
    return _delegate(
        f"Error listing digital twin models for domain {iot_domain_id}",
        list_digital_twin_models_records,
        iot_domain_id=iot_domain_id,
    )

@tool(
    description="Lists digital twin instances in a specified IoT domain."
)
def list_digital_twin_instances(
    iot_domain_id: Annotated[str, "The IoT domain identifier"],
    limit: Annotated[int, "The limit of results"] = 1000
):
    return _delegate(
        f"Error listing digital twin instances for domain {iot_domain_id}",
        list_digital_twin_instances_records,
        iot_domain_id=iot_domain_id,
        limit=limit,
    )

@tool(
    description="Lists digital twin relationships in a specified IoT domain."
)
def list_digital_twin_relationships(
    iot_domain_id: Annotated[str, "The IoT domain identifier"]
):
    return _delegate(
        f"Error listing digital twin relationships for domain {iot_domain_id}",
        list_digital_twin_relationships_records,
        iot_domain_id=iot_domain_id,
    )

@tool(
    description="Lists IoT domain groups in a specified compartment."
)
def list_iot_domain_groups(
    compartment_id: Annotated[str, "Compartment containing IoT Domain Groups"]
):
    return _delegate(
        f"Error listing IoT domain groups for compartment {compartment_id}",
        list_iot_domain_groups_records,
        compartment_id=compartment_id,
    )

@tool(
    description="Lists IoT domains in a specified compartment."
)
def list_iot_domains(
    compartment_id: Annotated[str, "Compartment containing IoT Domains"]
):
    return _delegate(
        f"Error listing IoT domains for compartment {compartment_id}",
        list_iot_domains_records,
        compartment_id=compartment_id,
    )

@tool(
    description="Lists errors for a specific work request."
)
def list_work_request_errors(
    work_request_id: Annotated[str, "The work request identifier"]
):
    return _delegate(
        f"Error listing work request errors for {work_request_id}",
        list_work_request_errors_records,
        work_request_id=work_request_id,
    )

@tool(
    description="Lists logs for a specific work request."
)
def list_work_request_logs(
    work_request_id: Annotated[str, "The work request identifier"]
):
    return _delegate(
        f"Error listing work request logs for {work_request_id}",
        list_work_request_logs_records,
        work_request_id=work_request_id,
    )

@tool(
    description="Lists work requests in a specified compartment."
)
def list_work_requests(
    compartment_id: Annotated[str, "The compartment ID containing the work requests"]
):
    return _delegate(
        f"Error listing work requests for compartment {compartment_id}",
        list_work_requests_records,
        compartment_id=compartment_id,
    )

@tool(
    description="Return the full mapped digital twin adapter payload for debugging and migration workflows."
)
def get_digital_twin_adapter_full(
    digital_twin_adapter_id: Annotated[str, "The digital twin adapter OCID"],
):
    return _as_tool_result(get_digital_twin_adapter_record(digital_twin_adapter_id))


@tool(description="Derive normalized IoT domain context for ORDS and operator workflows.")
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


@tool(description="Mint and return an IoT Data API bearer token plus the resolved domain context.")
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


@tool(description="Fetch the raw command detail record for an ORDS request ID.")
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


@tool(description="List recent raw command records for a digital twin instance.")
def list_recent_raw_commands_for_twin(
    digital_twin_instance_id: Annotated[str | None, "The digital twin instance OCID"] = None,
    digital_twin_instance_name: Annotated[str | None, "The digital twin instance display name"] = None,
    iot_domain_id: Annotated[str | None, "The IoT domain OCID for friendly twin lookup"] = None,
    iot_domain_display_name: Annotated[str | None, "The IoT domain display name for friendly twin lookup"] = None,
    domain_short_id: Annotated[str | None, "The IoT domain short ID for friendly twin lookup"] = None,
    compartment_id: Annotated[str | None, "Compartment OCID for friendly domain lookup"] = None,
    limit: Annotated[int, "Maximum records to return"] = 20,
    since: Annotated[str | None, "Optional RFC 3339 lower bound"] = None,
    until: Annotated[str | None, "Optional RFC 3339 upper bound"] = None,
):
    limit_error = _limit_error(field_name="limit", value=limit)
    if limit_error:
        return limit_error
    rows = list_recent_raw_commands_for_twin_impl(
        digital_twin_instance_id=digital_twin_instance_id,
        digital_twin_instance_name=digital_twin_instance_name,
        iot_domain_id=iot_domain_id,
        iot_domain_display_name=iot_domain_display_name,
        domain_short_id=domain_short_id,
        compartment_id=compartment_id,
        limit=limit,
        since=since,
        until=until,
    )
    if _is_error(rows):
        return rows
    ordered = _sort_desc(rows, "time_created")
    return _as_tool_result(ordered[:limit])


@tool(description="Invoke a raw command on a digital twin instance and wait for a terminal data-plane result.")
def invoke_raw_command_and_wait(
    digital_twin_instance_id: Annotated[str | None, "The digital twin instance OCID"] = None,
    digital_twin_instance_name: Annotated[str | None, "The digital twin instance display name"] = None,
    iot_domain_id: Annotated[str | None, "The IoT domain OCID for friendly twin lookup"] = None,
    iot_domain_display_name: Annotated[str | None, "The IoT domain display name for friendly twin lookup"] = None,
    domain_short_id: Annotated[str | None, "The IoT domain short ID for friendly twin lookup"] = None,
    compartment_id: Annotated[str | None, "Compartment OCID for friendly domain lookup"] = None,
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
        iot_domain_display_name=iot_domain_display_name,
        domain_short_id=domain_short_id,
        compartment_id=compartment_id,
        request_endpoint=request_endpoint,
        request_data_format=request_data_format,
        request_data=request_data,
        response_endpoint=response_endpoint,
        request_duration=request_duration,
        response_duration=response_duration,
        timeout=timeout,
    )
    return _as_tool_result(result)


@tool(description="Wait for a twin snapshot update after a given timestamp.")
def wait_for_twin_update(
    digital_twin_instance_id: Annotated[str | None, "The digital twin instance OCID"] = None,
    digital_twin_instance_name: Annotated[str | None, "The digital twin instance display name"] = None,
    iot_domain_id: Annotated[str | None, "The IoT domain OCID for friendly twin lookup"] = None,
    iot_domain_display_name: Annotated[str | None, "The IoT domain display name for friendly twin lookup"] = None,
    domain_short_id: Annotated[str | None, "The IoT domain short ID for friendly twin lookup"] = None,
    compartment_id: Annotated[str | None, "Compartment OCID for friendly domain lookup"] = None,
    content_path: Annotated[str | None, "Optional exact snapshot content path"] = None,
    since: Annotated[str, "RFC 3339 timestamp"] = "",
    timeout: Annotated[int, "Maximum seconds to wait"] = 30,
):
    if not since:
        return error_result(
            code="invalid_input",
            message="since is required and must be an RFC 3339 timestamp.",
            retry_hint="Retry with since set to an RFC 3339 timestamp.",
            details={"since": since},
        )
    return _as_tool_result(
        wait_for_twin_update_impl(
            digital_twin_instance_id=digital_twin_instance_id,
            digital_twin_instance_name=digital_twin_instance_name,
            iot_domain_id=iot_domain_id,
            iot_domain_display_name=iot_domain_display_name,
            domain_short_id=domain_short_id,
            compartment_id=compartment_id,
            content_path=content_path,
            since=since,
            timeout=timeout,
        )
    )


@tool(description="List recent rejected ingest records for a digital twin instance.")
def list_recent_rejected_data_for_twin(
    digital_twin_instance_id: Annotated[str | None, "The digital twin instance OCID"] = None,
    digital_twin_instance_name: Annotated[str | None, "The digital twin instance display name"] = None,
    iot_domain_id: Annotated[str | None, "The IoT domain OCID for friendly twin lookup"] = None,
    iot_domain_display_name: Annotated[str | None, "The IoT domain display name for friendly twin lookup"] = None,
    domain_short_id: Annotated[str | None, "The IoT domain short ID for friendly twin lookup"] = None,
    compartment_id: Annotated[str | None, "Compartment OCID for friendly domain lookup"] = None,
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
        iot_domain_display_name=iot_domain_display_name,
        domain_short_id=domain_short_id,
        compartment_id=compartment_id,
        limit=limit,
        since=since,
        until=until,
    )
    if _is_error(rows):
        return rows
    ordered = _sort_desc(rows, "time_received")
    return _as_tool_result(ordered[:limit])

@tool(
    description="Health check endpoint for the OCI IoT MCP server."
)
def health_check():
    """Health check endpoint that verifies the server is running."""
    return {
        "status": "healthy",
        "service": "oci-iot-mcp-server",
        "version": __version__
    }

def main():
    """Main function to run the MCP server."""
    try:
        mcp.run()
    except Exception as e:
        logger.error(f"Error running MCP server: {e}")
        raise

if __name__ == "__main__":
    main()
