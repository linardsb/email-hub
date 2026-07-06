"""Tests for Phase 53.5 — standalone VECTOR/LINE recovery.

Corpus reality (structure.json audit, 2026-07-06): the 6 fixture cases carry
exactly 9 standalone vectors, ALL zero-area ``mj-divider`` LINEs (case 5: 2
stroke-less; case 8: 1 @ #373737/1px; case 9: 2 @ #545454/2px; case 10: 2 @
#C7CCCF/1px). NO icon/logomark vectors exist in the corpus — the rasterize
half below is covered by synthetic trees ONLY; the divider half additionally
regresses through cases 8/9/10 baselines.
"""

from __future__ import annotations

from app.design_sync.component_matcher import (
    _build_token_overrides,
    _derive_image_alt,
)
from app.design_sync.component_renderer import ComponentRenderer
from app.design_sync.converter_service import DesignConverterService
from app.design_sync.email_design_document import EmailDesignDocument
from app.design_sync.figma.layout_analyzer import (
    EmailSection,
    EmailSectionType,
    ImagePlaceholder,
    _rasterizable_vector,
    _walk_for_images,
    _zero_area_vector_stroke,
    analyze_layout,
)
from app.design_sync.protocol import (
    DesignFileStructure,
    DesignNode,
    DesignNodeType,
    ExtractedTokens,
)
from app.design_sync.tests.conftest import make_design_node, make_file_structure

# ── shared builders ──


def _divider_line(stroke: str | None = "#545454", weight: float | None = 2.0) -> DesignNode:
    return make_design_node(
        id="line-1",
        name="mj-divider",
        type=DesignNodeType.VECTOR,
        width=640.0,
        height=0.0,
        stroke_color=stroke,
        stroke_weight=weight,
    )


def _icon_vector(id: str = "icon-1", size: float = 24.0) -> DesignNode:
    return make_design_node(
        id=id,
        name="Vector 3",
        type=DesignNodeType.VECTOR,
        width=size,
        height=size,
    )


# ── zero-area LINE → divider stroke ──


def test_zero_area_vector_stroke_found() -> None:
    frame = make_design_node(id="f", name="mj-divider-Frame", children=[_divider_line()])
    assert _zero_area_vector_stroke(frame) == ("#545454", 2.0)


def test_zero_area_vector_stroke_ignores_strokeless() -> None:
    """Case-5 shape: zero-height LINEs with no stroke carry nothing to adopt."""
    frame = make_design_node(id="f", name="mj-divider-Frame", children=[_divider_line(stroke=None)])
    assert _zero_area_vector_stroke(frame) is None


def test_zero_area_vector_stroke_ignores_real_area_vectors() -> None:
    frame = make_design_node(id="f", children=[_icon_vector()])
    assert _zero_area_vector_stroke(frame) is None


def test_analyze_layout_divider_adopts_line_stroke() -> None:
    divider = make_design_node(
        id="sec-div",
        name="mj-divider-Frame",
        height=24.0,
        children=[_divider_line()],
    )
    other = make_design_node(id="sec-other", name="content", height=100.0)
    layout = analyze_layout(make_file_structure(divider, other))
    by_id = {s.node_id: s for s in layout.sections}
    assert by_id["sec-div"].section_type == EmailSectionType.DIVIDER
    assert by_id["sec-div"].stroke_color == "#545454"
    assert by_id["sec-div"].stroke_weight == 2.0


def test_analyze_layout_non_divider_does_not_adopt() -> None:
    """The lift is DIVIDER-scoped — a content frame keeps its own (empty) stroke."""
    content = make_design_node(
        id="sec-c",
        name="product-content",
        height=100.0,
        children=[
            _divider_line(),
            make_design_node(id="t1", type=DesignNodeType.TEXT, text_content="Body", height=40.0),
        ],
    )
    other = make_design_node(id="sec-other", name="hero", height=100.0)
    layout = analyze_layout(make_file_structure(content, other))
    section = next(s for s in layout.sections if s.node_id == "sec-c")
    assert section.stroke_color is None


# ── non-zero-area vectors → rasterize via node export ──


def test_rasterizable_vector_bounds() -> None:
    assert _rasterizable_vector(_icon_vector(size=24.0)) is True
    assert _rasterizable_vector(_icon_vector(size=7.0)) is False
    assert _rasterizable_vector(_divider_line()) is False
    hidden = make_design_node(
        id="h", type=DesignNodeType.VECTOR, width=24.0, height=24.0, visible=False
    )
    assert _rasterizable_vector(hidden) is False


def test_walk_for_images_collects_icon_vector() -> None:
    frame = make_design_node(id="f", children=[_icon_vector()])
    results: list[ImagePlaceholder] = []
    _walk_for_images(frame, results)
    assert len(results) == 1
    assert results[0].node_id == "icon-1"
    assert results[0].export_node_id == "icon-1"
    assert results[0].width == 24.0


def test_walk_for_images_skips_vector_inside_imaged_frame() -> None:
    """A vector under a bg-image frame is baked into the frame's export."""
    imaged = make_design_node(id="bg-frame", image_ref="ref-1", children=[_icon_vector(id="baked")])
    results: list[ImagePlaceholder] = []
    _walk_for_images(imaged, results)
    assert [r.node_id for r in results] == ["bg-frame"]


def test_walk_for_images_skips_zero_area_and_artifacts() -> None:
    frame = make_design_node(
        id="f",
        children=[_divider_line(), _icon_vector(id="tiny", size=4.0)],
    )
    results: list[ImagePlaceholder] = []
    _walk_for_images(frame, results)
    assert results == []


def test_vector_alt_derivation_is_gate_clean() -> None:
    """Figma vector layer names ('Vector 3') must not leak into alt text."""
    placeholder = ImagePlaceholder(node_id="icon-1", node_name="Vector 3")
    assert _derive_image_alt(placeholder) == "Content image"


# ── matcher + renderer: divider border threading ──


def _divider_section(**overrides: object) -> EmailSection:
    base: dict[str, object] = {
        "section_type": EmailSectionType.DIVIDER,
        "node_id": "sec-div",
        "node_name": "mj-divider-Frame",
        "stroke_color": "#545454",
        "stroke_weight": 2.0,
    }
    base.update(overrides)
    return EmailSection(**base)  # type: ignore[arg-type]


def test_divider_override_emitted() -> None:
    overrides = _build_token_overrides(_divider_section())
    values = {(o.css_property, o.target_class): o.value for o in overrides}
    assert values[("border-top", "_divider")] == "2px solid #545454"


def test_divider_override_defaults_weight_to_1px() -> None:
    overrides = _build_token_overrides(_divider_section(stroke_weight=None))
    values = {(o.css_property, o.target_class): o.value for o in overrides}
    assert values[("border-top", "_divider")] == "1px solid #545454"


def test_divider_override_floors_subpixel_weight_to_1px() -> None:
    """A 0.5px design stroke must not format as an invisible '0px solid'."""
    overrides = _build_token_overrides(_divider_section(stroke_weight=0.5))
    values = {(o.css_property, o.target_class): o.value for o in overrides}
    assert values[("border-top", "_divider")] == "1px solid #545454"


def test_divider_override_requires_stroke_and_divider_type() -> None:
    assert not any(
        o.target_class == "_divider"
        for o in _build_token_overrides(_divider_section(stroke_color=None))
    )
    assert not any(
        o.target_class == "_divider"
        for o in _build_token_overrides(_divider_section(section_type=EmailSectionType.CONTENT))
    )
    # Non-hex stroke (CSS injection guard) never reaches the override.
    assert not any(
        o.target_class == "_divider"
        for o in _build_token_overrides(_divider_section(stroke_color="red;}"))
    )


def test_renderer_replaces_divider_border() -> None:
    renderer = ComponentRenderer(container_width=600)
    html_in = (
        '<td data-slot="divider_style" style="padding:16px 24px;">'
        '<div class="divider-line" style="border-top:1px solid #e0e0e0;'
        'font-size:1px;line-height:1px;">&nbsp;</div></td>'
    )
    out = renderer._replace_divider_border(html_in, "2px solid #545454")
    assert "border-top:2px solid #545454;" in out
    assert "#e0e0e0" not in out


def test_renderer_divider_noop_without_divider_line_class() -> None:
    renderer = ComponentRenderer(container_width=600)
    html_in = '<div class="other" style="border-top:1px solid #e0e0e0;">x</div>'
    assert renderer._replace_divider_border(html_in, "2px solid #545454") == html_in


# ── end-to-end ──


def _divider_structure() -> DesignFileStructure:
    divider = make_design_node(
        id="sec-div",
        name="mj-divider-Frame",
        height=24.0,
        y=100.0,
        children=[_divider_line()],
    )
    text = make_design_node(
        id="sec-txt",
        name="content",
        height=80.0,
        y=200.0,
        children=[
            make_design_node(
                id="t1",
                type=DesignNodeType.TEXT,
                text_content="Below the rule",
                height=40.0,
            )
        ],
    )
    return make_file_structure(divider, text)


def test_convert_document_renders_divider_stroke_end_to_end() -> None:
    document = EmailDesignDocument.from_legacy(_divider_structure(), ExtractedTokens())
    assert document.sections[0].stroke_color == "#545454"
    result = DesignConverterService().convert_document(document)
    assert "border-top:2px solid #545454" in result.html
    assert "1px solid #e0e0e0" not in result.html
