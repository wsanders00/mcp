"""
Copyright (c) 2025, Oracle and/or its affiliates.
Licensed under the Universal Permissive License v1.0 as shown at
https://oss.oracle.com/licenses/upl.
"""

import logging
from typing import Annotated

from fastmcp import FastMCP
from oci.iot.models import IotDomainGroupCollection, IotDomainGroupSummary, IotDomainSummary, DigitalTwinModelSummary, DigitalTwinAdapterSummary, DigitalTwinInstanceSummary, DigitalTwinRelationshipSummary

from . import __project__, __version__
from .client import get_iot_client

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create FastMCP instance
mcp = FastMCP(name=__project__)

def _normalize_items(data):
    """Normalize OCI list response data into a list of items."""
    if hasattr(data, "items"):
        return data.items
    if isinstance(data, (list, tuple)):
        return list(data)
    if data is None:
        return []
    return [data]

@mcp.tool(
    description="Retrieves a specific digital twin adapter by its identifier."
)
def get_digital_twin_adapter(
    digital_twin_adapter_id: Annotated[str, "The digital twin adapter identifier"]
):
    """Get a specific digital twin adapter by ID.
    
    Additional kwargs that can be passed to the OCI client:
    - opc_request_id: str - Unique identifier for the request
    - retry_strategy: RetryStrategy - Custom retry strategy for the request
    """
    try:
        iot_client = get_iot_client()
        digital_twin_adapter = iot_client.get_digital_twin_adapter(digital_twin_adapter_id=digital_twin_adapter_id)
        # Convert to pydantic model for validation and structured output
        from .models import DigitalTwinAdapterModel
        return DigitalTwinAdapterModel.model_validate(digital_twin_adapter.data).model_dump()
    except Exception as e:
        logger.error(f"Error getting digital twin adapter {digital_twin_adapter_id}: {e}")
        raise

@mcp.tool(
    description="Retrieves a specific digital twin instance by its identifier."
)
def get_digital_twin_instance(
    digital_twin_instance_id: Annotated[str, "The digital twin instance identifier"]
    ):
    """Get a specific digital twin instance by ID.
    
    Additional kwargs that can be passed to the OCI client:
    - opc_request_id: str - Unique identifier for the request
    - retry_strategy: RetryStrategy - Custom retry strategy for the request
    """
    try:
        iot_client = get_iot_client()
        digital_twin_instance = iot_client.get_digital_twin_instance(digital_twin_instance_id=digital_twin_instance_id)#, **kwargs)
        # Convert to pydantic model for validation and structured output
        from .models import DigitalTwinInstanceModel
        return DigitalTwinInstanceModel.model_validate(digital_twin_instance.data).model_dump()
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
        # For content, return as-is since it's a string
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
    """Get a specific digital twin model by ID.
    
    Additional kwargs that can be passed to the OCI client:
    - opc_request_id: str - Unique identifier for the request
    - retry_strategy: RetryStrategy - Custom retry strategy for the request
    """
    try:
        iot_client = get_iot_client()
        digital_twin_model = iot_client.get_digital_twin_model(digital_twin_model_id=digital_twin_model_id)#, **kwargs)
        # Convert OCI SDK object to pydantic model with explicit field mapping
        from .models import DigitalTwinModelModel
        return DigitalTwinModelModel.from_oci_model(digital_twin_model.data).model_dump()
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
        # For spec, return as-is since it's a string
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
        digital_twin_relationship = iot_client.get_digital_twin_relationship(digital_twin_relationship_id=digital_twin_relationship_id)#, **kwargs)
        # Convert to pydantic model for validation and structured output
        from .models import DigitalTwinRelationshipModel
        return DigitalTwinRelationshipModel.model_validate(digital_twin_relationship.data).model_dump()
    except Exception as e:
        logger.error(f"Error getting digital twin relationship {digital_twin_relationship_id}: {e}")
        raise

@mcp.tool(
    description="Retrieves a specific IoT domain by its identifier."
)
def get_iot_domain(
    iot_domain_id: Annotated[str, "The IoT domain identifier"] #,
#    **kwargs
):
    """Get a specific IoT domain by ID."""
    try:
        iot_client = get_iot_client()
        iot_domain = iot_client.get_iot_domain(iot_domain_id=iot_domain_id)#, **kwargs)
        # Convert to pydantic model for validation and structured output
        from .models import IoTDomainModel
        return IoTDomainModel.model_validate(iot_domain.data).model_dump()
    except Exception as e:
        logger.error(f"Error getting IoT domain {iot_domain_id}: {e}")
        raise

@mcp.tool(
    description="Retrieves a specific IoT domain group by its identifier."
)
def get_iot_domain_group(
    iot_domain_group_id: Annotated[str, "The IoT domain group identifier"] #,
#    **kwargs
):
    """Get a specific IoT domain group by ID."""
    try:
        iot_client = get_iot_client()
        iot_domain_group = iot_client.get_iot_domain_group(iot_domain_group_id=iot_domain_group_id)#, **kwargs)
        # Convert to pydantic model for validation and structured output
        from .models import IoTDomainGroupModel
        return IoTDomainGroupModel.model_validate(iot_domain_group.data).model_dump()
    except Exception as e:
        logger.error(f"Error getting IoT domain group {iot_domain_group_id}: {e}")
        raise

@mcp.tool(
    description="Retrieves a specific work request by its identifier."
)
def get_work_request(
    work_request_id: Annotated[str, "The work request identifier"] #,
#    **kwargs
):
    """Get a specific work request by ID."""
    try:
        iot_client = get_iot_client()
        work_request = iot_client.get_work_request(work_request_id=work_request_id)#, **kwargs)
        # Convert to pydantic model for validation and structured output
        from .models import WorkRequestModel
        return WorkRequestModel.model_validate(work_request.data).model_dump()
    except Exception as e:
        logger.error(f"Error getting work request {work_request_id}: {e}")
        raise

@mcp.tool(
    description="Lists digital twin adapters in a specified IoT domain."
)
def list_digital_twin_adapters(
    iot_domain_id: Annotated[str, "The IoT domain identifier"] #,
#    **kwargs
):
    """List digital twin adapters in a specified IoT domain.
    
    Additional kwargs that can be passed to the OCI client:
    - opc_request_id: str - Unique identifier for the request
    - retry_strategy: RetryStrategy - Custom retry strategy for the request
    - page: str - Page token for pagination
    - page_size: int - Number of items per page
    """
    try:
        iot_client = get_iot_client()
        digital_twin_adapters = iot_client.list_digital_twin_adapters(iot_domain_id=iot_domain_id)#, **kwargs)
        # Convert OCI SDK summary objects to pydantic models with explicit field mapping
        from .models import DigitalTwinAdapterModel
        adapters = _normalize_items(digital_twin_adapters.data)
        return [DigitalTwinAdapterModel.from_oci_model(adapter).model_dump() for adapter in adapters]
    except Exception as e:
        logger.error(f"Error listing digital twin adapters for domain {iot_domain_id}: {e}")
        raise

@mcp.tool(
    description="Lists digital twin models in a specified IoT domain."
)
def list_digital_twin_models(
    iot_domain_id: Annotated[str, "The IoT domain identifier"] #,
#    **kwargs
):
    """List digital twin models in a specified IoT domain.
    
    Additional kwargs that can be passed to the OCI client:
    - opc_request_id: str - Unique identifier for the request
    - retry_strategy: RetryStrategy - Custom retry strategy for the request
    - page: str - Page token for pagination
    - page_size: int - Number of items per page
    """
    try:
        iot_client = get_iot_client()
        digital_twin_models = iot_client.list_digital_twin_models(iot_domain_id=iot_domain_id)#, **kwargs)
        # Convert OCI SDK summary objects to pydantic models with explicit field mapping
        from .models import DigitalTwinModelSummaryModel
        models = _normalize_items(digital_twin_models.data)
        return [DigitalTwinModelSummaryModel.from_oci_model(model).model_dump() for model in models]
    except Exception as e:
        logger.error(f"Error listing digital twin models for domain {iot_domain_id}: {e}")
        raise

@mcp.tool(
    description="Lists digital twin instances in a specified IoT domain."
)
def list_digital_twin_instances(
    iot_domain_id: Annotated[str, "The IoT domain identifier"],
    limit: Annotated[int, "The limit of results"] = 1000 #,
#    **kwargs
):
    """List digital twin instances in a specified IoT domain.
    
    Additional kwargs that can be passed to the OCI client:
    - opc_request_id: str - Unique identifier for the request
    - retry_strategy: RetryStrategy - Custom retry strategy for the request
    - page: str - Page token for pagination
    - page_size: int - Number of items per page
    """
    try:
        iot_client = get_iot_client()
        digital_twin_instances = iot_client.list_digital_twin_instances(iot_domain_id=iot_domain_id, limit=limit)#, **kwargs)
        # Convert OCI SDK summary objects to pydantic models with explicit field mapping
        from .models import DigitalTwinInstanceModel
        instances = _normalize_items(digital_twin_instances.data)
        return [DigitalTwinInstanceModel.from_oci_model(instance).model_dump() for instance in instances]
    except Exception as e:
        logger.error(f"Error listing digital twin instances for domain {iot_domain_id}: {e}")
        raise

@mcp.tool(
    description="Lists digital twin relationships in a specified IoT domain."
)
def list_digital_twin_relationships(
    iot_domain_id: Annotated[str, "The IoT domain identifier"] #,
#    **kwargs
):
    """List digital twin relationships in a specified IoT domain.
    
    Additional kwargs that can be passed to the OCI client:
    - opc_request_id: str - Unique identifier for the request
    - retry_strategy: RetryStrategy - Custom retry strategy for the request
    - page: str - Page token for pagination
    - page_size: int - Number of items per page
    """
    try:
        iot_client = get_iot_client()
        digital_twin_relationships = iot_client.list_digital_twin_relationships(iot_domain_id=iot_domain_id)#, **kwargs)
        # Convert OCI SDK summary objects to pydantic models with explicit field mapping
        from .models import DigitalTwinRelationshipModel
        relationships = _normalize_items(digital_twin_relationships.data)
        return [DigitalTwinRelationshipModel.from_oci_model(relationship).model_dump() for relationship in relationships]
    except Exception as e:
        logger.error(f"Error listing digital twin relationships for domain {iot_domain_id}: {e}")
        raise

@mcp.tool(
    description="Lists IoT domain groups in a specified compartment."
)
def list_iot_domain_groups(
    compartment_id: Annotated[str, "Compartment containing IoT Domain Groups"] #,
#    **kwargs
):
    """List IoT domain groups in a specified compartment.
    
    Additional kwargs that can be passed to the OCI client:
    - opc_request_id: str - Unique identifier for the request
    - retry_strategy: RetryStrategy - Custom retry strategy for the request
    - page: str - Page token for pagination
    - page_size: int - Number of items per page
    """
    try:
        iot_client = get_iot_client()
        domain_groups = iot_client.list_iot_domain_groups(compartment_id=compartment_id)#, **kwargs)
        # Convert OCI SDK summary objects to pydantic models with explicit field mapping
        from .models import IoTDomainGroupModel
        groups = _normalize_items(domain_groups.data)
        return [IoTDomainGroupModel.from_oci_model(domain_group).model_dump() for domain_group in groups]
    except Exception as e:
        logger.error(f"Error listing IoT domain groups for compartment {compartment_id}: {e}")
        raise

@mcp.tool(
    description="Lists IoT domains in a specified compartment."
)
def list_iot_domains(
    compartment_id: Annotated[str, "Compartment containing IoT Domains"] #,
#    **kwargs
):
    """List IoT domains in a specified compartment.
    
    Additional kwargs that can be passed to the OCI client:
    - opc_request_id: str - Unique identifier for the request
    - retry_strategy: RetryStrategy - Custom retry strategy for the request
    - page: str - Page token for pagination
    - page_size: int - Number of items per page
    """
    try:
        iot_client = get_iot_client()
        domains = iot_client.list_iot_domains(compartment_id=compartment_id)#, **kwargs)
        # Convert OCI SDK summary objects to pydantic models with explicit field mapping
        from .models import IoTDomainModel
        domains_list = _normalize_items(domains.data)
        return [IoTDomainModel.from_oci_model(domain).model_dump() for domain in domains_list]
    except Exception as e:
        logger.error(f"Error listing IoT domains for compartment {compartment_id}: {e}")
        raise

@mcp.tool(
    description="Lists errors for a specific work request."
)
def list_work_request_errors(
    work_request_id: Annotated[str, "The work request identifier"]#,
#    **kwargs
):
    """List errors for a specific work request.
    
    Additional kwargs that can be passed to the OCI client:
    - opc_request_id: str - Unique identifier for the request
    - retry_strategy: RetryStrategy - Custom retry strategy for the request
    - page: str - Page token for pagination
    - page_size: int - Number of items per page
    """
    try:
        iot_client = get_iot_client()
        work_request_errors = iot_client.list_work_request_errors(work_request_id=work_request_id)#, **kwargs)
        # Convert OCI SDK error objects to pydantic models with explicit field mapping
        from .models import ErrorModel
        errors = _normalize_items(work_request_errors.data)
        return [ErrorModel.from_oci_model(error).model_dump() for error in errors]
    except Exception as e:
        logger.error(f"Error listing work request errors for {work_request_id}: {e}")
        raise

@mcp.tool(
    description="Lists logs for a specific work request."
)
def list_work_request_logs(
    work_request_id: Annotated[str, "The work request identifier"]#,
    #**kwargs
):
    """List logs for a specific work request.
    
    Additional kwargs that can be passed to the OCI client:
    - opc_request_id: str - Unique identifier for the request
    - retry_strategy: RetryStrategy - Custom retry strategy for the request
    - page: str - Page token for pagination
    - page_size: int - Number of items per page
    """
    try:
        iot_client = get_iot_client()
        work_request_logs = iot_client.list_work_request_logs(work_request_id=work_request_id) #, **kwargs)
        # Convert OCI SDK log objects to pydantic models with explicit field mapping
        from .models import LogModel
        logs = _normalize_items(work_request_logs.data)
        return [LogModel.from_oci_model(log).model_dump() for log in logs]
    except Exception as e:
        logger.error(f"Error listing work request logs for {work_request_id}: {e}")
        raise

@mcp.tool(
    description="Lists work requests in a specified compartment."
)
def list_work_requests(
    compartment_id: Annotated[str, "The compartment ID containing the work requests"] #,
#    **kwargs
):
    """List work requests in a specified compartment.
    
    Additional kwargs that can be passed to the OCI client:
    - opc_request_id: str - Unique identifier for the request
    - retry_strategy: RetryStrategy - Custom retry strategy for the request
    - page: str - Page token for pagination
    - page_size: int - Number of items per page
    """
    try:
        iot_client = get_iot_client()
        work_requests = iot_client.list_work_requests(compartment_id=compartment_id) #, **kwargs)
        # Convert OCI SDK work request objects to pydantic models with explicit field mapping
        from .models import WorkRequestModel
        requests_list = _normalize_items(work_requests.data)
        return [WorkRequestModel.from_oci_model(work_request).model_dump() for work_request in requests_list]
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
