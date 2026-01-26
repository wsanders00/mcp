"""
Copyright (c) 2025, Oracle and/or its affiliates.
Licensed under the Universal Permissive License v1.0 as shown at
https://oss.oracle.com/licenses/upl.
"""

import os
import logging
from logging import Logger
from typing import Annotated, Optional
from functools import lru_cache

import oci
from fastmcp import FastMCP
from oci.iot.models import IotDomainGroupCollection, IotDomainGroupSummary, IotDomainSummary, DigitalTwinModelSummary, DigitalTwinAdapterSummary, DigitalTwinInstanceSummary, DigitalTwinRelationshipSummary
from oci.exceptions import ServiceError, ConfigFileNotFound, InvalidConfig

from . import __project__, __version__

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create FastMCP instance
mcp = FastMCP(name=__project__)

# Global client cache
_iot_client = None

def get_iot_client( profile_name: Annotated[Optional[str], "Stored/Authenticated OCI Profile"] = "INTWIM-IAD-IOT"):
    """
    Get or create IoT client with caching.
    
    Args:
        profile_name: OCI configuration profile name. If None, uses environment variable or default.
        
    Returns:
        IotClient instance
        
    Raises:
        ConfigFileNotFound: If OCI config file is not found
        InvalidConfig: If OCI configuration is invalid
        ServiceError: If there's an issue connecting to OCI
    """
    global _iot_client
    
    # Use environment variable if no profile name provided
    if profile_name is None:
        profile_name = os.getenv("OCI_CONFIG_PROFILE", "DEFAULT")
    
    # If we already have a client for this profile, return it
    if _iot_client is not None:
        return _iot_client
    
    try:
        logger.info(f"Creating IoT client for profile: {profile_name}")
        config = oci.config.from_file(profile_name=profile_name)
        user_agent_name = __project__.split("oracle.", 1)[1].split("-server", 1)[0]
        config["additional_user_agent"] = f"{user_agent_name}/{__version__}"

        private_key = oci.signer.load_private_key_from_file(config["key_file"])
        token_file = config["security_token_file"]
        token = None
        with open(token_file, "r") as f:
            token = f.read()
        signer = oci.auth.signers.SecurityTokenSigner(token, private_key)
        _iot_client = oci.iot.IotClient(config, signer=signer)
        logger.info("IoT client created successfully")
        return _iot_client
    except ConfigFileNotFound as e:
        logger.error(f"OCI config file not found: {e}")
        raise
    except InvalidConfig as e:
        logger.error(f"Invalid OCI configuration: {e}")
        raise
    except Exception as e:
        logger.error(f"Error creating IoT client: {e}")
        raise

@mcp.tool(
    description="Retrieves a specific digital twin adapter by its identifier."
)
def get_digital_twin_adapter(
    digital_twin_adapter_id: Annotated[str, "The digital twin adapter identifier"]
):
    """Get a specific digital twin adapter by ID."""
    try:
        iot_client = get_iot_client()
        digital_twin_adapter = iot_client.get_digital_twin_adapter(digital_twin_adapter_id=digital_twin_adapter_id)
        return digital_twin_adapter.data
    except Exception as e:
        logger.error(f"Error getting digital twin adapter {digital_twin_adapter_id}: {e}")
        raise

@mcp.tool(
    description="Retrieves a specific digital twin instance by its identifier."
)
def get_digital_twin_instance(
    digital_twin_instance_id: Annotated[str, "The digital twin instance identifier"]
):
    """Get a specific digital twin instance by ID."""
    try:
        iot_client = get_iot_client()
        digital_twin_instance = iot_client.get_digital_twin_instance(digital_twin_instance_id=digital_twin_instance_id)
        return digital_twin_instance.data
    except Exception as e:
        logger.error(f"Error getting digital twin instance {digital_twin_instance_id}: {e}")
        raise

@mcp.tool(
    description="Retrieves the content of a specific digital twin instance by its identifier."
)
def get_digital_twin_instance_content(
    digital_twin_instance_id: Annotated[str, "The digital twin instance identifier"]
):
    """Get content of a specific digital twin instance by ID."""
    try:
        iot_client = get_iot_client()
        digital_twin_instance_content = iot_client.get_digital_twin_instance_content(digital_twin_instance_id=digital_twin_instance_id)
        return digital_twin_instance_content.data
    except Exception as e:
        logger.error(f"Error getting digital twin instance content {digital_twin_instance_id}: {e}")
        raise

@mcp.tool(
    description="Retrieves a specific digital twin model by its identifier."
)
def get_digital_twin_model(
    digital_twin_model_id: Annotated[str, "The digital twin model identifier"]
):
    """Get a specific digital twin model by ID."""
    try:
        iot_client = get_iot_client()
        digital_twin_model = iot_client.get_digital_twin_model(digital_twin_model_id=digital_twin_model_id)
        return digital_twin_model.data
    except Exception as e:
        logger.error(f"Error getting digital twin model {digital_twin_model_id}: {e}")
        raise

@mcp.tool(
    description="Retrieves the specification of a specific digital twin model by its identifier."
)
def get_digital_twin_model_spec(
    digital_twin_model_id: Annotated[str, "The digital twin model identifier"]
):
    """Get specification of a specific digital twin model by ID."""
    try:
        iot_client = get_iot_client()
        digital_twin_model_spec = iot_client.get_digital_twin_model_spec(digital_twin_model_id=digital_twin_model_id)
        return digital_twin_model_spec.data
    except Exception as e:
        logger.error(f"Error getting digital twin model spec {digital_twin_model_id}: {e}")
        raise

@mcp.tool(
    description="Retrieves a specific digital twin relationship by its identifier."
)
def get_digital_twin_relationship(
    digital_twin_relationship_id: Annotated[str, "The digital twin relationship identifier"]
):
    """Get a specific digital twin relationship by ID."""
    try:
        iot_client = get_iot_client()
        digital_twin_relationship = iot_client.get_digital_twin_relationship(digital_twin_relationship_id=digital_twin_relationship_id)
        return digital_twin_relationship.data
    except Exception as e:
        logger.error(f"Error getting digital twin relationship {digital_twin_relationship_id}: {e}")
        raise

@mcp.tool(
    description="Retrieves a specific IoT domain by its identifier."
)
def get_iot_domain(
    iot_domain_id: Annotated[str, "The IoT domain identifier"]
):
    """Get a specific IoT domain by ID."""
    try:
        iot_client = get_iot_client()
        iot_domain = iot_client.get_iot_domain(iot_domain_id=iot_domain_id)
        return iot_domain.data
    except Exception as e:
        logger.error(f"Error getting IoT domain {iot_domain_id}: {e}")
        raise

@mcp.tool(
    description="Retrieves a specific IoT domain group by its identifier."
)
def get_iot_domain_group(
    iot_domain_group_id: Annotated[str, "The IoT domain group identifier"]
):
    """Get a specific IoT domain group by ID."""
    try:
        iot_client = get_iot_client()
        iot_domain_group = iot_client.get_iot_domain_group(iot_domain_group_id=iot_domain_group_id)
        return iot_domain_group.data
    except Exception as e:
        logger.error(f"Error getting IoT domain group {iot_domain_group_id}: {e}")
        raise

@mcp.tool(
    description="Retrieves a specific work request by its identifier."
)
def get_work_request(
    work_request_id: Annotated[str, "The work request identifier"]
):
    """Get a specific work request by ID."""
    try:
        iot_client = get_iot_client()
        work_request = iot_client.get_work_request(work_request_id=work_request_id)
        return work_request.data
    except Exception as e:
        logger.error(f"Error getting work request {work_request_id}: {e}")
        raise

@mcp.tool(
    description="Lists digital twin adapters in a specified IoT domain."
)
def list_digital_twin_adapters(
    iot_domain_id: Annotated[str, "The IoT domain identifier"]
):
    """List digital twin adapters in a specified IoT domain."""
    try:
        iot_client = get_iot_client()
        digital_twin_adapters = iot_client.list_digital_twin_adapters(iot_domain_id=iot_domain_id)
        return digital_twin_adapters.data
    except Exception as e:
        logger.error(f"Error listing digital twin adapters for domain {iot_domain_id}: {e}")
        raise

@mcp.tool(
    description="Lists digital twin models in a specified IoT domain."
)
def list_digital_twin_models(
    iot_domain_id: Annotated[str, "The IoT domain identifier"]
):
    """List digital twin models in a specified IoT domain."""
    try:
        iot_client = get_iot_client()
        digital_twin_models = iot_client.list_digital_twin_models(iot_domain_id=iot_domain_id)
        return digital_twin_models.data
    except Exception as e:
        logger.error(f"Error listing digital twin models for domain {iot_domain_id}: {e}")
        raise

@mcp.tool(
    description="Lists digital twin instances in a specified IoT domain."
)
def list_digital_twin_instances(
    iot_domain_id: Annotated[str, "The IoT domain identifier"]
):
    """List digital twin instances in a specified IoT domain."""
    try:
        iot_client = get_iot_client()
        digital_twin_instances = iot_client.list_digital_twin_instances(iot_domain_id=iot_domain_id)
        return digital_twin_instances.data
    except Exception as e:
        logger.error(f"Error listing digital twin instances for domain {iot_domain_id}: {e}")
        raise

@mcp.tool(
    description="Lists digital twin relationships in a specified IoT domain."
)
def list_digital_twin_relationships(
    iot_domain_id: Annotated[str, "The IoT domain identifier"]
):
    """List digital twin relationships in a specified IoT domain."""
    try:
        iot_client = get_iot_client()
        digital_twin_relationships = iot_client.list_digital_twin_relationships(iot_domain_id=iot_domain_id)
        return digital_twin_relationships.data
    except Exception as e:
        logger.error(f"Error listing digital twin relationships for domain {iot_domain_id}: {e}")
        raise

@mcp.tool(
    description="Lists IoT domain groups in a specified compartment."
)
def list_iot_domain_groups(
    compartment_id: Annotated[str, "Compartment containing IoT Domain Groups"]
):
    """List IoT domain groups in a specified compartment."""
    try:
        iot_client = get_iot_client()
        domain_groups = iot_client.list_iot_domain_groups(compartment_id=compartment_id)
        return domain_groups.data
    except Exception as e:
        logger.error(f"Error listing IoT domain groups for compartment {compartment_id}: {e}")
        raise

@mcp.tool(
    description="Lists IoT domains in a specified compartment."
)
def list_iot_domains(
    compartment_id: Annotated[str, "Compartment containing IoT Domains"]
):
    """List IoT domains in a specified compartment."""
    try:
        iot_client = get_iot_client()
        domains = iot_client.list_iot_domains(compartment_id=compartment_id)
        return domains.data
    except Exception as e:
        logger.error(f"Error listing IoT domains for compartment {compartment_id}: {e}")
        raise

@mcp.tool(
    description="Lists errors for a specific work request."
)
def list_work_request_errors(
    work_request_id: Annotated[str, "The work request identifier"]
):
    """List errors for a specific work request."""
    try:
        iot_client = get_iot_client()
        work_request_errors = iot_client.list_work_request_errors(work_request_id=work_request_id)
        return work_request_errors.data
    except Exception as e:
        logger.error(f"Error listing work request errors for {work_request_id}: {e}")
        raise

@mcp.tool(
    description="Lists logs for a specific work request."
)
def list_work_request_logs(
    work_request_id: Annotated[str, "The work request identifier"]
):
    """List logs for a specific work request."""
    try:
        iot_client = get_iot_client()
        work_request_logs = iot_client.list_work_request_logs(work_request_id=work_request_id)
        return work_request_logs.data
    except Exception as e:
        logger.error(f"Error listing work request logs for {work_request_id}: {e}")
        raise

@mcp.tool(
    description="Lists work requests in a specified compartment."
)
def list_work_requests(
    compartment_id: Annotated[str, "The compartment ID containing the work requests"]
):
    """List work requests in a specified compartment."""
    try:
        iot_client = get_iot_client()
        work_requests = iot_client.list_work_requests(compartment_id=compartment_id)
        return work_requests.data
    except Exception as e:
        logger.error(f"Error listing work requests for compartment {compartment_id}: {e}")
        raise

@mcp.tool(
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
