"""Tests for FRAME-tree rule predicates (Phase 50.5 — Rules 7, 8, 10, 11)."""

from __future__ import annotations

import pytest

from app.design_sync.component_matcher import (
    _build_token_overrides,
)
from app.design_sync.figma.layout_analyzer import (
    ButtonElement,
    ColumnLayout,
    EmailSection,
    EmailSectionType,
    ImagePlaceholder,
    TextBlock,
)
from app.design_sync.frame_rules import (
    CornerRadiusSpec,
    rule_8_corner_radius,
    rule_10_image_corner_radii,
    rule_11_card_width_from_dominant_image,
)
from app.design_sync.protocol import DesignNode, DesignNodeType


def _node(
    *,
    x: float = 0.0,
    y: float = 0.0,
    width: float = 100.0,
    height: float = 40.0,
    node_id: str = "n1",
    name: str = "node",
    node_type: DesignNodeType = DesignNodeType.FRAME,
    corner_radius: float | None = None,
    corner_radii: tuple[float, ...] | None = None,
    children: list[DesignNode] | None = None,
    image_ref: str | None = None,
) -> DesignNode:
    return DesignNode(
        id=node_id,
        name=name,
        type=node_type,
        children=children or [],
        x=x,
        y=y,
        width=width,
        height=height,
        corner_radius=corner_radius,
        corner_radii=corner_radii,
        image_ref=image_ref,
    )


def _section(
    *,
    inner_card_fixed_width: int | None = None,
    images: list[ImagePlaceholder] | None = None,
    texts: list[TextBlock] | None = None,
    buttons: list[ButtonElement] | None = None,
    inner_bg: str | None = None,
) -> EmailSection:
    return EmailSection(
        section_type=EmailSectionType.CONTENT,
        node_id="s1",
        node_name="section",
        column_layout=ColumnLayout.SINGLE,
        column_count=1,
        texts=texts or [],
        images=images or [],
        buttons=buttons or [],
        inner_bg=inner_bg,
        inner_card_fixed_width=inner_card_fixed_width,
    )


# ---------------------------------------------------------------------------
# Rule 8 — cornerRadius is source of truth
# ---------------------------------------------------------------------------


class TestRule8CornerRadius:
    def test_zero_radius_returns_square(self) -> None:
        node = _node(corner_radius=0)
        spec = rule_8_corner_radius(node)
        assert spec == CornerRadiusSpec(scalar=None, per_corner=None)

    def test_missing_radius_returns_square(self) -> None:
        node = _node(corner_radius=None)
        spec = rule_8_corner_radius(node)
        assert spec.scalar is None
        assert spec.per_corner is None

    def test_scalar_radius(self) -> None:
        node = _node(corner_radius=12.0)
        spec = rule_8_corner_radius(node)
        assert spec.scalar == 12.0
        assert spec.per_corner is None

    def test_per_corner_radius(self) -> None:
        node = _node(corner_radii=(6.0, 0.0, 0.0, 6.0))
        spec = rule_8_corner_radius(node)
        assert spec.scalar is None
        assert spec.per_corner == (6.0, 0.0, 0.0, 6.0)

    def test_per_corner_all_zero_falls_back_to_scalar(self) -> None:
        node = _node(corner_radii=(0.0, 0.0, 0.0, 0.0), corner_radius=8.0)
        spec = rule_8_corner_radius(node)
        # All-zero per-corner is treated as no per-corner override; use scalar.
        assert spec.scalar == 8.0
        assert spec.per_corner is None


# ---------------------------------------------------------------------------
# Rule 10 — image per-corner radii (alias of Rule 8 for image FRAMEs)
# ---------------------------------------------------------------------------


class TestRule10ImageCornerRadii:
    def test_image_per_corner(self) -> None:
        image_frame = _node(
            corner_radii=(6.0, 0.0, 0.0, 6.0),
            node_type=DesignNodeType.FRAME,
            image_ref="abc123",
        )
        spec = rule_10_image_corner_radii(image_frame)
        assert spec.per_corner == (6.0, 0.0, 0.0, 6.0)

    def test_image_no_radius(self) -> None:
        image_frame = _node(
            node_type=DesignNodeType.FRAME,
            image_ref="abc123",
        )
        spec = rule_10_image_corner_radii(image_frame)
        assert spec.scalar is None
        assert spec.per_corner is None


# ---------------------------------------------------------------------------
# Rule 11 — inner card width from dominant image width
# ---------------------------------------------------------------------------


class TestRule11CardWidth:
    def test_uniform_image_widths(self) -> None:
        children = [_node(width=440, node_id=f"img{i}", image_ref=f"r{i}") for i in range(4)]
        card = _node(width=480, children=children)
        spec = rule_11_card_width_from_dominant_image(card)
        assert spec is not None
        assert spec.fixed_width_px == 440
        assert spec.use_class == "wf"

    def test_dominant_image_width(self) -> None:
        widths = [440, 440, 440, 200, 300]
        children = [
            _node(width=w, node_id=f"img{i}", image_ref=f"r{i}") for i, w in enumerate(widths)
        ]
        card = _node(width=480, children=children)
        spec = rule_11_card_width_from_dominant_image(card)
        assert spec is not None
        assert spec.fixed_width_px == 440

    def test_no_dominant_width_returns_none(self) -> None:
        widths = [100, 200, 300, 400, 500]  # all distinct
        children = [
            _node(width=w, node_id=f"img{i}", image_ref=f"r{i}") for i, w in enumerate(widths)
        ]
        card = _node(width=600, children=children)
        spec = rule_11_card_width_from_dominant_image(card)
        assert spec is None

    def test_single_image_returns_none(self) -> None:
        card = _node(
            width=480,
            children=[_node(width=440, node_id="img1", image_ref="r1")],
        )
        spec = rule_11_card_width_from_dominant_image(card)
        assert spec is None


# ---------------------------------------------------------------------------
# Token override emissions in the matcher (Rules 7, 10, 11)
# ---------------------------------------------------------------------------


class TestTokenOverrideEmissions:
    def test_emits_rule_11_width_align_class(self) -> None:
        section = _section(inner_bg="#ffffff", inner_card_fixed_width=440)
        overrides = _build_token_overrides(section)
        targets = [(o.css_property, o.target_class, o.value) for o in overrides]
        assert ("width", "_inner", "440px") in targets
        assert ("__html_attr_align", "_inner", "center") in targets
        assert ("__html_attr_class_add", "_inner", "wf") in targets

    def test_emits_rule_10_per_corner_longhand(self) -> None:
        img = ImagePlaceholder(
            node_id="image-001",
            node_name="hero",
            width=440,
            height=320,
            corner_radius_spec=CornerRadiusSpec(scalar=None, per_corner=(6.0, 0.0, 0.0, 6.0)),
        )
        section = _section(images=[img])
        overrides = _build_token_overrides(section)
        per_corner = [
            o
            for o in overrides
            if o.target_class == "_image_image-001"
            and o.css_property.startswith("border-")
            and o.css_property.endswith("-radius")
        ]
        assert len(per_corner) == 4
        prop_to_value = {o.css_property: o.value for o in per_corner}
        assert prop_to_value == {
            "border-top-left-radius": "6px",
            "border-top-right-radius": "0px",
            "border-bottom-right-radius": "0px",
            "border-bottom-left-radius": "6px",
        }


# ---------------------------------------------------------------------------
# Verify ImagePlaceholder.corner_radius_spec / EmailSection.inner_card_fixed_width
# defaults stay None when no rule fires (regression for plan drift)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"width": 200, "height": 100},
        {"is_background": True},
    ],
)
def test_image_placeholder_default_corner_spec_none(kwargs: dict[str, object]) -> None:
    img = ImagePlaceholder(node_id="i", node_name="n", **kwargs)  # type: ignore[arg-type]
    assert img.corner_radius_spec is None
