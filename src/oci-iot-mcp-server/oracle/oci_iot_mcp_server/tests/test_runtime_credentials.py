"""Focused tests for offline credential lifecycle contracts."""

# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v1.0 as shown at
# https://oss.oracle.com/licenses/upl.

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event, Lock

import pytest

from oracle.oci_iot_mcp_server.runtime_credentials import (
    AuthSpec,
    CredentialError,
    CredentialMaterial,
    CredentialRuntime,
    DatabasePairStore,
)
from oracle.oci_iot_mcp_server.runtime_targets import TargetPolicyError


def spec(context="boat", mode="boat_session", *, profile="ops", auth_tenancy="auth",
         resource_tenancy="resource", region="us-phoenix-1", material_profile="DEFAULT"):
    return AuthSpec(context, mode, profile, auth_tenancy, resource_tenancy, region, material_profile)


def material(auth_spec, payload, *, expires=None, **overrides):
    values = {
        "expires_at": expires or datetime.now(timezone.utc) + timedelta(hours=1),
        "payload": payload,
        "context_id": auth_spec.context_id,
        "mode": auth_spec.mode,
        "profile": auth_spec.profile,
        "authentication_tenancy": auth_spec.authentication_tenancy,
        "resource_tenancy": auth_spec.resource_tenancy,
        "region": auth_spec.region,
        "material_profile": auth_spec.material_profile,
    }
    values.update(overrides)
    return CredentialMaterial(**values)


class Provider:
    def __init__(self):
        self.calls = 0
        self.lock = Lock()
        self.failure = None

    def renew(self, auth_spec, previous):
        with self.lock:
            self.calls += 1
            call = self.calls
        if self.failure:
            raise RuntimeError(self.failure)
        return material(auth_spec, {"signer": call, "client": call})


def test_expiry_requires_explicit_renewal_and_rotates_signer_and_client():
    provider = Provider()
    runtime = CredentialRuntime(provider)
    auth = spec()
    runtime.register(auth)
    first = runtime.renew(auth.context_id)
    client1 = runtime.cached("ssv", first, lambda lease: (lease.generation, lease.material.payload["client"]))

    expired = CredentialMaterial(
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1), payload="secret",
        context_id=auth.context_id, mode=auth.mode,
        profile="ops", authentication_tenancy="auth", resource_tenancy="resource",
        region="us-phoenix-1", material_profile="DEFAULT",
    )
    runtime._leases[auth.context_id] = first.__class__(auth, 1, expired)
    with pytest.raises(CredentialError, match="explicit renewal"):
        runtime.snapshot(auth.context_id)
    second = runtime.renew(auth.context_id)
    client2 = runtime.cached("ssv", second, lambda lease: (lease.generation, lease.material.payload["client"]))
    assert second.generation == 2
    assert client1 != client2
    assert second.material.payload["signer"] != first.material.payload["signer"]


def test_auth_metadata_mismatch_and_boat_context_reuse_are_rejected():
    runtime = CredentialRuntime(Provider())
    runtime.register(spec())
    with pytest.raises(CredentialError) as exc:
        runtime.register(spec(region="us-ashburn-1"))
    assert exc.value.code == "auth_context_mismatch"

    api = spec("normal", "api_key", auth_tenancy="same", resource_tenancy="same", material_profile=None)
    runtime.register(api)
    with pytest.raises(TargetPolicyError) as exc:
        AuthSpec("bad-api", "api_key", "ops", "other", "same", "us-phoenix-1", None)
    assert exc.value.code == "auth_tenancy_mismatch"


def test_concurrent_stale_renewals_share_one_new_generation():
    entered, release = Event(), Event()

    class SlowProvider(Provider):
        def renew(self, auth_spec, previous):
            with self.lock:
                self.calls += 1
                call = self.calls
            if call == 2:
                entered.set()
                assert release.wait(2)
            return material(auth_spec, {"signer": call})

    provider = SlowProvider()
    runtime = CredentialRuntime(provider)
    auth = spec()
    runtime.register(auth)
    initial = runtime.renew(auth.context_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(runtime.renew, auth.context_id, expected_generation=initial.generation)
        assert entered.wait(2)
        second = pool.submit(runtime.renew, auth.context_id, expected_generation=initial.generation)
        release.set()
        assert first.result().generation == second.result().generation == 2
    assert provider.calls == 2


def test_failed_renewal_invalidates_new_work_and_redacts_provider_error():
    provider = Provider()
    runtime = CredentialRuntime(provider)
    auth = spec()
    runtime.register(auth)
    first = runtime.renew(auth.context_id)
    runtime.cached("ssv", first, lambda _: object())
    provider.failure = "PRIVATE_TOKEN_MARKER"
    with pytest.raises(CredentialError) as exc:
        runtime.renew(auth.context_id, expected_generation=first.generation)
    assert exc.value.code == "credential_renewal_failed"
    assert "PRIVATE_TOKEN_MARKER" not in str(exc.value)
    assert "PRIVATE_TOKEN_MARKER" not in repr(exc.value)
    with pytest.raises(CredentialError):
        runtime.snapshot(auth.context_id)


def test_provider_metadata_mismatch_fails_closed_without_fallback():
    class WrongProvider(Provider):
        def renew(self, auth_spec, previous):
            return material(auth_spec, "opaque", region="wrong-region")

    runtime = CredentialRuntime(WrongProvider())
    auth = spec()
    runtime.register(auth)
    with pytest.raises(CredentialError) as exc:
        runtime.renew(auth.context_id)
    assert exc.value.code == "credential_context_mismatch"


def test_cache_is_scoped_by_target_auth_region_and_generation_and_old_snapshot_lives():
    runtime = CredentialRuntime(Provider())
    auth = spec()
    runtime.register(auth)
    old = runtime.renew(auth.context_id)
    marker = object()
    assert runtime.cached("ssv", old, lambda _: marker) is marker
    assert runtime.cached("sandbox", old, lambda _: object()) is not marker
    new = runtime.renew(auth.context_id, expected_generation=old.generation)
    assert new.generation == old.generation + 1
    assert old.material.payload["signer"] == 1
    with pytest.raises(CredentialError) as exc:
        runtime.cached("ssv", old, lambda _: "stale")
    assert exc.value.code == "credential_generation_stale"
    newer = runtime.cached("ssv", new, lambda lease: lease.material.payload["signer"])
    assert newer == 2


def test_secret_material_is_omitted_from_repr_and_db_pair_replacement_requires_disconnect():
    auth = spec()
    secret = "TOP_SECRET_MARKER"
    cred = material(auth, secret)
    assert secret not in repr(cred)
    store = DatabasePairStore()
    pair = store.replace(target_id="ssv", context_id="boat", token_generation=1,
                         key_generation=1, expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                         token="TOKEN_MARKER", private_key="KEY_MARKER")
    assert "TOKEN_MARKER" not in repr(pair) and "KEY_MARKER" not in repr(pair)
    with store.lease("ssv", "boat") as active:
        assert active.token_generation == 1
        with pytest.raises(CredentialError) as exc:
            store.replace(target_id="ssv", context_id="boat", token_generation=2,
                          key_generation=2, expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                          token="next-token", private_key="next-key")
        assert exc.value.code == "database_pair_in_use"
    with pytest.raises(CredentialError) as exc:
        store.replace(target_id="ssv", context_id="boat", token_generation=2,
                      key_generation=1, expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                      token="mixed", private_key="pair")
    assert exc.value.code == "database_pair_mismatch"
    replaced = store.replace(target_id="ssv", context_id="boat", token_generation=2,
                             key_generation=2, expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                             token="next-token", private_key="next-key")
    assert replaced.token_generation == 2
    with pytest.raises(CredentialError):
        store.replace(target_id="ssv", context_id="boat", token_generation=2,
                      key_generation=2, expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                      token="mixed", private_key="pair")
    other = store.replace(target_id="sandbox", context_id="boat", token_generation=1,
                          key_generation=1, expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                          token="other", private_key="other-key")
    assert other.target_id == "sandbox"
    with pytest.raises(CredentialError) as exc:
        store.replace(target_id="ssv", context_id="boat", token_generation=3,
                      key_generation=3, expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                      token=None, private_key="missing-token")
    assert exc.value.code == "database_pair_invalid"


def test_failure_recovery_increments_generation_and_malformed_material_invalidates():
    provider = Provider()
    runtime = CredentialRuntime(provider)
    auth = spec()
    runtime.register(auth)
    first = runtime.renew(auth.context_id)
    provider.failure = "HIDDEN_PROVIDER_DETAIL"
    with pytest.raises(CredentialError) as exc:
        runtime.renew(auth.context_id, expected_generation=first.generation)
    assert exc.value.code == "credential_renewal_failed"
    provider.failure = None
    recovered = runtime.renew(auth.context_id)
    assert recovered.generation == 2
    with pytest.raises(CredentialError) as exc:
        runtime.renew(auth.context_id, expected_generation=4)
    assert exc.value.code == "credential_generation_conflict"

    class MalformedProvider(Provider):
        def renew(self, auth_spec, previous):
            return object()

    malformed_runtime = CredentialRuntime(Provider())
    malformed_runtime.register(auth)
    existing = malformed_runtime.renew(auth.context_id)
    malformed_runtime._provider = MalformedProvider()
    with pytest.raises(CredentialError) as exc:
        malformed_runtime.renew(auth.context_id, expected_generation=existing.generation)
    assert exc.value.code == "credential_material_invalid"
    with pytest.raises(CredentialError):
        malformed_runtime.snapshot(auth.context_id)


def test_client_factory_errors_are_redacted_and_not_cached():
    runtime = CredentialRuntime(Provider())
    auth = spec()
    runtime.register(auth)
    lease = runtime.renew(auth.context_id)
    with pytest.raises(CredentialError) as exc:
        runtime.cached("ssv", lease, lambda _: (_ for _ in ()).throw(RuntimeError("SECRET_IN_SIGNER_ERROR")))
    assert exc.value.code == "client_creation_failed"
    assert "SECRET_IN_SIGNER_ERROR" not in str(exc.value)
    assert runtime.cached("ssv", lease, lambda _: "valid-client") == "valid-client"

