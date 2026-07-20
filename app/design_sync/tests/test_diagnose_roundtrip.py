"""Round-trip parity for the diagnose/report.py structure serializer.

Guards `phase-53.3-line-height-relative-loader-gap`: the
``load_structure_from_json`` loader that feeds the ENTIRE corpus harness
(snapshot-test, converter-data-regression, service.py) round-trips through
``report.py:_node_from_dict``. If that loader drops a DesignNode field, the
whole harness silently loses it — the exact drift that left
``line_height_relative`` (52.5) out of the loader while ``_dataclass_to_dict``
kept dumping it.

This is a DIFFERENT serializer from ``_serialization.py`` (the app cache path,
covered by test_serialization_roundtrip.py / #327). Neither test substitutes
for the other.
"""

from __future__ import annotations

import dataclasses

from app.design_sync.diagnose.report import (
    _dataclass_to_dict,
    _dict_to_structure,
    _node_from_dict,
    _structure_to_dict,
)
from app.design_sync.protocol import (
    DesignFileStructure,
    DesignNode,
    DesignNodeType,
    StyleRun,
)


def _sentinel_node() -> DesignNode:
    """A DesignNode carrying a distinct, non-default value on EVERY field.

    Distinct values make a silently-dropped field surface as ``got != node``
    (the loader falls the field back to None / its default).
    """
    child = DesignNode(id="child-1", name="child", type=DesignNodeType.TEXT, text_content="c")
    return DesignNode(
        id="node-diag-1",
        name="diag-node",
        type=DesignNodeType.TEXT,
        children=[child],
        width=520.0,
        height=44.0,
        x=12.0,
        y=34.0,
        text_content="Hello diagnose",
        fill_color="#112233",
        text_color="#445566",
        padding_top=1.0,
        padding_right=2.0,
        padding_bottom=3.0,
        padding_left=4.0,
        item_spacing=8.0,
        counter_axis_spacing=6.0,
        layout_mode="HORIZONTAL",
        font_family="Noto Sans",
        font_size=14.0,
        font_weight=700,
        line_height_px=20.0,
        line_height_relative=1.4,  # the 52.5 field the loader dropped
        letter_spacing_px=0.5,
        text_transform="uppercase",
        text_decoration="underline",
        image_ref="ref-hash-abc",
        hyperlink="https://example.com/x",
        corner_radius=25.0,
        corner_radii=(4.0, 4.0, 12.0, 12.0),
        text_align="center",
        primary_axis_align="space-between",
        counter_axis_align="center",
        stroke_weight=2.0,
        stroke_color="#778899",
        style_runs=(StyleRun(start=0, end=5, bold=True, color_hex="#000000"),),
        visible=False,
        opacity=0.5,
        scale_mode="FILL",
        rotation=1.5,
        effects_summary="1:DROP_SHADOW",
    )


class TestDiagnoseNodeParity:
    def test_full_field_parity_through_report_serializer(self) -> None:
        """Every DesignNode field must survive _dataclass_to_dict → _node_from_dict.

        Fails when a field is added to DesignNode but not to the report.py loader
        — the drift that dropped line_height_relative from the corpus harness.
        """
        node = _sentinel_node()
        got = _node_from_dict(_dataclass_to_dict(node))
        for f in dataclasses.fields(DesignNode):
            if f.name == "children":
                continue
            assert getattr(got, f.name) == getattr(node, f.name), f.name

    def test_children_survive(self) -> None:
        node = _sentinel_node()
        got = _node_from_dict(_dataclass_to_dict(node))
        assert len(got.children) == 1
        assert got.children[0].id == "child-1"
        assert got.children[0].text_content == "c"

    def test_line_height_relative_survives_reload(self) -> None:
        """The 52.5 AUTO/% line height must survive the real structure loader path.

        Exercises load_structure_from_json's serializer pair
        (_structure_to_dict → _dict_to_structure → _node_from_dict), the loader
        that feeds snapshot-test / converter-data-regression.
        """
        node = _sentinel_node()
        structure = DesignFileStructure(file_name="diag.fig", pages=[node])
        got = _dict_to_structure(_structure_to_dict(structure))
        assert got.pages[0].line_height_relative == 1.4
