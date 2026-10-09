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
invalidates previous handles. This bounded fixture policy is not a production
long-running session-reaping design. It must be settled before deployment.

Container tests publish only `127.0.0.1` and use a private internal network,
non-root identity, read-only root, dropped capabilities, no-new-privileges,
bounded memory/CPU/PIDs/logs and a private read-only caller-token volume.
No host credential directories, projects or Docker socket enter the service.
All tokens/data in disposable tests are generated local fixtures, not OCI secrets.
