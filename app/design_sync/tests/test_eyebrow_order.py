"""RC-F6 (Phase 53 Track F): eyebrow/kicker order.

A small body-classed text that PRECEDES the first heading in source (tree/y)
order is a kicker/eyebrow. Before F6 the builders bucketed it into the body slot,
which the seed hardcodes BELOW the heading, so the eyebrow rendered under its
headline (maap "New Season Collaboration", Ferrari "FERRARI 849 TESTAROSSA").
F6 emits pre-heading body texts as ``<td data-node-id>`` rows ABOVE the heading
row via the RC-D-prime anchor pattern, preserving per-node typography.
"""

from __future__ import annotations

from app.design_sync.component_matcher import (
    _build_slot_fills,
    match_section,
)
from app.design_sync.component_renderer import ComponentRenderer
from app.design_sync.figma.layout_analyzer import (
    ColumnLayout,
    EmailSection,
    EmailSectionType,
    TextBlock,
)

EYEBROW = "New Season Collaboration"
HEADING = "MAAP x KASK"
PARAGRAPH = "Now live, the collaboration paragraph body copy."


def _eyebrow_section() -> EmailSection:
    """A text-block section whose small red eyebrow precedes the headline in
    source order, followed by the real body paragraph (mirrors maap/Ferrari)."""
    return EmailSection(
        section_type=EmailSectionType.CONTENT,
        node_id="frame_1",
        node_name="Editorial",
        column_layout=ColumnLayout.SINGLE,
        texts=[
            TextBlock(
                node_id="eb1",
                content=EYEBROW,
                font_size=12.0,
                is_heading=False,
                font_family="Courier New",
                font_weight=400,
                line_height=14.0,
                text_color="#DA291C",
                text_align="center",
            ),
            TextBlock(
                node_id="hd1",
                content=HEADING,
                font_size=40.0,
                is_heading=True,
                font_family="Helvetica",
                text_color="#222222",
            ),
            TextBlock(
                node_id="pg1",
                content=PARAGRAPH,
                font_size=16.0,
                is_heading=False,
                font_family="Helvetica",
                text_color="#222222",
            ),
        ],
        # 4-side padding → the _cell override takes the `padding:` shorthand path
        # (mirrors c5/c8); guards that the spliced eyebrow row does not steal it.
        padding_top=16.0,
        padding_right=24.0,
        padding_bottom=16.0,
        padding_left=24.0,
    )


def _render(section: EmailSection) -> str:
    renderer = ComponentRenderer(container_width=600)
    renderer.load()
    match = match_section(section, 0)
    assert match.component_slug == "text-block", match.component_slug
    return renderer.render_section(match).html


def test_eyebrow_renders_above_heading() -> None:
    """RED pre-fix: the eyebrow renders below the heading (in the body slot)."""
    html = _render(_eyebrow_section())
    eyebrow_at = html.index(EYEBROW)
    heading_at = html.index(HEADING)
    assert eyebrow_at < heading_at, (
        f"eyebrow at {eyebrow_at} should precede heading at {heading_at}"
    )


def test_eyebrow_anchor_precedes_heading_slot() -> None:
    """Structural form: the eyebrow's data-node-id anchor sits before the
    heading slot <td>, i.e. as a spliced row above it."""
    html = _render(_eyebrow_section())
    assert 'data-node-id="eb1"' in html
    assert html.index('data-node-id="eb1"') < html.index('data-slot="heading"')


def test_eyebrow_keeps_its_own_typography() -> None:
    """Per-node typography preserved: the eyebrow anchor renders its own red
    color and 12px size, not the heading's or the shared body's."""
    html = _render(_eyebrow_section())
    anchor_start = html.index('data-node-id="eb1"')
    anchor_style = html[anchor_start : html.index(">", anchor_start)]
    assert "#DA291C" in anchor_style
    assert "12.0px" in anchor_style


def test_heading_padding_survives_eyebrow_splice() -> None:
    """The 4-side _cell padding override still lands on the heading <td>, not the
    spliced eyebrow row (longhand padding-bottom dodges the `padding:` shorthand
    replace)."""
    html = _render(_eyebrow_section())
    heading_start = html.index('data-slot="heading"')
    heading_style = html[heading_start : html.index(">", heading_start)]
    assert "padding:16px 24px 16px 24px" in heading_style


def test_pre_heading_text_in_heading_stacked_before_not_body() -> None:
    """Matcher: the eyebrow rides on the heading fill's stacked_before as a
    data-node-id row; the body fill carries only the post-heading paragraph."""
    fills = _build_slot_fills("text-block", _eyebrow_section(), 600)
    heading = next(f for f in fills if f.slot_id == "heading")
    assert 'data-node-id="eb1"' in heading.stacked_before
    assert EYEBROW in heading.stacked_before
    body = next(f for f in fills if f.slot_id == "body")
    assert EYEBROW not in body.value
    assert PARAGRAPH in body.value


def test_heading_first_section_unchanged() -> None:
    """Regression: when the heading comes first (no pre-heading eyebrow), nothing
    is stacked and the single body keeps its plain fill."""
    section = EmailSection(
        section_type=EmailSectionType.CONTENT,
        node_id="frame_2",
        node_name="Normal",
        column_layout=ColumnLayout.SINGLE,
        texts=[
            TextBlock(node_id="h", content="Heading First", font_size=40.0, is_heading=True),
            TextBlock(node_id="b", content="Only body paragraph", font_size=16.0),
        ],
    )
    fills = _build_slot_fills("text-block", section, 600)
    heading = next(f for f in fills if f.slot_id == "heading")
    assert heading.stacked_before == ""
    body = next(f for f in fills if f.slot_id == "body")
    assert body.value == "Only body paragraph"


def test_hero_subtext_before_headline_lifts_above() -> None:
    """Hero symmetry: a body preceding the headline in source order rides the
    headline fill's stacked_before rather than filling the subtext slot below."""
    section = EmailSection(
        section_type=EmailSectionType.HERO,
        node_id="frame_3",
        node_name="Hero",
        column_layout=ColumnLayout.SINGLE,
        texts=[
            TextBlock(node_id="hb", content="Kicker Above", font_size=12.0, is_heading=False),
            TextBlock(node_id="hh", content="Big Headline", font_size=40.0, is_heading=True),
        ],
    )
    fills = _build_slot_fills("hero-block", section, 600)
    headline = next(f for f in fills if f.slot_id == "headline")
    assert 'data-node-id="hb"' in headline.stacked_before
    assert "Kicker Above" in headline.stacked_before
    # The pre-headline kicker must not also fill the subtext slot below.
    subtext = next((f for f in fills if f.slot_id == "subtext"), None)
    assert subtext is None or "Kicker Above" not in subtext.value
