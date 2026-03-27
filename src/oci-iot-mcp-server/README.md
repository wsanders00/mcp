# OCI IoT Platform MCP Server

## Overview

This server provides tools for interacting with Oracle Cloud Infrastructure (OCI) IoT Platform service.

## Running the server

```sh
uv run oracle.oci-iot-mcp-server
```

## Tools

| Tool Name | Description |
| --- | --- |
| get_digital_twin_adapter | Retrieves a specific digital twin adapter by its identifier |
| get_digital_twin_adapter_full | Returns the full mapped digital twin adapter payload for debugging and migration workflows |
| get_digital_twin_instance | Retrieves a specific digital twin instance by its identifier |
| get_digital_twin_instance_content | Retrieves the content of a specific digital twin instance by its identifier |
| get_digital_twin_model | Retrieves a specific digital twin model by its identifier |
| get_digital_twin_model_spec | Retrieves the specification of a specific digital twin model by its identifier |
| get_digital_twin_relationship | Retrieves a specific digital twin relationship by its identifier |
| derive_domain_context | Derives normalized IoT domain context for ORDS and operator workflows |
| get_data_api_token | Mints and returns an IoT Data API bearer token plus the resolved domain context |
| get_raw_command_by_request_id | Fetches the raw command detail record for an ORDS request ID |
| get_iot_domain | Retrieves a specific IoT domain by its identifier |
| get_iot_domain_group | Retrieves a specific IoT domain group by its identifier |
| invoke_raw_command_and_wait | Invokes a raw command on a digital twin instance and waits for a terminal data-plane result |
| list_recent_raw_commands_for_twin | Lists recent raw command records for a digital twin instance |
| list_recent_rejected_data_for_twin | Lists recent rejected ingest records for a digital twin instance |
| get_work_request | Retrieves a specific work request by its identifier |
| list_digital_twin_adapters | Lists digital twin adapters in a specified IoT domain |
| list_digital_twin_models | Lists digital twin models in a specified IoT domain |
| list_digital_twin_instances | Lists digital twin instances in a specified IoT domain |
| list_digital_twin_relationships | Lists digital twin relationships in a specified IoT domain |
| list_iot_domain_groups | Lists IoT domain groups in a specified compartment |
| list_iot_domains | Lists IoT domains in a specified compartment |
| list_work_request_errors | Lists errors for a specific work request |
| list_work_request_logs | Lists logs for a specific work request |
| list_work_requests | Lists work requests in a specified compartment |
| wait_for_twin_update | Waits for a twin snapshot update after a given timestamp |

## Configuration

The server uses the OCI configuration profile specified by the `OCI_CONFIG_PROFILE` environment variable. If not set, it defaults to "DEFAULT".

## Friendly Identifier Rules

- `digital_twin_instance_id` and `iot_domain_id` work directly.
- Twin display-name lookup requires an IoT domain selector.
- Domain display-name lookup and `domain_short_id` lookup require `compartment_id`.
- Ambiguous friendly matches fail with `ambiguous_identifier` and list candidate identifiers for retry.

## ORDS Credentials And Token Behavior

- Required environment variables:
  - `OCI_IOT_ORDS_CLIENT_ID`
  - `OCI_IOT_ORDS_CLIENT_SECRET`
  - `OCI_IOT_ORDS_USERNAME`
  - `OCI_IOT_ORDS_PASSWORD`
- `get_data_api_token` returns a live bearer token and expiry metadata to the MCP caller.
- Treat the returned bearer token as a secret and do not log, persist, or echo it beyond the intended caller.
- Tokens are minted in-memory per call, are not cached across tool invocations, and must never be logged.

## Security

⚠️ **NOTE**: All actions are performed with the permissions of the configured OCI CLI profile. We advise least-privilege IAM setup, secure credential management, safe network practices, secure logging, and warn against exposing secrets.

## Third-Party APIs

Developers choosing to distribute a binary implementation of this project are responsible for obtaining and providing all required licenses and copyright notices for the third-party code used in order to ensure compliance with their respective open source licenses.

## Disclaimer

Users are responsible for their local environment and credential safety. Different language model selections may yield different results and performance.

## License

Copyright (c) 2025 Oracle and/or its affiliates.
 
Released under the Universal Permissive License v1.0 as shown at  
<https://oss.oracle.com/licenses/upl/>.
