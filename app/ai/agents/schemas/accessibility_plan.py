"""Structured output schema for the Accessibility agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class AltTextDecision:
    """Alt text decision for a single image."""

    img_selector: str
    category: Literal["content", "decorative", "functional", "complex"]
    alt_text: str
    is_decorative: bool


@dataclass(frozen=True)
class A11yFix:
    """A single accessibility fix to apply."""

    issue_type: Literal[
        "missing_lang",
        "missing_role",
        "missing_scope",
        "missing_alt",
        "heading_order",
        "link_text",
        "color_contrast",
        "missing_landmark",
        "zoom_disabled",
    ]
    selector: str
    fix_value: str
    severity: Literal["critical", "serious", "moderate", "mild"] = "moderate"


@dataclass(frozen=True)
class AccessibilityPlan:
    """Structured plan for accessibility improvements."""

    alt_text_decisions: tuple[AltTextDecision, ...]
    structural_fixes: tuple[A11yFix, ...]
    reasoning: str = ""
