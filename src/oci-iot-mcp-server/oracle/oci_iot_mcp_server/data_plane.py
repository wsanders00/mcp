import base64
import json
from datetime import timedelta

import httpx

from .errors import error_result
from .tool_models import DataApiTokenModel, success_result

ORDS_API_DATE = "20250531"


def build_ords_base_url(domain_context: dict) -> str:
    return f"https://{domain_context['data_host']}/ords/{domain_context['domain_short_id']}/{ORDS_API_DATE}"


def build_twin_filter(digital_twin_instance_id: str) -> dict:
    return {"$and": [{"digital_twin_instance_id": digital_twin_instance_id}]}


def encode_q(filter_payload: dict) -> str:
    return json.dumps(filter_payload, separators=(",", ":"))


def require_token_credentials(env: dict) -> dict:
    required = [
        "OCI_IOT_ORDS_CLIENT_ID",
        "OCI_IOT_ORDS_CLIENT_SECRET",
        "OCI_IOT_ORDS_USERNAME",
        "OCI_IOT_ORDS_PASSWORD",
    ]
    missing = [name for name in required if not env.get(name)]
    if missing:
        return error_result(
            code="missing_token_credentials",
            message="Missing one or more OCI IoT ORDS credential environment variables.",
            retry_hint="Set the missing OCI_IOT_ORDS_* environment variables and retry.",
            details={"missing": missing},
        )

    return success_result({"present": required, "missing": []})


def mint_data_api_token(*, domain_context: dict, env: dict, now) -> DataApiTokenModel:
    scope = (
        f"/{domain_context['domain_group_short_id']}/iot/"
        f"{domain_context['domain_short_id']}"
    )
    auth = base64.b64encode(
        f"{env['OCI_IOT_ORDS_CLIENT_ID']}:{env['OCI_IOT_ORDS_CLIENT_SECRET']}".encode()
    ).decode()

    response = httpx.post(
        f"https://{domain_context['db_allowed_identity_domain_host']}/oauth2/v1/token",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "password",
            "username": env["OCI_IOT_ORDS_USERNAME"],
            "password": env["OCI_IOT_ORDS_PASSWORD"],
            "scope": scope,
        },
        timeout=30.0,
    )
    raise_for_status = getattr(response, "raise_for_status", None)
    if callable(raise_for_status):
        raise_for_status()

    payload = response.json()
    minted_at = now()
    return DataApiTokenModel(
        access_token=payload["access_token"],
        token_type=payload["token_type"],
        expires_in=payload["expires_in"],
        expires_at=minted_at + timedelta(seconds=payload["expires_in"]),
    )


def _get_json(*, url: str, token: str, params: dict) -> dict:
    response = httpx.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def get_collection_record(*, base_url: str, path: str, token: str, record_id: str) -> dict:
    return _get_json(url=f"{base_url}{path}/{record_id}", token=token, params={})


def list_collection_records(
    *,
    base_url: str,
    path: str,
    token: str,
    params: dict,
    target_count: int,
) -> list[dict]:
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


def get_raw_command_record(*, base_url: str, token: str, request_id: str) -> dict:
    return get_collection_record(
        base_url=base_url,
        path="/rawCommandData",
        token=token,
        record_id=request_id,
    )


def list_raw_command_records(
    *,
    base_url: str,
    token: str,
    digital_twin_instance_id: str,
    target_count: int,
) -> list[dict]:
    return list_collection_records(
        base_url=base_url,
        path="/rawCommandData",
        token=token,
        params={"q": encode_q(build_twin_filter(digital_twin_instance_id))},
        target_count=target_count,
    )


def list_snapshot_records(
    *,
    base_url: str,
    token: str,
    digital_twin_instance_id: str,
    target_count: int,
) -> list[dict]:
    return list_collection_records(
        base_url=base_url,
        path="/snapshotData",
        token=token,
        params={"q": encode_q(build_twin_filter(digital_twin_instance_id))},
        target_count=target_count,
    )


def list_historized_records(
    *,
    base_url: str,
    token: str,
    digital_twin_instance_id: str,
    target_count: int,
) -> list[dict]:
    return list_collection_records(
        base_url=base_url,
        path="/historizedData",
        token=token,
        params={"q": encode_q(build_twin_filter(digital_twin_instance_id))},
        target_count=target_count,
    )


def list_rejected_data_records(
    *,
    base_url: str,
    token: str,
    digital_twin_instance_id: str,
    target_count: int,
) -> list[dict]:
    return list_collection_records(
        base_url=base_url,
        path="/rejectedData",
        token=token,
        params={"q": encode_q(build_twin_filter(digital_twin_instance_id))},
        target_count=target_count,
    )
