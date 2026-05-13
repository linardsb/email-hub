"""Correction tracker (F060).

Moved from ``app/design_sync/correction_tracker.py``. The legacy file is a
shim re-exporting from this module so existing import sites are
untouched.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from lxml.html import HtmlElement

from pydantic import BaseModel

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorrectionDiff:
    """Single atomic change between original and corrected HTML."""

    element_tag: str
    attribute: str
    change_type: str  # "property_added", "property_changed", "property_removed", "attribute_added", "attribute_removed", "element_added", "element_removed"
    old_value: str
    new_value: str


@dataclass(frozen=True)
class CorrectionPattern:
    """Aggregated correction pattern from multiple observations."""

    agent: str
    pattern_hash: str
    element_tag: str
    attribute: str
    change_type: str
    input_snippet: str
    output_snippet: str
    occurrences: int
    first_seen: datetime
    last_seen: datetime
    confidence: float


@dataclass(frozen=True)
class ConverterRuleSuggestion:
    """Human-reviewable suggestion for a converter rule."""

    id: str
    description: str
    agent_source: str
    pattern: CorrectionPattern
    suggested_code: str
    status: Literal["suggested", "approved", "rejected", "applied"]


# ---------------------------------------------------------------------------
# Pydantic response schemas (for API endpoints)
# ---------------------------------------------------------------------------


class CorrectionPatternResponse(BaseModel):
    agent: str
    pattern_hash: str
    element_tag: str
    attribute: str
    change_type: str
    input_snippet: str
    output_snippet: str
    occurrences: int
    first_seen: datetime
    last_seen: datetime
    confidence: float

    @classmethod
    def from_pattern(cls, p: CorrectionPattern) -> CorrectionPatternResponse:
        return cls(
            agent=p.agent,
            pattern_hash=p.pattern_hash,
            element_tag=p.element_tag,
            attribute=p.attribute,
            change_type=p.change_type,
            input_snippet=p.input_snippet,
            output_snippet=p.output_snippet,
            occurrences=p.occurrences,
            first_seen=p.first_seen,
            last_seen=p.last_seen,
            confidence=p.confidence,
        )


class ConverterRuleSuggestionResponse(BaseModel):
    id: str
    description: str
    agent_source: str
    pattern: CorrectionPatternResponse
    suggested_code: str
    status: str

    @classmethod
    def from_suggestion(cls, s: ConverterRuleSuggestion) -> ConverterRuleSuggestionResponse:
        return cls(
            id=s.id,
            description=s.description,
            agent_source=s.agent_source,
            pattern=CorrectionPatternResponse.from_pattern(s.pattern),
            suggested_code=s.suggested_code,
            status=s.status,
        )


# ---------------------------------------------------------------------------
# Structural diff extraction
# ---------------------------------------------------------------------------

_SNIPPET_MAX = 200


def _parse_inline_style(style: str) -> dict[str, str]:
    """Parse CSS inline style string into property→value dict."""
    props: dict[str, str] = {}
    for part in style.split(";"):
        part = part.strip()
        if ":" not in part:
            continue
        key, _, val = part.partition(":")
        props[key.strip().lower()] = val.strip()
    return props


def _truncate(text: str, max_len: int = _SNIPPET_MAX) -> str:
    return text[:max_len] if len(text) > max_len else text


def extract_correction_diffs(original_html: str, corrected_html: str) -> list[CorrectionDiff]:
    """Extract structural diffs between original and agent-corrected HTML.

    Uses lxml for DOM comparison — identifies element additions/removals,
    attribute changes, and inline style property changes.
    """
    try:
        from lxml import html as lxml_html
    except ImportError:
        logger.warning("correction_tracker.lxml_unavailable")
        return []

    try:
        orig_doc = lxml_html.fragment_fromstring(original_html, create_parent="div")
        corr_doc = lxml_html.fragment_fromstring(corrected_html, create_parent="div")
    except Exception:
        logger.debug("correction_tracker.html_parse_failed")
        return []

    diffs: list[CorrectionDiff] = []

    # 1. Element count diffs (added/removed tags)
    orig_tags: dict[str, int] = {}
    for el in orig_doc.iter():
        tag = el.tag if isinstance(el.tag, str) else ""
        if tag:
            orig_tags[tag] = orig_tags.get(tag, 0) + 1

    corr_tags: dict[str, int] = {}
    for el in corr_doc.iter():
        tag = el.tag if isinstance(el.tag, str) else ""
        if tag:
            corr_tags[tag] = corr_tags.get(tag, 0) + 1

    all_tags = set(orig_tags) | set(corr_tags)
    for tag in sorted(all_tags):
        orig_count = orig_tags.get(tag, 0)
        corr_count = corr_tags.get(tag, 0)
        if corr_count > orig_count:
            for _ in range(corr_count - orig_count):
                diffs.append(
                    CorrectionDiff(
                        element_tag=tag,
                        attribute="",
                        change_type="element_added",
                        old_value="",
                        new_value=tag,
                    )
                )
        elif orig_count > corr_count:
            for _ in range(orig_count - corr_count):
                diffs.append(
                    CorrectionDiff(
                        element_tag=tag,
                        attribute="",
                        change_type="element_removed",
                        old_value=tag,
                        new_value="",
                    )
                )

    # 2. Attribute and style diffs on elements present in both DOMs
    def _collect_attrs(doc: HtmlElement) -> dict[str, dict[str, str]]:
        attrs: dict[str, dict[str, str]] = {}
        for el in doc.iter():
            if not isinstance(el.tag, str):
                continue
            path = doc.getroottree().getpath(el)
            el_attrs = dict(el.attrib)
            if el_attrs:
                attrs[path] = el_attrs
        return attrs

    orig_attrs = _collect_attrs(orig_doc)
    corr_attrs = _collect_attrs(corr_doc)

    common_paths = set(orig_attrs) & set(corr_attrs)
    for path in sorted(common_paths):
        o_attrs = orig_attrs[path]
        c_attrs = corr_attrs[path]

        tag = path.rsplit("/", 1)[-1].split("[")[0] if "/" in path else "unknown"

        for attr in sorted(set(c_attrs) - set(o_attrs)):
            if attr == "style":
                continue
            diffs.append(
                CorrectionDiff(
                    element_tag=tag,
                    attribute=attr,
                    change_type="attribute_added",
                    old_value="",
                    new_value=_truncate(c_attrs[attr]),
                )
            )

        for attr in sorted(set(o_attrs) - set(c_attrs)):
            if attr == "style":
                continue
            diffs.append(
                CorrectionDiff(
                    element_tag=tag,
                    attribute=attr,
                    change_type="attribute_removed",
                    old_value=_truncate(o_attrs[attr]),
                    new_value="",
                )
            )

        orig_style = o_attrs.get("style", "")
        corr_style = c_attrs.get("style", "")
        if orig_style != corr_style:
            orig_props = _parse_inline_style(orig_style)
            corr_props = _parse_inline_style(corr_style)

            for prop in sorted(set(corr_props) - set(orig_props)):
                diffs.append(
                    CorrectionDiff(
                        element_tag=tag,
                        attribute=f"style.{prop}",
                        change_type="property_added",
                        old_value="",
                        new_value=corr_props[prop],
                    )
                )
            for prop in sorted(set(orig_props) - set(corr_props)):
                diffs.append(
                    CorrectionDiff(
                        element_tag=tag,
                        attribute=f"style.{prop}",
                        change_type="property_removed",
                        old_value=orig_props[prop],
                        new_value="",
                    )
                )
            for prop in sorted(set(orig_props) & set(corr_props)):
                if orig_props[prop] != corr_props[prop]:
                    diffs.append(
                        CorrectionDiff(
                            element_tag=tag,
                            attribute=f"style.{prop}",
                            change_type="property_changed",
                            old_value=orig_props[prop],
                            new_value=corr_props[prop],
                        )
                    )

    return diffs


# ---------------------------------------------------------------------------
# Core tracker
# ---------------------------------------------------------------------------


def _compute_pattern_hash(agent: str, element_tag: str, attribute: str, change_type: str) -> str:
    key = f"{agent}:{element_tag}:{attribute}:{change_type}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


RuleStatus = Literal["suggested", "approved", "rejected", "applied"]


class CorrectionTracker:
    """Tracks agent corrections and suggests converter rules.

    Stores corrections in a JSONL log and aggregates them into patterns.
    Patterns that exceed frequency and confidence thresholds are surfaced
    as converter rule suggestions for human review.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._log_path = data_dir / "correction_patterns.jsonl"
        self._rules_path = data_dir / "correction_rules.json"

    async def record_correction(
        self,
        agent: str,
        original_html: str,
        corrected_html: str,
    ) -> int:
        """Record structural diffs between original and corrected HTML.

        Returns the number of atomic diffs recorded.
        """
        diffs = extract_correction_diffs(original_html, corrected_html)
        if not diffs:
            return 0

        max_entries = get_settings().correction_tracker.max_log_entries

        now = datetime.now(UTC).isoformat()
        entries: list[dict[str, str]] = []
        for d in diffs:
            entries.append(
                {
                    "timestamp": now,
                    "agent": agent,
                    "pattern_hash": _compute_pattern_hash(
                        agent, d.element_tag, d.attribute, d.change_type
                    ),
                    "element_tag": d.element_tag,
                    "attribute": d.attribute,
                    "change_type": d.change_type,
                    "old_value": _truncate(d.old_value),
                    "new_value": _truncate(d.new_value),
                }
            )

        self._append_to_log(entries, max_entries)

        logger.info(
            "correction_tracker.recorded",
            agent=agent,
            diff_count=len(entries),
        )
        return len(entries)

    def get_frequent_patterns(
        self,
        *,
        min_occurrences: int = 5,
        min_confidence: float = 0.9,
    ) -> list[CorrectionPattern]:
        """Return patterns that exceed frequency and confidence thresholds."""
        entries = self._load_log()
        return self._aggregate_patterns(entries, min_occurrences, min_confidence)

    def suggest_converter_rules(
        self,
        *,
        min_occurrences: int = 5,
        min_confidence: float = 0.9,
    ) -> list[ConverterRuleSuggestion]:
        """Generate rule suggestions from frequent patterns."""
        patterns = self.get_frequent_patterns(
            min_occurrences=min_occurrences,
            min_confidence=min_confidence,
        )

        statuses = self._load_rule_statuses()

        _VALID_STATUSES: set[RuleStatus] = {"suggested", "approved", "rejected", "applied"}

        suggestions: list[ConverterRuleSuggestion] = []
        for p in patterns:
            raw_status = statuses.get(p.pattern_hash, "suggested")
            status: RuleStatus = raw_status if raw_status in _VALID_STATUSES else "suggested"
            code = self._generate_code_snippet(p)
            suggestions.append(
                ConverterRuleSuggestion(
                    id=p.pattern_hash,
                    description=f"{p.change_type.replace('_', ' ').title()} "
                    f"on <{p.element_tag}> {p.attribute} (by {p.agent})",
                    agent_source=p.agent,
                    pattern=p,
                    suggested_code=code,
                    status=status,
                )
            )
        return suggestions

    def approve_rule(self, pattern_hash: str) -> None:
        """Mark a correction pattern as approved."""
        statuses = self._load_rule_statuses()
        entries = self._load_log()
        found = any(e.get("pattern_hash") == pattern_hash for e in entries)
        if not found:
            from app.core.exceptions import DomainValidationError

            raise DomainValidationError(f"Pattern {pattern_hash} not found")

        statuses[pattern_hash] = "approved"
        self._save_rule_statuses(statuses)
        logger.info("correction_tracker.rule_approved", pattern_hash=pattern_hash)

    # -- Private helpers --

    def _append_to_log(self, entries: list[dict[str, str]], max_entries: int) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)

        with self._log_path.open("a") as f:
            f.writelines(json.dumps(entry, separators=(",", ":")) + "\n" for entry in entries)

        self._maybe_rotate(max_entries)

    def _maybe_rotate(self, max_entries: int) -> None:
        if not self._log_path.exists():
            return
        lines = self._log_path.read_text().strip().split("\n")
        if len(lines) > max_entries:
            kept = lines[-max_entries:]
            self._log_path.write_text("\n".join(kept) + "\n")
            logger.info(
                "correction_tracker.log_rotated",
                dropped=len(lines) - max_entries,
                kept=max_entries,
            )

    def _load_log(self) -> list[dict[str, Any]]:
        if not self._log_path.exists():
            return []
        entries: list[dict[str, Any]] = []
        for raw in self._log_path.read_text().strip().split("\n"):
            line = raw.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries

    def _aggregate_patterns(
        self,
        entries: list[dict[str, Any]],
        min_occurrences: int,
        min_confidence: float,
    ) -> list[CorrectionPattern]:
        """Group entries by pattern_hash and compute aggregates."""
        groups: dict[str, list[dict[str, Any]]] = {}
        for e in entries:
            h = e.get("pattern_hash", "")
            if not h:
                continue
            groups.setdefault(h, []).append(e)

        patterns: list[CorrectionPattern] = []
        for h, group in groups.items():
            if len(group) < min_occurrences:
                continue

            value_pairs: dict[tuple[str, str], int] = {}
            for e in group:
                pair = (e.get("old_value", ""), e.get("new_value", ""))
                value_pairs[pair] = value_pairs.get(pair, 0) + 1
            most_common_count = max(value_pairs.values()) if value_pairs else 0
            confidence = most_common_count / len(group) if group else 0.0

            if confidence < min_confidence:
                continue

            most_common_pair = max(value_pairs, key=lambda k: value_pairs[k])

            timestamps = [e.get("timestamp", "") for e in group if e.get("timestamp")]
            first = group[0]

            patterns.append(
                CorrectionPattern(
                    agent=first.get("agent", ""),
                    pattern_hash=h,
                    element_tag=first.get("element_tag", ""),
                    attribute=first.get("attribute", ""),
                    change_type=first.get("change_type", ""),
                    input_snippet=most_common_pair[0],
                    output_snippet=most_common_pair[1],
                    occurrences=len(group),
                    first_seen=datetime.fromisoformat(min(timestamps))
                    if timestamps
                    else datetime.now(UTC),
                    last_seen=datetime.fromisoformat(max(timestamps))
                    if timestamps
                    else datetime.now(UTC),
                    confidence=round(confidence, 4),
                )
            )

        patterns.sort(key=lambda p: p.occurrences, reverse=True)
        return patterns

    def _generate_code_snippet(self, p: CorrectionPattern) -> str:
        """Generate a human-readable Python snippet for a converter rule."""
        if p.change_type == "property_changed":
            css_prop = p.attribute.removeprefix("style.")
            return (
                f"# In converter.py — {p.agent} correction\n"
                f"# Change '{css_prop}' from '{p.input_snippet}' to '{p.output_snippet}' on <{p.element_tag}>\n"
                f"if element.tag == '{p.element_tag}' and '{css_prop}' in style:\n"
                f"    style['{css_prop}'] = '{p.output_snippet}'  # {p.occurrences}x by {p.agent}"
            )
        if p.change_type == "property_added":
            css_prop = p.attribute.removeprefix("style.")
            return (
                f"# In converter.py — {p.agent} correction\n"
                f"# Add '{css_prop}: {p.output_snippet}' to <{p.element_tag}>\n"
                f"if element.tag == '{p.element_tag}' and '{css_prop}' not in style:\n"
                f"    style['{css_prop}'] = '{p.output_snippet}'  # {p.occurrences}x by {p.agent}"
            )
        if p.change_type == "attribute_added":
            return (
                f"# In converter.py — {p.agent} correction\n"
                f'# Add {p.attribute}="{p.output_snippet}" to <{p.element_tag}>\n'
                f"if element.tag == '{p.element_tag}':\n"
                f"    element.set('{p.attribute}', '{p.output_snippet}')  # {p.occurrences}x by {p.agent}"
            )
        return (
            f"# In converter.py — {p.agent} correction\n"
            f"# {p.change_type} on <{p.element_tag}> {p.attribute}\n"
            f"# Input: {p.input_snippet}\n"
            f"# Output: {p.output_snippet}\n"
            f"# Occurrences: {p.occurrences}, confidence: {p.confidence}"
        )

    def _load_rule_statuses(self) -> dict[str, str]:
        if not self._rules_path.exists():
            return {}
        try:
            data = json.loads(self._rules_path.read_text())
            result: dict[str, str] = data.get("statuses", {})
            return result
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_rule_statuses(self, statuses: dict[str, str]) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._rules_path.write_text(json.dumps({"statuses": statuses}, indent=2) + "\n")


__all__ = [
    "ConverterRuleSuggestion",
    "ConverterRuleSuggestionResponse",
    "CorrectionDiff",
    "CorrectionPattern",
    "CorrectionPatternResponse",
    "CorrectionTracker",
    "RuleStatus",
    "extract_correction_diffs",
]
