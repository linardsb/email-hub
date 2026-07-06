"""Tests for Phase 53.3 — never-parsed ingest render (53.3b/c/d/a).

Corpus reality (raw_figma.json audit, 2026-07-06): the 6 fixture cases carry
ZERO gradients, zero non-FILL scaleModes, zero rotations beyond float noise,
zero effects arrays, and only NORMAL/PASS_THROUGH blend modes. Synthetic trees
are therefore the ONLY coverage for every sub-item here — the fixture corpus
cannot exercise this code and its baselines must stay byte-identical.
"""

from __future__ import annotations

from typing import cast

import pytest

from app.design_sync.component_matcher import (
    _build_token_overrides,
    _linear_gradient_css,
)
from app.design_sync.component_renderer import ComponentRenderer
from app.design_sync.converter_service import DesignConverterService
from app.design_sync.email_design_document import EmailDesignDocument
from app.design_sync.figma.layout_analyzer import (
    EmailSection,
    EmailSectionType,
    ImagePlaceholder,
    _collect_effects_summary,
    _crop_export_id,
    _is_reproducible,
    _unreproducible_reason,
    _walk_for_images,
    analyze_layout,
)
from app.design_sync.figma.raw_types import RawFigmaNode
from app.design_sync.figma.service import _parse_effects_summary, _parse_visual_props
from app.design_sync.protocol import (
    DesignFileStructure,
    DesignNodeType,
    ExtractedGradient,
    ExtractedTokens,
)
from app.design_sync.tests.conftest import make_design_node, make_file_structure

# ── shared builders ──


def _gradient(node_id: str | None = "frame-grad") -> ExtractedGradient:
    return ExtractedGradient(
        name="hero gradient",
        type="linear",
        angle=90.0,
        stops=(("#112233", 0.0), ("#aabbcc", 1.0)),
        fallback_hex="#5e6f80",
        node_id=node_id,
    )


def _tokens_with_gradient(node_id: str | None = "frame-grad") -> ExtractedTokens:
    return ExtractedTokens(gradients=[_gradient(node_id)])


def _gradient_frame(frame_id: str = "frame-grad") -> DesignFileStructure:
    """One section frame with a text child; the frame id carries the gradient."""
    text = make_design_node(
        id="txt-1",
        name="Heading",
        type=DesignNodeType.TEXT,
        width=400.0,
        height=40.0,
        text_content="Gradient hero",
    )
    frame = make_design_node(id=frame_id, name="hero", children=[text], height=300.0)
    return make_file_structure(frame)


# ── 53.3b — per-node gradient reattach ──


def test_analyze_layout_attaches_gradient_ref() -> None:
    layout = analyze_layout(_gradient_frame(), gradient_node_ids=frozenset({"frame-grad"}))
    assert layout.sections, "expected one section"
    assert layout.sections[0].gradient_ref == "frame-grad"


def test_analyze_layout_no_gradient_ref_without_match() -> None:
    layout = analyze_layout(_gradient_frame(), gradient_node_ids=frozenset({"other-node"}))
    assert layout.sections[0].gradient_ref is None


def test_from_legacy_threads_gradient_node_ids() -> None:
    """from_legacy → analyze_layout → DocumentSection: the full attach path."""
    document = EmailDesignDocument.from_legacy(_gradient_frame(), _tokens_with_gradient())
    assert document.sections, "expected one section"
    assert document.sections[0].gradient_ref == "frame-grad"
    # And the document tokens keep the join key.
    assert document.tokens.gradients[0].node_id == "frame-grad"


def test_linear_gradient_css_emits_stops_and_angle() -> None:
    css = _linear_gradient_css(_gradient())
    assert css == "linear-gradient(90deg, #112233 0%, #aabbcc 100%)"


def test_linear_gradient_css_radial_returns_none() -> None:
    radial = ExtractedGradient(
        name="r",
        type="radial",
        angle=0.0,
        stops=(("#112233", 0.0), ("#aabbcc", 1.0)),
        fallback_hex="#5e6f80",
        node_id="n",
    )
    assert _linear_gradient_css(radial) is None


def test_linear_gradient_css_rejects_non_hex_stop() -> None:
    evil = ExtractedGradient(
        name="e",
        type="linear",
        angle=0.0,
        stops=(("url(javascript:1)", 0.0), ("#aabbcc", 1.0)),
        fallback_hex="#5e6f80",
        node_id="n",
    )
    assert _linear_gradient_css(evil) is None


def _section_with_gradient(**overrides: object) -> EmailSection:
    base: dict[str, object] = {
        "section_type": EmailSectionType.HERO,
        "node_id": "frame-grad",
        "node_name": "hero",
        "gradient_ref": "frame-grad",
    }
    base.update(overrides)
    return EmailSection(**base)  # type: ignore[arg-type]


def test_token_overrides_emit_gradient_and_fallback() -> None:
    overrides = _build_token_overrides(_section_with_gradient(), gradients=[_gradient()])
    by_prop = {(o.css_property, o.target_class): o.value for o in overrides}
    assert by_prop[("background-image", "_outer")] == (
        "linear-gradient(90deg, #112233 0%, #aabbcc 100%)"
    )
    # No solid fill on the section → the gradient's midpoint becomes the
    # non-supporting-client (and MSO bgcolor) fallback.
    assert by_prop[("background-color", "_outer")] == "#5e6f80"


def test_token_overrides_gradient_keeps_existing_solid() -> None:
    overrides = _build_token_overrides(
        _section_with_gradient(bg_color="#123456"), gradients=[_gradient()]
    )
    solid = [o for o in overrides if o.css_property == "background-color"]
    assert [o.value for o in solid] == ["#123456"], "fallback must not shadow the design fill"
    assert any(o.css_property == "background-image" for o in overrides)


def test_token_overrides_no_gradient_without_ref() -> None:
    overrides = _build_token_overrides(
        _section_with_gradient(gradient_ref=None), gradients=[_gradient()]
    )
    assert not any(o.css_property == "background-image" for o in overrides)


def test_renderer_upserts_background_image_on_outer_class() -> None:
    renderer = ComponentRenderer(container_width=600)
    html_in = (
        '<table role="presentation" width="100%" class="_outer" '
        'style="background-color:#5e6f80;"><tr><td>x</td></tr></table>'
    )
    out = renderer._apply_outer_bg_image(
        html_in, "linear-gradient(90deg, #112233 0%, #aabbcc 100%)"
    )
    assert "background-image:linear-gradient(90deg, #112233 0%, #aabbcc 100%);" in out
    assert out.count("background-image:") == 1


def test_renderer_upserts_background_image_first_table_without_outer() -> None:
    renderer = ComponentRenderer(container_width=600)
    html_in = (
        '<table role="presentation" width="600"><tr><td>ghost</td></tr></table>'
        '<table role="presentation" width="100%" style="border-collapse:collapse;">'
        "<tr><td>x</td></tr></table>"
    )
    out = renderer._apply_outer_bg_image(html_in, "linear-gradient(0deg, #112233 0%, #aabbcc 100%)")
    ghost, _, visible = out.partition('width="100%"')
    assert "background-image:" not in ghost, "fixed-width MSO ghost must be skipped"
    assert "background-image:linear-gradient(0deg" in visible


def test_convert_document_renders_gradient_end_to_end() -> None:
    document = EmailDesignDocument.from_legacy(_gradient_frame(), _tokens_with_gradient())
    result = DesignConverterService().convert_document(document)
    # Hexes are canonicalised to uppercase by token validation.
    assert "background-image:linear-gradient(90deg, #112233 0%, #AABBCC 100%)" in result.html
    # Non-supporting clients keep the solid midpoint fallback.
    assert "#5E6F80" in result.html


# ── 53.3c — image crop via frame export ──


def _raw_image_fill_node(scale_mode: str | None) -> RawFigmaNode:
    fill: dict[str, object] = {"type": "IMAGE", "imageRef": "ref-1"}
    if scale_mode is not None:
        fill["scaleMode"] = scale_mode
    return cast(
        "RawFigmaNode",
        {"id": "1:1", "name": "photo", "type": "RECTANGLE", "fills": [fill]},
    )


def test_parse_visual_props_captures_scale_mode() -> None:
    visual = _parse_visual_props(_raw_image_fill_node("FIT"), DesignNodeType.VECTOR, 1.0)
    assert visual.resolved_node_type == DesignNodeType.IMAGE
    assert visual.scale_mode == "FIT"
    assert visual.image_ref == "ref-1"


def test_parse_visual_props_scale_mode_none_without_image_fill() -> None:
    visual = _parse_visual_props(
        {"id": "1:2", "name": "box", "type": "RECTANGLE", "fills": []},
        DesignNodeType.VECTOR,
        1.0,
    )
    assert visual.scale_mode is None


def test_crop_export_id_only_for_non_fill_modes() -> None:
    cropped = make_design_node(id="img-c", type=DesignNodeType.IMAGE, scale_mode="CROP")
    filled = make_design_node(id="img-f", type=DesignNodeType.IMAGE, scale_mode="FILL")
    unset = make_design_node(id="img-n", type=DesignNodeType.IMAGE)
    assert _crop_export_id(cropped) == "img-c"
    assert _crop_export_id(filled) is None
    assert _crop_export_id(unset) is None


def test_walk_for_images_cropped_image_exports_itself() -> None:
    node = make_design_node(id="img-1", name="photo", type=DesignNodeType.IMAGE, scale_mode="CROP")
    results: list[ImagePlaceholder] = []
    _walk_for_images(node, results)
    assert results[0].export_node_id == "img-1"


def test_walk_for_images_cropped_frame_bg_exports_itself() -> None:
    frame = make_design_node(id="frame-1", name="hero-bg", image_ref="ref-9", scale_mode="TILE")
    results: list[ImagePlaceholder] = []
    _walk_for_images(frame, results)
    assert results[0].is_background is True
    assert results[0].export_node_id == "frame-1"


def test_walk_for_images_fill_default_keeps_no_export_id() -> None:
    node = make_design_node(id="img-2", name="photo", type=DesignNodeType.IMAGE)
    results: list[ImagePlaceholder] = []
    _walk_for_images(node, results)
    assert results[0].export_node_id is None


# ── 53.3d — reproducibility classifier + frame-export fallback ──


def test_rotation_beyond_tolerance_is_unreproducible() -> None:
    node = make_design_node(rotation=15.0)
    assert _is_reproducible(node) is False
    reason = _unreproducible_reason(node)
    assert reason is not None and reason.startswith("rotation:")


def test_rotation_within_tolerance_is_reproducible() -> None:
    assert _is_reproducible(make_design_node(rotation=0.5)) is True
    assert _is_reproducible(make_design_node(rotation=None)) is True


def test_overlapping_siblings_are_unreproducible() -> None:
    a = make_design_node(id="a", x=0.0, y=0.0, width=100.0, height=100.0)
    b = make_design_node(id="b", x=50.0, y=50.0, width=100.0, height=100.0)
    parent = make_design_node(id="p", children=[a, b], width=600.0, height=400.0)
    reason = _unreproducible_reason(parent)
    assert reason is not None and reason.startswith("overlap:")


def test_disjoint_siblings_are_reproducible() -> None:
    a = make_design_node(id="a", x=0.0, y=0.0, width=100.0, height=100.0)
    b = make_design_node(id="b", x=0.0, y=120.0, width=100.0, height=100.0)
    parent = make_design_node(id="p", children=[a, b], width=600.0, height=400.0)
    assert _is_reproducible(parent) is True


def test_backdrop_child_is_not_an_overlap() -> None:
    """Text over a near-parent-sized image (hero pattern) must NOT raster."""
    backdrop = make_design_node(id="bg", x=0.0, y=0.0, width=600.0, height=400.0)
    text = make_design_node(
        id="t", type=DesignNodeType.TEXT, x=100.0, y=150.0, width=400.0, height=60.0
    )
    parent = make_design_node(id="p", children=[backdrop, text], width=600.0, height=400.0)
    assert _is_reproducible(parent) is True


def test_invisible_subtree_is_ignored() -> None:
    hidden = make_design_node(id="h", rotation=45.0, visible=False)
    parent = make_design_node(id="p", children=[hidden])
    assert _is_reproducible(parent) is True


def _rotated_structure() -> DesignFileStructure:
    rotated = make_design_node(
        id="rot-1",
        name="badge",
        rotation=30.0,
        x=10.0,
        y=10.0,
        width=200.0,
        height=100.0,
    )
    text = make_design_node(
        id="txt-9",
        name="label",
        type=DesignNodeType.TEXT,
        text_content="Rotated content",
        x=10.0,
        y=200.0,
        width=300.0,
        height=40.0,
    )
    frame = make_design_node(id="sec-rot", name="content", children=[rotated, text])
    return make_file_structure(frame)


def test_frame_export_fallback_flag_on_rasters_section(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings().design_sync, "frame_export_fallback_enabled", True)
    layout = analyze_layout(_rotated_structure())
    section = layout.sections[0]
    assert section.texts == [], "raster fallback must replace content extraction"
    assert len(section.images) == 1
    assert section.images[0].export_node_id == "sec-rot"
    assert section.images[0].is_background is False


def test_frame_export_fallback_default_off_extracts_normally() -> None:
    layout = analyze_layout(_rotated_structure())
    section = layout.sections[0]
    assert any(t.content == "Rotated content" for t in section.texts)
    assert not (len(section.images) == 1 and section.images[0].export_node_id == "sec-rot")


# ── 53.3a — effects/blendMode capture + warning ──


def test_parse_effects_summary_counts_and_types() -> None:
    raw = cast(
        "RawFigmaNode",
        {
            "effects": [
                {"type": "DROP_SHADOW", "visible": True},
                {"type": "LAYER_BLUR"},
                {"type": "INNER_SHADOW", "visible": False},
            ],
            "blendMode": "MULTIPLY",
        },
    )
    assert _parse_effects_summary(raw) == "3:BLEND_MULTIPLY,DROP_SHADOW,LAYER_BLUR"


def test_parse_effects_summary_ignores_default_blends() -> None:
    assert _parse_effects_summary(cast("RawFigmaNode", {"blendMode": "NORMAL"})) is None
    assert (
        _parse_effects_summary(cast("RawFigmaNode", {"blendMode": "PASS_THROUGH", "effects": []}))
        is None
    )


def test_collect_effects_summary_aggregates_subtree() -> None:
    child_a = make_design_node(id="a", effects_summary="2:DROP_SHADOW")
    child_b = make_design_node(id="b", effects_summary="1:LAYER_BLUR")
    parent = make_design_node(id="p", children=[child_a, child_b])
    assert _collect_effects_summary(parent) == "3:DROP_SHADOW,LAYER_BLUR"


def test_collect_effects_summary_none_when_clean() -> None:
    assert _collect_effects_summary(make_design_node(id="clean")) is None


def test_convert_document_warns_on_dropped_effects() -> None:
    shadowed = make_design_node(
        id="fx-1",
        name="card",
        effects_summary="1:DROP_SHADOW",
        children=[
            make_design_node(
                id="fx-txt",
                type=DesignNodeType.TEXT,
                text_content="Shadowed card",
                width=300.0,
                height=40.0,
            )
        ],
    )
    structure = make_file_structure(shadowed)
    document = EmailDesignDocument.from_legacy(structure, ExtractedTokens())
    assert document.sections[0].effects_summary == "1:DROP_SHADOW"
    result = DesignConverterService().convert_document(document)
    dropped = [w for w in result.warnings if "DROP_SHADOW" in w]
    assert dropped, f"expected an effects_dropped warning, got: {result.warnings}"
