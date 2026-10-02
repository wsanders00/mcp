# Changelog

## Unreleased

### Security

- Require PyJWT 2.15.1 or newer and urllib3 2.8.0 or newer to address published security advisories. The PyJWT shared-options advisory has no patched release listed; upgrading does not establish that it is resolved.
- Updated `cryptography` to 50.0.1 to prevent PKCS#7 EnvelopedData decryption from exposing a Bleichenbacher oracle through distinguishable errors and timing (CVE-2026-69247).

## 1.0.2

### Changed

- Excluded development artifacts, local configuration, and container build files from source-distribution packages.

## 1.0.1

### Changed

- Updated dependency locks for FastMCP 3.4.5, OCI SDK 2.182.1, and refreshed authentication-related transitive packages.
