"""MCP (Model Context Protocol) server for the Email Hub."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context

# Type alias for MCP Context — avoids repeating generic params in every tool signature
MCPContext = Context[Any, Any, Any]

__all__ = ["MCPContext"]
