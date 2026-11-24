# Changelog

## Unreleased

### Added

- Add opt-in full-registry shared HTTP with loopback bearer/Host/Origin checks, authenticated service binding, initialized Common OCI context and auth drift refusal. Native service staging is separate from deployment; owner refresh requires an explicit restart.

### Fixed

- Resolve friendly domain names/short IDs and twin names across SDK pages instead of claiming absence or uniqueness from the first page. Lookup requests 100 rows per page, bounded by 100 pages or 10,000 returned rows; incomplete or repeated-token scans fail with `incomplete_lookup` and OCID retry guidance. Additional list calls add latency. Ambiguity may return early with only the first two distinct matching candidates; public list-tool shapes are unchanged.

### Changed

- Document the immutable Moon lock and repository setup for development.

### Added

- Add an authenticated shared HTTP read-only mode with policy-bound IoT domain and digital-twin model GET access.

### Breaking Changes

- Shared read-only mode now requires absolute OCI config, key, and security-token paths; relative and tilde-style paths fail before authentication.
- `auto` selects session-token auth only when `security_token_file` is declared directly in the selected profile; a token inherited from `[DEFAULT]` now selects API-key auth. An explicitly selected session-token profile must declare its own token file, and an invalid declared token fails closed instead of falling back to API-key auth.
- OKE and delegation authentication reject simultaneous token-file and inline-token inputs. OKE no longer gives the inline token precedence.

### Changed

- Use `oracle-mcp-common` for OCI credential resolution, retaining IoT's existing eight authentication modes and deprecated `OCI_IOT_*` aliases. Canonical `OCI_MCP_*` settings take precedence, and conflicting inline/path delegation or OKE token inputs now fail closed.
- Use published `oracle-mcp-common` 0.1.x for local development and installed distributions, compatible with FastMCP 3.4.10.
- Document current and legacy IoT domain group types, the active digital-twin restriction on IoT domain deletion, and the compatible additive minor-model upgrade workflow. Model downgrades are unsupported.

### Added

- Add an explicitly selected offline HTTP fixture with five synthetic tools, bearer caller authentication, session-bound handles and loopback Host/Origin checks. Existing stdio and OCI tool paths remain unchanged.

- Add disconnected target-binding and credential-generation contracts for a future shared runtime, with offline fixtures; no HTTP activation, credential reader or OCI provider is included.

- Add read-only Flow Runtime tools for one bounded list page, full SDK runtime metadata, and the complete SDK-decoded flow document with its own ETag. Return explicit success/error envelopes and selected response metadata; document sensitive output and managed-editor evidence boundaries.

### Security

- Require PyJWT 2.15.1 or newer and urllib3 2.8.0 or newer to address published security advisories. The PyJWT shared-options advisory has no patched release listed; upgrading does not establish that it is resolved.

## 1.0.3

### Security

- Updated locked multidict to 6.9.1; updated locked AnyIO to 4.15.1; updated locked `PyJWT` to 2.15.1 and `urllib3` to 2.8.0; updated `cryptography` to 50.0.2 to prevent PKCS#7 EnvelopedData decryption from exposing a Bleichenbacher oracle through distinguishable errors and timing (CVE-2026-69247).

## 1.0.2

### Changed

- Excluded development artifacts, local configuration, and container build files from source-distribution packages.

## 1.0.1

### Changed

- Updated dependency locks for FastMCP 3.4.5, OCI SDK 2.182.1, and refreshed authentication-related transitive packages.
