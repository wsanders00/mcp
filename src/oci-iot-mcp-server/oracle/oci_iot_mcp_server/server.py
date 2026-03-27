"""
Copyright (c) 2025, Oracle and/or its affiliates.
Licensed under the Universal Permissive License v1.0 as shown at
https://oss.oracle.com/licenses/upl.
"""

import logging
from typing import Annotated

from fastmcp import FastMCP

from . import __project__, __version__
from .control_plane import (
    get_digital_twin_adapter_record,
    get_digital_twin_instance_content_record,
    get_digital_twin_instance_record,
    get_digital_twin_model_record,
    get_digital_twin_model_spec_record,
    get_digital_twin_relationship_record,
    get_iot_domain_group_record,
    get_iot_domain_record,
    get_work_request_record,
    list_digital_twin_adapters_records,
    list_digital_twin_instances_records,
    list_digital_twin_models_records,
    list_digital_twin_relationships_records,
    list_iot_domain_groups_records,
    list_iot_domains_records,
    list_work_request_errors_records,
    list_work_request_logs_records,
    list_work_requests_records,
)

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create FastMCP instance
mcp = FastMCP(name=__project__)


def tool(*, description: str):
    def decorator(func):
        mcp.tool(description=description)(func)
        return func

    return decorator


def _delegate(message: str, func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception as e:
        logger.error(f"{message}: {e}")
        raise


@tool(
    description="Retrieves a specific digital twin adapter by its identifier."
)
def get_digital_twin_adapter(
    digital_twin_adapter_id: Annotated[str, "The digital twin adapter identifier"]
):
    return _delegate(
        f"Error getting digital twin adapter {digital_twin_adapter_id}",
        get_digital_twin_adapter_record,
        digital_twin_adapter_id,
    )

@tool(
    description="Retrieves a specific digital twin instance by its identifier."
)
def get_digital_twin_instance(
    digital_twin_instance_id: Annotated[str, "The digital twin instance identifier"]
):
    return _delegate(
        f"Error getting digital twin instance {digital_twin_instance_id}",
        get_digital_twin_instance_record,
        digital_twin_instance_id,
    )

@tool(
    description="Retrieves the content of a specific digital twin instance by its identifier."
)
def get_digital_twin_instance_content(
    digital_twin_instance_id: Annotated[str, "The digital twin instance identifier"]
):
    return _delegate(
        f"Error getting digital twin instance content {digital_twin_instance_id}",
        get_digital_twin_instance_content_record,
        digital_twin_instance_id,
    )

@tool(
    description="Retrieves a specific digital twin model by its identifier."
)
def get_digital_twin_model(
    digital_twin_model_id: Annotated[str, "The digital twin model identifier"]
):
    return _delegate(
        f"Error getting digital twin model {digital_twin_model_id}",
        get_digital_twin_model_record,
        digital_twin_model_id,
    )

@tool(
    description="Retrieves the specification of a specific digital twin model by its identifier."
)
def get_digital_twin_model_spec(
    digital_twin_model_id: Annotated[str, "The digital twin model identifier"]
):
    return _delegate(
        f"Error getting digital twin model spec {digital_twin_model_id}",
        get_digital_twin_model_spec_record,
        digital_twin_model_id,
    )

@tool(
    description="Retrieves a specific digital twin relationship by its identifier."
)
def get_digital_twin_relationship(
    digital_twin_relationship_id: Annotated[str, "The digital twin relationship identifier"]
):
    return _delegate(
        f"Error getting digital twin relationship {digital_twin_relationship_id}",
        get_digital_twin_relationship_record,
        digital_twin_relationship_id,
    )

@tool(
    description="Retrieves a specific IoT domain by its identifier."
)
def get_iot_domain(
    iot_domain_id: Annotated[str, "The IoT domain identifier"]
):
    return _delegate(f"Error getting IoT domain {iot_domain_id}", get_iot_domain_record, iot_domain_id)

@tool(
    description="Retrieves a specific IoT domain group by its identifier."
)
def get_iot_domain_group(
    iot_domain_group_id: Annotated[str, "The IoT domain group identifier"]
):
    return _delegate(
        f"Error getting IoT domain group {iot_domain_group_id}",
        get_iot_domain_group_record,
        iot_domain_group_id,
    )

@tool(
    description="Retrieves a specific work request by its identifier."
)
def get_work_request(
    work_request_id: Annotated[str, "The work request identifier"]
):
    return _delegate(
        f"Error getting work request {work_request_id}",
        get_work_request_record,
        work_request_id,
    )

@tool(
    description="Lists digital twin adapters in a specified IoT domain."
)
def list_digital_twin_adapters(
    iot_domain_id: Annotated[str, "The IoT domain identifier"]
):
    return _delegate(
        f"Error listing digital twin adapters for domain {iot_domain_id}",
        list_digital_twin_adapters_records,
        iot_domain_id=iot_domain_id,
    )

@tool(
    description="Lists digital twin models in a specified IoT domain."
)
def list_digital_twin_models(
    iot_domain_id: Annotated[str, "The IoT domain identifier"]
):
    return _delegate(
        f"Error listing digital twin models for domain {iot_domain_id}",
        list_digital_twin_models_records,
        iot_domain_id=iot_domain_id,
    )

@tool(
    description="Lists digital twin instances in a specified IoT domain."
)
def list_digital_twin_instances(
    iot_domain_id: Annotated[str, "The IoT domain identifier"],
    limit: Annotated[int, "The limit of results"] = 1000
):
    return _delegate(
        f"Error listing digital twin instances for domain {iot_domain_id}",
        list_digital_twin_instances_records,
        iot_domain_id=iot_domain_id,
        limit=limit,
    )

@tool(
    description="Lists digital twin relationships in a specified IoT domain."
)
def list_digital_twin_relationships(
    iot_domain_id: Annotated[str, "The IoT domain identifier"]
):
    return _delegate(
        f"Error listing digital twin relationships for domain {iot_domain_id}",
        list_digital_twin_relationships_records,
        iot_domain_id=iot_domain_id,
    )

@tool(
    description="Lists IoT domain groups in a specified compartment."
)
def list_iot_domain_groups(
    compartment_id: Annotated[str, "Compartment containing IoT Domain Groups"]
):
    return _delegate(
        f"Error listing IoT domain groups for compartment {compartment_id}",
        list_iot_domain_groups_records,
        compartment_id=compartment_id,
    )

@tool(
    description="Lists IoT domains in a specified compartment."
)
def list_iot_domains(
    compartment_id: Annotated[str, "Compartment containing IoT Domains"]
):
    return _delegate(
        f"Error listing IoT domains for compartment {compartment_id}",
        list_iot_domains_records,
        compartment_id=compartment_id,
    )

@tool(
    description="Lists errors for a specific work request."
)
def list_work_request_errors(
    work_request_id: Annotated[str, "The work request identifier"]
):
    return _delegate(
        f"Error listing work request errors for {work_request_id}",
        list_work_request_errors_records,
        work_request_id=work_request_id,
    )

@tool(
    description="Lists logs for a specific work request."
)
def list_work_request_logs(
    work_request_id: Annotated[str, "The work request identifier"]
):
    return _delegate(
        f"Error listing work request logs for {work_request_id}",
        list_work_request_logs_records,
        work_request_id=work_request_id,
    )

@tool(
    description="Lists work requests in a specified compartment."
)
def list_work_requests(
    compartment_id: Annotated[str, "The compartment ID containing the work requests"]
):
    return _delegate(
        f"Error listing work requests for compartment {compartment_id}",
        list_work_requests_records,
        compartment_id=compartment_id,
    )

@tool(
    description="Health check endpoint for the OCI IoT MCP server."
)
def health_check():
    """Health check endpoint that verifies the server is running."""
    return {
        "status": "healthy",
        "service": "oci-iot-mcp-server",
        "version": __version__
    }

def main():
    """Main function to run the MCP server."""
    try:
        mcp.run()
    except Exception as e:
        logger.error(f"Error running MCP server: {e}")
        raise

if __name__ == "__main__":
    main()
