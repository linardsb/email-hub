"""Tests for Gap 11 / Phase 50.6 — text-align override from text-node attribute.

Two layers:
* matcher emission (``_build_token_overrides``) — the override is produced;
* renderer application (``ComponentRenderer._apply_token_overrides``) — the
  override actually reaches the HTML (replace existing OR inject when absent),
  with value validation.
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


def test_heading_left_align() -> None:
    section = _section(
        texts=[TextBlock(node_id="t1", content="Hello", is_heading=True, text_align="LEFT")]
    )
    overrides = _build_token_overrides(section)
    assert TokenOverride("text-align", "_heading", "left") in overrides


def test_heading_right_align() -> None:
    section = _section(
        texts=[TextBlock(node_id="t1", content="Hello", is_heading=True, text_align="RIGHT")]
    )
    overrides = _build_token_overrides(section)
    assert TokenOverride("text-align", "_heading", "right") in overrides


def test_heading_center_align() -> None:
    section = _section(
        texts=[TextBlock(node_id="t1", content="Hello", is_heading=True, text_align="CENTER")]
    )
    overrides = _build_token_overrides(section)
    assert TokenOverride("text-align", "_heading", "center") in overrides


def test_body_align_emitted() -> None:
    section = _section(
        texts=[TextBlock(node_id="t1", content="Body copy", is_heading=False, text_align="LEFT")]
    )
    overrides = _build_token_overrides(section)
    assert TokenOverride("text-align", "_body", "left") in overrides


def test_no_emission_when_unset() -> None:
    section = _section(
        texts=[TextBlock(node_id="t1", content="Hello", is_heading=True, text_align=None)]
    )
    overrides = _build_token_overrides(section)
    assert not any(o.css_property == "text-align" for o in overrides)


def test_unknown_align_value_skipped() -> None:
    section = _section(
        texts=[
            TextBlock(node_id="t1", content="Hello", is_heading=True, text_align="JUSTIFY-FOOBAR")
        ]
    )
    overrides = _build_token_overrides(section)
    assert not any(o.css_property == "text-align" for o in overrides)


# --- Renderer application (Gap 11) ---------------------------------------

# ``_apply_token_overrides`` is a pure string transform — no template loading
# required, so the renderer can be used without ``load()``.
_RENDERER = ComponentRenderer(container_width=600)


def test_renderer_replaces_existing_heading_align() -> None:
    """A heading cell that already declares text-align gets it replaced."""
    html_in = (
        '<td data-slot="heading" class="textblock-heading" '
        'style="font-size:24px; text-align:left; color:#333;">Hi</td>'
    )
    out = _RENDERER._apply_token_overrides(
        html_in, [TokenOverride("text-align", "_heading", "right")]
    )
    assert "text-align:right" in out
    assert "text-align:left" not in out
    # No duplicate declaration despite the cell matching both slot and class.
    assert out.count("text-align:") == 1


def test_renderer_injects_missing_heading_align() -> None:
    """A heading cell without text-align gets one injected into its style."""
    html_in = (
        '<td data-slot="heading" class="textblock-heading" '
        'style="font-size:24px; color:#333;">Hi</td>'
    )
    out = _RENDERER._apply_token_overrides(
        html_in, [TokenOverride("text-align", "_heading", "center")]
    )
    assert "text-align:center" in out
    assert out.count("text-align:") == 1


def test_renderer_injects_missing_body_align() -> None:
    """Mirror of case 7: body cell without text-align gets one injected."""
    html_in = (
        '<td data-slot="body" class="textblock-body" style="font-size:16px; color:#555;">Body</td>'
    )
    out = _RENDERER._apply_token_overrides(html_in, [TokenOverride("text-align", "_body", "right")])
    assert "text-align:right" in out
    assert out.count("text-align:") == 1


def test_renderer_rejects_invalid_align_value() -> None:
    """An out-of-allowlist value is a no-op — nothing injected or replaced."""
    html_in = (
        '<td data-slot="heading" class="textblock-heading" '
        'style="font-size:24px; color:#333;">Hi</td>'
    )
    out = _RENDERER._apply_token_overrides(
        html_in, [TokenOverride("text-align", "_heading", "right;display:none")]
    )
    assert out == html_in
    assert "text-align" not in out
