"""IoT compatibility facade over the shared OCI authentication policy."""

from __future__ import annotations

import os

import oci
from oracle_mcp_common import (
    AuthContext,
    AuthOptions,
    AuthType,
    build_auth_context as _build_shared_auth_context,
    resolve_auth_type as _resolve_shared_auth_type,
    resolve_config_file,
    resolve_profile_name,
)

from . import __project__, __version__

SUPPORTED_AUTH_TYPES = (
    "auto",
    "security_token",
    "api_key",
    "instance_principal",
    "resource_principal",
    "instance_principal_delegation",
    "resource_principal_delegation",
    "oke_workload_identity",
)
PRINCIPAL_AUTH_TYPES = {
    AuthType.INSTANCE_PRINCIPAL.value,
    AuthType.RESOURCE_PRINCIPAL.value,
    AuthType.INSTANCE_PRINCIPAL_DELEGATION.value,
    AuthType.RESOURCE_PRINCIPAL_DELEGATION.value,
    AuthType.OKE_WORKLOAD_IDENTITY.value,
}


def resolved_profile_name(profile_name: str | None = None) -> str:
    """Resolve the selected OCI profile using shared canonical and legacy inputs."""
    return resolve_profile_name(AuthOptions(profile_name=profile_name))


def resolved_auth_type(auth_type: str | None = None) -> str:
    """Resolve an IoT-supported auth mode; reject common-only modes explicitly."""
    try:
        resolved = _resolve_shared_auth_type(AuthOptions(auth_type=auth_type))
    except ValueError as error:
        supported = ", ".join(SUPPORTED_AUTH_TYPES)
        raise ValueError(f"Unsupported OCI authentication type. Supported values: {supported}") from error
    if resolved.value not in SUPPORTED_AUTH_TYPES:
        supported = ", ".join(SUPPORTED_AUTH_TYPES)
        raise ValueError(f"Unsupported OCI authentication type. Supported values: {supported}")
    return resolved.value


def build_auth_context(profile_name: str | None = None, auth_type: str | None = None) -> AuthContext:
    """Build shared auth context while adding this server's derived OCI user agent."""
    selected_type = resolved_auth_type(auth_type)
    options = _auth_options(profile_name, selected_type)
    context = _build_shared_auth_context(options)
    config = {**context.config, "additional_user_agent": _additional_user_agent()}
    return AuthContext(
        auth_type=context.auth_type,
        config=config,
        signer=context.signer,
        tenancy_id=context.tenancy_id,
        region=context.region,
        profile_name=context.profile_name,
    )


def auth_cache_selectors(profile_name: str | None = None, auth_type: str | None = None) -> tuple[str | None, ...]:
    """Return non-secret inputs that select a shared auth context for caching."""
    selected_type = resolved_auth_type(auth_type)
    options = _auth_options(profile_name, selected_type)
    return (
        resolve_config_file(options),
        resolve_profile_name(options),
        selected_type,
        _nonempty(os.getenv("OCI_REGION")),
        _nonempty(os.getenv("OCI_MCP_DELEGATION_TOKEN_FILE")),
        _nonempty(os.getenv("OCI_MCP_OKE_SERVICE_ACCOUNT_TOKEN_PATH")),
        _nonempty(os.getenv("OCI_IOT_OKE_SERVICE_ACCOUNT_TOKEN_PATH")),
        _nonempty(os.getenv("OCI_MCP_TENANCY_ID_OVERRIDE")),
        _nonempty(os.getenv("OCI_IOT_TENANCY_ID_OVERRIDE")),
        _nonempty(os.getenv("TENANCY_ID_OVERRIDE")),
    )


def has_inline_auth_secret() -> bool:
    """Avoid caching clients whose signer depends on an inline secret value."""
    return bool(
        os.getenv("OCI_MCP_DELEGATION_TOKEN")
        or os.getenv("OCI_IOT_DELEGATION_TOKEN")
        or os.getenv("OCI_MCP_OKE_SERVICE_ACCOUNT_TOKEN")
        or os.getenv("OCI_IOT_OKE_SERVICE_ACCOUNT_TOKEN")
    )


def get_default_region(profile_name: str | None = None, auth_type: str | None = None) -> str | None:
    """Resolve OCI region for IoT Data API URL construction without signing."""
    selected_type = resolved_auth_type(auth_type)
    region = _nonempty(os.getenv("OCI_REGION"))
    if region:
        return region
    options = _auth_options(profile_name, selected_type)
    if selected_type in PRINCIPAL_AUTH_TYPES:
        return _build_shared_auth_context(options).region
    # Data API bearer-token calls only need region metadata. Keep this profile
    # read separate from signer construction so they require no OCI key/token.
    config = oci.config.from_file(
        file_location=resolve_config_file(options),
        profile_name=resolve_profile_name(options),
    )
    return config.get("region")


def _auth_options(profile_name: str | None, auth_type: str) -> AuthOptions:
    return AuthOptions(auth_type=auth_type, profile_name=profile_name)


def _additional_user_agent() -> str:
    name = __project__.split("oracle.", 1)[1].removesuffix("-server")
    return f"{name}/{__version__}"


def _nonempty(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None
