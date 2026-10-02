# Changelog

## Unreleased

### Breaking Changes

- `auto` selects session-token auth only when `security_token_file` is declared directly in the selected profile; a token inherited from `[DEFAULT]` now selects API-key auth. An explicitly selected session-token profile must declare its own token file, and an invalid declared token fails closed instead of falling back to API-key auth.
- OKE and delegation authentication reject simultaneous token-file and inline-token inputs. OKE no longer gives the inline token precedence.

### Changed

- Use `oracle-mcp-common` for OCI credential resolution, retaining IoT's existing eight authentication modes and deprecated `OCI_IOT_*` aliases. Canonical `OCI_MCP_*` settings take precedence, and conflicting inline/path delegation or OKE token inputs now fail closed.
- Document current and legacy IoT domain group types, the active digital-twin restriction on IoT domain deletion, and the compatible additive minor-model upgrade workflow. Model downgrades are unsupported.

### Added

- Add read-only Flow Runtime tools for one bounded list page, full SDK runtime metadata, and the complete SDK-decoded flow document with its own ETag. Return explicit success/error envelopes and selected response metadata; document sensitive output and managed-editor evidence boundaries.

### Security

- Require PyJWT 2.15.1 or newer and urllib3 2.8.0 or newer to address published security advisories. The PyJWT shared-options advisory has no patched release listed; upgrading does not establish that it is resolved.
- Updated `cryptography` to 50.0.1 to prevent PKCS#7 EnvelopedData decryption from exposing a Bleichenbacher oracle through distinguishable errors and timing (CVE-2026-69247).

## 1.0.2

### Changed

- Excluded development artifacts, local configuration, and container build files from source-distribution packages.

## 1.0.1

### Changed

- Updated dependency locks for FastMCP 3.4.5, OCI SDK 2.182.1, and refreshed authentication-related transitive packages.
