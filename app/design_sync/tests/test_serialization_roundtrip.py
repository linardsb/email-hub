"""Round-trip tests for the snapshot `_file_structure` node serializer.

Guards `phase-53f-app-snapshot-serializer-drops-render-fields`: every
render-bearing DesignNode field must survive serialize_node →
cached_dict_to_node, or app-side conversions render CTAs without stroke,
radius, alignment, or per-node text colour while the fixture harness (which
loads structure.json with the full-field loader) renders them correctly.
"""

from __future__ import annotations

from app.design_sync.protocol import DesignNode, DesignNodeType, StyleRun
from app.design_sync.services._serialization import cached_dict_to_node, serialize_node


def _outlined_cta_node() -> DesignNode:
    """The LEGO 'Explore now' shape: white fill, 2px black stroke, r25, black text child."""
    label = DesignNode(
        id="2833:1891",
        name="mj-button-text",
        type=DesignNodeType.TEXT,
        text_content="Explore now",
        text_color="#000000",
        font_family="Noto Sans",
        font_size=14.0,
        font_weight=700,
        text_align="center",
        style_runs=(StyleRun(start=0, end=7, bold=True, color_hex="#000000"),),
    )
    return DesignNode(
        id="2833:1890",
        name="mj-button",
        type=DesignNodeType.FRAME,
        children=[label],
        width=126.0,
        height=43.0,
        fill_color="#FFFFFF",
        corner_radius=25.0,
        stroke_weight=2.0,
        stroke_color="#000000",
        primary_axis_align="center",
        counter_axis_align="center",
        hyperlink="https://lego.com/halloween",
    )


def _roundtrip(node: DesignNode) -> DesignNode:
    return cached_dict_to_node(serialize_node(node))


class TestRenderFieldRoundTrip:
    def test_button_stroke_and_radius_survive(self) -> None:
        got = _roundtrip(_outlined_cta_node())
        assert got.corner_radius == 25.0
        assert got.stroke_weight == 2.0
        assert got.stroke_color == "#000000"

    def test_axis_alignment_survives(self) -> None:
        got = _roundtrip(_outlined_cta_node())
        assert got.primary_axis_align == "center"
        assert got.counter_axis_align == "center"

    def test_text_child_color_align_and_style_runs_survive(self) -> None:
        got = _roundtrip(_outlined_cta_node())
        label = got.children[0]
        assert label.text_color == "#000000"
        assert label.text_align == "center"
        assert label.style_runs == (StyleRun(start=0, end=7, bold=True, color_hex="#000000"),)

    def test_hyperlink_survives(self) -> None:
        got = _roundtrip(_outlined_cta_node())
        assert got.hyperlink == "https://lego.com/halloween"

    def test_corner_radii_tuple_survives(self) -> None:
        node = DesignNode(
            id="n1",
            name="pill",
            type=DesignNodeType.FRAME,
            corner_radii=(4.0, 4.0, 12.0, 12.0),
        )
        assert _roundtrip(node).corner_radii == (4.0, 4.0, 12.0, 12.0)

    def test_image_ref_and_opacity_and_visible_survive(self) -> None:
        node = DesignNode(
            id="n2",
            name="hero",
            type=DesignNodeType.FRAME,
            image_ref="abc123hash",
            visible=False,
            opacity=0.5,
            line_height_relative=1.4,
        )
        got = _roundtrip(node)
        assert got.image_ref == "abc123hash"
        assert got.visible is False
        assert got.opacity == 0.5
        assert got.line_height_relative == 1.4

    def test_defaults_stay_compact_and_default(self) -> None:
        node = DesignNode(id="n3", name="plain", type=DesignNodeType.FRAME)
        data = serialize_node(node)
        # Default visible/opacity/style_runs are omitted from the cache dict...
        assert "visible" not in data
        assert "opacity" not in data
        assert "style_runs" not in data
        # ...and deserialize back to their defaults.
        got = cached_dict_to_node(data)
        assert got.visible is True
        assert got.opacity == 1.0
        assert got.style_runs == ()

    def test_full_field_parity_with_protocol(self) -> None:
        """Every dataclass field on DesignNode must round-trip the cache.

        Fails when a new render field is added to DesignNode but not to the
        serializer pair — the exact drift that caused the app-vs-harness split.
        """
        import dataclasses

        node = _outlined_cta_node()
        got = _roundtrip(node)
        for f in dataclasses.fields(DesignNode):
            if f.name == "children":
                continue
            assert getattr(got, f.name) == getattr(node, f.name), f.name
