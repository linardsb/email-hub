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
from app.design_sync.protocol import DesignFileStructure, DesignNode
from app.design_sync.tests.conftest import make_full_design_node, non_default_field_names


class TestDiagnoseNodeParity:
    def test_sentinel_sets_every_field(self) -> None:
        """The shared sentinel must carry a non-default value on every field.

        Fails when DesignNode grows a field the sentinel does not set, so both
        serializer parity tests keep covering every field.
        """
        all_fields = {f.name for f in dataclasses.fields(DesignNode)}
        assert non_default_field_names(make_full_design_node()) | {"children"} == all_fields

    def test_full_field_parity_through_report_serializer(self) -> None:
        """Every DesignNode field must survive _dataclass_to_dict → _node_from_dict.

        Fails when a field is added to DesignNode but not to the report.py loader
        — the drift that dropped line_height_relative from the corpus harness.
        """
        node = make_full_design_node()
        got = _node_from_dict(_dataclass_to_dict(node))
        for f in dataclasses.fields(DesignNode):
            if f.name == "children":
                continue
            assert getattr(got, f.name) == getattr(node, f.name), f.name

    def test_children_survive(self) -> None:
        node = make_full_design_node()
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
        node = make_full_design_node()
        structure = DesignFileStructure(file_name="diag.fig", pages=[node])
        got = _dict_to_structure(_structure_to_dict(structure))
        assert got.pages[0].line_height_relative == 1.4
