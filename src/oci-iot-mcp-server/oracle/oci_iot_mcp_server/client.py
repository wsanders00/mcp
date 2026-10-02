from functools import lru_cache

import oci

from .auth import (
    auth_cache_selectors,
    build_auth_context,
    has_inline_auth_secret,
    resolved_auth_type,
    resolved_profile_name,
)


@lru_cache(maxsize=None)
def _build_iot_client_cached(selectors: tuple[str | None, ...]):
    _, profile_name, auth_type, *_ = selectors
    auth_context = build_auth_context(profile_name=profile_name, auth_type=auth_type)
    return oci.iot.IotClient(auth_context.config, signer=auth_context.signer)


def get_iot_client(profile_name: str | None = None, auth_type: str | None = None):
    selected_profile = resolved_profile_name(profile_name)
    selected_type = resolved_auth_type(auth_type)
    selectors = auth_cache_selectors(selected_profile, selected_type)
    if has_inline_auth_secret():
        auth_context = build_auth_context(profile_name=selected_profile, auth_type=selected_type)
        return oci.iot.IotClient(auth_context.config, signer=auth_context.signer)
    return _build_iot_client_cached(selectors)


def clear_iot_client_cache():
    _build_iot_client_cached.cache_clear()
