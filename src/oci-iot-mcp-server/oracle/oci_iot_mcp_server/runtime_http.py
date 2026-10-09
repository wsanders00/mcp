"""Offline-only, authenticated Streamable HTTP fixture for the IoT runtime.

This module imports only the disconnected runtime contracts. It has no OCI SDK,
profile, filesystem, subprocess, or real-provider path.
"""

# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v1.0 as shown at
# https://oss.oracle.com/licenses/upl.

from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import hmac
import math
import secrets
from threading import RLock
import time
from typing import Any, Mapping
from urllib.parse import urlsplit

from fastmcp import Context, FastMCP
from starlette.responses import PlainTextResponse

from .runtime_credentials import CredentialMaterial, CredentialRuntime
from .runtime_targets import AuthSpec, Target, TargetPolicyError, TargetRegistry


_caller: ContextVar[str | None] = ContextVar("iot_fixture_caller", default=None)
_FIXTURE_SENTINEL = "FIXTURE_ONLY_NOT_REAL"


def fixture_targets() -> tuple[Target, ...]:
    """Return deliberately synthetic BOAT shared-context and normal targets."""
    boat = AuthSpec("fixture-boat-context", "boat_session", "SSV",
                    "fixture-auth-tenancy", "fixture-resource-tenancy",
                    "fixture-region", "DEFAULT")
    normal = AuthSpec("fixture-normal-context", "api_key", "NORMAL",
                      "fixture-normal-tenancy", "fixture-normal-tenancy",
                      "fixture-region")
    ops = ("inspect_target", "read_iot_data")
    return (
        Target("fixture-boat-ssv", "fixture-domain-ssv", "fixture-group-ssv",
               "fixture-compartment-ssv", boat.resource_tenancy, boat.region, boat, ops),
        Target("fixture-boat-sandbox", "fixture-domain-sandbox", "fixture-group-sandbox",
               "fixture-compartment-sandbox", boat.resource_tenancy, boat.region, boat, ops),
        Target("fixture-normal", "fixture-domain-normal", "fixture-group-normal",
               "fixture-compartment-normal", normal.resource_tenancy, normal.region, normal, ops),
    )


class _FixtureProvider:
    """Explicit fake provider; renewal creates only synthetic in-memory material."""

    def renew(self, spec: AuthSpec, previous: CredentialMaterial | None) -> CredentialMaterial:
        return CredentialMaterial(
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            payload={"fixture": _FIXTURE_SENTINEL, "nonce": secrets.token_hex(8)},
            context_id=spec.context_id, mode=spec.mode, profile=spec.profile,
            authentication_tenancy=spec.authentication_tenancy,
            resource_tenancy=spec.resource_tenancy, region=spec.region,
            material_profile=spec.material_profile,
        )


class _AuthenticatedHTTP:
    """Small ASGI guard: bearer identity, host/origin, and per-session ownership."""

    def __init__(self, app, mcp: FastMCP, tokens: Mapping[str, str], host: str, port: int,
                 max_sessions: int, ttl: float):
        self.app, self.mcp, self.tokens = app, mcp, dict(tokens)
        self.host, self.port = host, port
        self.max_sessions, self.ttl = max_sessions, ttl
        self.sessions: dict[str, tuple[str, float]] = {}
        self.reserved = 0
        # FastMCP retains closed/expired sessions internally; cap successful
        # initialization for process lifetime to bound that version's session store.
        self.initialized = 0
        self.lock = RLock()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        header_values: dict[bytes, list[bytes]] = {}
        for key, value in scope.get("headers", []):
            header_values.setdefault(key.lower(), []).append(value)
        if any(len(header_values.get(key, [])) > 1 for key in (
            b"host", b"origin", b"authorization", b"mcp-session-id"
        )):
            await PlainTextResponse("request rejected", status_code=400)(scope, receive, send)
            return
        headers = {key: values[0] for key, values in header_values.items()}
        host = headers.get(b"host", b"").decode("latin1")
        expected = f"{self.host}:{self.port}"
        if host not in {expected, f"localhost:{self.port}", f"127.0.0.1:{self.port}"}:
            await PlainTextResponse("request rejected", status_code=400)(scope, receive, send)
            return
        origin = headers.get(b"origin")
        if origin:
            try:
                parsed = urlsplit(origin.decode("latin1"))
                if parsed.scheme != "http" or parsed.netloc not in {
                    f"localhost:{self.port}", f"127.0.0.1:{self.port}"
                } or parsed.path not in ("", "/") or parsed.username is not None \
                        or parsed.password is not None or parsed.query or parsed.fragment:
                    raise ValueError
            except Exception:
                await PlainTextResponse("request rejected", status_code=403)(scope, receive, send)
                return
        authorization = headers.get(b"authorization", b"").decode("latin1")
        scheme, _, supplied = authorization.partition(" ")
        caller = None
        try:
            supplied.encode("ascii")
        except UnicodeEncodeError:
            supplied = ""
        if scheme.lower() == "bearer" and supplied:
            # Constant-time comparisons avoid an early-exit token lookup.
            for token, identity in self.tokens.items():
                if hmac.compare_digest(supplied, token):
                    caller = identity
        if caller is None:
            await PlainTextResponse("authentication required", status_code=401,
                                    headers={"www-authenticate": "Bearer"})(scope, receive, send)
            return

        method = scope["method"].upper()
        session_id = headers.get(b"mcp-session-id", b"").decode("latin1")
        initializing = False
        invalid_session = False
        at_capacity = False
        now = time.monotonic()
        with self.lock:
            for sid in [sid for sid, owner in self.sessions.items() if owner[1] <= now]:
                del self.sessions[sid]
            if session_id:
                owner = self.sessions.get(session_id)
                invalid_session = owner is None or owner[0] != caller
            elif method == "POST":
                initializing = True
                at_capacity = self.initialized + self.reserved >= self.max_sessions
                if not at_capacity:
                    self.reserved += 1
        if invalid_session:
            await PlainTextResponse("session unavailable", status_code=404)(scope, receive, send)
            return
        if at_capacity:
            await PlainTextResponse("session capacity reached", status_code=503)(scope, receive, send)
            return

        context_token = _caller.set(caller)
        reservation_released = False
        issued_session: str | None = None
        async def capture(message):
            nonlocal issued_session, reservation_released
            if message["type"] == "http.response.start":
                for key, value in message.get("headers", []):
                    if key.lower() == b"mcp-session-id" and initializing and issued_session is None:
                        issued_session = value.decode("latin1")
                        # Publish ownership before forwarding the response start. A client
                        # can send its first request as soon as it receives this header,
                        # even while the initialization response body is still streaming.
                        with self.lock:
                            if not reservation_released:
                                self.reserved -= 1
                                reservation_released = True
                            self.initialized += 1
                            self.sessions[issued_session] = (
                                caller, time.monotonic() + self.ttl
                            )
            await send(message)
        try:
            await self.app(scope, receive, capture)
        finally:
            _caller.reset(context_token)
            if initializing:
                with self.lock:
                    if not reservation_released:
                        self.reserved -= 1
                        reservation_released = True
            if method == "DELETE" and session_id:
                with self.lock:
                    self.sessions.pop(session_id, None)


def build_fixture_app(
    *,
    caller_tokens: Mapping[str, str],
    max_sessions: int = 32,
    max_callers: int = 32,
    session_ttl_seconds: float = 3600,
    host: str = "127.0.0.1",
    port: int = 8765,
):
    """Build stateful Streamable HTTP fixture ASGI app; tokens are injected privately.

    ``caller_tokens`` maps opaque bearer token values to local caller identifiers.
    Tokens are neither read from the environment nor returned or logged. This
    listener's trust model is same-user loopback process trust.
    """
    if (not isinstance(caller_tokens, Mapping) or not caller_tokens
            or isinstance(max_callers, bool) or not isinstance(max_callers, int)
            or not 1 <= max_callers <= 1024 or len(caller_tokens) > max_callers
            or any(not isinstance(t, str) or len(t) < 32 or not t.isascii()
                   or not isinstance(i, str) or not i.strip()
                   for t, i in caller_tokens.items())):
        raise ValueError("caller token configuration is invalid")
    if (isinstance(max_sessions, bool) or not isinstance(max_sessions, int) or max_sessions < 1
            or not isinstance(session_ttl_seconds, (int, float))
            or isinstance(session_ttl_seconds, bool) or not math.isfinite(session_ttl_seconds)
            or session_ttl_seconds <= 0
            or host not in ("127.0.0.1", "localhost")
            or isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535):
        raise ValueError("session limits are invalid")
    configured_targets = fixture_targets()
    registry = TargetRegistry(configured_targets, revision=secrets.token_hex(8),
                              max_bindings=max_sessions, ttl_seconds=session_ttl_seconds)
    credential_runtime = CredentialRuntime(_FixtureProvider())
    for target in configured_targets:
        credential_runtime.register(target.auth)
    handle_targets: dict[str, tuple[Target, float]] = {}
    handle_lock = RLock()
    mcp = FastMCP("OCI IoT Offline Fixture")

    def identity(ctx: Context) -> tuple[str, str]:
        caller = _caller.get()
        if caller is None:
            raise ValueError("authentication_required")
        return caller, ctx.session_id

    def safe_error(exc: Exception) -> ValueError:
        code = getattr(exc, "code", "fixture_request_failed")
        return ValueError(str(code))

    @mcp.tool(
        description="Select one configured synthetic target for this authenticated MCP session.",
        run_in_thread=False,
    )
    def select_target(domain_id: str, ctx: Context) -> dict[str, str]:
        caller, session = identity(ctx)
        try:
            target = registry.resolve_domain(domain_id)
            handle = registry.bind(target.name, caller, session)
            with handle_lock:
                now = time.monotonic()
                for key in [key for key, value in handle_targets.items() if value[1] <= now]:
                    del handle_targets[key]
                handle_targets[handle] = (target, now + session_ttl_seconds)
            return {"handle": handle, "target": target.name, "fixture": _FIXTURE_SENTINEL}
        except Exception as exc:
            raise safe_error(exc) from None

    def authorize(handle: str, caller: str, session: str, operation: str) -> Target:
        with handle_lock:
            entry = handle_targets.get(handle)
            if entry is not None and entry[1] <= time.monotonic():
                del handle_targets[handle]
                entry = None
        if entry is None:
            raise TargetPolicyError("invalid_binding")
        target = entry[0]
        return registry.authorize(
            handle, caller_id=caller, session_id=session,
            domain_id=target.domain_id, group_id=target.group_id,
            compartment_id=target.compartment_id,
            resource_tenancy=target.resource_tenancy, operation=operation,
        )

    @mcp.tool(description="Inspect synthetic metadata for a selected fixture target.", run_in_thread=False)
    def inspect_target(handle: str, ctx: Context) -> dict[str, Any]:
        caller, session = identity(ctx)
        try:
            target = authorize(handle, caller, session, "inspect_target")
            return {"fixture": _FIXTURE_SENTINEL, "domain": target.domain_id,
                    "group": target.group_id, "sample_count": 2}
        except Exception as exc:
            raise safe_error(exc) from None

    @mcp.tool(
        description="Explicitly renew fake in-memory fixture credentials for a selected target.",
        run_in_thread=False,
    )
    def renew_fixture_credentials(handle: str, ctx: Context) -> dict[str, Any]:
        caller, session = identity(ctx)
        try:
            target = authorize(handle, caller, session, "read_iot_data")
            lease = credential_runtime.renew(target.auth.context_id)
            return {"target": target.name, "generation": lease.generation,
                    "expires_at": lease.material.expires_at.isoformat(),
                    "fixture": _FIXTURE_SENTINEL}
        except Exception as exc:
            raise safe_error(exc) from None

    @mcp.tool(description="Read synthetic IoT metadata for a selected fixture target.", run_in_thread=False)
    def read_fixture_metadata(handle: str, ctx: Context) -> dict[str, Any]:
        caller, session = identity(ctx)
        try:
            target = authorize(handle, caller, session, "read_iot_data")
            credential_runtime.snapshot(target.auth.context_id)
            return {"fixture": _FIXTURE_SENTINEL, "domain": target.domain_id,
                    "group": target.group_id, "sample_count": 2}
        except Exception as exc:
            raise safe_error(exc) from None

    @mcp.tool(
        description="Close a selected target handle owned by this authenticated session.",
        run_in_thread=False,
    )
    def close_target(handle: str, ctx: Context) -> dict[str, bool]:
        caller, session = identity(ctx)
        try:
            registry.close(handle, caller_id=caller, session_id=session)
            with handle_lock:
                handle_targets.pop(handle, None)
            return {"closed": True}
        except Exception as exc:
            raise safe_error(exc) from None

    app = mcp.http_app(path="/mcp", transport="streamable-http", stateless_http=False,
                       allowed_hosts=[f"{host}:{port}", f"localhost:{port}", f"127.0.0.1:{port}"],
                       allowed_origins=[f"http://localhost:{port}", f"http://127.0.0.1:{port}"])
    return _AuthenticatedHTTP(app, mcp, caller_tokens, host, port, max_sessions,
                              session_ttl_seconds)
