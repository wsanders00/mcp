"""
Copyright (c) 2025, Oracle and/or its affiliates.
Licensed under the Universal Permissive License v1.0 as shown at
https://oss.oracle.com/licenses/upl.
"""

from pydantic import BaseModel, Field, validator
from typing import Annotated, Optional
from datetime import datetime

class DigitalTwinAdapterModel(BaseModel):
    id: str = Field(..., description="The digital twin adapter identifier")
    name: str = Field(..., description="The name of the digital twin adapter")
    description: str = Field(..., description="Description of the digital twin adapter")
    created_at: datetime = Field(..., description="Creation timestamp of the digital twin adapter")
    last_updated: datetime = Field(..., description="Last update timestamp of the digital twin adapter")

class DigitalTwinModelModel(BaseModel):
    id: str = Field(..., description="The digital twin model identifier")
    name: str = Field(..., description="The name of the digital twin model")
    description: str = Field(..., description="Description of the digital twin model")
    created_at: datetime = Field(..., description="Creation timestamp of the digital twin model")
    last_updated: datetime = Field(..., description="Last update timestamp of the digital twin model")

class DigitalTwinInstanceModel(BaseModel):
    id: str = Field(..., description="The digital twin instance identifier")
    name: str = Field(..., description="The name of the digital twin instance")
    description: str = Field(..., description="Description of the digital twin instance")
    created_at: datetime = Field(..., description="Creation timestamp of the digital twin instance")
    last_updated: datetime = Field(..., description="Last update timestamp of the digital twin instance")

class DigitalTwinRelationshipModel(BaseModel):
    id: str = Field(..., description="The digital twin relationship identifier")
    name: str = Field(..., description="The name of the digital twin relationship")
    description: str = Field(..., description="Description of the digital twin relationship")
    created_at: datetime = Field(..., description="Creation timestamp of the digital twin relationship")
    last_updated: datetime = Field(..., description="Last update timestamp of the digital twin relationship")

class IoTDomainModel(BaseModel):
    id: str = Field(..., description="The IoT domain identifier")
    name: str = Field(..., description="The name of the IoT domain")
    description: str = Field(..., description="Description of the IoT domain")
    compartment_id: str = Field(..., description="Compartment containing the IoT domain")
    created_at: datetime = Field(..., description="Creation timestamp of the IoT domain")
    last_updated: datetime = Field(..., description="Last update timestamp of the IoT domain")

class IoTDomainGroupModel(BaseModel):
    id: str = Field(..., description="The IoT domain group identifier")
    name: str = Field(..., description="The name of the IoT domain group")
    description: str = Field(..., description="Description of the IoT domain group")
    compartment_id: str = Field(..., description="Compartment containing the IoT domain group")
    created_at: datetime = Field(..., description="Creation timestamp of the IoT domain group")
    last_updated: datetime = Field(..., description="Last update timestamp of the IoT domain group")

class WorkRequestModel(BaseModel):
    id: str = Field(..., description="The work request identifier")
    status: str = Field(..., description="Status of the work request")
    compartment_id: str = Field(..., description="Compartment containing the work request")
    created_at: datetime = Field(..., description="Creation timestamp of the work request")
    last_updated: datetime = Field(..., description="Last update timestamp of the work request")

class ErrorModel(BaseModel):
    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    timestamp: datetime = Field(..., description="Timestamp of the error")

class LogModel(BaseModel):
    level: str = Field(..., description="Log level")
    message: str = Field(..., description="Log message")
    timestamp: datetime = Field(..., description="Timestamp of the log entry")