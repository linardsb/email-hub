"""Hub MCP server factory and transport configuration."""

from __future__ import annotations

import functools
import json
from typing import Any

from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings
from app.core.logging import get_logger
from app.mcp.auth import current_scopes_var, require_scope, verify_mcp_token
from app.mcp.config import is_tool_allowed
from app.mcp.optimization import (
    MCPResponseCache,
    SchemaRegistry,
    ToolCall,
    batch_execute,
    get_mcp_cache,
    get_schema_registry,
)
from app.mcp.resources import register_resources
from app.mcp.tools.agents import register_agent_tools
from app.mcp.tools.ai import register_ai_tools
from app.mcp.tools.email import register_email_tools
from app.mcp.tools.knowledge import register_knowledge_tools
from app.mcp.tools.qa import register_qa_tools
from app.mcp.tools.rendering import register_rendering_tools
from app.mcp.tools.templates import register_template_tools

logger = get_logger(__name__)


class MCPAuthMiddleware:
    """ASGI middleware that enforces bearer-token authentication on MCP requests."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            auth = headers.get(b"authorization", b"").decode()
            if not auth.startswith("Bearer "):
                response = JSONResponse({"detail": "Missing authentication"}, status_code=401)
                await response(scope, receive, send)
                return
            token = auth.removeprefix("Bearer ")
            result = await verify_mcp_token(token)
            if result is None:
                response = JSONResponse({"detail": "Invalid token"}, status_code=401)
                await response(scope, receive, send)
                return
            # Per-request scope plumb: tool-level @require_scope reads this.
            granted = frozenset(s for s in result.get("scopes", "").split(",") if s)
            token_var = current_scopes_var.set(granted)
            try:
                await self.app(scope, receive, send)
            finally:
                current_scopes_var.reset(token_var)
            return
        await self.app(scope, receive, send)


def create_mcp_server() -> FastMCP:
    """Create and configure the Hub MCP server with all tools and resources.

    Returns a FastMCP instance ready to be mounted or run standalone.
    """
    mcp = FastMCP(
        name="Email Hub",
        instructions=(
            "You are connected to the Email Innovation Hub — a comprehensive platform "
            "for building, testing, and optimizing HTML emails. Use the available tools to "
            "validate email HTML against client compatibility, check deliverability, optimize "
            "CSS for email clients, search email development knowledge, and more. "
            "Start with `qa_check` for basic validation, or `email_production_readiness` "
            "for comprehensive pre-send analysis."
        ),
        stateless_http=True,
        json_response=True,
    )

    # Register tool groups
    register_qa_tools(mcp)
    register_knowledge_tools(mcp)
    register_email_tools(mcp)
    register_rendering_tools(mcp)
    register_template_tools(mcp)
    register_ai_tools(mcp)
    register_agent_tools(mcp)

    # Register batch_execute meta-tool (before allowlist so it participates in filtering)
    _register_batch_tool(mcp)

    # Default-deny: every tool must declare a required scope. Fail closed
    # at boot when a registration is missing the @require_scope marker.
    # Runs *before* allowlist + caching so the audit covers everything
    # that could possibly be reached at runtime.
    _enforce_scope_declarations(mcp)

    # Apply tool allowlist filter — remove tools not in the operator allowlist
    _apply_tool_allowlist(mcp)

    # Register resources
    register_resources(mcp)

    # Initialize cache and schema registry
    settings = get_settings()
    if settings.mcp.cache_enabled:
        cache = get_mcp_cache()
        _wrap_cacheable_tools(mcp, cache)

    if settings.mcp.compress_schemas:
        registry = get_schema_registry()
        _register_schemas(mcp, registry)

    # Wrap scope enforcement LAST so it sits *outside* the cache wrapper —
    # a viewer token must not receive a cached result that an admin
    # primed the cache with.
    _wrap_scope_enforcement(mcp)

    tool_count = len(mcp._tool_manager._tools)
    logger.info("mcp.server_created", tool_count=tool_count)

    return mcp


def _enforce_scope_declarations(mcp: FastMCP) -> None:
    """Fail server startup if any registered tool lacks ``@require_scope``.

    Default-deny: a tool that omits the decorator can be invoked by any
    authenticated user, which is the bug F005 closes. Failing closed at
    boot is safer than warn-only.
    """
    tools = mcp._tool_manager._tools
    missing = [name for name, tool in tools.items() if not _has_scope_marker(tool.fn)]
    if missing:
        raise RuntimeError(
            "MCP tools missing @require_scope decorator (default-deny): "
            + ", ".join(sorted(missing))
        )


def _wrap_scope_enforcement(mcp: FastMCP) -> None:
    """Wrap each tool with the scope check declared by ``@require_scope``.

    The marker decorator stamps ``_mcp_required_scope`` on the tool's
    function. We re-apply the live scope check here, *after* the cache
    wrapper has been installed, so the call order at runtime becomes
    ``scope_check → cache_check → original`` — denied requests never
    reach the cache.
    """
    tools = mcp._tool_manager._tools
    for name, tool in tools.items():
        scope = _scope_marker_of(tool.fn)
        if scope == "read":
            tool.fn = require_scope("read")(tool.fn)
        elif scope == "write":
            tool.fn = require_scope("write")(tool.fn)
        elif scope == "admin":
            tool.fn = require_scope("admin")(tool.fn)
        else:
            # _enforce_scope_declarations already validated this; defensive.
            raise RuntimeError(f"tool {name!r} lost its scope marker before wrap")


def _has_scope_marker(fn: Any) -> bool:  # noqa: ANN401
    return _scope_marker_of(fn) is not None


def _scope_marker_of(fn: Any) -> str | None:  # noqa: ANN401
    """Walk through ``functools.wraps`` chains to find the scope marker."""
    seen: set[int] = set()
    cur: Any = fn
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        scope = getattr(cur, "_mcp_required_scope", None)
        if scope is not None:
            return str(scope)
        cur = getattr(cur, "__wrapped__", None)
    return None


def _apply_tool_allowlist(mcp: FastMCP) -> None:
    """Remove tools that don't match the operator allowlist."""
    tools = mcp._tool_manager._tools
    blocked = [name for name in tools if not is_tool_allowed(name)]
    for name in blocked:
        del tools[name]
        logger.info("mcp.tool_blocked_by_allowlist", tool=name)


def _wrap_cacheable_tools(mcp: FastMCP, cache: MCPResponseCache) -> None:
    """Wrap cacheable tool handlers with cache-check logic."""
    tools = mcp._tool_manager._tools
    for name in list(tools):
        if name not in MCPResponseCache.CACHEABLE_TOOLS:
            continue

        tool = tools[name]
        original_fn = tool.fn

        @functools.wraps(original_fn)
        async def _cached_handler(
            *args: Any,  # noqa: ANN401
            _original: Any = original_fn,  # noqa: ANN401
            _tool_name: str = name,
            **kwargs: Any,  # noqa: ANN401
        ) -> str:
            # Build params dict excluding ctx for cache key
            params = {k: v for k, v in kwargs.items() if k != "ctx"}
            cached = cache.get(_tool_name, params)
            if cached is not None:
                logger.debug("mcp.cache_hit", tool=_tool_name)
                return cached + "\n\n---\n_Cached response_"

            result: str = await _original(*args, **kwargs)
            cache.put(_tool_name, params, result)
            return result

        tool.fn = _cached_handler


def _register_schemas(mcp: FastMCP, registry: SchemaRegistry) -> None:
    """Register and compress all tool input schemas."""
    tools = mcp._tool_manager._tools
    for name, tool in tools.items():
        if hasattr(tool, "parameters") and tool.parameters:
            schema = tool.parameters.get("properties", {})
            if schema:
                registry.register(name, tool.parameters)


def _register_batch_tool(mcp: FastMCP) -> None:
    """Register the batch_execute meta-tool."""
    settings = get_settings()

    @mcp.tool()
    @require_scope("write")
    async def mcp_batch_execute(calls: list[dict[str, Any]], ctx: Any) -> str:  # noqa: ANN401
        """Execute multiple MCP tool calls in a single request to reduce round-trip overhead.

        Each call is ``{"tool_name": "...", "params": {...}}``.
        Cached results from previous identical read-only tool invocations are returned
        immediately without re-execution.  Non-cached calls run concurrently via asyncio
        gather with bounded concurrency.  Results are ordered to match the input call list.
        Useful for running qa_check, estimate_cost, and deliverability_score together.

        Per-call scope is also enforced by each inner tool's own decorator.
        """
        tool_calls: list[ToolCall] = []
        for c in calls:
            tool_name = c.get("tool_name")
            if not isinstance(tool_name, str) or not tool_name:
                continue
            tool_calls.append(ToolCall(tool_name=tool_name, params=c.get("params", {})))

        # Build handler lookup from current tools
        tools = mcp._tool_manager._tools
        handlers = {name: tool.fn for name, tool in tools.items()}

        cache = get_mcp_cache() if settings.mcp.cache_enabled else MCPResponseCache(max_size=0)
        results = await batch_execute(tool_calls, cache, handlers, ctx)

        return json.dumps(
            [
                {
                    "tool_name": r.tool_name,
                    "result": r.result,
                    "cached": r.cached,
                    "error": r.error,
                }
                for r in results
            ],
            indent=2,
        )


# Module-level singleton for mounting
_mcp_server: FastMCP | None = None


def get_mcp_server() -> FastMCP:
    """Get or create the singleton MCP server instance."""
    global _mcp_server
    if _mcp_server is None:
        _mcp_server = create_mcp_server()
    return _mcp_server


def get_mcp_asgi_app() -> ASGIApp:
    """Return the MCP streamable-HTTP ASGI app wrapped with auth middleware."""
    mcp = get_mcp_server()
    mcp.settings.streamable_http_path = "/"
    return MCPAuthMiddleware(mcp.streamable_http_app())
