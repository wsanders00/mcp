# OCI IoT Platform MCP Server

## Overview

This server provides MCP tools for interacting with the Oracle Cloud Infrastructure (OCI) IoT service.

## Running the server

```sh
uv run oracle.oci-iot-mcp-server
```

## Tools

| Tool Name | Description |
| --- | --- |
| get_digital_twin_adapter | Retrieves a specific digital twin adapter by its identifier |
| get_digital_twin_instance | Retrieves a specific digital twin instance by its identifier |
| get_digital_twin_instance_content | Retrieves the content of a specific digital twin instance by its identifier |
| get_digital_twin_model | Retrieves a specific digital twin model by its identifier |
| get_digital_twin_model_spec | Retrieves the specification of a specific digital twin model by its identifier |
| create_digital_twin_model | Creates a new digital twin model in a specified IoT domain |
| create_digital_twin_adapter | Creates a new digital twin adapter in a specified IoT domain |
| create_digital_twin_instance | Creates a new digital twin instance in a specified IoT domain |
| create_digital_twin_relationship | Creates a new digital twin relationship in a specified IoT domain |
| get_digital_twin_relationship | Retrieves a specific digital twin relationship by its identifier |
| delete_digital_twin_adapter | Deletes a specific digital twin adapter by its identifier |
| delete_digital_twin_instance | Deletes a specific digital twin instance by its identifier |
| delete_digital_twin_model | Deletes a specific digital twin model by its identifier |
| delete_digital_twin_relationship | Deletes a specific digital twin relationship by its identifier |
| update_digital_twin_adapter | Updates a specific digital twin adapter by its identifier |
| update_digital_twin_instance | Updates a specific digital twin instance by its identifier |
| update_digital_twin_model | Updates a specific digital twin model by its identifier |
| update_digital_twin_relationship | Updates a specific digital twin relationship by its identifier |
| create_iot_domain | Creates a new IoT domain in a specified IoT domain group |
| create_iot_domain_group | Creates a new IoT domain group in a specified compartment |
| change_iot_domain_compartment | Moves a specific IoT domain to a different compartment |
| change_iot_domain_data_retention_period | Changes the data retention period configuration for a specific IoT domain |
| change_iot_domain_group_compartment | Moves a specific IoT domain group to a different compartment |
| configure_iot_domain_data_access | Configures data access for a specific IoT domain |
| configure_iot_domain_group_data_access | Configures data access for a specific IoT domain group |
| update_iot_domain | Updates a specific IoT domain by its identifier |
| update_iot_domain_group | Updates a specific IoT domain group by its identifier |
| delete_iot_domain | Deletes a specific IoT domain by its identifier |
| delete_iot_domain_group | Deletes a specific IoT domain group by its identifier |
| invoke_raw_command | Invokes a raw command on a specific digital twin instance |
| get_iot_domain | Retrieves a specific IoT domain by its identifier |
| get_iot_domain_group | Retrieves a specific IoT domain group by its identifier |
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
| list_compartments | Lists all OCI compartments that the current user has access to |
| health_check | Health check endpoint for the OCI IoT MCP server |

## Configuration

The server uses the OCI configuration profile specified by the `OCI_CONFIG_PROFILE` environment variable. If not set, it defaults to "DEFAULT".

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
