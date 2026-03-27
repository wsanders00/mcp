"""
Health check endpoint for the OCI IoT MCP server.
"""

from fastmcp import FastMCP

from . import __version__

# Create a separate MCP instance for health checks
health_mcp = FastMCP(name="oci-iot-mcp-server-health")


def tool(*, description: str):
    def decorator(func):
        health_mcp.tool(description=description)(func)
        return func

    return decorator


@tool(description="Health check endpoint for the OCI IoT MCP server.")
def health_check() -> dict[str, str]:
    """Health check endpoint that verifies the server is running."""
    return {
        "status": "healthy",
        "service": "oci-iot-mcp-server",
        "version": __version__,
    }

# Export the health_mcp instance for use in main server
__all__ = ["health_check", "health_mcp"]
