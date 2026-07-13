"""Stdio entry point for IDE integration (Claude Desktop, Cursor).

Usage:
    python -m app.mcp

Configure in Claude Desktop / Cursor:
    {"mcpServers": {"email-hub": {
        "command": "python", "args": ["-m", "app.mcp"],
        "env": {"HUB_API_KEY": "your-api-key"}
    }}}
"""

from app.mcp.server import create_mcp_server


def main() -> None:
    """Run the MCP server in stdio transport mode."""
    mcp = create_mcp_server()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
