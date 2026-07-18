"""Full round-trip property tests for the EmailDesignDocument bridge (Phase 52.3).

Closes RC-B: the ``Document*`` dataclasses were narrower than the rich
``EmailSection`` / ``TextBlock`` / ``ImagePlaceholder`` / ``ButtonElement`` types,
so many fields were silently dropped on the round trip — making shipped Phase
49/50 fidelity logic inert.

The decisive gate is ``test_full_roundtrip_preserves_every_field``: it builds an
``EmailSection`` with every widened field set to a distinct non-default sentinel,
then asserts full structural equality through all four bridge boundaries::

    EmailSection
      -> DocumentSection.from_email_section   (writer)
      -> .to_json -> json.loads -> .from_json (serialize boundary)
      -> .to_email_section                    (reader)
      == EmailSection'

If any field is dropped at any boundary, ``==`` fails. ``validate() == []`` is
the only check that exercises the JSON-Schema ``additionalProperties: false``
fixes, so it is asserted explicitly.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from app.design_sync.email_design_document import (
    DocumentLayout,
    DocumentSection,
    DocumentTokens,
    EmailDesignDocument,
)
from app.design_sync.figma.layout_analyzer import (
    ButtonElement,
    ColumnGroup,
    ColumnLayout,
    ContentGroup,
    EmailSection,
    EmailSectionType,
    ImagePlaceholder,
    TextBlock,
)
from app.design_sync.frame_rules import CornerRadiusSpec
from app.design_sync.protocol import StyleRun

# ── Sentinel builders — every value is distinct so a mis-wired field is caught ──


def _full_text_block(prefix: str) -> TextBlock:
    """A TextBlock with every widened field set to a distinct non-default value.

    ``source_frame_id`` is deliberately left at its default — it is out of scope
    for 52.3 and is lossy-by-design through the bridge (see module docstring of
    the bridge file / task report).
    """
    return TextBlock(
        node_id=f"{prefix}-text-1",
        content=f"{prefix} body copy",
        font_size=18.0,
        is_heading=True,
        font_family="Inter",
        font_weight=700,
        line_height=24.0,
        letter_spacing=0.5,
        text_color="#112233",
        text_align="center",
        hyperlink="https://example.com/text-link",
        style_runs=(
            StyleRun(
                start=0,
                end=4,
                bold=True,
                italic=True,
                underline=True,
                strikethrough=True,
                color_hex="#445566",
                font_size=20.0,
                link_url="https://example.com/run-link",
            ),
            StyleRun(start=5, end=8, bold=False, color_hex="#778899"),
        ),
        text_transform="uppercase",
        text_decoration="underline",
        role_hint="heading",
    )


def _full_image(prefix: str) -> ImagePlaceholder:
    return ImagePlaceholder(
        node_id=f"{prefix}-img-1",
        node_name=f"{prefix} hero image",
        width=600.0,
        height=300.0,
        is_background=True,
        export_node_id=f"{prefix}-export-99",
        corner_radius_spec=CornerRadiusSpec(scalar=None, per_corner=(8.0, 8.0, 0.0, 0.0)),
        # 53.5 — non-button border (52.5 capture; schema gained the fields).
        stroke_color="#334455",
        stroke_weight=1.5,
    )


def _full_button(prefix: str) -> ButtonElement:
    return ButtonElement(
        node_id=f"{prefix}-btn-1",
        text=f"{prefix} CTA",
        width=200.0,
        height=48.0,
        fill_color="#aabbcc",
        url="https://example.com/cta",
        border_radius=6.0,
        text_color="#ffffff",
        stroke_color="#001122",
        stroke_weight=2.0,
        icon_node_id=f"{prefix}-icon-42",
        corner_radius_spec=CornerRadiusSpec(scalar=12.0, per_corner=None),
    )


def _full_section() -> EmailSection:
    """An EmailSection populated with every widened field at non-default values.

    Padding: all four set (the writer flattens any-set padding to all-four-floats
    and the reader cannot recover Nones — so a clean ``==`` requires all-set).
    """
    return EmailSection(
        section_type=EmailSectionType.CONTENT,
        node_id="sec-1",
        node_name="Content Section",
        y_position=120.0,
        width=600.0,
        height=400.0,
        column_layout=ColumnLayout.TWO_COLUMN,
        column_count=2,
        texts=[_full_text_block("sec")],
        images=[_full_image("sec")],
        buttons=[_full_button("sec")],
        spacing_after=32.0,
        bg_color="#f5f5f5",
        padding_top=10.0,
        padding_right=20.0,
        padding_bottom=30.0,
        padding_left=40.0,
        item_spacing=16.0,
        element_gaps=(8.0, 12.0),
        column_groups=[
            ColumnGroup(
                column_idx=0,
                node_id="col-0",
                node_name="Left Column",
                width=280.0,
                texts=[_full_text_block("col")],
                images=[_full_image("col")],
                buttons=[_full_button("col")],
            )
        ],
        classification_confidence=0.87,
        vlm_classification="hero",
        vlm_confidence=0.91,
        content_roles=("heading", "body", "cta"),
        child_content_groups=[
            ContentGroup(
                frame_node_id="grp-1",
                frame_name="Reason Block",
                texts=[_full_text_block("grp")],
                images=[_full_image("grp")],
                buttons=[_full_button("grp")],
            )
        ],
        boundary_above="darker",
        boundary_below="lighter",
        sampled_top_color="#101010",
        sampled_bottom_color="#202020",
        container_bg="#cfff00",
        parent_wrapper_id="wrap-1",
        inner_bg="#ffffff",
        inner_radius=14.0,
        inner_card_fixed_width=480,
        is_physical_card_surface=True,
        physical_card_signals=("aspect_ratio", "rounded_corners"),
        # 53.3b/a — gradient reattach ref + dropped-effects summary.
        gradient_ref="grad-node-1",
        effects_summary="2:DROP_SHADOW,LAYER_BLUR",
        # 53.5 — divider stroke (lifted from the zero-area LINE child).
        stroke_color="#545454",
        stroke_weight=2.0,
    )


def _roundtrip(section: EmailSection) -> EmailSection:
    """Run a section through all four bridge boundaries and back."""
    doc_section = DocumentSection.from_email_section(section)
    serialized = json.loads(json.dumps(doc_section.to_json()))
    rebuilt = DocumentSection.from_json(serialized)
    return rebuilt.to_email_section()


# ── 1. The decisive gate: full structural equality through every boundary ──


def test_full_roundtrip_preserves_every_field() -> None:
    original = _full_section()
    result = _roundtrip(original)
    assert result == original


def test_full_roundtrip_is_idempotent() -> None:
    """A second pass must be a fixed point — proves no lossy normalization."""
    original = _full_section()
    once = _roundtrip(original)
    twice = _roundtrip(once)
    assert twice == once


def test_full_document_passes_json_schema() -> None:
    """The only check that exercises the schema's ``additionalProperties: false``.

    Verifies that every field ``to_json`` emits is permitted by the schema —
    closes the existing holes (text lacked ``text_align``; button lacked
    ``url`` / ``border_radius`` / ``fill_color``).
    """
    doc = EmailDesignDocument(
        version="1.0",
        tokens=DocumentTokens(),
        sections=[DocumentSection.from_email_section(_full_section())],
        layout=DocumentLayout(container_width=600),
    )
    payload = doc.to_json()
    errors = EmailDesignDocument.validate(payload)
    assert errors == [], f"schema rejected fields to_json emits: {errors}"


# ── 2. Per-field assertions (explicit, so a failure names the dropped field) ──


def test_text_fields_survive() -> None:
    result = _roundtrip(_full_section())
    t = result.texts[0]
    original = _full_text_block("sec")
    assert t.text_transform == original.text_transform
    assert t.text_decoration == original.text_decoration
    assert t.role_hint == original.role_hint
    assert t.hyperlink == original.hyperlink
    assert t.style_runs == original.style_runs
    assert isinstance(t.style_runs, tuple)


def test_image_fields_survive() -> None:
    result = _roundtrip(_full_section())
    i = result.images[0]
    original = _full_image("sec")
    assert i.export_node_id == original.export_node_id
    assert i.corner_radius_spec == original.corner_radius_spec
    assert i.corner_radius_spec is not None
    assert i.corner_radius_spec.per_corner == (8.0, 8.0, 0.0, 0.0)


def test_button_fields_survive() -> None:
    result = _roundtrip(_full_section())
    b = result.buttons[0]
    original = _full_button("sec")
    assert b.text_color == original.text_color
    assert b.stroke_color == original.stroke_color
    assert b.stroke_weight == original.stroke_weight
    assert b.icon_node_id == original.icon_node_id
    assert b.corner_radius_spec == original.corner_radius_spec
    assert b.corner_radius_spec is not None
    assert b.corner_radius_spec.scalar == 12.0


def test_section_phase50_fields_survive() -> None:
    result = _roundtrip(_full_section())
    original = _full_section()
    for fld in (
        "boundary_above",
        "boundary_below",
        "sampled_top_color",
        "sampled_bottom_color",
        "container_bg",
        "parent_wrapper_id",
        "inner_bg",
        "inner_radius",
        "inner_card_fixed_width",
        "is_physical_card_surface",
        "physical_card_signals",
        "vlm_classification",
        "vlm_confidence",
    ):
        assert getattr(result, fld) == getattr(original, fld), f"{fld} dropped"
    assert isinstance(result.physical_card_signals, tuple)


def test_child_content_groups_survive() -> None:
    result = _roundtrip(_full_section())
    original = _full_section()
    assert result.child_content_groups == original.child_content_groups
    grp = result.child_content_groups[0]
    assert grp.texts[0].style_runs == _full_text_block("grp").style_runs
    assert grp.buttons[0].corner_radius_spec is not None


def test_column_group_fields_survive() -> None:
    result = _roundtrip(_full_section())
    original = _full_section()
    assert result.column_groups == original.column_groups


# ── 3. Backward compatibility: old (narrow) persisted JSON still loads ──


def test_legacy_minimal_json_still_deserializes() -> None:
    """A pre-52.3 document (no widened keys) must still load without KeyError."""
    legacy = {
        "id": "old-sec",
        "type": "content",
        "texts": [{"node_id": "t1", "content": "hello", "color": "#000000"}],
        "buttons": [{"node_id": "b1", "text": "Go", "url": "https://x.test"}],
        "images": [{"node_id": "i1", "node_name": "img"}],
    }
    sec = DocumentSection.from_json(legacy)
    assert sec.id == "old-sec"
    assert sec.texts[0].color == "#000000"
    assert sec.texts[0].style_runs == ()
    assert sec.texts[0].text_transform is None
    assert sec.images[0].corner_radius_spec is None
    assert sec.buttons[0].corner_radius_spec is None
    assert sec.child_content_groups == []
    es = sec.to_email_section()
    assert es.texts[0].text_color == "#000000"


# ── 4. Hypothesis: any combination of optional fields round-trips cleanly ──

_opt_str = st.one_of(st.none(), st.text(min_size=1, max_size=12))
_opt_float = st.one_of(st.none(), st.floats(0.0, 100.0, allow_nan=False, allow_infinity=False))


@st.composite
def _text_blocks(draw: st.DrawFn) -> TextBlock:
    return TextBlock(
        node_id=draw(st.text(min_size=1, max_size=8)),
        content=draw(st.text(max_size=20)),
        font_size=draw(_opt_float),
        is_heading=draw(st.booleans()),
        text_color=draw(_opt_str),
        text_align=draw(st.one_of(st.none(), st.sampled_from(["left", "center", "right"]))),
        hyperlink=draw(_opt_str),
        text_transform=draw(st.one_of(st.none(), st.sampled_from(["uppercase", "lowercase"]))),
        text_decoration=draw(st.one_of(st.none(), st.sampled_from(["underline", "line-through"]))),
        role_hint=draw(st.one_of(st.none(), st.sampled_from(["heading", "body", "cta"]))),
        style_runs=tuple(
            draw(
                st.lists(
                    st.builds(
                        StyleRun,
                        start=st.integers(0, 5),
                        end=st.integers(5, 10),
                        bold=st.booleans(),
                        color_hex=_opt_str,
                        link_url=_opt_str,
                    ),
                    max_size=3,
                )
            )
        ),
    )


@st.composite
def _sections(draw: st.DrawFn) -> EmailSection:
    return EmailSection(
        section_type=draw(st.sampled_from(list(EmailSectionType))),
        node_id=draw(st.text(min_size=1, max_size=8)),
        node_name=draw(st.text(min_size=1, max_size=12)),
        texts=draw(st.lists(_text_blocks(), max_size=3)),
        boundary_above=draw(_opt_str),
        boundary_below=draw(_opt_str),
        sampled_top_color=draw(_opt_str),
        sampled_bottom_color=draw(_opt_str),
        container_bg=draw(_opt_str),
        parent_wrapper_id=draw(_opt_str),
        inner_bg=draw(_opt_str),
        inner_radius=draw(_opt_float),
        inner_card_fixed_width=draw(st.one_of(st.none(), st.integers(100, 800))),
        is_physical_card_surface=draw(st.booleans()),
        physical_card_signals=tuple(draw(st.lists(st.text(min_size=1, max_size=8), max_size=3))),
        vlm_classification=draw(_opt_str),
        vlm_confidence=draw(st.one_of(st.none(), st.floats(0.0, 1.0, allow_nan=False))),
    )


@settings(max_examples=200)
@given(section=_sections())
def test_property_arbitrary_sections_roundtrip(section: EmailSection) -> None:
    assert _roundtrip(section) == section


# ── 5. Real fixtures: no populated field is lost across the bridge ──
#
# The fixtures start from ``analyze_layout`` output — the FIRST writer
# (``from_email_section``) has not yet run, so this is the only place that
# verifies the writer preserves real, converter-produced field values (the
# constructed sentinel test above is the synthetic analogue). The check is
# DIRECTIONAL, not full ``==``: two fields are lossy-by-design through the
# bridge and would break ``==`` for reasons unrelated to 52.3 —
#   * padding: the writer flattens any-set padding (None -> 0.0); the reader
#     cannot recover the Nones.
#   * ``TextBlock.source_frame_id``: out of scope for 52.3; intentionally dropped.
# So we assert that every WIDENED field that is non-default pre-roundtrip is
# still non-default (and equal) post-roundtrip — i.e. the bridge never silently
# drops a field the converter populated.

_DEBUG_DIR = Path(__file__).resolve().parents[3] / "data" / "debug"
_FIXTURE_CASES = sorted(
    p.parent.name
    for p in _DEBUG_DIR.glob("*/structure.json")
    if (p.parent / "tokens.json").exists()
)

_TEXT_FIELDS = (
    "text_transform",
    "text_decoration",
    "hyperlink",
    "role_hint",
    "style_runs",
)
_IMAGE_FIELDS = ("export_node_id", "corner_radius_spec")
_BUTTON_FIELDS = (
    "text_color",
    "stroke_color",
    "stroke_weight",
    "icon_node_id",
    "corner_radius_spec",
)
# ``child_content_groups`` is NOT compared whole-object here: ContentGroup's
# nested TextBlocks carry ``source_frame_id`` (out of scope for 52.3,
# lossy-by-design), so a whole-object ``==`` would trip on it. Instead the
# group structure is checked by count below, and every WIDENED field inside the
# groups is checked element-wise via the recursive iterators (which descend into
# child_content_groups).
_SECTION_FIELDS = (
    "boundary_above",
    "boundary_below",
    "sampled_top_color",
    "sampled_bottom_color",
    "container_bg",
    "parent_wrapper_id",
    "inner_bg",
    "inner_radius",
    "inner_card_fixed_width",
    "is_physical_card_surface",
    "physical_card_signals",
    "vlm_classification",
    "vlm_confidence",
)

_EMPTY: tuple[object, ...] = (None, (), [], False, 0)


def _assert_fields_preserved(
    label: str, before: object, after: object, fields: tuple[str, ...]
) -> int:
    """Assert each non-default field on *before* is unchanged on *after*. Returns hits."""
    hits = 0
    for fld in fields:
        bval = getattr(before, fld)
        if bval in _EMPTY:
            continue
        aval = getattr(after, fld)
        assert aval == bval, f"{label}.{fld}: {bval!r} (before) != {aval!r} (after)"
        hits += 1
    return hits


def _iter_text_blocks(section: EmailSection) -> Iterator[TextBlock]:
    yield from section.texts
    for c in section.column_groups:
        yield from c.texts
    for g in section.child_content_groups:
        yield from g.texts


def _iter_images(section: EmailSection) -> Iterator[ImagePlaceholder]:
    yield from section.images
    for c in section.column_groups:
        yield from c.images
    for g in section.child_content_groups:
        yield from g.images


def _iter_buttons(section: EmailSection) -> Iterator[ButtonElement]:
    yield from section.buttons
    for c in section.column_groups:
        yield from c.buttons
    for g in section.child_content_groups:
        yield from g.buttons


@pytest.mark.skipif(not _FIXTURE_CASES, reason="data/debug fixtures not present (gitignored)")
@pytest.mark.parametrize("case", _FIXTURE_CASES)
def test_real_fixture_widened_fields_survive_bridge(case: str) -> None:
    """No widened field the converter populated is dropped across the full bridge.

    Starts from ``analyze_layout`` (pre-writer) so the FIRST writer is exercised.
    Directional, per-field, indexed by node_id so column/content-group nesting is
    matched correctly. Asserts at least one widened field was actually exercised
    across the corpus (guards against a vacuous pass).
    """
    from app.design_sync.diagnose.report import (
        load_structure_from_json,
        load_tokens_from_json,
    )
    from app.design_sync.figma.layout_analyzer import analyze_layout

    case_dir = _DEBUG_DIR / case
    structure = load_structure_from_json(case_dir / "structure.json")
    _tokens = load_tokens_from_json(case_dir / "tokens.json")
    layout = analyze_layout(structure)

    total_hits = 0
    for orig in layout.sections:
        after = _roundtrip(orig)
        total_hits += _assert_fields_preserved(
            f"{case}:{orig.node_id}", orig, after, _SECTION_FIELDS
        )

        # child_content_groups: structure (count) must survive; their inner
        # widened fields are checked element-wise by the recursive iterators.
        assert len(after.child_content_groups) == len(orig.child_content_groups), (
            f"{case}:{orig.node_id}: child_content_groups count changed"
        )
        if orig.child_content_groups:
            total_hits += 1

        for ot, at_ in zip(_iter_text_blocks(orig), _iter_text_blocks(after), strict=True):
            total_hits += _assert_fields_preserved(
                f"{case}:text:{ot.node_id}", ot, at_, _TEXT_FIELDS
            )
        for oi, ai in zip(_iter_images(orig), _iter_images(after), strict=True):
            total_hits += _assert_fields_preserved(
                f"{case}:img:{oi.node_id}", oi, ai, _IMAGE_FIELDS
            )
        for obn, abn in zip(_iter_buttons(orig), _iter_buttons(after), strict=True):
            total_hits += _assert_fields_preserved(
                f"{case}:btn:{obn.node_id}", obn, abn, _BUTTON_FIELDS
            )

    # The fixtures are known to populate widened fields (style_runs, role_hint,
    # export_node_id, corner_radius_spec, container_bg, child_content_groups, ...).
    # A zero-hit pass would mean the test is vacuous — fail loudly instead.
    assert total_hits > 0, f"case {case}: no widened field exercised — test is vacuous"
