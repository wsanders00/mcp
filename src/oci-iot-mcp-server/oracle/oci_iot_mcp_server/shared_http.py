"""Authenticated, cloud-disabled HTTP access to the actual IoT MCP catalog."""

from __future__ import annotations

import hmac
import json
import os
import re
import stat
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from starlette.responses import JSONResponse, PlainTextResponse

SUPPORTED_TOOL_COUNT = 72
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{32,}\Z")


class _CloudDisabled(Middleware):
    """Reject every tool request before registry lookup or tool code."""

    async def on_call_tool(self, context: MiddlewareContext, call_next: CallNext):
        raise ToolError("Cloud operations are disabled in shared HTTP mode.")


class _AuthenticatedHTTP:
    """Bearer-authenticate local HTTP requests before reaching FastMCP."""

    def __init__(self, app, tokens: Mapping[str, str], port: int, readonly=False):
        self.app = app
        self.tokens = dict(tokens)
        self.hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        self.readonly = readonly

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        header_values: dict[bytes, list[bytes]] = {}
        for key, value in scope.get("headers", []):
            header_values.setdefault(key.lower(), []).append(value)
        if any(len(header_values.get(key, [])) != 1 for key in (b"host", b"authorization")) \
                or len(header_values.get(b"origin", [])) > 1:
            await PlainTextResponse("request rejected", status_code=400)(scope, receive, send)
            return

        headers = {key: values[0] for key, values in header_values.items()}
        host = headers[b"host"].decode("latin1")
        if host not in self.hosts:
            await PlainTextResponse("request rejected", status_code=400)(scope, receive, send)
            return

        origin = headers.get(b"origin")
        if origin:
            try:
                parsed = urlsplit(origin.decode("latin1"))
                if (parsed.scheme != "http" or parsed.netloc not in self.hosts
                        or parsed.path not in ("", "/") or parsed.username is not None
                        or parsed.password is not None or parsed.query or parsed.fragment):
                    raise ValueError
            except (UnicodeError, ValueError):
                await PlainTextResponse("request rejected", status_code=403)(scope, receive, send)
                return

        authorization = headers[b"authorization"].decode("latin1")
        scheme, _, supplied = authorization.partition(" ")
        try:
            supplied.encode("ascii")
        except UnicodeEncodeError:
            supplied = ""
        matched_token = next((token for token in self.tokens
                              if hmac.compare_digest(supplied, token)), None)
        authenticated = scheme.lower() == "bearer" and matched_token is not None
        if not authenticated:
            await PlainTextResponse(
                "authentication required", status_code=401,
                headers={"www-authenticate": "Bearer"},
            )(scope, receive, send)
            return

        if scope["path"] == "/healthz":
            if scope["method"] != "GET":
                await PlainTextResponse("method not allowed", status_code=405)(scope, receive, send)
                return
            await JSONResponse({
                "cloud_access": "read_only" if self.readonly else "disabled",
                "tool_count": SUPPORTED_TOOL_COUNT,
                **({"enabled_tools": ["get_digital_twin_model", "get_iot_domain"]}
                   if self.readonly else {}),
            })(
                scope, receive, send
            )
            return
        if scope["path"] != "/mcp":
            await PlainTextResponse("not found", status_code=404)(scope, receive, send)
            return
        if self.readonly:
            from .shared_readonly import _CALLER

            caller_token = _CALLER.set(self.tokens[matched_token])
            try:
                await self.app(scope, receive, send)
            finally:
                _CALLER.reset(caller_token)
        else:
            await self.app(scope, receive, send)


def load_caller_tokens(path: Path) -> dict[str, str]:
    """Read a private token-to-caller mapping without exposing its contents."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_uid != os.getuid() or info.st_size > 65536):
                raise ValueError
            with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as config_file:
                tokens = json.load(config_file)
        finally:
            os.close(fd)
        if (not isinstance(tokens, dict) or not tokens
                or any(not isinstance(token, str) or _TOKEN_PATTERN.fullmatch(token) is None
                       or not isinstance(caller, str) or not caller.strip()
                       for token, caller in tokens.items())):
            raise ValueError
        return tokens
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        raise RuntimeError("shared_http_configuration_invalid") from None


def build_shared_http_app(mcp: FastMCP, *, caller_tokens: Mapping[str, str], port: int = 8765):
    """Serve the existing registry in stateless HTTP mode with every tool disabled."""
    if (not isinstance(caller_tokens, Mapping) or not caller_tokens
            or any(not isinstance(token, str) or _TOKEN_PATTERN.fullmatch(token) is None
                   or not isinstance(caller, str) or not caller.strip()
                   for token, caller in caller_tokens.items())
            or isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535):
        raise ValueError("shared_http_configuration_invalid")
    if not any(isinstance(middleware, _CloudDisabled) for middleware in mcp.middleware):
        mcp.add_middleware(_CloudDisabled())
    app = mcp.http_app(
        path="/mcp", transport="streamable-http", stateless_http=True,
        allowed_hosts=[f"127.0.0.1:{port}", f"localhost:{port}"],
        allowed_origins=[f"http://127.0.0.1:{port}", f"http://localhost:{port}"],
    )
    return _AuthenticatedHTTP(app, caller_tokens, port)


def build_shared_readonly_http_app(
    mcp: FastMCP, *, caller_tokens: Mapping[str, str], policy, port: int = 8765,
):
    """Serve the catalog with a bounded OCI read-only middleware."""
    from .shared_readonly import ReadPolicy, SharedReadOnlyMiddleware

    if (not isinstance(caller_tokens, Mapping) or len(caller_tokens) != 2
            or any(not isinstance(token, str) or _TOKEN_PATTERN.fullmatch(token) is None
                   or not isinstance(caller, str) or not caller.strip()
                   for token, caller in caller_tokens.items())
            or len(set(caller_tokens.values())) != 2
            or not isinstance(policy, ReadPolicy)
            or set(caller_tokens.values()) != policy.allowed_callers
            or isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535):
        raise ValueError("shared_readonly_configuration_invalid")
    middleware = SharedReadOnlyMiddleware(policy)
    mcp.add_middleware(middleware)
    app = mcp.http_app(
        path="/mcp", transport="streamable-http", stateless_http=True,
        allowed_hosts=[f"127.0.0.1:{port}", f"localhost:{port}"],
        allowed_origins=[f"http://127.0.0.1:{port}", f"http://localhost:{port}"],
    )
    return _AuthenticatedHTTP(app, caller_tokens, port, readonly=True)
