"""Tests for Phase 52.4 — typography overrides from text-node attributes.

Two layers, mirroring ``test_text_align_override.py``:

* matcher emission (``_build_token_overrides``) — font-weight / line-height /
  letter-spacing / text-transform / text-decoration overrides are produced for
  the first heading/body text declaring each, with numeric coercion and enum
  allowlists;
* renderer application (``ComponentRenderer._apply_token_overrides``) — each
  override reaches the HTML (replace existing OR inject when absent), with value
  validation and double-inject safety.

``text-transform`` / ``text-decoration`` are not populated by any of the six
``data/debug`` fixtures (confirmed by discovery probe), so they are proven
synthetically here rather than via fixture conversion.
"""

from __future__ import annotations

from app.design_sync.component_matcher import (
    TokenOverride,
    _build_token_overrides,
)
from app.design_sync.component_renderer import ComponentRenderer
from app.design_sync.figma.layout_analyzer import (
    ColumnLayout,
    EmailSection,
    EmailSectionType,
    TextBlock,
)


def _section(*, texts: list[TextBlock]) -> EmailSection:
    return EmailSection(
        section_type=EmailSectionType.CONTENT,
        node_id="s1",
        node_name="section",
        column_layout=ColumnLayout.SINGLE,
        column_count=1,
        texts=texts,
    )


# --- Matcher emission -----------------------------------------------------


def test_heading_font_weight_emitted() -> None:
    section = _section(
        texts=[TextBlock(node_id="t1", content="Hi", is_heading=True, font_weight=800)]
    )
    overrides = _build_token_overrides(section)
    assert TokenOverride("font-weight", "_heading", "800") in overrides


def test_body_font_weight_emitted() -> None:
    section = _section(
        texts=[TextBlock(node_id="t1", content="Body", is_heading=False, font_weight=400)]
    )
    overrides = _build_token_overrides(section)
    assert TokenOverride("font-weight", "_body", "400") in overrides


def test_heading_line_height_rounded_to_px() -> None:
    """Fractional design line-height (63.28125) rounds to an integer px value."""
    section = _section(
        texts=[TextBlock(node_id="t1", content="Hi", is_heading=True, line_height=63.28125)]
    )
    overrides = _build_token_overrides(section)
    assert TokenOverride("line-height", "_heading", "63px") in overrides


def test_heading_letter_spacing_negative_two_decimals() -> None:
    """Negative tracking (-0.3199…) is coerced to two decimals (-0.32px)."""
    section = _section(
        texts=[
            TextBlock(
                node_id="t1",
                content="Hi",
                is_heading=True,
                letter_spacing=-0.3199999928474426,
            )
        ]
    )
    overrides = _build_token_overrides(section)
    assert TokenOverride("letter-spacing", "_heading", "-0.32px") in overrides


def test_zero_letter_spacing_skipped() -> None:
    """letter-spacing:0 is the typographic no-op default and is not emitted."""
    section = _section(
        texts=[TextBlock(node_id="t1", content="Hi", is_heading=True, letter_spacing=0.0)]
    )
    overrides = _build_token_overrides(section)
    assert not any(o.css_property == "letter-spacing" for o in overrides)


def test_text_transform_allowlist_accepts_valid() -> None:
    section = _section(
        texts=[TextBlock(node_id="t1", content="Hi", is_heading=True, text_transform="UPPERCASE")]
    )
    overrides = _build_token_overrides(section)
    assert TokenOverride("text-transform", "_heading", "uppercase") in overrides


def test_text_transform_invalid_dropped() -> None:
    section = _section(
        texts=[TextBlock(node_id="t1", content="Hi", is_heading=True, text_transform="slanty")]
    )
    overrides = _build_token_overrides(section)
    assert not any(o.css_property == "text-transform" for o in overrides)


def test_text_decoration_allowlist_accepts_valid() -> None:
    section = _section(
        texts=[
            TextBlock(node_id="t1", content="Body", is_heading=False, text_decoration="underline")
        ]
    )
    overrides = _build_token_overrides(section)
    assert TokenOverride("text-decoration", "_body", "underline") in overrides


def test_text_decoration_invalid_dropped() -> None:
    section = _section(
        texts=[TextBlock(node_id="t1", content="Body", is_heading=False, text_decoration="blink")]
    )
    overrides = _build_token_overrides(section)
    assert not any(o.css_property == "text-decoration" for o in overrides)


def test_no_typography_emission_when_unset() -> None:
    section = _section(texts=[TextBlock(node_id="t1", content="Hi", is_heading=True)])
    overrides = _build_token_overrides(section)
    typo_props = {
        "font-weight",
        "line-height",
        "letter-spacing",
        "text-transform",
        "text-decoration",
    }
    assert not any(o.css_property in typo_props for o in overrides)


# --- Renderer application -------------------------------------------------

# ``_apply_token_overrides`` is a pure string transform — no template loading.
_RENDERER = ComponentRenderer(container_width=600)


def test_renderer_replaces_existing_heading_font_weight() -> None:
    html_in = (
        '<td data-slot="heading" class="textblock-heading" '
        'style="font-size:24px; font-weight: bold; color:#333;">Hi</td>'
    )
    out = _RENDERER._apply_token_overrides(
        html_in, [TokenOverride("font-weight", "_heading", "800")]
    )
    assert "font-weight:800" in out
    assert "font-weight: bold" not in out
    assert out.count("font-weight:") == 1


def test_renderer_injects_missing_body_font_weight() -> None:
    """Body cells in the seeds carry no font-weight — it must be injected."""
    html_in = (
        '<td data-slot="body" class="textblock-body" style="font-size:16px; color:#555;">Body</td>'
    )
    out = _RENDERER._apply_token_overrides(html_in, [TokenOverride("font-weight", "_body", "400")])
    assert "font-weight:400" in out
    assert out.count("font-weight:") == 1


def test_renderer_replaces_line_height_and_preserves_mso_rule() -> None:
    """The seed's unitless ratio is replaced with px; mso-line-height-rule stays."""
    html_in = (
        '<td data-slot="heading" class="textblock-heading" '
        'style="line-height: 1.3; mso-line-height-rule: exactly;">Hi</td>'
    )
    out = _RENDERER._apply_token_overrides(
        html_in, [TokenOverride("line-height", "_heading", "63px")]
    )
    assert "line-height:63px" in out
    assert "line-height: 1.3" not in out
    assert "mso-line-height-rule: exactly" in out
    # Only the standalone line-height was rewritten, not the mso rule.
    assert out.count("line-height:63px") == 1


def test_renderer_injects_missing_letter_spacing() -> None:
    html_in = (
        '<td data-slot="heading" class="textblock-heading" '
        'style="font-size:24px; color:#333;">Hi</td>'
    )
    out = _RENDERER._apply_token_overrides(
        html_in, [TokenOverride("letter-spacing", "_heading", "-0.32px")]
    )
    assert "letter-spacing:-0.32px" in out
    assert out.count("letter-spacing:") == 1


def test_renderer_injects_text_transform() -> None:
    html_in = (
        '<td data-slot="heading" class="textblock-heading" '
        'style="font-size:24px; color:#333;">Hi</td>'
    )
    out = _RENDERER._apply_token_overrides(
        html_in, [TokenOverride("text-transform", "_heading", "uppercase")]
    )
    assert "text-transform:uppercase" in out
    assert out.count("text-transform:") == 1


def test_renderer_injects_text_decoration_body() -> None:
    html_in = (
        '<td data-slot="body" class="textblock-body" style="font-size:16px; color:#555;">Body</td>'
    )
    out = _RENDERER._apply_token_overrides(
        html_in, [TokenOverride("text-decoration", "_body", "underline")]
    )
    assert "text-decoration:underline" in out
    assert out.count("text-decoration:") == 1


def test_renderer_rejects_injected_font_weight_value() -> None:
    """A weight value carrying a CSS-injection payload is a no-op."""
    html_in = (
        '<td data-slot="heading" class="textblock-heading" '
        'style="font-size:24px; color:#333;">Hi</td>'
    )
    out = _RENDERER._apply_token_overrides(
        html_in, [TokenOverride("font-weight", "_heading", "800;display:none")]
    )
    assert out == html_in
    assert "font-weight" not in out


def test_renderer_rejects_invalid_letter_spacing_unit() -> None:
    html_in = (
        '<td data-slot="heading" class="textblock-heading" '
        'style="font-size:24px; color:#333;">Hi</td>'
    )
    out = _RENDERER._apply_token_overrides(
        html_in, [TokenOverride("letter-spacing", "_heading", "5em;color:red")]
    )
    assert out == html_in
    assert "letter-spacing" not in out


def test_renderer_rejects_invalid_text_transform() -> None:
    html_in = (
        '<td data-slot="heading" class="textblock-heading" '
        'style="font-size:24px; color:#333;">Hi</td>'
    )
    out = _RENDERER._apply_token_overrides(
        html_in, [TokenOverride("text-transform", "_heading", "uppercase;evil")]
    )
    assert out == html_in
    assert "text-transform" not in out


def test_renderer_no_double_inject_when_slot_and_class_match() -> None:
    """A cell matched by both data-slot and class is injected only once."""
    html_in = '<td data-slot="body" class="textblock-body" style="font-size:16px;">Body</td>'
    out = _RENDERER._apply_token_overrides(
        html_in, [TokenOverride("letter-spacing", "_body", "0.50px")]
    )
    assert out.count("letter-spacing:") == 1
