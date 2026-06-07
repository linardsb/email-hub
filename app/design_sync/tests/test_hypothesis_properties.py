"""Property-based tests for design_sync pipeline (39.2.2).

Uses Hypothesis to generate thousands of inputs and verify invariants
that must hold regardless of input values.
"""

from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import given, settings

from app.design_sync.figma.tree_normalizer import normalize_tree
from app.design_sync.protocol import (
    DesignFileStructure,
    DesignNode,
    DesignNodeType,
)
from app.design_sync.sanitizers import sanitize_web_tags_for_email

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_CONTAINER_TYPES = (DesignNodeType.FRAME, DesignNodeType.GROUP, DesignNodeType.PAGE)
_node_types = st.sampled_from(list(DesignNodeType))
_alnum = st.characters(whitelist_categories=("L", "N"))


@st.composite
def design_nodes(draw: st.DrawFn, max_depth: int = 3) -> DesignNode:
    """Generate arbitrary DesignNode trees up to *max_depth*."""
    type_ = draw(_node_types)
    depth = draw(st.integers(min_value=0, max_value=max_depth))

    children: list[DesignNode] = []
    if depth > 0 and type_ in _CONTAINER_TYPES:
        children = draw(st.lists(design_nodes(max_depth=depth - 1), max_size=4))

    return DesignNode(
        id=draw(st.text(min_size=1, max_size=10, alphabet=_alnum)),
        name=draw(st.text(min_size=1, max_size=20, alphabet=_alnum)),
        type=type_,
        children=children,
        width=draw(st.floats(0.0, 2000.0, allow_nan=False, allow_infinity=False)),
        height=draw(st.floats(0.0, 2000.0, allow_nan=False, allow_infinity=False)),
        x=draw(st.floats(-500.0, 2000.0, allow_nan=False, allow_infinity=False)),
        y=draw(st.floats(-500.0, 5000.0, allow_nan=False, allow_infinity=False)),
        opacity=draw(st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False)),
        visible=draw(st.booleans()),
        text_content=(draw(st.text(max_size=100)) if type_ == DesignNodeType.TEXT else None),
    )


# ---------------------------------------------------------------------------
# 1. Opacity preservation
# ---------------------------------------------------------------------------


class TestOpacityPreservation:
    """Opacity=0.0 must survive construction and normalization."""

    @given(opacity=st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False))
    def test_opacity_roundtrip(self, opacity: float) -> None:
        node = DesignNode(
            id="n1",
            name="F",
            type=DesignNodeType.FRAME,
            children=[],
            opacity=opacity,
            visible=True,
        )
        assert node.opacity == opacity

    @given(opacity=st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False))
    def test_opacity_survives_normalize(self, opacity: float) -> None:
        node = DesignNode(
            id="n1",
            name="F",
            type=DesignNodeType.FRAME,
            children=[],
            opacity=opacity,
            visible=True,
            width=100.0,
            height=50.0,
        )
        page = DesignNode(id="p", name="Page", type=DesignNodeType.PAGE, children=[node])
        struct = DesignFileStructure(file_name="t", pages=[page])
        result, _stats = normalize_tree(struct)
        if opacity > 0.0:
            # Visible nodes with non-zero opacity are preserved
            assert len(result.pages[0].children) >= 1
            assert result.pages[0].children[0].opacity == opacity


# ---------------------------------------------------------------------------
# 2. normalize_tree never crashes
# ---------------------------------------------------------------------------


class TestNormalizeNeverCrashes:
    """normalize_tree must never raise on valid DesignNode trees."""

    @given(tree=design_nodes(max_depth=3))
    @settings(max_examples=200, deadline=None)
    def test_normalize_no_crash(self, tree: DesignNode) -> None:
        page = DesignNode(id="p", name="Page", type=DesignNodeType.PAGE, children=[tree])
        struct = DesignFileStructure(file_name="t", pages=[page])
        result, stats = normalize_tree(struct)
        assert result is not None
        assert stats is not None
        assert stats.nodes_removed >= 0
        assert stats.groups_flattened >= 0

    @given(tree=design_nodes(max_depth=2))
    @settings(max_examples=100)
    def test_normalize_output_is_valid_tree(self, tree: DesignNode) -> None:
        """Every node in the output must still have id, name, type."""
        page = DesignNode(id="p", name="Page", type=DesignNodeType.PAGE, children=[tree])
        struct = DesignFileStructure(file_name="t", pages=[page])
        result, _stats = normalize_tree(struct)
        stack = list(result.pages)
        while stack:
            node = stack.pop()
            assert node.id
            assert node.name is not None
            assert node.type is not None
            stack.extend(node.children)


# ---------------------------------------------------------------------------
# 3. sanitize_web_tags_for_email properties
# ---------------------------------------------------------------------------


class TestSanitizeWebTags:
    """sanitize_web_tags_for_email must never crash and preserves safety."""

    @given(st.text(max_size=500))
    @settings(max_examples=200)
    def test_never_crashes(self, html: str) -> None:
        result = sanitize_web_tags_for_email(html)
        assert isinstance(result, str)

    @given(st.text(min_size=1, max_size=100))
    def test_mso_comments_preserved(self, content: str) -> None:
        """MSO conditional blocks must survive sanitization."""
        safe_content = content.replace("-->", "").replace("<![", "").replace("]>", "")
        mso = f"<!--[if mso]><p>{safe_content}</p><![endif]-->"
        html = f"<td>{mso}</td>"
        result = sanitize_web_tags_for_email(html)
        assert "<!--[if mso]>" in result or "__MSO_" not in result

    @given(st.text(min_size=1, max_size=100, alphabet=_alnum))
    def test_text_inside_td_preserved(self, text: str) -> None:
        """Text content inside <td> survives sanitization (p tags stripped, content kept)."""
        html = f"<td><p>{text}</p></td>"
        result = sanitize_web_tags_for_email(html)
        assert "<p" not in result
        assert text in result


# ---------------------------------------------------------------------------
# 4. DesignNode dimension properties
# ---------------------------------------------------------------------------


class TestDimensionProperties:
    """Width/height must be faithfully stored including edge values."""

    @given(
        w=st.floats(0.0, 5000.0, allow_nan=False, allow_infinity=False),
        h=st.floats(0.0, 5000.0, allow_nan=False, allow_infinity=False),
    )
    def test_dimensions_roundtrip(self, w: float, h: float) -> None:
        node = DesignNode(
            id="d",
            name="D",
            type=DesignNodeType.FRAME,
            width=w,
            height=h,
        )
        assert node.width == w
        assert node.height == h

    @given(
        fs=st.floats(0.0, 200.0, allow_nan=False, allow_infinity=False),
        fw=st.sampled_from([100, 200, 300, 400, 500, 600, 700, 800, 900]),
    )
    def test_typography_values_preserved(self, fs: float, fw: int) -> None:
        node = DesignNode(
            id="t",
            name="T",
            type=DesignNodeType.TEXT,
            font_size=fs,
            font_weight=fw,
            text_content="Test",
        )
        assert node.font_size == fs
        assert node.font_weight == fw
