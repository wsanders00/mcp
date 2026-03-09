"""
Copyright (c) 2025, Oracle and/or its affiliates.
Licensed under the Universal Permissive License v1.0 as shown at
https://oss.oracle.com/licenses/upl.
"""

from pydantic import BaseModel, Field
from typing import Any, Optional
from datetime import datetime

class DigitalTwinAdapterModel(BaseModel):
    id: str = Field(..., description="The digital twin adapter identifier")
    name: Optional[str] = Field(None, description="The name of the digital twin adapter")
    description: Optional[str] = Field(None, description="Description of the digital twin adapter")
    lifecycle_state: Optional[str] = Field(None, description="Lifecycle state of the digital twin adapter")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp of the digital twin adapter")
    last_updated: Optional[datetime] = Field(None, description="Last update timestamp of the digital twin adapter")

    @classmethod
    def from_oci_model(cls, model: Any):
        """Create a DigitalTwinAdapterModel from an OCI digital twin adapter object."""
        return cls(
            id=getattr(model, "id"),
            name=getattr(model, "name", getattr(model, "display_name", None)),
            description=getattr(model, "description", None),
            lifecycle_state=getattr(model, "lifecycle_state", None),
            created_at=getattr(model, "created_at", getattr(model, "time_created", None)),
            last_updated=getattr(model, "last_updated", getattr(model, "time_updated", None)),
        )

class DigitalTwinModelModel(BaseModel):
    id: str = Field(..., description="The digital twin model identifier")
    name: Optional[str] = Field(None, description="The name of the digital twin model")
    description: Optional[str] = Field(None, description="Description of the digital twin model")
    lifecycle_state: Optional[str] = Field(None, description="Lifecycle state of the digital twin model")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp of the digital twin model")
    last_updated: Optional[datetime] = Field(None, description="Last update timestamp of the digital twin model")
    freeform_tags: Optional[dict[str, Any]] = Field(None, description="Simple key-value pair that is applied without any predefined name, type, or scope")
    defined_tags: Optional[dict[str, dict[str, Any]]] = Field(None, description="Defined tags for this resource")

    @classmethod
    def from_oci_model(cls, model: Any):
        """Create a DigitalTwinModelModel from an OCI digital twin model object."""
        return cls(
            id=getattr(model, "id"),
            name=getattr(model, "name", getattr(model, "display_name", None)),
            description=getattr(model, "description", None),
            lifecycle_state=getattr(model, "lifecycle_state", None),
            created_at=getattr(model, "created_at", getattr(model, "time_created", None)),
            last_updated=getattr(model, "last_updated", getattr(model, "time_updated", None)),
            freeform_tags=getattr(model, "freeform_tags", None),
            defined_tags=getattr(model, "defined_tags", None),
        )


class DigitalTwinModelSummaryModel(BaseModel):
    id: str = Field(..., description="The digital twin model identifier")
    name: Optional[str] = Field(None, description="The name of the digital twin model")
    description: Optional[str] = Field(None, description="Description of the digital twin model")
    lifecycle_state: Optional[str] = Field(None, description="Lifecycle state of the digital twin model")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp of the digital twin model")
    last_updated: Optional[datetime] = Field(None, description="Last update timestamp of the digital twin model")

    @classmethod
    def from_oci_model(cls, model: Any):
        """Create a DigitalTwinModelSummaryModel from an OCI DigitalTwinModelSummary object."""
        return cls(
            id=getattr(model, "id"),
            name=getattr(model, "name", getattr(model, "display_name", None)),
            description=getattr(model, "description", None),
            lifecycle_state=getattr(model, "lifecycle_state", None),
            created_at=getattr(model, "created_at", getattr(model, "time_created", None)),
            last_updated=getattr(model, "last_updated", getattr(model, "time_updated", None)),
        )

class DigitalTwinInstanceModel(BaseModel):
    id: str = Field(..., description="The digital twin instance identifier")
    name: Optional[str] = Field(None, description="The name of the digital twin instance")
    description: Optional[str] = Field(None, description="Description of the digital twin instance")
    lifecycle_state: Optional[str] = Field(None, description="Lifecycle state of the digital twin instance")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp of the digital twin instance")
    last_updated: Optional[datetime] = Field(None, description="Last update timestamp of the digital twin instance")

    @classmethod
    def from_oci_model(cls, model: Any):
        """Create a DigitalTwinInstanceModel from an OCI digital twin instance object."""
        return cls(
            id=getattr(model, "id"),
            name=getattr(model, "name", getattr(model, "display_name", None)),
            description=getattr(model, "description", None),
            lifecycle_state=getattr(model, "lifecycle_state", None),
            created_at=getattr(model, "created_at", getattr(model, "time_created", None)),
            last_updated=getattr(model, "last_updated", getattr(model, "time_updated", None)),
        )

class DigitalTwinRelationshipModel(BaseModel):
    id: str = Field(..., description="The digital twin relationship identifier")
    name: Optional[str] = Field(None, description="The name of the digital twin relationship")
    description: Optional[str] = Field(None, description="Description of the digital twin relationship")
    lifecycle_state: Optional[str] = Field(None, description="Lifecycle state of the digital twin relationship")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp of the digital twin relationship")
    last_updated: Optional[datetime] = Field(None, description="Last update timestamp of the digital twin relationship")

    @classmethod
    def from_oci_model(cls, model: Any):
        """Create a DigitalTwinRelationshipModel from an OCI digital twin relationship object."""
        return cls(
            id=getattr(model, "id"),
            name=getattr(model, "name", getattr(model, "display_name", None)),
            description=getattr(model, "description", None),
            lifecycle_state=getattr(model, "lifecycle_state", None),
            created_at=getattr(model, "created_at", getattr(model, "time_created", None)),
            last_updated=getattr(model, "last_updated", getattr(model, "time_updated", None)),
        )

class IoTDomainModel(BaseModel):
    id: str = Field(..., description="The IoT domain identifier")
    name: Optional[str] = Field(None, description="The name of the IoT domain")
    description: Optional[str] = Field(None, description="Description of the IoT domain")
    compartment_id: Optional[str] = Field(None, description="Compartment containing the IoT domain")
    lifecycle_state: Optional[str] = Field(None, description="Lifecycle state of the IoT domain")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp of the IoT domain")
    last_updated: Optional[datetime] = Field(None, description="Last update timestamp of the IoT domain")
    
    @classmethod
    def from_oci_model(cls, model: Any):
        """Create an IoTDomainModel from an OCI IotDomainSummary object."""
        # Handle potential attribute differences between summary and full objects
        domain_name = getattr(model, 'name', getattr(model, 'display_name', None))
        description = getattr(model, 'description', None)
        return cls(
            id=getattr(model, "id"),
            name=domain_name,
            description=description,
            compartment_id=getattr(model, "compartment_id", None),
            lifecycle_state=getattr(model, "lifecycle_state", None),
            created_at=getattr(model, "created_at", getattr(model, "time_created", None)),
            last_updated=getattr(model, "last_updated", getattr(model, "time_updated", None)),
        )

class IoTDomainGroupModel(BaseModel):
    id: str = Field(..., description="The IoT domain group identifier")
    name: Optional[str] = Field(None, description="The name of the IoT domain group")
    description: Optional[str] = Field(None, description="Description of the IoT domain group")
    compartment_id: Optional[str] = Field(None, description="Compartment containing the IoT domain group")
    lifecycle_state: Optional[str] = Field(None, description="Lifecycle state of the IoT domain group")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp of the IoT domain group")
    last_updated: Optional[datetime] = Field(None, description="Last update timestamp of the IoT domain group")
    
    @classmethod
    def from_oci_model(cls, model: Any):
        """Create an IoTDomainGroupModel from an OCI IotDomainGroupSummary object."""
        # Handle potential attribute differences between summary and full objects
        group_name = getattr(model, 'name', getattr(model, 'display_name', None))
        description = getattr(model, 'description', None)
        return cls(
            id=getattr(model, "id"),
            name=group_name,
            description=description,
            compartment_id=getattr(model, "compartment_id", None),
            lifecycle_state=getattr(model, "lifecycle_state", None),
            created_at=getattr(model, "created_at", getattr(model, "time_created", None)),
            last_updated=getattr(model, "last_updated", getattr(model, "time_updated", None)),
        )

class WorkRequestModel(BaseModel):
    id: str = Field(..., description="The work request identifier")
    status: Optional[str] = Field(None, description="Status of the work request")
    compartment_id: Optional[str] = Field(None, description="Compartment containing the work request")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp of the work request")
    last_updated: Optional[datetime] = Field(None, description="Last update timestamp of the work request")

    @classmethod
    def from_oci_model(cls, model: Any):
        """Create a WorkRequestModel from an OCI work request object."""
        return cls(
            id=getattr(model, "id"),
            status=getattr(model, "status", getattr(model, "lifecycle_state", None)),
            compartment_id=getattr(model, "compartment_id", None),
            created_at=getattr(model, "created_at", getattr(model, "time_created", None)),
            last_updated=getattr(model, "last_updated", getattr(model, "time_updated", None)),
        )

class ErrorModel(BaseModel):
    code: Optional[str] = Field(None, description="Error code")
    message: str = Field(..., description="Error message")
    timestamp: Optional[datetime] = Field(None, description="Timestamp of the error")

    @classmethod
    def from_oci_model(cls, model: Any):
        """Create an ErrorModel from an OCI work request error object."""
        if isinstance(model, str):
            return cls(message=model)
        return cls(
            code=getattr(model, "code", None),
            message=getattr(model, "message", str(model)),
            timestamp=getattr(model, "timestamp", getattr(model, "time_stamp", None)),
        )

class LogModel(BaseModel):
    level: Optional[str] = Field(None, description="Log level")
    message: str = Field(..., description="Log message")
    timestamp: Optional[datetime] = Field(None, description="Timestamp of the log entry")

    @classmethod
    def from_oci_model(cls, model: Any):
        """Create a LogModel from an OCI work request log entry object."""
        if isinstance(model, str):
            return cls(message=model)
        return cls(
            level=getattr(model, "level", None),
            message=getattr(model, "message", str(model)),
            timestamp=getattr(model, "timestamp", getattr(model, "time_stamp", None)),
        )


class CompartmentModel(BaseModel):
    id: str = Field(..., description="The compartment identifier")
    name: Optional[str] = Field(None, description="The name of the compartment")
    description: Optional[str] = Field(None, description="Description of the compartment")
    parent_id: Optional[str] = Field(None, description="The parent compartment identifier")
    lifecycle_state: Optional[str] = Field(None, description="Lifecycle state of the compartment")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp of the compartment")

    @classmethod
    def from_oci_model(cls, model: Any):
        """Create a CompartmentModel from an OCI compartment object."""
        return cls(
            id=getattr(model, "id"),
            name=getattr(model, "name", getattr(model, "display_name", None)),
            description=getattr(model, "description", None),
            parent_id=getattr(model, "compartment_id", getattr(model, "parent_id", None)),
            lifecycle_state=getattr(model, "lifecycle_state", None),
            created_at=getattr(model, "time_created", getattr(model, "created_at", None)),
        )
