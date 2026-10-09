# Offline connection contracts

The `runtime_targets` and `runtime_credentials` modules are disconnected internal
policy components. They do not register MCP tools, change existing authentication,
read OCI profiles/credentials, construct SDK signers or make network calls.
They are not a working BOAT login or database connector.

## Target binding

Create immutable `AuthSpec` and `Target` records from owner-approved private
configuration. BOAT explicitly names its operational profile and generated
`DEFAULT` material profile, authentication tenancy, resource tenancy and region.
Normal API-key records name an existing profile and require matching authentication
and resource tenancy. No default profile or alternate auth mode is selected.
Actual credential parsing/signing must later use `oracle-mcp-common`.

`TargetRegistry` snapshots the approved records and a configuration revision.
`resolve_domain` rejects unknown/ambiguous domains; `bind` issues opaque handles
for an authenticated caller/session. Authenticate callers in the future HTTP
layer before invoking this internal API: caller/session strings do not authenticate
themselves. `authorize` requires the same caller/session, exact domain/group,
compartment/resource tenancy and an allowed operation. Binding policy separates
accidental target use; it does not create different OCI IAM permissions.

Validate every binding **before** requesting credentials or invoking a provider.
Only the exact configured scope is supported. Other resource identifiers require
authoritative membership checks in a later live adapter; these modules do not
claim to verify twins, models or arbitrary OCI resources. A new process/registry
does not accept old handles. Changing targets creates another binding.

## Credential generations

`CredentialRuntime` accepts a trusted, explicitly supplied provider. Creating it
and registering an `AuthSpec` do not contact that provider. `renew` is explicit;
the provider contract must atomically return material with matching identity,
profile/region/tenancy and expiry metadata. No real provider is included.
The service validates snapshots, advances generations, rejects stale new client
lookups and serializes renewal. Already acquired clients keep their original
generation; they must not be reused for new calls after rotation.

Cache identity includes target, context, region and generation. Use an authorized
registry target as the target identifier, not unchecked caller input. A failed or
expired credential closes new work. Provider failures become fixed errors; no
silent mode fallback, implicit login or retry of cloud operations exists.

`DatabasePairStore` exercises only an in-memory matched token/key generation and
lease policy. It does not establish real cryptographic pairing, authenticate a
database, write credentials, choose a network route or supervise a tunnel.
Later providers must obtain actual matched credentials and confirm authoritative
domain-group scope. Disconnect before replacing leased credentials.

Opaque payloads remain private to trusted provider/client code and are excluded
from repr/error output. They are not encrypted memory or a security boundary
against code running inside this Python process or the host/Docker owner.
Do not serialize material/lease objects to MCP responses. No real values belong
in public examples, image build contexts or tracked source.

## Verification and remaining gates

The focused `test_runtime_targets.py` and `test_runtime_credentials.py` fixtures
exercise target separation, stale/expired handles, rotation/concurrent renewal,
redaction and DB pair leases without OCI. Run the normal package Moon test and
root lint tasks for integration validation with sanitized credentials and offline
dependencies. Fixtures establish internal policy, not live account readiness.

Managed offline image preparation belongs in the environment repository's
`tools/oci-iot-runtime`. It packages only these contracts. Approved image build,
shared authenticated HTTP, native context deferral, actual BOAT/API-key providers,
OCI metadata reads and database access remain separate increments.

## Shared HTTP fixture

`runtime_http.build_fixture_app` provides only synthetic targets and five fixed
tools. It has no real provider or OCI call path. An explicit `server.main` flag
selects it; default stdio behavior is preserved. Runtime caller tokens come from
an owner-readable regular mode-0600 file, never the image or a tool response.
The service checks bearer identity, loopback Host/Origin and MCP session ownership
before tool execution. Session identifiers do not authenticate callers.

Native clients still need disposable multi-client runtime evidence; tool-context
deferral is a separate gate. Fixture target handles are bound to both caller and
MCP session. Synthetic BOAT targets share a fake auth context, while the normal
fixture has another. Startup/listing performs no fake renewal or account work.

FastMCP 3.4.5 lacks a supported external session-removal API. This fixture caps
successful initializations for the process lifetime (default 32); expiry/DELETE
revoke access but do not recycle those slots. Restart permits new sessions and
invalidates previous handles. This remains fixture-only behavior.

## Shared cloud-disabled catalog

`server.main --shared-http-cloud-disabled` serves the actual 72-tool FastMCP
registry at `/mcp` using stateless Streamable HTTP. A FastMCP `on_call_tool`
middleware rejects every tool invocation before registry lookup and tool
execution, including calls for unknown tool names. Tool discovery remains
available, but no OCI SDK client, profile, credential, token, or ORDS request is
used by this mode. The regular stdio entry point and offline fixture remain
separate.

All `/mcp` requests and `GET /healthz` require a configured bearer token. The
caller mapping is loaded at startup from a regular file owned by the process UID
with mode `0600`; bearer tokens must be at least 32 ASCII characters. Host and
Origin checks accept only the configured local loopback names. Health returns
`{"cloud_access":"disabled","tool_count":72}` and contains no caller or
credential data. Uvicorn access logging is disabled.

Stateless transport removes the fixture's cumulative 32-session issue for this
mode. This is still an offline authenticated catalog and health surface, not a
provider adapter or a live OCI readiness check. Real tool execution, credential
provisioning, OCI egress, provider authorization and live validation remain
separate work and are not enabled by this change.

The synthetic fixture's container tests publish only `127.0.0.1` and use a
private internal network, non-root identity, read-only root, dropped
capabilities, no-new-privileges, bounded memory/CPU/PIDs/logs and a private
read-only caller-token volume.
No host credential directories, projects or Docker socket enter the service.
All tokens/data in disposable tests are generated local fixtures, not OCI secrets.

## Shared read-only OCI mode

`server.main --shared-http-read-only --caller-config PATH --read-policy PATH`
serves the same stateless 72-tool catalog while enabling only `get_iot_domain`
and `get_digital_twin_model`. The private version-1 policy binds one region,
security-token profile/configuration, tenancy, domain group, domain,
compartment, one explicit model ID, credential generation, and exactly two
allowed caller identifiers. The caller-token file must have exactly two
entries whose caller IDs match that policy set. Policy, OCI config,
security-token, and private-key files must be
regular nonsymlink files owned by the service UID with mode `0600`.

The shared HTTP bearer identity is bound to the request context and checked
against `allowed_callers` before dispatch. The first permitted call builds one
OCI SDK client; all calls in that process share the same immutable
security-token signer, and token expiry requires an explicit process restart
after reauthentication. Client requests are restricted to exact HTTPS GET
paths for the configured domain and model allowlist, with TLS verification,
no redirects, no proxy environment inheritance, no retry, and bounded
connect/read timeouts. Domain response identity, group, and compartment and
model response identity and domain are checked before returning data. Errors
are sanitized. Health reports `cloud_access: read_only`, `tool_count: 72`, and
the sorted names of the two enabled tools.

This is an implementation contract. Offline unit tests use mocked SDK clients;
they do not establish OCI reachability, cloud authorization, deployment state,
or provider behavior.
