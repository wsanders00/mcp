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
    from .client import get_shared_clients
    shared = get_shared_clients(profile_name, auth_type)
    if shared is not None:
        return shared.identity["region"]
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


class SharedAuthError(RuntimeError):
    """A shared service must be explicitly restarted or switched by its owner."""


def resolve_shared_binding(environment_config):
    """Read only selection metadata; never read key or token contents here."""
    import configparser
    import stat
    import tomllib
    from pathlib import Path

    def private_metadata(path):
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise ValueError
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
                info.st_ctime_ns, info.st_uid, stat.S_IMODE(info.st_mode))

    def absolute(value):
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError
        return path.resolve(strict=True)

    try:
        environment = absolute(environment_config)
        environment_before = private_metadata(environment)
        with environment.open('rb') as selected:
            data = tomllib.load(selected)
        selection = data['oci']
        config_file = absolute(selection['config_file'])
        profile = selection['resource_profile_name']
        if not isinstance(profile, str) or not profile.strip():
            raise ValueError
        config_before = private_metadata(config_file)
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(config_file.read_text())
        raw = parser.defaults() if profile == 'DEFAULT' else parser._sections[profile]
        if not raw.get('security_token_file'):
            raise ValueError
        config = parser[profile]
        identity = {
            'environment_config': str(environment), 'config_file': str(config_file),
            'profile': profile, 'auth_type': 'security_token',
            'region': config['region'], 'tenancy': config['tenancy'],
            'principal': config['user'],
            'token_file': str(absolute(raw['security_token_file'])),
            'key_file': str(absolute(config['key_file'])),
        }
        if any(not isinstance(value, str) or not value.strip() for value in identity.values()):
            raise ValueError
        expected = {'OCI_CONFIG_FILE': identity['config_file'], 'OCI_CONFIG_PROFILE': profile,
                    'OCI_MCP_AUTH_TYPE': 'security_token', 'OCI_REGION': identity['region']}
        for name, value in expected.items():
            if os.getenv(name) not in (None, '', value):
                raise SharedAuthError('OCI selection changed; explicit restart or environment switch required.')
        for name in ('OCI_IOT_AUTH_TYPE', 'OCI_AUTH_TYPE', 'ORACLE_MCP_AUTH_METHOD',
                     'ORACLE_MCP_AUTH_PROFILE', 'OCI_MCP_DELEGATION_TOKEN',
                     'OCI_IOT_DELEGATION_TOKEN', 'OCI_MCP_DELEGATION_TOKEN_FILE',
                     'OCI_MCP_OKE_SERVICE_ACCOUNT_TOKEN', 'OCI_IOT_OKE_SERVICE_ACCOUNT_TOKEN',
                     'OCI_MCP_OKE_SERVICE_ACCOUNT_TOKEN_PATH', 'OCI_IOT_OKE_SERVICE_ACCOUNT_TOKEN_PATH',
                     'OCI_MCP_TENANCY_ID_OVERRIDE', 'OCI_IOT_TENANCY_ID_OVERRIDE', 'TENANCY_ID_OVERRIDE'):
            if os.getenv(name):
                raise SharedAuthError('Conflicting OCI auth override; use the selected environment and restart.')
        metadata = tuple((identity[name], private_metadata(Path(identity[name])))
                         for name in ('environment_config', 'config_file', 'token_file', 'key_file'))
        if environment_before != metadata[0][1] or config_before != metadata[1][1]:
            raise SharedAuthError('OCI configuration changed during selection; explicit restart required.')
        return identity, metadata
    except SharedAuthError:
        raise
    except (OSError, ValueError, KeyError, TypeError, configparser.Error):
        raise SharedAuthError('OCI authentication configuration unavailable; use token-mgr, then explicitly restart the service.') from None


def build_shared_context(identity):
    """Construct one Common context for both SDK clients; no credential copies."""
    try:
        context = _build_shared_auth_context(AuthOptions(
            auth_type='security_token', config_file=identity['config_file'],
            profile_name=identity['profile'], region=identity['region'],
        ))
        if (context.tenancy_id != identity['tenancy'] or context.region != identity['region']
                or context.config.get('user') != identity['principal']):
            raise SharedAuthError('OCI identity changed during construction; explicit environment switch required.')
        config = {**context.config, 'additional_user_agent': _additional_user_agent()}
        return config, context.signer
    except SharedAuthError:
        raise
    except Exception:
        raise SharedAuthError('OCI authentication unavailable; use token-mgr, then explicitly restart the service.') from None
