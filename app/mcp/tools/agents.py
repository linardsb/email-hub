"""AI agent tools — expose all 9 production agents as MCP tools.

Each tool invokes a full LLM-powered agent pipeline (skill loading, prompt
construction, LLM call, post-processing, optional QA gate).  Expect 10-30 s
per invocation depending on model and HTML size.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.core.logging import get_logger
from app.mcp import MCPContext
from app.mcp.auth import require_scope
from app.mcp.formatting import to_dict, truncate_html

logger = get_logger(__name__)

_MAX_HTML_SIZE = 500_000
_MAX_BRIEF_SIZE = 4_000
_MAX_TEXT_SIZE = 10_000


def _split_csv(value: str | None) -> list[str] | None:
    """Split a comma-separated string into a cleaned list, or return None."""
    if not value:
        return None
    items = [s.strip() for s in value.split(",") if s.strip()]
    return items or None


def _format_agent_result(data: dict[str, Any], label: str) -> str:
    """Format agent response with truncated HTML and confidence-first ordering."""
    lines: list[str] = [f"**{label}:**"]

    if (conf := data.get("confidence")) is not None:
        lines.append(f"  - **confidence:** {conf:.0%}")

    # Capture full HTML length before truncation
    raw_html = data.get("html")
    html_len = len(raw_html) if isinstance(raw_html, str) else 0

    for key, val in data.items():
        if key in ("html", "confidence"):
            continue
        # Skip empty collections
        if isinstance(val, (list, dict)) and not val:
            continue
        lines.append(f"  - **{key}:** {val}")

    if isinstance(raw_html, str) and raw_html:
        lines.append(f"\n**HTML** ({html_len:,} chars):")
        lines.append(truncate_html(raw_html))

    return "\n".join(lines)


def register_agent_tools(mcp: FastMCP) -> None:
    """Register all 9 AI agent tools."""

    # ── Scaffolder ──

    @mcp.tool()
    @require_scope("write")
    async def agent_scaffold(
        brief: str,
        ctx: MCPContext,
        output_mode: str = "html",
        run_qa: bool = False,
    ) -> str:
        """Generate a complete, production-ready Maizzle email HTML from a campaign brief. \
The scaffolder agent selects the best-fit golden template, fills content slots, applies \
design tokens, adds MSO conditionals for Outlook, VML backgrounds, dark mode meta tags, \
and accessibility attributes. This tool calls an AI model and may take 10-30 seconds.

Args:
  brief: Campaign description (10-4000 chars). Include target audience, tone, \
sections needed, and any brand requirements.
  output_mode: "html" for rendered HTML (default), "structured" for template-first \
build plan JSON.
  run_qa: Run 14-check QA gate on generated HTML (default false).

Output: Generated HTML with confidence score, model used, skills loaded, and optional QA results."""
        if output_mode not in ("html", "structured"):
            return f"Invalid output_mode `{output_mode}`. Must be 'html' or 'structured'."
        if len(brief) > _MAX_BRIEF_SIZE:
            return f"Brief too long ({len(brief):,} chars). Maximum is {_MAX_BRIEF_SIZE:,} chars."
        if len(brief) < 10:
            return "Brief too short. Provide at least 10 characters describing the email campaign."
        try:
            from app.ai.agents.scaffolder.schemas import ScaffolderRequest
            from app.ai.agents.scaffolder.service import get_scaffolder_service

            request = ScaffolderRequest(
                brief=brief,
                output_mode=output_mode,  # pyright: ignore[reportArgumentType]
                run_qa=run_qa,
            )
            service = get_scaffolder_service()
            response = await service.process(request)
            return _format_agent_result(to_dict(response), "Scaffolder")
        except Exception:
            logger.exception("mcp.tool_error", tool="agent_scaffold")
            return "Email scaffolding failed due to an internal error."

    # ── Dark Mode ──

    @mcp.tool()
    @require_scope("write")
    async def agent_dark_mode(
        html: str,
        ctx: MCPContext,
        run_qa: bool = False,
    ) -> str:
        """Add dark mode support to existing email HTML. Injects prefers-color-scheme \
media queries, Outlook [data-ogsc]/[data-ogsb] selectors, color-scheme meta tags, \
and colour remapping for backgrounds, text, borders, and images. Preserves existing \
MSO conditionals and VML. This tool calls an AI model and may take 10-30 seconds.

Args:
  html: Email HTML to enhance (50-500K chars).
  run_qa: Run 14-check QA gate on enhanced HTML (default false).

Output: Enhanced HTML with dark mode styles, confidence score, meta tags injected, \
and optional QA results."""
        if len(html) > _MAX_HTML_SIZE:
            return f"HTML too large ({len(html):,} chars). Maximum is {_MAX_HTML_SIZE:,} chars."
        if len(html) < 50:
            return "HTML too short. Provide at least 50 characters of email HTML."
        try:
            from app.ai.agents.dark_mode.schemas import DarkModeRequest
            from app.ai.agents.dark_mode.service import get_dark_mode_service

            request = DarkModeRequest(html=html, run_qa=run_qa)
            service = get_dark_mode_service()
            response = await service.process(request)
            return _format_agent_result(to_dict(response), "Dark Mode")
        except Exception:
            logger.exception("mcp.tool_error", tool="agent_dark_mode")
            return "Dark mode processing failed due to an internal error."

    # ── Content ──

    @mcp.tool()
    @require_scope("write")
    async def agent_content(
        operation: str,
        text: str,
        ctx: MCPContext,
        tone: str | None = None,
        num_alternatives: int = 3,
    ) -> str:
        """Generate email copy: subject lines, preheaders, CTAs, body text, rewrites, \
and tone adjustments. Includes anti-spam scoring, PII detection, and character length \
validation per operation. This tool calls an AI model and may take 10-30 seconds.

Args:
  operation: One of: subject_line, preheader, cta, body_copy, rewrite, shorten, \
expand, tone_adjust.
  text: Source text or campaign brief (1-10K chars).
  tone: Target tone for tone_adjust, optional hint for others (e.g. "friendly", \
"urgent", "professional").
  num_alternatives: Number of alternatives to generate (1-10, default 3).

Output: Generated alternatives list, spam warnings, length warnings, confidence score."""
        valid_ops = {
            "subject_line",
            "preheader",
            "cta",
            "body_copy",
            "rewrite",
            "shorten",
            "expand",
            "tone_adjust",
        }
        if operation not in valid_ops:
            return (
                f"Invalid operation `{operation}`. Must be one of: {', '.join(sorted(valid_ops))}."
            )
        if len(text) > _MAX_TEXT_SIZE:
            return f"Text too long ({len(text):,} chars). Maximum is {_MAX_TEXT_SIZE:,} chars."
        if not text.strip():
            return "Text cannot be empty. Provide source text or a campaign brief."
        try:
            from app.ai.agents.content.schemas import ContentRequest
            from app.ai.agents.content.service import get_content_service

            request = ContentRequest(
                operation=operation,  # pyright: ignore[reportArgumentType]
                text=text,
                tone=tone,
                num_alternatives=min(max(num_alternatives, 1), 10),
            )
            service = get_content_service()
            response = await service.process(request)
            return _format_agent_result(to_dict(response), "Content")
        except Exception:
            logger.exception("mcp.tool_error", tool="agent_content")
            return "Content generation failed due to an internal error."

    # ── Outlook Fixer ──

    @mcp.tool()
    @require_scope("write")
    async def agent_outlook_fix(
        html: str,
        ctx: MCPContext,
        issues: str | None = None,
    ) -> str:
        """Fix Outlook rendering issues in email HTML. Adds MSO conditionals, VML \
backgrounds, ghost tables, bulletproof buttons, DPI scaling fixes, and font fallback \
stacks. Auto-detects issues when none specified. This tool calls an AI model and \
may take 10-30 seconds.

Args:
  html: Email HTML with Outlook issues (50-500K chars).
  issues: Comma-separated list of specific issues to fix (e.g. "vml,ghost_tables,dpi"). \
When omitted, auto-detects all Outlook issues.

Output: Fixed HTML with list of fixes applied, MSO validation warnings, confidence score."""
        if len(html) > _MAX_HTML_SIZE:
            return f"HTML too large ({len(html):,} chars). Maximum is {_MAX_HTML_SIZE:,} chars."
        if len(html) < 50:
            return "HTML too short. Provide at least 50 characters of email HTML."
        try:
            from app.ai.agents.outlook_fixer.schemas import OutlookFixerRequest
            from app.ai.agents.outlook_fixer.service import get_outlook_fixer_service

            request = OutlookFixerRequest(html=html, issues=_split_csv(issues))
            service = get_outlook_fixer_service()
            response = await service.process(request)
            return _format_agent_result(to_dict(response), "Outlook Fixer")
        except Exception:
            logger.exception("mcp.tool_error", tool="agent_outlook_fix")
            return "Outlook fixing failed due to an internal error."

    # ── Accessibility ──

    @mcp.tool()
    @require_scope("write")
    async def agent_accessibility(
        html: str,
        ctx: MCPContext,
        focus_areas: str | None = None,
    ) -> str:
        """Audit and fix email HTML for WCAG 2.1 AA accessibility compliance. Adds alt \
text to images, table role attributes, lang attributes, heading hierarchy fixes, colour \
contrast improvements, and screen reader compatibility. This tool calls an AI model and \
may take 10-30 seconds.

Args:
  html: Email HTML to audit (50-500K chars).
  focus_areas: Comma-separated list of areas to focus on (e.g. "alt_text,contrast,headings"). \
When omitted, audits all accessibility categories.

Output: Fixed HTML with accessibility improvements, alt text warnings, confidence score."""
        if len(html) > _MAX_HTML_SIZE:
            return f"HTML too large ({len(html):,} chars). Maximum is {_MAX_HTML_SIZE:,} chars."
        if len(html) < 50:
            return "HTML too short. Provide at least 50 characters of email HTML."
        try:
            from app.ai.agents.accessibility.schemas import AccessibilityRequest
            from app.ai.agents.accessibility.service import get_accessibility_service

            request = AccessibilityRequest(html=html, focus_areas=_split_csv(focus_areas))
            service = get_accessibility_service()
            response = await service.process(request)
            return _format_agent_result(to_dict(response), "Accessibility")
        except Exception:
            logger.exception("mcp.tool_error", tool="agent_accessibility")
            return "Accessibility processing failed due to an internal error."

    # ── Code Reviewer ──

    @mcp.tool()
    @require_scope("write")
    async def agent_code_review(
        html: str,
        ctx: MCPContext,
        focus: str = "all",
    ) -> str:
        """Review email HTML for quality and compatibility issues. Performs static analysis \
for redundant code, unsupported CSS per email client, invalid nesting, file size concerns, \
link validation, anti-patterns, and spam triggers. Analysis-only — does NOT modify HTML. \
This tool calls an AI model and may take 10-30 seconds.

Args:
  html: Email HTML to review (50-500K chars).
  focus: Review focus area — one of: redundant_code, css_support, nesting, file_size, \
link_validation, anti_patterns, spam_patterns, all (default: all).

Output: Structured issues list with severity, rule, suggestion, affected clients, and \
responsible agent. Original HTML returned unmodified."""
        valid_focuses = {
            "redundant_code",
            "css_support",
            "nesting",
            "file_size",
            "link_validation",
            "anti_patterns",
            "spam_patterns",
            "all",
        }
        if focus not in valid_focuses:
            return f"Invalid focus `{focus}`. Must be one of: {', '.join(sorted(valid_focuses))}."
        if len(html) > _MAX_HTML_SIZE:
            return f"HTML too large ({len(html):,} chars). Maximum is {_MAX_HTML_SIZE:,} chars."
        if len(html) < 50:
            return "HTML too short. Provide at least 50 characters of email HTML."
        try:
            from app.ai.agents.code_reviewer.schemas import CodeReviewRequest
            from app.ai.agents.code_reviewer.service import get_code_review_service

            request = CodeReviewRequest(html=html, focus=focus)  # pyright: ignore[reportArgumentType]
            service = get_code_review_service()
            response = await service.process(request)
            return _format_agent_result(to_dict(response), "Code Review")
        except Exception:
            logger.exception("mcp.tool_error", tool="agent_code_review")
            return "Code review failed due to an internal error."

    # ── Personalisation ──

    @mcp.tool()
    @require_scope("write")
    async def agent_personalise(
        html: str,
        platform: str,
        requirements: str,
        ctx: MCPContext,
    ) -> str:
        """Inject ESP-specific dynamic content syntax into email HTML. Supports Braze \
Liquid, SFMC AMPscript, Adobe Campaign JavaScript, Klaviyo Django, Mailchimp Merge \
Language, HubSpot HubL, and Iterable Handlebars. Adds conditional blocks, merge tags, \
fallback values, and dynamic sections. This tool calls an AI model and may take \
10-30 seconds.

Args:
  html: Email HTML to personalise (50-500K chars).
  platform: Target ESP — one of: braze, sfmc, adobe_campaign, klaviyo, mailchimp, \
hubspot, iterable.
  requirements: What personalisation to add (5-5000 chars). E.g. "Add first name \
greeting with fallback, show VIP section for premium users".

Output: Personalised HTML with ESP syntax injected, tags list, syntax warnings, \
confidence score."""
        valid_platforms = {
            "braze",
            "sfmc",
            "adobe_campaign",
            "klaviyo",
            "mailchimp",
            "hubspot",
            "iterable",
        }
        if platform not in valid_platforms:
            return f"Invalid platform `{platform}`. Must be one of: {', '.join(sorted(valid_platforms))}."
        if len(html) > _MAX_HTML_SIZE:
            return f"HTML too large ({len(html):,} chars). Maximum is {_MAX_HTML_SIZE:,} chars."
        if len(html) < 50:
            return "HTML too short. Provide at least 50 characters of email HTML."
        if not requirements.strip() or len(requirements) < 5:
            return (
                "Requirements too short. Describe what personalisation to add (at least 5 chars)."
            )
        try:
            from app.ai.agents.personalisation.schemas import PersonalisationRequest
            from app.ai.agents.personalisation.service import get_personalisation_service

            request = PersonalisationRequest(
                html=html,
                platform=platform,  # pyright: ignore[reportArgumentType]
                requirements=requirements,
            )
            service = get_personalisation_service()
            response = await service.process(request)
            return _format_agent_result(to_dict(response), "Personalisation")
        except Exception:
            logger.exception("mcp.tool_error", tool="agent_personalise")
            return "Personalisation failed due to an internal error."

    # ── Innovation ──

    @mcp.tool()
    @require_scope("write")
    async def agent_innovate(
        technique: str,
        ctx: MCPContext,
        category: str | None = None,
        target_clients: str | None = None,
    ) -> str:
        """Prototype experimental email techniques and assess their feasibility. Handles \
CSS checkbox hacks (tabs, accordions, carousels), AMP for Email, CSS animations, and \
progressive enhancement patterns. Returns working prototype code with static fallback \
for unsupported clients. This tool calls an AI model and may take 10-30 seconds.

Args:
  technique: Description of the technique to prototype (5-2000 chars). E.g. "CSS-only \
accordion for FAQ section" or "AMP carousel with 5 product cards".
  category: Optional category hint — interactive, visual_effects, amp, \
progressive_enhancement, accessibility.
  target_clients: Comma-separated email client filter (e.g. "gmail,apple_mail,outlook_365").

Output: Working HTML/CSS prototype, feasibility assessment, client coverage percentage, \
risk level, recommendation (ship/test_further/avoid), static fallback HTML."""
        if len(technique) > 2000:
            return f"Technique description too long ({len(technique):,} chars). Maximum is 2,000 chars."
        if len(technique) < 5:
            return "Technique description too short. Provide at least 5 characters."
        try:
            from app.ai.agents.innovation.schemas import InnovationRequest
            from app.ai.agents.innovation.service import get_innovation_service

            request = InnovationRequest(
                technique=technique,
                category=category,
                target_clients=_split_csv(target_clients),
            )
            service = get_innovation_service()
            response = await service.process(request)
            return _format_agent_result(to_dict(response), "Innovation")
        except Exception:
            logger.exception("mcp.tool_error", tool="agent_innovate")
            return "Innovation prototyping failed due to an internal error."

    # ── Knowledge ──

    @mcp.tool()
    @require_scope("read")
    async def agent_knowledge(
        question: str,
        ctx: MCPContext,
        domain: str | None = None,
    ) -> str:
        """Ask the Knowledge agent an email development question. Searches the Hub \
knowledge base (20 documents across CSS support, best practices, client quirks) and \
generates a grounded answer with citations and confidence score. Use this for deeper \
analysis than knowledge_search — it synthesises an answer rather than returning raw \
search results. This tool calls an AI model and may take 10-30 seconds.

Args:
  question: Email development question (5-2000 chars). E.g. "Why does Gmail strip \
media queries?" or "What's the best way to do responsive columns in Outlook?".
  domain: Optional domain filter — css_support, best_practices, client_quirks.

Output: Synthesised answer with cited sources, confidence score, relevance scores."""
        if len(question) > 2000:
            return f"Question too long ({len(question):,} chars). Maximum is 2,000 chars."
        if len(question) < 5:
            return "Question too short. Provide at least 5 characters."
        try:
            from app.ai.agents.knowledge.schemas import KnowledgeRequest
            from app.ai.agents.knowledge.service import get_knowledge_agent_service
            from app.core.database import get_db_context
            from app.knowledge.services.search import SearchService

            request = KnowledgeRequest(question=question, domain=domain)
            service = get_knowledge_agent_service()
            async with get_db_context() as db:
                rag_service = SearchService(db)
                response = await service.process(request, rag_service=rag_service)
            return _format_agent_result(to_dict(response), "Knowledge")
        except Exception:
            logger.exception("mcp.tool_error", tool="agent_knowledge")
            return "Knowledge query failed due to an internal error."
