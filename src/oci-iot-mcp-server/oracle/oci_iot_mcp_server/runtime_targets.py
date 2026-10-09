"""Offline target policy and caller-bound runtime handles.

This module deliberately performs no profile, credential, filesystem, or OCI work.
Typical use: ``registry.resolve_domain(domain)``, then ``registry.bind(target.name,
caller_id, session_id)``; pass the returned opaque string to ``authorize`` for each
operation and ``close`` it when finished.
"""

# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v1.0 as shown at
# https://oss.oracle.com/licenses/upl.

from __future__ import annotations

from dataclasses import dataclass, field
import secrets
import math
from threading import RLock
import time
from types import MappingProxyType
from typing import Callable, Iterable


class TargetPolicyError(ValueError):
    """Stable, non-sensitive policy failure exposed through ``code``."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


READ_OPERATION_FAMILIES = frozenset({
    "inspect", "inspect_target", "connect", "read", "read_domain", "read_group",
    "read_iot_data",
})


def _required(value: str, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TargetPolicyError(code)
    return value


@dataclass(frozen=True, slots=True)
class AuthSpec:
    context_id: str
    mode: str
    profile: str
    authentication_tenancy: str
    resource_tenancy: str
    region: str
    material_profile: str | None = None

    def __post_init__(self) -> None:
        for value in (self.context_id, self.profile, self.authentication_tenancy,
                      self.resource_tenancy, self.region):
            _required(value, "invalid_auth_spec")
        if self.mode not in ("boat_session", "api_key"):
            raise TargetPolicyError("invalid_auth_mode")
        if self.mode == "boat_session" and self.profile == "DEFAULT":
            raise TargetPolicyError("invalid_operational_profile")
        if self.mode == "api_key" and self.authentication_tenancy != self.resource_tenancy:
            raise TargetPolicyError("auth_tenancy_mismatch")
        if self.mode == "boat_session" and self.material_profile != "DEFAULT":
            raise TargetPolicyError("invalid_material_profile")
        if self.mode == "api_key" and self.material_profile is not None:
            raise TargetPolicyError("invalid_material_profile")


@dataclass(frozen=True, slots=True)
class Target:
    name: str
    domain_id: str
    group_id: str
    compartment_id: str
    resource_tenancy: str
    region: str
    auth: AuthSpec
    allowed_operations: tuple[str, ...]

    def __post_init__(self) -> None:
        for value in (self.name, self.domain_id, self.group_id, self.compartment_id,
                      self.resource_tenancy, self.region):
            _required(value, "invalid_target")
        # Copy caller-owned iterables into immutable, normalized tuple storage.
        if not isinstance(self.auth, AuthSpec):
            raise TargetPolicyError("invalid_target_auth")
        try:
            ops = tuple(self.allowed_operations)
        except TypeError:
            raise TargetPolicyError("invalid_operations") from None
        if not ops or any(not isinstance(x, str) or not x.strip() for x in ops):
            raise TargetPolicyError("invalid_operations")
        if any(x not in READ_OPERATION_FAMILIES for x in ops):
            raise TargetPolicyError("unsupported_operation_family")
        if len(set(ops)) != len(ops):
            raise TargetPolicyError("duplicate_operation")
        object.__setattr__(self, "allowed_operations", ops)
        if self.auth.resource_tenancy != self.resource_tenancy or self.auth.region != self.region:
            raise TargetPolicyError("target_auth_mismatch")


@dataclass(frozen=True, slots=True)
class Binding:
    """Internal immutable snapshot; callers receive only its random token."""
    token: str = field(repr=False)
    caller_id: str = field(repr=False)
    session_id: str = field(repr=False)
    revision: str = field(repr=False)
    target: Target = field(repr=False)
    expires_at: float | None = field(repr=False)


class TargetRegistry:
    """Immutable target snapshot with bounded, process-local binding handles."""

    def __init__(self, targets: Iterable[Target], revision: str, *,
                 max_bindings: int = 256, ttl_seconds: float | None = 3600,
                 clock: Callable[[], float] = time.time):
        _required(revision, "invalid_revision")
        if isinstance(max_bindings, bool) or not isinstance(max_bindings, int) or max_bindings <= 0:
            raise TargetPolicyError("invalid_binding_limits")
        if ttl_seconds is not None:
            try:
                valid_ttl = (
                    not isinstance(ttl_seconds, bool)
                    and isinstance(ttl_seconds, (int, float))
                    and math.isfinite(ttl_seconds)
                    and ttl_seconds > 0
                )
            except (OverflowError, ValueError):
                valid_ttl = False
            if not valid_ttl:
                raise TargetPolicyError("invalid_binding_limits")
        by_name: dict[str, Target] = {}
        by_domain: dict[str, Target] = {}
        contexts: dict[str, AuthSpec] = {}
        for target in tuple(targets):
            if not isinstance(target, Target):
                raise TargetPolicyError("invalid_target")
            if target.name in by_name:
                raise TargetPolicyError("duplicate_target")
            if target.domain_id in by_domain:
                raise TargetPolicyError("ambiguous_domain")
            previous = contexts.get(target.auth.context_id)
            if previous is not None and previous != target.auth:
                raise TargetPolicyError("inconsistent_auth_context")
            by_name[target.name] = target
            by_domain[target.domain_id] = target
            contexts[target.auth.context_id] = target.auth
        self._targets = MappingProxyType(by_name)
        self._domains = MappingProxyType(by_domain)
        self._revision = revision
        self._max_bindings = max_bindings
        self._ttl = ttl_seconds
        self._clock = clock
        self._bindings: dict[str, Binding] = {}
        self._lock = RLock()

    @property
    def revision(self) -> str:
        return self._revision

    def resolve_domain(self, domain_id: str) -> Target:
        try:
            return self._domains[domain_id]
        except (KeyError, TypeError):
            raise TargetPolicyError("unknown_domain") from None

    def bind(self, target_name: str, caller_id: str, session_id: str) -> str:
        _required(caller_id, "invalid_binding_owner")
        _required(session_id, "invalid_binding_owner")
        try:
            target = self._targets[target_name]
        except (KeyError, TypeError):
            raise TargetPolicyError("unknown_target") from None
        with self._lock:
            self._purge_expired()
            if len(self._bindings) >= self._max_bindings:
                raise TargetPolicyError("binding_capacity")
            token = secrets.token_urlsafe(32)
            expires = None if self._ttl is None else self._clock() + self._ttl
            self._bindings[token] = Binding(token, caller_id, session_id, self.revision, target, expires)
            return token

    def authorize(self, handle: str, *, caller_id: str, session_id: str,
                  domain_id: str, group_id: str, compartment_id: str,
                  resource_tenancy: str, operation: str) -> Target:
        with self._lock:
            binding = self._get(handle)
        if binding.caller_id != caller_id or binding.session_id != session_id:
            raise TargetPolicyError("binding_owner_mismatch")
        target = binding.target
        if (domain_id, group_id, compartment_id, resource_tenancy) != (
                target.domain_id, target.group_id, target.compartment_id, target.resource_tenancy):
            raise TargetPolicyError("target_scope_mismatch")
        if operation not in target.allowed_operations:
            raise TargetPolicyError("operation_not_allowed")
        return target

    def close(self, handle: str, *, caller_id: str, session_id: str) -> None:
        with self._lock:
            binding = self._get(handle)
            if binding.caller_id != caller_id or binding.session_id != session_id:
                raise TargetPolicyError("binding_owner_mismatch")
            del self._bindings[handle]

    def _get(self, handle: str) -> Binding:
        if not isinstance(handle, str):
            raise TargetPolicyError("invalid_binding")
        with self._lock:
            binding = self._bindings.get(handle)
            if binding is None:
                raise TargetPolicyError("invalid_binding")
            if binding.revision != self.revision:
                del self._bindings[handle]
                raise TargetPolicyError("stale_binding")
            if binding.expires_at is not None and self._clock() >= binding.expires_at:
                del self._bindings[handle]
                raise TargetPolicyError("expired_binding")
            return binding

    def _purge_expired(self) -> None:
        if self._ttl is None:
            return
        with self._lock:
            now = self._clock()
            for token, binding in tuple(self._bindings.items()):
                if binding.expires_at is not None and now >= binding.expires_at:
                    del self._bindings[token]

