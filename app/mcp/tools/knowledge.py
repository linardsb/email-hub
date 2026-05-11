"""Knowledge search and ontology tools."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.core.logging import get_logger
from app.mcp import MCPContext
from app.mcp.auth import require_scope
from app.mcp.formatting import format_knowledge_result, to_dict

logger = get_logger(__name__)


def register_knowledge_tools(mcp: FastMCP) -> None:
    """Register knowledge-domain tools."""

    @mcp.tool()
    @require_scope("read")
    async def knowledge_search(
        query: str,
        ctx: MCPContext,
        domain: str | None = None,
        limit: int = 5,
    ) -> str:
        """Search the email development knowledge base for CSS compatibility data, \
best practices, client rendering quirks, and troubleshooting guides. The knowledge base \
includes caniemail.com data (CSS/HTML support across 30+ email clients), curated \
email development guides, and automatically documented chaos test failures.

Domains: 'compatibility' (CSS support queries), 'how_to' (development guides), \
'template' (template patterns), 'debug' (rendering issue troubleshooting), \
None (auto-detect from query).

Examples: "does Gmail support CSS grid?", "how to make dark mode safe email", \
"Outlook VML fallback pattern".

Output: Ranked results with relevance scores and source domain."""
        limit = min(limit, 50)  # Cap to prevent expensive queries
        try:
            from app.core.database import get_db_context
            from app.knowledge.schemas import SearchRequest
            from app.knowledge.services.search import SearchService

            request = SearchRequest(query=query, domain=domain, language=None, limit=limit)
            async with get_db_context() as db:
                service = SearchService(db)
                if domain:
                    results = await service.search(request)
                else:
                    results = await service.search_routed(request)
            return format_knowledge_result([to_dict(r) for r in results.results])
        except Exception:
            logger.exception("mcp.tool_error", tool="knowledge_search")
            return "Knowledge search failed due to an internal error."

    @mcp.tool()
    @require_scope("read")
    async def css_support_check(
        css_property: str,
        ctx: MCPContext,
        clients: list[str] | None = None,
    ) -> str:
        """Check email client support for a specific CSS property using the caniemail ontology. \
Returns a support matrix showing which email clients support the property, with notes on \
partial support and known quirks.

Examples: "flex", "gap", "background-image", "max-width", ":hover".

If clients specified, filters to those clients only. Otherwise shows all 30+ clients.

Output: Support matrix table with Yes/No/Partial per client and fallback recommendations."""
        try:
            from app.knowledge.ontology.structured_query import OntologyQueryEngine

            engine = OntologyQueryEngine()
            result = engine.query_property_support(css_property, client_ids=clients)
            if result is None:
                return (
                    f"CSS property `{css_property}` not found in the email ontology. "
                    "Try a different property name or search with `knowledge_search`."
                )
            return _format_support_matrix(result)
        except Exception:
            logger.exception("mcp.tool_error", tool="css_support_check")
            return "CSS support check failed due to an internal error."

    @mcp.tool()
    @require_scope("read")
    async def safe_css_alternatives(
        css_property: str,
        ctx: MCPContext,
        target_clients: list[str] | None = None,
    ) -> str:
        """Find email-safe CSS alternatives for a property that has limited client support. \
Uses the caniemail ontology to find fallback properties that work across the specified \
target clients (or all major clients if none specified).

Example: `safe_css_alternatives("gap")` suggests margin-based spacing patterns.

Output: Alternative properties with support coverage and code examples."""
        try:
            from app.knowledge.ontology.structured_query import OntologyQueryEngine

            engine = OntologyQueryEngine()
            alternatives = engine.find_safe_alternatives(
                css_property, target_clients=target_clients
            )
            if not alternatives:
                return f"No alternatives found for `{css_property}`. Try `knowledge_search` for manual workarounds."
            return format_knowledge_result([to_dict(a) for a in alternatives])
        except Exception:
            logger.exception("mcp.tool_error", tool="safe_css_alternatives")
            return "CSS alternatives lookup failed due to an internal error."


def _format_support_matrix(result: object) -> str:
    """Format CSS support data as a readable matrix."""
    data = to_dict(result)
    lines = [f"## CSS Support: `{data.get('property', '?')}`\n"]
    for client in data.get("clients", []):
        if client.get("supported"):
            status = "supported"
        elif client.get("partial"):
            status = "partial"
        else:
            status = "not supported"
        lines.append(f"  {status} **{client.get('name', '?')}** — {client.get('notes', 'No data')}")
    return "\n".join(lines)
