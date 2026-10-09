"""Offline credential lifecycle contracts for the OCI IoT runtime.

This module deliberately knows nothing about OCI SDKs, profiles, files, or login.
Credential material enters only through an explicitly supplied provider.
"""

# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v1.0 as shown at
# https://oss.oracle.com/licenses/upl.

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Iterator, Protocol

from .runtime_targets import AuthSpec


class CredentialError(RuntimeError):
    """A safe, coded credential lifecycle error with no provider text."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class CredentialMaterial:
    """Opaque trusted-provider payload; repr intentionally excludes its contents."""

    expires_at: datetime
    payload: Any = field(repr=False, compare=False)
    context_id: str = ""
    mode: str = ""
    profile: str = ""
    authentication_tenancy: str = ""
    resource_tenancy: str = ""
    region: str = ""
    material_profile: str | None = None


class CredentialProvider(Protocol):
    """Trusted offline adapter boundary.

    The provider receives the explicit BOAT-session or API-key AuthSpec and returns
    metadata-validated opaque material. BOAT renewal and API-key acquisition are
    separate provider responsibilities; implementations must not change profile,
    tenancy, or auth mode as a fallback. This core performs no login or file access.
    """

    def renew(self, spec: AuthSpec, previous: CredentialMaterial | None) -> CredentialMaterial: ...


@dataclass(frozen=True)
class CredentialLease:
    spec: AuthSpec
    generation: int
    material: CredentialMaterial = field(repr=False, compare=False)


@dataclass(frozen=True)
class CacheKey:
    target_id: str
    context_id: str
    region: str
    generation: int


class CredentialRuntime:
    """Generation-aware credential snapshots and target-scoped cached clients."""

    def __init__(self, provider: CredentialProvider):
        self._provider = provider
        self._lock = RLock()
        self._specs: dict[str, AuthSpec] = {}
        self._leases: dict[str, CredentialLease] = {}
        self._generations: dict[str, int] = {}
        self._invalid: set[str] = set()
        self._cache: dict[CacheKey, Any] = {}

    def register(self, spec: AuthSpec) -> None:
        """Bind a context identity; repeated BOAT targets must share exact metadata."""
        _validate_spec(spec)
        with self._lock:
            previous = self._specs.get(spec.context_id)
            if previous is not None and previous != spec:
                raise CredentialError("auth_context_mismatch", "Authentication context metadata changed.")
            self._specs[spec.context_id] = spec

    def renew(self, context_id: str, *, expected_generation: int | None = None) -> CredentialLease:
        """Explicitly renew; concurrent stale callers coalesce under the context lock."""
        with self._lock:
            spec = self._specs.get(context_id)
            if spec is None:
                raise CredentialError("unknown_auth_context", "Authentication context is not registered.")
            current = self._leases.get(context_id)
            if expected_generation is not None:
                if isinstance(expected_generation, bool) or not isinstance(expected_generation, int) or expected_generation < 0:
                    raise CredentialError("credential_generation_invalid", "Expected credential generation is invalid.")
                if current is None:
                    raise CredentialError("credential_generation_unavailable", "Expected credential generation is no longer active.")
                if current.generation > expected_generation:
                    return self.snapshot(context_id)
                if current.generation < expected_generation:
                    raise CredentialError("credential_generation_conflict", "Expected credential generation is newer than current state.")
            try:
                material = self._provider.renew(spec, current.material if current else None)
            except Exception:
                self._invalidate_locked(context_id)
                raise CredentialError("credential_renewal_failed", "Credential renewal failed; owner action is required.") from None
            try:
                _validate_material(spec, material)
                if not _is_unexpired(material.expires_at):
                    raise CredentialError("credential_expired", "Provider returned expired credential material.")
            except CredentialError:
                self._invalidate_locked(context_id)
                raise
            generation = self._generations.get(context_id, 0) + 1
            lease = CredentialLease(spec, generation, material)
            self._leases[context_id] = lease
            self._generations[context_id] = generation
            self._invalid.discard(context_id)
            self._cache = {key: value for key, value in self._cache.items() if key.context_id != context_id}
            return lease

    def snapshot(self, context_id: str) -> CredentialLease:
        """Return current immutable generation; never renew implicitly."""
        with self._lock:
            lease = self._leases.get(context_id)
            if context_id in self._invalid or lease is None:
                raise CredentialError("reauthentication_required", "No usable credentials; explicit renewal is required.")
            if not _is_unexpired(lease.material.expires_at):
                self._invalidate_locked(context_id)
                raise CredentialError("credential_expired", "Credentials expired; explicit renewal is required.")
            return lease

    def cached(self, target_id: str, lease: CredentialLease, factory) -> Any:
        """Get/create a client bound to target, context, region, and generation."""
        key = CacheKey(target_id, lease.spec.context_id, lease.spec.region, lease.generation)
        with self._lock:
            if self.snapshot(lease.spec.context_id) is not lease:
                raise CredentialError("credential_generation_stale", "Credential generation changed; obtain a current lease.")
            if key not in self._cache:
                try:
                    self._cache[key] = factory(lease)
                except Exception:
                    raise CredentialError("client_creation_failed", "Credentialed client creation failed.") from None
            return self._cache[key]

    def _invalidate_locked(self, context_id: str) -> None:
        self._invalid.add(context_id)
        self._leases.pop(context_id, None)
        self._cache = {key: value for key, value in self._cache.items() if key.context_id != context_id}


@dataclass(frozen=True)
class DatabaseCredentialPair:
    target_id: str
    context_id: str
    token_generation: int
    key_generation: int
    expires_at: datetime
    token: Any = field(repr=False, compare=False)
    private_key: Any = field(repr=False, compare=False)


class DatabasePairStore:
    """Keep DB token/key replacements atomic and prohibit replacement while leased."""

    def __init__(self):
        self._lock = RLock()
        self._pairs: dict[tuple[str, str], DatabaseCredentialPair] = {}
        self._active: dict[tuple[str, str], int] = {}

    def replace(self, *, target_id: str, context_id: str, token_generation: int,
                key_generation: int, expires_at: datetime, token: Any,
                private_key: Any) -> DatabaseCredentialPair:
        with self._lock:
            key = (target_id, context_id)
            if self._active.get(key, 0):
                raise CredentialError("database_pair_in_use", "Disconnect database clients before replacing credentials.")
            if token_generation != key_generation:
                raise CredentialError("database_pair_mismatch", "Database token and key generations do not match.")
            if (isinstance(token_generation, bool) or not isinstance(token_generation, int)
                    or token_generation <= 0 or isinstance(key_generation, bool)
                    or not isinstance(key_generation, int) or not target_id or not context_id
                    or token is None or private_key is None
                    or not _is_unexpired(expires_at)):
                raise CredentialError("database_pair_invalid", "Database credential pair is invalid or expired.")
            previous = self._pairs.get(key)
            if token_generation <= (previous.token_generation if previous else 0):
                raise CredentialError("database_generation_invalid", "Database credential generation must increase.")
            pair = DatabaseCredentialPair(target_id, context_id, token_generation,
                                          key_generation, expires_at, token, private_key)
            self._pairs[key] = pair
            return pair

    @contextmanager
    def lease(self, target_id: str, context_id: str) -> Iterator[DatabaseCredentialPair]:
        with self._lock:
            key = (target_id, context_id)
            pair = self._pairs.get(key)
            if pair is None:
                raise CredentialError("database_credentials_missing", "Database credentials are unavailable.")
            if not _is_unexpired(pair.expires_at):
                raise CredentialError("database_credentials_expired", "Database credential pair expired.")
            self._active[key] = self._active.get(key, 0) + 1
        try:
            yield pair
        finally:
            with self._lock:
                count = self._active[key] - 1
                if count:
                    self._active[key] = count
                else:
                    del self._active[key]


def _validate_spec(spec: AuthSpec) -> None:
    if not all((spec.context_id, spec.profile, spec.authentication_tenancy,
                spec.resource_tenancy, spec.region)):
        raise CredentialError("auth_context_invalid", "Authentication context metadata is incomplete.")
    if spec.mode not in ("boat_session", "api_key"):
        raise CredentialError("auth_mode_unsupported", "Authentication mode is unsupported.")
    if spec.mode == "api_key" and (spec.authentication_tenancy != spec.resource_tenancy or spec.material_profile is not None):
        raise CredentialError("auth_context_invalid", "API-key context metadata is inconsistent.")
    if spec.mode == "boat_session" and spec.material_profile != "DEFAULT":
        raise CredentialError("auth_context_invalid", "BOAT session material profile is invalid.")


def _validate_material(spec: AuthSpec, material: CredentialMaterial) -> None:
    if not isinstance(material, CredentialMaterial):
        raise CredentialError("credential_material_invalid", "Credential provider returned invalid material.")
    expected = (spec.profile, spec.authentication_tenancy, spec.resource_tenancy,
                spec.region, spec.material_profile, spec.context_id, spec.mode)
    actual = (material.profile, material.authentication_tenancy, material.resource_tenancy,
              material.region, material.material_profile, material.context_id, material.mode)
    if actual != expected:
        raise CredentialError("credential_context_mismatch", "Credential material does not match its selected context.")
    if material.payload is None:
        raise CredentialError("credential_material_missing", "Credential provider returned no credential material.")


def _is_unexpired(expires_at: datetime) -> bool:
    if not isinstance(expires_at, datetime) or expires_at.tzinfo is None or expires_at.utcoffset() is None:
        return False
    return expires_at > datetime.now(timezone.utc)
