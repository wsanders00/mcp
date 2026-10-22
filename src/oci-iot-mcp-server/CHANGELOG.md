# Changelog

## Unreleased

### Fixed

- Resolve friendly domain names/short IDs and twin names across SDK pages instead of claiming absence or uniqueness from the first page. Lookup requests 100 rows per page, bounded by 100 pages or 10,000 returned rows; incomplete or repeated-token scans fail with `incomplete_lookup` and OCID retry guidance. Additional list calls add latency. Ambiguity may return early with only the first two distinct matching candidates; public list-tool shapes are unchanged.

### Security

- Updated locked multidict to 6.9.1; updated locked AnyIO to 4.15.1; updated locked `PyJWT` to 2.15.1 and `urllib3` to 2.8.0; updated `cryptography` to 50.0.1 to prevent PKCS#7 EnvelopedData decryption from exposing a Bleichenbacher oracle through distinguishable errors and timing (CVE-2026-69247).

## 1.0.2

### Changed

- Excluded development artifacts, local configuration, and container build files from source-distribution packages.

## 1.0.1

### Changed

- Updated dependency locks for FastMCP 3.4.5, OCI SDK 2.182.1, and refreshed authentication-related transitive packages.
