"""Tests for 51.1 composite-slot infrastructure.

``render_composite`` (the depth-capped sub-renderer) + ``_splice_rows_after_slot``
(the injection primitive). The nested-table splice case (8e) is the regression
guard that a naive forward ``find("</tr>")`` would fail (c10's ``_per_node_body_html``
body cell wraps a ``<table>``).
"""

from __future__ import annotations

from app.design_sync.component_matcher import (
    CompositeSlot,
    SlotFill,
    render_composite,
)
from app.design_sync.component_renderer import ComponentRenderer

# ── render_composite ──────────────────────────────────────────────────


class TestRenderComposite:
    def test_depth1_terminal_children_concat_and_center_wrap(self) -> None:
        cs = CompositeSlot(
            children=(SlotFill("x", "A"), SlotFill("y", "B")),
            after_slot="body",
            cell_style="padding:0 24px 24px;",
            child_separator="\n",
        )
        html = render_composite(cs)
        assert html == '<tr><td align="center" style="padding:0 24px 24px;">A\nB</td></tr>'

    def test_align_and_style_from_composite(self) -> None:
        cs = CompositeSlot(children=(SlotFill("x", "Z"),), after_slot="body", align="left")
        assert '<td align="left" style="">' in render_composite(cs)

    def test_depth2_composite_child_recurses(self) -> None:
        inner = CompositeSlot(children=(SlotFill("z", "INNER"),), after_slot="body")
        outer = CompositeSlot(
            children=(SlotFill("c", "", slot_type="composite", composite=inner),),
            after_slot="body",
        )
        html = render_composite(outer)
        # the inner composite renders as a nested <tr> inside the outer cell
        assert html.count("<tr>") == 2
        assert "INNER" in html

    def test_mislabeled_composite_child_without_payload_degrades_to_value(self) -> None:
        # slot_type == "composite" but composite is None → falls back to .value
        cs = CompositeSlot(
            children=(SlotFill("c", "FALLBACK", slot_type="composite", composite=None),),
            after_slot="body",
        )
        assert "FALLBACK" in render_composite(cs)

    def test_depth_cap_truncates_at_depth4(self) -> None:
        # A chain 4 composites deep: the depth-4 re-entry returns "" (leaf never
        # renders); depth 3 still renders. Guards against unbounded recursion.
        def chain(n: int) -> CompositeSlot:
            if n == 0:
                return CompositeSlot(children=(SlotFill("leaf", "LEAF"),), after_slot="body")
            child = SlotFill("c", "", slot_type="composite", composite=chain(n - 1))
            return CompositeSlot(children=(child,), after_slot="body")

        html = render_composite(chain(4))
        assert "LEAF" not in html  # truncated at the cap
        # three nested rows render (depths 1,2,3), the deepest cell is empty
        assert html.count("<tr>") == 3


# ── _splice_rows_after_slot ───────────────────────────────────────────


class TestSpliceRowsAfterSlot:
    def test_splices_after_the_slot_row(self) -> None:
        html = (
            "<table>"
            '<tr><td data-slot="heading">H</td></tr>'
            '<tr><td data-slot="body">B</td></tr>'
            "</table>"
        )
        row = '<tr><td align="center">CTA</td></tr>'
        out = ComponentRenderer._splice_rows_after_slot(html, "body", row)
        # the new row lands between the body </tr> and </table>, not inside body
        assert out == (
            "<table>"
            '<tr><td data-slot="heading">H</td></tr>'
            '<tr><td data-slot="body">B</td></tr>'
            '<tr><td align="center">CTA</td></tr>'
            "</table>"
        )

    def test_noop_when_slot_absent(self) -> None:
        html = '<table><tr><td data-slot="heading">H</td></tr></table>'
        out = ComponentRenderer._splice_rows_after_slot(html, "body", "<tr><td>X</td></tr>")
        assert out == html  # defensive no-op, no dropped row mid-table

    def test_nested_table_body_splices_after_outer_row(self) -> None:
        # REGRESSION GUARD (8e): a <td data-slot="body"> wrapping a nested
        # <table><tr>...</tr></table> (c10's _per_node_body_html shape). A naive
        # forward find("</tr>") would splice INSIDE the body cell at the inner
        # </tr>; the depth-counted _find_matching_close must reach the OUTER </tr>.
        html = (
            "<table>"
            '<tr><td data-slot="body">'
            "<table><tr><td>para1</td></tr><tr><td>para2</td></tr></table>"
            "</td></tr>"
            "</table>"
        )
        row = '<tr><td align="center">CTA</td></tr>'
        out = ComponentRenderer._splice_rows_after_slot(html, "body", row)
        # CTA row must sit AFTER the outer body </tr>, i.e. the nested table
        # (para2) is fully closed before the CTA row appears.
        assert out.index("para2") < out.index("CTA")
        body_cell = out.split('data-slot="body"')[1].split("CTA")[0]
        assert 'align="center">CTA' not in body_cell  # not inside the body cell
        assert out.endswith('<tr><td align="center">CTA</td></tr></table>')
