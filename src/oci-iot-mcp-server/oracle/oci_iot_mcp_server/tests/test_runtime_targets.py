"""Focused offline tests for runtime target and binding policy."""

# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v1.0 as shown at
# https://oss.oracle.com/licenses/upl.

from dataclasses import FrozenInstanceError
from concurrent.futures import ThreadPoolExecutor

import pytest

from oracle.oci_iot_mcp_server.runtime_targets import (
    AuthSpec,
    Target,
    TargetPolicyError,
    TargetRegistry,
)


def auth(context="boat", mode="boat_session", *, auth_tenancy="auth-tenancy",
         resource_tenancy="resource-tenancy", region="us-phoenix-1", profile="SSV",
         material_profile="DEFAULT"):
    return AuthSpec(context, mode, profile, auth_tenancy, resource_tenancy, region,
                    material_profile if mode == "boat_session" else None)


def target(name="boat-ssv", domain="domain-ssv", group="group-ssv",
           compartment="comp-ssv", *, authspec=None, operations=None):
    spec = authspec or auth()
    return Target(name, domain, group, compartment, spec.resource_tenancy,
                  spec.region, spec, operations or ["inspect_target", "read_iot_data"])


def code(expected):
    return pytest.raises(TargetPolicyError, match=expected)


def test_shared_boat_targets_and_distinct_wildbio_context():
    ssv_auth = auth()
    ssv = target(authspec=ssv_auth)
    sandbox = target("boat-sandbox", "domain-sandbox", "group-sandbox", "comp-sandbox",
                     authspec=ssv_auth)
    wildbio_auth = auth("wildbio", "api_key", auth_tenancy="wildbio-tenancy",
                        resource_tenancy="wildbio-tenancy", region="us-ashburn-1",
                        profile="WILDBIO")
    wildbio = target("wildbio", "domain-wildbio", "group-wildbio", "comp-wildbio",
                     authspec=wildbio_auth)
    registry = TargetRegistry([ssv, sandbox, wildbio], "rev-1")
    assert registry.resolve_domain("domain-ssv") is ssv
    assert registry.resolve_domain("domain-sandbox") is sandbox
    assert registry.resolve_domain("domain-wildbio") is wildbio
    assert ssv.auth is sandbox.auth
    assert wildbio.auth.context_id != ssv.auth.context_id


@pytest.mark.parametrize("targets, expected", [
    ([target(), target()], "duplicate_target"),
    ([target(), target("other", "domain-ssv", "other-group", "other-comp")],
     "ambiguous_domain"),
    ([target(), target("sandbox", "domain-sandbox", "g", "c",
                       authspec=auth("boat", resource_tenancy="other"))],
     "inconsistent_auth_context"),
])
def test_registry_rejects_conflicts(targets, expected):
    with code(expected):
        TargetRegistry(targets, "rev")


def test_auth_and_target_tenancy_validation():
    with code("auth_tenancy_mismatch"):
        auth("x", "api_key", auth_tenancy="auth", resource_tenancy="resource")
    with code("invalid_material_profile"):
        AuthSpec("x", "api_key", "P", "t", "t", "r", "DEFAULT")
    with code("invalid_material_profile"):
        AuthSpec("x", "boat_session", "P", "auth", "resource", "r")
    with code("target_auth_mismatch"):
        Target("wrong", "d", "g", "c", "other", "r", auth(), ("read",))


def test_unknown_domain_and_non_echoing_errors():
    registry = TargetRegistry([target()], "rev")
    with code("unknown_domain") as exc:
        registry.resolve_domain("sensitive-domain-value")
    assert "sensitive-domain-value" not in str(exc.value)


def test_binding_checks_owner_scope_and_operations():
    registry = TargetRegistry([target()], "rev")
    handle = registry.bind("boat-ssv", "caller-a", "session-a")
    args = dict(caller_id="caller-a", session_id="session-a", domain_id="domain-ssv",
                group_id="group-ssv", compartment_id="comp-ssv",
                resource_tenancy="resource-tenancy", operation="read_iot_data")
    assert registry.authorize(handle, **args).name == "boat-ssv"
    for bad in ({"caller_id": "caller-b"}, {"session_id": "session-b"}):
        with code("binding_owner_mismatch"):
            registry.authorize(handle, **(args | bad))
    for bad in ({"domain_id": "domain-sandbox"}, {"group_id": "wrong"},
                {"compartment_id": "wrong"}, {"resource_tenancy": "wrong"}):
        with code("target_scope_mismatch"):
            registry.authorize(handle, **(args | bad))
    with code("operation_not_allowed"):
        registry.authorize(handle, **(args | {"operation": "write"}))
    with code("binding_owner_mismatch"):
        registry.close(handle, caller_id="caller-b", session_id="session-a")
    registry.close(handle, caller_id="caller-a", session_id="session-a")
    with code("invalid_binding"):
        registry.authorize(handle, **args)


def test_revision_restart_expiry_and_capacity():
    now = [100.0]
    registry = TargetRegistry([target()], "r1", ttl_seconds=5, max_bindings=1,
                              clock=lambda: now[0])
    handle = registry.bind("boat-ssv", "c", "s")
    with code("binding_capacity"):
        registry.bind("boat-ssv", "c", "s")
    args = dict(caller_id="c", session_id="s", domain_id="domain-ssv",
                group_id="group-ssv", compartment_id="comp-ssv",
                resource_tenancy="resource-tenancy", operation="read")
    now[0] = 105
    with code("expired_binding"):
        registry.authorize(handle, **args)
    assert registry.bind("boat-ssv", "c", "s")
    # A new process/config snapshot has no old token state; the old handle is invalid.
    restarted = TargetRegistry([target()], "r2", clock=lambda: now[0])
    with code("invalid_binding"):
        restarted.authorize(handle, **args)


@pytest.mark.parametrize("max_bindings, ttl_seconds", [
    (1.5, 10), (True, 10), (0, 10), (1, float("nan")),
    (1, float("inf")), (1, float("-inf")), (1, True), (1, 0),
    (1, 10**400),
])
def test_registry_rejects_invalid_binding_limits(max_bindings, ttl_seconds):
    with code("invalid_binding_limits"):
        TargetRegistry([target()], "rev", max_bindings=max_bindings,
                       ttl_seconds=ttl_seconds)


@pytest.mark.parametrize("entry", [None, "target"])
def test_registry_rejects_non_target_entries(entry):
    with code("invalid_target"):
        TargetRegistry([entry], "rev")


def test_deep_immutability_and_caller_container_copy():
    operations = ["read_iot_data"]
    spec = auth()
    item = target(operations=operations, authspec=spec)
    operations.append("write")
    assert item.allowed_operations == ("read_iot_data",)
    with pytest.raises(FrozenInstanceError):
        item.name = "changed"
    with pytest.raises(FrozenInstanceError):
        spec.profile = "changed"


def test_binding_capacity_is_atomic_under_concurrent_calls():
    registry = TargetRegistry([target()], "rev", ttl_seconds=None, max_bindings=1)

    def attempt(index):
        try:
            return registry.bind("boat-ssv", f"caller-{index}", f"session-{index}")
        except TargetPolicyError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))
    assert sum(isinstance(result, str) and result not in {
        "binding_capacity", "invalid_binding", "unknown_target"
    } for result in results) == 1
    assert results.count("binding_capacity") == 7
