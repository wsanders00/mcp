"""
Health check endpoint for the OCI IoT MCP server.
"""

from fastmcp import FastMCP
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

# Create a separate MCP instance for health checks
health_mcp = FastMCP(name="oci-iot-mcp-server-health")

@health_mcp.tool(
    description="Health check endpoint for the OCI IoT MCP server."
)
def health_check() -> Dict[str, Any]:
    """Health check endpoint that verifies the server is running."""
    return {
        "status": "healthy",
        "service": "oci-iot-mcp-server",
        "version": "1.0.0"
    }

# Export the health_mcp instance for use in main server
__all__ = ["health_mcp"]
