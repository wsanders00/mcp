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
    shared = get_shared_clients(profile_name, auth_type)
    if shared is not None:
        return shared.iot
    selected_profile = resolved_profile_name(profile_name)
    selected_type = resolved_auth_type(auth_type)
    selectors = auth_cache_selectors(selected_profile, selected_type)
    if has_inline_auth_secret():
        auth_context = build_auth_context(profile_name=selected_profile, auth_type=selected_type)
        return oci.iot.IotClient(auth_context.config, signer=auth_context.signer)
    return _build_iot_client_cached(selectors)


def clear_iot_client_cache():
    _build_iot_client_cached.cache_clear()


_SHARED_CLIENTS = None


class SharedClients:
    """One eagerly constructed SDK pair bound to unchanged files and selection."""

    def __init__(self, environment_config):
        import threading
        from .auth import build_shared_context, resolve_shared_binding
        self.lock = threading.RLock()
        self.environment_config = environment_config
        self.identity, self.metadata = resolve_shared_binding(environment_config)
        self.config, self.signer = build_shared_context(self.identity)
        self.guard()
        self.iot = oci.iot.IotClient(self.config, signer=self.signer)
        self.guard()
        self.identity_client = oci.identity.IdentityClient(self.config, signer=self.signer)
        self.guard()

    def guard(self):
        import time
        import jwt
        from .auth import SharedAuthError, resolve_shared_binding
        with self.lock:
            identity, metadata = resolve_shared_binding(self.environment_config)
            if identity != self.identity or metadata != self.metadata:
                raise SharedAuthError('OCI context or credential files changed; explicit restart or environment switch required.')
            try:
                token = self.signer.api_key
                if not isinstance(token, str) or not token.startswith('ST$'):
                    raise ValueError
                claims = jwt.decode(token[3:], options={'verify_signature': False})
                if claims['exp'] <= time.time():
                    raise ValueError
            except (AttributeError, ValueError, KeyError, TypeError, jwt.PyJWTError):
                raise SharedAuthError('OCI authentication unavailable or expired; use token-mgr, then explicitly restart the service.') from None

    def select(self, profile_name=None, auth_type=None):
        from .auth import SharedAuthError
        self.guard()
        if profile_name not in (None, self.identity['profile']) or auth_type not in (None, 'security_token'):
            raise SharedAuthError('OCI selection changed; explicit environment switch required.')
        return self


def initialize_shared_clients(environment_config):
    global _SHARED_CLIENTS
    if _SHARED_CLIENTS is not None:
        raise RuntimeError('Shared SDK context already initialized; start a fresh process.')
    clients = SharedClients(environment_config)
    _SHARED_CLIENTS = clients
    return clients


def get_shared_clients(profile_name=None, auth_type=None):
    return None if _SHARED_CLIENTS is None else _SHARED_CLIENTS.select(profile_name, auth_type)


def clear_shared_clients():
    """Release process-owned context for tests; production refresh restarts process."""
    global _SHARED_CLIENTS
    _SHARED_CLIENTS = None
