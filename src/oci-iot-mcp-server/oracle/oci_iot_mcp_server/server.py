"""
Copyright (c) 2025, Oracle and/or its affiliates.
Licensed under the Universal Permissive License v1.0 as shown at
https://oss.oracle.com/licenses/upl.
"""

import json
import os
import logging
from typing import Annotated, Any, Optional

import oci
from fastmcp import FastMCP
from oci.exceptions import ConfigFileNotFound, InvalidConfig

from . import __project__, __version__

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create FastMCP instance
mcp = FastMCP(name=__project__)

# Global client cache
_iot_client = None
_identity_client = None
_tenancy_id = None

def _normalize_items(data):
    """Normalize OCI list response data into a list of items."""
    if hasattr(data, "items"):
        return data.items
    if isinstance(data, (list, tuple)):
        return list(data)
    if data is None:
        return []
    return [data]


def _parse_json_input(value, field_name: str):
    """Parse a JSON string input while leaving native Python values unchanged."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON for {field_name}: {e}")
            raise ValueError(f"Invalid JSON for {field_name}: {e}") from e
    return value

def get_iot_client( profile_name: Annotated[Optional[str], "Stored/Authenticated OCI Profile"] = None):
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


def get_identity_client(profile_name: Annotated[Optional[str], "Stored/Authenticated OCI Profile"] = None):
    """
    Get or create OCI Identity client with caching.

    Args:
        profile_name: OCI configuration profile name. If None, uses environment variable or default.

    Returns:
        Tuple of (IdentityClient instance, tenancy OCID)
    """
    global _identity_client, _tenancy_id

    if profile_name is None:
        profile_name = os.getenv("OCI_CONFIG_PROFILE", "DEFAULT")

    if _identity_client is not None and _tenancy_id is not None:
        return _identity_client, _tenancy_id

    try:
        logger.info(f"Creating Identity client for profile: {profile_name}")
        config = oci.config.from_file(profile_name=profile_name)
        user_agent_name = __project__.split("oracle.", 1)[1].split("-server", 1)[0]
        config["additional_user_agent"] = f"{user_agent_name}/{__version__}"

        private_key = oci.signer.load_private_key_from_file(config["key_file"])
        token_file = config["security_token_file"]
        with open(token_file, "r") as f:
            token = f.read()
        signer = oci.auth.signers.SecurityTokenSigner(token, private_key)

        _identity_client = oci.identity.IdentityClient(config, signer=signer)
        _tenancy_id = config["tenancy"]
        logger.info("Identity client created successfully")
        return _identity_client, _tenancy_id
    except ConfigFileNotFound as e:
        logger.error(f"OCI config file not found: {e}")
        raise
    except InvalidConfig as e:
        logger.error(f"Invalid OCI configuration: {e}")
        raise
    except Exception as e:
        logger.error(f"Error creating Identity client: {e}")
        raise

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
    description="Creates a new digital twin model in a specified IoT domain."
)
def create_digital_twin_model(
    iot_domain_id: Annotated[str, "The IoT domain identifier"],
    display_name: Annotated[str, "A user-friendly display name for the digital twin model"],
    spec: Annotated[dict[str, Any] | str, "The DTDL v3 digital twin model specification as a JSON object or JSON string"],
    description: Annotated[Optional[str], "A short description of the digital twin model"] = None,
    opc_retry_token: Annotated[Optional[str], "A retry token for safely retrying the request"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the request"] = None,
):
    """Create a new digital twin model.

    The specification must be valid DTDL v3 JSON content.
    """
    try:
        iot_client = get_iot_client()

        specification = _parse_json_input(spec, "spec")

        create_digital_twin_model_details = oci.iot.models.CreateDigitalTwinModelDetails(
            iot_domain_id=iot_domain_id,
            display_name=display_name,
            description=description,
            specification=specification,
        )

        kwargs = {
            "create_digital_twin_model_details": create_digital_twin_model_details,
        }
        if opc_retry_token is not None:
            kwargs["opc_retry_token"] = opc_retry_token
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id

        digital_twin_model = iot_client.create_digital_twin_model(**kwargs)
        from .models import DigitalTwinModelModel
        return DigitalTwinModelModel.from_oci_model(digital_twin_model.data).model_dump()
    except Exception as e:
        logger.error(f"Error creating digital twin model in domain {iot_domain_id}: {e}")
        raise

@mcp.tool(
    description="Creates a new digital twin adapter in a specified IoT domain."
)
def create_digital_twin_adapter(
    iot_domain_id: Annotated[str, "The IoT domain identifier"],
    display_name: Annotated[Optional[str], "A user-friendly display name for the digital twin adapter"] = None,
    description: Annotated[Optional[str], "A short description of the digital twin adapter"] = None,
    digital_twin_model_id: Annotated[Optional[str], "The digital twin model OCID associated with the adapter"] = None,
    digital_twin_model_spec_uri: Annotated[Optional[str], "The URI of the digital twin model specification"] = None,
    inbound_envelope: Annotated[Optional[dict[str, Any] | str], "The adapter inbound envelope as a JSON object or JSON string"] = None,
    inbound_routes: Annotated[Optional[list[dict[str, Any]] | str], "The adapter inbound routes as a JSON array or JSON string"] = None,
    freeform_tags: Annotated[Optional[dict[str, str] | str], "Free-form tags as an object or JSON string"] = None,
    defined_tags: Annotated[Optional[dict[str, dict[str, Any]] | str], "Defined tags as an object or JSON string"] = None,
    opc_retry_token: Annotated[Optional[str], "A retry token for safely retrying the request"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the request"] = None,
):
    """Create a new digital twin adapter."""
    try:
        iot_client = get_iot_client()

        create_digital_twin_adapter_details = oci.iot.models.CreateDigitalTwinAdapterDetails(
            iot_domain_id=iot_domain_id,
            display_name=display_name,
            description=description,
            digital_twin_model_id=digital_twin_model_id,
            digital_twin_model_spec_uri=digital_twin_model_spec_uri,
            inbound_envelope=_parse_json_input(inbound_envelope, "inbound_envelope"),
            inbound_routes=_parse_json_input(inbound_routes, "inbound_routes"),
            freeform_tags=_parse_json_input(freeform_tags, "freeform_tags"),
            defined_tags=_parse_json_input(defined_tags, "defined_tags"),
        )

        kwargs = {
            "create_digital_twin_adapter_details": create_digital_twin_adapter_details,
        }
        if opc_retry_token is not None:
            kwargs["opc_retry_token"] = opc_retry_token
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id

        digital_twin_adapter = iot_client.create_digital_twin_adapter(**kwargs)
        from .models import DigitalTwinAdapterModel
        return DigitalTwinAdapterModel.from_oci_model(digital_twin_adapter.data).model_dump()
    except Exception as e:
        logger.error(f"Error creating digital twin adapter in domain {iot_domain_id}: {e}")
        raise

@mcp.tool(
    description="Creates a new digital twin instance in a specified IoT domain."
)
def create_digital_twin_instance(
    iot_domain_id: Annotated[str, "The IoT domain identifier"],
    auth_id: Annotated[Optional[str], "The OCID of the authentication resource for the instance"] = None,
    external_key: Annotated[Optional[str], "A unique identifier for the physical entity represented by the twin"] = None,
    display_name: Annotated[Optional[str], "A user-friendly display name for the digital twin instance"] = None,
    description: Annotated[Optional[str], "A short description of the digital twin instance"] = None,
    digital_twin_adapter_id: Annotated[Optional[str], "The digital twin adapter OCID associated with the instance"] = None,
    digital_twin_model_id: Annotated[Optional[str], "The digital twin model OCID associated with the instance"] = None,
    digital_twin_model_spec_uri: Annotated[Optional[str], "The URI of the digital twin model specification"] = None,
    freeform_tags: Annotated[Optional[dict[str, str] | str], "Free-form tags as an object or JSON string"] = None,
    defined_tags: Annotated[Optional[dict[str, dict[str, Any]] | str], "Defined tags as an object or JSON string"] = None,
    opc_retry_token: Annotated[Optional[str], "A retry token for safely retrying the request"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the request"] = None,
):
    """Create a new digital twin instance."""
    try:
        iot_client = get_iot_client()

        create_digital_twin_instance_details = oci.iot.models.CreateDigitalTwinInstanceDetails(
            iot_domain_id=iot_domain_id,
            auth_id=auth_id,
            external_key=external_key,
            display_name=display_name,
            description=description,
            digital_twin_adapter_id=digital_twin_adapter_id,
            digital_twin_model_id=digital_twin_model_id,
            digital_twin_model_spec_uri=digital_twin_model_spec_uri,
            freeform_tags=_parse_json_input(freeform_tags, "freeform_tags"),
            defined_tags=_parse_json_input(defined_tags, "defined_tags"),
        )

        kwargs = {
            "create_digital_twin_instance_details": create_digital_twin_instance_details,
        }
        if opc_retry_token is not None:
            kwargs["opc_retry_token"] = opc_retry_token
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id

        digital_twin_instance = iot_client.create_digital_twin_instance(**kwargs)
        from .models import DigitalTwinInstanceModel
        return DigitalTwinInstanceModel.from_oci_model(digital_twin_instance.data).model_dump()
    except Exception as e:
        logger.error(f"Error creating digital twin instance in domain {iot_domain_id}: {e}")
        raise

@mcp.tool(
    description="Creates a new digital twin relationship in a specified IoT domain."
)
def create_digital_twin_relationship(
    iot_domain_id: Annotated[str, "The IoT domain identifier"],
    content_path: Annotated[str, "The relationship name from the source digital twin model"],
    source_digital_twin_instance_id: Annotated[str, "The source digital twin instance identifier"],
    target_digital_twin_instance_id: Annotated[str, "The target digital twin instance identifier"],
    display_name: Annotated[Optional[str], "A user-friendly display name for the digital twin relationship"] = None,
    description: Annotated[Optional[str], "A short description of the digital twin relationship"] = None,
    content: Annotated[Optional[dict[str, Any] | str], "The relationship property values as an object or JSON string"] = None,
    freeform_tags: Annotated[Optional[dict[str, str] | str], "Free-form tags as an object or JSON string"] = None,
    defined_tags: Annotated[Optional[dict[str, dict[str, Any]] | str], "Defined tags as an object or JSON string"] = None,
    opc_retry_token: Annotated[Optional[str], "A retry token for safely retrying the request"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the request"] = None,
):
    """Create a new digital twin relationship."""
    try:
        iot_client = get_iot_client()

        create_digital_twin_relationship_details = oci.iot.models.CreateDigitalTwinRelationshipDetails(
            iot_domain_id=iot_domain_id,
            content_path=content_path,
            source_digital_twin_instance_id=source_digital_twin_instance_id,
            target_digital_twin_instance_id=target_digital_twin_instance_id,
            display_name=display_name,
            description=description,
            content=_parse_json_input(content, "content"),
            freeform_tags=_parse_json_input(freeform_tags, "freeform_tags"),
            defined_tags=_parse_json_input(defined_tags, "defined_tags"),
        )

        kwargs = {
            "create_digital_twin_relationship_details": create_digital_twin_relationship_details,
        }
        if opc_retry_token is not None:
            kwargs["opc_retry_token"] = opc_retry_token
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id

        digital_twin_relationship = iot_client.create_digital_twin_relationship(**kwargs)
        from .models import DigitalTwinRelationshipModel
        return DigitalTwinRelationshipModel.from_oci_model(digital_twin_relationship.data).model_dump()
    except Exception as e:
        logger.error(f"Error creating digital twin relationship in domain {iot_domain_id}: {e}")
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
    description="Lists all OCI compartments that the current user has access to."
)
def list_compartments(
    include_root: Annotated[bool, "Include the root tenancy compartment"] = True
):
    """List all accessible OCI compartments for the authenticated user."""
    try:
        identity_client, tenancy_id = get_identity_client()
        from .models import CompartmentModel

        compartments = []

        if include_root:
            try:
                root_compartment = identity_client.get_compartment(compartment_id=tenancy_id).data
                compartments.append(root_compartment)
            except Exception as root_error:
                logger.warning(f"Unable to load root tenancy compartment {tenancy_id}: {root_error}")

        list_result = oci.pagination.list_call_get_all_results(
            identity_client.list_compartments,
            compartment_id=tenancy_id,
            compartment_id_in_subtree=True,
            access_level="ACCESSIBLE",
        )
        compartments.extend(_normalize_items(list_result.data))

        # De-duplicate by compartment OCID (root may also appear in list results in some tenancies).
        deduped = {}
        for compartment in compartments:
            compartment_id = getattr(compartment, "id", None)
            if compartment_id:
                deduped[compartment_id] = compartment

        return [CompartmentModel.from_oci_model(compartment).model_dump() for compartment in deduped.values()]
    except Exception as e:
        logger.error(f"Error listing compartments: {e}")
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
