"""
Copyright (c) 2025, Oracle and/or its affiliates.
Licensed under the Universal Permissive License v1.0 as shown at
https://oss.oracle.com/licenses/upl.
"""

import json
import os
import logging
from typing import Annotated, Any, Optional
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

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

def _response_to_dict(response):
    """Convert an OCI response object into a serializable dictionary."""
    headers = dict(getattr(response, "headers", {}) or {})
    request_id = getattr(response, "request_id", None) or headers.get("opc-request-id")

    return {
        "status": getattr(response, "status", None),
        "request_id": request_id,
        "headers": headers,
        "data": getattr(response, "data", None),
    }


def _result_payload(value):
    """Wrap list-style tool results in a structured payload expected by tests/clients."""
    return {"result": value}

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

def _get_oci_config(profile_name: Optional[str] = None):
    """Load OCI configuration for the selected profile."""
    if profile_name is None:
        profile_name = os.getenv("OCI_CONFIG_PROFILE", "DEFAULT")
    return oci.config.from_file(profile_name=profile_name)


def _get_iot_data_api_access_token(access_token: Optional[str] = None):
    """Resolve the IoT Data API access token from an argument or environment variable."""
    token = access_token or os.getenv("OCI_IOT_DATA_API_ACCESS_TOKEN")
    if not token:
        raise ValueError(
            "IoT Data API access token is required. Pass access_token or set OCI_IOT_DATA_API_ACCESS_TOKEN."
        )
    return token


def _normalize_query_params(query_params: Optional[dict[str, Any] | str]):
    """Normalize query parameters for Data API requests."""
    params = _parse_json_input(query_params, "query_params")
    if params is None:
        return {}
    if not isinstance(params, dict):
        raise ValueError("query_params must be a dictionary or JSON object string")

    normalized = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            normalized[key] = str(value).lower()
        elif isinstance(value, (dict, list)):
            normalized[key] = json.dumps(value)
        else:
            normalized[key] = value
    return normalized


def _build_iot_data_api_url(
    iot_domain_group_short_id: str,
    iot_domain_short_id: str,
    resource_path: str,
    region: Optional[str] = None,
):
    """Build an Oracle IoT Data API URL."""
    if region is None:
        config = _get_oci_config()
        region = config.get("region")

    base_url = (
        f"https://{iot_domain_group_short_id}.data.iot.{region}.oci.oraclecloud.com"
        f"/ords/{iot_domain_short_id}"
    )
    return f"{base_url}{resource_path}"


def _call_iot_data_api(
    resource_path: str,
    iot_domain_group_short_id: str,
    iot_domain_short_id: str,
    query_params: Optional[dict[str, Any] | str] = None,
    region: Optional[str] = None,
    access_token: Optional[str] = None,
    opc_request_id: Optional[str] = None,
):
    """Call the Oracle IoT Data API using a bearer token."""
    token = _get_iot_data_api_access_token(access_token)
    url = _build_iot_data_api_url(
        iot_domain_group_short_id=iot_domain_group_short_id,
        iot_domain_short_id=iot_domain_short_id,
        resource_path=resource_path,
        region=region,
    )

    normalized_query_params = _normalize_query_params(query_params)
    if normalized_query_params:
        url = f"{url}?{urlencode(normalized_query_params, doseq=True)}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    if opc_request_id is not None:
        headers["opc-request-id"] = opc_request_id

    request = Request(url, headers=headers, method="GET")

    try:
        with urlopen(request) as response:
            payload = response.read().decode("utf-8")
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return json.loads(payload)
            return payload
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        logger.error(f"IoT Data API request failed for {url}: {e.code} {error_body}")
        raise RuntimeError(f"IoT Data API request failed with status {e.code}: {error_body}") from e


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
        return DigitalTwinAdapterModel.from_oci_model(digital_twin_adapter.data).model_dump()
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
        return DigitalTwinInstanceModel.from_oci_model(digital_twin_instance.data).model_dump()
    except Exception as e:
        logger.error(f"Error getting digital twin instance {digital_twin_instance_id}: {e}")
        raise

@mcp.tool(
    description="Retrieves the content of a specific digital twin instance by its identifier."
)
def get_digital_twin_instance_content(
    digital_twin_instance_id: Annotated[str, "The digital twin instance identifier"],
    should_include_metadata: Annotated[
        bool,
        "If true, includes digital twin instance metadata in the response payload",
    ] = False,
    opc_request_id: Annotated[
        Optional[str],
        "A unique Oracle-assigned identifier for the request",
    ] = None,
):
    """Get content of a specific digital twin instance by ID."""
    try:
        iot_client = get_iot_client()

        kwargs = {
            "digital_twin_instance_id": digital_twin_instance_id,
            "should_include_metadata": should_include_metadata,
        }
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id

        digital_twin_instance_content = iot_client.get_digital_twin_instance_content(**kwargs)
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
            spec=specification,
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
        return DigitalTwinRelationshipModel.from_oci_model(digital_twin_relationship.data).model_dump()
    except Exception as e:
        logger.error(f"Error getting digital twin relationship {digital_twin_relationship_id}: {e}")
        raise

@mcp.tool(
    description="Deletes a specific digital twin adapter by its identifier."
)
def delete_digital_twin_adapter(
    digital_twin_adapter_id: Annotated[str, "The digital twin adapter identifier"],
    if_match: Annotated[
        Optional[str],
        "An etag value for optimistic concurrency control when deleting the digital twin adapter",
    ] = None,
    opc_request_id: Annotated[
        Optional[str],
        "A unique Oracle-assigned identifier for the delete digital twin adapter request",
    ] = None,
):
    """Delete a specific digital twin adapter by ID."""
    try:
        iot_client = get_iot_client()

        kwargs = {"digital_twin_adapter_id": digital_twin_adapter_id}
        if if_match is not None:
            kwargs["if_match"] = if_match
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id

        response = iot_client.delete_digital_twin_adapter(**kwargs)
        return _response_to_dict(response)
    except Exception as e:
        logger.error(f"Error deleting digital twin adapter {digital_twin_adapter_id}: {e}")
        raise

@mcp.tool(
    description="Deletes a specific digital twin instance by its identifier."
)
def delete_digital_twin_instance(
    digital_twin_instance_id: Annotated[str, "The digital twin instance identifier"],
    if_match: Annotated[
        Optional[str],
        "An etag value for optimistic concurrency control when deleting the digital twin instance",
    ] = None,
    opc_request_id: Annotated[
        Optional[str],
        "A unique Oracle-assigned identifier for the delete digital twin instance request",
    ] = None,
):
    """Delete a specific digital twin instance by ID."""
    try:
        iot_client = get_iot_client()

        kwargs = {"digital_twin_instance_id": digital_twin_instance_id}
        if if_match is not None:
            kwargs["if_match"] = if_match
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id

        response = iot_client.delete_digital_twin_instance(**kwargs)
        return _response_to_dict(response)
    except Exception as e:
        logger.error(f"Error deleting digital twin instance {digital_twin_instance_id}: {e}")
        raise

@mcp.tool(
    description="Deletes a specific digital twin model by its identifier."
)
def delete_digital_twin_model(
    digital_twin_model_id: Annotated[str, "The digital twin model identifier"],
    if_match: Annotated[
        Optional[str],
        "An etag value for optimistic concurrency control when deleting the digital twin model",
    ] = None,
    opc_request_id: Annotated[
        Optional[str],
        "A unique Oracle-assigned identifier for the delete digital twin model request",
    ] = None,
):
    """Delete a specific digital twin model by ID."""
    try:
        iot_client = get_iot_client()

        kwargs = {"digital_twin_model_id": digital_twin_model_id}
        if if_match is not None:
            kwargs["if_match"] = if_match
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id

        response = iot_client.delete_digital_twin_model(**kwargs)
        return _response_to_dict(response)
    except Exception as e:
        logger.error(f"Error deleting digital twin model {digital_twin_model_id}: {e}")
        raise

@mcp.tool(
    description="Deletes a specific digital twin relationship by its identifier."
)
def delete_digital_twin_relationship(
    digital_twin_relationship_id: Annotated[str, "The digital twin relationship identifier"],
    if_match: Annotated[
        Optional[str],
        "An etag value for optimistic concurrency control when deleting the digital twin relationship",
    ] = None,
    opc_request_id: Annotated[
        Optional[str],
        "A unique Oracle-assigned identifier for the delete digital twin relationship request",
    ] = None,
):
    """Delete a specific digital twin relationship by ID."""
    try:
        iot_client = get_iot_client()

        kwargs = {"digital_twin_relationship_id": digital_twin_relationship_id}
        if if_match is not None:
            kwargs["if_match"] = if_match
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id

        response = iot_client.delete_digital_twin_relationship(**kwargs)
        return _response_to_dict(response)
    except Exception as e:
        logger.error(f"Error deleting digital twin relationship {digital_twin_relationship_id}: {e}")
        raise

def _build_invoke_raw_command_details(
    request_data_format: str,
    request_endpoint: str,
    response_endpoint: Optional[str] = None,
    request_duration: Optional[str] = None,
    response_duration: Optional[str] = None,
    request_data_content_type: Optional[str] = None,
    request_data: Optional[dict[str, Any] | str] = None,
):
    """Build the correct OCI invoke raw command details model for the requested data format."""
    normalized_format = request_data_format.upper()
    common_kwargs = {
        "request_duration": request_duration,
        "response_duration": response_duration,
        "request_endpoint": request_endpoint,
        "response_endpoint": response_endpoint,
        "request_data_content_type": request_data_content_type,
    }

    if normalized_format == "JSON":
        return oci.iot.models.InvokeRawJsonCommandDetails(
            request_data=_parse_json_input(request_data, "request_data"),
            **common_kwargs,
        )
    if normalized_format == "TEXT":
        return oci.iot.models.InvokeRawTextCommandDetails(
            request_data=request_data,
            **common_kwargs,
        )
    if normalized_format == "BINARY":
        return oci.iot.models.InvokeRawBinaryCommandDetails(
            request_data=request_data,
            **common_kwargs,
        )

    raise ValueError("request_data_format must be one of: JSON, TEXT, BINARY")

@mcp.tool(
    description="Updates a specific digital twin adapter by its identifier."
)
def update_digital_twin_adapter(
    digital_twin_adapter_id: Annotated[str, "The digital twin adapter identifier"],
    display_name: Annotated[Optional[str], "A user-friendly display name for the digital twin adapter"] = None,
    description: Annotated[Optional[str], "A short description of the digital twin adapter"] = None,
    inbound_envelope: Annotated[Optional[dict[str, Any] | str], "The adapter inbound envelope as a JSON object or JSON string"] = None,
    inbound_routes: Annotated[Optional[list[dict[str, Any]] | str], "The adapter inbound routes as a JSON array or JSON string"] = None,
    freeform_tags: Annotated[Optional[dict[str, str] | str], "Free-form tags as an object or JSON string"] = None,
    defined_tags: Annotated[Optional[dict[str, dict[str, Any]] | str], "Defined tags as an object or JSON string"] = None,
    if_match: Annotated[Optional[str], "An etag value for optimistic concurrency control when updating the digital twin adapter"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the update digital twin adapter request"] = None,
):
    """Update a specific digital twin adapter by ID."""
    try:
        iot_client = get_iot_client()

        update_digital_twin_adapter_details = oci.iot.models.UpdateDigitalTwinAdapterDetails(
            display_name=display_name,
            description=description,
            inbound_envelope=_parse_json_input(inbound_envelope, "inbound_envelope"),
            inbound_routes=_parse_json_input(inbound_routes, "inbound_routes"),
            freeform_tags=_parse_json_input(freeform_tags, "freeform_tags"),
            defined_tags=_parse_json_input(defined_tags, "defined_tags"),
        )

        kwargs = {
            "digital_twin_adapter_id": digital_twin_adapter_id,
            "update_digital_twin_adapter_details": update_digital_twin_adapter_details,
        }
        if if_match is not None:
            kwargs["if_match"] = if_match
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id

        digital_twin_adapter = iot_client.update_digital_twin_adapter(**kwargs)
        from .models import DigitalTwinAdapterModel
        return DigitalTwinAdapterModel.from_oci_model(digital_twin_adapter.data).model_dump()
    except Exception as e:
        logger.error(f"Error updating digital twin adapter {digital_twin_adapter_id}: {e}")
        raise

@mcp.tool(
    description="Updates a specific digital twin instance by its identifier."
)
def update_digital_twin_instance(
    digital_twin_instance_id: Annotated[str, "The digital twin instance identifier"],
    auth_id: Annotated[Optional[str], "The OCID of the authentication resource for the instance"] = None,
    external_key: Annotated[Optional[str], "A unique identifier for the physical entity represented by the twin"] = None,
    display_name: Annotated[Optional[str], "A user-friendly display name for the digital twin instance"] = None,
    description: Annotated[Optional[str], "A short description of the digital twin instance"] = None,
    digital_twin_adapter_id: Annotated[Optional[str], "The digital twin adapter OCID associated with the instance"] = None,
    digital_twin_model_id: Annotated[Optional[str], "The digital twin model OCID associated with the instance"] = None,
    digital_twin_model_spec_uri: Annotated[Optional[str], "The URI of the digital twin model specification"] = None,
    freeform_tags: Annotated[Optional[dict[str, str] | str], "Free-form tags as an object or JSON string"] = None,
    defined_tags: Annotated[Optional[dict[str, dict[str, Any]] | str], "Defined tags as an object or JSON string"] = None,
    if_match: Annotated[Optional[str], "An etag value for optimistic concurrency control when updating the digital twin instance"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the update digital twin instance request"] = None,
):
    """Update a specific digital twin instance by ID."""
    try:
        iot_client = get_iot_client()

        update_digital_twin_instance_details = oci.iot.models.UpdateDigitalTwinInstanceDetails(
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
            "digital_twin_instance_id": digital_twin_instance_id,
            "update_digital_twin_instance_details": update_digital_twin_instance_details,
        }
        if if_match is not None:
            kwargs["if_match"] = if_match
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id

        digital_twin_instance = iot_client.update_digital_twin_instance(**kwargs)
        from .models import DigitalTwinInstanceModel
        return DigitalTwinInstanceModel.from_oci_model(digital_twin_instance.data).model_dump()
    except Exception as e:
        logger.error(f"Error updating digital twin instance {digital_twin_instance_id}: {e}")
        raise

@mcp.tool(
    description="Updates a specific digital twin model by its identifier."
)
def update_digital_twin_model(
    digital_twin_model_id: Annotated[str, "The digital twin model identifier"],
    display_name: Annotated[Optional[str], "A user-friendly display name for the digital twin model"] = None,
    description: Annotated[Optional[str], "A short description of the digital twin model"] = None,
    freeform_tags: Annotated[Optional[dict[str, str] | str], "Free-form tags as an object or JSON string"] = None,
    defined_tags: Annotated[Optional[dict[str, dict[str, Any]] | str], "Defined tags as an object or JSON string"] = None,
    if_match: Annotated[Optional[str], "An etag value for optimistic concurrency control when updating the digital twin model"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the update digital twin model request"] = None,
):
    """Update a specific digital twin model by ID."""
    try:
        iot_client = get_iot_client()

        update_digital_twin_model_details = oci.iot.models.UpdateDigitalTwinModelDetails(
            display_name=display_name,
            description=description,
            freeform_tags=_parse_json_input(freeform_tags, "freeform_tags"),
            defined_tags=_parse_json_input(defined_tags, "defined_tags"),
        )

        kwargs = {
            "digital_twin_model_id": digital_twin_model_id,
            "update_digital_twin_model_details": update_digital_twin_model_details,
        }
        if if_match is not None:
            kwargs["if_match"] = if_match
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id

        digital_twin_model = iot_client.update_digital_twin_model(**kwargs)
        from .models import DigitalTwinModelModel
        return DigitalTwinModelModel.from_oci_model(digital_twin_model.data).model_dump()
    except Exception as e:
        logger.error(f"Error updating digital twin model {digital_twin_model_id}: {e}")
        raise

@mcp.tool(
    description="Updates a specific digital twin relationship by its identifier."
)
def update_digital_twin_relationship(
    digital_twin_relationship_id: Annotated[str, "The digital twin relationship identifier"],
    display_name: Annotated[Optional[str], "A user-friendly display name for the digital twin relationship"] = None,
    description: Annotated[Optional[str], "A short description of the digital twin relationship"] = None,
    content: Annotated[Optional[dict[str, Any] | str], "The relationship property values as an object or JSON string"] = None,
    freeform_tags: Annotated[Optional[dict[str, str] | str], "Free-form tags as an object or JSON string"] = None,
    defined_tags: Annotated[Optional[dict[str, dict[str, Any]] | str], "Defined tags as an object or JSON string"] = None,
    if_match: Annotated[Optional[str], "An etag value for optimistic concurrency control when updating the digital twin relationship"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the update digital twin relationship request"] = None,
):
    """Update a specific digital twin relationship by ID."""
    try:
        iot_client = get_iot_client()

        update_digital_twin_relationship_details = oci.iot.models.UpdateDigitalTwinRelationshipDetails(
            display_name=display_name,
            description=description,
            content=_parse_json_input(content, "content"),
            freeform_tags=_parse_json_input(freeform_tags, "freeform_tags"),
            defined_tags=_parse_json_input(defined_tags, "defined_tags"),
        )

        kwargs = {
            "digital_twin_relationship_id": digital_twin_relationship_id,
            "update_digital_twin_relationship_details": update_digital_twin_relationship_details,
        }
        if if_match is not None:
            kwargs["if_match"] = if_match
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id

        digital_twin_relationship = iot_client.update_digital_twin_relationship(**kwargs)
        from .models import DigitalTwinRelationshipModel
        return DigitalTwinRelationshipModel.from_oci_model(digital_twin_relationship.data).model_dump()
    except Exception as e:
        logger.error(f"Error updating digital twin relationship {digital_twin_relationship_id}: {e}")
        raise

@mcp.tool(
    description="Creates a new IoT domain in a specified IoT domain group."
)
def create_iot_domain(
    iot_domain_group_id: Annotated[str, "The IoT domain group identifier"],
    compartment_id: Annotated[str, "The compartment identifier where the IoT domain will be created"],
    display_name: Annotated[Optional[str], "A user-friendly display name for the IoT domain"] = None,
    description: Annotated[Optional[str], "A short description of the IoT domain"] = None,
    freeform_tags: Annotated[Optional[dict[str, str] | str], "Free-form tags as an object or JSON string"] = None,
    defined_tags: Annotated[Optional[dict[str, dict[str, Any]] | str], "Defined tags as an object or JSON string"] = None,
    opc_retry_token: Annotated[Optional[str], "A retry token for safely retrying the request"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the request"] = None,
):
    """Create a new IoT domain."""
    try:
        iot_client = get_iot_client()

        create_iot_domain_details = oci.iot.models.CreateIotDomainDetails(
            iot_domain_group_id=iot_domain_group_id,
            compartment_id=compartment_id,
            display_name=display_name,
            description=description,
            freeform_tags=_parse_json_input(freeform_tags, "freeform_tags"),
            defined_tags=_parse_json_input(defined_tags, "defined_tags"),
        )

        kwargs = {"create_iot_domain_details": create_iot_domain_details}
        if opc_retry_token is not None:
            kwargs["opc_retry_token"] = opc_retry_token
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id

        iot_domain = iot_client.create_iot_domain(**kwargs)
        from .models import IoTDomainModel
        return IoTDomainModel.from_oci_model(iot_domain.data).model_dump()
    except Exception as e:
        logger.error(f"Error creating IoT domain in group {iot_domain_group_id}: {e}")
        raise

@mcp.tool(
    description="Creates a new IoT domain group in a specified compartment."
)
def create_iot_domain_group(
    compartment_id: Annotated[str, "The compartment identifier where the IoT domain group will be created"],
    type: Annotated[Optional[str], "The IoT domain group type, such as STANDARD or LIGHTWEIGHT"] = None,
    display_name: Annotated[Optional[str], "A user-friendly display name for the IoT domain group"] = None,
    description: Annotated[Optional[str], "A short description of the IoT domain group"] = None,
    freeform_tags: Annotated[Optional[dict[str, str] | str], "Free-form tags as an object or JSON string"] = None,
    defined_tags: Annotated[Optional[dict[str, dict[str, Any]] | str], "Defined tags as an object or JSON string"] = None,
    opc_retry_token: Annotated[Optional[str], "A retry token for safely retrying the request"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the request"] = None,
):
    """Create a new IoT domain group."""
    try:
        iot_client = get_iot_client()

        create_iot_domain_group_details = oci.iot.models.CreateIotDomainGroupDetails(
            compartment_id=compartment_id,
            type=type,
            display_name=display_name,
            description=description,
            freeform_tags=_parse_json_input(freeform_tags, "freeform_tags"),
            defined_tags=_parse_json_input(defined_tags, "defined_tags"),
        )

        kwargs = {"create_iot_domain_group_details": create_iot_domain_group_details}
        if opc_retry_token is not None:
            kwargs["opc_retry_token"] = opc_retry_token
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id

        iot_domain_group = iot_client.create_iot_domain_group(**kwargs)
        from .models import IoTDomainGroupModel
        return IoTDomainGroupModel.from_oci_model(iot_domain_group.data).model_dump()
    except Exception as e:
        logger.error(f"Error creating IoT domain group in compartment {compartment_id}: {e}")
        raise

@mcp.tool(
    description="Moves a specific IoT domain to a different compartment."
)
def change_iot_domain_compartment(
    iot_domain_id: Annotated[str, "The IoT domain identifier"],
    compartment_id: Annotated[str, "The target compartment identifier for the IoT domain"],
    if_match: Annotated[Optional[str], "An etag value for optimistic concurrency control when moving the IoT domain"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the change IoT domain compartment request"] = None,
    opc_retry_token: Annotated[Optional[str], "A retry token for safely retrying the request"] = None,
):
    """Move a specific IoT domain to another compartment."""
    try:
        iot_client = get_iot_client()

        change_iot_domain_compartment_details = oci.iot.models.ChangeIotDomainCompartmentDetails(
            compartment_id=compartment_id,
        )

        kwargs = {
            "iot_domain_id": iot_domain_id,
            "change_iot_domain_compartment_details": change_iot_domain_compartment_details,
        }
        if if_match is not None:
            kwargs["if_match"] = if_match
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id
        if opc_retry_token is not None:
            kwargs["opc_retry_token"] = opc_retry_token

        response = iot_client.change_iot_domain_compartment(**kwargs)
        return _response_to_dict(response)
    except Exception as e:
        logger.error(f"Error changing IoT domain compartment for {iot_domain_id}: {e}")
        raise

@mcp.tool(
    description="Changes the data retention period configuration for a specific IoT domain."
)
def change_iot_domain_data_retention_period(
    iot_domain_id: Annotated[str, "The IoT domain identifier"],
    type: Annotated[str, "The retention data type, such as RAW_DATA, REJECTED_DATA, HISTORIZED_DATA, or RAW_COMMAND_DATA"],
    data_retention_period_in_days: Annotated[int, "The number of days to retain the selected data type"],
    if_match: Annotated[Optional[str], "An etag value for optimistic concurrency control when updating retention settings"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the data retention period change request"] = None,
    opc_retry_token: Annotated[Optional[str], "A retry token for safely retrying the request"] = None,
):
    """Change the data retention period for a specific IoT domain."""
    try:
        iot_client = get_iot_client()

        change_iot_domain_data_retention_period_details = oci.iot.models.ChangeIotDomainDataRetentionPeriodDetails(
            type=type,
            data_retention_period_in_days=data_retention_period_in_days,
        )

        kwargs = {
            "iot_domain_id": iot_domain_id,
            "change_iot_domain_data_retention_period_details": change_iot_domain_data_retention_period_details,
        }
        if if_match is not None:
            kwargs["if_match"] = if_match
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id
        if opc_retry_token is not None:
            kwargs["opc_retry_token"] = opc_retry_token

        response = iot_client.change_iot_domain_data_retention_period(**kwargs)
        return _response_to_dict(response)
    except Exception as e:
        logger.error(f"Error changing data retention period for IoT domain {iot_domain_id}: {e}")
        raise

@mcp.tool(
    description="Moves a specific IoT domain group to a different compartment."
)
def change_iot_domain_group_compartment(
    iot_domain_group_id: Annotated[str, "The IoT domain group identifier"],
    compartment_id: Annotated[str, "The target compartment identifier for the IoT domain group"],
    if_match: Annotated[Optional[str], "An etag value for optimistic concurrency control when moving the IoT domain group"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the change IoT domain group compartment request"] = None,
    opc_retry_token: Annotated[Optional[str], "A retry token for safely retrying the request"] = None,
):
    """Move a specific IoT domain group to another compartment."""
    try:
        iot_client = get_iot_client()

        change_iot_domain_group_compartment_details = oci.iot.models.ChangeIotDomainGroupCompartmentDetails(
            compartment_id=compartment_id,
        )

        kwargs = {
            "iot_domain_group_id": iot_domain_group_id,
            "change_iot_domain_group_compartment_details": change_iot_domain_group_compartment_details,
        }
        if if_match is not None:
            kwargs["if_match"] = if_match
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id
        if opc_retry_token is not None:
            kwargs["opc_retry_token"] = opc_retry_token

        response = iot_client.change_iot_domain_group_compartment(**kwargs)
        return _response_to_dict(response)
    except Exception as e:
        logger.error(f"Error changing IoT domain group compartment for {iot_domain_group_id}: {e}")
        raise

@mcp.tool(
    description="Configures data access for a specific IoT domain."
)
def configure_iot_domain_data_access(
    iot_domain_id: Annotated[str, "The IoT domain identifier"],
    type: Annotated[str, "The data access configuration type: DIRECT, ORDS, or APEX"],
    db_allow_listed_identity_group_names: Annotated[Optional[list[str] | str], "Allowed identity group names for DIRECT access as a list or JSON string"] = None,
    db_allowed_identity_domain_host: Annotated[Optional[str], "The allowed identity domain host for ORDS access"] = None,
    db_workspace_admin_initial_password: Annotated[Optional[str], "The initial workspace admin password for APEX access"] = None,
    if_match: Annotated[Optional[str], "An etag value for optimistic concurrency control when configuring IoT domain data access"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the configure IoT domain data access request"] = None,
    opc_retry_token: Annotated[Optional[str], "A retry token for safely retrying the request"] = None,
):
    """Configure data access for a specific IoT domain."""
    try:
        iot_client = get_iot_client()

        normalized_type = type.upper()
        if normalized_type == "DIRECT":
            configure_iot_domain_data_access_details = oci.iot.models.DirectDataAccessDetails(
                db_allow_listed_identity_group_names=_parse_json_input(
                    db_allow_listed_identity_group_names,
                    "db_allow_listed_identity_group_names",
                ),
            )
        elif normalized_type == "ORDS":
            configure_iot_domain_data_access_details = oci.iot.models.OrdsDataAccessDetails(
                db_allowed_identity_domain_host=db_allowed_identity_domain_host,
            )
        elif normalized_type == "APEX":
            configure_iot_domain_data_access_details = oci.iot.models.ApexDataAccessDetails(
                db_workspace_admin_initial_password=db_workspace_admin_initial_password,
            )
        else:
            raise ValueError("type must be one of: DIRECT, ORDS, APEX")

        kwargs = {
            "iot_domain_id": iot_domain_id,
            "configure_iot_domain_data_access_details": configure_iot_domain_data_access_details,
        }
        if if_match is not None:
            kwargs["if_match"] = if_match
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id
        if opc_retry_token is not None:
            kwargs["opc_retry_token"] = opc_retry_token

        response = iot_client.configure_iot_domain_data_access(**kwargs)
        return _response_to_dict(response)
    except Exception as e:
        logger.error(f"Error configuring IoT domain data access for {iot_domain_id}: {e}")
        raise

@mcp.tool(
    description="Configures data access for a specific IoT domain group."
)
def configure_iot_domain_group_data_access(
    iot_domain_group_id: Annotated[str, "The IoT domain group identifier"],
    db_allow_listed_vcn_ids: Annotated[list[str] | str, "Allowed VCN identifiers as a list or JSON string"],
    if_match: Annotated[Optional[str], "An etag value for optimistic concurrency control when configuring IoT domain group data access"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the configure IoT domain group data access request"] = None,
    opc_retry_token: Annotated[Optional[str], "A retry token for safely retrying the request"] = None,
):
    """Configure data access for a specific IoT domain group."""
    try:
        iot_client = get_iot_client()

        configure_iot_domain_group_data_access_details = oci.iot.models.ConfigureIotDomainGroupDataAccessDetails(
            db_allow_listed_vcn_ids=_parse_json_input(db_allow_listed_vcn_ids, "db_allow_listed_vcn_ids"),
        )

        kwargs = {
            "iot_domain_group_id": iot_domain_group_id,
            "configure_iot_domain_group_data_access_details": configure_iot_domain_group_data_access_details,
        }
        if if_match is not None:
            kwargs["if_match"] = if_match
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id
        if opc_retry_token is not None:
            kwargs["opc_retry_token"] = opc_retry_token

        response = iot_client.configure_iot_domain_group_data_access(**kwargs)
        return _response_to_dict(response)
    except Exception as e:
        logger.error(f"Error configuring IoT domain group data access for {iot_domain_group_id}: {e}")
        raise

@mcp.tool(
    description="Updates a specific IoT domain by its identifier."
)
def update_iot_domain(
    iot_domain_id: Annotated[str, "The IoT domain identifier"],
    display_name: Annotated[Optional[str], "A user-friendly display name for the IoT domain"] = None,
    description: Annotated[Optional[str], "A short description of the IoT domain"] = None,
    freeform_tags: Annotated[Optional[dict[str, str] | str], "Free-form tags as an object or JSON string"] = None,
    defined_tags: Annotated[Optional[dict[str, dict[str, Any]] | str], "Defined tags as an object or JSON string"] = None,
    if_match: Annotated[Optional[str], "An etag value for optimistic concurrency control when updating the IoT domain"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the update IoT domain request"] = None,
):
    """Update a specific IoT domain by ID."""
    try:
        iot_client = get_iot_client()

        update_iot_domain_details = oci.iot.models.UpdateIotDomainDetails(
            display_name=display_name,
            description=description,
            freeform_tags=_parse_json_input(freeform_tags, "freeform_tags"),
            defined_tags=_parse_json_input(defined_tags, "defined_tags"),
        )

        kwargs = {
            "iot_domain_id": iot_domain_id,
            "update_iot_domain_details": update_iot_domain_details,
        }
        if if_match is not None:
            kwargs["if_match"] = if_match
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id

        response = iot_client.update_iot_domain(**kwargs)
        return _response_to_dict(response)
    except Exception as e:
        logger.error(f"Error updating IoT domain {iot_domain_id}: {e}")
        raise

@mcp.tool(
    description="Updates a specific IoT domain group by its identifier."
)
def update_iot_domain_group(
    iot_domain_group_id: Annotated[str, "The IoT domain group identifier"],
    display_name: Annotated[Optional[str], "A user-friendly display name for the IoT domain group"] = None,
    description: Annotated[Optional[str], "A short description of the IoT domain group"] = None,
    freeform_tags: Annotated[Optional[dict[str, str] | str], "Free-form tags as an object or JSON string"] = None,
    defined_tags: Annotated[Optional[dict[str, dict[str, Any]] | str], "Defined tags as an object or JSON string"] = None,
    if_match: Annotated[Optional[str], "An etag value for optimistic concurrency control when updating the IoT domain group"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the update IoT domain group request"] = None,
):
    """Update a specific IoT domain group by ID."""
    try:
        iot_client = get_iot_client()

        update_iot_domain_group_details = oci.iot.models.UpdateIotDomainGroupDetails(
            display_name=display_name,
            description=description,
            freeform_tags=_parse_json_input(freeform_tags, "freeform_tags"),
            defined_tags=_parse_json_input(defined_tags, "defined_tags"),
        )

        kwargs = {
            "iot_domain_group_id": iot_domain_group_id,
            "update_iot_domain_group_details": update_iot_domain_group_details,
        }
        if if_match is not None:
            kwargs["if_match"] = if_match
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id

        response = iot_client.update_iot_domain_group(**kwargs)
        return _response_to_dict(response)
    except Exception as e:
        logger.error(f"Error updating IoT domain group {iot_domain_group_id}: {e}")
        raise

@mcp.tool(
    description="Deletes a specific IoT domain by its identifier."
)
def delete_iot_domain(
    iot_domain_id: Annotated[str, "The IoT domain identifier"],
    if_match: Annotated[Optional[str], "An etag value for optimistic concurrency control when deleting the IoT domain"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the delete IoT domain request"] = None,
):
    """Delete a specific IoT domain by ID."""
    try:
        iot_client = get_iot_client()

        kwargs = {"iot_domain_id": iot_domain_id}
        if if_match is not None:
            kwargs["if_match"] = if_match
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id

        response = iot_client.delete_iot_domain(**kwargs)
        return _response_to_dict(response)
    except Exception as e:
        logger.error(f"Error deleting IoT domain {iot_domain_id}: {e}")
        raise

@mcp.tool(
    description="Deletes a specific IoT domain group by its identifier."
)
def delete_iot_domain_group(
    iot_domain_group_id: Annotated[str, "The IoT domain group identifier"],
    if_match: Annotated[Optional[str], "An etag value for optimistic concurrency control when deleting the IoT domain group"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the delete IoT domain group request"] = None,
):
    """Delete a specific IoT domain group by ID."""
    try:
        iot_client = get_iot_client()

        kwargs = {"iot_domain_group_id": iot_domain_group_id}
        if if_match is not None:
            kwargs["if_match"] = if_match
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id

        response = iot_client.delete_iot_domain_group(**kwargs)
        return _response_to_dict(response)
    except Exception as e:
        logger.error(f"Error deleting IoT domain group {iot_domain_group_id}: {e}")
        raise

@mcp.tool(
    description="Invokes a raw command on a specific digital twin instance."
)
def invoke_raw_command(
    digital_twin_instance_id: Annotated[str, "The digital twin instance identifier"],
    request_endpoint: Annotated[str, "The device endpoint where the request should be forwarded"],
    request_data_format: Annotated[str, "The request payload format: JSON, TEXT, or BINARY"],
    request_data: Annotated[Optional[dict[str, Any] | str], "The request payload as an object, plain text, base64 string, or JSON string"] = None,
    response_endpoint: Annotated[Optional[str], "The device endpoint from which a response is expected"] = None,
    request_duration: Annotated[Optional[str], "The duration by which the request should be sent"] = None,
    response_duration: Annotated[Optional[str], "The duration by which the response should be received"] = None,
    request_data_content_type: Annotated[Optional[str], "The MIME content type for the request payload"] = None,
    opc_retry_token: Annotated[Optional[str], "A retry token for safely retrying the request"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the request"] = None,
):
    """Invoke a raw command on a specific digital twin instance."""
    try:
        iot_client = get_iot_client()

        invoke_raw_command_details = _build_invoke_raw_command_details(
            request_data_format=request_data_format,
            request_endpoint=request_endpoint,
            response_endpoint=response_endpoint,
            request_duration=request_duration,
            response_duration=response_duration,
            request_data_content_type=request_data_content_type,
            request_data=request_data,
        )

        kwargs = {
            "digital_twin_instance_id": digital_twin_instance_id,
            "invoke_raw_command_details": invoke_raw_command_details,
        }
        if opc_retry_token is not None:
            kwargs["opc_retry_token"] = opc_retry_token
        if opc_request_id is not None:
            kwargs["opc_request_id"] = opc_request_id

        response = iot_client.invoke_raw_command(**kwargs)
        return _response_to_dict(response)
    except Exception as e:
        logger.error(f"Error invoking raw command for digital twin instance {digital_twin_instance_id}: {e}")
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
        return IoTDomainModel.from_oci_model(iot_domain.data).model_dump()
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
        return IoTDomainGroupModel.from_oci_model(iot_domain_group.data).model_dump()
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
        return WorkRequestModel.from_oci_model(work_request.data).model_dump()
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
        return _result_payload([DigitalTwinAdapterModel.from_oci_model(adapter).model_dump() for adapter in adapters])
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
        return _result_payload([DigitalTwinModelSummaryModel.from_oci_model(model).model_dump() for model in models])
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
        return _result_payload([DigitalTwinInstanceModel.from_oci_model(instance).model_dump() for instance in instances])
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
        return _result_payload([DigitalTwinRelationshipModel.from_oci_model(relationship).model_dump() for relationship in relationships])
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
        return _result_payload([IoTDomainGroupModel.from_oci_model(domain_group).model_dump() for domain_group in groups])
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
        return _result_payload([IoTDomainModel.from_oci_model(domain).model_dump() for domain in domains_list])
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
        result = [error if isinstance(error, str) else ErrorModel.from_oci_model(error).model_dump() for error in errors]
        return _result_payload(result)
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
        result = [log if isinstance(log, str) else LogModel.from_oci_model(log).model_dump() for log in logs]
        return _result_payload(result)
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
        return _result_payload([WorkRequestModel.from_oci_model(work_request).model_dump() for work_request in requests_list])
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

        return _result_payload([CompartmentModel.from_oci_model(compartment).model_dump() for compartment in deduped.values()])
    except Exception as e:
        logger.error(f"Error listing compartments: {e}")
        raise

@mcp.tool(
    description="Lists raw data records from the Oracle IoT Data API for a specific IoT domain."
)
def list_raw_data(
    iot_domain_group_short_id: Annotated[str, "The IoT domain group short identifier used by the Data API host"],
    iot_domain_short_id: Annotated[str, "The IoT domain short identifier used by the Data API path"],
    query_params: Annotated[Optional[dict[str, Any] | str], "Optional Data API query parameters as an object or JSON string"] = None,
    region: Annotated[Optional[str], "OCI region for the IoT Data API endpoint; defaults to the configured OCI profile region"] = None,
    access_token: Annotated[Optional[str], "Bearer token for the IoT Data API; defaults to OCI_IOT_DATA_API_ACCESS_TOKEN if omitted"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the request"] = None,
):
    """List raw data records from the Oracle IoT Data API."""
    return _call_iot_data_api(
        resource_path="/rawData",
        iot_domain_group_short_id=iot_domain_group_short_id,
        iot_domain_short_id=iot_domain_short_id,
        query_params=query_params,
        region=region,
        access_token=access_token,
        opc_request_id=opc_request_id,
    )


@mcp.tool(
    description="Gets a raw data record by identifier from the Oracle IoT Data API for a specific IoT domain."
)
def get_raw_data(
    iot_domain_group_short_id: Annotated[str, "The IoT domain group short identifier used by the Data API host"],
    iot_domain_short_id: Annotated[str, "The IoT domain short identifier used by the Data API path"],
    record_id: Annotated[str, "The raw data record identifier"],
    region: Annotated[Optional[str], "OCI region for the IoT Data API endpoint; defaults to the configured OCI profile region"] = None,
    access_token: Annotated[Optional[str], "Bearer token for the IoT Data API; defaults to OCI_IOT_DATA_API_ACCESS_TOKEN if omitted"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the request"] = None,
):
    """Get a raw data record by ID from the Oracle IoT Data API."""
    return _call_iot_data_api(
        resource_path=f"/rawData/{record_id}",
        iot_domain_group_short_id=iot_domain_group_short_id,
        iot_domain_short_id=iot_domain_short_id,
        region=region,
        access_token=access_token,
        opc_request_id=opc_request_id,
    )


@mcp.tool(
    description="Lists rejected data records from the Oracle IoT Data API for a specific IoT domain."
)
def list_rejected_data(
    iot_domain_group_short_id: Annotated[str, "The IoT domain group short identifier used by the Data API host"],
    iot_domain_short_id: Annotated[str, "The IoT domain short identifier used by the Data API path"],
    query_params: Annotated[Optional[dict[str, Any] | str], "Optional Data API query parameters as an object or JSON string"] = None,
    region: Annotated[Optional[str], "OCI region for the IoT Data API endpoint; defaults to the configured OCI profile region"] = None,
    access_token: Annotated[Optional[str], "Bearer token for the IoT Data API; defaults to OCI_IOT_DATA_API_ACCESS_TOKEN if omitted"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the request"] = None,
):
    """List rejected data records from the Oracle IoT Data API."""
    return _call_iot_data_api(
        resource_path="/rejectedData",
        iot_domain_group_short_id=iot_domain_group_short_id,
        iot_domain_short_id=iot_domain_short_id,
        query_params=query_params,
        region=region,
        access_token=access_token,
        opc_request_id=opc_request_id,
    )


@mcp.tool(
    description="Gets a rejected data record by identifier from the Oracle IoT Data API for a specific IoT domain."
)
def get_rejected_data(
    iot_domain_group_short_id: Annotated[str, "The IoT domain group short identifier used by the Data API host"],
    iot_domain_short_id: Annotated[str, "The IoT domain short identifier used by the Data API path"],
    record_id: Annotated[str, "The rejected data record identifier"],
    region: Annotated[Optional[str], "OCI region for the IoT Data API endpoint; defaults to the configured OCI profile region"] = None,
    access_token: Annotated[Optional[str], "Bearer token for the IoT Data API; defaults to OCI_IOT_DATA_API_ACCESS_TOKEN if omitted"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the request"] = None,
):
    """Get a rejected data record by ID from the Oracle IoT Data API."""
    return _call_iot_data_api(
        resource_path=f"/rejectedData/{record_id}",
        iot_domain_group_short_id=iot_domain_group_short_id,
        iot_domain_short_id=iot_domain_short_id,
        region=region,
        access_token=access_token,
        opc_request_id=opc_request_id,
    )


@mcp.tool(
    description="Lists snapshot data records from the Oracle IoT Data API for a specific IoT domain."
)
def list_snapshot_data(
    iot_domain_group_short_id: Annotated[str, "The IoT domain group short identifier used by the Data API host"],
    iot_domain_short_id: Annotated[str, "The IoT domain short identifier used by the Data API path"],
    query_params: Annotated[Optional[dict[str, Any] | str], "Optional Data API query parameters as an object or JSON string"] = None,
    region: Annotated[Optional[str], "OCI region for the IoT Data API endpoint; defaults to the configured OCI profile region"] = None,
    access_token: Annotated[Optional[str], "Bearer token for the IoT Data API; defaults to OCI_IOT_DATA_API_ACCESS_TOKEN if omitted"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the request"] = None,
):
    """List snapshot data records from the Oracle IoT Data API."""
    return _call_iot_data_api(
        resource_path="/snapshotData",
        iot_domain_group_short_id=iot_domain_group_short_id,
        iot_domain_short_id=iot_domain_short_id,
        query_params=query_params,
        region=region,
        access_token=access_token,
        opc_request_id=opc_request_id,
    )


@mcp.tool(
    description="Lists historized data records from the Oracle IoT Data API for a specific IoT domain."
)
def list_historized_data(
    iot_domain_group_short_id: Annotated[str, "The IoT domain group short identifier used by the Data API host"],
    iot_domain_short_id: Annotated[str, "The IoT domain short identifier used by the Data API path"],
    query_params: Annotated[Optional[dict[str, Any] | str], "Optional Data API query parameters as an object or JSON string"] = None,
    region: Annotated[Optional[str], "OCI region for the IoT Data API endpoint; defaults to the configured OCI profile region"] = None,
    access_token: Annotated[Optional[str], "Bearer token for the IoT Data API; defaults to OCI_IOT_DATA_API_ACCESS_TOKEN if omitted"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the request"] = None,
):
    """List historized data records from the Oracle IoT Data API."""
    return _call_iot_data_api(
        resource_path="/historizedData",
        iot_domain_group_short_id=iot_domain_group_short_id,
        iot_domain_short_id=iot_domain_short_id,
        query_params=query_params,
        region=region,
        access_token=access_token,
        opc_request_id=opc_request_id,
    )


@mcp.tool(
    description="Gets a historized data record by identifier from the Oracle IoT Data API for a specific IoT domain."
)
def get_historized_data(
    iot_domain_group_short_id: Annotated[str, "The IoT domain group short identifier used by the Data API host"],
    iot_domain_short_id: Annotated[str, "The IoT domain short identifier used by the Data API path"],
    record_id: Annotated[str, "The historized data record identifier"],
    region: Annotated[Optional[str], "OCI region for the IoT Data API endpoint; defaults to the configured OCI profile region"] = None,
    access_token: Annotated[Optional[str], "Bearer token for the IoT Data API; defaults to OCI_IOT_DATA_API_ACCESS_TOKEN if omitted"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the request"] = None,
):
    """Get a historized data record by ID from the Oracle IoT Data API."""
    return _call_iot_data_api(
        resource_path=f"/historizedData/{record_id}",
        iot_domain_group_short_id=iot_domain_group_short_id,
        iot_domain_short_id=iot_domain_short_id,
        region=region,
        access_token=access_token,
        opc_request_id=opc_request_id,
    )


@mcp.tool(
    description="Lists raw command data records from the Oracle IoT Data API for a specific IoT domain."
)
def list_raw_command_data(
    iot_domain_group_short_id: Annotated[str, "The IoT domain group short identifier used by the Data API host"],
    iot_domain_short_id: Annotated[str, "The IoT domain short identifier used by the Data API path"],
    query_params: Annotated[Optional[dict[str, Any] | str], "Optional Data API query parameters as an object or JSON string"] = None,
    region: Annotated[Optional[str], "OCI region for the IoT Data API endpoint; defaults to the configured OCI profile region"] = None,
    access_token: Annotated[Optional[str], "Bearer token for the IoT Data API; defaults to OCI_IOT_DATA_API_ACCESS_TOKEN if omitted"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the request"] = None,
):
    """List raw command data records from the Oracle IoT Data API."""
    return _call_iot_data_api(
        resource_path="/rawCommandData",
        iot_domain_group_short_id=iot_domain_group_short_id,
        iot_domain_short_id=iot_domain_short_id,
        query_params=query_params,
        region=region,
        access_token=access_token,
        opc_request_id=opc_request_id,
    )


@mcp.tool(
    description="Gets a raw command data record by identifier from the Oracle IoT Data API for a specific IoT domain."
)
def get_raw_command_data(
    iot_domain_group_short_id: Annotated[str, "The IoT domain group short identifier used by the Data API host"],
    iot_domain_short_id: Annotated[str, "The IoT domain short identifier used by the Data API path"],
    record_id: Annotated[str, "The raw command data record identifier"],
    region: Annotated[Optional[str], "OCI region for the IoT Data API endpoint; defaults to the configured OCI profile region"] = None,
    access_token: Annotated[Optional[str], "Bearer token for the IoT Data API; defaults to OCI_IOT_DATA_API_ACCESS_TOKEN if omitted"] = None,
    opc_request_id: Annotated[Optional[str], "A unique Oracle-assigned identifier for the request"] = None,
):
    """Get a raw command data record by ID from the Oracle IoT Data API."""
    return _call_iot_data_api(
        resource_path=f"/rawCommandData/{record_id}",
        iot_domain_group_short_id=iot_domain_group_short_id,
        iot_domain_short_id=iot_domain_short_id,
        region=region,
        access_token=access_token,
        opc_request_id=opc_request_id,
    )


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
